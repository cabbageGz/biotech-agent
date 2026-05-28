from __future__ import annotations

import html
import re
from dataclasses import dataclass

from tools.http import HTTPClient
from tools.rss.reader import RSSItem
from tools.scraper.extractor import compact_text, strip_html


WUXI_ORIGIN = "https://www.wuxiapptec.cn"


@dataclass(frozen=True)
class WuXiSection:
    url: str
    source: str


DEFAULT_SECTIONS = [
    WuXiSection(
        url=f"{WUXI_ORIGIN}/news/wuxi-news",
        source="药明康德 / 公司新闻",
    ),
    WuXiSection(
        url=f"{WUXI_ORIGIN}/news/media-coverage",
        source="药明康德 / 媒体文章",
    ),
]


class WuXiAppTecClient:
    """Reads public WuXi AppTec news pages."""

    def __init__(self, http: HTTPClient | None = None, timeout: int = 16) -> None:
        self.http = http or HTTPClient(timeout=timeout, retries=2, backoff=0.5)
        self.timeout = timeout

    def fetch_latest(self, max_items: int = 10) -> list[RSSItem]:
        items: list[RSSItem] = []
        for section in DEFAULT_SECTIONS:
            response = self.http.get(
                section.url,
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Referer": WUXI_ORIGIN,
                },
                timeout=self.timeout,
            )
            items.extend(self.parse_listing(response.text(), section=section))
        return self._dedupe(items)[:max_items]

    def parse_listing(self, html_text: str, section: WuXiSection) -> list[RSSItem]:
        items: list[RSSItem] = []
        for match in re.finditer(
            r'<div class="list-item"[^>]*>\s*'
            r'<p class="date"[^>]*>(?P<date>[\s\S]*?)</p>\s*'
            r'<h1 class="title"[^>]*>(?P<title>[\s\S]*?)</h1>\s*'
            r'<p class="content"[^>]*>(?P<summary>[\s\S]*?)</p>\s*'
            r'<a href="(?P<href>[^"]+)"',
            html_text,
        ):
            title = strip_html(self._decode(match.group("title")))
            href = self._absolute_url(self._decode(match.group("href")))
            if not title or not href:
                continue
            items.append(
                RSSItem(
                    title=title,
                    link=href,
                    summary=compact_text(strip_html(self._decode(match.group("summary"))), max_chars=420),
                    source=section.source,
                    published=self._normalize_date(strip_html(self._decode(match.group("date")))),
                )
            )
        return items

    def _absolute_url(self, href: str) -> str:
        if href.startswith("http://") or href.startswith("https://"):
            return href
        if href.startswith("/"):
            return f"{WUXI_ORIGIN}{href}"
        return f"{WUXI_ORIGIN}/{href}"

    def _normalize_date(self, value: str) -> str:
        text = compact_text(value)
        match = re.fullmatch(r"(\d{4})/(\d{1,2})/(\d{1,2})", text)
        if not match:
            return text
        year, month, day = match.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"

    def _decode(self, value: str) -> str:
        return html.unescape(value or "").replace("\xa0", " ")

    def _dedupe(self, items: list[RSSItem]) -> list[RSSItem]:
        seen: set[str] = set()
        result: list[RSSItem] = []
        for item in sorted(items, key=lambda candidate: candidate.published, reverse=True):
            key = item.link or item.title
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result
