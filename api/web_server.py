from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from workflows.storage import RunStorage
from workflows.xiaohongshu_flow import XiaohongshuDailyFlow


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT / "frontend"


class ConsoleApp:
    def __init__(self) -> None:
        self.storage = RunStorage(ROOT / "database" / "runs")
        self.flow = XiaohongshuDailyFlow(storage=self.storage)

    def status(self) -> dict[str, object]:
        return {
            "ok": True,
            "runs": len(self.storage.list_runs()),
            "sources": str(ROOT / "tools" / "rss" / "sources.json"),
        }

    def run_daily(self, body: dict[str, object]) -> dict[str, object]:
        topic = str(body.get("topic") or "")
        max_items = int(body.get("max_items") or 24)
        max_hotspots = int(body.get("max_hotspots") or 6)
        return self.flow.run(topic_hint=topic, max_items=max_items, max_hotspots=max_hotspots)

    def clear_runs(self) -> dict[str, object]:
        return {"removed": self.storage.clear_runs()}

    def generate_cover(self, run_id: str) -> dict[str, object]:
        return self.flow.generate_cover_for_run(run_id)


def serve(host: str = "127.0.0.1", port: int = 8787) -> None:
    app = ConsoleApp()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            try:
                self._handle_get()
            except Exception as exc:
                self._json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

        def do_POST(self) -> None:
            try:
                self._handle_post()
            except Exception as exc:
                self._json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

        def _handle_get(self) -> None:
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            if path == "/api/status":
                self._json(app.status())
                return
            if path == "/api/runs":
                self._json({"runs": app.storage.list_runs()})
                return
            if path.startswith("/api/runs/"):
                rest = path.removeprefix("/api/runs/").strip("/")
                if "/assets/" in rest:
                    run_id, filename = rest.split("/assets/", 1)
                    self._run_asset(run_id, filename)
                    return
                run_id = rest
                self._json(app.storage.read_run(run_id))
                return
            self._static(path)

        def _handle_post(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/run":
                self._json(app.run_daily(self._read_json()))
                return
            if parsed.path == "/api/runs/clear":
                self._json(app.clear_runs())
                return
            if parsed.path.startswith("/api/runs/") and parsed.path.endswith("/cover"):
                run_id = unquote(parsed.path.removeprefix("/api/runs/").removesuffix("/cover").strip("/"))
                self._json(app.generate_cover(run_id))
                return
            self._json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

        def _static(self, path: str) -> None:
            if path == "/":
                path = "/index.html"
            target = (FRONTEND_DIR / path.lstrip("/")).resolve()
            if not str(target).startswith(str(FRONTEND_DIR.resolve())) or not target.exists():
                self._json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
                return
            content_type = {
                ".html": "text/html; charset=utf-8",
                ".css": "text/css; charset=utf-8",
                ".js": "application/javascript; charset=utf-8",
            }.get(target.suffix, "application/octet-stream")
            data = target.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _run_asset(self, run_id: str, filename: str) -> None:
            target = (ROOT / "database" / "runs" / run_id / filename).resolve()
            runs_root = (ROOT / "database" / "runs").resolve()
            if not str(target).startswith(str(runs_root)) or not target.exists():
                self._json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
                return
            content_type = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".webp": "image/webp",
            }.get(target.suffix.lower(), "application/octet-stream")
            data = target.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _read_json(self) -> dict[str, object]:
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length <= 0:
                return {}
            return json.loads(self.rfile.read(length).decode("utf-8"))

        def _json(self, payload: dict[str, object], status: HTTPStatus = HTTPStatus.OK) -> None:
            data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Biotech Agent console: http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
