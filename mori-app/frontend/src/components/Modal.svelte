<script>
  import { createEventDispatcher } from 'svelte'
  export let open = false
  export let title = ''

  const dispatch = createEventDispatcher()

  function close() {
    dispatch('close')
  }

  function handleKeydown(e) {
    if (e.key === 'Escape') close()
  }
</script>

<svelte:window on:keydown={handleKeydown} />

{#if open}
  <div class="overlay" on:click={close} role="dialog" aria-modal="true">
    <div class="modal" on:click|stopPropagation>
      <div class="modal-header">
        <h2>{title}</h2>
        <button class="close-btn" on:click={close} aria-label="Cerrar">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>
      <div class="modal-body">
        <slot />
      </div>
    </div>
  </div>
{/if}

<style>
  .overlay {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.7);
    z-index: 1000;
    display: flex;
    align-items: center;
    justify-content: center;
    animation: fadeIn 0.15s ease;
  }

  .modal {
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    width: 100%;
    max-width: 520px;
    max-height: 85vh;
    overflow-y: auto;
    animation: slideUp 0.15s ease;
  }

  .modal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 20px 24px 0;
    margin-bottom: 20px;
  }

  .modal-header h2 {
    font-size: 16px;
  }

  .close-btn {
    background: none;
    border: none;
    color: var(--text-muted);
    cursor: pointer;
    padding: 4px;
    border-radius: var(--radius-sm);
    display: flex;
    align-items: center;
  }
  .close-btn:hover { color: var(--text); background: var(--bg-elevated); }

  .modal-body {
    padding: 0 24px 24px;
  }

  @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
  @keyframes slideUp { from { transform: translateY(12px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
</style>
