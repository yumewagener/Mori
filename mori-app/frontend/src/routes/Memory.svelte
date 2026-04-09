<script>
  import { onMount } from 'svelte'
  import { api } from '../lib/api.js'
  import { addToast } from '../lib/stores.js'
  import TopBar from '../components/TopBar.svelte'

  let searchQ = ''
  let results = []
  let chunks = []
  let loading = false
  let initialLoading = true
  let searchTimer

  const sourceColors = {
    note: 'var(--accent)',
    task: 'var(--info)',
    decision: 'var(--warning)',
    run: 'var(--success)',
  }

  async function loadChunks() {
    try {
      const res = await api.getMemoryChunks()
      chunks = Array.isArray(res) ? res : (res?.chunks || [])
    } catch (e) {
      // Memory API may not be available
    } finally {
      initialLoading = false
    }
  }

  async function doSearch() {
    if (!searchQ.trim()) {
      results = []
      return
    }
    loading = true
    try {
      const res = await api.searchMemory(searchQ)
      results = Array.isArray(res) ? res : (res?.results || [])
    } catch (e) {
      addToast('Error buscando en memoria', 'error')
      results = []
    } finally {
      loading = false
    }
  }

  function onInput() {
    clearTimeout(searchTimer)
    searchTimer = setTimeout(doSearch, 400)
  }

  function formatDate(d) {
    if (!d) return '—'
    return new Date(d).toLocaleDateString('es', { day: 'numeric', month: 'short', year: 'numeric' })
  }

  function excerpt(text, max = 200) {
    if (!text) return ''
    return text.length > max ? text.slice(0, max) + '...' : text
  }

  onMount(loadChunks)
</script>

<div>
  <TopBar title="Memoria" subtitle="Contexto acumulado del orquestador" />

  <!-- Info banner -->
  <div class="info-banner">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;color:var(--info)">
      <circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>
    </svg>
    <p>La memoria incluye notas, decisiones y resultados de tareas pasadas. Se inyecta automáticamente en el contexto del agente al procesar nuevas tareas relacionadas.</p>
  </div>

  <!-- Search -->
  <div class="search-section">
    <div class="search-wrap">
      <svg class="search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
      <input
        type="text"
        placeholder="Buscar en memoria y contexto acumulado..."
        bind:value={searchQ}
        on:input={onInput}
        class="search-input"
      />
    </div>
  </div>

  {#if loading}
    <div class="loading-text">Buscando...</div>
  {:else if searchQ && results.length === 0 && !loading}
    <div class="empty-state">No se encontraron resultados para "{searchQ}"</div>
  {:else if results.length > 0}
    <div class="results-list">
      {#each results as item}
        <div class="result-card">
          <div class="result-header">
            <span class="source-badge" style="color: {sourceColors[item.source_type] || 'var(--text-muted)'}">
              {item.source_type || 'contexto'}
            </span>
            <span class="result-date">{formatDate(item.date || item.created_at)}</span>
          </div>
          {#if item.title}
            <h3 class="result-title">{item.title}</h3>
          {/if}
          <p class="result-excerpt">{excerpt(item.content || item.text)}</p>
          {#if item.score != null}
            <div class="relevance">
              <div class="relevance-bar" style="width: {Math.round(item.score * 100)}%"></div>
              <span class="relevance-label">{Math.round(item.score * 100)}% relevante</span>
            </div>
          {/if}
        </div>
      {/each}
    </div>
  {:else if !searchQ}
    <!-- Show memory chunks overview -->
    <div class="chunks-section">
      <h2 class="section-title">Contexto almacenado</h2>
      {#if initialLoading}
        <div class="loading-text">Cargando...</div>
      {:else if chunks.length === 0}
        <div class="empty-state">No hay datos en memoria todavía</div>
      {:else}
        <div class="chunks-grid">
          {#each chunks as chunk}
            <div class="chunk-card">
              <div class="chunk-header">
                <span class="source-badge" style="color: {sourceColors[chunk.source_type] || 'var(--text-muted)'}">
                  {chunk.source_type || 'chunk'}
                </span>
                <span class="chunk-date">{formatDate(chunk.created_at)}</span>
              </div>
              {#if chunk.title}
                <p class="chunk-title">{chunk.title}</p>
              {/if}
              <p class="chunk-excerpt">{excerpt(chunk.content, 100)}</p>
            </div>
          {/each}
        </div>
      {/if}
    </div>
  {/if}
</div>

<style>
  .info-banner {
    display: flex;
    gap: 12px;
    background: rgba(56,189,248,0.08);
    border: 1px solid rgba(56,189,248,0.2);
    border-radius: var(--radius);
    padding: 14px 16px;
    margin-bottom: 20px;
    font-size: 13px;
    color: var(--text-muted);
    line-height: 1.5;
    align-items: flex-start;
  }

  .search-section { margin-bottom: 20px; }
  .search-wrap { position: relative; max-width: 520px; }
  .search-icon {
    position: absolute; left: 12px; top: 50%;
    transform: translateY(-50%);
    color: var(--text-muted); pointer-events: none;
  }
  .search-input { padding-left: 40px !important; font-size: 14px; }

  .loading-text { color: var(--text-muted); padding: 40px; text-align: center; }

  .empty-state {
    text-align: center; padding: 40px;
    color: var(--text-muted);
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
  }

  .results-list { display: flex; flex-direction: column; gap: 12px; }

  .result-card {
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 16px 20px;
    transition: border-color 0.15s;
  }
  .result-card:hover { border-color: var(--accent); }

  .result-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 8px;
  }

  .source-badge {
    font-size: 10px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.5px;
  }

  .result-date, .chunk-date {
    font-size: 11px; color: var(--text-muted);
  }

  .result-title {
    font-size: 14px; font-weight: 600;
    margin-bottom: 6px;
  }

  .result-excerpt {
    font-size: 13px; color: var(--text-muted);
    line-height: 1.5;
  }

  .relevance {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-top: 10px;
  }
  .relevance-bar {
    height: 3px;
    background: var(--accent);
    border-radius: 2px;
    max-width: 120px;
  }
  .relevance-label { font-size: 11px; color: var(--text-muted); }

  .chunks-section { margin-top: 8px; }
  .section-title {
    font-size: 12px; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.5px;
    color: var(--text-muted); margin-bottom: 14px;
  }

  .chunks-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 12px;
  }

  .chunk-card {
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 14px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .chunk-header {
    display: flex; justify-content: space-between; align-items: center;
  }

  .chunk-title { font-size: 12px; font-weight: 600; }
  .chunk-excerpt { font-size: 11px; color: var(--text-muted); line-height: 1.4; }
</style>
