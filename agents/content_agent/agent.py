from __future__ import annotations

from dataclasses import dataclass, asdict
import re
from typing import Any

from agents.research_agent.agent import ResearchReport
from tools.llm import DeepSeekClient, LLMError


REFERENCE_TAG_PATTERN = re.compile(r"#?记录吧就现在\s*")


@dataclass
class XiaohongshuPost:
    title: str
    hook: str
    body: str
    hashtags: list[str]
    publish_notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def cleaned(self) -> "XiaohongshuPost":
        return XiaohongshuPost(
            title=REFERENCE_TAG_PATTERN.sub("", self.title).strip(),
            hook=REFERENCE_TAG_PATTERN.sub("", self.hook).strip(),
            body=REFERENCE_TAG_PATTERN.sub("", self.body).strip(),
            hashtags=[tag for tag in self.hashtags if "记录吧就现在" not in tag],
            publish_notes=self.publish_notes,
        )


class ContentAgent:
    """Turns research hotspots into a publish-ready Xiaohongshu draft."""

    def __init__(self, llm: DeepSeekClient | None = None) -> None:
        self.llm = llm or DeepSeekClient()

    def create_post(
        self,
        report: ResearchReport,
        style_reference: dict[str, Any] | None = None,
        content_options: dict[str, Any] | None = None,
    ) -> XiaohongshuPost:
        posts = self.create_posts(
            report=report,
            style_reference=style_reference,
            content_options=content_options,
        )
        if posts:
            return posts[0]
        return self._fallback_post(report)

    def create_posts(
        self,
        report: ResearchReport,
        style_reference: dict[str, Any] | None = None,
        content_options: dict[str, Any] | None = None,
    ) -> list[XiaohongshuPost]:
        if self.llm.available:
            try:
                return self._create_ai_posts(
                    report,
                    style_reference=style_reference or {},
                    content_options=content_options or {},
                )
            except LLMError:
                pass
        return [self._fallback_post_for_hotspot(item, index) for index, item in enumerate(report.hotspots, start=1)]

    def _fallback_post(self, report: ResearchReport) -> XiaohongshuPost:
        top_titles = [item.title for item in report.hotspots[:3]]
        title = "今日生物医药热点：临床、交易与新技术信号"
        if top_titles:
            title = f"今日生物医药热点：{self._short_title(top_titles[0])}"

        hook = "今天的生物医药新闻，重点不只是“发生了什么”，更要看它可能改变哪条赛道的预期。"
        body_parts = [hook, ""]
        for index, item in enumerate(report.hotspots, start=1):
            body_parts.extend(
                [
                    f"{index}. {item.title}",
                    f"一句话：{item.summary}",
                    f"为什么重要：{item.why_it_matters}",
                    f"关键词：{' / '.join(item.tags)}",
                    "",
                ]
            )
        body_parts.extend(
            [
                "今日观察：",
                "创新药新闻的价值，往往藏在临床节点、交易价格、适应症选择和大药企管线取舍里。单条新闻不要过度解读，但连续信号值得跟踪。",
                "",
                "资料来自公开行业信息，仅作行业学习与信息整理，不构成医疗或投资建议。",
            ]
        )
        hashtags = self._hashtags(report)
        publish_notes = [
            "配图建议：使用“今日热点 + 3 个关键词”的信息图，不使用药品疗效暗示图片",
            "首图标题建议控制在 18 字以内",
            "评论区可引导：你最关注哪条管线或赛道？",
        ]
        return XiaohongshuPost(
            title=title,
            hook=hook,
            body="\n".join(body_parts),
            hashtags=hashtags,
            publish_notes=publish_notes,
        ).cleaned()

    def _fallback_post_for_hotspot(self, item: Any, index: int) -> XiaohongshuPost:
        title = f"{self._short_title(item.title)}｜值得关注"
        body = "\n".join(
            [
                f"{item.title}",
                "",
                f"一句话：{item.summary}",
                f"为什么重要：{item.why_it_matters}",
                f"关键词：{' / '.join(item.tags)}",
                "",
                "资料来自公开信息，仅作行业学习与信息整理，不构成医疗或投资建议。",
            ]
        )
        tags = ["#生物医药", "#创新药", *[f"#{tag}" for tag in item.tags]][:8]
        return XiaohongshuPost(
            title=title,
            hook=f"第 {index} 条热点，值得单独看一眼。",
            body=body,
            hashtags=tags,
            publish_notes=[
                "配图建议：围绕本条热点做单页信息图",
                "评论区可引导读者讨论该赛道后续变化",
            ],
        )

    def _create_ai_posts(
        self,
        report: ResearchReport,
        style_reference: dict[str, Any],
        content_options: dict[str, Any],
    ) -> list[XiaohongshuPost]:
        reference_text = ""
        if style_reference:
            reference_text = (
                f"参考小红书标题：{style_reference.get('title', '')}\n"
                f"参考正文：{style_reference.get('description', '')}\n"
                f"参考关键词：{style_reference.get('keywords', [])}\n"
                "请学习它的表达结构：标题具体、有收藏感；正文用口语化开头、编号要点、数据说话、小科普和结尾提醒。"
                "不要照抄参考内容，不要复用其药物事实，必须围绕今日热点重写。"
                "不要使用参考笔记里的固定话题标签或口号，例如“#记录吧就现在”。"
            )
        content_words = int(content_options.get("content_words") or 700)
        content_instruction = str(content_options.get("content_instruction") or "").strip()
        format_reference = str(content_options.get("format_reference") or "").strip()
        custom_text = (
            f"用户自定义内容要求：{content_instruction}\n" if content_instruction else "用户自定义内容要求：无\n"
        )
        format_text = (
            f"用户自定义格式参考：{format_reference}\n请优先按照这个格式组织每套文案。\n"
            if format_reference
            else "用户未提供格式参考，请使用当前默认格式：口语化开头、编号要点、数据说话、小科普、结尾免责声明。\n"
        )
        payload = self.llm.chat_json(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是小红书生物医药内容编辑。输出严格 JSON，不要 Markdown。"
                        "风格要清晰、有信息密度、克制，不夸大医疗疗效，不构成投资建议。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "请基于以下热点生成一篇可发布的小红书文案。"
                        "每个热点都必须单独生成一套完整小红书发布文案，不要合并成一篇总文案。"
                        "JSON schema: {\"posts\":[{\"title\":\"不超过28字\", \"hook\":\"开头金句\","
                        "\"body\":\"正文，包含每条热点的一句话和为什么重要\","
                        "\"hashtags\":[\"#标签\"], \"publish_notes\":[\"发布建议\"]}]}。"
                        f"每套文案正文控制在约 {content_words} 个中文字，可上下浮动 15%。"
                        f"{custom_text}"
                        f"{format_text}"
                        "每套正文最后都必须包含：资料来自公开信息，仅作行业学习与信息整理，不构成医疗或投资建议。\n\n"
                        f"{reference_text}\n\n"
                        f"热点：{report.to_dict()}"
                    ),
                },
            ],
            max_tokens=7000,
            temperature=0.45,
        )
        posts = []
        for item in payload.get("posts", []):
            if not isinstance(item, dict):
                continue
            posts.append(
                XiaohongshuPost(
                    title=str(item.get("title") or "今日生物医药热点"),
                    hook=str(item.get("hook") or ""),
                    body=str(item.get("body") or ""),
                    hashtags=[str(tag) for tag in item.get("hashtags", []) if str(tag).strip()],
                    publish_notes=[str(note) for note in item.get("publish_notes", []) if str(note).strip()],
                ).cleaned()
            )
        return posts or [self._fallback_post_for_hotspot(item, index) for index, item in enumerate(report.hotspots, start=1)]

    def _short_title(self, text: str) -> str:
        cleaned = " ".join(text.split())
        return cleaned[:24] + ("..." if len(cleaned) > 24 else "")

    def _hashtags(self, report: ResearchReport) -> list[str]:
        tags = ["生物医药", "创新药", "医药行业", "Biotech"]
        for item in report.hotspots:
            for tag in item.tags:
                if tag not in tags:
                    tags.append(tag)
        return [f"#{tag}" for tag in tags[:10]]

    def render_markdown(self, post: XiaohongshuPost) -> str:
        return "\n".join(
            [
                f"# {post.title}",
                "",
                "## 正文",
                post.body,
                "",
                "## 标签",
                " ".join(post.hashtags),
                "",
                "## 发布备注",
                *[f"- {note}" for note in post.publish_notes],
                "",
            ]
        )

    def render_posts_markdown(self, posts: list[XiaohongshuPost]) -> str:
        sections: list[str] = ["# 小红书单条热点发布文案", ""]
        for index, post in enumerate(posts, start=1):
            sections.extend(
                [
                    f"## {index}. {post.title}",
                    "",
                    "### 正文",
                    post.body,
                    "",
                    "### 标签",
                    " ".join(post.hashtags),
                    "",
                    "### 发布备注",
                    *[f"- {note}" for note in post.publish_notes],
                    "",
                ]
            )
        return "\n".join(sections)
