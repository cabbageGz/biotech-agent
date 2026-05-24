from __future__ import annotations

import html
import re


TAG_PATTERN = re.compile(r"<[^>]+>")
SPACE_PATTERN = re.compile(r"\s+")


def strip_html(value: str) -> str:
    text = TAG_PATTERN.sub(" ", value or "")
    return compact_text(html.unescape(text))


def compact_text(value: str, max_chars: int | None = None) -> str:
    text = SPACE_PATTERN.sub(" ", value or "").strip()
    if max_chars and len(text) > max_chars:
        return text[: max_chars - 3].rstrip() + "..."
    return text
