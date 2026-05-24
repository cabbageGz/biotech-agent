from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any

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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResearchReport:
    generated_at: str
    total_items: int
    hotspots: list[Hotspot]
    source_errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "total_items": self.total_items,
            "hotspots": [item.to_dict() for item in self.hotspots],
            "source_errors": self.source_errors,
        }


class ResearchAgent:
    """Fetches and condenses biotech industry news into ranked hotspots."""

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

    def collect(self, max_items: int = 24, max_hotspots: int = 6) -> ResearchReport:
        items, errors = self._collect_items(max_items=max_items)
        ranked = sorted(items, key=self._score_item, reverse=True)
        hotspots = [self._to_hotspot(item) for item in ranked[:max_hotspots]]
        hotspots = self._ai_enrich_hotspots(hotspots, errors)
        return ResearchReport(
            generated_at=datetime.now(timezone.utc).isoformat(),
            total_items=len(items),
            hotspots=hotspots,
            source_errors=errors,
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
        items, errors = self.rss_reader.fetch_many(max_items=max_items)
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
        return items[: max_items * 2], errors

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
            lines.extend(
                [
                    f"## {index}. {item.title}",
                    f"- 来源：{item.source}",
                    f"- 时间：{item.published or '未知'}",
                    f"- 标签：{', '.join(item.tags)}",
                    f"- 摘要：{item.summary}",
                    f"- 为什么重要：{item.why_it_matters}",
                    f"- 链接：{item.url}",
                    "",
                ]
            )
        if report.source_errors:
            lines.append("## 来源错误")
            lines.extend(f"- {error}" for error in report.source_errors)
            lines.append("")
        return "\n".join(lines)
