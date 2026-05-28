from __future__ import annotations

import urllib.error
import unittest
from unittest.mock import patch

from tools.http import HTTPClient, HTTPRequestError
from tools.oss import AliyunOSSClient


class _FakeResponse:
    status = 200
    headers = {"ETag": '"ok"'}

    def __init__(self, body: bytes = b'{"ok": true}') -> None:
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return self._body

    def geturl(self) -> str:
        return "https://example.com/final"

    def close(self) -> None:
        return None


class HTTPClientTests(unittest.TestCase):
    def test_retries_transient_network_error(self) -> None:
        calls = []

        def fake_urlopen(_request, timeout):
            calls.append(timeout)
            if len(calls) == 1:
                raise urllib.error.URLError("temporary")
            return _FakeResponse()

        with patch("tools.http.time.sleep"), patch("urllib.request.urlopen", side_effect=fake_urlopen):
            response = HTTPClient(timeout=3, retries=1, backoff=0).get("https://example.com")

        self.assertEqual(response.status, 200)
        self.assertEqual(len(calls), 2)

    def test_does_not_retry_permanent_http_error(self) -> None:
        calls = []

        def fake_urlopen(_request, timeout):
            calls.append(timeout)
            raise urllib.error.HTTPError(
                url="https://example.com",
                code=403,
                msg="Forbidden",
                hdrs={},
                fp=_FakeResponse(b"no"),
            )

        with patch("tools.http.time.sleep"), patch("urllib.request.urlopen", side_effect=fake_urlopen):
            with self.assertRaises(HTTPRequestError) as context:
                HTTPClient(timeout=3, retries=2, backoff=0).get("https://example.com")

        self.assertEqual(context.exception.status, 403)
        self.assertEqual(len(calls), 1)

    def test_oss_access_point_can_fallback_to_bucket_endpoint(self) -> None:
        client = AliyunOSSClient(
            access_key_id="ak",
            access_key_secret="secret",
            endpoint="gzz-agent-1326456261273942.oss-cn-beijing.oss-accesspoint.aliyuncs.com",
            bucket="gzz-agent",
            canonical_bucket="gzz-agent-alias",
        )

        fallback = client._bucket_endpoint_client()

        self.assertIsNotNone(fallback)
        self.assertEqual(fallback.endpoint, "oss-cn-beijing.aliyuncs.com")
        self.assertEqual(fallback.canonical_bucket, "gzz-agent")


if __name__ == "__main__":
    unittest.main()
