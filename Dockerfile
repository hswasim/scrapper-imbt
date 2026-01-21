# =============================================================================
# BASE IMAGE OPTIONS (uncomment ONE)
# =============================================================================

# Option 1: Standard Python (default - for API scrapers like requests/httpx)
FROM python:3.11-slim

# Option 2: Playwright (for browser automation - uncomment and comment Option 1)
# FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy
# Note: Requires CLOUD_RUN_MEMORY=2Gi and CLOUD_RUN_CPU=2 in CI/CD variables

# =============================================================================

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all Python files (scraper.py, main.py, parsers.py, etc.)
COPY *.py .

# =============================================================================
# RUN OPTIONS (uncomment ONE based on your structure)
# =============================================================================

# Option A: Single script (default - Cloud Run Job)
CMD ["python", "scraper.py"]

# Option B: HTTP API (Cloud Run Service with FastAPI)
# EXPOSE 8080
# CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
