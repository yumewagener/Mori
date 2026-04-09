<script>
  import { onMount } from 'svelte'
  import { api } from '../lib/api.js'
  import { addToast } from '../lib/stores.js'
  import StatusBadge from '../components/StatusBadge.svelte'
  import TopBar from '../components/TopBar.svelte'

  let pipelineList = []
  let pipelineRuns = []
  let loading = true

  async function load() {
    try {
      const [p, r] = await Promise.all([
        api.getPipelines().catch(() => []),
        api.getPipelineRuns().catch(() => []),
      ])
      pipelineList = Array.isArray(p) ? p : (p?.pipelines || [])
      pipelineRuns = Array.isArray(r) ? r : (r?.runs || [])
    } catch (e) {
      addToast('Error cargando pipelines', 'error')
    } finally {
      loading = false
    }
  }

  function formatDate(d) {
    if (!d) return '—'
    return new Date(d).toLocaleString('es', { dateStyle: 'short', timeStyle: 'short' })
  }

  function formatCost(v) {
    if (v == null) return '—'
    return '$' + Number(v).toFixed(4)
  }

  function formatDuration(ms) {
    if (!ms) return '—'
    const s = Math.round(ms / 1000)
    return s < 60 ? s + 's' : Math.floor(s/60) + 'm ' + (s%60) + 's'
  }

  onMount(load)
</script>

<div>
  <TopBar title="Pipelines" subtitle="Flujos de trabajo multi-agente" />

  {#if loading}
    <div class="loading-text">Cargando pipelines...</div>
  {:else}
    <!-- Pipelines disponibles -->
    <div class="section">
      <h2 class="section-title">Pipelines disponibles</h2>
      {#if pipelineList.length === 0}
        <div class="empty-state">No hay pipelines configurados</div>
      {:else}
        <div class="pipeline-list">
          {#each pipelineList as p}
            <div class="pipeline-card">
              <div class="pipeline-header">
                <span class="pipeline-name">{p.name}</span>
                {#if p.description}
                  <span class="pipeline-desc">{p.description}</span>
                {/if}
              </div>
              {#if p.steps && p.steps.length > 0}
                <div class="steps-visual">
                  {#each p.steps as step, i}
                    <div class="step-box">
                      <span class="step-num">{i + 1}</span>
                      <span class="step-name">{step.name || step.agent || step}</span>
                    </div>
                    {#if i < p.steps.length - 1}
                      <div class="step-arrow">→</div>
                    {/if}
                  {/each}
                </div>
              {/if}
              <div class="pipeline-meta">
                {#if p.agents_count != null}
                  <span class="meta-item">{p.agents_count} agentes</span>
                {/if}
                {#if p.runs_count != null}
                  <span class="meta-item">{p.runs_count} ejecuciones</span>
                {/if}
              </div>
            </div>
          {/each}
        </div>
      {/if}
    </div>

    <!-- Ejecuciones recientes -->
    <div class="section">
      <h2 class="section-title">Ejecuciones recientes</h2>
      {#if pipelineRuns.length === 0}
        <div class="empty-state">No hay ejecuciones registradas</div>
      {:else}
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Tarea</th>
                <th>Pipeline</th>
                <th>Estado</th>
                <th>Agentes</th>
                <th>Costo</th>
                <th>Duración</th>
                <th>Fecha</th>
              </tr>
            </thead>
            <tbody>
              {#each pipelineRuns as run}
                <tr>
                  <td class="task-name">{run.task_title || run.task_id || '—'}</td>
                  <td>{run.pipeline_name || run.pipeline_id || '—'}</td>
                  <td><StatusBadge status={run.status} /></td>
                  <td class="agents-cell">
                    {#if run.agents_used && run.agents_used.length > 0}
                      {#each run.agents_used.slice(0,3) as a}
                        <span class="agent-chip">{a}</span>
                      {/each}
                      {#if run.agents_used.length > 3}
                        <span class="agent-chip more">+{run.agents_used.length - 3}</span>
                      {/if}
                    {:else}—{/if}
                  </td>
                  <td class="mono">{formatCost(run.cost)}</td>
                  <td class="mono">{formatDuration(run.duration_ms)}</td>
                  <td class="mono date-cell">{formatDate(run.created_at)}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {/if}
    </div>
  {/if}
</div>

<style>
  .loading-text { color: var(--text-muted); padding: 40px; text-align: center; }

  .section { margin-bottom: 32px; }
  .section-title {
    font-size: 12px; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.5px;
    color: var(--text-muted); margin-bottom: 14px;
  }

  .empty-state {
    text-align: center; padding: 32px;
    color: var(--text-muted);
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
  }

  .pipeline-list { display: flex; flex-direction: column; gap: 12px; }

  .pipeline-card {
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 16px 20px;
  }

  .pipeline-header {
    display: flex;
    align-items: baseline;
    gap: 12px;
    margin-bottom: 12px;
  }
  .pipeline-name { font-weight: 600; font-size: 14px; }
  .pipeline-desc { font-size: 12px; color: var(--text-muted); }

  .steps-visual {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 6px;
    margin-bottom: 12px;
  }

  .step-box {
    display: flex;
    align-items: center;
    gap: 6px;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 5px 10px;
    font-size: 12px;
  }
  .step-num {
    width: 16px; height: 16px;
    background: var(--accent);
    color: white;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 9px;
    font-weight: 700;
    flex-shrink: 0;
  }
  .step-name { font-size: 12px; color: var(--text); }
  .step-arrow { color: var(--text-muted); font-size: 16px; }

  .pipeline-meta {
    display: flex;
    gap: 16px;
  }
  .meta-item { font-size: 12px; color: var(--text-muted); }

  .table-wrap {
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: auto;
  }
  table { width: 100%; border-collapse: collapse; }
  thead tr { border-bottom: 1px solid var(--border); }
  th { padding: 10px 14px; text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-muted); font-weight: 500; }
  td { padding: 10px 14px; font-size: 13px; border-bottom: 1px solid var(--border); }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: var(--bg-elevated); }
  .task-name { font-weight: 500; max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .mono { font-family: var(--font-mono); font-size: 12px; }
  .date-cell { color: var(--text-muted); }

  .agents-cell { display: flex; flex-wrap: wrap; gap: 4px; }
  .agent-chip {
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 1px 6px;
    font-size: 11px;
    color: var(--text-muted);
  }
  .more { color: var(--accent); }
</style>
