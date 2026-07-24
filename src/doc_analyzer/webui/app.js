/* COEBOT frontend — vanilla JS, talks to the Starlette API. */
'use strict';

const S = {
  user: null,
  chats: [],
  currentId: null,
  messages: [],
  privateMode: false,
  bannerDismissed: false,
  models: [],
  selectedModel: '',
  pending: [],
  memory: [],
  view: 'history',
  busy: false,
  registerMode: false,
};

const $ = (id) => document.getElementById(id);
const api = async (path, opts = {}) => {
  const r = await fetch(path, {
    headers: opts.body instanceof FormData ? {} : { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    ...opts,
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
  return data;
};

/* ---------- markdown renderer (headings/tables/nested lists/quotes) --- */
const esc = (s) => s.replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

/* Inline spans. Code spans are extracted first so *, _ and [ inside
   backticks are never mangled by the emphasis/link passes. */
function inline(t) {
  const codes = [];
  t = esc(t).replace(/`([^`]+)`/g, (_, c) => { codes.push(c); return `\u0000${codes.length - 1}\u0000`; });
  t = t
    .replace(/\*\*\*(.+?)\*\*\*/g, '<b><i>$1</i></b>')
    .replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')
    .replace(/__(.+?)__/g, '<b>$1</b>')
    .replace(/(^|[\s([])\*([^*\n]+)\*/g, '$1<i>$2</i>')
    .replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  return t.replace(/\u0000(\d+)\u0000/g, (_, i) => `<code>${codes[+i]}</code>`);
}

function md(src) {
  const lines = String(src || '').replace(/\r\n?/g, '\n').split('\n');
  const out = [];
  const lists = [];            // stack: {type:'ol'|'ul', indent, wrap}
  let para = [], quote = [];
  let inCode = false, codeBuf = [];

  // Top-level ordered lists get the blue-circle "steps" treatment; its
  // flex layout needs the item content wrapped in a <span> (wrap=true).
  const closeLi = (t) => (t.wrap ? '</span></li>' : '</li>');
  const flushPara = () => { if (para.length) { out.push(`<p>${para.map(inline).join(' ')}</p>`); para = []; } };
  const flushQuote = () => { if (quote.length) { out.push(`<blockquote>${quote.map(inline).join('<br>')}</blockquote>`); quote = []; } };
  const closeLists = (toIndent = -1) => {
    while (lists.length && lists[lists.length - 1].indent > toIndent) {
      const t = lists.pop();
      out.push(closeLi(t), t.type === 'ol' ? '</ol>' : '</ul>');
    }
  };

  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i];

    if (raw.trim().startsWith('```')) {
      flushPara(); flushQuote();
      if (inCode) { closeLists(); out.push(`<pre><code>${esc(codeBuf.join('\n'))}</code></pre>`); codeBuf = []; }
      inCode = !inCode; continue;
    }
    if (inCode) { codeBuf.push(raw); continue; }

    // Table: a |...| row followed by a |---|---| separator row.
    if (/^\s*\|.*\|\s*$/.test(raw) && i + 1 < lines.length &&
        /^\s*[|\s:-]+\s*$/.test(lines[i + 1]) && lines[i + 1].includes('-')) {
      flushPara(); flushQuote(); closeLists();
      const rows = [raw];
      let j = i + 1;
      while (j < lines.length && /^\s*\|.*\|\s*$/.test(lines[j])) rows.push(lines[j++]);
      i = j - 1;
      const cells = (r) => r.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => inline(c.trim()));
      out.push('<div class="tbl-wrap"><table><thead><tr>'
        + cells(rows[0]).map((h) => `<th>${h}</th>`).join('')
        + '</tr></thead><tbody>'
        + rows.slice(2).map((r) => `<tr>${cells(r).map((c) => `<td>${c}</td>`).join('')}</tr>`).join('')
        + '</tbody></table></div>');
      continue;
    }

    if (raw.trim() === '') { flushPara(); flushQuote(); continue; }

    // Horizontal rule (checked before lists so "- - -" isn't an item).
    if (/^\s*([-*_])\s*(\1\s*){2,}$/.test(raw)) { flushPara(); flushQuote(); closeLists(); out.push('<hr>'); continue; }

    const h = raw.match(/^\s*(#{1,6})\s+(.*)$/);
    if (h) {
      flushPara(); flushQuote(); closeLists();
      // Style guide restricts model output to '### ' (three hashes), so
       //   1–3 hashes → h3 (the main heading in a chat bubble)
       //   4+ hashes  → h4 (rarely produced; still supported)
      const tag = h[1].length <= 3 ? 'h3' : 'h4';
      out.push(`<${tag}>${inline(h[2].replace(/\s*#+\s*$/, ''))}</${tag}>`);
      continue;
    }

    const q = raw.match(/^\s*>\s?(.*)$/);
    if (q) { flushPara(); closeLists(); quote.push(q[1]); continue; }
    flushQuote();

    const m = raw.match(/^(\s*)(?:(\d+)[.)]|[-*•+])\s+(.*)$/);
    if (m) {
      flushPara();
      const indent = m[1].replace(/\t/g, '  ').length;
      const type = m[2] !== undefined ? 'ol' : 'ul';
      let top = lists[lists.length - 1];
      if (top && indent <= top.indent) {
        closeLists(indent);
        top = lists[lists.length - 1];
        if (top && top.type !== type) {          // same level, list type changed
          out.push(closeLi(top), top.type === 'ol' ? '</ol>' : '</ul>');
          lists.pop();
        } else if (top) {
          out.push(closeLi(top));                // sibling item
        }
      }
      if (!lists.length || indent > lists[lists.length - 1].indent) {
        const wrap = type === 'ol' && lists.length === 0;
        out.push(type === 'ol' ? (wrap ? '<ol class="steps">' : '<ol>') : '<ul>');
        lists.push({ type, indent, wrap });
      }
      const t = lists[lists.length - 1];
      out.push(t.wrap ? `<li><span>${inline(m[3])}` : `<li>${inline(m[3])}`);
      continue;
    }

    // Indented plain line while a list is open → continuation of that item.
    if (lists.length && /^\s/.test(raw)) { out.push(' ' + inline(raw.trim())); continue; }

    closeLists();
    para.push(raw.trim());
  }
  if (inCode && codeBuf.length) out.push(`<pre><code>${esc(codeBuf.join('\n'))}</code></pre>`);
  flushPara(); flushQuote(); closeLists();
  return out.join('');
}

/* ---------- time formatting ---------- */
const fmtTime = (iso) => {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d)) return '';
  return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
};
const fmtRel = (iso) => {
  if (!iso) return '';
  const d = new Date(iso); if (isNaN(d)) return '';
  const now = new Date();
  const days = Math.floor((new Date(now.getFullYear(), now.getMonth(), now.getDate()) -
                           new Date(d.getFullYear(), d.getMonth(), d.getDate())) / 86400000);
  if (days <= 0) return fmtTime(iso);
  if (days === 1) return 'Yesterday';
  if (days < 7) return `${days} days ago`;
  return d.toLocaleDateString([], { day: 'numeric', month: 'short' });
};

const toast = (msg) => {
  const t = $('toast');
  t.textContent = msg; t.classList.remove('hidden');
  clearTimeout(t._h); t._h = setTimeout(() => t.classList.add('hidden'), 2600);
};

/* ================= RENDER ================= */

function renderAuth() {
  $('login-view').classList.toggle('hidden', !!S.user);
  $('app-view').classList.toggle('hidden', !S.user);
  if (S.user) $('header-avatar').textContent = S.user[0].toUpperCase();
}

function renderRecents() {
  const box = $('recents');
  box.innerHTML = '';
  let items = S.chats;
  if (S.view === 'favorites') items = items.filter((c) => c.favorite);
  $('recents-label').textContent =
    S.view === 'favorites' ? 'FAVORITES' : S.view === 'saved' ? 'SAVED CHATS' : 'RECENT CHATS';
  document.querySelectorAll('.nav-item[data-view]').forEach((b) =>
    b.classList.toggle('active', b.dataset.view === S.view));
  if (!items.length) {
    box.innerHTML = `<div class="recents-empty">${S.view === 'favorites' ? 'No favorites yet — hover a chat and press the star.' : 'No chats yet.'}</div>`;
    return;
  }
  for (const c of items) {
    const row = document.createElement('button');
    row.className = 'chat-row' + (c.id === S.currentId && !S.privateMode ? ' active' : '');
    row.innerHTML = `
      <svg viewBox="0 0 24 24"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
      <span class="row-title"></span>
      <span class="row-time">${fmtRel(c.updated_at)}</span>
      <span class="row-btns">
        <button class="fav ${c.favorite ? 'fav-on' : ''}" title="Favorite">
          <svg viewBox="0 0 24 24"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
        </button>
        <button class="del" title="Delete">
          <svg viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
      </span>`;
    row.querySelector('.row-title').textContent = c.title;
    row.addEventListener('click', (e) => {
      if (e.target.closest('.fav')) return favToggle(c);
      if (e.target.closest('.del')) return delChat(c);
      openChat(c.id);
    });
    box.appendChild(row);
  }
}

function messageEl(m) {
  const wrap = document.createElement('div');
  const isUser = m.role === 'user';
  wrap.className = 'msg ' + (isUser ? 'user' : 'ai');
  const atts = (m.attachments || [])
    .map((n) => `<span class="att-tag">📄 ${esc(n)}</span>`).join('');
  const meta = m.ts
    ? `<div class="msg-meta">${fmtTime(m.ts)}${isUser ? ' <span class="ticks">✓✓</span>' : ''}</div>`
    : '';
  if (isUser) {
    wrap.innerHTML = `<div class="bubble">${atts}${md(m.content)}${meta}</div>`;
  } else {
    wrap.innerHTML = `
      <div class="ai-avatar">
        <svg viewBox="0 0 24 24"><rect x="5" y="8" width="14" height="11" rx="3"/><circle cx="9.5" cy="13" r="1" fill="currentColor" stroke="none"/><circle cx="14.5" cy="13" r="1" fill="currentColor" stroke="none"/><path d="M12 8V5"/><circle cx="12" cy="4" r="1"/><path d="M9 16.2c.8.6 1.8 1 3 1s2.2-.4 3-1"/></svg>
      </div>
      <div class="bubble">${atts}${md(m.content)}${meta}</div>`;
  }
  return wrap;
}

function renderMessages() {
  const box = $('messages');
  box.innerHTML = '';
  for (const m of S.messages) box.appendChild(messageEl(m));
  $('hero').classList.toggle('hidden', S.messages.length > 0);
  $('hero-title').textContent = S.privateMode ? 'Private Chat' : 'COEBOT';
  $('hero-cap').textContent = S.privateMode
    ? 'Temporary session — nothing you say here is saved or remembered.'
    : 'Your smart assistant for PNM. Ask anything about your documents.';
  $('chat-scroll').scrollTop = $('chat-scroll').scrollHeight;
}

function renderPrivate() {
  $('private-toggle').checked = S.privateMode;
  $('private-banner').classList.toggle('hidden', !S.privateMode || S.bannerDismissed);
  $('under-input').classList.toggle('hidden', !S.privateMode);
}

function renderChips() {
  const rail = $('chip-rail');
  rail.innerHTML = '';
  for (const name of S.pending) {
    const chip = document.createElement('span');
    chip.className = 'chip';
    chip.innerHTML = `📄 <span></span>
      <button title="Remove"><svg viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>`;
    chip.querySelector('span').textContent = name;
    chip.querySelector('button').addEventListener('click', async () => {
      S.pending = S.pending.filter((n) => n !== name);
      renderChips();
      api('/api/pending', { method: 'POST', body: JSON.stringify({ names: S.pending, private: S.privateMode }) }).catch(() => {});
    });
    rail.appendChild(chip);
  }
}

function renderModel() {
  $('model-name').textContent = S.selectedModel
    ? 'Model: ' + S.selectedModel.replace(/\.gguf$/i, '')
    : 'No model';
}

function renderAll() {
  renderAuth();
  if (!S.user) return;
  renderRecents(); renderMessages(); renderPrivate(); renderChips(); renderModel();
}

/* ================= ACTIONS ================= */

async function boot() {
  try {
    const d = await api('/api/bootstrap');
    if (!d.user) {
      S.user = null;
      S.registerMode = !d.has_users;
      updateLoginMode();
      renderAuth();
      return;
    }
    S.user = d.user;
    S.chats = d.chats || [];
    S.models = d.models || [];
    S.selectedModel = d.selected || '';
    S.pending = d.pending || [];
    S.memory = d.memory || [];
    if (d.current_chat) {
      S.currentId = d.current_chat.id;
      S.messages = d.current_chat.messages || [];
    }
    renderAll();
  } catch (e) {
    toast('Cannot reach COEBOT server: ' + e.message);
  }
}

function updateLoginMode() {
  $('card-login').classList.toggle('hidden', S.registerMode);
  $('card-register').classList.toggle('hidden', !S.registerMode);
  $('li-error').classList.add('hidden');
  $('reg-error').classList.add('hidden');
}

const authFail = (id, msg) => { const e = $(id); e.textContent = msg; e.classList.remove('hidden'); };

async function doLogin() {
  const username = $('li-user').value.trim();
  const password = $('li-pass').value;
  $('li-error').classList.add('hidden');
  if (!username || !password) return authFail('li-error', 'Please fill in your username and password.');
  try {
    await api('/api/login', {
      method: 'POST',
      body: JSON.stringify({ username, password, remember: $('li-remember').checked }),
    });
    $('li-pass').value = '';
    await boot();
  } catch (e) { authFail('li-error', e.message); }
}

async function doRegister() {
  const username = $('reg-user').value.trim();
  const password = $('reg-pass').value;
  const confirm = $('reg-pass2').value;
  $('reg-error').classList.add('hidden');
  if (username.length < 3) return authFail('reg-error', 'Username must be at least 3 characters.');
  if (password.length < 8 || !/[A-Z]/.test(password) || !/[a-z]/.test(password) ||
      !/[0-9]/.test(password) || !/[^A-Za-z0-9]/.test(password))
    return authFail('reg-error', 'Password needs at least 8 characters with uppercase, lowercase, number, and symbol.');
  if (password !== confirm) return authFail('reg-error', 'Passwords do not match.');
  if (!$('reg-agree').checked) return authFail('reg-error', 'Please agree to the Terms of Use and Privacy Policy.');
  try {
    await api('/api/register', { method: 'POST', body: JSON.stringify({ username, password }) });
    $('reg-pass').value = ''; $('reg-pass2').value = '';
    await boot();
  } catch (e) { authFail('reg-error', e.message); }
}

function newChat() {
  S.currentId = null;
  S.messages = [];
  S.pending = [];
  api('/api/pending', { method: 'POST', body: JSON.stringify({ names: [], private: S.privateMode }) }).catch(() => {});
  renderAll();
  $('chat-input').focus();
}

async function openChat(id) {
  try {
    const chat = await api('/api/chats/' + id);
    S.privateMode = false; // opening saved history exits private mode
    S.bannerDismissed = false;
    S.currentId = chat.id;
    S.messages = chat.messages || [];
    renderAll();
  } catch (e) { toast(e.message); }
}

async function favToggle(c) {
  try {
    await api(`/api/chats/${c.id}/favorite`, { method: 'POST', body: JSON.stringify({ on: !c.favorite }) });
    c.favorite = !c.favorite;
    renderRecents();
  } catch (e) { toast(e.message); }
}

async function delChat(c) {
  try {
    await api('/api/chats/' + c.id, { method: 'DELETE' });
    S.chats = S.chats.filter((x) => x.id !== c.id);
    if (S.currentId === c.id) { S.currentId = null; S.messages = []; }
    renderAll();
  } catch (e) { toast(e.message); }
}

function setPrivate(on) {
  if (on === S.privateMode) return;
  S.privateMode = on;
  S.bannerDismissed = false;
  // Both directions open a fresh conversation (recorded chats are
  // already persisted server-side per message; the temporary one is
  // discarded by design).
  S.currentId = null;
  S.messages = [];
  S.pending = [];
  renderAll();
}

async function send() {
  if (S.busy) return;
  const ta = $('chat-input');
  const q = ta.value.trim();
  if (!q) return;
  ta.value = ''; autoGrow();
  S.busy = true; $('send-btn').disabled = true;

  const userMsg = { role: 'user', content: q, ts: new Date().toISOString(), attachments: [...S.pending] };
  S.messages.push(userMsg);
  renderMessages();

  const typing = document.createElement('div');
  typing.className = 'msg ai';
  typing.innerHTML = `<div class="ai-avatar"><svg viewBox="0 0 24 24"><rect x="5" y="8" width="14" height="11" rx="3"/><circle cx="9.5" cy="13" r="1" fill="currentColor" stroke="none"/><circle cx="14.5" cy="13" r="1" fill="currentColor" stroke="none"/><path d="M12 8V5"/><circle cx="12" cy="4" r="1"/></svg></div>
    <div class="bubble"><span class="typing"><i></i><i></i><i></i></span></div>`;
  $('messages').appendChild(typing);
  $('chat-scroll').scrollTop = $('chat-scroll').scrollHeight;

  const attachments = [...S.pending];
  S.pending = []; renderChips();

  try {
    const d = await api('/api/send', {
      method: 'POST',
      body: JSON.stringify({
        question: q,
        chat_id: S.privateMode ? null : S.currentId,
        private: S.privateMode,
        model: S.selectedModel,
        attachments,
        messages: S.privateMode ? S.messages.slice(0, -1) : undefined,
      }),
    });
    typing.remove();
    S.messages[S.messages.length - 1] = d.user_message;
    S.messages.push(d.assistant_message);
    if (!S.privateMode) {
      S.currentId = d.chat_id;
      S.chats = (await api('/api/chats')).chats;
    }
    renderAll();
  } catch (e) {
    typing.remove();
    S.messages.push({ role: 'assistant', content: '⚠️ ' + e.message, ts: new Date().toISOString() });
    renderMessages();
  } finally {
    S.busy = false; $('send-btn').disabled = false; ta.focus();
  }
}

async function uploadFiles(files) {
  for (const f of files) {
    const fd = new FormData();
    fd.append('file', f);
    toast(`Indexing ${f.name}…`);
    try {
      const d = await api('/api/upload', { method: 'POST', body: fd });
      if (!S.pending.includes(d.name)) S.pending.push(d.name);
      toast(d.existing ? `${d.name} already indexed` : `${d.name} — ${d.chunks} chunks, ${d.pages} pages`);
    } catch (e) { toast(e.message); }
  }
  renderChips();
  api('/api/pending', { method: 'POST', body: JSON.stringify({ names: S.pending, private: S.privateMode }) }).catch(() => {});
}

/* ---------- modals ---------- */
function openModal(title, bodyHTML) {
  $('modal-title').textContent = title;
  $('modal-body').innerHTML = bodyHTML;
  $('modal-back').classList.remove('hidden');
}
const closeModal = () => $('modal-back').classList.add('hidden');

async function openSettings() {
  const mem = await api('/api/memory').then((d) => d.facts).catch(() => []);
  S.memory = mem;
  const models = S.models.map((m) =>
    `<button class="${m === S.selectedModel ? 'sel' : ''}" data-model="${esc(m)}">
       ${m === S.selectedModel ? '✓' : '&nbsp;&nbsp;'} ${esc(m)}
     </button>`).join('') || '<p style="color:var(--muted)">No .gguf models found in models/.</p>';
  const memory = mem.map((f, i) =>
    `<div class="mem-item"><span>${esc(f)}</span>
       <button data-del="${i}" title="Forget"><svg viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg></button>
     </div>`).join('') || '<p style="color:var(--muted)">Nothing remembered yet. Say “remember: …” in a chat.</p>';
  openModal('Settings', `
    <h4>Model</h4><div class="model-list">${models}</div>
    <h4>Memory (${mem.length})</h4>${memory}
    ${mem.length ? '<button class="btn-danger" id="mem-clear">🗑 Clear all memory</button>' : ''}`);
  $('modal-body').querySelectorAll('[data-model]').forEach((b) =>
    b.addEventListener('click', async () => {
      try {
        const d = await api('/api/model', { method: 'POST', body: JSON.stringify({ model: b.dataset.model }) });
        S.selectedModel = d.selected; renderModel(); closeModal();
        toast('Model switched — loads on your next message');
      } catch (e) { toast(e.message); }
    }));
  $('modal-body').querySelectorAll('[data-del]').forEach((b) =>
    b.addEventListener('click', async () => {
      await api('/api/memory', { method: 'POST', body: JSON.stringify({ delete: S.memory[+b.dataset.del] }) });
      openSettings();
    }));
  const clr = $('modal-body').querySelector('#mem-clear');
  if (clr) clr.addEventListener('click', async () => {
    await api('/api/memory', { method: 'POST', body: JSON.stringify({ clear: true }) });
    openSettings();
  });
}

function openProfile() {
  openModal('Profile', `
    <div class="profile-line"><b>Username</b><span>${esc(S.user)}</span></div>
    <div class="profile-line"><b>Account type</b><span>Local (this device only)</span></div>
    <div class="profile-line"><b>Chats saved</b><span>${S.chats.length}</span></div>
    <p style="margin-top:14px;color:var(--muted);font-size:13px">
      All data lives in the <code>data/</code> folder on this computer.
      Nothing is sent anywhere.</p>`);
}

function openHelp() {
  openModal('Help & Support', `
    <p><b>Ask about documents:</b> click the paperclip, attach a PDF/DOCX/XLSX,
    then ask your question. COEBOT reads the whole document when it fits.</p>
    <p style="margin-top:10px"><b>Memory:</b> say <code>remember: …</code> to store
    a fact. Manage facts in Settings.</p>
    <p style="margin-top:10px"><b>Private Chat:</b> flip the toggle in the sidebar —
    nothing in a private session is saved or remembered.</p>
    <p style="margin-top:10px"><b>Docs & updates:</b>
    <a href="https://github.com/Zhafir24/COEBOT#readme" target="_blank" rel="noopener">github.com/Zhafir24/COEBOT</a></p>`);
}

async function logout() {
  await api('/api/logout', { method: 'POST' }).catch(() => {});
  S.user = null; S.messages = []; S.currentId = null; S.privateMode = false;
  S.registerMode = false;
  updateLoginMode();
  renderAuth();
}

/* ---------- input helpers ---------- */
function autoGrow() {
  const ta = $('chat-input');
  ta.style.height = 'auto';
  ta.style.height = Math.min(ta.scrollHeight, 130) + 'px';
}

/* ================= WIRE-UP ================= */
window.addEventListener('DOMContentLoaded', () => {
  $('li-btn').addEventListener('click', doLogin);
  $('reg-btn').addEventListener('click', doRegister);
  ['li-user', 'li-pass'].forEach((id) =>
    $(id).addEventListener('keydown', (e) => { if (e.key === 'Enter') doLogin(); }));
  ['reg-user', 'reg-pass', 'reg-pass2'].forEach((id) =>
    $(id).addEventListener('keydown', (e) => { if (e.key === 'Enter') doRegister(); }));
  $('to-register').addEventListener('click', (e) => {
    e.preventDefault(); S.registerMode = true; updateLoginMode();
  });
  $('to-login').addEventListener('click', (e) => {
    e.preventDefault(); S.registerMode = false; updateLoginMode();
  });
  document.querySelectorAll('.eye').forEach((b) =>
    b.addEventListener('click', () => {
      const inp = $(b.dataset.eye);
      inp.type = inp.type === 'password' ? 'text' : 'password';
    }));
  $('forgot-link').addEventListener('click', (e) => {
    e.preventDefault();
    openModal('Forgot password', `
      <p>COEBOT runs fully on this computer — there is no email reset.</p>
      <p style="margin-top:10px">To regain access, create a new account with the
      <b>Create account</b> link, or ask the person who manages this computer to
      reset <code>data/users.json</code>. Chats and documents are kept either way.</p>`);
  });
  const policyModal = (e) => {
    e.preventDefault();
    openModal('Terms & Privacy', `
      <p><b>Local only.</b> COEBOT stores your account, chats, documents, and
      memory in the <code>data/</code> folder on this computer. Nothing is ever
      sent to any external server.</p>
      <p style="margin-top:10px"><b>Private Chat.</b> Conversations in Private
      mode are never written to disk.</p>
      <p style="margin-top:10px"><b>Use responsibly.</b> COEBOT is an internal
      PNM assistant — verify important answers against the source documents.</p>`);
  };
  $('terms-link').addEventListener('click', policyModal);
  $('privacy-link').addEventListener('click', policyModal);

  $('new-chat').addEventListener('click', newChat);
  document.querySelectorAll('.nav-item[data-view]').forEach((b) =>
    b.addEventListener('click', () => { S.view = b.dataset.view; renderRecents(); }));
  $('nav-settings').addEventListener('click', openSettings);
  $('nav-profile').addEventListener('click', openProfile);
  $('nav-help').addEventListener('click', openHelp);
  $('nav-logout').addEventListener('click', logout);

  $('private-toggle').addEventListener('change', (e) => setPrivate(e.target.checked));
  $('turn-off-private').addEventListener('click', (e) => { e.preventDefault(); setPrivate(false); });
  $('banner-x').addEventListener('click', () => { S.bannerDismissed = true; renderPrivate(); });

  $('attach-btn').addEventListener('click', () => $('file-input').click());
  $('file-input').addEventListener('change', (e) => {
    uploadFiles([...e.target.files]); e.target.value = '';
  });

  $('send-btn').addEventListener('click', send);
  $('chat-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  });
  $('chat-input').addEventListener('input', autoGrow);

  $('model-chip').addEventListener('click', (e) => {
    if (e.target.closest('.model-menu')) return;
    const menu = $('model-menu');
    if (!menu.classList.contains('hidden')) return menu.classList.add('hidden');
    menu.innerHTML = S.models.map((m) =>
      `<button class="${m === S.selectedModel ? 'sel' : ''}" data-m="${esc(m)}">${m === S.selectedModel ? '✓' : '&nbsp;&nbsp;'} ${esc(m)}</button>`
    ).join('') || '<button disabled>No models found</button>';
    menu.classList.remove('hidden');
    menu.querySelectorAll('[data-m]').forEach((b) =>
      b.addEventListener('click', async (ev) => {
        ev.stopPropagation();
        try {
          const d = await api('/api/model', { method: 'POST', body: JSON.stringify({ model: b.dataset.m }) });
          S.selectedModel = d.selected; renderModel();
          toast('Model switched — loads on your next message');
        } catch (err) { toast(err.message); }
        menu.classList.add('hidden');
      }));
  });
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.model-chip')) $('model-menu').classList.add('hidden');
  });

  $('modal-x').addEventListener('click', closeModal);
  $('modal-back').addEventListener('click', (e) => { if (e.target === $('modal-back')) closeModal(); });

  boot();
});
