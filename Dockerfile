FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
COPY fleet_engine.py .
COPY venue_adapters.py .
COPY ifas_local_bridge.py .
COPY fund_member.py .
COPY sports_adapter.py .
COPY treasury_adapter.py .
COPY pdeue.db .
EXPOSE 8000
CMD ["python3", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
