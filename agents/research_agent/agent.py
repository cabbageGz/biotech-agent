from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import re
from typing import Any

from agents.topic_agent import TopicClusterer, TopicScorer
from tools.clinicaltrials import ClinicalTrialsClient
from tools.fda import OpenFDAClient
from tools.llm import DeepSeekClient, LLMError
from tools.pubmed import PubMedClient
from tools.rss.reader import RSSItem, RSSReader
from tools.scraper.extractor import compact_text


@dataclass
class Hotspot:
    title: str
    source: str
    url: str
    published: str
    summary: str
    why_it_matters: str
    tags: list[str]
    scores: dict[str, int] | None = None
    score_labels: dict[str, str] | None = None
    total_score: int = 0
    score_reason: str = ""
    compliance_note: str = ""
    evidence: list[dict[str, str]] | None = None
    selected: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResearchReport:
    generated_at: str
    total_items: int
    hotspots: list[Hotspot]
    source_errors: list[str]
    source_items: list[dict[str, str]] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "total_items": self.total_items,
            "hotspots": [item.to_dict() for item in self.hotspots],
            "source_errors": self.source_errors,
            "source_items": self.source_items or [],
        }


class ResearchAgent:
    """Fetches and condenses biotech industry news into ranked hotspots."""

    max_item_age_days = 14

    def __init__(
        self,
        rss_reader: RSSReader | None = None,
        pubmed_client: PubMedClient | None = None,
        clinical_trials_client: ClinicalTrialsClient | None = None,
        fda_client: OpenFDAClient | None = None,
        llm: DeepSeekClient | None = None,
    ) -> None:
        self.rss_reader = rss_reader or RSSReader()
        self.pubmed_client = pubmed_client or PubMedClient()
        self.clinical_trials_client = clinical_trials_client or ClinicalTrialsClient()
        self.fda_client = fda_client or OpenFDAClient()
        self.llm = llm or DeepSeekClient()
        self.topic_clusterer = TopicClusterer(self.llm)
        self.topic_scorer = TopicScorer(self.llm)

    def collect(self, max_items: int = 24, max_hotspots: int = 6) -> ResearchReport:
        items, errors = self._collect_items(max_items=max_items)
        clusters = self.topic_clusterer.cluster(items, max_topics=max_hotspots, errors=errors)
        scored_topics = self.topic_scorer.score(clusters, errors=errors)
        hotspots = [self._topic_to_hotspot(item) for item in scored_topics[:max_hotspots]]
        return ResearchReport(
            generated_at=datetime.now(timezone.utc).isoformat(),
            total_items=len(items),
            hotspots=hotspots,
            source_errors=errors,
            source_items=[self._source_item_to_dict(item) for item in items],
        )

    def from_payload(self, payload: dict[str, Any]) -> ResearchReport:
        hotspots = []
        for item in payload.get("hotspots", []):
            if not isinstance(item, dict):
                continue
            hotspots.append(
                Hotspot(
                    title=str(item.get("title") or ""),
                    source=str(item.get("source") or ""),
                    url=str(item.get("url") or ""),
                    published=str(item.get("published") or ""),
                    summary=str(item.get("summary") or ""),
                    why_it_matters=str(item.get("why_it_matters") or ""),
                    tags=[str(tag) for tag in item.get("tags", []) if str(tag).strip()],
                    scores={str(key): int(value) for key, value in (item.get("scores") or {}).items()},
                    score_labels={str(key): str(value) for key, value in (item.get("score_labels") or {}).items()},
                    total_score=int(item.get("total_score") or 0),
                    score_reason=str(item.get("score_reason") or ""),
                    compliance_note=str(item.get("compliance_note") or ""),
                    evidence=[dict(evidence) for evidence in (item.get("evidence") or []) if isinstance(evidence, dict)],
                    selected=bool(item.get("selected")),
                )
            )
        return ResearchReport(
            generated_at=str(payload.get("generated_at") or datetime.now(timezone.utc).isoformat()),
            total_items=int(payload.get("total_items") or 0),
            hotspots=hotspots,
            source_errors=[str(error) for error in payload.get("source_errors", [])],
            source_items=[dict(item) for item in payload.get("source_items", []) if isinstance(item, dict)],
        )

    def _source_item_to_dict(self, item: RSSItem) -> dict[str, str]:
        return {
            "title": item.title,
            "source": item.source,
            "url": item.link,
            "published": item.published,
            "summary": compact_text(item.summary, max_chars=220),
        }

    def _topic_to_hotspot(self, scored: Any) -> Hotspot:
        topic = scored.topic
        lead = topic.evidence[0] if topic.evidence else {}
        return Hotspot(
            title=topic.title,
            source=str(lead.get("source") or "多来源"),
            url=str(lead.get("url") or ""),
            published=str(lead.get("published") or ""),
            summary=topic.summary,
            why_it_matters=scored.reason,
            tags=topic.tags or [topic.angle],
            scores=scored.scores,
            score_labels=scored.to_dict().get("score_labels", {}),
            total_score=scored.total_score,
            score_reason=scored.reason,
            compliance_note=scored.compliance_note,
            evidence=topic.evidence,
            selected=False,
        )

    def _ai_enrich_hotspots(self, hotspots: list[Hotspot], errors: list[str]) -> list[Hotspot]:
        if not self.llm.available or not hotspots:
            return hotspots
        try:
            payload = self.llm.chat_json(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是生物医药行业研究员。请基于给定新闻条目生成克制、准确的中文摘要。"
                            "只输出严格 JSON，不要 Markdown。不要编造事实，不要提供医疗或投资建议。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "请改写以下热点，保留 title/source/url/published，不改变事实。"
                            "JSON schema: {\"hotspots\":[{\"title\":\"\",\"source\":\"\",\"url\":\"\","
                            "\"published\":\"\",\"summary\":\"80-140字中文事实摘要\","
                            "\"why_it_matters\":\"一句话说明产业意义，必须克制\","
                            "\"tags\":[\"标签\"]}]}\n\n"
                            f"热点：{[item.to_dict() for item in hotspots]}"
                        ),
                    },
                ],
                max_tokens=4500,
            )
            enriched: list[Hotspot] = []
            for item in payload.get("hotspots", []):
                if not isinstance(item, dict):
                    continue
                enriched.append(
                    Hotspot(
                        title=str(item.get("title") or ""),
                        source=str(item.get("source") or ""),
                        url=str(item.get("url") or ""),
                        published=str(item.get("published") or ""),
                        summary=str(item.get("summary") or ""),
                        why_it_matters=str(item.get("why_it_matters") or ""),
                        tags=[str(tag) for tag in item.get("tags", []) if str(tag).strip()],
                    )
                )
            return [item for item in enriched if item.title and item.url] or hotspots
        except LLMError as exc:
            errors.append(f"DeepSeek research summary: {exc}")
            return hotspots

    def _collect_items(self, max_items: int) -> tuple[list[RSSItem], list[str]]:
        try:
            items, errors = self.rss_reader.fetch_many(max_items=max_items * 2, max_age_days=self.max_item_age_days)
        except TypeError:
            items, errors = self.rss_reader.fetch_many(max_items=max_items * 2)
        api_fetches = [
            ("PubMed", lambda: self.pubmed_client.search_recent(self._pubmed_query(), max_items=8)),
            (
                "ClinicalTrials.gov",
                lambda: self.clinical_trials_client.search_recent(self._clinical_trials_query(), max_items=8),
            ),
            ("FDA / openFDA", lambda: self.fda_client.recent_drug_approvals(max_items=8)),
        ]
        for source_name, fetch in api_fetches:
            try:
                items.extend(fetch())
            except Exception as exc:
                errors.append(f"{source_name}: {exc}")
        filtered, removed = self._filter_recent_items(items)
        if removed:
            errors.append(f"近期过滤：已剔除 {removed} 条超过 {self.max_item_age_days} 天或日期异常的旧内容")
        return filtered[: max_items * 2], errors

    def _filter_recent_items(self, items: list[RSSItem]) -> tuple[list[RSSItem], int]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.max_item_age_days)
        dated: list[tuple[datetime, RSSItem]] = []
        unknown: list[RSSItem] = []
        removed = 0
        for item in items:
            parsed = self._parse_item_date(item.published)
            if parsed is None:
                unknown.append(item)
                continue
            if parsed < cutoff:
                removed += 1
                continue
            dated.append((parsed, item))
        dated.sort(key=lambda pair: pair[0], reverse=True)
        unknown_limit = max(0, min(2, len(dated) // 5))
        removed += max(0, len(unknown) - unknown_limit)
        return [item for _, item in dated] + unknown[:unknown_limit], removed

    def _parse_item_date(self, value: str) -> datetime | None:
        text = value.strip()
        if not text:
            return None
        normalized = text.replace("Z", "+00:00")
        for candidate in (normalized, normalized[:10]):
            try:
                parsed = datetime.fromisoformat(candidate)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc)
            except ValueError:
                pass
        compact = re.fullmatch(r"(\d{4})(\d{2})(\d{2})", text)
        if compact:
            return datetime(
                int(compact.group(1)),
                int(compact.group(2)),
                int(compact.group(3)),
                tzinfo=timezone.utc,
            )
        pubmed_date = re.match(r"^(\d{4})\s+([A-Za-z]{3,9})(?:\s+(\d{1,2}))?", text)
        if pubmed_date:
            month_names = {
                "jan": 1,
                "feb": 2,
                "mar": 3,
                "apr": 4,
                "may": 5,
                "jun": 6,
                "jul": 7,
                "aug": 8,
                "sep": 9,
                "sept": 9,
                "oct": 10,
                "nov": 11,
                "dec": 12,
            }
            month = month_names.get(pubmed_date.group(2).lower()[:4]) or month_names.get(pubmed_date.group(2).lower()[:3])
            if month:
                return datetime(
                    int(pubmed_date.group(1)),
                    month,
                    int(pubmed_date.group(3) or 1),
                    tzinfo=timezone.utc,
                )
        try:
            parsed = parsedate_to_datetime(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except (TypeError, ValueError, IndexError):
            return None

    def _pubmed_query(self) -> str:
        return (
            '(biotech OR biopharma OR "drug discovery" OR "cell therapy" OR "gene therapy" '
            'OR oncology OR ADC OR "clinical trial")'
        )

    def _clinical_trials_query(self) -> str:
        return 'oncology OR "cell therapy" OR "gene therapy" OR ADC OR obesity'

    def _to_hotspot(self, item: RSSItem) -> Hotspot:
        text = compact_text(f"{item.title}. {item.summary}", max_chars=420)
        tags = self._tags_for(text)
        return Hotspot(
            title=item.title,
            source=item.source,
            url=item.link,
            published=item.published,
            summary=self._summary_for(text),
            why_it_matters=self._why_it_matters(text, tags),
            tags=tags,
        )

    def _score_item(self, item: RSSItem) -> int:
        text = f"{item.title} {item.summary}".lower()
        weighted_keywords = {
            "fda": 7,
            "approval": 7,
            "phase 3": 6,
            "phase iii": 6,
            "clinical": 4,
            "trial": 4,
            "licensing": 5,
            "deal": 5,
            "merger": 5,
            "acquisition": 5,
            "financing": 4,
            "biotech": 3,
            "pharma": 3,
            "oncology": 4,
            "adc": 5,
            "cell therapy": 5,
            "gene therapy": 5,
            "ai": 3,
            "china": 3,
            "pubmed": 4,
            "clinicaltrials": 5,
            "openfda": 6,
        }
        return sum(weight for keyword, weight in weighted_keywords.items() if keyword in text)

    def _tags_for(self, text: str) -> list[str]:
        lowered = text.lower()
        mapping = [
            ("FDA", ["fda", "approval", "regulator"]),
            ("临床进展", ["phase", "clinical", "trial"]),
            ("交易合作", ["deal", "licensing", "collaboration", "acquisition", "merger"]),
            ("创新药", ["drug", "therapy", "oncology", "antibody"]),
            ("AI制药", [" ai ", "machine learning", "computational"]),
            ("细胞基因治疗", ["cell therapy", "gene therapy", "car-t"]),
            ("融资", ["financing", "funding", "series"]),
        ]
        tags = [label for label, keys in mapping if any(key in f" {lowered} " for key in keys)]
        return tags or ["行业动态"]

    def _summary_for(self, text: str) -> str:
        if len(text) <= 160:
            return text
        return text[:157].rstrip() + "..."

    def _why_it_matters(self, text: str, tags: list[str]) -> str:
        if "FDA" in tags or "临床进展" in tags:
            return "可能影响相关管线的临床节奏、同类靶点竞争格局和后续监管预期。"
        if "交易合作" in tags:
            return "交易和授权合作通常反映大药企对技术路线、适应症和资产稀缺性的再定价。"
        if "融资" in tags:
            return "融资变化能观察资本对细分赛道和平台型公司的风险偏好。"
        if "AI制药" in tags:
            return "AI 制药进展值得关注其是否从效率叙事走向真实管线和临床验证。"
        return "该事件为观察产业趋势、公司策略和后续管线变化提供了新信号。"

    def render_markdown(self, report: ResearchReport) -> str:
        lines = [
            "# 今日生物医药热点研究报告",
            f"生成时间：{report.generated_at}",
            f"抓取新闻数：{report.total_items}",
            "",
        ]
        for index, item in enumerate(report.hotspots, start=1):
            if item.scores:
                score_lines = [
                    f"- 总分：{item.total_score}",
                    *[
                        f"- {item.score_labels.get(key, key) if item.score_labels else key}：{value}"
                        for key, value in item.scores.items()
                    ],
                    f"- 打分理由：{item.score_reason or item.why_it_matters}",
                    f"- 合规提醒：{item.compliance_note or '避免医疗和投资建议。'}",
                ]
            else:
                score_lines = []
            evidence_lines = []
            for evidence in item.evidence or []:
                evidence_lines.append(
                    f"- 证据：{evidence.get('source', '未知')}｜{evidence.get('title', '')}｜{evidence.get('url', '')}"
                )
            lines.extend(
                [
                    f"## {index}. {item.title}",
                    *score_lines,
                    f"- 来源：{item.source}",
                    f"- 时间：{item.published or '未知'}",
                    f"- 标签：{', '.join(item.tags)}",
                    f"- 摘要：{item.summary}",
                    f"- 为什么重要：{item.why_it_matters}",
                    f"- 链接：{item.url}",
                    *evidence_lines,
                    "",
                ]
            )
        if report.source_errors:
            lines.append("## 来源错误")
            lines.extend(f"- {error}" for error in report.source_errors)
            lines.append("")
        if report.source_items:
            lines.append("## 原始新闻清单")
            for item in report.source_items:
                lines.append(f"- {item.get('source', '未知')}｜{item.get('title', '')}｜{item.get('url', '')}")
            lines.append("")
        return "\n".join(lines)
