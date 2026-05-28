from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", "database"}
EXCLUDED_FILES = {".env", ".env.local", ".env.production", ".env.example"}
TEXT_SUFFIXES = {
    "",
    ".css",
    ".dockerignore",
    ".example",
    ".gitignore",
    ".html",
    ".js",
    ".json",
    ".md",
    ".py",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
SECRET_PATTERNS = [
    re.compile(r"\bLTAI[A-Za-z0-9]{12,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"(?i)(api[_-]?key|access[_-]?key[_-]?secret|secret)[ \t]*=[ \t]*['\"]?[^'\"\r\n \t#]{12,}"),
]
PLACEHOLDER_WORDS = {
    "your",
    "example",
    "placeholder",
    "你的",
    "oss_access_key_id",
    "oss_access_key_secret",
    "access_point_alias",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan deployable files for likely hard-coded secrets.")
    parser.add_argument("--root", default=str(ROOT), help="Project root to scan.")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    findings: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file() or should_skip(path, root):
            continue
        if path.suffix not in TEXT_SUFFIXES and path.name not in {".gitignore", ".dockerignore", "Dockerfile"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in SECRET_PATTERNS:
            for match in pattern.finditer(text):
                token = match.group(0)
                if is_placeholder(token) or " or " in token:
                    continue
                rel = path.relative_to(root)
                line = text.count("\n", 0, match.start()) + 1
                findings.append(f"{rel}:{line}: possible secret: {redact(token)}")
    if findings:
        print("Security check failed. Remove or move these secrets to .env / server secret manager:", file=sys.stderr)
        for finding in findings:
            print(f"- {finding}", file=sys.stderr)
        return 1
    print("Security check passed: no obvious hard-coded secrets found.")
    return 0


def should_skip(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    if path.name in EXCLUDED_FILES:
        return True
    return any(part in EXCLUDED_DIRS for part in rel.parts)


def is_placeholder(value: str) -> bool:
    lowered = value.lower()
    if any(word in lowered for word in PLACEHOLDER_WORDS):
        return True
    if "=" in lowered:
        assigned_value = lowered.split("=", 1)[1].strip().strip("\"'")
        if assigned_value in {
            "api_key",
            "access_key_id",
            "access_key_secret",
            "secret",
            "self.api_key",
            "self.access_key_secret",
            "self.access_key_secret,",
        }:
            return True
    return False


def redact(value: str) -> str:
    if len(value) <= 10:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


if __name__ == "__main__":
    raise SystemExit(main())
