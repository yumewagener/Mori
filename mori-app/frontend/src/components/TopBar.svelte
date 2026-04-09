<script>
  export let title = ''
  export let subtitle = ''
</script>

<div class="topbar">
  <div>
    <h1 class="topbar-title">{title}</h1>
    {#if subtitle}
      <p class="topbar-subtitle">{subtitle}</p>
    {/if}
  </div>
  <slot />
</div>

<style>
  .topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 24px;
  }
  .topbar-title { font-size: 20px; font-weight: 600; }
  .topbar-subtitle { font-size: 13px; color: var(--text-muted); margin-top: 2px; }
</style>
