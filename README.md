# Mori

Local multi-model AI orchestrator — self-hosted, configurable, no vendor lock-in.

Mori routes tasks to the right AI model automatically, executes multi-step pipelines, and streams results to a real-time UI. Run it on your laptop or VPS with any combination of local (Ollama) and cloud (Anthropic, OpenAI, Google) models.

## Features

- **Multi-model routing** — configurable via YAML, no hardcoded models
- **Parallel execution** — up to N tasks simultaneously across different models
- **Pipeline engine** — execute → review → fix loops with automatic handoffs  
- **Real-time streaming** — see model output as it happens in the web UI
- **Tool calling loop** — agents can use filesystem, web search, shell, and more
- **Memory/context** — FTS5 search over notes and history injected before each run
- **Cost tracking** — per-model cost dashboard, no surprises
- **Local-first** — works offline with Ollama, cloud models optional

## Quick start

```bash
git clone https://github.com/yumewagener/Mori
cd Mori
cp mori.env.example ~/.mori/.env
cp mori.yaml.example ~/.mori/config/mori.yaml
# Edit ~/.mori/config/mori.yaml — add your API keys
chmod +x mori
./mori install
./mori start
```

Open http://localhost:18811

## Requirements

- Docker + Docker Compose
- 4GB RAM minimum (8GB recommended if running local models)
- Optional: NVIDIA GPU for Ollama

## Configuration

Everything is configured in `~/.mori/config/mori.yaml`:
- `models:` — add/remove models, set API keys
- `agents:` — define routing rules, system prompts, tools
- `pipelines:` — multi-step execution flows
- `memory:` — context injection settings
- `tools:` — web search, shell, browser

See [docs/CONFIG-REFERENCE.md](docs/CONFIG-REFERENCE.md) for full documentation.

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## License

MIT
