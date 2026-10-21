FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md requirements.txt requirements-ui.txt ./
COPY src ./src
COPY backend ./backend
COPY frontend ./frontend
COPY scripts/container-entrypoint.sh ./scripts/container-entrypoint.sh
COPY scripts/setup_demo.sh ./scripts/setup_demo.sh

RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt -r requirements-ui.txt \
    && python -m pip install --no-deps . \
    && chmod +x scripts/container-entrypoint.sh scripts/setup_demo.sh

EXPOSE 8000 8501

CMD ["/app/scripts/container-entrypoint.sh"]
