from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from typing import Any

from tools.http import HTTPClient
from tools.rss.reader import RSSItem
from tools.scraper.extractor import compact_text, strip_html


BYDRUG_HOME_URL = "https://bydrug.pharmcube.com/"
BYDRUG_ORIGIN = "https://bydrug.pharmcube.com"


@dataclass
class _NuxtContext:
    aliases: dict[str, Any]


class PharmcubeByDrugClient:
    """Reads public ByDrug homepage SSR data from PharmCube.

    This only consumes content rendered in the public homepage HTML. It does
    not use account cookies, private APIs, or paywalled database endpoints.
    """

    def __init__(self, http: HTTPClient | None = None, timeout: int = 16) -> None:
        self.http = http or HTTPClient(timeout=timeout, retries=2, backoff=0.5)
        self.timeout = timeout

    def fetch_latest(self, max_items: int = 10) -> list[RSSItem]:
        response = self.http.get(
            BYDRUG_HOME_URL,
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Referer": BYDRUG_HOME_URL,
            },
            timeout=self.timeout,
        )
        return self.parse_homepage(response.text(), max_items=max_items)

    def parse_homepage(self, html_text: str, max_items: int = 10) -> list[RSSItem]:
        context = self._parse_nuxt_context(html_text)
        news = self._parse_records(
            html_text,
            array_name="newsPCList",
            context=context,
            kind="news",
        )
        reports = self._parse_records(
            html_text,
            array_name="reportListPCList",
            context=context,
            kind="report",
        )
        items = news + reports
        return self._dedupe(items)[:max_items]

    def _parse_records(
        self,
        html_text: str,
        array_name: str,
        context: _NuxtContext,
        kind: str,
    ) -> list[RSSItem]:
        body = self._extract_array_body(html_text, array_name)
        if not body:
            return []
        records: list[RSSItem] = []
        for object_body in self._iter_object_bodies(body):
            item = self._record_to_item(object_body, context=context, kind=kind)
            if item and item.title:
                records.append(item)
        return records

    def _record_to_item(self, object_body: str, context: _NuxtContext, kind: str) -> RSSItem | None:
        if kind == "news":
            title = self._field_value(object_body, "title", context)
            esid = self._field_value(object_body, "esid", context)
            resource = self._field_value(object_body, "resource", context)
            published = self._field_value(object_body, "publishTime", context)
            summary = self._field_value(object_body, "abstracts", context)
            tags = self._array_field_values(object_body, "tags", context)
            if not self._is_biomed_relevant(f"{title} {summary} {' '.join(tags)} {resource}"):
                return None
            link = f"{BYDRUG_ORIGIN}/news/detail/{esid}" if esid else f"{BYDRUG_ORIGIN}/news"
            tag_text = f"｜标签：{'、'.join(tags[:4])}" if tags else ""
            return RSSItem(
                title=compact_text(title),
                link=link,
                summary=compact_text(f"{strip_html(summary)}{tag_text}", max_chars=420),
                source=self._source_name("医药魔方 ByDrug", resource),
                published=published,
            )

        title = self._field_value(object_body, "fileName", context)
        esid = self._field_value(object_body, "esid", context)
        resource = self._field_value(object_body, "resource", context)
        published = self._field_value(object_body, "publishDate", context)
        summary = self._field_value(object_body, "report_subtitle", context)
        link = f"{BYDRUG_ORIGIN}/report/detail/{esid}" if esid else f"{BYDRUG_ORIGIN}/report"
        return RSSItem(
            title=compact_text(title),
            link=link,
            summary=compact_text(strip_html(summary), max_chars=420),
            source=self._source_name("医药魔方报告", resource),
            published=published,
        )

    def _parse_nuxt_context(self, html_text: str) -> _NuxtContext:
        start = html_text.find("window.__NUXT__=(function(")
        if start < 0:
            return _NuxtContext(aliases={})
        params_start = html_text.find("(", start) + 1
        params_end = html_text.find(")", params_start)
        if params_start <= 0 or params_end < 0:
            return _NuxtContext(aliases={})
        params = [item.strip() for item in html_text[params_start:params_end].split(",") if item.strip()]

        call_start = html_text.rfind("}(", start, html_text.find("</script>", start))
        if call_start < 0:
            return _NuxtContext(aliases={})
        args_start = call_start + 2
        args_end = self._find_matching(html_text, args_start - 1, "(", ")")
        if args_end < 0:
            return _NuxtContext(aliases={})
        args = self._split_top_level(html_text[args_start:args_end])
        aliases = {
            name: self._decode_js_value(value)
            for name, value in zip(params, args)
        }
        return _NuxtContext(aliases=aliases)

    def _extract_array_body(self, html_text: str, array_name: str) -> str:
        marker = f"{array_name}:["
        start = html_text.find(marker)
        if start < 0:
            return ""
        bracket_start = start + len(array_name) + 1
        bracket_end = self._find_matching(html_text, bracket_start, "[", "]")
        if bracket_end < 0:
            return ""
        return html_text[bracket_start + 1 : bracket_end]

    def _iter_object_bodies(self, array_body: str) -> list[str]:
        bodies: list[str] = []
        index = 0
        while index < len(array_body):
            start = array_body.find("{", index)
            if start < 0:
                break
            end = self._find_matching(array_body, start, "{", "}")
            if end < 0:
                break
            bodies.append(array_body[start + 1 : end])
            index = end + 1
        return bodies

    def _field_value(self, object_body: str, field_name: str, context: _NuxtContext) -> str:
        value = self._raw_field_value(object_body, field_name)
        decoded = self._resolve_value(value, context)
        if decoded is None:
            return ""
        return compact_text(str(decoded))

    def _array_field_values(self, object_body: str, field_name: str, context: _NuxtContext) -> list[str]:
        value = self._raw_field_value(object_body, field_name)
        if not value.startswith("[") or not value.endswith("]"):
            return []
        return [
            compact_text(str(item))
            for item in (self._resolve_value(part, context) for part in self._split_top_level(value[1:-1]))
            if item is not None and str(item).strip()
        ]

    def _raw_field_value(self, object_body: str, field_name: str) -> str:
        match = re.search(rf"(?:^|,){re.escape(field_name)}:", object_body)
        if not match:
            return ""
        index = match.end()
        end = self._field_end(object_body, index)
        return object_body[index:end].strip()

    def _field_end(self, text: str, start: int) -> int:
        quote = ""
        escaped = False
        depth = 0
        for index in range(start, len(text)):
            char = text[index]
            if quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = ""
                continue
            if char in {"'", '"'}:
                quote = char
                continue
            if char in "[{(":
                depth += 1
                continue
            if char in "]})":
                if depth == 0:
                    return index
                depth -= 1
                continue
            if char == "," and depth == 0:
                return index
        return len(text)

    def _resolve_value(self, raw_value: str, context: _NuxtContext) -> Any:
        value = raw_value.strip()
        if not value:
            return None
        if value in context.aliases:
            return context.aliases[value]
        return self._decode_js_value(value)

    def _decode_js_value(self, value: str) -> Any:
        text = value.strip()
        if not text:
            return ""
        if text in {"null", "undefined"}:
            return ""
        if text == "true":
            return True
        if text == "false":
            return False
        if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
            try:
                if text.startswith("'"):
                    text = '"' + text[1:-1].replace('"', '\\"') + '"'
                return html.unescape(json.loads(text))
            except json.JSONDecodeError:
                return html.unescape(text.strip("'\""))
        if re.fullmatch(r"-?\d+(?:\.\d+)?", text):
            return float(text) if "." in text else int(text)
        return text

    def _split_top_level(self, text: str) -> list[str]:
        parts: list[str] = []
        start = 0
        quote = ""
        escaped = False
        stack: list[str] = []
        pairs = {"[": "]", "{": "}", "(": ")"}
        for index, char in enumerate(text):
            if quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = ""
                continue
            if char in {"'", '"'}:
                quote = char
                continue
            if char in pairs:
                stack.append(pairs[char])
                continue
            if stack and char == stack[-1]:
                stack.pop()
                continue
            if char == "," and not stack:
                parts.append(text[start:index].strip())
                start = index + 1
        tail = text[start:].strip()
        if tail:
            parts.append(tail)
        return parts

    def _find_matching(self, text: str, start: int, opener: str, closer: str) -> int:
        if start < 0 or start >= len(text) or text[start] != opener:
            return -1
        quote = ""
        escaped = False
        depth = 0
        for index in range(start, len(text)):
            char = text[index]
            if quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = ""
                continue
            if char in {"'", '"'}:
                quote = char
                continue
            if char == opener:
                depth += 1
            elif char == closer:
                depth -= 1
                if depth == 0:
                    return index
        return -1

    def _dedupe(self, items: list[RSSItem]) -> list[RSSItem]:
        seen: set[str] = set()
        result: list[RSSItem] = []
        for item in items:
            key = item.link or item.title
            if not key or key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result

    def _source_name(self, prefix: str, resource: str) -> str:
        resource = compact_text(resource)
        return f"{prefix} / {resource}" if resource else prefix

    def _is_biomed_relevant(self, text: str) -> bool:
        normalized = text.lower()
        keywords = [
            "adc",
            "ai制药",
            "asco",
            "car-t",
            "cdmo",
            "cro",
            "fda",
            "her2",
            "ii期",
            "iii期",
            "临床",
            "免疫",
            "制药",
            "医",
            "医院",
            "医药",
            "医保",
            "医疗",
            "基因",
            "抗体",
            "新药",
            "治疗",
            "疫苗",
            "癌",
            "研发",
            "细胞",
            "肿瘤",
            "药",
            "获批",
            "适应症",
        ]
        return any(keyword in normalized for keyword in keywords)
