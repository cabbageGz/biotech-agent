FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY pyproject.toml README.md ./
COPY agents ./agents
COPY api ./api
COPY frontend ./frontend
COPY prompts ./prompts
COPY tools ./tools
COPY workflows ./workflows

RUN pip install --no-cache-dir .

EXPOSE 8787

CMD ["python", "-m", "api.cli", "serve", "--host", "0.0.0.0", "--port", "8787"]
