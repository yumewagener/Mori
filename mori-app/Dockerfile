# ── Stage 1: Build Svelte frontend ────────────────────────────
FROM node:20-slim AS frontend-builder
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci --silent
COPY frontend/ ./
RUN npm run build

# ── Stage 2: Python API server ────────────────────────────────
FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY db/ ./db/

# Copy compiled frontend from stage 1
COPY --from=frontend-builder /frontend/dist ./frontend/dist

EXPOSE 8080

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "2"]
