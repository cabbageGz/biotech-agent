from __future__ import annotations

import re
from typing import Any


class CoverTextGenerator:
    def generate(self, context: dict[str, Any]) -> dict[str, Any]:
        title = self._short_title(str(context.get("post_title") or context.get("title") or "生物医药热点"))
        tags = [str(tag) for tag in context.get("tags", []) if str(tag).strip()]
        text = " ".join(
            str(context.get(key) or "")
            for key in ["title", "summary", "why_it_matters", "post_body", "score_reason"]
        ).lower()
        blocks = self._blocks_for(text, tags)
        return {
            "title": title,
            "blocks": blocks,
            "labels": tags[:3] or ["行业信号"],
            "text_budget": "整张图中文字控制在45个中文字符以内",
        }

    def _blocks_for(self, text: str, tags: list[str]) -> list[str]:
        if any(word in text for word in ["ai", "人工智能", "大模型", "model"]):
            return ["AI模型", "研发提速", "管线验证"]
        if any(word in text for word in ["phase 3", "phase iii", "iii期", "临床", "endpoint"]):
            return ["临床节点", "关键读出", "后续观察"]
        if any(word in text for word in ["deal", "licensing", "合作", "交易", "授权"]):
            return ["交易合作", "资产流向", "赛道信号"]
        if any(word in text for word in ["fda", "approval", "批准", "审批"]):
            return ["监管进展", "获批信号", "同类竞争"]
        result = tags[:3]
        while len(result) < 3:
            result.append(["行业信号", "技术路线", "后续观察"][len(result)])
        return [self._short_label(item) for item in result[:3]]

    def _short_title(self, value: str) -> str:
        cleaned = re.sub(r"[#｜|:：\-—]+", " ", value)
        cleaned = " ".join(cleaned.split())
        return cleaned[:18] if len(cleaned) > 18 else cleaned

    def _short_label(self, value: str) -> str:
        cleaned = re.sub(r"[#｜|:：\-—]+", " ", value)
        cleaned = "".join(cleaned.split())
        return cleaned[:8] if len(cleaned) > 8 else cleaned
