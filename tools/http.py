from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


DEFAULT_USER_AGENT = "biotech-agent/0.1 (+local intelligence workflow)"


class HTTPRequestError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, detail: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.detail = detail


@dataclass
class HTTPResponse:
    body: bytes
    status: int
    url: str
    headers: Any

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")

    def json(self) -> dict[str, Any]:
        parsed = json.loads(self.text())
        if not isinstance(parsed, dict):
            raise HTTPRequestError("HTTP response JSON must be an object", status=self.status)
        return parsed


class HTTPClient:
    def __init__(
        self,
        timeout: int = 20,
        retries: int = 2,
        backoff: float = 0.6,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self.user_agent = user_agent

    def get(self, url: str, headers: dict[str, str] | None = None, timeout: int | None = None) -> HTTPResponse:
        return self.request("GET", url, headers=headers, timeout=timeout)

    def post_json(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> HTTPResponse:
        request_headers = {"Content-Type": "application/json"}
        request_headers.update(headers or {})
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return self.request("POST", url, data=data, headers=request_headers, timeout=timeout)

    def request(
        self,
        method: str,
        url: str,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> HTTPResponse:
        request_headers = {"User-Agent": self.user_agent}
        request_headers.update(headers or {})
        attempts = max(1, self.retries + 1)
        last_error: Exception | None = None
        for attempt in range(attempts):
            request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
            try:
                with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                    return HTTPResponse(
                        body=response.read(),
                        status=int(response.status),
                        url=response.geturl(),
                        headers=response.headers,
                    )
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                last_error = HTTPRequestError(f"HTTP {exc.code}: {detail[:500]}", status=exc.code, detail=detail)
                if exc.code not in {408, 425, 429, 500, 502, 503, 504} or attempt == attempts - 1:
                    raise last_error from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                last_error = HTTPRequestError(f"Network error: {getattr(exc, 'reason', exc)}")
                if attempt == attempts - 1:
                    raise last_error from exc
            time.sleep(self._sleep_seconds(attempt))
        raise HTTPRequestError(str(last_error or "HTTP request failed"))

    def _sleep_seconds(self, attempt: int) -> float:
        return self.backoff * (2**attempt)
