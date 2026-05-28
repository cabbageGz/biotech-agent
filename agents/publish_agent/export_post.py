from __future__ import annotations

import shutil
import zipfile
from datetime import date
from pathlib import Path

from agents.publish_agent.format_xiaohongshu import XiaohongshuFormatter
from agents.publish_agent.schema import PublishPackage
from tools.http import HTTPClient
from tools.oss import AliyunOSSClient


class PublishExporter:
    def __init__(self, formatter: XiaohongshuFormatter | None = None, oss_client: AliyunOSSClient | None = None) -> None:
        self.formatter = formatter or XiaohongshuFormatter()
        self.oss_client = oss_client or AliyunOSSClient()
        self.http = HTTPClient(timeout=120, retries=2, backoff=0.8)

    def export_zip(self, package: PublishPackage, run_dir: Path) -> str:
        export_dir = run_dir / "publish_export"
        if export_dir.exists():
            shutil.rmtree(export_dir)
        export_dir.mkdir(parents=True)

        for index, post in enumerate(package.posts, start=1):
            safe_title = self._safe_name(post.title)[:36] or f"hotspot_{index:02d}"
            post_dir = export_dir / f"{index:02d}_{safe_title}"
            post_dir.mkdir()
            (post_dir / "文案汇总.txt").write_text(self.formatter.format_markdown(post), encoding="utf-8")
            for image_index, image in enumerate(post.images, start=1):
                suffix = Path(image.asset).suffix or ".png"
                target = post_dir / f"image_{image_index:02d}{suffix}"
                if image.oss_key and self.oss_client.available:
                    self._download_to_file(self.oss_client.signed_url(image.oss_key, expires_in=1800), target)
                    continue
                if image.image_url:
                    self._download_to_file(image.image_url, target)
                    continue
                source = run_dir / image.asset
                if source.exists():
                    shutil.copy2(source, target)

        date_suffix = self._date_suffix(package.run_id)
        zip_name = f"publish_export_{date_suffix}.zip"
        zip_path = run_dir / zip_name
        if zip_path.exists():
            zip_path.unlink()
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in export_dir.rglob("*"):
                if path.is_file():
                    archive.write(path, path.relative_to(export_dir))
        return zip_name

    def _safe_name(self, value: str) -> str:
        return "".join(char if char.isalnum() or char in "-_ " else "_" for char in value).strip()

    def _date_suffix(self, run_id: str) -> str:
        if len(run_id) >= 8 and run_id[:8].isdigit():
            return run_id[:8]
        return date.today().strftime("%Y%m%d")

    def _download_to_file(self, url: str, target: Path) -> None:
        target.write_bytes(self.http.get(url, timeout=120).body)
