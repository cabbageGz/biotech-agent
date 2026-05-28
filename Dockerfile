FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    PIP_DEFAULT_TIMEOUT=120

WORKDIR /app

COPY pyproject.toml README.md ./
COPY agents ./agents
COPY api ./api
COPY frontend ./frontend
COPY prompts ./prompts
COPY tools ./tools
COPY workflows ./workflows

EXPOSE 8787

CMD ["python", "-m", "api.cli", "serve", "--host", "0.0.0.0", "--port", "8787"]
