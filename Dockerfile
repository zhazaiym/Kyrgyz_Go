FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --upgrade "pip>=26.2" \
    && python -m pip install --no-cache-dir -r requirements.txt \
    && groupadd --system app \
    && useradd --system --gid app --home-dir /app app

COPY --chown=app:app Dockerfile main.py create_admin.py seed_demo.py alembic.ini ./
COPY --chown=app:app ML ./ML
COPY --chown=app:app mysite ./mysite
COPY --chown=app:app alembic ./alembic

USER app
EXPOSE 8000

CMD ["sh", "-c", "python -m alembic upgrade head && exec python -m uvicorn main:app --host 0.0.0.0 --port 8000 --proxy-headers --limit-concurrency 128 --backlog 256 --timeout-keep-alive 5 --ws-max-size 16384 --ws-max-queue 8 --ws-per-message-deflate false"]
