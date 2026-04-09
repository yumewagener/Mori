<script>
  export let content = ''
  export let isStreaming = false
  import { afterUpdate } from 'svelte'
  let container

  afterUpdate(() => {
    if (container) container.scrollTop = container.scrollHeight
  })
</script>

<div class="terminal" bind:this={container}>
  <pre>{content}{#if isStreaming}<span class="cursor">▋</span>{/if}</pre>
</div>

<style>
  .terminal {
    background: #0a0a0f;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 16px;
    max-height: 500px;
    overflow-y: auto;
    font-family: var(--font-mono);
    font-size: 13px;
    line-height: 1.6;
  }
  pre { white-space: pre-wrap; word-break: break-word; color: #c8e6c9; margin: 0; }
  .cursor { animation: blink 1s step-end infinite; color: var(--success); }
  @keyframes blink { 50% { opacity: 0 } }
</style>
