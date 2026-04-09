<script>
  import StatusBadge from './StatusBadge.svelte'
  import ModelBadge from './ModelBadge.svelte'

  export let task = {}

  const priorityColors = {
    baja: '#8888aa',
    normal: 'var(--info)',
    alta: 'var(--warning)',
    critica: 'var(--danger)',
  }

  $: tags = Array.isArray(task.tags)
    ? task.tags
    : (typeof task.tags === 'string' && task.tags ? task.tags.split(',').map(t => t.trim()).filter(Boolean) : [])
</script>

<div class="task-card" on:click on:keypress role="button" tabindex="0">
  <div class="card-header">
    <span class="priority-dot" style="background: {priorityColors[task.priority] || 'var(--text-muted)'}"></span>
    <StatusBadge status={task.status} />
  </div>

  <p class="task-title">{task.title || 'Sin título'}</p>

  {#if tags.length > 0}
    <div class="tags">
      {#each tags.slice(0, 3) as tag}
        <span class="tag">{tag}</span>
      {/each}
      {#if tags.length > 3}
        <span class="tag tag-more">+{tags.length - 3}</span>
      {/if}
    </div>
  {/if}

  <div class="card-footer">
    {#if task.agent}
      <span class="agent-label">
        <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="8" r="4"/><path d="M20 21a8 8 0 10-16 0"/></svg>
        {task.agent}
      </span>
    {/if}
    {#if task.model}
      <ModelBadge modelId={task.model} />
    {/if}
    {#if task.has_run || task.latest_run_id}
      <a href="/tasks/{task.id}/run" on:click|stopPropagation>
        <span class="run-link">▶ Ver ejecución</span>
      </a>
    {/if}
  </div>
</div>

<style>
  .task-card {
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 12px;
    cursor: pointer;
    transition: border-color 0.15s ease;
    margin-bottom: 8px;
  }
  .task-card:hover { border-color: var(--accent); }

  .card-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
  }

  .priority-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .task-title {
    font-size: 13px;
    font-weight: 500;
    color: var(--text);
    margin-bottom: 8px;
    line-height: 1.4;
  }

  .tags {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-bottom: 8px;
  }

  .tag {
    background: rgba(124,106,255,0.1);
    color: var(--accent);
    border-radius: var(--radius-sm);
    padding: 1px 6px;
    font-size: 10px;
    font-weight: 500;
  }

  .tag-more { background: var(--bg-surface); color: var(--text-muted); }

  .card-footer {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    margin-top: 4px;
  }

  .agent-label {
    font-size: 11px;
    color: var(--text-muted);
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .run-link {
    font-size: 11px;
    color: var(--accent);
    font-weight: 500;
  }
</style>
