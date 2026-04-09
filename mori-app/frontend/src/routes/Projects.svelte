<script>
  import { onMount } from 'svelte'
  import { api } from '../lib/api.js'
  import { addToast } from '../lib/stores.js'
  import Card from '../components/Card.svelte'
  import Button from '../components/Button.svelte'
  import Modal from '../components/Modal.svelte'
  import TopBar from '../components/TopBar.svelte'
  import StatusBadge from '../components/StatusBadge.svelte'

  let projectList = []
  let loading = true
  let showNewProject = false
  let creating = false
  let selectedProject = null
  let projectTasks = []
  let loadingTasks = false

  let newProject = { name: '', description: '', area: '' }

  async function loadProjects() {
    try {
      const res = await api.getProjects()
      projectList = Array.isArray(res) ? res : (res?.projects || [])
    } catch (e) {
      addToast('Error cargando proyectos', 'error')
    } finally {
      loading = false
    }
  }

  async function selectProject(p) {
    selectedProject = p
    loadingTasks = true
    try {
      const res = await api.getProjectTasks(p.id)
      projectTasks = Array.isArray(res) ? res : (res?.tasks || [])
    } catch (e) {
      addToast('Error cargando tareas del proyecto', 'error')
      projectTasks = []
    } finally {
      loadingTasks = false
    }
  }

  async function createProject() {
    if (!newProject.name.trim()) return
    creating = true
    try {
      await api.createProject(newProject)
      showNewProject = false
      newProject = { name: '', description: '', area: '' }
      addToast('Proyecto creado', 'success')
      await loadProjects()
    } catch (e) {
      addToast('Error creando proyecto', 'error')
    } finally {
      creating = false
    }
  }

  onMount(loadProjects)

  const areaColors = {
    dev: 'var(--accent)',
    research: 'var(--info)',
    ops: 'var(--warning)',
    marketing: 'var(--success)',
  }
</script>

<div>
  <TopBar title="Proyectos" subtitle="Organización por proyectos">
    <Button on:click={() => showNewProject = true}>+ Nuevo proyecto</Button>
  </TopBar>

  {#if loading}
    <div class="projects-grid skeleton-grid">
      {#each [1,2,3,4] as _}
        <div class="skeleton-card"></div>
      {/each}
    </div>
  {:else if projectList.length === 0}
    <div class="empty-state">
      <div class="empty-icon">📁</div>
      <p>No hay proyectos todavía</p>
      <Button on:click={() => showNewProject = true}>Crear primer proyecto</Button>
    </div>
  {:else}
    <div class="projects-grid">
      {#each projectList as project}
        <div class="project-card" on:click={() => selectProject(project)} role="button" tabindex="0">
          <div class="project-header">
            <span class="project-name">{project.name}</span>
            {#if project.area}
              <span class="area-badge" style="color: {areaColors[project.area] || 'var(--text-muted)'}">
                {project.area}
              </span>
            {/if}
          </div>
          {#if project.description}
            <p class="project-desc">{project.description}</p>
          {/if}
          <div class="project-stats">
            <span class="task-count">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
              {project.task_count || 0} tareas
            </span>
            {#if project.pending_count != null}
              <span class="pending-count">{project.pending_count} pendientes</span>
            {/if}
          </div>
        </div>
      {/each}
    </div>
  {/if}

  <!-- Project tasks panel -->
  {#if selectedProject}
    <div class="tasks-panel">
      <div class="panel-header">
        <h2>{selectedProject.name} — Tareas</h2>
        <button class="close-panel" on:click={() => selectedProject = null}>✕</button>
      </div>
      {#if loadingTasks}
        <div class="loading-text">Cargando...</div>
      {:else if projectTasks.length === 0}
        <div class="empty-state-sm">No hay tareas en este proyecto</div>
      {:else}
        <table>
          <thead>
            <tr><th>Estado</th><th>Título</th><th>Prioridad</th></tr>
          </thead>
          <tbody>
            {#each projectTasks as t}
              <tr>
                <td><StatusBadge status={t.status} /></td>
                <td>{t.title}</td>
                <td><span class="priority">{t.priority || '—'}</span></td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}
    </div>
  {/if}
</div>

<Modal open={showNewProject} title="Nuevo proyecto" on:close={() => showNewProject = false}>
  <div class="form-group">
    <label>Nombre *</label>
    <input bind:value={newProject.name} placeholder="Nombre del proyecto..." />
  </div>
  <div class="form-group">
    <label>Descripción</label>
    <textarea bind:value={newProject.description} rows="2" placeholder="Descripción opcional..."></textarea>
  </div>
  <div class="form-group">
    <label>Área</label>
    <select bind:value={newProject.area}>
      <option value="">Sin área</option>
      <option value="dev">Dev</option>
      <option value="research">Research</option>
      <option value="ops">Ops</option>
      <option value="marketing">Marketing</option>
    </select>
  </div>
  <div class="modal-actions">
    <Button variant="secondary" on:click={() => showNewProject = false}>Cancelar</Button>
    <Button loading={creating} on:click={createProject}>Crear</Button>
  </div>
</Modal>

<style>
  .projects-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 16px;
    margin-bottom: 24px;
  }
  .skeleton-grid {}
  .skeleton-card {
    height: 120px;
    background: var(--bg-surface);
    border-radius: var(--radius);
    border: 1px solid var(--border);
    animation: pulse 1.5s ease infinite;
  }
  @keyframes pulse { 0%,100%{opacity:1}50%{opacity:0.5} }

  .project-card {
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 18px;
    cursor: pointer;
    transition: border-color 0.15s ease;
  }
  .project-card:hover { border-color: var(--accent); }

  .project-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 8px;
  }

  .project-name { font-weight: 600; font-size: 14px; }

  .area-badge {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    background: rgba(255,255,255,0.06);
    padding: 2px 8px;
    border-radius: 12px;
    flex-shrink: 0;
  }

  .project-desc {
    font-size: 12px;
    color: var(--text-muted);
    margin-bottom: 12px;
    line-height: 1.4;
  }

  .project-stats {
    display: flex;
    gap: 12px;
    font-size: 12px;
    color: var(--text-muted);
  }

  .task-count, .pending-count {
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .empty-state {
    text-align: center;
    padding: 60px;
    color: var(--text-muted);
  }
  .empty-icon { font-size: 40px; margin-bottom: 12px; }
  .empty-state p { margin-bottom: 16px; }

  .tasks-panel {
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    margin-top: 16px;
    overflow: hidden;
  }

  .panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 18px;
    border-bottom: 1px solid var(--border);
  }

  .close-panel {
    background: none; border: none;
    color: var(--text-muted); cursor: pointer;
    font-size: 16px; padding: 4px;
  }
  .close-panel:hover { color: var(--text); }

  .loading-text, .empty-state-sm {
    padding: 24px; text-align: center; color: var(--text-muted);
  }

  table { width: 100%; border-collapse: collapse; }
  thead tr { border-bottom: 1px solid var(--border); }
  th { padding: 10px 16px; text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-muted); }
  td { padding: 10px 16px; font-size: 13px; border-bottom: 1px solid var(--border); }
  tr:last-child td { border-bottom: none; }
  .priority { font-size: 11px; color: var(--text-muted); text-transform: capitalize; }

  .modal-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 20px; }
  textarea { resize: vertical; }
</style>
