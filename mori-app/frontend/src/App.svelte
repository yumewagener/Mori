<script>
  import { Router, Route } from 'svelte-routing'
  import Sidebar from './components/Sidebar.svelte'
  import Dashboard from './routes/Dashboard.svelte'
  import Tasks from './routes/Tasks.svelte'
  import TaskRun from './routes/TaskRun.svelte'
  import Projects from './routes/Projects.svelte'
  import Notes from './routes/Notes.svelte'
  import Pipelines from './routes/Pipelines.svelte'
  import Models from './routes/Models.svelte'
  import Agents from './routes/Agents.svelte'
  import Memory from './routes/Memory.svelte'
  import System from './routes/System.svelte'
  import { toasts } from './lib/stores.js'

  export let url = ''
</script>

<Router {url}>
  <div class="app">
    <Sidebar />
    <main class="content">
      <Route path="/" component={Dashboard} />
      <Route path="/tasks" component={Tasks} />
      <Route path="/tasks/:id/run" let:params>
        <TaskRun runId={params.id} />
      </Route>
      <Route path="/projects" component={Projects} />
      <Route path="/notes" component={Notes} />
      <Route path="/pipelines" component={Pipelines} />
      <Route path="/models" component={Models} />
      <Route path="/agents" component={Agents} />
      <Route path="/memory" component={Memory} />
      <Route path="/system" component={System} />
    </main>
  </div>
</Router>

<!-- Toast notifications -->
<div class="toast-container">
  {#each $toasts as toast (toast.id)}
    <div class="toast toast-{toast.type}">{toast.message}</div>
  {/each}
</div>

<style>
  :global(*) { box-sizing: border-box; margin: 0; padding: 0; }
  :global(body) {
    background: var(--bg);
    color: var(--text);
    font-family: var(--font);
    font-size: 14px;
    line-height: 1.5;
  }
  :global(:root) {
    --bg: #0f0f13;
    --bg-surface: #1a1a24;
    --bg-elevated: #22223a;
    --border: #2e2e45;
    --text: #e8e8f0;
    --text-muted: #8888aa;
    --accent: #7c6aff;
    --accent-hover: #9580ff;
    --success: #22c55e;
    --warning: #f59e0b;
    --danger: #ef4444;
    --info: #38bdf8;
    --font: 'Inter', -apple-system, sans-serif;
    --font-mono: 'JetBrains Mono', 'Fira Code', monospace;
    --radius: 8px;
    --radius-sm: 4px;
  }
  :global(a) { color: var(--accent); text-decoration: none; }
  :global(a:hover) { color: var(--accent-hover); }
  :global(input), :global(textarea), :global(select) {
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    color: var(--text);
    font-family: var(--font);
    font-size: 14px;
    padding: 8px 12px;
    outline: none;
    width: 100%;
  }
  :global(input:focus), :global(textarea:focus), :global(select:focus) {
    border-color: var(--accent);
  }
  :global(label) {
    display: block;
    font-size: 12px;
    font-weight: 500;
    color: var(--text-muted);
    margin-bottom: 4px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  :global(.form-group) { margin-bottom: 16px; }
  :global(h1) { font-size: 22px; font-weight: 600; }
  :global(h2) { font-size: 18px; font-weight: 600; }
  :global(h3) { font-size: 15px; font-weight: 600; }
  .app {
    display: flex;
    height: 100vh;
    overflow: hidden;
  }
  .content {
    flex: 1;
    overflow-y: auto;
    padding: 24px;
  }

  .toast-container {
    position: fixed;
    bottom: 24px;
    right: 24px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    z-index: 9999;
  }
  .toast {
    padding: 12px 18px;
    border-radius: var(--radius);
    font-size: 13px;
    font-weight: 500;
    max-width: 340px;
    animation: slideIn 0.2s ease;
  }
  .toast-error { background: var(--danger); color: #fff; }
  .toast-success { background: var(--success); color: #fff; }
  .toast-info { background: var(--info); color: #000; }
  .toast-warning { background: var(--warning); color: #000; }
  @keyframes slideIn {
    from { transform: translateX(40px); opacity: 0; }
    to { transform: translateX(0); opacity: 1; }
  }
</style>
