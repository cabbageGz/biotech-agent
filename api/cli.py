from __future__ import annotations

import argparse
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Sequence

from api.web_server import serve
from workflows.xiaohongshu_flow import XiaohongshuDailyFlow
from workflows.storage import RunStorage


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="biotech-agent", description="Biotech intelligence agent console.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run-once", help="Generate one Xiaohongshu biotech hotspot post.")
    run_parser.add_argument("--topic", default="", help="Optional topic hint, such as ADC or AI 制药.")

    schedule_parser = subparsers.add_parser("schedule", help="Run the daily workflow in a long-lived loop.")
    schedule_parser.add_argument("--time", default="08:30", help="Daily run time in HH:MM. Defaults to 08:30.")
    schedule_parser.add_argument("--topic", default="", help="Optional topic hint.")

    serve_parser = subparsers.add_parser("serve", help="Start the local console.")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", default=8787, type=int)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    load_env(Path(".env"))
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "run-once":
        payload = XiaohongshuDailyFlow(storage=RunStorage(Path("database/runs"))).run(topic_hint=args.topic)
        print(f"Generated run: database/runs/{payload['run_id']}")
        print(f"Post: database/runs/{payload['run_id']}/xiaohongshu_post.md")
        return 0
    if args.command == "schedule":
        run_schedule(run_time=args.time, topic_hint=args.topic)
        return 0
    if args.command == "serve":
        serve(host=args.host, port=args.port)
        return 0
    parser.error(f"Unknown command: {args.command}")
    return 2


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def run_schedule(run_time: str, topic_hint: str = "") -> None:
    last_run_date = ""
    while True:
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        current_date = now.strftime("%Y-%m-%d")
        if current_time >= run_time and last_run_date != current_date:
            payload = XiaohongshuDailyFlow(storage=RunStorage(Path("database/runs"))).run(topic_hint=topic_hint)
            last_run_date = current_date
            print(f"[{now.isoformat()}] Generated run {payload['run_id']}", flush=True)
        time.sleep(30)


if __name__ == "__main__":
    raise SystemExit(main())
