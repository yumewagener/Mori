import { writable } from 'svelte/store'

export const tasks = writable([])
export const projects = writable([])
export const notes = writable([])
export const agents = writable([])
export const models = writable([])
export const pipelines = writable([])
export const stats = writable(null)
export const currentRoute = writable('/')

// Toast notifications
export const toasts = writable([])

export function addToast(message, type = 'error', duration = 4000) {
  const id = Date.now()
  toasts.update(t => [...t, { id, message, type }])
  setTimeout(() => {
    toasts.update(t => t.filter(x => x.id !== id))
  }, duration)
}

// Token store (persisted to localStorage)
function createTokenStore() {
  const { subscribe, set } = writable(localStorage.getItem('mori_token') || '')
  return {
    subscribe,
    set: (v) => { localStorage.setItem('mori_token', v); set(v) }
  }
}
export const token = createTokenStore()
