# Mori Configuration Reference

Config file location: `~/.mori/config/mori.yaml`

---

## `orchestrator`

Controls the core execution engine.

```yaml
orchestrator:
  poll_seconds: 15            # How often to check for new tasks (seconds)
  max_parallel_tasks: 4       # Max tasks running simultaneously across all projects
  max_parallel_per_project: 2 # Max parallel tasks within a single project
  heartbeat_seconds: 30       # How often the orchestrator writes a heartbeat to the DB
  timeout_default_seconds: 1800 # Default task timeout (30 min), overridable per agent
  retry_on_failure: 1         # Times to retry a failed step before marking it failed
  stream_output: true         # Stream token output to DB in real-time (slightly slower but enables live UI)
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `poll_seconds` | integer | `15` | Task poll interval |
| `max_parallel_tasks` | integer | `4` | Global parallelism cap |
| `max_parallel_per_project` | integer | `2` | Per-project parallelism cap |
| `heartbeat_seconds` | integer | `30` | Heartbeat interval |
| `timeout_default_seconds` | integer | `1800` | Default step timeout |
| `retry_on_failure` | integer | `1` | Retry count on step failure |
| `stream_output` | boolean | `true` | Enable streaming to DB |

---

## `models`

A list of model definitions. Each model is referenced by its `id` in agent configs.

```yaml
models:
  - id: claude-opus           # Unique identifier used in agents/pipelines
    provider: anthropic       # Provider: anthropic, openai, google, ollama, mistral
    model: claude-opus-4-5    # Provider's model name
    api_key_env: ANTHROPIC_API_KEY  # Env var containing the API key
    max_tokens: 200000        # Context window size
    capabilities:             # Used for auto-routing
      - reasoning
      - coding
      - writing
      - analysis
      - planning
    cost_per_1k_input: 0.015  # USD per 1,000 input tokens
    cost_per_1k_output: 0.075 # USD per 1,000 output tokens
    supports_tools: true      # Whether model supports tool/function calling
```

### Model fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | yes | Unique identifier referenced by agents |
| `provider` | string | yes | `anthropic`, `openai`, `google`, `ollama`, `mistral` |
| `model` | string | yes | Provider's model name |
| `api_key_env` | string | no | Name of env var with API key (omit for Ollama) |
| `base_url` | string | no | Override API endpoint (required for Ollama) |
| `max_tokens` | integer | no | Context window (used to limit input) |
| `capabilities` | list | no | Capability tags for auto-routing |
| `cost_per_1k_input` | float | no | Cost for cost tracking |
| `cost_per_1k_output` | float | no | Cost for cost tracking |
| `supports_tools` | boolean | no | Whether tool calling is supported |

### Example: Adding an OpenAI model

```yaml
models:
  - id: gpt-4o-mini
    provider: openai
    model: gpt-4o-mini
    api_key_env: OPENAI_API_KEY
    capabilities: [writing, analysis, fast]
    cost_per_1k_input: 0.00015
    cost_per_1k_output: 0.0006
    supports_tools: true
```

### Example: Adding an Ollama model

```yaml
models:
  - id: mistral-local
    provider: ollama
    model: mistral:7b
    base_url: http://ollama:11434
    capabilities: [writing, analysis]
    cost_per_1k_input: 0
    cost_per_1k_output: 0
    supports_tools: false
```

### Example: Adding a custom OpenAI-compatible endpoint

```yaml
models:
  - id: local-lm-studio
    provider: openai          # LM Studio is OpenAI-compatible
    model: lmstudio-community/Meta-Llama-3-8B-Instruct-GGUF
    base_url: http://host.docker.internal:1234/v1
    api_key_env: ""           # LM Studio doesn't require a key
    capabilities: [coding, writing]
    cost_per_1k_input: 0
    supports_tools: false
```

---

## `agents`

A list of agent definitions. Agents define how a model is used for a specific role.

```yaml
agents:
  - id: coder               # Unique identifier
    name: Code Agent        # Display name
    model: claude-sonnet    # Primary model ID (from models list)
    fallback_model: qwen-coder-local  # Used if primary fails or has no key
    role: executor          # Role: router, executor, reviewer, planner
    enabled: true           # Set false to disable without removing
    routing:                # Routing rules (only for executor role)
      tags: [coding, dev, bug, feature, refactor, test, deploy]
      areas: [proyecto, sistema]
      keywords: [código, script, función, clase, API]
    system_prompt: |
      Your system prompt here.
    tools:                  # MCP tools this agent can call
      - read_file
      - write_file
      - container_logs
    working_directory: true # Inject project working directory into context
    timeout_seconds: 3600   # Override default timeout for this agent
```

### Agent fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | yes | Unique identifier |
| `name` | string | yes | Display name |
| `model` | string | yes | Model ID from `models` list |
| `fallback_model` | string | no | Model to use if primary is unavailable |
| `role` | string | yes | `router`, `executor`, `reviewer`, `planner` |
| `enabled` | boolean | no | Default `true` |
| `routing` | object | no | Routing rules (executor agents only) |
| `routing.tags` | list | no | Task tags that route to this agent |
| `routing.areas` | list | no | Task areas that route to this agent |
| `routing.keywords` | list | no | Keywords in title/description that route here |
| `system_prompt` | string | yes | System prompt injected before each run |
| `tools` | list | no | MCP tool names available to this agent |
| `working_directory` | boolean | no | Inject project path into context |
| `timeout_seconds` | integer | no | Override global timeout for this agent |

### Available tools

| Tool | Server | Description |
|------|--------|-------------|
| `task_list` | tasks-mcp | List tasks |
| `task_create` | tasks-mcp | Create a task |
| `task_update_status` | tasks-mcp | Update task status |
| `task_get` | tasks-mcp | Get task by ID |
| `note_list` | notes-mcp | List notes (with FTS search) |
| `note_create` | notes-mcp | Create a note |
| `note_get` | notes-mcp | Get note by ID |
| `note_update` | notes-mcp | Update a note |
| `decision_create` | notes-mcp | Create a decision record |
| `project_list` | platform-mcp | List projects |
| `project_create` | platform-mcp | Create a project |
| `container_logs` | platform-mcp | Get container logs |
| `container_restart` | platform-mcp | Restart a container |
| `pipeline_status` | platform-mcp | Get recent pipeline runs |
| `web_search` | searxng | Web search (requires tools.web_search enabled) |
| `read_file` | orchestrator | Read file from working directory |
| `write_file` | orchestrator | Write file to working directory |
| `list_directory` | orchestrator | List directory contents |
| `search_files` | orchestrator | Search files by content/name |

### Example: Creating a custom agent

```yaml
agents:
  - id: data-analyst
    name: Data Analyst
    model: gpt-4o
    fallback_model: claude-sonnet
    role: executor
    enabled: true
    routing:
      tags: [data, analytics, sql, pandas, visualización]
      keywords: [analiza, dataset, csv, dataframe, gráfico, estadística]
    system_prompt: |
      Eres un analista de datos experto en Python, pandas, SQL y visualización.
      Cuando recibes una tarea de análisis:
      1. Lee los archivos de datos disponibles en el directorio de trabajo
      2. Escribe el código Python necesario
      3. Interpreta los resultados y crea una nota con el resumen
    tools:
      - read_file
      - write_file
      - list_directory
      - note_create
    working_directory: true
    timeout_seconds: 1800
```

---

## `pipelines`

Multi-step execution flows. The orchestrator selects a pipeline based on task tags.

```yaml
pipelines:
  - id: code_pipeline       # Unique identifier
    name: Code Pipeline     # Display name
    description: Implement code with review and auto-correction
    trigger:                # When to use this pipeline
      tags: [coding, dev, bug, feature, refactor]
    steps:
      - agent: coder        # Agent ID or 'auto' for automatic routing
        phase: execute      # Phase name (arbitrary string, shown in UI)
      - agent: reviewer
        phase: review
        condition: on_success    # Run only if previous step succeeded
      - agent: coder
        phase: fix
        condition: needs_changes # Run only if reviewer returned NECESITA_CAMBIOS
        max_iterations: 2        # Retry this step up to N times
```

### Pipeline fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | yes | Unique identifier |
| `name` | string | yes | Display name |
| `description` | string | no | Human description |
| `default` | boolean | no | Use when no other pipeline matches |
| `trigger.tags` | list | no | Task tags that activate this pipeline |
| `steps[].agent` | string | yes | Agent ID or `auto` |
| `steps[].phase` | string | yes | Phase label |
| `steps[].condition` | string | no | `on_success`, `needs_changes`, `always` |
| `steps[].optional` | boolean | no | Don't fail pipeline if this step fails |
| `steps[].parallel` | boolean | no | Run subtasks in parallel (planner output) |
| `steps[].max_iterations` | integer | no | Max retries for this step |

### Example: Custom pipeline

```yaml
pipelines:
  - id: deploy_pipeline
    name: Deploy Pipeline
    description: Test, build, and deploy a project
    trigger:
      tags: [deploy, release]
    steps:
      - agent: coder
        phase: test
      - agent: coder
        phase: build
        condition: on_success
      - agent: reviewer
        phase: review
        condition: on_success
      - agent: coder
        phase: deploy
        condition: on_success
```

---

## `memory`

Controls how past context is injected into agent runs.

```yaml
memory:
  enabled: true
  embedding_model: nomic-embed-text  # Ollama model for embeddings (if available)
  fallback: tfidf                     # Fallback if embedding model unavailable
  top_k: 5                           # Number of relevant items to inject
  sources:
    - notes          # Search notes table
    - decisions      # Search decision notes
    - task_history   # Search completed task descriptions
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | boolean | `true` | Enable memory injection |
| `embedding_model` | string | `nomic-embed-text` | Ollama embedding model |
| `fallback` | string | `tfidf` | Fallback search: `tfidf` or `fts5` |
| `top_k` | integer | `5` | Items to inject per run |
| `sources` | list | `[notes, decisions, task_history]` | Tables to search |

---

## `tools`

Enable optional external tool integrations.

```yaml
tools:
  web_search:
    enabled: false
    provider: searxng
    searxng_url: http://searxng:8080

  shell:
    enabled: false
    allowed_commands: [git, pytest, npm, cargo, make, python]
    working_directory_only: true  # Commands can only run in the project working directory

  browser:
    enabled: false
    headless: true
```

> **Security note:** `shell` and `browser` tools give agents significant system access. Only enable them if you trust the agents and use a restrictive `allowed_commands` list.

---

## `notifications`

```yaml
notifications:
  telegram:
    enabled: false
    bot_token_env: MORI_TELEGRAM_BOT_TOKEN  # Env var with the bot token
    chat_id_env: MORI_TELEGRAM_CHAT_ID      # Env var with the chat ID
    on_events:
      - task_completed
      - task_failed
      - pipeline_blocked

  webhook:
    enabled: false
    url_env: MORI_WEBHOOK_URL   # Env var with the webhook URL
```

Events: `task_completed`, `task_failed`, `task_created`, `pipeline_blocked`, `agent_error`.

Webhook payload:
```json
{
  "event": "task_completed",
  "task_id": 42,
  "task_title": "...",
  "timestamp": "2024-01-15T10:30:00Z"
}
```
