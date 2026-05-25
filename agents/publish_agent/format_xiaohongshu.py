from __future__ import annotations

from agents.publish_agent.schema import PublishPost


class XiaohongshuFormatter:
    def format_markdown(self, post: PublishPost) -> str:
        lines = [
            f"# {post.title}",
            "",
            "## 正文",
            post.body,
            "",
            "## 标签",
            " ".join(post.hashtags),
            "",
            "## 图片",
        ]
        if post.images:
            lines.extend(f"- {image.asset}" for image in post.images)
        else:
            lines.append("- 暂无")
        if post.warnings:
            lines.extend(["", "## 发布前提醒", *[f"- {warning}" for warning in post.warnings]])
        lines.append("")
        return "\n".join(lines)
