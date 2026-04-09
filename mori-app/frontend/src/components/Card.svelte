<script>
  export let padding = '20px'
  export let hoverable = false
</script>

<div class="card" class:hoverable style="padding: {padding}">
  <slot />
</div>

<style>
  .card {
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
  }
  .card.hoverable {
    cursor: pointer;
    transition: border-color 0.15s ease, background 0.15s ease;
  }
  .card.hoverable:hover {
    border-color: var(--accent);
    background: var(--bg-elevated);
  }
</style>
