from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from agents.image_agent.analyze_visual_style import VisualStyleAnalyzer
from agents.image_agent.generate_cover_text import CoverTextGenerator
from tools.llm import DeepSeekClient, LLMError


@dataclass
class ImagePromptOption:
    title: str
    style: str
    cover_text: dict[str, Any]
    prompt: str
    rationale: str
    image_role: str = "cover"
    sequence: int = 1
    score: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ImagePromptGenerator:
    def __init__(
        self,
        llm: DeepSeekClient | None = None,
        style_analyzer: VisualStyleAnalyzer | None = None,
        text_generator: CoverTextGenerator | None = None,
    ) -> None:
        self.llm = llm or DeepSeekClient()
        self.style_analyzer = style_analyzer or VisualStyleAnalyzer(self.llm)
        self.text_generator = text_generator or CoverTextGenerator()

    def generate(
        self,
        context: dict[str, Any],
        image_size_label: str,
        user_instruction: str = "",
        count: int = 5,
    ) -> list[ImagePromptOption]:
        count = max(1, min(5, count))
        style = self.style_analyzer.analyze(context, user_instruction=user_instruction)
        cover_text = self.text_generator.generate(context)
        if self.llm.available:
            try:
                options = self._ai_generate(context, style, cover_text, image_size_label, user_instruction, count)
                if options:
                    return options
            except LLMError:
                pass
        return self._fallback_generate(context, style, cover_text, image_size_label, user_instruction, count)

    def _ai_generate(
        self,
        context: dict[str, Any],
        style: dict[str, str],
        cover_text: dict[str, Any],
        image_size_label: str,
        user_instruction: str,
        count: int,
    ) -> list[ImagePromptOption]:
        payload = self.llm.chat_json(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是生物医药小红书封面图 Prompt 设计师。"
                        "请根据发布文案规划一套小红书图组，并输出可直接给通义万相使用的中文 Prompt。只输出严格 JSON。"
                        "不要让图片生成模型编造具体数据。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"请决定这个主题适合生成几张图，最多 {count} 张。推荐结构通常是 1 张封面图 + 2-4 张内容卡片。"
                        "每张图必须承担不同功能，不要只是换风格。"
                        "JSON schema: {\"image_count\":3,\"strategy\":\"图组策略\","
                        "\"options\":[{\"sequence\":1,\"image_role\":\"cover|content_card\","
                        "\"title\":\"图名\", \"style\":\"视觉风格\","
                        "\"prompt\":\"可直接给万相的完整Prompt\", \"rationale\":\"为什么需要这张图\"}]}。\n"
                        f"图片尺寸：{image_size_label}\n"
                        f"用户要求：{user_instruction or '无'}\n"
                        f"视觉判断：{style}\n"
                        f"画面文字白名单：{cover_text}\n"
                        f"源新闻和文案上下文：{context}\n"
                        "硬性要求：封面图只允许使用白名单中的标题、三个信息块和标签作为画面文字；"
                        "内容卡片可以从文案中抽取极短小标题和 2-3 个事实点，但必须来自给定文案或证据；"
                        "每张图中文字总量控制在 70 个中文字符以内；"
                        "不要输出来源链接、长段落、脚注、曲线坐标或未经证实的数值；"
                        "不要出现真实患者、真实药盒、疗效承诺、投资收益暗示。"
                    ),
                },
            ],
            temperature=0.45,
            max_tokens=6000,
        )
        options: list[ImagePromptOption] = []
        for raw in payload.get("options", []):
            if not isinstance(raw, dict):
                continue
            prompt = str(raw.get("prompt") or "").strip()
            if not prompt:
                continue
            options.append(
                ImagePromptOption(
                    title=str(raw.get("title") or f"方案 {len(options) + 1}"),
                    style=str(raw.get("style") or style.get("style") or "医药信息图"),
                    cover_text=cover_text,
                    prompt=prompt,
                    rationale=str(raw.get("rationale") or ""),
                    image_role=self._role(str(raw.get("image_role") or ("cover" if len(options) == 0 else "content_card"))),
                    sequence=self._sequence(raw.get("sequence"), len(options) + 1),
                )
            )
        return options[:count]

    def _fallback_generate(
        self,
        context: dict[str, Any],
        style: dict[str, str],
        cover_text: dict[str, Any],
        image_size_label: str,
        user_instruction: str,
        count: int,
    ) -> list[ImagePromptOption]:
        title = str(cover_text["title"])
        blocks = [str(item) for item in cover_text["blocks"][:3]]
        labels = "、".join(str(item) for item in cover_text.get("labels", [])[:3]) or "行业热点"
        fact_context = self._fact_context(context)
        planned_count = min(count, self._recommended_count(context))
        directions = [
            ("封面图", "cover", style.get("style", "医药信息图"), style.get("composition", "标题、视觉中心、三点信息块")),
            ("内容卡 1：发生了什么", "content_card", "事实拆解卡", "左侧简短标题，右侧 2-3 个事实点，中间用分子或管线节点连接"),
            ("内容卡 2：为什么重要", "content_card", "产业意义卡", "中心放行业影响路径，周围三张短信息块"),
            ("内容卡 3：后续观察", "content_card", "观察清单卡", "用时间线或清单展示后续监管、临床、合作或商业化观察点"),
            ("内容卡 4：证据摘要", "content_card", "证据来源卡", "展示来源类型和信息层级，不放长链接，不放脚注"),
        ]
        options: list[ImagePromptOption] = []
        for sequence, (option_title, image_role, option_style, composition) in enumerate(directions[:planned_count], start=1):
            text_limit = "45" if image_role == "cover" else "70"
            role_instruction = (
                "这是图组第1张封面图，负责吸引点击并概括主题。"
                if image_role == "cover"
                else f"这是图组第{sequence}张内容卡片，负责解释「{option_title.replace('内容卡 ', '')}」。"
            )
            prompt = (
                f"生成一张适合小红书图组的生物医药热点图片，{image_size_label}，{option_style}。"
                f"{role_instruction}"
                f"构图：{composition}。视觉中心：{style.get('visual_focus', '药物研发主题视觉')}。"
                f"画面文字白名单：主标题「{title}」；三个重点信息块「{blocks[0]}」「{blocks[1]}」「{blocks[2]}」；"
                f"角标/标签「{labels}」。除此之外不要出现任何长段落、来源链接、日期、脚注或密集小字。"
                f"整张图中文字总量控制在{text_limit}个中文字符以内，保留充足留白。"
                f"色彩和气质：{style.get('tone', '专业、清爽、克制')}。"
                f"用户额外要求：{user_instruction or '无'}。"
                f"事实背景仅供理解，不要把它排版进画面：{fact_context}"
                "事实准确性要求：公司名、药物名、阶段、金额、比例、会议名、监管结论只能来自白名单文字；"
                "不要自行编造数据、曲线坐标、试验结果、疗效、安全性或投资含义。"
                f"避免：{style.get('avoid', '真实患者、真实药盒、疗效承诺、投资收益暗示')}。"
            )
            options.append(
                ImagePromptOption(
                    title=option_title,
                    style=option_style,
                    cover_text=cover_text,
                    prompt=prompt,
                    rationale=f"适合从“{style.get('style', '医药信息图')}”角度表达该主题。",
                    image_role=image_role,
                    sequence=sequence,
                )
            )
        return options

    def _fact_context(self, context: dict[str, Any]) -> str:
        evidence = context.get("evidence") or []
        evidence_text = "；".join(
            f"{item.get('source', '公开信息')}：{item.get('title', '')}"
            for item in evidence[:3]
            if isinstance(item, dict)
        )
        return (
            f"主题：{context.get('title', '')}。摘要：{context.get('summary', '')}。"
            f"发布文案：{str(context.get('post_body') or '')[:180]}。证据：{evidence_text or '公开信息'}。"
        )

    def _recommended_count(self, context: dict[str, Any]) -> int:
        body = str(context.get("post_body") or context.get("summary") or "")
        evidence_count = len([item for item in context.get("evidence", []) if isinstance(item, dict)])
        sections = sum(1 for marker in ["为什么", "小科普", "后续", "观察", "一句话", "1.", "2.", "3."] if marker in body)
        if len(body) > 650 or evidence_count >= 3 or sections >= 4:
            return 5
        if len(body) > 420 or evidence_count >= 2 or sections >= 2:
            return 4
        return 3

    def _role(self, value: str) -> str:
        return "content_card" if value == "content_card" else "cover"

    def _sequence(self, value: Any, fallback: int) -> int:
        try:
            return max(1, int(value))
        except (TypeError, ValueError):
            return fallback
