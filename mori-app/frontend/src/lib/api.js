const BASE = '/api'

function headers() {
  const token = localStorage.getItem('mori_token') || ''
  return {
    'Content-Type': 'application/json',
    ...(token ? { 'Authorization': `Bearer ${token}` } : {})
  }
}

async function req(method, path, body) {
  const res = await fetch(BASE + path, {
    method,
    headers: headers(),
    body: body ? JSON.stringify(body) : undefined
  })
  if (!res.ok) throw new Error(`${method} ${path} → ${res.status}`)
  return res.json()
}

export const api = {
  // Tasks
  getTasks: (params = {}) => req('GET', '/tasks?' + new URLSearchParams(params)),
  getTask: (id) => req('GET', `/tasks/${id}`),
  createTask: (data) => req('POST', '/tasks', data),
  updateTask: (id, data) => req('PATCH', `/tasks/${id}`, data),
  deleteTask: (id) => req('DELETE', `/tasks/${id}`),
  getTaskRuns: (id) => req('GET', `/tasks/${id}/runs`),
  cancelTask: (id) => req('POST', `/tasks/${id}/cancel`),

  // Projects
  getProjects: () => req('GET', '/projects'),
  createProject: (data) => req('POST', '/projects', data),
  getProjectTasks: (id) => req('GET', `/projects/${id}/tasks`),

  // Notes
  getNotes: (params = {}) => req('GET', '/notes?' + new URLSearchParams(params)),
  createNote: (data) => req('POST', '/notes', data),
  updateNote: (id, data) => req('PATCH', `/notes/${id}`, data),
  searchNotes: (q) => req('GET', `/notes/search?q=${encodeURIComponent(q)}`),

  // Pipelines
  getPipelines: () => req('GET', '/pipelines'),
  getPipelineRuns: () => req('GET', '/pipelines/runs'),

  // Agents
  getAgents: () => req('GET', '/agents'),

  // Models
  getModels: () => req('GET', '/models'),
  getModelStats: (id) => req('GET', `/models/${id}/stats`),

  // Memory
  searchMemory: (q) => req('GET', `/memory/search?q=${encodeURIComponent(q)}`),
  getMemoryChunks: () => req('GET', '/memory/chunks'),

  // Chat
  getChatSessions: () => req('GET', '/chat/sessions'),
  createChatSession: (data) => req('POST', '/chat/sessions', data),
  getChatSession: (id) => req('GET', `/chat/sessions/${id}`),
  deleteChatSession: (id) => req('DELETE', `/chat/sessions/${id}`),
  getChatMessages: (sessionId) => req('GET', `/chat/sessions/${sessionId}/messages`),
  sendChatMessage: (sessionId, data) => req('POST', `/chat/sessions/${sessionId}/send`, data),

  // System
  getHealth: () => req('GET', '/health'),
  getStats: () => req('GET', '/system/stats'),
  getConfig: () => req('GET', '/system/config'),
}

// SSE stream for a run — uses fetch so we can pass the Bearer token
export function streamRun(runId, onChunk, onDone, onError) {
  const url = `${BASE}/runs/${runId}/stream`
  const token = localStorage.getItem('mori_token') || ''
  const controller = new AbortController()
  let stopped = false

  fetch(url, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    signal: controller.signal,
  })
    .then(async (res) => {
      if (!res.ok) { onError?.(new Error(`SSE ${res.status}`)); return }
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (!stopped) {
        const { done, value } = await reader.read()
        if (done) { onDone?.(); break }
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const data = line.slice(6)
          if (data === '[DONE]') { onDone?.(); stopped = true; break }
          if (data) onChunk?.(data)
        }
      }
    })
    .catch((err) => { if (!stopped) onError?.(err) })

  return () => { stopped = true; controller.abort() }
}
