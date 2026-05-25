from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from tools.llm import DeepSeekClient, LLMError
from tools.rss.reader import RSSItem
from tools.scraper.extractor import compact_text


@dataclass
class TopicCluster:
    title: str
    angle: str
    summary: str
    evidence: list[dict[str, str]]
    tags: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TopicClusterer:
    def __init__(self, llm: DeepSeekClient | None = None) -> None:
        self.llm = llm or DeepSeekClient()

    def cluster(
        self,
        items: list[RSSItem],
        max_topics: int = 10,
        errors: list[str] | None = None,
    ) -> list[TopicCluster]:
        if self.llm.available and items:
            try:
                return self._ai_cluster(items=items, max_topics=max_topics)
            except LLMError as exc:
                if errors is not None:
                    errors.append(f"DeepSeek topic clustering: {exc}")
        return self._fallback_cluster(items=items, max_topics=max_topics)

    def _ai_cluster(self, items: list[RSSItem], max_topics: int) -> list[TopicCluster]:
        payload = self.llm.chat_json(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是生物医药行业主题分析员。请把新闻整理成若干可讨论主题。"
                        "只能基于给定新闻，不要编造公司、药物、金额、试验结果或监管结论。"
                        "只输出严格 JSON，不要 Markdown。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"请把以下新闻聚类为不超过 {max_topics} 个主题。"
                        "每个主题需要有明确角度，证据新闻使用原始序号。"
                        "JSON schema: {\"topics\":[{\"title\":\"主题标题\","
                        "\"angle\":\"内容角度\", \"summary\":\"80-140字主题摘要\","
                        "\"evidence_indices\":[0], \"tags\":[\"标签\"]}]}。\n\n"
                        f"新闻：{self._items_for_prompt(items)}"
                    ),
                },
            ],
            temperature=0.2,
            max_tokens=6000,
        )
        topics: list[TopicCluster] = []
        for raw in payload.get("topics", []):
            if not isinstance(raw, dict):
                continue
            evidence = self._evidence_from_indices(items, raw.get("evidence_indices", []))
            if not evidence:
                continue
            topics.append(
                TopicCluster(
                    title=str(raw.get("title") or evidence[0]["title"]),
                    angle=str(raw.get("angle") or "行业动态"),
                    summary=str(raw.get("summary") or evidence[0]["summary"]),
                    evidence=evidence,
                    tags=[str(tag) for tag in raw.get("tags", []) if str(tag).strip()][:6],
                )
            )
        return topics or self._fallback_cluster(items=items, max_topics=max_topics)

    def _fallback_cluster(self, items: list[RSSItem], max_topics: int) -> list[TopicCluster]:
        groups: dict[str, list[RSSItem]] = {}
        for item in items:
            groups.setdefault(self._topic_key(item), []).append(item)
        ordered = sorted(groups.items(), key=lambda pair: len(pair[1]), reverse=True)
        topics: list[TopicCluster] = []
        for key, group in ordered[:max_topics]:
            lead = group[0]
            evidence = [self._item_to_dict(item) for item in group[:4]]
            topics.append(
                TopicCluster(
                    title=self._title_for_group(key, lead),
                    angle=key,
                    summary=compact_text("；".join(item.summary or item.title for item in group), max_chars=180),
                    evidence=evidence,
                    tags=self._tags_for_group(key, group),
                )
            )
        return topics

    def _items_for_prompt(self, items: list[RSSItem]) -> list[dict[str, str]]:
        return [{**self._item_to_dict(item), "index": str(index)} for index, item in enumerate(items)]

    def _evidence_from_indices(self, items: list[RSSItem], indices: Any) -> list[dict[str, str]]:
        evidence: list[dict[str, str]] = []
        for index in indices if isinstance(indices, list) else []:
            try:
                item = items[int(index)]
            except (TypeError, ValueError, IndexError):
                continue
            evidence.append(self._item_to_dict(item))
        return evidence[:5]

    def _item_to_dict(self, item: RSSItem) -> dict[str, str]:
        return {
            "title": item.title,
            "source": item.source,
            "url": item.link,
            "published": item.published,
            "summary": compact_text(item.summary, max_chars=240),
        }

    def _topic_key(self, item: RSSItem) -> str:
        text = f"{item.title} {item.summary}".lower()
        mapping = [
            ("监管审批", ["fda", "approval", "regulator", "批准", "审批"]),
            ("临床进展", ["phase", "clinical", "trial", "endpoint", "临床", "试验"]),
            ("交易合作", ["deal", "licensing", "collaboration", "partner", "acquisition", "merger", "授权", "合作"]),
            ("AI制药", [" ai ", "artificial intelligence", "machine learning", "computational", "大模型", "人工智能"]),
            ("肿瘤管线", ["oncology", "cancer", "tumor", "asco", "肿瘤"]),
            ("细胞基因治疗", ["cell therapy", "gene therapy", "car-t", "细胞", "基因"]),
            ("资本市场", ["financing", "funding", "ipo", "earnings", "财报", "融资"]),
        ]
        padded = f" {text} "
        for label, keywords in mapping:
            if any(keyword in padded for keyword in keywords):
                return label
        return "行业动态"

    def _title_for_group(self, key: str, lead: RSSItem) -> str:
        return f"{key}：{compact_text(lead.title, max_chars=42)}"

    def _tags_for_group(self, key: str, group: list[RSSItem]) -> list[str]:
        tags = [key]
        text = " ".join(f"{item.title} {item.summary}" for item in group).lower()
        if "fda" in text:
            tags.append("FDA")
        if "phase 3" in text or "phase iii" in text:
            tags.append("III期")
        if "ai" in text or "人工智能" in text:
            tags.append("AI")
        if "oncology" in text or "cancer" in text or "肿瘤" in text:
            tags.append("肿瘤")
        return tags[:6]
