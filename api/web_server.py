from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from http.cookies import SimpleCookie
from urllib.parse import unquote, urlparse

from api.auth import AuthStore
from workflows.storage import RunStorage
from workflows.xiaohongshu_flow import XiaohongshuDailyFlow


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT / "frontend"


class ConsoleApp:
    def __init__(self) -> None:
        self.storage = RunStorage(ROOT / "database" / "runs")
        self.flow = XiaohongshuDailyFlow(storage=self.storage)
        self.auth = AuthStore(ROOT / "database" / "app.db")

    def status(self, user: dict[str, object]) -> dict[str, object]:
        return {
            "ok": True,
            "runs": len(self.storage.list_runs(user_id=int(user["id"]))),
            "sources": str(ROOT / "tools" / "rss" / "sources.json"),
        }

    def run_daily(self, body: dict[str, object], user: dict[str, object]) -> dict[str, object]:
        topic = str(body.get("topic") or "")
        max_items = int(body.get("max_items") or 24)
        max_hotspots = int(body.get("max_hotspots") or 6)
        reference_url = str(body.get("reference_url") or "")
        content_words = int(body.get("content_words") or 700)
        content_instruction = str(body.get("content_instruction") or "")
        format_reference = str(body.get("format_reference") or "")
        payload = self.flow.run(
            topic_hint=topic,
            max_items=max_items,
            max_hotspots=max_hotspots,
            reference_url=reference_url,
            content_words=content_words,
            content_instruction=content_instruction,
            format_reference=format_reference,
            user_id=int(user["id"]),
            username=str(user["username"]),
        )
        self.auth.increment_hotspots(int(user["id"]), len(payload.get("item_posts", [])))
        return payload

    def clear_runs(self, user: dict[str, object]) -> dict[str, object]:
        return {"removed": self.storage.clear_runs(user_id=int(user["id"]))}

    def generate_cover(self, run_id: str, body: dict[str, object], user: dict[str, object]) -> dict[str, object]:
        run = self.storage.read_run(run_id)
        if run.get("user_id") != int(user["id"]):
            raise PermissionError("Forbidden")
        index = body.get("index")
        image_size = str(body.get("image_size") or "")
        image_instruction = str(body.get("image_instruction") or "")
        payload = self.flow.generate_cover_for_run(
            run_id,
            index=int(index) if index is not None else None,
            image_size=image_size,
            image_instruction=image_instruction,
        )
        if index is not None:
            cover = payload.get("item_covers", [])[int(index)]
            if cover.get("asset") and not cover.get("error"):
                self.auth.increment_images(int(user["id"]))
        return payload


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

        def do_DELETE(self) -> None:
            try:
                self._handle_delete()
            except FileNotFoundError as exc:
                self._json({"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
            except ValueError as exc:
                self._json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                self._json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

        def _handle_get(self) -> None:
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            if path == "/login.html" or path == "/login":
                self._static("/login.html")
                return
            if path in {"/app.css", "/login.js"}:
                self._static(path)
                return
            if path == "/admin.html" or path == "/admin":
                user = self._require_user(redirect=True)
                if not user:
                    return
                if user.get("role") != "admin":
                    self._json({"error": "Forbidden"}, status=HTTPStatus.FORBIDDEN)
                    return
                self._static("/admin.html")
                return
            if path == "/api/me":
                user = self._require_user()
                if not user:
                    return
                self._json({"user": user})
                return
            if path == "/api/admin/users":
                user = self._require_admin()
                if not user:
                    return
                self._json({"users": app.auth.list_users()})
                return
            user = self._require_user(redirect=not path.startswith("/api/"))
            if not user:
                return
            if path == "/api/status":
                self._json(app.status(user))
                return
            if path == "/api/runs":
                self._json({"runs": app.storage.list_runs(user_id=int(user["id"]))})
                return
            if path.startswith("/api/runs/"):
                rest = path.removeprefix("/api/runs/").strip("/")
                if "/assets/" in rest:
                    run_id, filename = rest.split("/assets/", 1)
                    self._run_asset(run_id, filename, user)
                    return
                run_id = rest
                run = app.storage.read_run(run_id)
                if run.get("user_id") != int(user["id"]):
                    self._json({"error": "Forbidden"}, status=HTTPStatus.FORBIDDEN)
                    return
                self._json(run)
                return
            self._static(path)

        def _handle_post(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/login":
                body = self._read_json()
                user = app.auth.authenticate(str(body.get("username") or ""), str(body.get("password") or ""))
                if not user:
                    self._json({"error": "用户名或密码错误"}, status=HTTPStatus.UNAUTHORIZED)
                    return
                token = app.auth.create_session(int(user["id"]))
                self._json({"user": user}, cookie=f"session={token}; HttpOnly; Path=/; SameSite=Lax; Max-Age=1209600")
                return
            if parsed.path == "/api/logout":
                app.auth.delete_session(self._session_token())
                self._json({"ok": True}, cookie="session=; HttpOnly; Path=/; SameSite=Lax; Max-Age=0")
                return
            if parsed.path == "/api/admin/users":
                user = self._require_admin()
                if not user:
                    return
                body = self._read_json()
                self._json({"user": app.auth.create_user(str(body.get("username") or ""), str(body.get("password") or ""), str(body.get("role") or "user"))})
                return
            user = self._require_user()
            if not user:
                return
            if parsed.path == "/api/run":
                self._json(app.run_daily(self._read_json(), user))
                return
            if parsed.path == "/api/runs/clear":
                self._json(app.clear_runs(user))
                return
            if parsed.path.startswith("/api/runs/") and parsed.path.endswith("/cover"):
                run_id = unquote(parsed.path.removeprefix("/api/runs/").removesuffix("/cover").strip("/"))
                self._json(app.generate_cover(run_id, self._read_json(), user))
                return
            self._json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

        def _handle_delete(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/admin/users/"):
                user = self._require_admin()
                if not user:
                    return
                user_id = int(unquote(parsed.path.removeprefix("/api/admin/users/").strip("/")))
                app.auth.delete_user(user_id, current_user_id=int(user["id"]))
                self._json({"ok": True})
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
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _run_asset(self, run_id: str, filename: str, user: dict[str, object]) -> None:
            run = app.storage.read_run(run_id)
            if run.get("user_id") != int(user["id"]):
                self._json({"error": "Forbidden"}, status=HTTPStatus.FORBIDDEN)
                return
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

        def _json(
            self,
            payload: dict[str, object],
            status: HTTPStatus = HTTPStatus.OK,
            cookie: str = "",
        ) -> None:
            data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            if cookie:
                self.send_header("Set-Cookie", cookie)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _session_token(self) -> str:
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
            return cookie.get("session").value if cookie.get("session") else ""

        def _require_user(self, redirect: bool = False) -> dict[str, object] | None:
            user = app.auth.user_for_session(self._session_token())
            if user:
                return user
            if redirect:
                self.send_response(HTTPStatus.FOUND)
                self.send_header("Location", "/login.html")
                self.end_headers()
            else:
                self._json({"error": "Unauthorized"}, status=HTTPStatus.UNAUTHORIZED)
            return None

        def _require_admin(self) -> dict[str, object] | None:
            user = self._require_user()
            if not user:
                return None
            if user.get("role") != "admin":
                self._json({"error": "Forbidden"}, status=HTTPStatus.FORBIDDEN)
                return None
            return user

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
