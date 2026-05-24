from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


class LLMError(RuntimeError):
    pass


class DeepSeekClient:
    """Small stdlib client for DeepSeek's OpenAI-compatible chat completions API."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: int = 90,
    ) -> None:
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        self.base_url = (base_url or os.environ.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com").rstrip("/")
        self.model = model or os.environ.get("DEEPSEEK_MODEL") or "deepseek-v4-flash"
        self.timeout = timeout

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def chat_text(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4000,
    ) -> str:
        if not self.api_key:
            raise LLMError("DEEPSEEK_API_KEY is not configured")
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        response = self._post("/chat/completions", payload)
        try:
            return str(response["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("DeepSeek returned an unexpected response shape") from exc

    def chat_json(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 5000,
    ) -> dict[str, Any]:
        content = self.chat_text(messages=messages, temperature=temperature, max_tokens=max_tokens)
        return self._parse_json(content)

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise LLMError(f"DeepSeek API error {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise LLMError(f"DeepSeek API connection failed: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise LLMError("DeepSeek returned invalid JSON") from exc

    def _parse_json(self, content: str) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError(f"Model did not return valid JSON: {content[:500]}") from exc
        if not isinstance(parsed, dict):
            raise LLMError("Model JSON output must be an object")
        return parsed
