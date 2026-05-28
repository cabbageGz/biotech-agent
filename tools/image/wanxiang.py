from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from tools.http import HTTPClient, HTTPRequestError
from tools.oss import AliyunOSSClient


class WanxiangError(RuntimeError):
    pass


@dataclass
class CoverImage:
    prompt: str
    model: str
    size: str
    image_url: str = ""
    local_path: str = ""
    oss_key: str = ""
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
        oss_client: AliyunOSSClient | None = None,
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
        self.oss_client = oss_client or AliyunOSSClient()
        self.http = HTTPClient(timeout=timeout, retries=2, backoff=1.0)

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def generate(self, prompt: str, output_path: Path, size: str | None = None) -> CoverImage:
        image_size = size or self.size
        cover = CoverImage(prompt=prompt, model=self.model, size=image_size)
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
                "size": image_size,
                "n": 1,
            },
        }
        try:
            response = self._post(payload)
            image_url = self._extract_image_url(response)
            cover.image_url = image_url
            if image_url:
                data = self._download_bytes(image_url)
                if self.oss_client.available:
                    uploaded = self.oss_client.upload_bytes(
                        data,
                        key=self.oss_client.key_for_path(output_path),
                        content_type=self._content_type(output_path),
                    )
                    cover.image_url = uploaded.url
                    cover.oss_key = uploaded.key
                else:
                    self._write_local(data, output_path)
                    cover.local_path = str(output_path)
        except Exception as exc:
            cover.error = str(exc)
        return cover

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self.http.request(
                "POST",
                self.base_url,
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
            return json.loads(response.text())
        except HTTPRequestError as exc:
            if exc.status:
                raise WanxiangError(f"Wanxiang API error {exc.status}: {exc.detail or exc}") from exc
            raise WanxiangError(f"Wanxiang API connection failed: {exc}") from exc

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

    def _download_bytes(self, image_url: str) -> bytes:
        return self.http.get(image_url, timeout=self.timeout).body

    def _write_local(self, data: bytes, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(data)

    def _content_type(self, path: Path) -> str:
        return {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }.get(path.suffix.lower(), "application/octet-stream")
