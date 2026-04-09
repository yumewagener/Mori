FROM python:3.12-slim

# Install system deps for Playwright
RUN apt-get update && apt-get install -y \
    wget gnupg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml .
RUN pip install -e ".[all]"

# Install Playwright chromium (only if needed, controlled by config)
RUN playwright install chromium --with-deps 2>/dev/null || true

COPY src/ ./src/
CMD ["python", "-m", "src.main"]
