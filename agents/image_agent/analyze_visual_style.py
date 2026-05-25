from __future__ import annotations

from typing import Any

from tools.llm import DeepSeekClient, LLMError


class VisualStyleAnalyzer:
    def __init__(self, llm: DeepSeekClient | None = None) -> None:
        self.llm = llm or DeepSeekClient()

    def analyze(self, context: dict[str, Any], user_instruction: str = "") -> dict[str, str]:
        if self.llm.available:
            try:
                return self._ai_analyze(context, user_instruction)
            except LLMError:
                pass
        return self._fallback_analyze(context, user_instruction)

    def _ai_analyze(self, context: dict[str, Any], user_instruction: str) -> dict[str, str]:
        payload = self.llm.chat_json(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是生物医药内容视觉总监。请判断小红书封面的视觉风格。"
                        "只输出严格 JSON，不要 Markdown，不要编造事实。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "根据源新闻、选题评分和已生成发布文案，判断适合的视觉风格。"
                        "JSON schema: {\"style\":\"风格名\", \"composition\":\"构图\","
                        "\"visual_focus\":\"视觉中心\", \"tone\":\"色彩和气质\","
                        "\"avoid\":\"需要避免的画面\"}。\n"
                        f"用户图片要求：{user_instruction or '无'}\n"
                        f"上下文：{context}"
                    ),
                },
            ],
            temperature=0.25,
            max_tokens=1800,
        )
        return {
            "style": str(payload.get("style") or "医药信息图"),
            "composition": str(payload.get("composition") or "标题、视觉中心、三点信息块"),
            "visual_focus": str(payload.get("visual_focus") or "药物研发主题视觉"),
            "tone": str(payload.get("tone") or "专业、清爽、克制"),
            "avoid": str(payload.get("avoid") or "避免密集文字、疗效承诺和投资暗示"),
        }

    def _fallback_analyze(self, context: dict[str, Any], user_instruction: str) -> dict[str, str]:
        text = " ".join(
            str(context.get(key) or "")
            for key in ["title", "summary", "why_it_matters", "post_body", "tags"]
        ).lower()
        if any(word in text for word in ["ai", "人工智能", "model", "大模型"]):
            return {
                "style": "AI制药流程信息图",
                "composition": "左右节点连接，中间用箭头指向药物分子和研发管线",
                "visual_focus": "AI模型节点连接药物发现流程",
                "tone": "冷静科技感，白底或深浅对比，少量蓝绿色点缀",
                "avoid": "避免复杂代码屏、密集参数、真实疗效数据",
            }
        if any(word in text for word in ["phase", "clinical", "trial", "临床", "endpoint"]):
            return {
                "style": "临床节点时间线",
                "composition": "顶部标题，中间横向或纵向临床进展时间线，侧边三张信息卡",
                "visual_focus": "临床试验节点和药物分子示意",
                "tone": "白底、清爽、研究报告感",
                "avoid": "避免患者照片、疗效承诺、具体未核实数据",
            }
        if any(word in text for word in ["deal", "licensing", "合作", "交易", "授权"]):
            return {
                "style": "交易合作结构图",
                "composition": "两家公司/平台节点相连，资产或管线作为视觉中心",
                "visual_focus": "合作关系、资产流向和管线价值卡片",
                "tone": "专业商业感，白底、深绿和蓝色点缀",
                "avoid": "避免股价、收益、夸大金额和投资建议",
            }
        return {
            "style": "生物医药热点信息图",
            "composition": "顶部短标题，中间药物研发视觉中心，底部三点信息块",
            "visual_focus": "分子结构、研发管线、行业信号节点",
            "tone": user_instruction or "专业、清爽、少文字、有信息量",
            "avoid": "避免密集小字、真实患者、真实药盒、疗效承诺、投资收益暗示",
        }
