<script>
  import { onMount } from 'svelte'
  import { api } from '../lib/api.js'
  import { addToast } from '../lib/stores.js'
  import ModelBadge from '../components/ModelBadge.svelte'
  import TopBar from '../components/TopBar.svelte'

  let modelList = []
  let loading = true
  let activeTab = 'catalog'

  async function load() {
    try {
      const res = await api.getModels()
      modelList = Array.isArray(res) ? res : (res?.models || [])
    } catch (e) {
      addToast('Error cargando modelos', 'error')
    } finally {
      loading = false
    }
  }

  function getProvider(id) {
    const s = (id || '').toLowerCase()
    if (s.includes('claude') || s.includes('anthropic')) return 'anthropic'
    if (s.includes('gpt') || s.includes('openai') || s.startsWith('o1') || s.startsWith('o3') || s.startsWith('o4')) return 'openai'
    if (s.includes('gemini') || s.includes('google')) return 'google'
    if (s.includes('llama') || s.includes('mistral') || s.includes('qwen') || s.includes(':')) return 'ollama'
    return 'unknown'
  }

  function formatCost(v) {
    if (v == null) return '—'
    if (v === 0) return 'Local'
    return '$' + Number(v).toFixed(4)
  }

  function isConfigured(model) {
    return model.configured !== false && model.status !== 'missing_key'
  }

  onMount(load)
</script>

<div>
  <TopBar title="Modelos" subtitle="Catálogo y estadísticas de modelos LLM" />

  <div class="tab-bar">
    <button class="tab-btn" class:active={activeTab === 'catalog'} on:click={() => activeTab = 'catalog'}>
      Catálogo
    </button>
    <button class="tab-btn" class:active={activeTab === 'stats'} on:click={() => activeTab = 'stats'}>
      Estadísticas
    </button>
  </div>

  {#if loading}
    <div class="loading-text">Cargando modelos...</div>
  {:else if activeTab === 'catalog'}
    {#if modelList.length === 0}
      <div class="empty-state">No hay modelos configurados</div>
    {:else}
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Proveedor</th>
              <th>Modelo</th>
              <th>Capacidades</th>
              <th>Tool calling</th>
              <th>Costo / 1K in</th>
              <th>Costo / 1K out</th>
              <th>Estado</th>
            </tr>
          </thead>
          <tbody>
            {#each modelList as model}
              <tr>
                <td>
                  <span class="provider-label provider-{getProvider(model.id || model.model_id)}">
                    {getProvider(model.id || model.model_id)}
                  </span>
                </td>
                <td><ModelBadge modelId={model.id || model.model_id} /></td>
                <td>
                  <div class="caps">
                    {#if model.capabilities}
                      {#each (Array.isArray(model.capabilities) ? model.capabilities : [model.capabilities]) as cap}
                        <span class="cap-chip">{cap}</span>
                      {/each}
                    {:else}
                      <span class="cap-chip">text</span>
                    {/if}
                  </div>
                </td>
                <td>
                  <span class="check" style="color: {model.tool_calling ? 'var(--success)' : 'var(--border)'}">
                    {model.tool_calling ? '✓' : '—'}
                  </span>
                </td>
                <td class="mono">
                  {#if getProvider(model.id || model.model_id) === 'ollama'}
                    <span class="local-badge">Local</span>
                  {:else}
                    {formatCost(model.cost_per_1k_input || model.input_cost)}
                  {/if}
                </td>
                <td class="mono">
                  {#if getProvider(model.id || model.model_id) === 'ollama'}
                    <span class="local-badge">Local</span>
                  {:else}
                    {formatCost(model.cost_per_1k_output || model.output_cost)}
                  {/if}
                </td>
                <td>
                  <span class="status-indicator" style="color: {isConfigured(model) ? 'var(--success)' : 'var(--danger)'}">
                    {isConfigured(model) ? '● Configurado' : '● Sin API key'}
                  </span>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}

  {:else}
    <!-- Stats tab -->
    {#if modelList.length === 0}
      <div class="empty-state">No hay estadísticas disponibles</div>
    {:else}
      <div class="stats-grid">
        {#each modelList as model}
          <div class="stat-card">
            <div class="stat-card-header">
              <ModelBadge modelId={model.id || model.model_id} />
            </div>
            <div class="stat-rows">
              <div class="stat-row">
                <span class="stat-label">Costo total</span>
                <span class="stat-val mono">{formatCost(model.stats?.total_cost)}</span>
              </div>
              <div class="stat-row">
                <span class="stat-label">Tokens totales</span>
                <span class="stat-val mono">{model.stats?.total_tokens != null ? (model.stats.total_tokens / 1000).toFixed(1) + 'K' : '—'}</span>
              </div>
              <div class="stat-row">
                <span class="stat-label">Ejecuciones</span>
                <span class="stat-val">{model.stats?.runs_count ?? '—'}</span>
              </div>
              <div class="stat-row">
                <span class="stat-label">Tiempo promedio</span>
                <span class="stat-val mono">{model.stats?.avg_response_time_ms != null ? (model.stats.avg_response_time_ms / 1000).toFixed(1) + 's' : '—'}</span>
              </div>
            </div>
          </div>
        {/each}
      </div>
    {/if}
  {/if}
</div>

<style>
  .tab-bar {
    display: flex;
    gap: 4px;
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 4px;
    width: fit-content;
    margin-bottom: 20px;
  }
  .tab-btn {
    background: none; border: none;
    color: var(--text-muted);
    padding: 6px 16px;
    border-radius: var(--radius-sm);
    font-size: 13px; font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
  }
  .tab-btn.active { background: var(--bg-elevated); color: var(--text); }

  .loading-text { color: var(--text-muted); padding: 40px; text-align: center; }

  .empty-state {
    text-align: center; padding: 40px;
    color: var(--text-muted);
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
  }

  .table-wrap {
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: auto;
  }
  table { width: 100%; border-collapse: collapse; }
  thead tr { border-bottom: 1px solid var(--border); }
  th { padding: 10px 14px; text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-muted); font-weight: 500; }
  td { padding: 10px 14px; font-size: 13px; border-bottom: 1px solid var(--border); vertical-align: middle; }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: var(--bg-elevated); }
  .mono { font-family: var(--font-mono); font-size: 12px; }

  .provider-label {
    font-size: 11px; font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding: 2px 8px;
    border-radius: 12px;
  }
  .provider-anthropic { color: #a259ff; background: rgba(162,89,255,0.12); }
  .provider-openai { color: var(--success); background: rgba(34,197,94,0.12); }
  .provider-google { color: var(--info); background: rgba(56,189,248,0.12); }
  .provider-ollama { color: var(--warning); background: rgba(245,158,11,0.12); }
  .provider-unknown { color: var(--text-muted); background: var(--bg-elevated); }

  .caps { display: flex; flex-wrap: wrap; gap: 4px; }
  .cap-chip {
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 1px 6px;
    font-size: 10px;
    color: var(--text-muted);
  }

  .check { font-size: 15px; font-weight: 700; }

  .local-badge {
    background: rgba(245,158,11,0.12);
    color: var(--warning);
    border-radius: var(--radius-sm);
    padding: 1px 6px;
    font-size: 11px;
    font-weight: 600;
  }

  .status-indicator { font-size: 12px; font-weight: 500; }

  .stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 16px;
  }

  .stat-card {
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 16px;
  }

  .stat-card-header { margin-bottom: 14px; }

  .stat-rows { display: flex; flex-direction: column; gap: 8px; }

  .stat-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 12px;
  }
  .stat-label { color: var(--text-muted); }
  .stat-val { font-weight: 500; }
</style>
