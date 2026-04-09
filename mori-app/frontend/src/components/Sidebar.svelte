<script>
  import { Link, navigate } from 'svelte-routing'

  const navItems = [
    { label: 'Dashboard', path: '/', icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6' },
    { label: 'Tareas', path: '/tasks', icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4' },
    { label: 'Proyectos', path: '/projects', icon: 'M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z' },
    { label: 'Notas', path: '/notes', icon: 'M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z' },
    { label: 'Pipelines', path: '/pipelines', icon: 'M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15' },
    { label: 'Modelos', path: '/models', icon: 'M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v10m0 0h10M9 13H5a2 2 0 00-2 2v4a2 2 0 002 2h4M9 13h10a2 2 0 012 2v4a2 2 0 01-2 2h-4m0 0V13m0 8H9' },
    { label: 'Agentes', path: '/agents', icon: 'M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z' },
    { label: 'Memoria', path: '/memory', icon: 'M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z' },
    { label: 'Sistema', path: '/system', icon: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z' },
  ]

  let currentPath = window.location.pathname

  function isActive(path) {
    if (path === '/') return currentPath === '/'
    return currentPath.startsWith(path)
  }
</script>

<nav class="sidebar">
  <div class="logo">
    <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-label="Mori">
      <rect width="28" height="28" rx="8" fill="var(--accent)"/>
      <circle cx="14" cy="14" r="5" stroke="white" stroke-width="2" fill="none"/>
      <circle cx="14" cy="14" r="1.5" fill="white"/>
      <line x1="14" y1="4" x2="14" y2="9" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
      <line x1="14" y1="19" x2="14" y2="24" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
      <line x1="4" y1="14" x2="9" y2="14" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
      <line x1="19" y1="14" x2="24" y2="14" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
    </svg>
    <span class="logo-text">Mori</span>
  </div>

  <ul class="nav-list">
    {#each navItems as item}
      <li>
        <Link to={item.path}>
          <div class="nav-item" class:active={isActive(item.path)} on:click={() => currentPath = item.path}>
            <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <path d={item.icon}/>
            </svg>
            <span>{item.label}</span>
          </div>
        </Link>
      </li>
    {/each}
  </ul>

  <div class="sidebar-footer">
    <div class="footer-dot online"></div>
    <span class="footer-text">API conectada</span>
  </div>
</nav>

<style>
  .sidebar {
    width: 240px;
    min-width: 240px;
    background: var(--bg-surface);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    height: 100vh;
    overflow-y: auto;
  }

  .logo {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 20px 16px 16px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 8px;
  }

  .logo-text {
    font-size: 18px;
    font-weight: 600;
    letter-spacing: -0.5px;
    color: var(--text);
  }

  .nav-list {
    list-style: none;
    flex: 1;
    padding: 0 8px;
  }

  .nav-list li {
    margin-bottom: 2px;
  }

  .nav-list :global(a) {
    color: inherit;
    text-decoration: none;
  }

  .nav-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 9px 12px;
    border-radius: var(--radius);
    cursor: pointer;
    color: var(--text-muted);
    font-size: 13.5px;
    font-weight: 500;
    transition: all 0.15s ease;
    border-left: 2px solid transparent;
  }

  .nav-item:hover {
    background: var(--bg-elevated);
    color: var(--text);
  }

  .nav-item.active {
    background: rgba(124, 106, 255, 0.12);
    color: var(--accent);
    border-left-color: var(--accent);
  }

  .nav-icon {
    width: 16px;
    height: 16px;
    flex-shrink: 0;
  }

  .sidebar-footer {
    padding: 16px;
    border-top: 1px solid var(--border);
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .footer-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--text-muted);
  }

  .footer-dot.online {
    background: var(--success);
    box-shadow: 0 0 4px var(--success);
  }

  .footer-text {
    font-size: 12px;
    color: var(--text-muted);
  }
</style>
