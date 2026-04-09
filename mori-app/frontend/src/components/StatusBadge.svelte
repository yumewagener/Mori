<script>
  export let status = 'pendiente'
  const colors = {
    pendiente: 'var(--text-muted)',
    en_progreso: 'var(--info)',
    completada: 'var(--success)',
    bloqueada: 'var(--danger)',
    cancelada: 'var(--text-muted)',
    running: 'var(--info)',
    completed: 'var(--success)',
    failed: 'var(--danger)',
    pending: 'var(--text-muted)',
  }
  const labels = {
    pendiente: 'Pendiente',
    en_progreso: 'En progreso',
    completada: 'Completada',
    bloqueada: 'Bloqueada',
    cancelada: 'Cancelada',
    running: 'Ejecutando',
    completed: 'Completada',
    failed: 'Fallida',
    pending: 'Pendiente',
  }
</script>
<span class="badge" style="color: {colors[status] || 'var(--text-muted)'}; border-color: {colors[status] || 'var(--border)'}">
  {labels[status] || status}
</span>
<style>
  .badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 12px;
    border: 1px solid;
    font-size: 11px;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
</style>
