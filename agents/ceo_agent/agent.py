from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date
from typing import Any

from tools.llm import DeepSeekClient, LLMError


@dataclass
class DailyBrief:
    objective: str
    audience: str
    content_angle: str
    research_focus: list[str]
    source_policy: list[str]
    quality_bar: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TopicDecision:
    index: int
    title: str
    decision: str
    score: int
    reason: str
    content_angle: str
    required_capabilities: list[str]
    human_review_required: bool
    review_reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CEODecision:
    today_content: str
    strategy: str
    generate_count: int
    recommended_indices: list[int]
    optional_indices: list[int]
    manual_review_indices: list[int]
    capabilities: list[str]
    overall_score: int
    overall_reason: str
    topic_decisions: list[TopicDecision]
    execution_notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["topic_decisions"] = [item.to_dict() for item in self.topic_decisions]
        return payload


class CEOAgent:
    """Decides the daily editorial brief for the biotech intelligence workflow."""

    def __init__(self, llm: DeepSeekClient | None = None) -> None:
        self.llm = llm or DeepSeekClient()

    def create_daily_brief(
        self,
        target_date: date,
        topic_hint: str = "",
        audience: str = "关注生物医药、创新药、投融资和产业趋势的小红书读者",
    ) -> DailyBrief:
        topic = topic_hint.strip() or "今日生物医药热点"
        return DailyBrief(
            objective=f"生成 {target_date.isoformat()} 的《小红书生物医药热点》",
            audience=audience,
            content_angle=(
                f"围绕“{topic}”，优先选择有产业意义、临床进展、监管变化、交易合作或资本市场信号的新闻。"
            ),
            research_focus=[
                "创新药临床与监管里程碑",
                "Biotech/Pharma 交易、授权合作与融资",
                "AI 制药、细胞/基因治疗、抗体药物、ADC 等技术趋势",
                "大型药企管线调整、商业化进展与行业风向",
            ],
            source_policy=[
                "优先使用可追溯的公开来源，并保留链接",
                "同一事件多源重复时合并处理",
                "避免把单一公司宣传稿写成确定性行业结论",
            ],
            quality_bar=[
                "每条热点要说明为什么重要",
                "结论要克制，区分事实、推断和待观察点",
                "小红书文案要可读、可发布，但不夸大医疗疗效或投资收益",
            ],
        )

    def decide_daily_plan(
        self,
        target_date: date,
        brief: DailyBrief,
        hotspots: list[dict[str, Any]],
        max_posts: int = 3,
        errors: list[str] | None = None,
    ) -> CEODecision:
        if self.llm.available and hotspots:
            try:
                return self._ai_decide(target_date, brief, hotspots, max_posts=max_posts)
            except LLMError as exc:
                if errors is not None:
                    errors.append(f"DeepSeek CEO decision: {exc}")
        return self._fallback_decide(target_date, brief, hotspots, max_posts=max_posts)

    def render_markdown(self, brief: DailyBrief) -> str:
        sections = [
            f"# {brief.objective}",
            f"目标读者：{brief.audience}",
            f"内容角度：{brief.content_angle}",
            "## 研究重点",
            *[f"- {item}" for item in brief.research_focus],
            "## 来源策略",
            *[f"- {item}" for item in brief.source_policy],
            "## 质量标准",
            *[f"- {item}" for item in brief.quality_bar],
        ]
        return "\n".join(sections) + "\n"

    def render_decision_markdown(self, decision: CEODecision) -> str:
        sections = [
            f"# CEO 内容决策：{decision.today_content}",
            "",
            f"总体评分：{decision.overall_score}/100",
            f"总体理由：{decision.overall_reason}",
            f"今日策略：{decision.strategy}",
            f"建议生成篇数：{decision.generate_count}",
            f"调用能力：{'、'.join(decision.capabilities) or '-'}",
            f"推荐主题：{', '.join(str(index + 1) for index in decision.recommended_indices) or '-'}",
            f"可选主题：{', '.join(str(index + 1) for index in decision.optional_indices) or '-'}",
            f"需要人工审核：{', '.join(str(index + 1) for index in decision.manual_review_indices) or '-'}",
            "",
            "## 执行意见",
            *[f"- {note}" for note in decision.execution_notes],
            "",
            "## 逐主题判断",
        ]
        for item in decision.topic_decisions:
            sections.extend(
                [
                    f"### {item.index + 1}. {item.title}",
                    f"- 判断：{item.decision}",
                    f"- CEO评分：{item.score}/100",
                    f"- 原因：{item.reason}",
                    f"- 做法：{item.content_angle}",
                    f"- 调用能力：{'、'.join(item.required_capabilities) or '-'}",
                    f"- 人工审核：{'是' if item.human_review_required else '否'}；{item.review_reason or '-'}",
                    "",
                ]
            )
        return "\n".join(sections).strip() + "\n"

    def _ai_decide(
        self,
        target_date: date,
        brief: DailyBrief,
        hotspots: list[dict[str, Any]],
        max_posts: int,
    ) -> CEODecision:
        compact_hotspots = [self._compact_hotspot(index, item) for index, item in enumerate(hotspots)]
        payload = self.llm.chat_json(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是生物医药内容公司的 CEO Agent，负责内容日程和资源调度。"
                        "你要决定今天做什么、哪些值得做、怎么做、调用哪些能力、生成几篇、哪些必须人工审核。"
                        "只基于给定热点和证据，不编造事实。只输出严格 JSON。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "请给出 CEO 级内容决策。JSON schema: "
                        "{\"today_content\":\"\",\"strategy\":\"\",\"generate_count\":0,"
                        "\"recommended_indices\":[0],\"optional_indices\":[1],\"manual_review_indices\":[0],"
                        "\"capabilities\":[\"research_agent\"],\"overall_score\":0,\"overall_reason\":\"\","
                        "\"execution_notes\":[\"\"],"
                        "\"topic_decisions\":[{\"index\":0,\"decision\":\"do|optional|skip\","
                        "\"score\":0,\"reason\":\"\",\"content_angle\":\"\",\"required_capabilities\":[\"\"],"
                        "\"human_review_required\":false,\"review_reason\":\"\"}]}"
                        f"。最多建议生成 {max_posts} 篇。"
                        "decision 只能是 do、optional、skip；score 为 0-100。"
                        "capabilities 可从 research_agent、topic_agent、content_agent、image_agent、review_agent、publish_agent 中选择。"
                        "如果涉及医疗疗效、临床数据、监管结论、投资融资金额或争议内容，应标记人工审核。\n\n"
                        f"日期：{target_date.isoformat()}\n"
                        f"Brief：{brief.to_dict()}\n"
                        f"热点：{compact_hotspots}"
                    ),
                },
            ],
            temperature=0.12,
            max_tokens=5000,
        )
        return self._normalize_decision(payload, hotspots, max_posts=max_posts)

    def _fallback_decide(
        self,
        target_date: date,
        brief: DailyBrief,
        hotspots: list[dict[str, Any]],
        max_posts: int,
    ) -> CEODecision:
        ranked = sorted(
            enumerate(hotspots),
            key=lambda pair: int(pair[1].get("total_score") or 0),
            reverse=True,
        )
        recommended = [
            index for index, item in ranked if int(item.get("total_score") or 0) >= 60
        ][:max_posts]
        if not recommended and ranked:
            recommended = [ranked[0][0]]
        optional = [
            index
            for index, item in ranked
            if index not in recommended and int(item.get("total_score") or 0) >= 45
        ][: max(0, max_posts)]
        manual_review = [
            index
            for index, item in enumerate(hotspots)
            if self._needs_review(item)
        ]
        topic_decisions = []
        for index, item in enumerate(hotspots):
            score = int(item.get("total_score") or 0)
            decision = "do" if index in recommended else "optional" if index in optional else "skip"
            review = index in manual_review
            topic_decisions.append(
                TopicDecision(
                    index=index,
                    title=str(item.get("title") or f"主题 {index + 1}"),
                    decision=decision,
                    score=max(0, min(100, score)),
                    reason=self._fallback_reason(item, decision),
                    content_angle=self._content_angle(item),
                    required_capabilities=self._capabilities_for_topic(item, include_publish=decision != "skip"),
                    human_review_required=review,
                    review_reason="涉及临床/监管/交易数据或潜在合规表达，发布前建议人工复核。" if review else "",
                )
            )
        capabilities = self._merge_capabilities(topic_decisions)
        return CEODecision(
            today_content=f"{target_date.isoformat()} 生物医药热点选题",
            strategy=(
                "优先做高分且证据较充分的主题；低分主题保留为备选，先不消耗内容与图片生成资源。"
            ),
            generate_count=len(recommended),
            recommended_indices=recommended,
            optional_indices=optional,
            manual_review_indices=manual_review,
            capabilities=capabilities,
            overall_score=self._overall_score(hotspots),
            overall_reason=f"根据 {len(hotspots)} 个候选主题的行业影响、数据质量和合规风险排序。",
            topic_decisions=topic_decisions,
            execution_notes=[
                "先展示 CEO 推荐排序，人工可改选后再生成文案。",
                "推荐主题生成文案后，再由 Image Agent 为每条生成多套封面提示词。",
                "标记人工审核的主题发布前需核对原始来源、数字和措辞。",
            ],
        )

    def _normalize_decision(
        self,
        payload: dict[str, Any],
        hotspots: list[dict[str, Any]],
        max_posts: int,
    ) -> CEODecision:
        topic_count = len(hotspots)
        raw_topic_decisions = payload.get("topic_decisions") if isinstance(payload.get("topic_decisions"), list) else []
        by_index = {int(item.get("index", -1)): item for item in raw_topic_decisions if isinstance(item, dict)}
        topic_decisions = []
        for index, hotspot in enumerate(hotspots):
            raw = by_index.get(index, {})
            decision = str(raw.get("decision") or "").strip().lower()
            if decision not in {"do", "optional", "skip"}:
                decision = "do" if index in self._valid_indices(payload.get("recommended_indices"), topic_count) else "optional"
            review = bool(raw.get("human_review_required")) or self._needs_review(hotspot)
            topic_decisions.append(
                TopicDecision(
                    index=index,
                    title=str(hotspot.get("title") or raw.get("title") or f"主题 {index + 1}"),
                    decision=decision,
                    score=max(0, min(100, int(raw.get("score") or hotspot.get("total_score") or 0))),
                    reason=str(raw.get("reason") or self._fallback_reason(hotspot, decision)),
                    content_angle=str(raw.get("content_angle") or self._content_angle(hotspot)),
                    required_capabilities=self._normalize_capabilities(raw.get("required_capabilities"), decision),
                    human_review_required=review,
                    review_reason=str(raw.get("review_reason") or ("发布前需人工复核事实和合规表达。" if review else "")),
                )
            )
        recommended = self._valid_indices(payload.get("recommended_indices"), topic_count)
        if not recommended:
            recommended = [item.index for item in topic_decisions if item.decision == "do"]
        recommended = recommended[:max_posts]
        optional = [
            index for index in self._valid_indices(payload.get("optional_indices"), topic_count)
            if index not in recommended
        ]
        if not optional:
            optional = [item.index for item in topic_decisions if item.decision == "optional" and item.index not in recommended]
        manual_review = sorted(
            set(self._valid_indices(payload.get("manual_review_indices"), topic_count))
            | {item.index for item in topic_decisions if item.human_review_required}
        )
        capabilities = self._normalize_capabilities(payload.get("capabilities"), "do")
        if not capabilities:
            capabilities = self._merge_capabilities(topic_decisions)
        return CEODecision(
            today_content=str(payload.get("today_content") or "今日生物医药热点"),
            strategy=str(payload.get("strategy") or "优先选择高分、证据充分、适合小红书表达的主题。"),
            generate_count=max(0, min(max_posts, int(payload.get("generate_count") or len(recommended)))),
            recommended_indices=recommended,
            optional_indices=optional,
            manual_review_indices=manual_review,
            capabilities=capabilities,
            overall_score=max(0, min(100, int(payload.get("overall_score") or self._overall_score(hotspots)))),
            overall_reason=str(payload.get("overall_reason") or "基于主题评分和合规风险形成今日内容排期。"),
            topic_decisions=topic_decisions,
            execution_notes=[str(item) for item in payload.get("execution_notes", []) if str(item).strip()]
            or ["人工可在热点卡片中调整 CEO 推荐后再生成文案。"],
        )

    def _compact_hotspot(self, index: int, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "index": index,
            "title": item.get("title"),
            "summary": item.get("summary"),
            "score": item.get("total_score"),
            "scores": item.get("scores"),
            "reason": item.get("score_reason") or item.get("why_it_matters"),
            "compliance_note": item.get("compliance_note"),
            "tags": item.get("tags"),
            "evidence": (item.get("evidence") or [])[:3],
        }

    def _valid_indices(self, value: Any, topic_count: int) -> list[int]:
        if not isinstance(value, list):
            return []
        result = []
        for item in value:
            try:
                index = int(item)
            except (TypeError, ValueError):
                continue
            if 0 <= index < topic_count and index not in result:
                result.append(index)
        return result

    def _normalize_capabilities(self, value: Any, decision: str) -> list[str]:
        allowed = {"research_agent", "topic_agent", "content_agent", "image_agent", "review_agent", "publish_agent"}
        result = []
        if isinstance(value, list):
            for item in value:
                name = str(item).strip()
                if name in allowed and name not in result:
                    result.append(name)
        if result:
            return result
        base = ["research_agent", "topic_agent"]
        if decision != "skip":
            base.extend(["content_agent", "image_agent", "publish_agent"])
        return base

    def _merge_capabilities(self, decisions: list[TopicDecision]) -> list[str]:
        result = ["research_agent", "topic_agent"]
        for item in decisions:
            if item.decision == "skip":
                continue
            for name in item.required_capabilities:
                if name not in result:
                    result.append(name)
            if item.human_review_required and "review_agent" not in result:
                result.append("review_agent")
        return result

    def _needs_review(self, item: dict[str, Any]) -> bool:
        scores = item.get("scores") if isinstance(item.get("scores"), dict) else {}
        risk = int(scores.get("compliance_risk") or 0)
        text = " ".join(
            str(value)
            for value in [
                item.get("title"),
                item.get("summary"),
                item.get("why_it_matters"),
                item.get("compliance_note"),
            ]
        ).lower()
        return risk <= -8 or any(
            keyword in text
            for keyword in ["疗效", "治愈", "survival", "安全性", "fda", "批准", "approval", "融资", "交易", "投资"]
        )

    def _capabilities_for_topic(self, item: dict[str, Any], include_publish: bool) -> list[str]:
        capabilities = ["research_agent", "topic_agent"]
        if include_publish:
            capabilities.extend(["content_agent", "image_agent", "publish_agent"])
        if self._needs_review(item):
            capabilities.append("review_agent")
        return capabilities

    def _content_angle(self, item: dict[str, Any]) -> str:
        tags = [str(tag) for tag in item.get("tags", []) if str(tag).strip()]
        if tags:
            return f"从“{tags[0]}”切入，先讲事实，再解释产业意义和后续观察点。"
        return "先讲事实，再解释为什么重要，最后给出克制的后续观察。"

    def _fallback_reason(self, item: dict[str, Any], decision: str) -> str:
        score = int(item.get("total_score") or 0)
        if decision == "do":
            return f"综合评分 {score}，证据和行业意义相对更强，适合优先生成。"
        if decision == "optional":
            return f"综合评分 {score}，有一定内容价值，但建议排在推荐主题之后。"
        return f"综合评分 {score}，当前证据或可读性不足，暂不优先生成。"

    def _overall_score(self, hotspots: list[dict[str, Any]]) -> int:
        if not hotspots:
            return 0
        top_scores = [int(item.get("total_score") or 0) for item in hotspots[:3]]
        return max(0, min(100, round(sum(top_scores) / len(top_scores))))
