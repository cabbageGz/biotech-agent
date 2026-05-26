from __future__ import annotations

from typing import Any

from agents.publish_agent.schema import PublishImage, PublishPackage, PublishPost
from agents.publish_agent.validate_post import PublishValidator


class PublishPackager:
    def __init__(self, validator: PublishValidator | None = None) -> None:
        self.validator = validator or PublishValidator()

    def package(self, run: dict[str, Any]) -> PublishPackage:
        covers_by_source: dict[int, dict[str, Any]] = {}
        for cover in run.get("item_covers", []):
            if isinstance(cover, dict):
                covers_by_source[int(cover.get("source_index", cover.get("index", -1)))] = cover

        raw_posts = [post for post in run.get("item_posts", []) if isinstance(post, dict)]
        order = [int(item) for item in run.get("publish_order", []) if str(item).lstrip("-").isdigit()]
        if order:
            order_rank = {source_index: rank for rank, source_index in enumerate(order)}
            raw_posts = sorted(
                enumerate(raw_posts),
                key=lambda pair: order_rank.get(int(pair[1].get("source_index", pair[0])), len(order) + pair[0]),
            )
            raw_posts = [post for _, post in raw_posts]

        posts: list[PublishPost] = []
        for index, raw_post in enumerate(raw_posts):
            source_index = int(raw_post.get("source_index", index))
            cover = covers_by_source.get(source_index, {})
            images = [
                PublishImage(
                    asset=str(image.get("asset") or ""),
                    prompt=str(image.get("prompt") or ""),
                    prompt_index=int(image.get("prompt_index") or 0),
                    size=str(image.get("size") or ""),
                    model=str(image.get("model") or ""),
                )
                for image in cover.get("images", [])
                if isinstance(image, dict) and image.get("asset")
            ]
            if not images and cover.get("asset"):
                images.append(
                    PublishImage(
                        asset=str(cover.get("asset") or ""),
                        prompt=str(cover.get("prompt") or ""),
                        prompt_index=0,
                        size=str(cover.get("size") or ""),
                        model=str(cover.get("model") or ""),
                    )
                )
            post = PublishPost(
                source_index=source_index,
                title=str(raw_post.get("title") or cover.get("title") or f"发布内容 {len(posts) + 1}"),
                body=str(raw_post.get("body") or ""),
                hashtags=[str(tag) for tag in raw_post.get("hashtags", []) if str(tag).strip()],
                images=images,
                warnings=[],
            )
            post.warnings = self.validator.validate(post)
            posts.append(post)

        warnings = [warning for post in posts for warning in post.warnings]
        return PublishPackage(run_id=str(run.get("run_id") or ""), posts=posts, warnings=warnings)
