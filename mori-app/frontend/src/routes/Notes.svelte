<script>
  import { onMount } from 'svelte'
  import { api } from '../lib/api.js'
  import { addToast } from '../lib/stores.js'
  import Button from '../components/Button.svelte'
  import Modal from '../components/Modal.svelte'
  import TopBar from '../components/TopBar.svelte'

  let noteList = []
  let loading = true
  let showNewNote = false
  let creating = false
  let activeType = 'all'
  let searchQ = ''
  let searchTimer

  let newNote = { title: '', content: '', type: 'nota', tags: '', area: '' }

  const typeFilters = [
    { key: 'all', label: 'Todas' },
    { key: 'nota', label: 'Notas' },
    { key: 'decision', label: 'Decisiones' },
    { key: 'investigacion', label: 'Investigación' },
    { key: 'idea', label: 'Ideas' },
  ]

  const typeColors = {
    nota: 'var(--text-muted)',
    decision: 'var(--warning)',
    investigacion: 'var(--info)',
    idea: 'var(--accent)',
  }

  async function loadNotes() {
    loading = true
    try {
      const params = {}
      if (activeType !== 'all') params.type = activeType

      let res
      if (searchQ.trim()) {
        res = await api.searchNotes(searchQ)
      } else {
        res = await api.getNotes(params)
      }
      noteList = Array.isArray(res) ? res : (res?.notes || [])
    } catch (e) {
      addToast('Error cargando notas', 'error')
    } finally {
      loading = false
    }
  }

  function onSearch() {
    clearTimeout(searchTimer)
    searchTimer = setTimeout(loadNotes, 400)
  }

  async function createNote() {
    if (!newNote.title.trim()) return
    creating = true
    try {
      const payload = { ...newNote }
      if (payload.tags) payload.tags = payload.tags.split(',').map(t => t.trim()).filter(Boolean)
      await api.createNote(payload)
      showNewNote = false
      newNote = { title: '', content: '', type: 'nota', tags: '', area: '' }
      addToast('Nota creada', 'success')
      await loadNotes()
    } catch (e) {
      addToast('Error creando nota', 'error')
    } finally {
      creating = false
    }
  }

  function formatDate(d) {
    if (!d) return '—'
    return new Date(d).toLocaleDateString('es', { day: 'numeric', month: 'short', year: 'numeric' })
  }

  function excerpt(text, max = 120) {
    if (!text) return ''
    return text.length > max ? text.slice(0, max) + '...' : text
  }

  onMount(loadNotes)
</script>

<div>
  <TopBar title="Notas" subtitle="Conocimiento y decisiones">
    <Button on:click={() => showNewNote = true}>+ Nueva nota</Button>
  </TopBar>

  <div class="controls">
    <!-- Type tabs -->
    <div class="type-tabs">
      {#each typeFilters as f}
        <button
          class="tab-btn"
          class:active={activeType === f.key}
          on:click={() => { activeType = f.key; loadNotes() }}
        >{f.label}</button>
      {/each}
    </div>

    <!-- Search -->
    <div class="search-wrap">
      <svg class="search-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
      <input
        type="text"
        placeholder="Buscar notas..."
        bind:value={searchQ}
        on:input={onSearch}
        class="search-input"
      />
    </div>
  </div>

  {#if loading}
    <div class="notes-grid">
      {#each [1,2,3,4,5,6] as _}
        <div class="skeleton-note"></div>
      {/each}
    </div>
  {:else if noteList.length === 0}
    <div class="empty-state">
      <div class="empty-icon">📝</div>
      <p>No hay notas todavía</p>
      <Button on:click={() => showNewNote = true}>Crear primera nota</Button>
    </div>
  {:else}
    <div class="notes-grid">
      {#each noteList as note}
        <div class="note-card">
          <div class="note-header">
            <h3 class="note-title">{note.title}</h3>
            <span class="type-badge" style="color: {typeColors[note.type] || 'var(--text-muted)'}">
              {note.type || 'nota'}
            </span>
          </div>
          {#if note.content}
            <p class="note-excerpt">{excerpt(note.content)}</p>
          {/if}
          {#if note.tags && note.tags.length > 0}
            <div class="note-tags">
              {#each (Array.isArray(note.tags) ? note.tags : note.tags.split(',')).slice(0, 4) as tag}
                <span class="tag">{tag.trim()}</span>
              {/each}
            </div>
          {/if}
          <div class="note-footer">
            <span class="note-date">{formatDate(note.created_at || note.date)}</span>
            {#if note.area}
              <span class="note-area">{note.area}</span>
            {/if}
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<Modal open={showNewNote} title="Nueva nota" on:close={() => showNewNote = false}>
  <div class="form-group">
    <label>Título *</label>
    <input bind:value={newNote.title} placeholder="Título de la nota..." />
  </div>
  <div class="form-group">
    <label>Contenido</label>
    <textarea bind:value={newNote.content} rows="5" placeholder="Escribe aquí..."></textarea>
  </div>
  <div class="form-row">
    <div class="form-group">
      <label>Tipo</label>
      <select bind:value={newNote.type}>
        <option value="nota">Nota</option>
        <option value="decision">Decisión</option>
        <option value="investigacion">Investigación</option>
        <option value="idea">Idea</option>
      </select>
    </div>
    <div class="form-group">
      <label>Área</label>
      <input bind:value={newNote.area} placeholder="dev, research..." />
    </div>
  </div>
  <div class="form-group">
    <label>Tags (comas)</label>
    <input bind:value={newNote.tags} placeholder="tag1, tag2" />
  </div>
  <div class="modal-actions">
    <Button variant="secondary" on:click={() => showNewNote = false}>Cancelar</Button>
    <Button loading={creating} on:click={createNote}>Guardar</Button>
  </div>
</Modal>

<style>
  .controls {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 20px;
  }

  .type-tabs {
    display: flex;
    gap: 4px;
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 4px;
  }

  .tab-btn {
    background: none; border: none;
    color: var(--text-muted);
    padding: 5px 12px;
    border-radius: var(--radius-sm);
    font-size: 12px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
  }
  .tab-btn:hover { color: var(--text); }
  .tab-btn.active { background: var(--bg-elevated); color: var(--text); }

  .search-wrap {
    position: relative;
    min-width: 220px;
  }
  .search-icon {
    position: absolute; left: 10px; top: 50%;
    transform: translateY(-50%);
    color: var(--text-muted); pointer-events: none;
  }
  .search-input { padding-left: 32px !important; }

  .notes-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 16px;
  }

  .skeleton-note {
    height: 140px;
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    animation: pulse 1.5s ease infinite;
  }
  @keyframes pulse { 0%,100%{opacity:1}50%{opacity:0.5} }

  .note-card {
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 16px;
    transition: border-color 0.15s;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .note-card:hover { border-color: var(--accent); }

  .note-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 8px;
  }
  .note-title { font-size: 13px; font-weight: 600; flex: 1; line-height: 1.3; }
  .type-badge {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    flex-shrink: 0;
  }

  .note-excerpt {
    font-size: 12px;
    color: var(--text-muted);
    line-height: 1.5;
    flex: 1;
  }

  .note-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }
  .tag {
    background: rgba(124,106,255,0.1);
    color: var(--accent);
    border-radius: var(--radius-sm);
    padding: 1px 6px;
    font-size: 10px;
  }

  .note-footer {
    display: flex;
    justify-content: space-between;
    font-size: 11px;
    color: var(--text-muted);
    margin-top: auto;
  }

  .empty-state {
    text-align: center; padding: 60px; color: var(--text-muted);
  }
  .empty-icon { font-size: 40px; margin-bottom: 12px; }
  .empty-state p { margin-bottom: 16px; }

  .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  .modal-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 20px; }
  textarea { resize: vertical; }
</style>
