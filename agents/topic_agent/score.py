from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from agents.topic_agent.cluster import TopicCluster
from tools.llm import DeepSeekClient, LLMError


SCORE_WEIGHTS = {
    "timeliness": 20,
    "industry_impact": 20,
    "top_company_or_star_asset": 15,
    "data_quality": 15,
    "xiaohongshu_readability": 15,
    "debate_potential": 10,
    "compliance_risk": -20,
}

SCORE_LABELS = {
    "timeliness": "时效性",
    "industry_impact": "行业影响力",
    "top_company_or_star_asset": "头部公司/明星药物相关性",
    "data_quality": "数据含金量",
    "xiaohongshu_readability": "小红书可读性",
    "debate_potential": "争议/讨论度",
    "compliance_risk": "合规风险",
}


@dataclass
class ScoredTopic:
    topic: TopicCluster
    scores: dict[str, int]
    total_score: int
    reason: str
    compliance_note: str
    selected: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic.to_dict(),
            "scores": self.scores,
            "score_labels": SCORE_LABELS,
            "total_score": self.total_score,
            "reason": self.reason,
            "compliance_note": self.compliance_note,
            "selected": self.selected,
        }


class TopicScorer:
    def __init__(self, llm: DeepSeekClient | None = None) -> None:
        self.llm = llm or DeepSeekClient()

    def score(
        self,
        topics: list[TopicCluster],
        errors: list[str] | None = None,
    ) -> list[ScoredTopic]:
        if self.llm.available and topics:
            try:
                return self._ai_score(topics)
            except LLMError as exc:
                if errors is not None:
                    errors.append(f"DeepSeek topic scoring: {exc}")
        return self._fallback_score(topics)

    def _ai_score(self, topics: list[TopicCluster]) -> list[ScoredTopic]:
        payload = self.llm.chat_json(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是生物医药行业内容选题主编。请按指定维度给主题打分。"
                        "分数必须克制，合规风险为 -20 到 0，风险越高越接近 -20。"
                        "只能基于给定证据，不要编造事实。只输出严格 JSON。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "按 100 分制给每个主题打分：时效性20、行业影响力20、"
                        "头部公司/明星药物相关性15、数据含金量15、小红书可读性15、"
                        "争议/讨论度10、合规风险-20到0。"
                        "JSON schema: {\"topics\":[{\"index\":0,\"scores\":{\"timeliness\":0,"
                        "\"industry_impact\":0,\"top_company_or_star_asset\":0,\"data_quality\":0,"
                        "\"xiaohongshu_readability\":0,\"debate_potential\":0,\"compliance_risk\":0},"
                        "\"reason\":\"一句话理由\",\"compliance_note\":\"合规提醒\"}]}。\n\n"
                        f"主题：{[topic.to_dict() | {'index': index} for index, topic in enumerate(topics)]}"
                    ),
                },
            ],
            temperature=0.15,
            max_tokens=5000,
        )
        by_index = {int(item.get("index", -1)): item for item in payload.get("topics", []) if isinstance(item, dict)}
        scored: list[ScoredTopic] = []
        for index, topic in enumerate(topics):
            raw = by_index.get(index, {})
            scores = self._normalize_scores(raw.get("scores", {}))
            scored.append(
                ScoredTopic(
                    topic=topic,
                    scores=scores,
                    total_score=sum(scores.values()),
                    reason=str(raw.get("reason") or self._fallback_reason(topic)),
                    compliance_note=str(raw.get("compliance_note") or "避免医疗疗效承诺和投资建议。"),
                )
            )
        return sorted(scored, key=lambda item: item.total_score, reverse=True)

    def _fallback_score(self, topics: list[TopicCluster]) -> list[ScoredTopic]:
        scored = []
        for topic in topics:
            text = f"{topic.title} {topic.summary} {' '.join(topic.tags)}".lower()
            scores = {
                "timeliness": 14 + min(len(topic.evidence), 3) * 2,
                "industry_impact": self._score_by_keywords(text, 20, ["fda", "approval", "phase 3", "deal", "licensing", "clinical", "监管", "临床", "交易"]),
                "top_company_or_star_asset": self._score_by_keywords(text, 15, ["lilly", "novo", "pfizer", "bms", "merck", "roche", "astrazeneca", "novartis", "明星", "头部"]),
                "data_quality": self._score_by_keywords(text, 15, ["phase", "endpoint", "data", "trial", "approval", "clinicaltrials", "pubmed", "数据", "终点"]),
                "xiaohongshu_readability": self._score_by_keywords(text, 15, ["ai", "fda", "deal", "asco", "obesity", "肿瘤", "减重", "合作", "融资"]),
                "debate_potential": self._score_by_keywords(text, 10, ["ai", "price", "safety", "acquisition", "controversy", "争议", "安全", "并购"]),
                "compliance_risk": self._compliance_risk(text),
            }
            scored.append(
                ScoredTopic(
                    topic=topic,
                    scores=scores,
                    total_score=sum(scores.values()),
                    reason=self._fallback_reason(topic),
                    compliance_note="避免使用疗效承诺、投资收益暗示和未经证实的数据。",
                )
            )
        return sorted(scored, key=lambda item: item.total_score, reverse=True)

    def _normalize_scores(self, raw_scores: Any) -> dict[str, int]:
        scores: dict[str, int] = {}
        raw = raw_scores if isinstance(raw_scores, dict) else {}
        for key, weight in SCORE_WEIGHTS.items():
            value = int(raw.get(key, 0) or 0)
            if key == "compliance_risk":
                scores[key] = max(-20, min(0, value))
            else:
                scores[key] = max(0, min(weight, value))
        return scores

    def _score_by_keywords(self, text: str, max_score: int, keywords: list[str]) -> int:
        hits = sum(1 for keyword in keywords if keyword in text)
        return min(max_score, 8 + hits * 4)

    def _compliance_risk(self, text: str) -> int:
        if any(word in text for word in ["疗效", "治愈", "survival", "safety", "安全"]):
            return -8
        if any(word in text for word in ["stock", "share", "投资", "股价"]):
            return -6
        return -2

    def _fallback_reason(self, topic: TopicCluster) -> str:
        return f"主题聚合了 {len(topic.evidence)} 条证据新闻，适合从“{topic.angle}”角度拆解。"
