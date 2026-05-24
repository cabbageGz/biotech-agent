from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from tools.rss.reader import RSSItem


EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


@dataclass
class PubMedClient:
    email: str = ""
    api_key: str = ""
    timeout: int = 12

    def search_recent(self, query: str, max_items: int = 8, days: int = 7) -> list[RSSItem]:
        ids = self._search_ids(query=query, max_items=max_items, days=days)
        if not ids:
            return []
        summaries = self._summaries(ids)
        items: list[RSSItem] = []
        for pmid in ids:
            record = summaries.get(pmid, {})
            title = str(record.get("title") or "").rstrip(".")
            if not title:
                continue
            journal = str(record.get("fulljournalname") or record.get("source") or "PubMed")
            pubdate = str(record.get("pubdate") or "")
            authors = record.get("authors") or []
            author_text = ", ".join(str(author.get("name")) for author in authors[:3] if author.get("name"))
            summary = f"{journal}. {author_text}".strip()
            items.append(
                RSSItem(
                    title=title,
                    link=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    summary=summary,
                    source="PubMed",
                    published=pubdate,
                )
            )
        return items

    def _search_ids(self, query: str, max_items: int, days: int) -> list[str]:
        payload = self._get_json(
            "esearch.fcgi",
            {
                "db": "pubmed",
                "term": query,
                "retmode": "json",
                "retmax": str(max_items),
                "sort": "pub date",
                "datetype": "pdat",
                "reldate": str(days),
            },
        )
        return [str(item) for item in payload.get("esearchresult", {}).get("idlist", [])]

    def _summaries(self, ids: list[str]) -> dict[str, Any]:
        payload = self._get_json(
            "esummary.fcgi",
            {
                "db": "pubmed",
                "id": ",".join(ids),
                "retmode": "json",
            },
        )
        return dict(payload.get("result") or {})

    def _get_json(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        if self.email:
            params["email"] = self.email
        if self.api_key:
            params["api_key"] = self.api_key
        url = f"{EUTILS_BASE}/{endpoint}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(url, headers={"User-Agent": "biotech-agent/0.1"})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))
