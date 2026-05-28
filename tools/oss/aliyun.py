from __future__ import annotations

import base64
import hashlib
import hmac
import os
import urllib.parse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from time import time
from typing import Any

from tools.http import HTTPClient, HTTPRequestError


class OSSConfigError(RuntimeError):
    pass


@dataclass
class OSSObject:
    bucket: str
    key: str
    url: str
    etag: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AliyunOSSClient:
    """Small stdlib Aliyun OSS client for PUT/DELETE object uploads."""

    def __init__(
        self,
        access_key_id: str | None = None,
        access_key_secret: str | None = None,
        endpoint: str | None = None,
        bucket: str | None = None,
        public_base_url: str | None = None,
        canonical_bucket: str | None = None,
        timeout: int = 120,
    ) -> None:
        self.access_key_id = access_key_id or os.environ.get("ALIYUN_OSS_ACCESS_KEY_ID", "")
        self.access_key_secret = access_key_secret or os.environ.get("ALIYUN_OSS_ACCESS_KEY_SECRET", "")
        self.endpoint = (endpoint or os.environ.get("ALIYUN_OSS_ENDPOINT", "")).strip().rstrip("/")
        self.bucket = bucket or os.environ.get("ALIYUN_OSS_BUCKET") or "gzz-agent"
        self.public_base_url = (public_base_url or os.environ.get("ALIYUN_OSS_PUBLIC_BASE_URL", "")).strip().rstrip("/")
        self.canonical_bucket = (
            canonical_bucket
            or os.environ.get("ALIYUN_OSS_CANONICAL_BUCKET")
            or os.environ.get("ALIYUN_OSS_ACCESS_POINT_ALIAS")
            or self.bucket
        )
        self.timeout = timeout
        self.http = HTTPClient(timeout=timeout, retries=2, backoff=0.6)

    @property
    def available(self) -> bool:
        return bool(self.access_key_id and self.access_key_secret and self.endpoint and self.bucket)

    def upload_bytes(self, data: bytes, key: str, content_type: str = "application/octet-stream") -> OSSObject:
        if not self.available:
            raise OSSConfigError("ALIYUN_OSS_ACCESS_KEY_ID/SECRET/ENDPOINT/BUCKET is not configured")
        clean_key = key.lstrip("/")
        url = self._object_url(clean_key)
        content_md5 = base64.b64encode(hashlib.md5(data).digest()).decode("ascii")
        headers = self._headers(
            method="PUT",
            key=clean_key,
            content_type=content_type,
            content_md5=content_md5,
        )
        try:
            response = self.http.request("PUT", url, data=data, headers=headers, timeout=self.timeout)
            etag = response.headers.get("ETag", "").strip('"')
        except HTTPRequestError as exc:
            raise RuntimeError(f"Aliyun OSS upload error {exc.status or 'network'}: {exc.detail or exc}") from exc
        return OSSObject(bucket=self.bucket, key=clean_key, url=self.public_url(clean_key), etag=etag)

    def delete_object(self, key: str) -> None:
        if not self.available:
            return
        clean_key = key.lstrip("/")
        try:
            self.http.request(
                "DELETE",
                self._object_url(clean_key),
                headers=self._headers(method="DELETE", key=clean_key),
                timeout=self.timeout,
            )
        except HTTPRequestError as exc:
            if exc.status == 404:
                return
            if exc.status == 403 and self._is_access_point_endpoint():
                fallback = self._bucket_endpoint_client()
                if fallback is not None:
                    fallback.delete_object(clean_key)
                    return
            raise RuntimeError(f"Aliyun OSS delete error {exc.status or 'network'}: {exc.detail or exc}") from exc

    def public_url(self, key: str) -> str:
        clean_key = key.lstrip("/")
        if self.public_base_url:
            return f"{self.public_base_url}/{urllib.parse.quote(clean_key)}"
        endpoint = self.endpoint.removeprefix("https://").removeprefix("http://")
        return f"https://{self.bucket}.{endpoint}/{urllib.parse.quote(clean_key)}"

    def signed_url(self, key: str, expires_in: int = 3600) -> str:
        if not self.available:
            raise OSSConfigError("ALIYUN_OSS_ACCESS_KEY_ID/SECRET/ENDPOINT/BUCKET is not configured")
        clean_key = key.lstrip("/")
        expires = str(int(time()) + max(60, expires_in))
        canonical_resource = f"/{self.canonical_bucket}/{clean_key}"
        string_to_sign = "\n".join(["GET", "", "", expires, canonical_resource])
        signature = base64.b64encode(
            hmac.new(self.access_key_secret.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha1).digest()
        ).decode("ascii")
        query = urllib.parse.urlencode(
            {
                "OSSAccessKeyId": self.access_key_id,
                "Expires": expires,
                "Signature": signature,
            }
        )
        return f"{self._object_url(clean_key)}?{query}"

    def key_for_path(self, local_path: Path, prefix: str = "biotech-agent") -> str:
        run_id = local_path.parent.name
        return f"{prefix.strip('/')}/{run_id}/{local_path.name}"

    def _object_url(self, key: str) -> str:
        endpoint = self.endpoint
        if not endpoint.startswith(("http://", "https://")):
            endpoint = f"https://{endpoint}"
        host = endpoint.removeprefix("https://").removeprefix("http://")
        if self._is_access_point_host(host):
            return f"https://{host}/{urllib.parse.quote(key)}"
        return f"https://{self.bucket}.{host}/{urllib.parse.quote(key)}"

    def _is_access_point_endpoint(self) -> bool:
        host = self.endpoint.removeprefix("https://").removeprefix("http://")
        return self._is_access_point_host(host)

    def _is_access_point_host(self, host: str) -> bool:
        return ".oss-accesspoint." in host or "-ossalias." in host

    def _bucket_endpoint_client(self) -> AliyunOSSClient | None:
        host = self.endpoint.removeprefix("https://").removeprefix("http://")
        marker = ".oss-accesspoint.aliyuncs.com"
        if not host.endswith(marker):
            return None
        prefix = host.removesuffix(marker)
        region = prefix.rsplit(".", 1)[-1]
        if not region:
            return None
        return AliyunOSSClient(
            access_key_id=self.access_key_id,
            access_key_secret=self.access_key_secret,
            endpoint=f"{region}.aliyuncs.com",
            bucket=self.bucket,
            public_base_url=self.public_base_url,
            canonical_bucket=self.bucket,
            timeout=self.timeout,
        )

    def _headers(
        self,
        method: str,
        key: str,
        content_type: str = "",
        content_md5: str = "",
    ) -> dict[str, str]:
        request_date = format_datetime(datetime.now(timezone.utc), usegmt=True)
        canonical_resource = f"/{self.canonical_bucket}/{key}"
        string_to_sign = "\n".join([method, content_md5, content_type, request_date, canonical_resource])
        signature = base64.b64encode(
            hmac.new(self.access_key_secret.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha1).digest()
        ).decode("ascii")
        headers = {
            "Authorization": f"OSS {self.access_key_id}:{signature}",
            "Date": request_date,
        }
        if content_type:
            headers["Content-Type"] = content_type
        if content_md5:
            headers["Content-MD5"] = content_md5
        return headers
