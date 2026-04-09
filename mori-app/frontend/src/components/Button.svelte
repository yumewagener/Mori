<script>
  export let variant = 'primary'  // primary | secondary | danger | ghost
  export let size = 'md'          // sm | md
  export let loading = false
  export let disabled = false
  export let type = 'button'
</script>

<button
  {type}
  class="btn btn-{variant} btn-{size}"
  disabled={disabled || loading}
  on:click
>
  {#if loading}
    <span class="spinner"></span>
  {/if}
  <slot />
</button>

<style>
  .btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    border: none;
    border-radius: var(--radius);
    cursor: pointer;
    font-family: var(--font);
    font-weight: 500;
    transition: all 0.15s ease;
    white-space: nowrap;
  }

  .btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  /* Sizes */
  .btn-sm { font-size: 12px; padding: 5px 10px; }
  .btn-md { font-size: 13px; padding: 8px 16px; }

  /* Variants */
  .btn-primary {
    background: var(--accent);
    color: #fff;
  }
  .btn-primary:hover:not(:disabled) {
    background: var(--accent-hover);
  }

  .btn-secondary {
    background: var(--bg-elevated);
    color: var(--text);
    border: 1px solid var(--border);
  }
  .btn-secondary:hover:not(:disabled) {
    background: var(--border);
  }

  .btn-danger {
    background: var(--danger);
    color: #fff;
  }
  .btn-danger:hover:not(:disabled) {
    background: #dc2626;
  }

  .btn-ghost {
    background: transparent;
    color: var(--text-muted);
    border: 1px solid var(--border);
  }
  .btn-ghost:hover:not(:disabled) {
    color: var(--text);
    background: var(--bg-elevated);
  }

  /* Spinner */
  .spinner {
    display: inline-block;
    width: 12px;
    height: 12px;
    border: 2px solid rgba(255,255,255,0.3);
    border-top-color: currentColor;
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
