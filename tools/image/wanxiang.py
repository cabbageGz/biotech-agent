from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


class WanxiangError(RuntimeError):
    pass


@dataclass
class CoverImage:
    prompt: str
    model: str
    size: str
    image_url: str = ""
    local_path: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WanxiangClient:
    """DashScope / Alibaba Bailian Wanxiang image generation client."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        size: str | None = None,
        timeout: int = 120,
    ) -> None:
        self.api_key = api_key or os.environ.get("DASHSCOPE_API_KEY", "")
        self.base_url = (
            base_url
            or os.environ.get("WANXIANG_BASE_URL")
            or "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
        )
        self.model = model or os.environ.get("WANXIANG_MODEL") or "wan2.7-image"
        self.size = size or os.environ.get("WANXIANG_IMAGE_SIZE") or "1024*1024"
        self.timeout = timeout

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def generate(self, prompt: str, output_path: Path) -> CoverImage:
        cover = CoverImage(prompt=prompt, model=self.model, size=self.size)
        if not self.api_key:
            cover.error = "DASHSCOPE_API_KEY is not configured"
            return cover

        payload = {
            "model": self.model,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": [{"text": prompt}],
                    }
                ]
            },
            "parameters": {
                "size": self.size,
                "n": 1,
            },
        }
        try:
            response = self._post(payload)
            image_url = self._extract_image_url(response)
            cover.image_url = image_url
            if image_url:
                self._download(image_url, output_path)
                cover.local_path = str(output_path)
        except Exception as exc:
            cover.error = str(exc)
        return cover

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            self.base_url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
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
            raise WanxiangError(f"Wanxiang API error {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise WanxiangError(f"Wanxiang API connection failed: {exc.reason}") from exc

    def _extract_image_url(self, response: dict[str, Any]) -> str:
        output = response.get("output") or {}
        choices = output.get("choices") or []
        for choice in choices:
            content = choice.get("message", {}).get("content") or []
            for item in content:
                if item.get("image"):
                    return str(item["image"])
        results = output.get("results") or []
        for item in results:
            if item.get("url"):
                return str(item["url"])
        raise WanxiangError(f"No image URL in Wanxiang response: {json.dumps(response, ensure_ascii=False)[:500]}")

    def _download(self, image_url: str, output_path: Path) -> None:
        request = urllib.request.Request(image_url, headers={"User-Agent": "biotech-agent/0.1"})
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            output_path.write_bytes(response.read())
