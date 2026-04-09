<script>
  export let modelId = ''

  function getProvider(id) {
    const s = (id || '').toLowerCase()
    if (s.includes('claude') || s.includes('anthropic')) return 'anthropic'
    if (s.includes('gpt') || s.includes('openai') || s.startsWith('o1') || s.startsWith('o3') || s.startsWith('o4')) return 'openai'
    if (s.includes('gemini') || s.includes('google')) return 'google'
    if (s.includes('llama') || s.includes('mistral') || s.includes('qwen') || s.includes(':')) return 'ollama'
    return 'unknown'
  }

  const providerColors = {
    anthropic: '#a259ff',
    openai: '#22c55e',
    google: '#38bdf8',
    ollama: '#f59e0b',
    unknown: '#8888aa',
  }

  const providerLabels = {
    anthropic: 'Anthropic',
    openai: 'OpenAI',
    google: 'Google',
    ollama: 'Local',
    unknown: '?',
  }

  $: provider = getProvider(modelId)
  $: color = providerColors[provider]
  $: label = providerLabels[provider]
</script>

<span class="model-badge">
  <span class="dot" style="background: {color}"></span>
  <span class="name" title={modelId}>{modelId || '—'}</span>
</span>

<style>
  .model-badge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 12px;
    font-family: var(--font-mono);
    color: var(--text-muted);
    background: var(--bg-elevated);
    padding: 2px 8px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border);
    max-width: 200px;
    overflow: hidden;
  }
  .dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
</style>
