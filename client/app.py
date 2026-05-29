"""
client/app.py
=============
API REST + interfaz web de chat para el agente MCP.

Uso:
  .\\run_web.ps1
  # o: .\\venv\\Scripts\\python.exe -m uvicorn client.app:app --reload --port 8000

Abre http://localhost:8000
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from agent_core import (
    BASE_PATH,
    MODEL_NAME,
    _env_truthy,
    clear_memory,
    get_mcp_prompt_catalog,
    list_mcp_tools,
    load_memory,
    powerbi_enabled,
    run_agent_query,
)

# =====================================
# MODELOS
# =====================================


class ChatRequest(BaseModel):
    message: str
    max_steps: int = 8


class ChatResponse(BaseModel):
    answer: str
    steps: int
    tools_used: list[str]


class MemoryResponse(BaseModel):
    messages: list[dict]
    count: int


class ToolInfo(BaseModel):
    name: str
    description: str
    server: str


class PromptServer(BaseModel):
    id: str
    label: str
    description: str
    color: str
    prompts: list[str]
    disabled: bool = False
    disabled_hint: str | None = None


# =====================================
# INTERFAZ WEB
# =====================================

WEB_UI = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
  <title>ai-lab · Chat</title>
  <style>
    :root {
      --bg: #0c0e14;
      --surface: #141820;
      --surface-2: #1c2230;
      --border: #2a3142;
      --text: #e8eaef;
      --muted: #8b93a7;
      --accent: #3b82f6;
      --accent-hover: #2563eb;
      --user-bg: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
      --agent-bg: #1c2230;
      --danger: #ef4444;
      --ok: #22c55e;
      --radius: 14px;
      --shadow: 0 4px 24px rgba(0,0,0,.35);
      --font: "Segoe UI", system-ui, -apple-system, sans-serif;
      --mono: "Cascadia Code", "Consolas", monospace;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    html, body { height: 100%; }
    body {
      font-family: var(--font);
      background: var(--bg);
      color: var(--text);
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }
    body::before {
      content: "";
      position: fixed; inset: 0; z-index: -1;
      background:
        radial-gradient(ellipse 80% 50% at 50% -20%, rgba(59,130,246,.12), transparent),
        var(--bg);
    }

    /* HEADER */
    header {
      flex-shrink: 0;
      padding: 12px 20px;
      background: rgba(20, 24, 32, .85);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--border);
      display: flex; align-items: center; justify-content: space-between; gap: 12px;
    }
    .brand { display: flex; align-items: center; gap: 10px; min-width: 0; }
    .brand-icon {
      width: 36px; height: 36px; border-radius: 10px;
      background: linear-gradient(135deg, #3b82f6, #8b5cf6);
      display: grid; place-items: center; font-size: 1rem; flex-shrink: 0;
    }
    .brand h1 { font-size: 1rem; font-weight: 600; white-space: nowrap; }
    .model-badge {
      font-size: 0.7rem; color: var(--muted); background: var(--surface-2);
      border: 1px solid var(--border); padding: 2px 8px; border-radius: 999px;
      max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .header-actions { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
    .btn-ghost {
      background: transparent; border: 1px solid var(--border); color: var(--muted);
      border-radius: 8px; padding: 7px 12px; font-size: 0.8rem; cursor: pointer;
      transition: color .15s, border-color .15s, background .15s;
    }
    .btn-ghost:hover { color: var(--text); border-color: #444c5e; background: var(--surface-2); }
    .btn-ghost.danger:hover { color: var(--danger); border-color: var(--danger); }
    .status-pill {
      display: flex; align-items: center; gap: 6px; font-size: 0.75rem; color: var(--muted);
      padding: 6px 10px; border-radius: 999px; background: var(--surface-2);
      border: 1px solid var(--border);
    }
    #status-dot {
      width: 7px; height: 7px; border-radius: 50%; background: #555;
      transition: background .3s, box-shadow .3s;
    }
    #status-dot.ok { background: var(--ok); box-shadow: 0 0 8px rgba(34,197,94,.5); }
    #status-dot.err { background: var(--danger); }

    /* MAIN */
    main { flex: 1; display: flex; flex-direction: column; min-height: 0; position: relative; }
    #chat-wrap {
      flex: 1; overflow-y: auto; scroll-behavior: smooth;
      padding: 20px 16px 8px;
    }
    #chat {
      max-width: 720px; margin: 0 auto;
      display: flex; flex-direction: column; gap: 20px;
    }

    /* WELCOME */
    .welcome {
      text-align: center; padding: 24px 16px 16px;
      animation: fadeIn .4s ease;
    }
    .welcome h2 { font-size: 1.35rem; font-weight: 600; margin-bottom: 8px; }
    .welcome > p {
      color: var(--muted); font-size: 0.9rem; line-height: 1.5;
      max-width: 480px; margin: 0 auto 20px;
    }
    .mcp-prompts {
      max-width: 720px; margin: 0 auto; text-align: left;
      display: flex; flex-direction: column; gap: 12px;
    }
    .mcp-group {
      background: var(--surface); border: 1px solid var(--border);
      border-radius: 14px; padding: 14px 16px;
      transition: border-color .15s;
    }
    .mcp-group:hover { border-color: #3a4256; }
    .mcp-group.disabled { opacity: .72; }
    .mcp-group-head {
      display: flex; align-items: flex-start; gap: 12px; margin-bottom: 10px;
    }
    .mcp-icon {
      width: 36px; height: 36px; border-radius: 10px; flex-shrink: 0;
      display: grid; place-items: center; font-size: 0.72rem; font-weight: 700;
      color: #fff; letter-spacing: -.02em;
    }
    .mcp-label { font-size: 0.88rem; font-weight: 600; }
    .mcp-desc { font-size: 0.76rem; color: var(--muted); margin-top: 2px; line-height: 1.35; }
    .mcp-disabled-hint {
      font-size: 0.72rem; color: #fbbf24; margin-top: 6px; line-height: 1.4;
    }
    .prompt-row { display: flex; flex-wrap: wrap; gap: 6px; }
    .prompt-chip {
      background: var(--surface-2); border: 1px solid var(--border);
      color: var(--text); padding: 7px 12px; border-radius: 999px;
      font-size: 0.78rem; cursor: pointer; text-align: left; line-height: 1.35;
      transition: border-color .15s, background .15s, transform .1s, box-shadow .15s;
    }
    .prompt-chip:hover:not(:disabled) {
      border-color: var(--accent); background: rgba(59,130,246,.08);
      transform: translateY(-1px); box-shadow: 0 2px 8px rgba(0,0,0,.2);
    }
    .prompt-chip:active:not(:disabled) { transform: translateY(0); }
    .prompt-chip:disabled { opacity: .45; cursor: not-allowed; }
    .welcome-hint {
      text-align: center; font-size: 0.72rem; color: #5c6378;
      margin-top: 14px;
    }
    .suggestions { display: none; }

    /* MESSAGES */
    .row {
      display: flex; gap: 10px; align-items: flex-end;
      animation: slideUp .25s ease;
    }
    .row.user { flex-direction: row-reverse; }
    .avatar {
      width: 32px; height: 32px; border-radius: 10px; flex-shrink: 0;
      display: grid; place-items: center; font-size: 0.75rem; font-weight: 600;
    }
    .row.user .avatar { background: var(--accent); color: #fff; }
    .row.agent .avatar { background: var(--surface-2); border: 1px solid var(--border); color: #7dd3fc; }
    .bubble-wrap { max-width: min(85%, 560px); display: flex; flex-direction: column; gap: 4px; }
    .row.user .bubble-wrap { align-items: flex-end; }
    .bubble {
      padding: 12px 16px; border-radius: var(--radius); line-height: 1.6;
      font-size: 0.92rem; word-break: break-word;
    }
    .row.user .bubble {
      background: var(--user-bg); color: #fff;
      border-bottom-right-radius: 4px; box-shadow: var(--shadow);
    }
    .row.agent .bubble {
      background: var(--agent-bg); border: 1px solid var(--border);
      border-bottom-left-radius: 4px;
    }
    .bubble .content p { margin: 0 0 .6em; }
    .bubble .content p:last-child { margin-bottom: 0; }
    .bubble .content code {
      font-family: var(--mono); font-size: 0.85em;
      background: rgba(0,0,0,.3); padding: 2px 6px; border-radius: 4px;
    }
    .bubble .content pre {
      background: #0a0c10; border: 1px solid var(--border);
      border-radius: 8px; padding: 12px; overflow-x: auto; margin: .5em 0;
      font-family: var(--mono); font-size: 0.82rem; line-height: 1.45;
    }
    .bubble .content pre code { background: none; padding: 0; }
    .bubble .content ul, .bubble .content ol { margin: .4em 0 .6em 1.2em; }
    .bubble .content strong { color: #fff; font-weight: 600; }
    .row.agent .bubble .content strong { color: #f0f4ff; }

    .msg-footer {
      display: flex; align-items: center; gap: 8px; font-size: 0.72rem; color: var(--muted);
    }
    .row.user .msg-footer { justify-content: flex-end; }
    .tool-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 2px; }
    .tool-tag {
      font-size: 0.68rem; padding: 2px 6px; border-radius: 4px;
      background: rgba(59,130,246,.15); color: #93c5fd; font-family: var(--mono);
    }
    .btn-copy {
      background: none; border: none; color: var(--muted); cursor: pointer;
      padding: 2px 6px; border-radius: 4px; font-size: 0.7rem;
    }
    .btn-copy:hover { color: var(--text); background: var(--surface-2); }

    .system-banner {
      text-align: center; font-size: 0.78rem; color: var(--muted);
      padding: 6px 12px; background: var(--surface);
      border: 1px solid var(--border); border-radius: 999px;
      align-self: center; max-width: 90%;
    }
    .error-banner {
      background: rgba(239,68,68,.1); border-color: rgba(239,68,68,.3);
      color: #fca5a5; padding: 12px 16px; border-radius: var(--radius);
      font-size: 0.88rem; max-width: 720px; margin: 0 auto;
    }

    /* TYPING */
    .typing-row .bubble {
      display: flex; flex-direction: column; gap: 10px; min-width: 200px;
    }
    .typing-bar {
      height: 3px; background: var(--border); border-radius: 2px; overflow: hidden;
    }
    .typing-bar span {
      display: block; height: 100%; width: 30%; background: var(--accent);
      border-radius: 2px; animation: indeterminate 1.4s ease infinite;
    }
    @keyframes indeterminate {
      0% { transform: translateX(-100%); }
      100% { transform: translateX(350%); }
    }
    .typing-meta { font-size: 0.75rem; color: var(--muted); }

    /* SCROLL FAB */
    #scroll-fab {
      position: absolute; bottom: 100px; left: 50%; transform: translateX(-50%) translateY(12px);
      opacity: 0; pointer-events: none;
      background: var(--surface); border: 1px solid var(--border);
      color: var(--text); padding: 8px 14px; border-radius: 999px;
      font-size: 0.8rem; cursor: pointer; box-shadow: var(--shadow);
      transition: opacity .2s, transform .2s;
    }
    #scroll-fab.visible { opacity: 1; pointer-events: auto; transform: translateX(-50%) translateY(0); }

    /* INPUT */
    #composer {
      flex-shrink: 0; padding: 12px 16px 16px;
      background: rgba(20, 24, 32, .9); backdrop-filter: blur(12px);
      border-top: 1px solid var(--border);
    }
    .composer-inner {
      max-width: 720px; margin: 0 auto;
      background: var(--surface); border: 1px solid var(--border);
      border-radius: 16px; padding: 10px 10px 10px 14px;
      display: flex; gap: 8px; align-items: flex-end;
      transition: border-color .2s, box-shadow .2s;
    }
    .composer-inner:focus-within {
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(59,130,246,.15);
    }
    #msg-input {
      flex: 1; background: transparent; border: none; color: var(--text);
      font-size: 0.95rem; resize: none; outline: none;
      min-height: 24px; max-height: 140px; line-height: 1.5;
      font-family: inherit;
    }
    #msg-input::placeholder { color: #5c6378; }
    #msg-input:disabled { opacity: .5; }
    .composer-actions { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; }
  .hint-keys { font-size: 0.65rem; color: #5c6378; white-space: nowrap; }
    #send-btn {
      width: 40px; height: 40px; border-radius: 10px; border: none;
      background: var(--accent); color: #fff; cursor: pointer;
      display: grid; place-items: center; transition: background .15s, transform .1s;
    }
    #send-btn:hover:not(:disabled) { background: var(--accent-hover); }
    #send-btn:active:not(:disabled) { transform: scale(.96); }
    #send-btn:disabled { opacity: .35; cursor: not-allowed; }
    #send-btn svg { width: 18px; height: 18px; }

    /* SIDEBAR */
    #overlay {
      position: fixed; inset: 0; background: rgba(0,0,0,.5);
      opacity: 0; pointer-events: none; transition: opacity .25s; z-index: 20;
    }
    #overlay.open { opacity: 1; pointer-events: auto; }
    #sidebar {
      position: fixed; top: 0; right: 0; bottom: 0; width: min(360px, 92vw);
      background: var(--surface); border-left: 1px solid var(--border);
      z-index: 30; transform: translateX(100%); transition: transform .25s ease;
      display: flex; flex-direction: column;
    }
    #sidebar.open { transform: translateX(0); }
    .sidebar-head {
      padding: 16px; border-bottom: 1px solid var(--border);
      display: flex; justify-content: space-between; align-items: center;
    }
    .sidebar-head h2 { font-size: 0.9rem; font-weight: 600; }
    #tools-search {
      margin: 12px 16px 0; padding: 8px 12px; border-radius: 8px;
      border: 1px solid var(--border); background: var(--bg); color: var(--text);
      font-size: 0.85rem; outline: none; width: calc(100% - 32px);
    }
    #tools-search:focus { border-color: var(--accent); }
    #tools-list { flex: 1; overflow-y: auto; padding: 12px 16px 24px; }
    .tool-server { font-size: 0.68rem; text-transform: uppercase; letter-spacing: .06em;
      color: var(--muted); margin: 16px 0 6px; display: flex; align-items: center; gap: 8px; }
    .tool-server-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
    .sidebar-prompts { display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 8px; }
    .sidebar-prompt {
      background: rgba(59,130,246,.08); border: 1px solid var(--border);
      color: var(--text); padding: 5px 10px; border-radius: 999px;
      font-size: 0.72rem; cursor: pointer; line-height: 1.3; text-align: left;
      transition: border-color .15s, background .15s;
    }
    .sidebar-prompt:hover:not(:disabled) { border-color: var(--accent); background: rgba(59,130,246,.15); }
    .sidebar-prompt:disabled { opacity: .4; cursor: not-allowed; }
    .tool-item {
      padding: 10px 12px; border-radius: 8px; margin-bottom: 4px;
      background: var(--surface-2); border: 1px solid transparent;
      cursor: default; transition: border-color .15s;
    }
    .tool-item:hover { border-color: var(--border); }
    .tool-name { font-family: var(--mono); font-size: 0.78rem; color: #7dd3fc; }
    .tool-desc { font-size: 0.75rem; color: var(--muted); margin-top: 4px; line-height: 1.4; }

    /* TOAST */
    #toast {
      position: fixed; bottom: 90px; left: 50%; transform: translateX(-50%) translateY(20px);
      background: var(--surface-2); border: 1px solid var(--border);
      color: var(--text); padding: 10px 18px; border-radius: 10px; font-size: 0.85rem;
      box-shadow: var(--shadow); opacity: 0; pointer-events: none;
      transition: opacity .25s, transform .25s; z-index: 50;
    }
    #toast.show { opacity: 1; transform: translateX(-50%) translateY(0); }

    @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
    @keyframes slideUp { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

    @media (max-width: 600px) {
      header { padding: 10px 12px; }
      .model-badge { display: none; }
      .status-pill span:last-child { display: none; }
      .hint-keys { display: none; }
    }
  </style>
</head>
<body>

<header>
  <div class="brand">
    <div class="brand-icon" aria-hidden="true">AI</div>
    <div>
      <h1>ai-lab</h1>
      <div class="model-badge" id="model-badge" title="Modelo activo">—</div>
    </div>
  </div>
  <div class="header-actions">
    <div class="status-pill" title="Estado del servidor">
      <span id="status-dot"></span>
      <span id="status-text">conectando</span>
    </div>
    <button type="button" class="btn-ghost" id="tools-btn" aria-label="Ver herramientas MCP">Tools</button>
    <button type="button" class="btn-ghost" id="examples-btn" aria-label="Ver ejemplos por MCP">Ejemplos</button>
    <button type="button" class="btn-ghost danger" id="clear-btn" aria-label="Borrar historial">Limpiar</button>
  </div>
</header>

<main>
  <div id="chat-wrap" role="log" aria-live="polite" aria-relevant="additions">
    <div id="chat"></div>
  </div>
  <button type="button" id="scroll-fab" aria-label="Ir al final">↓ Nuevos mensajes</button>

  <div id="composer">
    <div class="composer-inner">
      <textarea id="msg-input" rows="1" placeholder="Pregunta sobre el proyecto, código, git…" aria-label="Mensaje"></textarea>
      <div class="composer-actions">
        <span class="hint-keys">Enter enviar · Shift+Enter nueva línea</span>
        <button type="button" id="send-btn" disabled aria-label="Enviar">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2L11 13"/><path d="M22 2L15 22L11 13L2 9L22 2Z"/></svg>
        </button>
      </div>
    </div>
  </div>
</main>

<div id="overlay" aria-hidden="true"></div>
<aside id="sidebar" aria-label="Panel de herramientas">
  <div class="sidebar-head">
    <h2 id="sidebar-title">Herramientas MCP</h2>
    <button type="button" class="btn-ghost" id="sidebar-close" aria-label="Cerrar">✕</button>
  </div>
  <input type="search" id="tools-search" placeholder="Buscar tool…" autocomplete="off">
  <div id="tools-list">Cargando…</div>
</aside>

<div id="toast" role="status"></div>

<script>
  const chatWrap = document.getElementById('chat-wrap');
  const chat = document.getElementById('chat');
  const input = document.getElementById('msg-input');
  const sendBtn = document.getElementById('send-btn');
  const dot = document.getElementById('status-dot');
  const statusTx = document.getElementById('status-text');
  const modelBadge = document.getElementById('model-badge');
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('overlay');
  const toolsList = document.getElementById('tools-list');
  const toolsSearch = document.getElementById('tools-search');
  const scrollFab = document.getElementById('scroll-fab');
  const toast = document.getElementById('toast');

  let isBusy = false;
  let stickToBottom = true;
  let typingTimer = null;
  let allToolsCache = [];
  let promptsCatalog = [];
  let sidebarMode = 'tools';

  const SERVER_ABBR = {
    filesystem: 'FS', custom: 'AI', git: 'Git', fetch: 'Web',
    thinking: 'Think', powerbi: 'PBI',
  };

  function escapeHtml(s) {
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  function renderMarkdown(text) {
    let h = escapeHtml(text);
    h = h.replace(/```([\\s\\S]*?)```/g, (_, code) => `<pre><code>${code.trim()}</code></pre>`);
    h = h.replace(/`([^`]+)`/g, '<code>$1</code>');
    h = h.replace(/\\*\\*([^*]+)\\*\\*/g, '<strong>$1</strong>');
    h = h.replace(/^### (.+)$/gm, '<p><strong>$1</strong></p>');
    h = h.replace(/^## (.+)$/gm, '<p><strong>$1</strong></p>');
    h = h.replace(/^[-*] (.+)$/gm, '<li>$1</li>');
    h = h.replace(/(<li>.*<\\/li>\\n?)+/gs, m => `<ul>${m}</ul>`);
  h = h.split(/\\n{2,}/).map(p => {
      if (/^<(pre|ul|p)/.test(p.trim())) return p;
      return `<p>${p.replace(/\\n/g, '<br>')}</p>`;
    }).join('');
    return h;
  }

  function showToast(msg) {
    toast.textContent = msg;
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 2800);
  }

  function scrollToBottom(smooth = true) {
    chatWrap.scrollTo({ top: chatWrap.scrollHeight, behavior: smooth ? 'smooth' : 'auto' });
  }

  function updateScrollFab() {
    const nearBottom = chatWrap.scrollHeight - chatWrap.scrollTop - chatWrap.clientHeight < 80;
    stickToBottom = nearBottom;
    scrollFab.classList.toggle('visible', !nearBottom && chat.children.length > 1);
  }

  chatWrap.addEventListener('scroll', updateScrollFab);
  scrollFab.addEventListener('click', () => { stickToBottom = true; scrollToBottom(); });

  function hideWelcome() {
    const w = document.getElementById('welcome');
    if (w) w.remove();
  }

  function usePrompt(text, { send = true, closeSidebar = false } = {}) {
    if (!text || isBusy) return;
    if (closeSidebar) openSidebar(false);
    if (send) {
      input.value = text;
      sendMessage();
      return;
    }
    input.value = text;
    resizeInput();
    input.focus();
    showToast('Frase cargada — Enter para enviar');
  }

  function makePromptChip(text, { disabled = false, compact = false } = {}) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = compact ? 'sidebar-prompt' : 'prompt-chip';
    btn.textContent = text;
    btn.disabled = disabled || isBusy;
    if (!disabled) {
      btn.addEventListener('click', () => usePrompt(text, { send: true, closeSidebar: compact }));
    }
    return btn;
  }

  function renderWelcomePrompts(servers) {
    const box = document.getElementById('mcp-prompts');
    if (!box) return;
    box.innerHTML = '';
    if (!servers.length) {
      box.innerHTML = '<p style="color:var(--muted);font-size:.85rem;text-align:center">No hay servidores MCP activos</p>';
      return;
    }
    servers.forEach(s => {
      const group = document.createElement('div');
      group.className = 'mcp-group' + (s.disabled ? ' disabled' : '');
      const abbr = SERVER_ABBR[s.id] || s.label.slice(0, 2).toUpperCase();
      group.innerHTML = `
        <div class="mcp-group-head">
          <div class="mcp-icon" style="background:${escapeHtml(s.color)}">${escapeHtml(abbr)}</div>
          <div>
            <div class="mcp-label">${escapeHtml(s.label)}</div>
            <div class="mcp-desc">${escapeHtml(s.description)}</div>
            ${s.disabled && s.disabled_hint ? `<div class="mcp-disabled-hint">${escapeHtml(s.disabled_hint)}</div>` : ''}
          </div>
        </div>
        <div class="prompt-row"></div>`;
      const row = group.querySelector('.prompt-row');
      s.prompts.forEach(p => row.appendChild(makePromptChip(p, { disabled: s.disabled })));
      box.appendChild(group);
    });
  }

  function showWelcome() {
    if (document.getElementById('welcome')) return;
    const el = document.createElement('div');
    el.id = 'welcome';
    el.className = 'welcome';
    el.innerHTML = `
      <h2>¿En qué te ayudo?</h2>
      <p>Elige una frase según el servidor MCP. Cada una usa las tools reales del proyecto.</p>
      <div class="mcp-prompts" id="mcp-prompts"></div>
      <p class="welcome-hint">Clic en una frase para enviar · Tools para ver todas las herramientas</p>`;
    chat.appendChild(el);
    renderWelcomePrompts(promptsCatalog);
  }

  function addSystemBanner(text) {
    hideWelcome();
    const el = document.createElement('div');
    el.className = 'system-banner';
    el.textContent = text;
    chat.appendChild(el);
    if (stickToBottom) scrollToBottom();
  }

  function addError(text) {
    hideWelcome();
    const el = document.createElement('div');
    el.className = 'error-banner';
    el.textContent = text;
    chat.appendChild(el);
    if (stickToBottom) scrollToBottom();
  }

  function addMessage(role, text, meta = {}) {
    hideWelcome();
    const row = document.createElement('div');
    row.className = `row ${role}`;

    const avatar = document.createElement('div');
    avatar.className = 'avatar';
    avatar.textContent = role === 'user' ? 'Tú' : 'AI';
    avatar.setAttribute('aria-hidden', 'true');

    const wrap = document.createElement('div');
    wrap.className = 'bubble-wrap';

    const bubble = document.createElement('div');
    bubble.className = 'bubble';
    const content = document.createElement('div');
    content.className = 'content';
    if (role === 'agent') content.innerHTML = renderMarkdown(text);
    else content.textContent = text;
    bubble.appendChild(content);
    wrap.appendChild(bubble);

    const footer = document.createElement('div');
    footer.className = 'msg-footer';
    const time = document.createElement('span');
    time.textContent = new Date().toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' });
    footer.appendChild(time);

    if (role === 'agent') {
      const copyBtn = document.createElement('button');
      copyBtn.type = 'button';
      copyBtn.className = 'btn-copy';
      copyBtn.textContent = 'Copiar';
      copyBtn.addEventListener('click', async () => {
        await navigator.clipboard.writeText(text);
        showToast('Respuesta copiada');
      });
      footer.appendChild(copyBtn);
      if (meta.tools?.length) {
        const tags = document.createElement('div');
        tags.className = 'tool-tags';
        meta.tools.slice(0, 5).forEach(t => {
          const tag = document.createElement('span');
          tag.className = 'tool-tag';
          tag.textContent = t.replace(/^\\w+__/, '');
          tags.appendChild(tag);
        });
        if (meta.tools.length > 5) {
          const more = document.createElement('span');
          more.className = 'tool-tag';
          more.textContent = `+${meta.tools.length - 5}`;
          tags.appendChild(more);
        }
        wrap.appendChild(tags);
      }
      if (meta.steps) {
        const steps = document.createElement('span');
        steps.textContent = ` · ${meta.steps} paso(s)`;
        footer.appendChild(steps);
      }
    }
    wrap.appendChild(footer);
    row.append(avatar, wrap);
    chat.appendChild(row);
    if (stickToBottom) scrollToBottom();
  }

  function addTyping() {
    hideWelcome();
    const row = document.createElement('div');
    row.className = 'row agent typing-row';
    row.id = 'typing-row';
    row.innerHTML = `
      <div class="avatar" aria-hidden="true">AI</div>
      <div class="bubble-wrap">
        <div class="bubble">
          <div class="typing-bar"><span></span></div>
          <div class="typing-meta" id="typing-meta">Iniciando agente…</div>
        </div>
      </div>`;
    chat.appendChild(row);
    let sec = 0;
    typingTimer = setInterval(() => {
      sec++;
      const el = document.getElementById('typing-meta');
      if (!el) return;
      const m = Math.floor(sec / 60);
      const s = sec % 60;
      const t = m ? `${m}:${String(s).padStart(2,'0')}` : `${s}s`;
      el.textContent = `Procesando (${t}) — puede tardar con LM Studio y tools MCP`;
    }, 1000);
    if (stickToBottom) scrollToBottom();
  }

  function removeTyping() {
    clearInterval(typingTimer);
    document.getElementById('typing-row')?.remove();
  }

  function setBusy(busy) {
    isBusy = busy;
    input.disabled = busy;
    sendBtn.disabled = busy || dot.classList.contains('err');
    if (document.getElementById('mcp-prompts')) renderWelcomePrompts(promptsCatalog);
  }

  function setStatus(ok, model) {
    dot.className = ok ? 'ok' : 'err';
    statusTx.textContent = ok ? 'listo' : 'offline';
    if (model) modelBadge.textContent = model;
    sendBtn.disabled = isBusy || !ok;
  }

  function resizeInput() {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 140) + 'px';
  }

  function openSidebar(open, mode = sidebarMode) {
    sidebarMode = mode;
    sidebar.classList.toggle('open', open);
    overlay.classList.toggle('open', open);
    const title = document.getElementById('sidebar-title');
    const search = document.getElementById('tools-search');
    if (title) title.textContent = mode === 'examples' ? 'Ejemplos por MCP' : 'Herramientas MCP';
    if (search) {
      search.style.display = '';
      search.placeholder = mode === 'examples' ? 'Buscar ejemplo…' : 'Buscar tool…';
      if (open) search.value = '';
    }
    if (open) {
      if (mode === 'examples') renderExamplesPanel();
      else loadTools();
    }
  }

  function renderExamplesPanel(filter = '') {
    const q = filter.trim().toLowerCase();
    toolsList.innerHTML = '';
    const servers = q
      ? promptsCatalog.filter(s =>
          (s.label + s.description + s.prompts.join(' ')).toLowerCase().includes(q))
      : promptsCatalog;
    if (!servers.length) {
      toolsList.innerHTML = '<p style="color:var(--muted);font-size:.85rem">Sin resultados</p>';
      return;
    }
    servers.forEach(s => {
      const h = document.createElement('div');
      h.className = 'tool-server';
      h.innerHTML = `<span class="tool-server-dot" style="background:${escapeHtml(s.color)}"></span>${escapeHtml(s.label)}`;
      toolsList.appendChild(h);
      if (s.disabled && s.disabled_hint) {
        const hint = document.createElement('p');
        hint.style.cssText = 'font-size:.72rem;color:#fbbf24;margin:0 0 8px;line-height:1.4';
        hint.textContent = s.disabled_hint;
        toolsList.appendChild(hint);
      }
      const row = document.createElement('div');
      row.className = 'sidebar-prompts';
      s.prompts.forEach(p => row.appendChild(makePromptChip(p, { disabled: s.disabled, compact: true })));
      toolsList.appendChild(row);
    });
  }

  async function checkHealth() {
    try {
      const r = await fetch('/health');
      if (r.ok) {
        const d = await r.json();
        setStatus(true, d.model);
        let banner = `Conectado · ${d.model}`;
        if (d.powerbi_mcp) banner += ' · Power BI MCP activo';
        addSystemBanner(banner);
      } else setStatus(false);
    } catch {
      setStatus(false);
      addError('No hay conexión con la API. Ejecuta .\\\\run_web.ps1 y recarga esta página.');
    }
  }

  async function loadHistory() {
    try {
      const r = await fetch('/memory');
      const d = await r.json();
      if (d.count > 0) {
        hideWelcome();
        addSystemBanner(`${d.count} mensajes en el historial`);
        d.messages.slice(-8).forEach(m => {
          addMessage(m.role === 'user' ? 'user' : 'agent', m.content);
        });
      } else showWelcome();
    } catch { showWelcome(); }
  }

  async function sendMessage() {
    const text = input.value.trim();
    if (!text || isBusy) return;
    input.value = '';
    resizeInput();
    setBusy(true);
    addMessage('user', text);
    addTyping();
    try {
      const r = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, max_steps: 8 }),
      });
      removeTyping();
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        const detail = typeof err.detail === 'string' ? err.detail : r.statusText;
        addError(detail || 'Error del servidor');
      } else {
        const d = await r.json();
        addMessage('agent', d.answer, { steps: d.steps, tools: d.tools_used });
      }
    } catch (e) {
      removeTyping();
      addError(`Error de red: ${e.message}`);
    }
    setBusy(false);
    input.focus();
  }

  function renderToolsList(tools, filter = '') {
    const q = filter.trim().toLowerCase();
    const filtered = q
      ? tools.filter(t => (t.name + t.description + t.server).toLowerCase().includes(q))
      : tools;
    if (!filtered.length) {
      toolsList.innerHTML = '<p style="color:var(--muted);font-size:.85rem">Sin resultados</p>';
      return;
    }
    const byServer = {};
    filtered.forEach(t => {
      if (!byServer[t.server]) byServer[t.server] = [];
      byServer[t.server].push(t);
    });
    const serverMeta = {};
    promptsCatalog.forEach(s => { serverMeta[s.id] = s; });
    toolsList.innerHTML = '';
    Object.entries(byServer).forEach(([server, items]) => {
      const meta = serverMeta[server] || {};
      const h = document.createElement('div');
      h.className = 'tool-server';
      const dotColor = meta.color || 'var(--muted)';
      h.innerHTML = `<span class="tool-server-dot" style="background:${escapeHtml(dotColor)}"></span>${escapeHtml(meta.label || server)}`;
      toolsList.appendChild(h);
      if (meta.prompts?.length) {
        const row = document.createElement('div');
        row.className = 'sidebar-prompts';
        meta.prompts.slice(0, 2).forEach(p =>
          row.appendChild(makePromptChip(p, { disabled: meta.disabled, compact: true })));
        toolsList.appendChild(row);
      }
      items.forEach(t => {
        const item = document.createElement('div');
        item.className = 'tool-item';
        const desc = (t.description || '').slice(0, 100);
        item.innerHTML = `<div class="tool-name">${escapeHtml(t.name)}</div><div class="tool-desc">${escapeHtml(desc)}</div>`;
        toolsList.appendChild(item);
      });
    });
  }

  async function loadPrompts() {
    try {
      const r = await fetch('/prompts');
      const d = await r.json();
      promptsCatalog = d.servers || [];
      const w = document.getElementById('mcp-prompts');
      if (w) renderWelcomePrompts(promptsCatalog);
    } catch {
      promptsCatalog = [];
    }
  }

  async function loadTools() {
    toolsList.textContent = 'Cargando…';
    try {
      const r = await fetch('/tools');
      const d = await r.json();
      allToolsCache = d.tools || [];
      renderToolsList(allToolsCache, toolsSearch.value);
    } catch {
      toolsList.innerHTML = '<p style="color:var(--muted)">Error al cargar</p>';
    }
  }

  toolsSearch.addEventListener('input', () => {
    if (sidebarMode === 'examples') renderExamplesPanel(toolsSearch.value);
    else renderToolsList(allToolsCache, toolsSearch.value);
  });

  document.getElementById('tools-btn').addEventListener('click', () => openSidebar(true, 'tools'));
  document.getElementById('examples-btn').addEventListener('click', () => openSidebar(true, 'examples'));
  document.getElementById('sidebar-close').addEventListener('click', () => openSidebar(false));
  overlay.addEventListener('click', () => openSidebar(false));

  document.getElementById('clear-btn').addEventListener('click', async () => {
    if (!confirm('¿Borrar todo el historial de conversación?')) return;
    await fetch('/memory', { method: 'DELETE' });
    chat.innerHTML = '';
    await loadPrompts();
    showWelcome();
    showToast('Historial borrado');
  });

  input.addEventListener('input', resizeInput);
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!sendBtn.disabled) sendMessage();
    }
  });
  sendBtn.addEventListener('click', sendMessage);

  (async () => {
    await checkHealth();
    await loadPrompts();
    await loadHistory();
    input.focus();
  })();
</script>
</body>
</html>"""


# =====================================
# FASTAPI
# =====================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("ai-lab web — http://localhost:8000")
    yield


app = FastAPI(
    title="ai-lab Agent API",
    description="Chat web + API REST para el agente MCP",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=HTMLResponse)
async def web_ui():
    return WEB_UI


REPORTS_DIR = BASE_PATH / "data" / "reports"


@app.get("/reports/{filename}")
async def get_report(filename: str):
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=404, detail="Informe no encontrado.")
    path = REPORTS_DIR / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Informe no encontrado.")
    return FileResponse(path, media_type="text/html; charset=utf-8")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model": MODEL_NAME,
        "base": str(BASE_PATH),
        "lm_studio": "http://localhost:1234/v1",
        "powerbi_mcp": powerbi_enabled(),
        "powerbi_readonly": _env_truthy("AI_LAB_POWERBI_READONLY"),
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="El mensaje no puede estar vacio.")
    try:
        result = await run_agent_query(req.message, max_steps=req.max_steps)
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return ChatResponse(**result)


@app.get("/memory", response_model=MemoryResponse)
async def get_memory():
    history = load_memory()
    return MemoryResponse(messages=history, count=len(history))


@app.delete("/memory")
async def delete_memory():
    clear_memory()
    return {"status": "ok", "message": "Historial borrado."}


@app.get("/tools")
async def list_tools():
    tools = await list_mcp_tools()
    return {
        "tools": [ToolInfo(**t) for t in tools],
        "count": len(tools),
    }


@app.get("/prompts")
async def list_prompts():
    servers = get_mcp_prompt_catalog()
    return {
        "servers": [PromptServer(**s) for s in servers],
        "count": len(servers),
    }
