from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class ReviewIssue:
    category: str
    severity: str
    finding: str
    evidence: str
    suggestion: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReviewReport:
    source_exists: bool
    source_confidence: int
    exaggeration_risk: int
    efficacy_promise_risk: int
    investment_advice_risk: int
    overall_confidence: int
    publish_status: str
    summary: str
    issues: list[ReviewIssue]
    revision_suggestions: list[str]
    evidence_used: list[dict[str, str]]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["issues"] = [item.to_dict() for item in self.issues]
        return payload
