FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PDEUE_DB_PATH=/var/lib/pdeue/pdeue.db
WORKDIR /app
COPY requirements.txt .
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt \
    && groupadd --system pdeue \
    && useradd --system --gid pdeue pdeue \
    && install -d --owner=pdeue --group=pdeue /var/lib/pdeue
COPY --chmod=0644 app.py fleet_engine.py venue_adapters.py ifas_local_bridge.py \
    fund_member.py sports_adapter.py treasury_adapter.py priority_eviction.py ./
COPY --chown=pdeue:pdeue --chmod=0600 pdeue.db /var/lib/pdeue/pdeue.db
USER pdeue
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["curl", "--fail", "--silent", "--max-time", "3", "http://127.0.0.1:8000/healthz"]
CMD ["python3", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
