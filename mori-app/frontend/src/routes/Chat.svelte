<script>
  import { onMount, tick } from 'svelte'
  import { api, streamRun } from '../lib/api.js'
  import { addToast } from '../lib/stores.js'

  // ── state ────────────────────────────────────────────────────────────────
  let sessions = []
  let activeSession = null
  let messages = []
  let inputText = ''
  let sending = false
  let loadingMessages = false
  let models = []
  let agents = []
  let selectedModel = ''
  let selectedAgent = ''

  let messagesEl    // bind:this for scroll
  let textareaEl    // bind:this for auto-resize
  let closeStream = null // cleanup fn returned by streamRun

  // ── lifecycle ─────────────────────────────────────────────────────────────

  onMount(async () => {
    await loadInitialData()
  })

  async function loadInitialData() {
    try {
      const [sessRes, modRes, agentRes] = await Promise.all([
        api.getChatSessions().catch(() => []),
        api.getModels().catch(() => []),
        api.getAgents().catch(() => []),
      ])

      sessions = Array.isArray(sessRes) ? sessRes : []
      models   = Array.isArray(modRes)  ? modRes  : (modRes?.models  || [])
      agents   = Array.isArray(agentRes)? agentRes : (agentRes?.agents || [])

      if (sessions.length > 0) {
        await selectSession(sessions[0])
      }
    } catch (e) {
      addToast('Error cargando sesiones', 'error')
    }
  }

  // ── session management ────────────────────────────────────────────────────

  async function selectSession(session) {
    if (closeStream) { closeStream(); closeStream = null }
    activeSession = session
    loadingMessages = true
    try {
      messages = await api.getChatMessages(session.id)
    } catch (e) {
      messages = []
    } finally {
      loadingMessages = false
    }
    await scrollToBottom()
  }

  async function newSession() {
    try {
      const session = await api.createChatSession({
        title: 'Nueva conversación',
        model_id: selectedModel || null,
        agent_id: selectedAgent || null,
      })
      sessions = [session, ...sessions]
      await selectSession(session)
    } catch (e) {
      addToast('Error creando sesión', 'error')
    }
  }

  async function deleteSession(session, e) {
    e.stopPropagation()
    try {
      await api.deleteChatSession(session.id)
      sessions = sessions.filter(s => s.id !== session.id)
      if (activeSession?.id === session.id) {
        activeSession = null
        messages = []
        if (sessions.length > 0) await selectSession(sessions[0])
      }
    } catch (e) {
      addToast('Error eliminando sesión', 'error')
    }
  }

  // ── send message ──────────────────────────────────────────────────────────

  async function sendMessage() {
    const content = inputText.trim()
    if (!content || sending) return

    // Create session on-the-fly if none exists
    if (!activeSession) {
      try {
        const session = await api.createChatSession({
          title: content.slice(0, 60),
          model_id: selectedModel || null,
          agent_id: selectedAgent || null,
        })
        sessions = [session, ...sessions]
        activeSession = session
        messages = []
      } catch (e) {
        addToast('Error creando sesión', 'error')
        return
      }
    }

    sending = true
    inputText = ''
    resizeTextarea()

    // Optimistically add user bubble
    const tempUserId = 'tmp_' + Date.now()
    messages = [...messages, { id: tempUserId, role: 'user', content, session_id: activeSession.id }]
    await scrollToBottom()

    // Optimistically add assistant bubble with spinner
    const tempAssistId = 'tmp_ast_' + Date.now()
    messages = [...messages, { id: tempAssistId, role: 'assistant', content: '', streaming: true, session_id: activeSession.id }]
    await scrollToBottom()

    try {
      const result = await api.sendChatMessage(activeSession.id, {
        content,
        model_id: selectedModel || null,
        agent_id: selectedAgent || null,
      })

      // Replace temp messages with real ones from server
      messages = messages.filter(m => m.id !== tempUserId && m.id !== tempAssistId)
      messages = [...messages, result.user_message, { ...result.assistant_message, streaming: true }]

      // Update session title in sidebar
      if (result.user_message?.session_id) {
        const updatedSession = await api.getChatSession(activeSession.id).catch(() => null)
        if (updatedSession) {
          activeSession = updatedSession
          sessions = sessions.map(s => s.id === updatedSession.id ? updatedSession : s)
        }
      }

      await scrollToBottom()

      // Connect SSE stream
      const runId = result.run_id
      if (runId) {
        closeStream = streamRun(
          runId,
          async (chunk) => {
            // Append chunk to the assistant message
            messages = messages.map(m => {
              if (m.id === result.assistant_message.id) {
                return { ...m, content: m.content + chunk }
              }
              return m
            })
            await scrollToBottom()
          },
          async () => {
            // Done event
            messages = messages.map(m => {
              if (m.id === result.assistant_message.id) {
                return { ...m, streaming: false }
              }
              return m
            })
            sending = false
            closeStream = null
            await scrollToBottom()
          },
          (err) => {
            messages = messages.map(m => {
              if (m.id === result.assistant_message.id) {
                return { ...m, streaming: false }
              }
              return m
            })
            sending = false
            closeStream = null
          }
        )
      } else {
        sending = false
      }
    } catch (e) {
      // Remove optimistic temp messages on error
      messages = messages.filter(m => !m.id.startsWith('tmp_'))
      addToast('Error enviando mensaje: ' + e.message, 'error')
      sending = false
    }
  }

  // ── input handling ────────────────────────────────────────────────────────

  function onKeydown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  function resizeTextarea() {
    if (!textareaEl) return
    textareaEl.style.height = 'auto'
    textareaEl.style.height = Math.min(textareaEl.scrollHeight, 120) + 'px'
  }

  // ── scroll ────────────────────────────────────────────────────────────────

  async function scrollToBottom() {
    await tick()
    if (messagesEl) {
      messagesEl.scrollTop = messagesEl.scrollHeight
    }
  }

  // ── time format ───────────────────────────────────────────────────────────

  function formatTime(iso) {
    if (!iso) return ''
    try {
      return new Date(iso).toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' })
    } catch { return '' }
  }
</script>

<!-- ── layout ─────────────────────────────────────────────────────────────── -->
<div class="chat-root">

  <!-- LEFT: session panel -->
  <aside class="sessions-panel">
    <div class="sessions-header">
      <span class="sessions-title">Conversaciones</span>
      <button class="new-btn" on:click={newSession} title="Nueva conversación">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <path d="M12 5v14M5 12h14"/>
        </svg>
      </button>
    </div>

    <div class="sessions-list">
      {#if sessions.length === 0}
        <div class="sessions-empty">Sin conversaciones</div>
      {/if}
      {#each sessions as session (session.id)}
        <button
          class="session-item"
          class:active={activeSession?.id === session.id}
          on:click={() => selectSession(session)}
        >
          <span class="session-title">{session.title || 'Nueva conversación'}</span>
          <button
            class="session-delete"
            on:click={(e) => deleteSession(session, e)}
            title="Eliminar"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M18 6L6 18M6 6l12 12"/>
            </svg>
          </button>
        </button>
      {/each}
    </div>
  </aside>

  <!-- RIGHT: chat panel -->
  <div class="chat-panel">

    <!-- header -->
    <div class="chat-header">
      <div class="chat-header-title">
        {#if activeSession}
          <span>{activeSession.title || 'Nueva conversación'}</span>
        {:else}
          <span class="muted">Selecciona o crea una conversación</span>
        {/if}
      </div>
      <div class="chat-selectors">
        <select bind:value={selectedModel} class="selector">
          <option value="">Modelo auto</option>
          {#each models as m}
            <option value={m.id}>{m.name || m.id}</option>
          {/each}
        </select>
        <select bind:value={selectedAgent} class="selector">
          <option value="">Agente auto</option>
          {#each agents as a}
            <option value={a.id}>{a.name}</option>
          {/each}
        </select>
      </div>
    </div>

    <!-- messages -->
    <div class="messages" bind:this={messagesEl}>
      {#if loadingMessages}
        <div class="messages-loading">Cargando mensajes...</div>
      {:else if !activeSession}
        <div class="messages-empty">
          <div class="empty-icon">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" opacity="0.3">
              <path d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"/>
            </svg>
          </div>
          <p>Inicia una conversación con Mori</p>
          <button class="empty-btn" on:click={newSession}>Nueva conversación</button>
        </div>
      {:else if messages.length === 0}
        <div class="messages-empty">
          <div class="empty-icon">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" opacity="0.3">
              <path d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"/>
            </svg>
          </div>
          <p>Escribe tu primer mensaje</p>
        </div>
      {:else}
        <div class="messages-inner">
          {#each messages as msg (msg.id)}
            {#if msg.role === 'user'}
              <div class="msg msg-user">
                <div class="bubble bubble-user">
                  <p class="bubble-text">{msg.content}</p>
                  <span class="bubble-time">{formatTime(msg.created_at)}</span>
                </div>
              </div>
            {:else}
              <div class="msg msg-assistant">
                <div class="msg-avatar">
                  <svg width="20" height="20" viewBox="0 0 28 28" fill="none" aria-hidden="true">
                    <rect width="28" height="28" rx="8" fill="var(--accent)"/>
                    <circle cx="14" cy="14" r="5" stroke="white" stroke-width="2" fill="none"/>
                    <circle cx="14" cy="14" r="1.5" fill="white"/>
                    <line x1="14" y1="4" x2="14" y2="9" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
                    <line x1="14" y1="19" x2="14" y2="24" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
                    <line x1="4" y1="14" x2="9" y2="14" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
                    <line x1="19" y1="14" x2="24" y2="14" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
                  </svg>
                </div>
                <div class="bubble bubble-assistant">
                  {#if msg.streaming && !msg.content}
                    <div class="typing-indicator">
                      <span></span><span></span><span></span>
                    </div>
                  {:else}
                    <p class="bubble-text">{msg.content}{#if msg.streaming}<span class="cursor">|</span>{/if}</p>
                    <span class="bubble-time">{formatTime(msg.created_at)}</span>
                  {/if}
                </div>
              </div>
            {/if}
          {/each}
        </div>
      {/if}
    </div>

    <!-- input area -->
    <div class="input-area">
      <div class="input-box" class:disabled={sending}>
        <textarea
          bind:this={textareaEl}
          bind:value={inputText}
          on:keydown={onKeydown}
          on:input={resizeTextarea}
          placeholder={sending ? 'Esperando respuesta...' : 'Escribe un mensaje... (Enter para enviar, Shift+Enter para nueva línea)'}
          disabled={sending}
          rows="1"
          class="chat-textarea"
        ></textarea>
        <button
          class="send-btn"
          on:click={sendMessage}
          disabled={sending || !inputText.trim()}
          title="Enviar"
        >
          {#if sending}
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="spin">
              <path d="M21 12a9 9 0 11-6.219-8.56"/>
            </svg>
          {:else}
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M22 2L11 13M22 2L15 22l-4-9-9-4 19-7z"/>
            </svg>
          {/if}
        </button>
      </div>
    </div>

  </div>
</div>

<style>
  /* ── root: full height, no scroll (override App.svelte .content padding) */
  .chat-root {
    display: flex;
    height: calc(100vh - 48px); /* subtract App .content padding top+bottom */
    margin: -24px;              /* cancel App .content padding */
    overflow: hidden;
    background: var(--bg);
  }

  /* ── sessions panel ───────────────────────────────────────────────────── */
  .sessions-panel {
    width: 260px;
    min-width: 260px;
    background: var(--bg-surface);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: hidden;
  }

  .sessions-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 14px 12px;
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
  }

  .sessions-title {
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--text-muted);
  }

  .new-btn {
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    color: var(--text-muted);
    cursor: pointer;
    padding: 4px 8px;
    display: flex;
    align-items: center;
    transition: all 0.15s;
  }

  .new-btn:hover {
    background: var(--accent);
    border-color: var(--accent);
    color: #fff;
  }

  .sessions-list {
    flex: 1;
    overflow-y: auto;
    padding: 8px;
  }

  .sessions-empty {
    text-align: center;
    padding: 24px 12px;
    color: var(--text-muted);
    font-size: 12px;
  }

  .session-item {
    display: flex;
    align-items: center;
    gap: 6px;
    width: 100%;
    padding: 9px 10px;
    border-radius: var(--radius);
    background: none;
    border: none;
    cursor: pointer;
    color: var(--text-muted);
    font-size: 13px;
    text-align: left;
    transition: all 0.15s;
    border-left: 2px solid transparent;
  }

  .session-item:hover {
    background: var(--bg-elevated);
    color: var(--text);
  }

  .session-item.active {
    background: rgba(124, 106, 255, 0.12);
    color: var(--accent);
    border-left-color: var(--accent);
  }

  .session-title {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .session-delete {
    background: none;
    border: none;
    cursor: pointer;
    color: var(--text-muted);
    padding: 2px;
    border-radius: 3px;
    display: flex;
    align-items: center;
    opacity: 0;
    transition: opacity 0.15s;
    flex-shrink: 0;
  }

  .session-item:hover .session-delete {
    opacity: 1;
  }

  .session-delete:hover {
    color: var(--danger);
  }

  /* ── chat panel ───────────────────────────────────────────────────────── */
  .chat-panel {
    flex: 1;
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: hidden;
    background: var(--bg);
  }

  /* ── chat header ──────────────────────────────────────────────────────── */
  .chat-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 20px;
    border-bottom: 1px solid var(--border);
    background: var(--bg-surface);
    flex-shrink: 0;
  }

  .chat-header-title {
    font-size: 14px;
    font-weight: 600;
    color: var(--text);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex: 1;
  }

  .muted { color: var(--text-muted); font-weight: 400; }

  .chat-selectors {
    display: flex;
    gap: 8px;
    flex-shrink: 0;
    margin-left: 12px;
  }

  .selector {
    width: auto;
    min-width: 120px;
    font-size: 12px;
    padding: 5px 8px;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    color: var(--text-muted);
    cursor: pointer;
  }

  .selector:focus { border-color: var(--accent); }

  /* ── messages area ────────────────────────────────────────────────────── */
  .messages {
    flex: 1;
    overflow-y: auto;
    padding: 20px;
    scroll-behavior: smooth;
  }

  .messages-inner {
    display: flex;
    flex-direction: column;
    gap: 16px;
    max-width: 820px;
    margin: 0 auto;
  }

  .messages-loading,
  .messages-empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    gap: 16px;
    color: var(--text-muted);
    font-size: 14px;
  }

  .empty-icon {
    color: var(--text-muted);
  }

  .empty-btn {
    background: var(--accent);
    color: #fff;
    border: none;
    border-radius: var(--radius);
    padding: 8px 18px;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    transition: background 0.15s;
  }

  .empty-btn:hover { background: var(--accent-hover); }

  /* ── message bubbles ──────────────────────────────────────────────────── */
  .msg {
    display: flex;
    gap: 10px;
    align-items: flex-end;
  }

  .msg-user {
    justify-content: flex-end;
  }

  .msg-assistant {
    justify-content: flex-start;
  }

  .msg-avatar {
    flex-shrink: 0;
    margin-bottom: 2px;
  }

  .bubble {
    max-width: 72%;
    padding: 10px 14px;
    border-radius: 14px;
    line-height: 1.6;
    font-size: 14px;
    position: relative;
  }

  .bubble-user {
    background: rgba(124, 106, 255, 0.18);
    border: 1px solid rgba(124, 106, 255, 0.3);
    border-bottom-right-radius: 4px;
    color: var(--text);
  }

  .bubble-assistant {
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-bottom-left-radius: 4px;
    color: var(--text);
  }

  .bubble-text {
    margin: 0;
    white-space: pre-wrap;
    word-break: break-word;
  }

  .bubble-time {
    display: block;
    font-size: 10px;
    color: var(--text-muted);
    margin-top: 4px;
    text-align: right;
  }

  /* streaming cursor */
  .cursor {
    display: inline-block;
    color: var(--accent);
    font-weight: 300;
    animation: blink 1s step-start infinite;
    margin-left: 1px;
  }

  @keyframes blink {
    0%, 100% { opacity: 1; }
    50% { opacity: 0; }
  }

  /* typing indicator */
  .typing-indicator {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 4px 2px;
  }

  .typing-indicator span {
    width: 6px;
    height: 6px;
    background: var(--text-muted);
    border-radius: 50%;
    display: inline-block;
    animation: bounce 1.2s ease-in-out infinite;
  }

  .typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
  .typing-indicator span:nth-child(3) { animation-delay: 0.4s; }

  @keyframes bounce {
    0%, 80%, 100% { transform: scale(0.7); opacity: 0.5; }
    40%           { transform: scale(1.1); opacity: 1; }
  }

  /* ── input area ───────────────────────────────────────────────────────── */
  .input-area {
    padding: 16px 20px;
    border-top: 1px solid var(--border);
    background: var(--bg-surface);
    flex-shrink: 0;
  }

  .input-box {
    display: flex;
    align-items: flex-end;
    gap: 10px;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 8px 12px;
    transition: border-color 0.15s;
    max-width: 820px;
    margin: 0 auto;
  }

  .input-box:focus-within {
    border-color: var(--accent);
  }

  .input-box.disabled {
    opacity: 0.6;
  }

  .chat-textarea {
    flex: 1;
    background: none;
    border: none;
    color: var(--text);
    font-family: var(--font);
    font-size: 14px;
    line-height: 1.5;
    outline: none;
    resize: none;
    min-height: 22px;
    max-height: 120px;
    overflow-y: auto;
    padding: 0;
    width: 100%;
  }

  .chat-textarea::placeholder {
    color: var(--text-muted);
  }

  .send-btn {
    background: var(--accent);
    border: none;
    border-radius: var(--radius-sm);
    color: #fff;
    cursor: pointer;
    padding: 7px 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    transition: background 0.15s;
    align-self: flex-end;
  }

  .send-btn:hover:not(:disabled) {
    background: var(--accent-hover);
  }

  .send-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  .spin {
    animation: spin 0.8s linear infinite;
  }
</style>
