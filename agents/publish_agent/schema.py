from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class PublishImage:
    asset: str
    prompt: str
    prompt_index: int
    size: str
    model: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PublishPost:
    source_index: int
    title: str
    body: str
    hashtags: list[str]
    images: list[PublishImage]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "images": [image.to_dict() for image in self.images],
        }


@dataclass
class PublishPackage:
    run_id: str
    posts: list[PublishPost]
    warnings: list[str]
    export_asset: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "posts": [post.to_dict() for post in self.posts],
            "warnings": self.warnings,
            "export_asset": self.export_asset,
        }
