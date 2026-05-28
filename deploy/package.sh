#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python3 scripts/security_check.py

mkdir -p deploy
STAMP="$(date +%Y%m%d-%H%M%S)"
ARCHIVE="deploy/biotech-agent-${STAMP}.tar.gz"

tar \
  --exclude=".git" \
  --exclude=".env" \
  --exclude=".env.*" \
  --exclude="database" \
  --exclude="__pycache__" \
  --exclude="*.pyc" \
  --exclude=".pytest_cache" \
  --exclude=".venv" \
  --exclude="deploy/*.tar" \
  --exclude="deploy/*.tar.gz" \
  -czf "$ARCHIVE" .

echo "$ARCHIVE"
