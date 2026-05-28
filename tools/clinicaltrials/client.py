from __future__ import annotations

import json
import urllib.parse
from dataclasses import dataclass
from typing import Any

from tools.http import HTTPClient
from tools.rss.reader import RSSItem


@dataclass
class ClinicalTrialsClient:
    timeout: int = 12

    def __post_init__(self) -> None:
        self.http = HTTPClient(timeout=self.timeout, retries=2, backoff=0.5)

    def search_recent(self, query: str, max_items: int = 8) -> list[RSSItem]:
        params = {
            "query.term": query,
            "pageSize": str(max_items),
            "format": "json",
        }
        url = "https://clinicaltrials.gov/api/v2/studies?" + urllib.parse.urlencode(params)
        payload = json.loads(self.http.get(url, timeout=self.timeout).text())
        return [self._to_item(study) for study in payload.get("studies", []) if self._title(study)]

    def _to_item(self, study: dict[str, Any]) -> RSSItem:
        protocol = study.get("protocolSection", {})
        identification = protocol.get("identificationModule", {})
        status = protocol.get("statusModule", {})
        design = protocol.get("designModule", {})
        conditions = protocol.get("conditionsModule", {})
        nct_id = str(identification.get("nctId") or "")
        phases = ", ".join(design.get("phases") or [])
        condition_text = ", ".join(conditions.get("conditions") or [])
        summary = f"{phases}. {condition_text}".strip(". ")
        return RSSItem(
            title=self._title(study),
            link=f"https://clinicaltrials.gov/study/{nct_id}" if nct_id else "https://clinicaltrials.gov/",
            summary=summary,
            source="ClinicalTrials.gov",
            published=str(status.get("lastUpdatePostDateStruct", {}).get("date") or ""),
        )

    def _title(self, study: dict[str, Any]) -> str:
        identification = study.get("protocolSection", {}).get("identificationModule", {})
        return str(identification.get("briefTitle") or identification.get("officialTitle") or "")
