# syntax=docker/dockerfile:1
FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ffmpeg \
    espeak-ng \
    libespeak-ng1 \
    && rm -rf /var/lib/apt/lists/*

FROM base AS builder
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

FROM base
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH
COPY . .
EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=3s --start-period=120s \
    CMD curl -f http://localhost:5000/health || exit 1
CMD ["gunicorn", "-b", "0.0.0.0:5000", "--timeout", "300", "--workers", "1", "app:app"]
