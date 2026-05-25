from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from agents.publish_agent.format_xiaohongshu import XiaohongshuFormatter
from agents.publish_agent.schema import PublishPackage


class PublishExporter:
    def __init__(self, formatter: XiaohongshuFormatter | None = None) -> None:
        self.formatter = formatter or XiaohongshuFormatter()

    def export_zip(self, package: PublishPackage, run_dir: Path) -> str:
        export_dir = run_dir / "publish_export"
        if export_dir.exists():
            shutil.rmtree(export_dir)
        export_dir.mkdir(parents=True)

        for index, post in enumerate(package.posts, start=1):
            post_dir = export_dir / f"post_{index:02d}"
            post_dir.mkdir()
            (post_dir / "post.md").write_text(self.formatter.format_markdown(post), encoding="utf-8")
            (post_dir / "title.txt").write_text(post.title + "\n", encoding="utf-8")
            (post_dir / "body.txt").write_text(post.body + "\n", encoding="utf-8")
            (post_dir / "hashtags.txt").write_text(" ".join(post.hashtags) + "\n", encoding="utf-8")
            for image_index, image in enumerate(post.images, start=1):
                source = run_dir / image.asset
                if source.exists():
                    shutil.copy2(source, post_dir / f"image_{image_index:02d}{source.suffix}")

        zip_name = "publish_export.zip"
        zip_path = run_dir / zip_name
        if zip_path.exists():
            zip_path.unlink()
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in export_dir.rglob("*"):
                if path.is_file():
                    archive.write(path, path.relative_to(export_dir))
        return zip_name
