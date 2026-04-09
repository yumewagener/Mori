<script>
  import { onMount } from 'svelte'
  import { api } from '../lib/api.js'
  import { addToast, token } from '../lib/stores.js'
  import Card from '../components/Card.svelte'
  import Button from '../components/Button.svelte'
  import TopBar from '../components/TopBar.svelte'

  let health = null
  let config = null
  let stats = null
  let loading = true
  let showTokenEdit = false
  let newToken = ''
  let savingToken = false

  async function load() {
    try {
      const [h, c, s] = await Promise.all([
        api.getHealth().catch(() => null),
        api.getConfig().catch(() => null),
        api.getStats().catch(() => null),
      ])
      health = h
      config = c
      stats = s
    } catch (e) {
      addToast('Error cargando sistema', 'error')
    } finally {
      loading = false
    }
  }

  function saveToken() {
    savingToken = true
    token.set(newToken)
    setTimeout(() => {
      savingToken = false
      showTokenEdit = false
      addToast('Token actualizado', 'success')
    }, 300)
  }

  function maskToken(t) {
    if (!t) return '(sin token)'
    if (t.length <= 8) return '•'.repeat(t.length)
    return t.slice(0, 4) + '•'.repeat(Math.max(0, t.length - 8)) + t.slice(-4)
  }

  $: currentToken = $token

  function isHealthy(h) {
    if (!h) return false
    return h.status === 'ok' || h.status === 'healthy' || h.healthy === true
  }

  onMount(load)
</script>

<div>
  <TopBar title="Sistema" subtitle="Estado y configuración de Mori" />

  {#if loading}
    <div class="loading-text">Cargando estado del sistema...</div>
  {:else}
    <div class="system-grid">
      <!-- Health card -->
      <Card>
        <div class="card-section">
          <div class="card-title">Estado de la API</div>
          <div class="health-status">
            <div class="health-dot" style="background: {health && isHealthy(health) ? 'var(--success)' : 'var(--danger)'}; box-shadow: 0 0 8px {health && isHealthy(health) ? 'var(--success)' : 'var(--danger)'}"></div>
            <span class="health-label" style="color: {health && isHealthy(health) ? 'var(--success)' : 'var(--danger)'}">
              {health && isHealthy(health) ? 'Operativo' : 'Sin conexión'}
            </span>
          </div>
          {#if health}
            <div class="health-details">
              {#each Object.entries(health).filter(([k]) => !['status', 'healthy'].includes(k)) as [k, v]}
                <div class="detail-row">
                  <span class="detail-key">{k}</span>
                  <span class="detail-val">{typeof v === 'object' ? JSON.stringify(v) : v}</span>
                </div>
              {/each}
            </div>
          {:else}
            <p class="no-data">No se pudo conectar con el backend</p>
          {/if}
        </div>
      </Card>

      <!-- Config card -->
      <Card>
        <div class="card-section">
          <div class="card-title">Configuración</div>
          {#if config}
            <div class="config-rows">
              {#each Object.entries(config).slice(0, 12) as [k, v]}
                <div class="detail-row">
                  <span class="detail-key">{k}</span>
                  <span class="detail-val mono">
                    {#if typeof v === 'object'}
                      {JSON.stringify(v).slice(0, 60)}
                    {:else}
                      {String(v)}
                    {/if}
                  </span>
                </div>
              {/each}
            </div>
          {:else}
            <p class="no-data">Configuración no disponible</p>
          {/if}
        </div>
      </Card>

      <!-- Stats card -->
      {#if stats}
        <Card>
          <div class="card-section">
            <div class="card-title">Estadísticas globales</div>
            <div class="stats-rows">
              <div class="stat-row">
                <span class="stat-label">Tareas totales</span>
                <span class="stat-val">{stats.total_tasks ?? '—'}</span>
              </div>
              <div class="stat-row">
                <span class="stat-label">Costo total</span>
                <span class="stat-val mono">{stats.total_cost != null ? '$' + Number(stats.total_cost).toFixed(4) : '—'}</span>
              </div>
              <div class="stat-row">
                <span class="stat-label">Tokens totales</span>
                <span class="stat-val mono">{stats.total_tokens != null ? (stats.total_tokens / 1000).toFixed(1) + 'K' : '—'}</span>
              </div>
              <div class="stat-row">
                <span class="stat-label">Modelos activos</span>
                <span class="stat-val">{stats.models_count ?? config?.models_count ?? '—'}</span>
              </div>
              <div class="stat-row">
                <span class="stat-label">Agentes activos</span>
                <span class="stat-val">{stats.agents_count ?? config?.agents_count ?? '—'}</span>
              </div>
            </div>
          </div>
        </Card>
      {/if}

      <!-- Token config card -->
      <Card>
        <div class="card-section">
          <div class="card-title">Token de autenticación</div>
          {#if !showTokenEdit}
            <div class="token-display">
              <code class="token-masked">{maskToken(currentToken)}</code>
              <Button size="sm" variant="secondary" on:click={() => { newToken = ''; showTokenEdit = true }}>
                Cambiar token
              </Button>
            </div>
            {#if !currentToken}
              <p class="no-token-warn">⚠ Sin token — las peticiones van sin autenticación</p>
            {/if}
          {:else}
            <div class="token-form">
              <input
                type="password"
                bind:value={newToken}
                placeholder="Nuevo token de API..."
                autocomplete="off"
              />
              <div class="token-actions">
                <Button variant="secondary" size="sm" on:click={() => showTokenEdit = false}>Cancelar</Button>
                <Button size="sm" loading={savingToken} on:click={saveToken}>Guardar</Button>
              </div>
            </div>
          {/if}
        </div>
      </Card>
    </div>
  {/if}
</div>

<style>
  .loading-text { color: var(--text-muted); padding: 40px; text-align: center; }

  .system-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
    gap: 16px;
  }

  .card-section { display: flex; flex-direction: column; gap: 14px; }
  .card-title {
    font-size: 11px; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.5px;
    color: var(--text-muted);
  }

  .health-status {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .health-dot {
    width: 12px; height: 12px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .health-label { font-size: 16px; font-weight: 600; }

  .health-details, .config-rows {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .detail-row {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 12px;
    font-size: 12px;
    border-bottom: 1px solid var(--border);
    padding-bottom: 6px;
  }
  .detail-row:last-child { border-bottom: none; padding-bottom: 0; }
  .detail-key { color: var(--text-muted); flex-shrink: 0; }
  .detail-val { font-family: var(--font-mono); font-size: 11px; text-align: right; word-break: break-all; }
  .mono { font-family: var(--font-mono); }

  .stats-rows { display: flex; flex-direction: column; gap: 10px; }
  .stat-row { display: flex; justify-content: space-between; align-items: center; font-size: 13px; }
  .stat-label { color: var(--text-muted); }
  .stat-val { font-weight: 600; }

  .no-data { font-size: 12px; color: var(--text-muted); font-style: italic; }

  .token-display {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .token-masked {
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 6px 12px;
    font-size: 12px;
    font-family: var(--font-mono);
    color: var(--text-muted);
    flex: 1;
    letter-spacing: 2px;
  }

  .no-token-warn {
    font-size: 12px;
    color: var(--warning);
  }

  .token-form { display: flex; flex-direction: column; gap: 10px; }
  .token-actions { display: flex; gap: 8px; justify-content: flex-end; }
</style>
