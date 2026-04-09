<script>
  import { onMount } from 'svelte'
  import { api } from '../lib/api.js'
  import { addToast } from '../lib/stores.js'
  import TaskCard from '../components/TaskCard.svelte'
  import Button from '../components/Button.svelte'
  import Modal from '../components/Modal.svelte'
  import TopBar from '../components/TopBar.svelte'

  let allTasks = []
  let loading = true
  let showNewTask = false
  let creating = false
  let searchQ = ''
  let filterStatus = ''
  let filterArea = ''
  let projects = []
  let pipelines = []
  let agents = []

  let newTask = {
    title: '', description: '', tags: '', area: '',
    priority: 'normal', project: '', pipeline: '', agent: ''
  }

  const columns = [
    { key: 'pendiente', label: 'Pendiente', color: 'var(--text-muted)' },
    { key: 'en_progreso', label: 'En progreso', color: 'var(--info)' },
    { key: 'completada', label: 'Completada', color: 'var(--success)' },
    { key: 'bloqueada', label: 'Bloqueada', color: 'var(--danger)' },
  ]

  async function loadData() {
    try {
      const params = {}
      if (searchQ) params.search = searchQ
      if (filterStatus) params.status = filterStatus
      if (filterArea) params.area = filterArea

      const [taskRes, projRes, pipeRes, agentRes] = await Promise.all([
        api.getTasks(params).catch(() => []),
        api.getProjects().catch(() => []),
        api.getPipelines().catch(() => []),
        api.getAgents().catch(() => []),
      ])

      allTasks = Array.isArray(taskRes) ? taskRes : (taskRes?.tasks || [])
      projects = Array.isArray(projRes) ? projRes : (projRes?.projects || [])
      pipelines = Array.isArray(pipeRes) ? pipeRes : (pipeRes?.pipelines || [])
      agents = Array.isArray(agentRes) ? agentRes : (agentRes?.agents || [])
    } catch (e) {
      addToast('Error cargando tareas', 'error')
    } finally {
      loading = false
    }
  }

  function tasksByStatus(status) {
    return allTasks.filter(t => t.status === status)
  }

  async function moveTask(task, newStatus) {
    try {
      await api.updateTask(task.id, { status: newStatus })
      task.status = newStatus
      allTasks = [...allTasks]
    } catch (e) {
      addToast('Error actualizando tarea', 'error')
    }
  }

  async function createTask() {
    if (!newTask.title.trim()) return
    creating = true
    try {
      const payload = { ...newTask }
      if (payload.tags) payload.tags = payload.tags.split(',').map(t => t.trim()).filter(Boolean)
      await api.createTask(payload)
      showNewTask = false
      newTask = { title: '', description: '', tags: '', area: '', priority: 'normal', project: '', pipeline: '', agent: '' }
      addToast('Tarea creada', 'success')
      await loadData()
    } catch (e) {
      addToast('Error creando tarea: ' + e.message, 'error')
    } finally {
      creating = false
    }
  }

  let searchTimer
  function onSearch() {
    clearTimeout(searchTimer)
    searchTimer = setTimeout(loadData, 400)
  }

  // Drag & drop
  let dragTask = null

  function onDragStart(task) {
    dragTask = task
  }

  function onDrop(status) {
    if (dragTask && dragTask.status !== status) {
      moveTask(dragTask, status)
    }
    dragTask = null
  }

  onMount(loadData)
</script>

<div>
  <TopBar title="Tareas" subtitle="Tablero kanban">
    <Button on:click={() => showNewTask = true}>+ Nueva tarea</Button>
  </TopBar>

  <!-- Filter bar -->
  <div class="filter-bar">
    <div class="search-wrap">
      <svg class="search-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
      <input
        class="search-input"
        type="text"
        placeholder="Buscar tareas..."
        bind:value={searchQ}
        on:input={onSearch}
      />
    </div>
    <select bind:value={filterStatus} on:change={loadData} class="filter-select">
      <option value="">Todos los estados</option>
      <option value="pendiente">Pendiente</option>
      <option value="en_progreso">En progreso</option>
      <option value="completada">Completada</option>
      <option value="bloqueada">Bloqueada</option>
    </select>
    <input
      class="filter-input"
      type="text"
      placeholder="Filtrar por área..."
      bind:value={filterArea}
      on:input={onSearch}
    />
  </div>

  {#if loading}
    <div class="loading-text">Cargando tareas...</div>
  {:else}
    <div class="kanban">
      {#each columns as col}
        <div
          class="kanban-col"
          on:dragover|preventDefault
          on:drop={() => onDrop(col.key)}
        >
          <div class="col-header">
            <span class="col-dot" style="background: {col.color}"></span>
            <span class="col-label">{col.label}</span>
            <span class="col-count">{tasksByStatus(col.key).length}</span>
          </div>
          <div class="col-body">
            {#each tasksByStatus(col.key) as task (task.id)}
              <div
                draggable="true"
                on:dragstart={() => onDragStart(task)}
              >
                <TaskCard {task} />
              </div>
            {/each}
            {#if tasksByStatus(col.key).length === 0}
              <div class="col-empty">No hay tareas</div>
            {/if}
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<!-- New task modal -->
<Modal open={showNewTask} title="Nueva tarea" on:close={() => showNewTask = false}>
  <div class="form-group">
    <label>Título *</label>
    <input bind:value={newTask.title} placeholder="Título de la tarea..." />
  </div>
  <div class="form-group">
    <label>Descripción</label>
    <textarea bind:value={newTask.description} rows="3" placeholder="Descripción detallada..."></textarea>
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
      <input bind:value={newTask.area} placeholder="dev, research, ops..." />
    </div>
  </div>
  <div class="form-group">
    <label>Tags (separados por comas)</label>
    <input bind:value={newTask.tags} placeholder="tag1, tag2, tag3" />
  </div>
  <div class="form-row">
    <div class="form-group">
      <label>Proyecto</label>
      <select bind:value={newTask.project}>
        <option value="">Sin proyecto</option>
        {#each projects as p}
          <option value={p.id}>{p.name}</option>
        {/each}
      </select>
    </div>
    <div class="form-group">
      <label>Pipeline</label>
      <select bind:value={newTask.pipeline}>
        <option value="">Sin pipeline</option>
        {#each pipelines as p}
          <option value={p.id}>{p.name}</option>
        {/each}
      </select>
    </div>
  </div>
  <div class="form-group">
    <label>Agente</label>
    <select bind:value={newTask.agent}>
      <option value="">Auto-selección</option>
      {#each agents as a}
        <option value={a.id}>{a.name} ({a.role})</option>
      {/each}
    </select>
  </div>
  <div class="modal-actions">
    <Button variant="secondary" on:click={() => showNewTask = false}>Cancelar</Button>
    <Button loading={creating} on:click={createTask}>Crear tarea</Button>
  </div>
</Modal>

<style>
  .filter-bar {
    display: flex;
    gap: 10px;
    margin-bottom: 20px;
    align-items: center;
  }
  .search-wrap {
    position: relative;
    flex: 1;
    max-width: 320px;
  }
  .search-icon {
    position: absolute;
    left: 10px;
    top: 50%;
    transform: translateY(-50%);
    color: var(--text-muted);
    pointer-events: none;
  }
  .search-input {
    padding-left: 32px !important;
  }
  .filter-select, .filter-input {
    width: auto;
    min-width: 160px;
  }

  .kanban {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    align-items: start;
  }

  .kanban-col {
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    min-height: 400px;
  }

  .col-header {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 12px 14px;
    border-bottom: 1px solid var(--border);
  }

  .col-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .col-label {
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--text-muted);
    flex: 1;
  }

  .col-count {
    background: var(--bg-elevated);
    color: var(--text-muted);
    border-radius: 10px;
    padding: 1px 7px;
    font-size: 11px;
    font-weight: 600;
  }

  .col-body {
    padding: 10px;
  }

  .col-empty {
    text-align: center;
    padding: 24px 12px;
    color: var(--text-muted);
    font-size: 12px;
  }

  .loading-text { color: var(--text-muted); padding: 40px; text-align: center; }

  .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  .modal-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 20px; }
  textarea { resize: vertical; }
</style>
