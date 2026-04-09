# Mori Installation Guide

## Prerequisites

### Required

- **Docker** 24.0 or later — [install Docker](https://docs.docker.com/get-docker/)
- **Docker Compose** v2 (included with Docker Desktop; on Linux, install the `docker-compose-plugin` package)
- **Git** — to clone the repository
- **openssl** — for generating the auth token (pre-installed on macOS/Linux)

### Verify

```bash
docker --version        # Docker version 24.x or later
docker compose version  # Docker Compose version v2.x
git --version
```

### Recommended

- 4 GB RAM minimum (8 GB if running Ollama local models)
- 10 GB free disk space (more if downloading large local models)
- Linux or macOS (Windows with WSL2 is supported but not primary target)

---

## 1. Clone and Prepare

```bash
git clone https://github.com/yumewagener/Mori
cd Mori
chmod +x mori
```

---

## 2. Configure Environment

Copy the example environment file to your Mori home directory:

```bash
cp mori.env.example ~/.mori/.env
```

Open `~/.mori/.env` in your editor and fill in the values you need:

```bash
# Required: set a strong auth token
# The install script will generate one automatically if you leave the default
MORI_TOKEN=cambia_esto_por_un_token_seguro

# Add at least one AI provider API key
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=...
```

You only need API keys for the models you plan to use. If you're running only local models via Ollama, no cloud API keys are required.

---

## 3. Configure Mori

Copy the example config:

```bash
cp mori.yaml.example ~/.mori/config/mori.yaml
```

Open `~/.mori/config/mori.yaml` and review the settings:

- **`models:`** — Comment out or remove models you don't have API keys for.
- **`agents:`** — The defaults work well; customize system prompts and routing rules as needed.
- **`pipelines:`** — The standard pipeline is the default; it works without any changes.
- **`tools:`** — All external tools (web_search, shell, browser) are disabled by default. Enable only what you need.

See [docs/CONFIG-REFERENCE.md](docs/CONFIG-REFERENCE.md) for documentation on every field.

---

## 4. Install and Start

```bash
./mori install
./mori start
```

`./mori install` will:
1. Create `~/.mori/{config,data,logs}` directories
2. Copy example files if they don't exist
3. Generate a random auth token if the default placeholder is still set
4. Build all Docker images

After a successful install, open **http://localhost:18811** in your browser.

Log in with the token shown after install (or from `~/.mori/.env` → `MORI_TOKEN`).

---

## 5. Verify Everything is Running

```bash
./mori status
```

You should see all services with status `Up`:

```
NAME                    STATUS
mori-caddy-1            Up
mori-app-1              Up
mori-orchestrator-1     Up
mori-mcp-gateway-1      Up
mori-mcp-gateway-sse-1  Up
mori-tasks-mcp-1        Up
mori-notes-mcp-1        Up
mori-platform-mcp-1     Up
mori-socket-proxy-1     Up
```

If any service is in a restart loop, check its logs:

```bash
./mori logs orchestrator
./mori logs app
```

---

## 6. Adding Local Models (Ollama)

To run AI models locally without cloud API keys:

### a. Enable Ollama in your config

In `~/.mori/config/mori.yaml`, the `llama3-local` and `qwen-coder-local` models are pre-configured for Ollama. Make sure they're uncommented.

### b. Start with the Ollama profile

```bash
./mori ollama
```

This starts all standard services plus the Ollama container. On first run it downloads the model (several GB).

### c. Pull a model

```bash
docker exec mori-ollama-1 ollama pull llama3.3:70b
```

Replace `llama3.3:70b` with any [Ollama model](https://ollama.com/library). For machines with limited RAM, try `llama3.2:3b` or `mistral:7b`.

### d. GPU acceleration (optional)

Ollama automatically uses an NVIDIA GPU if:
- NVIDIA drivers are installed
- `nvidia-container-toolkit` is installed (`sudo apt install nvidia-container-toolkit` on Ubuntu)
- Docker can access the GPU (`docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi` works)

The `docker-compose.yml` already configures the GPU reservation for the Ollama service.

---

## 7. Enable Web Search (SearXNG)

To give agents the ability to search the web:

### a. Enable in config

In `~/.mori/config/mori.yaml`:

```yaml
tools:
  web_search:
    enabled: true
    provider: searxng
    searxng_url: http://searxng:8080
```

### b. Start with the web-search profile

```bash
docker compose --env-file ~/.mori/.env --profile web-search up -d
```

Or add `web-search` to your start command permanently by creating a `docker-compose.override.yml`.

SearXNG will be available at http://localhost:8888 for direct access.

---

## 8. Cloudflare Tunnel Setup (Optional)

To access Mori remotely without opening ports:

### a. Create a Cloudflare tunnel

1. Go to [Cloudflare Zero Trust](https://one.dash.cloudflare.com/) → Networks → Tunnels
2. Create a new tunnel and copy the token
3. Point a hostname (e.g., `mori.yourdomain.com`) to `http://caddy:80`

### b. Add the Cloudflare connector service

Create `docker-compose.override.yml` in the Mori directory:

```yaml
services:
  cloudflared:
    image: cloudflare/cloudflared:latest
    restart: unless-stopped
    command: tunnel run
    environment:
      TUNNEL_TOKEN: ${MORI_CF_TOKEN}
    networks:
      - mori-net
```

### c. Add token to env file

```bash
echo "MORI_CF_TOKEN=your_tunnel_token_here" >> ~/.mori/.env
```

### d. Restart

```bash
./mori restart
```

Your Mori instance will now be accessible at `https://mori.yourdomain.com`, protected by the `MORI_TOKEN` Bearer auth.

---

## 9. Updating Mori

```bash
./mori update
```

This pulls the latest code, rebuilds images, and restarts services with zero-downtime for the database.

---

## 10. Backup

```bash
./mori backup
# Saves to ~/.mori/backups/mori-YYYYMMDD-HHMMSS.sqlite3
```

To restore:

```bash
cp ~/.mori/backups/mori-20240115-143022.sqlite3 ~/.mori/data/mori.sqlite3
./mori restart
```

---

## Troubleshooting

### "Permission denied" when running `./mori`

```bash
chmod +x mori
```

### Port 18811 already in use

Another service is using port 18811. Either stop it or change Mori's port in `docker-compose.yml`:

```yaml
caddy:
  ports:
    - "19000:80"   # Change 18811 to any free port
```

### Docker image build fails

Ensure Docker daemon is running and you have internet access:

```bash
docker pull python:3.12-slim   # Should succeed
```

If behind a corporate proxy, configure Docker's proxy settings.

### Orchestrator keeps restarting

Check the orchestrator logs:

```bash
./mori logs orchestrator
```

Common causes:
- Missing or invalid API key in `~/.mori/.env` for a model that's enabled in config
- Syntax error in `mori.yaml` (validate with `python -c "import yaml; yaml.safe_load(open('~/.mori/config/mori.yaml'))"`)
- Database permissions issue (ensure `~/.mori/data/` is writable)

### No models available / tasks not executing

1. Verify at least one model has a valid API key in `~/.mori/.env`
2. Confirm the model's `api_key_env` in `mori.yaml` matches the env var name exactly
3. Check orchestrator logs for connection errors to the model provider

### MCP Gateway connection refused

The MCP gateway depends on the MCP servers being healthy. Check:

```bash
./mori logs tasks-mcp
./mori logs notes-mcp
./mori logs platform-mcp
```

If the SQLite database doesn't exist yet, start Mori once without any tasks — the schema is created on first connection.
