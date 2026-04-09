<script>
  export let color = 'var(--text-muted)'
  export let bg = 'rgba(255,255,255,0.06)'
</script>

<span class="badge" style="color: {color}; background: {bg};">
  <slot />
</span>

<style>
  .badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.4px;
  }
</style>
