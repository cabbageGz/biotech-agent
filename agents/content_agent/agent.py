from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from agents.research_agent.agent import ResearchReport
from tools.llm import DeepSeekClient, LLMError


@dataclass
class XiaohongshuPost:
    title: str
    hook: str
    body: str
    hashtags: list[str]
    publish_notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ContentAgent:
    """Turns research hotspots into a publish-ready Xiaohongshu draft."""

    def __init__(self, llm: DeepSeekClient | None = None) -> None:
        self.llm = llm or DeepSeekClient()

    def create_post(self, report: ResearchReport) -> XiaohongshuPost:
        if self.llm.available:
            try:
                return self._create_ai_post(report)
            except LLMError:
                pass
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
        )

    def _create_ai_post(self, report: ResearchReport) -> XiaohongshuPost:
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
                        "JSON schema: {\"title\":\"不超过28字\", \"hook\":\"开头金句\","
                        "\"body\":\"正文，包含每条热点的一句话和为什么重要\","
                        "\"hashtags\":[\"#标签\"], \"publish_notes\":[\"发布建议\"]}。"
                        "正文最后必须包含：资料来自公开信息，仅作行业学习与信息整理，不构成医疗或投资建议。\n\n"
                        f"热点：{report.to_dict()}"
                    ),
                },
            ],
            max_tokens=4500,
            temperature=0.45,
        )
        return XiaohongshuPost(
            title=str(payload.get("title") or "今日生物医药热点"),
            hook=str(payload.get("hook") or ""),
            body=str(payload.get("body") or ""),
            hashtags=[str(tag) for tag in payload.get("hashtags", []) if str(tag).strip()],
            publish_notes=[str(note) for note in payload.get("publish_notes", []) if str(note).strip()],
        )

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
