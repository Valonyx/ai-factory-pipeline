# AI Factory Pipeline v5.6 — Cloud Run Container
# Spec: §7.4.1

FROM python:3.11-slim

# Security: non-root user
RUN groupadd -r factory && useradd -r -g factory factory

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY factory/ ./factory/
COPY pyproject.toml .

# Set ownership
RUN chown -R factory:factory /app

USER factory

# Cloud Run uses PORT env var (default 8080)
ENV PORT=8080
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE ${PORT}

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import httpx; r = httpx.get('http://localhost:${PORT}/health'); assert r.status_code == 200"

# Entry point (shell form so $PORT env var is expanded)
CMD python -m uvicorn factory.main:app --host 0.0.0.0 --port ${PORT}