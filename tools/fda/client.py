from __future__ import annotations

import json
import urllib.parse
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from tools.http import HTTPClient
from tools.rss.reader import RSSItem


@dataclass
class OpenFDAClient:
    timeout: int = 12

    def __post_init__(self) -> None:
        self.http = HTTPClient(timeout=self.timeout, retries=2, backoff=0.5)

    def recent_drug_approvals(self, max_items: int = 8, days: int = 30) -> list[RSSItem]:
        end = date.today()
        start = end - timedelta(days=days)
        search = f'submissions.submission_status_date:[{start:%Y%m%d}+TO+{end:%Y%m%d}]'
        params = {
            "search": search,
            "limit": str(max_items),
        }
        url = "https://api.fda.gov/drug/drugsfda.json?" + urllib.parse.urlencode(params, safe=":+[]")
        payload = json.loads(self.http.get(url, timeout=self.timeout).text())
        return [self._to_item(record) for record in payload.get("results", [])]

    def _to_item(self, record: dict[str, Any]) -> RSSItem:
        products = record.get("products") or []
        submissions = record.get("submissions") or []
        product = products[0] if products else {}
        submission = submissions[0] if submissions else {}
        brand = str(product.get("brand_name") or "FDA drug record")
        sponsor = str(record.get("sponsor_name") or "")
        app_no = str(record.get("application_number") or "")
        status_date = str(submission.get("submission_status_date") or "")
        title = f"{brand} {app_no}".strip()
        summary = f"Sponsor: {sponsor}. Submission: {submission.get('submission_type', '')} {submission.get('submission_status', '')}"
        return RSSItem(
            title=title,
            link=f"https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?event=overview.process&ApplNo={app_no}",
            summary=summary,
            source="FDA / openFDA",
            published=status_date,
        )
