from __future__ import annotations

from agents.publish_agent.schema import PublishPost


class PublishValidator:
    def validate(self, post: PublishPost) -> list[str]:
        warnings: list[str] = []
        if not post.title.strip():
            warnings.append("缺少标题")
        if not post.body.strip():
            warnings.append("缺少正文")
        if not post.images:
            warnings.append("尚未生成图片")
        if "不构成医疗或投资建议" not in post.body:
            warnings.append("正文缺少合规免责声明")
        return warnings
