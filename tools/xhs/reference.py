from __future__ import annotations

import html
import re
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any

from tools.scraper.extractor import compact_text


REFERENCE_TAG_PATTERN = re.compile(r"#?记录吧就现在\s*")


@dataclass
class XiaohongshuReference:
    url: str
    final_url: str = ""
    title: str = ""
    description: str = ""
    keywords: list[str] | None = None
    images: list[str] | None = None
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["keywords"] = self.keywords or []
        payload["images"] = self.images or []
        return payload

    def render_markdown(self) -> str:
        lines = [
            "# 小红书参考笔记",
            f"原始链接：{self.url}",
            f"最终链接：{self.final_url or '未获取'}",
            f"标题：{self.title or '未获取'}",
            f"关键词：{', '.join(self.keywords or [])}",
            "",
            "## 正文描述",
            self.description or "未获取",
        ]
        if self.images:
            lines.append("")
            lines.append("## 图片")
            lines.extend(f"- {item}" for item in self.images)
        if self.error:
            lines.append("")
            lines.append(f"错误：{self.error}")
        return "\n".join(lines) + "\n"


class XiaohongshuReferenceExtractor:
    def __init__(self, timeout: int = 15) -> None:
        self.timeout = timeout

    def fetch(self, url: str) -> XiaohongshuReference:
        reference = XiaohongshuReference(url=url, keywords=[], images=[])
        if not url.strip():
            return reference
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                )
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                reference.final_url = response.geturl()
                html_text = response.read().decode("utf-8", errors="replace")
        except Exception as exc:
            reference.error = str(exc)
            return reference

        reference.title = self._meta(html_text, "og:title") or self._title(html_text)
        reference.description = self._meta(html_text, "description") or self._meta(html_text, "og:description")
        reference.keywords = self._keywords(self._meta(html_text, "keywords"))
        reference.images = self._images(html_text)
        reference.title = compact_text(REFERENCE_TAG_PATTERN.sub("", reference.title.replace(" - 小红书", "")))
        reference.description = compact_text(
            REFERENCE_TAG_PATTERN.sub("", html.unescape(reference.description)),
            max_chars=2400,
        )
        reference.keywords = [item for item in reference.keywords if item != "记录吧就现在"]
        return reference

    def _meta(self, html_text: str, name: str) -> str:
        patterns = [
            rf'<meta[^>]+name=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']*)',
            rf'<meta[^>]+property=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']*)',
        ]
        for pattern in patterns:
            match = re.search(pattern, html_text, flags=re.IGNORECASE)
            if match:
                return html.unescape(match.group(1))
        return ""

    def _title(self, html_text: str) -> str:
        match = re.search(r"<title[^>]*>(.*?)</title>", html_text, flags=re.IGNORECASE | re.DOTALL)
        return html.unescape(match.group(1)) if match else ""

    def _keywords(self, value: str) -> list[str]:
        return [item.strip() for item in re.split(r"[,，#\s]+", value or "") if item.strip()]

    def _images(self, html_text: str) -> list[str]:
        images: list[str] = []
        for match in re.finditer(
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']*)',
            html_text,
            flags=re.IGNORECASE,
        ):
            image = html.unescape(match.group(1))
            if image and image not in images:
                images.append(image)
        return images[:8]
