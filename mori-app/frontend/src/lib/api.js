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

// SSE stream for a run
export function streamRun(runId, onChunk, onDone, onError) {
  const url = `${BASE}/runs/${runId}/stream`
  const es = new EventSource(url)
  es.onmessage = (e) => {
    if (e.data === '[DONE]') {
      es.close()
      onDone?.()
    } else {
      onChunk?.(e.data)
    }
  }
  es.onerror = (e) => { es.close(); onError?.(e) }
  return () => es.close()
}
