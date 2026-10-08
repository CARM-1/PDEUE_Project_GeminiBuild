# Lightweight Python 3.11 Linux base image
FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install minimal application dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy verified application files and persistent database
COPY stage2_core_desktops.py app.py
COPY fund_member.py .
COPY pdeue.db .

# Expose internal web port
EXPOSE 8000

# Start production server
CMD ["python3", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
