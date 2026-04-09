<script>
  import { onMount, onDestroy } from 'svelte'
  import { api, streamRun } from '../lib/api.js'
  import { addToast } from '../lib/stores.js'
  import StreamOutput from '../components/StreamOutput.svelte'
  import StatusBadge from '../components/StatusBadge.svelte'
  import ModelBadge from '../components/ModelBadge.svelte'
  import Button from '../components/Button.svelte'

  export let runId = ''

  let task = null
  let run = null
  let content = ''
  let isStreaming = false
  let loading = true
  let error = null
  let stopStream = null
  let elapsed = 0
  let timer = null

  async function load() {
    try {
      task = await api.getTask(runId)
      const runs = await api.getTaskRuns(runId).catch(() => [])
      const runList = Array.isArray(runs) ? runs : (runs?.runs || [])
      run = runList[0] || null

      if (run?.status === 'running') {
        startStream()
      } else if (run?.output) {
        content = run.output
      }
    } catch (e) {
      error = 'No se pudo cargar la tarea: ' + e.message
      addToast(error, 'error')
    } finally {
      loading = false
    }
  }

  function startStream() {
    isStreaming = true
    content = ''
    elapsed = 0
    timer = setInterval(() => elapsed++, 1000)

    stopStream = streamRun(
      run.id,
      (chunk) => {
        try { content += JSON.parse(chunk) }
        catch { content += chunk }
      },
      async () => {
        isStreaming = false
        clearInterval(timer)
        // Refresh final run stats
        try {
          const runs = await api.getTaskRuns(runId)
          const runList = Array.isArray(runs) ? runs : (runs?.runs || [])
          run = runList[0] || run
        } catch {}
      },
      (e) => {
        isStreaming = false
        clearInterval(timer)
        addToast('Error en streaming', 'error')
      }
    )
  }

  async function cancelTask() {
    try {
      await api.cancelTask(runId)
      addToast('Tarea cancelada', 'success')
      isStreaming = false
      stopStream?.()
      clearInterval(timer)
      await load()
    } catch (e) {
      addToast('Error cancelando tarea', 'error')
    }
  }

  function formatDuration(s) {
    if (s < 60) return s + 's'
    return Math.floor(s / 60) + 'm ' + (s % 60) + 's'
  }

  function formatCost(v) {
    if (v == null) return '—'
    return '$' + Number(v).toFixed(4)
  }

  onMount(load)
  onDestroy(() => {
    stopStream?.()
    clearInterval(timer)
  })
</script>

<div class="taskrun">
  {#if loading}
    <div class="loading">Cargando ejecución...</div>
  {:else if error}
    <div class="error-state">{error}</div>
  {:else if !task}
    <div class="error-state">Tarea no encontrada</div>
  {:else}
    <!-- Header -->
    <div class="run-header">
      <div class="run-header-main">
        <a href="/tasks" class="back-link">← Tareas</a>
        <h1 class="run-title">{task.title}</h1>
        <div class="run-meta">
          {#if task.agent}
            <span class="meta-item">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="8" r="4"/><path d="M20 21a8 8 0 10-16 0"/></svg>
              {task.agent}
            </span>
          {/if}
          {#if task.model}
            <ModelBadge modelId={task.model} />
          {/if}
          {#if task.pipeline}
            <span class="meta-item">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 014-4h14"/><polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 01-4 4H3"/></svg>
              {task.pipeline}
            </span>
          {/if}
          {#if run}
            <StatusBadge status={run.status} />
          {/if}
          {#if run?.turn != null}
            <span class="meta-item turn">Turno {run.turn}/{run.max_turns || '?'}</span>
          {/if}
        </div>
      </div>
      {#if isStreaming}
        <Button variant="danger" size="sm" on:click={cancelTask}>Cancelar</Button>
      {/if}
    </div>

    <!-- Stream output -->
    <div class="output-section">
      {#if content || isStreaming}
        <StreamOutput {content} {isStreaming} />
      {:else if !run}
        <div class="no-run">
          <div class="no-run-icon">▶</div>
          <p>No hay ejecuciones para esta tarea todavía.</p>
        </div>
      {:else}
        <div class="no-run">
          <p>No hay salida registrada para esta ejecución.</p>
        </div>
      {/if}
    </div>

    <!-- Stats bar -->
    {#if run || isStreaming}
      <div class="stats-bar">
        <div class="stat-item">
          <span class="stat-icon">💰</span>
          <span class="stat-val">{formatCost(run?.cost)}</span>
        </div>
        <div class="stat-item">
          <span class="stat-icon">⏱</span>
          <span class="stat-val">{isStreaming ? formatDuration(elapsed) : formatDuration(Math.round((run?.duration_ms || 0) / 1000))}</span>
        </div>
        <div class="stat-item">
          <span class="stat-icon">🔤</span>
          <span class="stat-val">{run?.total_tokens ? (run.total_tokens / 1000).toFixed(1) + 'K tokens' : '—'}</span>
        </div>
        {#if run?.model}
          <div class="stat-item">
            <ModelBadge modelId={run.model} />
          </div>
        {/if}
      </div>
    {/if}
  {/if}
</div>

<style>
  .taskrun { max-width: 860px; }

  .loading, .error-state {
    padding: 48px;
    text-align: center;
    color: var(--text-muted);
  }
  .error-state { color: var(--danger); }

  .back-link {
    font-size: 12px;
    color: var(--text-muted);
    display: block;
    margin-bottom: 8px;
  }
  .back-link:hover { color: var(--text); }

  .run-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    margin-bottom: 20px;
  }

  .run-title {
    font-size: 20px;
    font-weight: 600;
    margin-bottom: 10px;
  }

  .run-meta {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px;
  }

  .meta-item {
    font-size: 12px;
    color: var(--text-muted);
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .turn {
    background: var(--bg-elevated);
    padding: 2px 8px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border);
    font-family: var(--font-mono);
  }

  .output-section { margin-bottom: 16px; }

  .no-run {
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 48px;
    text-align: center;
    color: var(--text-muted);
  }
  .no-run-icon { font-size: 32px; margin-bottom: 12px; }

  .stats-bar {
    display: flex;
    align-items: center;
    gap: 20px;
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 12px 20px;
  }

  .stat-item {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    color: var(--text-muted);
  }

  .stat-icon { font-size: 14px; }
  .stat-val { font-family: var(--font-mono); font-size: 13px; color: var(--text); }
</style>
