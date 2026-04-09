FROM python:3.12-slim

# Install Node.js for Claude Code CLI
RUN apt-get update && apt-get install -y \
    wget gnupg ca-certificates curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI globally
RUN npm install -g @anthropic-ai/claude-code --quiet 2>/dev/null || true

# Install Playwright system deps
RUN apt-get update && apt-get install -y \
    libnss3 libatk-bridge2.0-0 libdrm2 libxkbcommon0 \
    libgbm1 libasound2 libxss1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[all]"

# Install Playwright Chromium
RUN playwright install chromium 2>/dev/null || true

COPY src/ ./src/
CMD ["python", "-m", "src.main"]
