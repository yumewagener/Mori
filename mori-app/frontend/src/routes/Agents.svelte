<script>
  import { onMount } from 'svelte'
  import { api } from '../lib/api.js'
  import { addToast } from '../lib/stores.js'
  import ModelBadge from '../components/ModelBadge.svelte'
  import TopBar from '../components/TopBar.svelte'

  let agentList = []
  let loading = true

  const roleColors = {
    router: 'var(--accent)',
    executor: 'var(--info)',
    reviewer: 'var(--warning)',
    planner: 'var(--success)',
  }

  const roleBg = {
    router: 'rgba(124,106,255,0.12)',
    executor: 'rgba(56,189,248,0.12)',
    reviewer: 'rgba(245,158,11,0.12)',
    planner: 'rgba(34,197,94,0.12)',
  }

  async function load() {
    try {
      const res = await api.getAgents()
      agentList = Array.isArray(res) ? res : (res?.agents || [])
    } catch (e) {
      addToast('Error cargando agentes', 'error')
    } finally {
      loading = false
    }
  }

  function successRate(agent) {
    if (!agent.runs_count || agent.runs_count === 0) return null
    const rate = (agent.success_count || 0) / agent.runs_count
    return Math.round(rate * 100)
  }

  onMount(load)
</script>

<div>
  <TopBar title="Agentes" subtitle="Agentes disponibles en el orquestador" />

  {#if loading}
    <div class="agents-grid">
      {#each [1,2,3,4] as _}
        <div class="skeleton-card"></div>
      {/each}
    </div>
  {:else if agentList.length === 0}
    <div class="empty-state">
      <div class="empty-icon">🤖</div>
      <p>No hay agentes configurados</p>
    </div>
  {:else}
    <div class="agents-grid">
      {#each agentList as agent}
        <div class="agent-card">
          <div class="agent-header">
            <div class="agent-avatar">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="8" r="4"/><path d="M20 21a8 8 0 10-16 0"/></svg>
            </div>
            <div class="agent-identity">
              <span class="agent-name">{agent.name || agent.id}</span>
              <span
                class="role-badge"
                style="color: {roleColors[agent.role] || 'var(--text-muted)'}; background: {roleBg[agent.role] || 'var(--bg-elevated)'};"
              >{agent.role || 'unknown'}</span>
            </div>
          </div>

          {#if agent.description}
            <p class="agent-desc">{agent.description}</p>
          {/if}

          <div class="agent-models">
            {#if agent.model}
              <div class="model-row">
                <span class="model-label">Modelo</span>
                <ModelBadge modelId={agent.model} />
              </div>
            {/if}
            {#if agent.fallback_model}
              <div class="model-row">
                <span class="model-label">Fallback</span>
                <ModelBadge modelId={agent.fallback_model} />
              </div>
            {/if}
          </div>

          {#if agent.routing_tags && agent.routing_tags.length > 0}
            <div class="routing-tags">
              <span class="routing-label">Routing:</span>
              {#each agent.routing_tags as tag}
                <span class="routing-chip">{tag}</span>
              {/each}
            </div>
          {/if}

          <div class="agent-stats">
            <div class="stat-item">
              <span class="stat-label">Ejecuciones</span>
              <span class="stat-value">{agent.runs_count ?? '—'}</span>
            </div>
            <div class="stat-item">
              <span class="stat-label">Éxito</span>
              <span class="stat-value" style="color: {(successRate(agent) || 0) >= 80 ? 'var(--success)' : 'var(--warning)'}">
                {successRate(agent) != null ? successRate(agent) + '%' : '—'}
              </span>
            </div>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .agents-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 16px;
  }

  .skeleton-card {
    height: 200px;
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    animation: pulse 1.5s ease infinite;
  }
  @keyframes pulse { 0%,100%{opacity:1}50%{opacity:0.5} }

  .agent-card {
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 18px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    transition: border-color 0.15s;
  }
  .agent-card:hover { border-color: var(--accent); }

  .agent-header {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .agent-avatar {
    width: 40px; height: 40px;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-muted);
    flex-shrink: 0;
  }

  .agent-identity {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .agent-name { font-weight: 600; font-size: 14px; }

  .role-badge {
    display: inline-block;
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding: 2px 8px;
    border-radius: 12px;
    width: fit-content;
  }

  .agent-desc {
    font-size: 12px;
    color: var(--text-muted);
    line-height: 1.5;
  }

  .agent-models { display: flex; flex-direction: column; gap: 6px; }

  .model-row {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .model-label {
    font-size: 11px;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.4px;
    min-width: 52px;
  }

  .routing-tags {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 4px;
  }
  .routing-label {
    font-size: 11px;
    color: var(--text-muted);
    margin-right: 2px;
  }
  .routing-chip {
    background: rgba(56,189,248,0.1);
    color: var(--info);
    border-radius: var(--radius-sm);
    padding: 1px 6px;
    font-size: 10px;
    font-weight: 500;
  }

  .agent-stats {
    display: flex;
    gap: 20px;
    padding-top: 8px;
    border-top: 1px solid var(--border);
  }
  .stat-item { display: flex; flex-direction: column; gap: 2px; }
  .stat-label { font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-muted); }
  .stat-value { font-size: 15px; font-weight: 600; }

  .empty-state {
    text-align: center; padding: 60px; color: var(--text-muted);
  }
  .empty-icon { font-size: 40px; margin-bottom: 12px; }
</style>
