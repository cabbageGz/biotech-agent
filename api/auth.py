from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


class AuthStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    generated_hotspots INTEGER NOT NULL DEFAULT 0,
                    generated_images INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
                """
            )
            count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            if count == 0:
                initial_password = os.environ.get("ADMIN_INITIAL_PASSWORD") or "123456"
                conn.execute(
                    """
                    INSERT INTO users (username, password_hash, role, created_at)
                    VALUES (?, ?, 'admin', ?)
                    """,
                    ("admin", self.hash_password(initial_password), self._now()),
                )

    def create_user(self, username: str, password: str, role: str = "user") -> dict[str, Any]:
        clean_username = username.strip()
        if not clean_username or not password:
            raise ValueError("Username and password are required")
        clean_role = "admin" if role == "admin" else "user"
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO users (username, password_hash, role, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (clean_username, self.hash_password(password), clean_role, self._now()),
            )
            user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        return self.get_user_by_id(int(user_id)) or {}

    def list_users(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, username, role, generated_hotspots, generated_images, created_at
                FROM users ORDER BY id ASC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_user(self, user_id: int, current_user_id: int) -> None:
        if user_id == current_user_id:
            raise ValueError("不能删除当前登录用户")
        with self._connect() as conn:
            target = conn.execute(
                "SELECT id, role FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            if not target:
                raise FileNotFoundError("用户不存在")
            if target["role"] == "admin":
                admin_count = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()[0]
                if admin_count <= 1:
                    raise ValueError("不能删除最后一个管理员")
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))

    def authenticate(self, username: str, password: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE username = ?", (username.strip(),)).fetchone()
        if not row or not self.verify_password(password, str(row["password_hash"])):
            return None
        return self._public_user(dict(row))

    def create_session(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(days=14)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (token, user_id, expires_at, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (token, user_id, expires.isoformat(), self._now()),
            )
        return token

    def delete_session(self, token: str) -> None:
        if not token:
            return
        with self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))

    def delete_user_sessions(self, user_id: int, keep_token: str = "") -> None:
        with self._connect() as conn:
            if keep_token:
                conn.execute("DELETE FROM sessions WHERE user_id = ? AND token != ?", (user_id, keep_token))
            else:
                conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))

    def user_for_session(self, token: str) -> dict[str, Any] | None:
        if not token:
            return None
        now = self._now()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT users.* FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.token = ? AND sessions.expires_at > ?
                """,
                (token, now),
            ).fetchone()
        if not row:
            return None
        return self._public_user(dict(row))

    def get_user_by_id(self, user_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return self._public_user(dict(row)) if row else None

    def change_password(self, user_id: int, current_password: str, new_password: str, keep_token: str = "") -> None:
        if len(new_password) < 6:
            raise ValueError("新密码至少需要 6 位")
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if not row:
                raise FileNotFoundError("用户不存在")
            if not self.verify_password(current_password, str(row["password_hash"])):
                raise ValueError("当前密码不正确")
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (self.hash_password(new_password), user_id),
            )
        self.delete_user_sessions(user_id, keep_token=keep_token)

    def reset_password(self, user_id: int, new_password: str) -> None:
        if len(new_password) < 6:
            raise ValueError("新密码至少需要 6 位")
        with self._connect() as conn:
            exists = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
            if not exists:
                raise FileNotFoundError("用户不存在")
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (self.hash_password(new_password), user_id),
            )
        self.delete_user_sessions(user_id)

    def increment_hotspots(self, user_id: int, count: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET generated_hotspots = generated_hotspots + ? WHERE id = ?",
                (count, user_id),
            )

    def increment_images(self, user_id: int, count: int = 1) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET generated_images = generated_images + ? WHERE id = ?",
                (count, user_id),
            )

    def hash_password(self, password: str) -> str:
        salt = os.urandom(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
        return f"pbkdf2_sha256${salt.hex()}${digest.hex()}"

    def verify_password(self, password: str, encoded: str) -> bool:
        try:
            algorithm, salt_hex, digest_hex = encoded.split("$", 2)
        except ValueError:
            return False
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), 200_000)
        return hmac.compare_digest(digest.hex(), digest_hex)

    def _public_user(self, row: dict[str, Any]) -> dict[str, Any]:
        row.pop("password_hash", None)
        return row

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
