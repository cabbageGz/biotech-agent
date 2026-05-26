from __future__ import annotations

from typing import Any

from agents.review_agent.schema import ReviewIssue, ReviewReport
from tools.llm import DeepSeekClient, LLMError


class ReviewAgent:
    """Reviews generated posts against source evidence and compliance constraints."""

    def __init__(self, llm: DeepSeekClient | None = None) -> None:
        self.llm = llm or DeepSeekClient()

    def review_post(
        self,
        post: dict[str, Any],
        hotspot: dict[str, Any],
        evidence: list[dict[str, str]],
    ) -> ReviewReport:
        if self.llm.available:
            try:
                return self._ai_review(post=post, hotspot=hotspot, evidence=evidence)
            except LLMError:
                pass
        return self._fallback_review(post=post, hotspot=hotspot, evidence=evidence)

    def revise_post(
        self,
        post: dict[str, Any],
        review: dict[str, Any],
        hotspot: dict[str, Any],
        evidence: list[dict[str, str]],
    ) -> dict[str, Any]:
        if self.llm.available:
            try:
                return self._ai_revise(post=post, review=review, hotspot=hotspot, evidence=evidence)
            except LLMError:
                pass
        return self._fallback_revise(post=post, review=review)

    def _ai_review(
        self,
        post: dict[str, Any],
        hotspot: dict[str, Any],
        evidence: list[dict[str, str]],
    ) -> ReviewReport:
        payload = self.llm.chat_json(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是生物医药内容审核员，负责 Evidence Review 和合规审核。"
                        "只能基于给定源新闻和热点信息判断，不要自行补充外部事实。"
                        "重点检查：来源是否存在、文案是否夸大、是否涉及疗效承诺、是否涉及投资建议。"
                        "输出严格 JSON，不要 Markdown。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "请审核这篇小红书文案。JSON schema: "
                        "{\"source_exists\":true,\"source_confidence\":0,"
                        "\"exaggeration_risk\":0,\"efficacy_promise_risk\":0,"
                        "\"investment_advice_risk\":0,\"overall_confidence\":0,"
                        "\"publish_status\":\"pass|revise|block\",\"summary\":\"\","
                        "\"issues\":[{\"category\":\"source|exaggeration|efficacy|investment|other\","
                        "\"severity\":\"low|medium|high\",\"finding\":\"\",\"evidence\":\"\",\"suggestion\":\"\"}],"
                        "\"revision_suggestions\":[\"\"],"
                        "\"evidence_used\":[{\"title\":\"\",\"source\":\"\",\"url\":\"\",\"published\":\"\"}]}"
                        "。各风险分为 0-100，越高风险越高；置信分为 0-100，越高越可信。"
                        "如果事实无法由证据支持，应指出具体句子并建议改写。\n\n"
                        f"热点：{hotspot}\n\n证据：{evidence}\n\n文案：{post}"
                    ),
                },
            ],
            temperature=0.1,
            max_tokens=5000,
        )
        return self._normalize_review(payload, evidence)

    def _ai_revise(
        self,
        post: dict[str, Any],
        review: dict[str, Any],
        hotspot: dict[str, Any],
        evidence: list[dict[str, str]],
    ) -> dict[str, Any]:
        payload = self.llm.chat_json(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是生物医药小红书文案编辑。请按审核意见修正文案。"
                        "不得新增证据之外的事实，不得夸大疗效，不得提供投资建议。"
                        "保留原文结构和可读性。输出严格 JSON。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "请修正文案。JSON schema: {\"title\":\"\",\"hook\":\"\",\"body\":\"\","
                        "\"hashtags\":[\"#标签\"],\"publish_notes\":[\"\"],\"revision_notes\":[\"\"]}。"
                        "正文最后必须包含：资料来自公开信息，仅作行业学习与信息整理，不构成医疗或投资建议。\n\n"
                        f"热点：{hotspot}\n\n证据：{evidence}\n\n审核结果：{review}\n\n原文案：{post}"
                    ),
                },
            ],
            temperature=0.25,
            max_tokens=5000,
        )
        return self._normalize_revision(payload, post)

    def _fallback_review(
        self,
        post: dict[str, Any],
        hotspot: dict[str, Any],
        evidence: list[dict[str, str]],
    ) -> ReviewReport:
        text = f"{post.get('title', '')}\n{post.get('hook', '')}\n{post.get('body', '')}".lower()
        issues: list[ReviewIssue] = []
        source_exists = bool(hotspot.get("url") or evidence)
        if not source_exists:
            issues.append(
                ReviewIssue(
                    category="source",
                    severity="high",
                    finding="未找到可追溯来源链接或证据新闻。",
                    evidence="当前热点缺少 url/evidence。",
                    suggestion="补充公开来源后再发布，或删除无法核对的具体事实。",
                )
            )
        exaggeration_words = ["重大突破", "颠覆", "确定", "必然", "爆发", "唯一", "最强"]
        efficacy_words = ["治愈", "根治", "疗效显著", "安全有效", "患者获益确定"]
        investment_words = ["买入", "投资机会", "稳赚", "股价", "收益", "布局窗口"]
        exaggeration_risk = self._risk_from_keywords(text, exaggeration_words)
        efficacy_risk = self._risk_from_keywords(text, efficacy_words)
        investment_risk = self._risk_from_keywords(text, investment_words)
        if exaggeration_risk >= 40:
            issues.append(self._keyword_issue("exaggeration", "存在绝对化或夸大表达。", "建议改为“可能、值得观察、信号之一”。"))
        if efficacy_risk >= 40:
            issues.append(self._keyword_issue("efficacy", "存在疗效承诺或疗效确定性表达。", "建议改为“研究显示/试验提示/仍需后续验证”。"))
        if investment_risk >= 40:
            issues.append(self._keyword_issue("investment", "存在投资建议或收益暗示。", "建议删除投资动作引导，只保留行业信息整理。"))
        max_risk = max(exaggeration_risk, efficacy_risk, investment_risk)
        status = "block" if not source_exists or max_risk >= 70 else "revise" if issues else "pass"
        confidence = 80 if source_exists and not issues else 58 if source_exists else 35
        return ReviewReport(
            source_exists=source_exists,
            source_confidence=85 if source_exists else 20,
            exaggeration_risk=exaggeration_risk,
            efficacy_promise_risk=efficacy_risk,
            investment_advice_risk=investment_risk,
            overall_confidence=confidence,
            publish_status=status,
            summary=self._status_summary(status),
            issues=issues,
            revision_suggestions=[issue.suggestion for issue in issues],
            evidence_used=self._evidence_used(hotspot, evidence),
        )

    def _fallback_revise(self, post: dict[str, Any], review: dict[str, Any]) -> dict[str, Any]:
        title = str(post.get("title") or "")
        body = str(post.get("body") or "")
        replacements = {
            "重大突破": "重要进展",
            "颠覆": "带来新观察",
            "确定": "可能",
            "必然": "可能",
            "治愈": "治疗探索",
            "根治": "治疗探索",
            "疗效显著": "数据显示出积极信号",
            "安全有效": "安全性和有效性仍需结合公开数据判断",
            "投资机会": "行业观察点",
            "稳赚": "需谨慎观察",
            "买入": "关注",
        }
        for source, target in replacements.items():
            title = title.replace(source, target)
            body = body.replace(source, target)
        disclaimer = "资料来自公开信息，仅作行业学习与信息整理，不构成医疗或投资建议。"
        if disclaimer not in body:
            body = body.rstrip() + "\n\n" + disclaimer
        notes = [str(note) for note in post.get("publish_notes", []) if str(note).strip()]
        notes.extend(str(item) for item in review.get("revision_suggestions", []) if str(item).strip())
        return {
            **post,
            "title": title.strip(),
            "body": body.strip(),
            "publish_notes": list(dict.fromkeys(notes)),
            "revision_notes": ["已按审核建议降低绝对化、疗效承诺和投资暗示表达。"],
        }

    def _normalize_review(self, payload: dict[str, Any], evidence: list[dict[str, str]]) -> ReviewReport:
        issues = []
        for item in payload.get("issues", []):
            if not isinstance(item, dict):
                continue
            issues.append(
                ReviewIssue(
                    category=str(item.get("category") or "other"),
                    severity=str(item.get("severity") or "medium"),
                    finding=str(item.get("finding") or ""),
                    evidence=str(item.get("evidence") or ""),
                    suggestion=str(item.get("suggestion") or ""),
                )
            )
        evidence_used = [
            {str(key): str(value) for key, value in item.items()}
            for item in payload.get("evidence_used", [])
            if isinstance(item, dict)
        ] or self._evidence_used({}, evidence)
        return ReviewReport(
            source_exists=bool(payload.get("source_exists")),
            source_confidence=self._clamp(payload.get("source_confidence")),
            exaggeration_risk=self._clamp(payload.get("exaggeration_risk")),
            efficacy_promise_risk=self._clamp(payload.get("efficacy_promise_risk")),
            investment_advice_risk=self._clamp(payload.get("investment_advice_risk")),
            overall_confidence=self._clamp(payload.get("overall_confidence")),
            publish_status=self._status(str(payload.get("publish_status") or "revise")),
            summary=str(payload.get("summary") or ""),
            issues=issues,
            revision_suggestions=[str(item) for item in payload.get("revision_suggestions", []) if str(item).strip()],
            evidence_used=evidence_used,
        )

    def _normalize_revision(self, payload: dict[str, Any], post: dict[str, Any]) -> dict[str, Any]:
        return {
            **post,
            "title": str(payload.get("title") or post.get("title") or ""),
            "hook": str(payload.get("hook") or post.get("hook") or ""),
            "body": str(payload.get("body") or post.get("body") or ""),
            "hashtags": [str(tag) for tag in payload.get("hashtags", post.get("hashtags", [])) if str(tag).strip()],
            "publish_notes": [
                str(note) for note in payload.get("publish_notes", post.get("publish_notes", [])) if str(note).strip()
            ],
            "revision_notes": [str(note) for note in payload.get("revision_notes", []) if str(note).strip()],
        }

    def _risk_from_keywords(self, text: str, keywords: list[str]) -> int:
        hits = sum(1 for keyword in keywords if keyword.lower() in text)
        return min(100, hits * 35)

    def _keyword_issue(self, category: str, finding: str, suggestion: str) -> ReviewIssue:
        return ReviewIssue(category=category, severity="medium", finding=finding, evidence="命中风险词规则。", suggestion=suggestion)

    def _evidence_used(self, hotspot: dict[str, Any], evidence: list[dict[str, str]]) -> list[dict[str, str]]:
        records = evidence or []
        if not records and hotspot:
            records = [
                {
                    "title": str(hotspot.get("title") or ""),
                    "source": str(hotspot.get("source") or ""),
                    "url": str(hotspot.get("url") or ""),
                    "published": str(hotspot.get("published") or ""),
                }
            ]
        return [
            {
                "title": str(item.get("title") or ""),
                "source": str(item.get("source") or ""),
                "url": str(item.get("url") or ""),
                "published": str(item.get("published") or ""),
            }
            for item in records[:6]
        ]

    def _clamp(self, value: Any) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = 0
        return max(0, min(100, number))

    def _status(self, value: str) -> str:
        return value if value in {"pass", "revise", "block"} else "revise"

    def _status_summary(self, status: str) -> str:
        return {
            "pass": "未发现明显来源或合规问题，可以进入发布前人工快速复核。",
            "revise": "存在可修正的表达风险，建议按修改点调整后再发布。",
            "block": "来源或合规风险较高，暂不建议发布。",
        }[status]
