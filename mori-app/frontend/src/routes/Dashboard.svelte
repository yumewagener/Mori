<script>
  import { onMount, onDestroy } from 'svelte'
  import { api } from '../lib/api.js'
  import { addToast } from '../lib/stores.js'
  import StatusBadge from '../components/StatusBadge.svelte'
  import ModelBadge from '../components/ModelBadge.svelte'
  import Card from '../components/Card.svelte'
  import Button from '../components/Button.svelte'
  import Modal from '../components/Modal.svelte'
  import TopBar from '../components/TopBar.svelte'

  let statsData = null
  let recentTasks = []
  let activeTasks = []
  let loading = true
  let showNewTask = false
  let creating = false

  let newTask = { title: '', description: '', priority: 'normal', area: '' }

  let interval

  async function loadData() {
    try {
      const [s, recent, active] = await Promise.all([
        api.getStats().catch(() => null),
        api.getTasks({ limit: 10 }).catch(() => []),
        api.getTasks({ status: 'en_progreso', limit: 5 }).catch(() => []),
      ])
      statsData = s
      recentTasks = Array.isArray(recent) ? recent : (recent?.tasks || [])
      activeTasks = Array.isArray(active) ? active : (active?.tasks || [])
    } catch (e) {
      addToast('Error cargando dashboard', 'error')
    } finally {
      loading = false
    }
  }

  async function createTask() {
    if (!newTask.title.trim()) return
    creating = true
    try {
      await api.createTask(newTask)
      showNewTask = false
      newTask = { title: '', description: '', priority: 'normal', area: '' }
      addToast('Tarea creada', 'success')
      await loadData()
    } catch (e) {
      addToast('Error creando tarea: ' + e.message, 'error')
    } finally {
      creating = false
    }
  }

  onMount(() => {
    loadData()
    interval = setInterval(loadData, 10000)
  })

  onDestroy(() => clearInterval(interval))

  function formatCost(v) {
    if (v == null) return '—'
    return '$' + Number(v).toFixed(4)
  }

  function formatDuration(ms) {
    if (!ms) return '—'
    const s = Math.round(ms / 1000)
    if (s < 60) return s + 's'
    return Math.floor(s / 60) + 'm ' + (s % 60) + 's'
  }
</script>

<div>
  <TopBar title="Dashboard" subtitle="Vista general del sistema Mori">
    <Button on:click={() => showNewTask = true}>+ Nueva tarea</Button>
  </TopBar>

  {#if loading}
    <div class="skeleton-grid">
      {#each [1,2,3,4] as _}
        <div class="skeleton-card"></div>
      {/each}
    </div>
  {:else}
    <!-- Stats row -->
    <div class="stats-grid">
      <Card>
        <div class="stat-label">Tareas hoy</div>
        <div class="stat-value">{statsData?.tasks_today ?? '—'}</div>
      </Card>
      <Card>
        <div class="stat-label">Costo hoy</div>
        <div class="stat-value">{formatCost(statsData?.cost_today)}</div>
      </Card>
      <Card>
        <div class="stat-label">En ejecución</div>
        <div class="stat-value" style="color: var(--info)">{activeTasks.length}</div>
      </Card>
      <Card>
        <div class="stat-label">Tasa de éxito</div>
        <div class="stat-value" style="color: var(--success)">
          {statsData?.success_rate != null ? Math.round(statsData.success_rate * 100) + '%' : '—'}
        </div>
      </Card>
    </div>

    <!-- Active runs -->
    {#if activeTasks.length > 0}
      <div class="section">
        <h2 class="section-title">Ejecuciones activas</h2>
        <div class="active-tasks">
          {#each activeTasks as task}
            <div class="active-task-row">
              <div class="pulse-dot"></div>
              <span class="task-title">{task.title}</span>
              {#if task.agent}<span class="meta">{task.agent}</span>{/if}
              {#if task.model}<ModelBadge modelId={task.model} />{/if}
              <a href="/tasks/{task.id}/run" class="run-link">Ver →</a>
            </div>
          {/each}
        </div>
      </div>
    {/if}

    <!-- Recent tasks table -->
    <div class="section">
      <h2 class="section-title">Tareas recientes</h2>
      {#if recentTasks.length === 0}
        <div class="empty-state">No hay tareas todavía</div>
      {:else}
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Estado</th>
                <th>Título</th>
                <th>Agente</th>
                <th>Modelo</th>
                <th>Costo</th>
                <th>Duración</th>
              </tr>
            </thead>
            <tbody>
              {#each recentTasks as task}
                <tr>
                  <td><StatusBadge status={task.status} /></td>
                  <td class="task-name">{task.title}</td>
                  <td class="meta">{task.agent || '—'}</td>
                  <td>{#if task.model}<ModelBadge modelId={task.model} />{:else}—{/if}</td>
                  <td class="mono">{formatCost(task.cost)}</td>
                  <td class="mono">{formatDuration(task.duration_ms)}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {/if}
    </div>
  {/if}
</div>

<!-- New task modal -->
<Modal open={showNewTask} title="Nueva tarea" on:close={() => showNewTask = false}>
  <div class="form-group">
    <label>Título</label>
    <input bind:value={newTask.title} placeholder="Describe la tarea..." />
  </div>
  <div class="form-group">
    <label>Descripción</label>
    <textarea bind:value={newTask.description} rows="3" placeholder="Detalles adicionales..."></textarea>
  </div>
  <div class="form-row">
    <div class="form-group">
      <label>Prioridad</label>
      <select bind:value={newTask.priority}>
        <option value="baja">Baja</option>
        <option value="normal">Normal</option>
        <option value="alta">Alta</option>
        <option value="critica">Crítica</option>
      </select>
    </div>
    <div class="form-group">
      <label>Área</label>
      <input bind:value={newTask.area} placeholder="dev, research..." />
    </div>
  </div>
  <div class="modal-actions">
    <Button variant="secondary" on:click={() => showNewTask = false}>Cancelar</Button>
    <Button loading={creating} on:click={createTask}>Crear tarea</Button>
  </div>
</Modal>

<style>
  .skeleton-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    margin-bottom: 24px;
  }
  .skeleton-card {
    height: 80px;
    background: var(--bg-surface);
    border-radius: var(--radius);
    animation: pulse 1.5s ease infinite;
  }
  @keyframes pulse { 0%,100% { opacity:1 } 50% { opacity: 0.5 } }

  .stats-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    margin-bottom: 28px;
  }
  .stat-label {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--text-muted);
    margin-bottom: 8px;
  }
  .stat-value {
    font-size: 28px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }

  .section { margin-bottom: 28px; }
  .section-title { font-size: 14px; font-weight: 600; margin-bottom: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; }

  .active-tasks {
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
  }
  .active-task-row {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 16px;
    border-bottom: 1px solid var(--border);
  }
  .active-task-row:last-child { border-bottom: none; }
  .pulse-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    background: var(--info);
    animation: pulse-glow 1.5s ease infinite;
    flex-shrink: 0;
  }
  @keyframes pulse-glow { 0%,100% { box-shadow: 0 0 0 0 rgba(56,189,248,0.4) } 50% { box-shadow: 0 0 0 6px rgba(56,189,248,0) } }
  .task-title { font-weight: 500; flex: 1; }
  .meta { font-size: 12px; color: var(--text-muted); }
  .run-link { font-size: 12px; color: var(--accent); margin-left: auto; }

  .table-wrap {
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: auto;
  }
  table { width: 100%; border-collapse: collapse; }
  thead tr { border-bottom: 1px solid var(--border); }
  th {
    text-align: left;
    padding: 10px 14px;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--text-muted);
    font-weight: 500;
  }
  td {
    padding: 10px 14px;
    font-size: 13px;
    border-bottom: 1px solid var(--border);
  }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: var(--bg-elevated); }
  .task-name { font-weight: 500; max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .mono { font-family: var(--font-mono); font-size: 12px; }

  .empty-state {
    text-align: center;
    padding: 40px;
    color: var(--text-muted);
    font-size: 14px;
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
  }

  .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  .modal-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 20px; }
  textarea { resize: vertical; }
</style>
