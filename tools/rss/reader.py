from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

from tools.scraper.extractor import strip_html


DEFAULT_SOURCES_PATH = Path(__file__).with_name("sources.json")


@dataclass
class RSSItem:
    title: str
    link: str
    summary: str
    source: str
    published: str


class RSSReader:
    def __init__(self, sources_path: Path | None = None, timeout: int = 12) -> None:
        self.sources_path = sources_path or DEFAULT_SOURCES_PATH
        self.timeout = timeout

    def fetch_many(self, max_items: int = 24, max_age_days: int = 14) -> tuple[list[RSSItem], list[str]]:
        sources = self._load_sources()
        items: list[RSSItem] = []
        errors: list[str] = []
        for source in sources:
            try:
                items.extend(self.fetch_source(source))
            except Exception as exc:  # Keep the daily run alive if one source breaks.
                errors.append(f"{source.get('name', 'unknown')}: {exc}")
        deduped = self._dedupe(items)
        recent = self._recent_first(deduped, max_age_days=max_age_days)
        return recent[:max_items], errors

    def fetch_source(self, source: dict[str, Any]) -> list[RSSItem]:
        name = str(source["name"])
        url = str(source["url"])
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "biotech-agent/0.1 (+local intelligence workflow)",
                "Accept": "application/rss+xml, application/xml, text/xml, */*",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.URLError as exc:
            raise RuntimeError(getattr(exc, "reason", exc)) from exc
        root = ET.fromstring(self._sanitize_xml(raw))
        return self._parse_feed(root, source_name=name)

    def _parse_feed(self, root: ET.Element, source_name: str) -> list[RSSItem]:
        channel_items = root.findall(".//item")
        if channel_items:
            return [self._parse_rss_item(item, source_name) for item in channel_items]
        atom_items = root.findall(".//{http://www.w3.org/2005/Atom}entry")
        return [self._parse_atom_item(item, source_name) for item in atom_items]

    def _parse_rss_item(self, item: ET.Element, source_name: str) -> RSSItem:
        title = self._text(item, "title")
        link = self._text(item, "link")
        summary = self._text(item, "description") or self._text(item, "summary")
        published = self._normalize_date(self._text(item, "pubDate") or self._text(item, "published"))
        return RSSItem(
            title=strip_html(title),
            link=link.strip(),
            summary=strip_html(summary),
            source=source_name,
            published=published,
        )

    def _parse_atom_item(self, item: ET.Element, source_name: str) -> RSSItem:
        ns = "{http://www.w3.org/2005/Atom}"
        title = item.findtext(f"{ns}title", default="")
        summary = item.findtext(f"{ns}summary", default="") or item.findtext(f"{ns}content", default="")
        published = item.findtext(f"{ns}published", default="") or item.findtext(f"{ns}updated", default="")
        link = ""
        for candidate in item.findall(f"{ns}link"):
            if candidate.attrib.get("href"):
                link = candidate.attrib["href"]
                break
        return RSSItem(
            title=strip_html(title),
            link=link.strip(),
            summary=strip_html(summary),
            source=source_name,
            published=self._normalize_date(published),
        )

    def _text(self, item: ET.Element, name: str) -> str:
        found = item.find(name)
        if found is not None and found.text:
            return found.text
        for child in item:
            if child.tag.endswith(name) and child.text:
                return child.text
        return ""

    def _normalize_date(self, value: str) -> str:
        text = value.strip()
        if not text:
            return ""
        try:
            return parsedate_to_datetime(text).isoformat()
        except (TypeError, ValueError, IndexError):
            return text

    def _dedupe(self, items: list[RSSItem]) -> list[RSSItem]:
        seen: set[str] = set()
        result: list[RSSItem] = []
        for item in items:
            key = re.sub(r"\W+", "", (item.link or item.title).lower())
            if not key or key in seen:
                continue
            seen.add(key)
            if item.title:
                result.append(item)
        return result

    def _recent_first(self, items: list[RSSItem], max_age_days: int) -> list[RSSItem]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        dated: list[tuple[datetime, RSSItem]] = []
        unknown: list[RSSItem] = []
        for item in items:
            parsed = self._parse_datetime(item.published)
            if parsed is None:
                unknown.append(item)
                continue
            if parsed >= cutoff:
                dated.append((parsed, item))
        dated.sort(key=lambda pair: pair[0], reverse=True)
        # Keep a very small number of undated RSS items only as a fallback, and
        # always place them after verified recent items.
        unknown_limit = max(0, min(3, len(dated) // 4))
        return [item for _, item in dated] + unknown[:unknown_limit]

    def _parse_datetime(self, value: str) -> datetime | None:
        text = value.strip()
        if not text:
            return None
        normalized = text.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass
        try:
            parsed = parsedate_to_datetime(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except (TypeError, ValueError, IndexError):
            return None

    def _load_sources(self) -> list[dict[str, Any]]:
        return json.loads(self.sources_path.read_text(encoding="utf-8"))

    def _sanitize_xml(self, raw: bytes) -> str:
        text = raw.decode("utf-8", errors="replace")
        return re.sub(r"&(?!amp;|lt;|gt;|quot;|apos;|#[0-9]+;|#x[0-9a-fA-F]+;)", "&amp;", text)
