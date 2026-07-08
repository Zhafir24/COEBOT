"""Streamlit UI for COEBOT — PNM-branded visual shell with local auth.

Layout:
  - Login/signup page when not authenticated.
  - Once signed in:
    - Sidebar: PNM logo, "+ New Chat", user pinned at bottom with sign-out.
    - Main: vertically-centered hero (Recording or Nobody mode).
    - Chat input pinned to the bottom.
  - A JS-injected hamburger button at top-left guarantees the sidebar
    can be toggled even if Streamlit's native toggle is hidden.

Run with:
    streamlit run src/doc_analyzer/ui/app.py
"""

from __future__ import annotations

import base64
import json
import logging
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from doc_analyzer import __version__
from doc_analyzer.auth.store import ActiveSessionStore, UserStore, UserStoreError
from doc_analyzer.config import Settings, get_settings
from doc_analyzer.embeddings.encoder import Embedder
from doc_analyzer.llm.client import LlmClient
from doc_analyzer.memory import UserMemory
from doc_analyzer.pipeline import (
    Answer,
    answer_full_documents,
    answer_question,
    converse,
    extract_memory_fact,
    ingest_document,
)
from doc_analyzer.retrieval.store import VectorStore
from doc_analyzer.ui.styles import CUSTOM_CSS

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_LOGO_PATH = _PROJECT_ROOT / "static" / "pnm-logo.svg"
_USERS_PATH = _PROJECT_ROOT / "data" / "users.json"
_SESSION_PATH = _PROJECT_ROOT / "data" / "active_session.json"
_PENDING_PATH = _PROJECT_ROOT / "data" / "pending_attachments.json"
_CHATS_DIR = _PROJECT_ROOT / "data" / "chats"
_CURRENT_CHAT_PATH = _PROJECT_ROOT / "data" / "current_chat.json"
_SELECTED_MODEL_PATH = _PROJECT_ROOT / "data" / "selected_model.json"
_MEMORY_PATH = _PROJECT_ROOT / "data" / "memory.json"

# Explicit memory command: "remember: fact" / "ingat: fakta" (EN/ID).
_REMEMBER_CMD_RE = re.compile(
    r"^\s*(?:remember|ingat|ingatlah)\s*[:,]?\s+(.+)$", re.IGNORECASE | re.DOTALL
)

# Heuristic gate for automatic memory extraction — only messages that
# look like they contain personal information trigger the (CPU-costly)
# LLM extraction pass.
_PERSONAL_SIGNAL_RE = re.compile(
    r"\b(nama saya|panggil saya|saya suka|saya tidak suka|saya lebih suka|"
    r"saya bekerja|saya seorang|pekerjaan saya|proyek saya|aku suka|"
    r"my name|call me|i am|i'm|i like|i love|i hate|i prefer|i work|"
    r"i'm working on|my job|my project|my role)\b",
    re.IGNORECASE,
)


def _memory() -> UserMemory:
    return UserMemory(_MEMORY_PATH)


# ----------------------------------------------------------------------------
# Chat persistence — one JSON file per chat under data/chats/.
# ----------------------------------------------------------------------------


def _serialize_message(msg: dict) -> dict:
    """Convert an in-memory message dict to JSON-safe form."""
    result: dict = {
        "role": msg.get("role", ""),
        "content": msg.get("content", ""),
    }
    attachments = msg.get("attachments")
    if attachments:
        result["attachments"] = list(attachments)
    sources = msg.get("sources")
    if sources:
        out: list[dict] = []
        for src in sources:
            if isinstance(src, dict):
                out.append(src)
            else:
                out.append({
                    "text": getattr(src, "text", ""),
                    "source": str(getattr(src, "source", "")),
                    "page_index": getattr(src, "page_index", 0),
                    "chunk_index": getattr(src, "chunk_index", 0),
                    "score": getattr(src, "score", 0.0),
                })
        result["sources"] = out
    return result


def _list_chats() -> list[dict]:
    """Return chat metadata for all saved chats, newest first."""
    if not _CHATS_DIR.exists():
        return []
    chats: list[dict] = []
    for path in _CHATS_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        chats.append({
            "id": str(data.get("id", path.stem)),
            "title": str(data.get("title") or "(Untitled)"),
            "updated_at": str(data.get("updated_at", "")),
        })
    chats.sort(key=lambda c: c.get("updated_at", ""), reverse=True)
    return chats


def _load_chat(chat_id: str) -> dict | None:
    """Read one chat's full payload from disk."""
    if not chat_id:
        return None
    path = _CHATS_DIR / f"{chat_id}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def _write_chat(chat: dict) -> None:
    """Persist a chat dict to disk atomically."""
    chat_id = str(chat.get("id", "")).strip()
    if not chat_id:
        return
    _CHATS_DIR.mkdir(parents=True, exist_ok=True)
    path = _CHATS_DIR / f"{chat_id}.json"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(chat, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def _delete_chat_file(chat_id: str) -> None:
    """Remove a chat's JSON file from disk."""
    if not chat_id:
        return
    path = _CHATS_DIR / f"{chat_id}.json"
    if path.exists():
        try:
            path.unlink()
        except OSError:
            pass


def _load_current_chat_id() -> str | None:
    """Return the chat ID the user was last viewing, or None."""
    if not _CURRENT_CHAT_PATH.exists():
        return None
    try:
        data = json.loads(_CURRENT_CHAT_PATH.read_text(encoding="utf-8"))
        cid = data.get("chat_id")
        return str(cid) if cid else None
    except (OSError, json.JSONDecodeError):
        return None


def _save_current_chat_id(chat_id: str | None) -> None:
    """Persist (or clear) the currently-viewed chat id."""
    try:
        _CURRENT_CHAT_PATH.parent.mkdir(parents=True, exist_ok=True)
        if chat_id is None:
            if _CURRENT_CHAT_PATH.exists():
                _CURRENT_CHAT_PATH.unlink()
            return
        tmp = _CURRENT_CHAT_PATH.with_suffix(_CURRENT_CHAT_PATH.suffix + ".tmp")
        tmp.write_text(json.dumps({"chat_id": chat_id}), encoding="utf-8")
        tmp.replace(_CURRENT_CHAT_PATH)
    except OSError:
        pass


def _list_available_models(models_dir: Path) -> list[Path]:
    """Return every .gguf file in the models directory, sorted A→Z."""
    if not models_dir.exists():
        return []
    return sorted(models_dir.glob("*.gguf"))


def _load_selected_model_filename() -> str:
    """Return the model filename the user last selected, or empty string."""
    if not _SELECTED_MODEL_PATH.exists():
        return ""
    try:
        data = json.loads(_SELECTED_MODEL_PATH.read_text(encoding="utf-8"))
        name = data.get("model_filename")
        return str(name) if name else ""
    except (OSError, json.JSONDecodeError):
        return ""


def _save_selected_model_filename(filename: str) -> None:
    """Persist the user's model selection so it survives refresh."""
    try:
        _SELECTED_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _SELECTED_MODEL_PATH.with_suffix(_SELECTED_MODEL_PATH.suffix + ".tmp")
        tmp.write_text(json.dumps({"model_filename": filename}), encoding="utf-8")
        tmp.replace(_SELECTED_MODEL_PATH)
    except OSError:
        pass


def _derive_chat_title(messages: list[dict]) -> str:
    """First user message becomes the title, truncated to ~50 chars."""
    for msg in messages:
        if msg.get("role") == "user":
            text = (msg.get("content") or "").strip()
            if text:
                return text[:50] + ("..." if len(text) > 50 else "")
    return "(Untitled)"


def _persist_current_chat() -> None:
    """Save the in-memory active chat to disk.

    No-op if there is no current chat id or no messages yet.
    """
    chat_id = st.session_state.get("current_chat_id")
    messages = st.session_state.get("messages", [])
    if not chat_id or not messages:
        return
    now = datetime.now(UTC).isoformat(timespec="seconds")
    created = st.session_state.get("current_chat_created_at") or now
    st.session_state.current_chat_created_at = created
    title = _derive_chat_title(messages)
    chat = {
        "id": chat_id,
        "title": title,
        "created_at": created,
        "updated_at": now,
        "messages": [_serialize_message(m) for m in messages],
    }
    _write_chat(chat)


def _start_new_chat() -> None:
    """Reset session to a blank state and clear current chat id."""
    _persist_current_chat()
    st.session_state.current_chat_id = None
    st.session_state.current_chat_created_at = None
    st.session_state.messages = []
    st.session_state.pending_question = None
    _save_current_chat_id(None)


def _switch_to_chat(chat_id: str) -> None:
    """Save the current chat then load and activate another one."""
    if st.session_state.get("current_chat_id") == chat_id:
        return
    _persist_current_chat()
    chat = _load_chat(chat_id)
    if chat is None:
        return
    st.session_state.current_chat_id = chat_id
    st.session_state.current_chat_created_at = chat.get("created_at")
    st.session_state.messages = list(chat.get("messages", []))
    st.session_state.pending_question = None
    _save_current_chat_id(chat_id)


def _ensure_chat_id() -> str:
    """Create a new chat id for the current session if there isn't one."""
    chat_id = st.session_state.get("current_chat_id")
    if not chat_id:
        chat_id = str(uuid.uuid4())
        st.session_state.current_chat_id = chat_id
        st.session_state.current_chat_created_at = datetime.now(
            UTC
        ).isoformat(timespec="seconds")
        _save_current_chat_id(chat_id)
    return chat_id


def _load_pending_attachments() -> list[str]:
    """Read pending chip-rail attachments from disk.

    Returns an empty list if the file doesn't exist or can't be parsed.
    """
    if not _PENDING_PATH.exists():
        return []
    try:
        raw = json.loads(_PENDING_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return [str(x) for x in raw if isinstance(x, str)]
    except (OSError, json.JSONDecodeError):
        pass
    return []


def _save_pending_attachments(names: list[str]) -> None:
    """Persist the pending chip-rail attachments to disk. Best-effort."""
    try:
        _PENDING_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _PENDING_PATH.with_suffix(_PENDING_PATH.suffix + ".tmp")
        tmp.write_text(json.dumps(names), encoding="utf-8")
        tmp.replace(_PENDING_PATH)
    except OSError:
        pass


def _load_logo_svg() -> str:
    """Read the PNM SVG and strip XML/DOCTYPE so it inlines cleanly."""
    if not _LOGO_PATH.exists():
        return ""
    raw = _LOGO_PATH.read_text(encoding="utf-8")
    raw = re.sub(r"<\?xml[^?]*\?>", "", raw)
    raw = re.sub(r"<!DOCTYPE[^>]*>", "", raw)
    return raw.strip()


PNM_LOGO_SVG = _load_logo_svg()


_CHAT_UPLOAD_JS = """
<script>
(function () {
  var PAPERCLIP = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>';

  var ACCEPT_TYPES = [
    '.pdf','.docx','.xlsx',
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/msword',
    'application/vnd.ms-excel'
  ].join(',');

  // Locate Streamlit's hidden file input and give it a stable id so a
  // <label for="..."> elsewhere on the page can open it natively. If
  // multiple file_uploader instances exist for any reason, only the
  // first connected one keeps the id; the rest have it removed.
  function findFileInput() {
    var D = window.parent.document;
    var inputs = D.querySelectorAll('[data-testid="stFileUploader"] input[type="file"]');
    var primary = null;
    for (var i = 0; i < inputs.length; i++) {
      var inp = inputs[i];
      if (!inp.isConnected) continue;
      if (primary === null) {
        primary = inp;
        if (primary.id !== 'cc-st-file-input') {
          primary.id = 'cc-st-file-input';
        }
        primary.setAttribute('accept', ACCEPT_TYPES);
        primary.setAttribute('multiple', 'multiple');
        if (primary.disabled) primary.disabled = false;
      } else if (inp.id === 'cc-st-file-input') {
        inp.removeAttribute('id');
      }
    }
    return primary;
  }

  function patchAccept() {
    findFileInput();  // sets accept as a side-effect
  }

  // Find the chat input bar (direct child of stChatInput) by tracing
  // up from the textarea. More reliable than class-based selectors,
  // which can accidentally match divs inside the chip rail.
  function findChatBar(D) {
    var chatInput = D.querySelector('[data-testid="stChatInput"]');
    if (!chatInput) return null;
    var textarea = chatInput.querySelector('textarea');
    if (!textarea) return null;
    var bar = textarea;
    while (bar.parentElement && bar.parentElement !== chatInput) {
      bar = bar.parentElement;
    }
    if (!bar || bar.parentElement !== chatInput) return null;
    return bar;
  }

  function ensureUploadBtn() {
    var D = window.parent.document;
    if (!D || !D.body) return;

    // FAST PATH: paperclip already present and in the right place.
    // O(1) check via getElementById — much cheaper than walking the tree.
    var fastClip = D.getElementById('chat-upload-btn');
    if (fastClip && !fastClip.closest('.cc-chip-rail')
        && fastClip.closest('[data-testid="stChatInput"]')) {
      return;
    }

    var bar = findChatBar(D);
    if (!bar) return;
    // Sweep any stray paperclips that landed inside the chip rail.
    var rail = bar.querySelector('.cc-chip-rail');
    if (rail) {
      var strays = rail.querySelectorAll('#chat-upload-btn');
      for (var k = 0; k < strays.length; k++) strays[k].remove();
    }
    // Look for an existing paperclip that is NOT inside the chip rail.
    var existingClips = bar.querySelectorAll('#chat-upload-btn');
    for (var m = 0; m < existingClips.length; m++) {
      if (!existingClips[m].closest('.cc-chip-rail')) return;
    }

    bar.style.position = 'relative';

    // Use a <label for="..."> instead of a <button> with JS click handler.
    // The browser natively links label clicks to the associated input,
    // opening the file picker regardless of the input's prior state.
    // This sidesteps every Chrome/React quirk that broke our previous
    // attempts to call inp.click() programmatically.
    var btn = D.createElement('label');
    btn.id = 'chat-upload-btn';
    btn.htmlFor = 'cc-st-file-input';
    btn.title = 'Attach PDF';
    btn.setAttribute('aria-label', 'Attach PDF');
    btn.innerHTML = PAPERCLIP;
    btn.style.cssText = [
      'position:absolute',
      // Paperclip sits LEFT of the model pill. Model pill is at
      // right:64px with max-width 200px → its left edge at right:264px.
      // Paperclip clears at right:280px with a small gap.
      'right:280px',
      'top:50%',
      'transform:translateY(-50%)',
      'width:26px',
      'height:26px',
      'background:transparent',
      'border:none',
      'color:#9CA3AF',
      'cursor:pointer',
      'border-radius:50%',
      'display:inline-flex',
      'align-items:center',
      'justify-content:center',
      'transition:color 0.15s ease, background 0.15s ease',
      'z-index:5',
      'padding:0',
      'outline:none',
      'user-select:none'
    ].join(';');
    btn.addEventListener('mouseenter', function () {
      btn.style.color = '#0C5BA8';
      btn.style.background = '#F3F4F6';
    });
    btn.addEventListener('mouseleave', function () {
      btn.style.color = '#9CA3AF';
      btn.style.background = 'transparent';
    });

    bar.appendChild(btn);
  }

  // Float the chip rail ABOVE the bar via absolute positioning
  // anchored to the BAR itself (the visible white pill — the actual
  // centered element). With bar set to position:relative and the
  // rail at bottom:100% + left:0, the chip's left edge automatically
  // matches the bar's left edge. Every ancestor up to stBottom gets
  // overflow:visible so the rail isn't clipped above the bar.
  function syncChipRail() {
    var D = window.parent.document;
    var bar = findChatBar(D);
    if (!bar) return;

    var source = D.getElementById('cc-chip-source');
    var hasSource = source && source.children.length > 0;
    var sig = '';
    if (hasSource) {
      for (var i = 0; i < source.children.length; i++) {
        sig += source.children[i].textContent + '|';
      }
    }

    // FAST PATH: check signature against the rail already attached to
    // the bar BEFORE doing any DOM mutations. When the file list
    // hasn't changed (the common case on every polling tick), this
    // exits in microseconds with zero DOM writes.
    var existing = bar.querySelector(':scope > .cc-chip-rail');
    if (hasSource && existing && existing.getAttribute('data-sig') === sig) {
      return;
    }

    // Sweep any leftover rails outside the bar (legacy code paths).
    var legacyRails = D.querySelectorAll('.cc-chip-rail');
    for (var k = 0; k < legacyRails.length; k++) {
      if (legacyRails[k].parentElement !== bar) legacyRails[k].remove();
    }
    // Reset bar's inline styles from previous code paths.
    bar.style.removeProperty('min-height');
    bar.style.removeProperty('flex-wrap');
    var textarea = bar.querySelector('textarea');
    if (textarea) {
      textarea.style.removeProperty('padding-top');
      textarea.style.removeProperty('padding-bottom');
    }

    // Force overflow:visible on the bar and all ancestors up to
    // stBottom — otherwise an ancestor with overflow:hidden would
    // clip the rail at the bar's top edge.
    var walker = bar;
    while (walker && walker.getAttribute) {
      walker.style.setProperty('overflow', 'visible', 'important');
      if (walker.getAttribute('data-testid') === 'stBottom') break;
      walker = walker.parentElement;
    }

    if (existing) existing.remove();
    if (!hasSource) return;

    var rail = D.createElement('div');
    rail.className = 'cc-chip-rail';
    rail.setAttribute('data-sig', sig);
    rail.style.setProperty('position', 'absolute', 'important');
    rail.style.setProperty('bottom', '100%', 'important');
    rail.style.setProperty('left', '0', 'important');
    rail.style.setProperty('padding-bottom', '8px', 'important');
    rail.style.setProperty('margin', '0', 'important');
    rail.style.setProperty('display', 'flex', 'important');
    rail.style.setProperty('gap', '6px', 'important');
    rail.style.setProperty('align-items', 'center', 'important');
    rail.style.setProperty('background', 'transparent', 'important');
    rail.style.setProperty('background-color', 'transparent', 'important');
    rail.style.setProperty('border', 'none', 'important');
    rail.style.setProperty('box-shadow', 'none', 'important');
    rail.style.setProperty('flex-wrap', 'wrap', 'important');
    rail.style.setProperty('z-index', '3', 'important');

    for (var j = 0; j < source.children.length; j++) {
      var src = source.children[j];
      var chip = D.createElement('div');
      chip.style.setProperty('background', '#f3f4f6', 'important');
      chip.style.setProperty('background-color', '#f3f4f6', 'important');
      chip.style.setProperty('color', '#6b7280', 'important');
      chip.style.setProperty('padding', '5px 6px 5px 10px', 'important');
      chip.style.setProperty('border-radius', '6px', 'important');
      chip.style.setProperty('font-size', '11px', 'important');
      chip.style.setProperty('font-weight', '500', 'important');
      chip.style.setProperty('border', '1px solid #e5e7eb', 'important');
      chip.style.setProperty('line-height', '1', 'important');
      chip.style.setProperty('flex-shrink', '0', 'important');
      chip.style.setProperty('display', 'inline-flex', 'important');
      chip.style.setProperty('align-items', 'center', 'important');
      chip.style.setProperty('gap', '4px', 'important');
      chip.style.setProperty('cursor', 'pointer', 'important');
      chip.style.setProperty('transition', 'background 0.15s ease', 'important');
      chip.addEventListener('mouseenter', function () {
        this.style.setProperty('background', '#e5e7eb', 'important');
        this.style.setProperty('background-color', '#e5e7eb', 'important');
      });
      chip.addEventListener('mouseleave', function () {
        this.style.setProperty('background', '#f3f4f6', 'important');
        this.style.setProperty('background-color', '#f3f4f6', 'important');
      });

      var name = src.getAttribute('data-name');

      // Chip-body click — open preview. The × button below stops
      // propagation so its delete action won't also trigger preview.
      // e.detail is 0 for keyboard-activated (Enter/Space) or
      // programmatic clicks — we only want real mouse clicks here,
      // otherwise pressing Enter in the chat input could spuriously
      // trigger the preview-open bridge.
      (function (capturedName) {
        chip.addEventListener('click', function (e) {
          if (e.detail < 1) return;
          if (!capturedName) return;
          var D = window.parent.document;
          var W = window.parent;
          var chatInput = D.querySelector('[data-testid="stChatInput"]');
          if (!chatInput) return;
          var textarea = chatInput.querySelector('textarea');
          if (!textarea) return;
          // Don't clobber unsent text — same protection as the × handler.
          if ((textarea.value || '').trim() !== '') return;

          var origColor = textarea.style.color;
          var origCaret = textarea.style.caretColor;
          textarea.style.setProperty('color', 'transparent', 'important');
          textarea.style.setProperty('caret-color', 'transparent', 'important');
          try {
            var proto = W.HTMLTextAreaElement.prototype;
            var setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
            setter.call(textarea, '__CCPREVIEW:' + capturedName);
            textarea.dispatchEvent(new Event('input', { bubbles: true }));
            setTimeout(function () {
              var enterEvt = new KeyboardEvent('keydown', {
                key: 'Enter', code: 'Enter', keyCode: 13, which: 13,
                bubbles: true, cancelable: true
              });
              textarea.dispatchEvent(enterEvt);
              var btns = chatInput.querySelectorAll('button');
              for (var i = 0; i < btns.length; i++) {
                if (btns[i].id !== 'chat-upload-btn') {
                  btns[i].click();
                  break;
                }
              }
              setTimeout(function () {
                textarea.style.color = origColor;
                textarea.style.caretColor = origCaret;
              }, 400);
            }, 50);
          } catch (err) {
            textarea.style.color = origColor;
            textarea.style.caretColor = origCaret;
          }
        });
      })(name);

      // Chip text (extension label)
      var chipLabel = D.createElement('span');
      chipLabel.textContent = src.textContent;
      chip.appendChild(chipLabel);

      // × delete button — sets a URL query param and reloads so
      // Streamlit can pick up the delete request on next render.
      var xBtn = D.createElement('span');
      xBtn.textContent = '×';
      xBtn.setAttribute('role', 'button');
      xBtn.setAttribute('aria-label', 'Delete ' + (name || 'document'));
      xBtn.style.cssText = [
        'cursor:pointer','color:#9CA3AF','font-weight:600',
        'font-size:14px','line-height:1','padding:1px 5px',
        'border-radius:3px','display:inline-flex',
        'align-items:center','justify-content:center',
        'transition:color 0.15s ease, background 0.15s ease'
      ].join(';');
      xBtn.addEventListener('mouseenter', function () {
        this.style.color = '#dc2626';
        this.style.background = '#fee2e2';
      });
      xBtn.addEventListener('mouseleave', function () {
        this.style.color = '#9CA3AF';
        this.style.background = 'transparent';
      });
      (function (capturedName, capturedChip) {
        xBtn.addEventListener('click', function (e) {
          e.stopPropagation();
          e.preventDefault();
          // Only respond to real mouse clicks — see note on chip body
          // handler above. Prevents Enter in chat input from firing the
          // delete bridge if focus accidentally landed on the ×.
          if (e.detail < 1) return;
          if (!capturedName) return;

          // Optimistic UI — fade the chip immediately so user sees
          // instant feedback before the WebSocket round-trip completes.
          capturedChip.style.transition = 'opacity 0.15s ease';
          capturedChip.style.opacity = '0.3';
          capturedChip.style.pointerEvents = 'none';

          var D = window.parent.document;
          var W = window.parent;
          var chatInput = D.querySelector('[data-testid="stChatInput"]');
          if (!chatInput) {
            capturedChip.style.opacity = '1';
            capturedChip.style.pointerEvents = '';
            return;
          }
          var textarea = chatInput.querySelector('textarea');
          if (!textarea) {
            capturedChip.style.opacity = '1';
            capturedChip.style.pointerEvents = '';
            return;
          }

          // Skip if user has unsent text — refuse to overwrite it.
          if ((textarea.value || '').trim() !== '') {
            capturedChip.style.opacity = '1';
            capturedChip.style.pointerEvents = '';
            return;
          }

          // Server-side bridge: set chat input value to "__CCDEL:<name>"
          // and submit. Python detects the prefix and deletes the file.
          var origColor = textarea.style.color;
          var origCaret = textarea.style.caretColor;
          textarea.style.setProperty('color', 'transparent', 'important');
          textarea.style.setProperty('caret-color', 'transparent', 'important');

          try {
            var proto = W.HTMLTextAreaElement.prototype;
            var setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
            setter.call(textarea, '__CCDEL:' + capturedName);
            textarea.dispatchEvent(new Event('input', { bubbles: true }));

            setTimeout(function () {
              // Try both submit paths — Enter keydown AND clicking
              // the send button — to maximize the chance one of them
              // actually triggers Streamlit's submit handler.
              var enterEvt = new KeyboardEvent('keydown', {
                key: 'Enter', code: 'Enter', keyCode: 13, which: 13,
                bubbles: true, cancelable: true
              });
              textarea.dispatchEvent(enterEvt);
              var btns = chatInput.querySelectorAll('button');
              for (var i = 0; i < btns.length; i++) {
                if (btns[i].id !== 'chat-upload-btn') {
                  btns[i].click();
                  break;
                }
              }
              setTimeout(function () {
                textarea.style.color = origColor;
                textarea.style.caretColor = origCaret;
              }, 400);
            }, 50);
          } catch (err) {
            textarea.style.color = origColor;
            textarea.style.caretColor = origCaret;
          }

          // OPTIMISTIC CLIENT-SIDE REMOVAL: after a brief fade, take
          // the chip out of the rail AND remove the matching span from
          // cc-chip-source so the next syncChipRail tick doesn't try
          // to rebuild the chip back. Update the rail's data-sig too
          // so the signature comparison sees a match. The visual is
          // now instant; the server-side delete happens in the
          // background via the bridge above.
          setTimeout(function () {
            var railEl = capturedChip.parentNode;
            if (capturedChip.parentNode) {
              capturedChip.parentNode.removeChild(capturedChip);
            }
            var src = D.getElementById('cc-chip-source');
            if (src) {
              var spans = src.querySelectorAll('.cc-chip-item');
              for (var k = 0; k < spans.length; k++) {
                if (spans[k].getAttribute('data-name') === capturedName) {
                  spans[k].parentNode.removeChild(spans[k]);
                  break;
                }
              }
            }
            if (railEl && railEl.parentNode) {
              if (railEl.children.length === 0) {
                railEl.parentNode.removeChild(railEl);
              } else {
                var newSig = '';
                if (src) {
                  for (var m = 0; m < src.children.length; m++) {
                    newSig += src.children[m].textContent + '|';
                  }
                }
                railEl.setAttribute('data-sig', newSig);
              }
            }
          }, 220);
        });
      })(name, chip);
      chip.appendChild(xBtn);

      if (name) chip.title = name;
      rail.appendChild(chip);
    }

    // Anchor the rail to the bar (the actual centered/max-width
    // element), not the bar's parent.
    bar.style.setProperty('position', 'relative', 'important');
    bar.appendChild(rail);
  }

  // Brute-force nuke any white background on every wrapper around the
  // chat input bar — including stChatInput itself, which extends
  // full-width with white bg while the bar inside it has max-width.
  // Only the bar (the div containing the textarea, found via
  // findChatBar) and its descendants keep their styling — that's the
  // visible white pill. Everything else goes transparent.
  function killBottomBg() {
    var D = window.parent.document;
    var bottom = D.querySelector('[data-testid="stBottom"]')
              || D.querySelector('[data-testid="stBottomBlockContainer"]');
    if (!bottom) return;
    // FAST PATH: we've already nuked the white bg on this exact bottom
    // container — exit without touching the DOM. The sentinel is on
    // the element itself so a Streamlit rerun that replaces the
    // container naturally invalidates the cache.
    if (bottom.dataset.ccBgKilled === '1') return;
    var bar = findChatBar(D);
    var rail = bottom.querySelector('.cc-chip-rail');
    bottom.style.setProperty('background', 'transparent', 'important');
    bottom.style.setProperty('background-color', 'transparent', 'important');
    var nodes = bottom.querySelectorAll('div');
    for (var i = 0; i < nodes.length; i++) {
      var n = nodes[i];
      // Skip the bar + its descendants (white pill stays white) and
      // the chip rail + its descendants (chips keep their grey bg).
      if (bar && (n === bar || bar.contains(n))) continue;
      if (rail && (n === rail || rail.contains(n))) continue;
      n.style.setProperty('background', 'transparent', 'important');
      n.style.setProperty('background-color', 'transparent', 'important');
    }
    bottom.dataset.ccBgKilled = '1';
  }

  // Strip every chat-message button from the tab order so that
  // pressing Enter never activates an attachment chip. Mouse clicks
  // still work — only keyboard activation is blocked. Without this,
  // focus could drift to an attachment chip after sending a message,
  // and the next Enter press would open the preview AND submit the
  // chat input simultaneously.
  function disableChatMessageButtonKeyboard() {
    var D = window.parent.document;
    var msgs = D.querySelectorAll('[data-testid="stChatMessage"]');
    for (var i = 0; i < msgs.length; i++) {
      var buttons = msgs[i].querySelectorAll('button');
      for (var j = 0; j < buttons.length; j++) {
        if (buttons[j].getAttribute('tabindex') !== '-1') {
          buttons[j].setAttribute('tabindex', '-1');
        }
      }
    }
  }

  // Each helper is wrapped so one throw can't kill the rest of the
  // pipeline. Without this, a stale reference inside (for example)
  // pushSignOutUp during a Streamlit rerun could abort runAll
  // mid-pass and leave the page in a half-mutated "white" state until
  // a manual refresh re-initializes everything.
  function safeCall(fn, label) {
    try { fn(); }
    catch (err) {
      try { console.warn('[COEBOT] ' + label + ' failed:', err); } catch (e) {}
    }
  }
  // Lift the sidebar content block up by 2.5rem so the Sign Out
  // button sits comfortably above the sidebar's bottom edge.
  // transform:translateY is used (not margin/padding) because every
  // CSS layout-based approach was silently absorbed by Streamlit's
  // internal styles; transform is a render-time visual offset that
  // bypasses layout entirely. Inline-style with !important wins over
  // any external stylesheet rule. NOT DOM surgery — just sets a
  // style on an existing element, so cannot race with React.
  function pushSignOutUp() {
    var D = window.parent.document;
    var sidebar = D.querySelector('section[data-testid="stSidebar"]');
    if (!sidebar) return;
    var buttons = sidebar.querySelectorAll('button');
    var signoutBtn = null;
    for (var i = 0; i < buttons.length; i++) {
      if ((buttons[i].textContent || '').trim() === 'Sign out') {
        signoutBtn = buttons[i];
        break;
      }
    }
    if (!signoutBtn) return;

    var mainBlock = sidebar.querySelector(
      '[data-testid="stSidebarUserContent"] > [data-testid="stVerticalBlock"]'
    );
    if (!mainBlock) {
      mainBlock = sidebar.querySelector('[data-testid="stSidebarUserContent"]');
    }
    if (!mainBlock) return;

    var wrapper = signoutBtn;
    var depth = 0;
    while (wrapper.parentElement && wrapper.parentElement !== mainBlock && depth < 20) {
      wrapper = wrapper.parentElement;
      depth++;
    }
    if (wrapper === signoutBtn || !wrapper.parentElement) return;
    if (wrapper.dataset.ccSignoutLifted === '1') return;
    wrapper.style.setProperty('transform', 'translateY(-2.5rem)', 'important');
    wrapper.dataset.ccSignoutLifted = '1';
  }

  // Chevron down icon for the model pill's dropdown indicator.
  var CHEVRON_DOWN = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>';
  var COG_ICON = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>';

  // Ensure the custom model pill exists in the chat input bar. This is
  // a BRAND NEW HTML element we create — Streamlit doesn't know it
  // exists, so reruns don't touch it (same crash-safe pattern as the
  // paperclip). Clicking it opens a JS-managed floating menu built from
  // #cc-model-source in the DOM.
  function ensureModelPill() {
    var D = window.parent.document;
    var bar = findChatBar(D);
    if (!bar) return;
    var source = D.getElementById('cc-model-source');
    if (!source) return;

    var pill = D.getElementById('cc-model-pill');
    var currentLabel = source.getAttribute('data-current-label') || 'No model';

    // Create the pill if it doesn't exist yet.
    if (!pill) {
      pill = D.createElement('button');
      pill.id = 'cc-model-pill';
      pill.type = 'button';
      pill.setAttribute('aria-label', 'Select model');
      // Every style is set via setProperty(..., 'important') so it
      // beats Streamlit's `[data-testid="stChatInput"] button {
      // background: var(--primary) !important; ... }` rule which
      // would otherwise paint our pill blue.
      var styles = {
        'position': 'absolute',
        'top': '50%',
        'transform': 'translateY(-50%)',
        // Model pill sits RIGHT (near send). Send at right:24px,
        // pill at right:64px. Paperclip is further left at right:280.
        'right': '64px',
        'background': 'transparent',
        'background-color': 'transparent',
        'border': 'none',
        'box-shadow': 'none',
        'padding': '4px 6px',
        'margin': '0',
        'font-family': 'inherit',
        'font-size': '13px',
        'font-weight': '500',
        'color': '#6B7280',
        'cursor': 'pointer',
        'display': 'inline-flex',
        'align-items': 'center',
        'gap': '5px',
        'z-index': '5',
        'outline': 'none',
        'user-select': 'none',
        'white-space': 'nowrap',
        'max-width': '200px',
        'overflow': 'hidden',
        'text-overflow': 'ellipsis',
        'height': 'auto',
        'min-height': '0',
        'width': 'auto',
        'min-width': '0',
        'border-radius': '4px',
        'transition': 'color 0.15s ease',
      };
      for (var k in styles) {
        if (styles.hasOwnProperty(k)) pill.style.setProperty(k, styles[k], 'important');
      }
      bar.style.position = 'relative';
      bar.appendChild(pill);
    }

    // Re-attach handlers on every tick — Streamlit reloads the iframe
    // on each rerun, which destroys the JS closure context. Using
    // `onclick`/`onmouseenter`/`onmouseleave` (rather than
    // addEventListener) lets us overwrite the old handler that points
    // to the dead context with a fresh one bound to the current iframe.
    pill.onmouseenter = function () {
      pill.style.setProperty('color', '#111', 'important');
    };
    pill.onmouseleave = function () {
      pill.style.setProperty('color', '#6B7280', 'important');
    };
    pill.onclick = function (e) {
      e.stopPropagation();
      toggleModelMenu();
    };

    // Update pill contents (icon + current model name + chevron).
    // Keep the pill's identity/DOM node stable; only update its innerHTML.
    var displayName = currentLabel.length > 24 ? currentLabel.slice(0, 21) + '…' : currentLabel;
    pill.innerHTML = '<span style="display:inline-flex;align-items:center">'
      + COG_ICON + '</span>'
      + '<span>' + displayName.replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</span>'
      + '<span style="display:inline-flex;align-items:center;color:#9CA3AF">'
      + CHEVRON_DOWN + '</span>';
    pill.title = currentLabel;

    // Dynamically place the paperclip just LEFT of the model pill,
    // hugging its left edge with a 10px gap. This keeps the two
    // controls visually clustered regardless of the model name's
    // width ("No model" vs "qwen2.5-7b-instruct.gguf").
    var paperclip = D.getElementById('chat-upload-btn');
    if (paperclip) {
      var pillRect = pill.getBoundingClientRect();
      var barRect = bar.getBoundingClientRect();
      var pillLeftFromBarRight = barRect.right - pillRect.left;
      paperclip.style.setProperty('right', (pillLeftFromBarRight + 10) + 'px', 'important');
    }
  }

  function toggleModelMenu() {
    var D = window.parent.document;
    var existing = D.getElementById('cc-model-menu');
    if (existing) {
      hideModelMenu();
    } else {
      showModelMenu();
    }
  }

  function hideModelMenu() {
    var D = window.parent.document;
    var menu = D.getElementById('cc-model-menu');
    if (menu && menu.parentNode) menu.parentNode.removeChild(menu);
    D.removeEventListener('click', outsideMenuClick, true);
    D.removeEventListener('keydown', escapeMenuKey, true);
  }

  function outsideMenuClick(e) {
    var D = window.parent.document;
    var menu = D.getElementById('cc-model-menu');
    var pill = D.getElementById('cc-model-pill');
    if (!menu) return;
    if (menu.contains(e.target)) return;
    if (pill && pill.contains(e.target)) return;
    hideModelMenu();
  }

  function escapeMenuKey(e) {
    if (e.key === 'Escape') hideModelMenu();
  }

  function showModelMenu() {
    var D = window.parent.document;
    var pill = D.getElementById('cc-model-pill');
    var source = D.getElementById('cc-model-source');
    if (!pill || !source) return;

    var pillRect = pill.getBoundingClientRect();
    var menu = D.createElement('div');
    menu.id = 'cc-model-menu';
    menu.style.cssText = [
      'position:fixed',
      'left:' + Math.round(pillRect.left - 60) + 'px',
      // Open ABOVE the pill so it doesn't get clipped by the viewport.
      'bottom:' + Math.round(window.parent.innerHeight - pillRect.top + 8) + 'px',
      'width:320px',
      'background:#ffffff',
      'border:1px solid #E5E7EB',
      'border-radius:14px',
      'box-shadow:0 8px 28px rgba(0,0,0,0.08),0 2px 6px rgba(0,0,0,0.04)',
      'padding:8px',
      'z-index:9999',
      'font-family:inherit',
      'max-height:400px',
      'overflow-y:auto',
    ].join(';');

    // Header (optional): compact label
    var header = D.createElement('div');
    header.textContent = 'Model';
    header.style.cssText = 'font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;color:#9CA3AF;padding:4px 8px 8px 8px';
    menu.appendChild(header);

    var items = source.querySelectorAll('.cc-model-item');
    if (items.length === 0) {
      var empty = D.createElement('div');
      empty.style.cssText = 'padding:16px 8px;text-align:center;color:#6B7280;font-size:13px';
      empty.innerHTML = 'No models yet.<br>Drop a <code style="background:#F3F4F6;padding:1px 4px;border-radius:3px;font-size:11px">.gguf</code> into <code style="background:#F3F4F6;padding:1px 4px;border-radius:3px;font-size:11px">models/</code> to see it here.';
      menu.appendChild(empty);
    } else {
      for (var i = 0; i < items.length; i++) {
        (function (item) {
          var name = item.getAttribute('data-name') || '';
          var size = item.getAttribute('data-size') || '';
          var isCurrent = item.getAttribute('data-current') === '1';
          var row = D.createElement('button');
          row.type = 'button';
          row.style.cssText = [
            'display:flex',
            'align-items:center',
            'justify-content:space-between',
            'width:100%',
            'padding:8px 10px',
            'margin:1px 0',
            'background:' + (isCurrent ? '#D6E4F2' : 'transparent'),
            'color:' + (isCurrent ? '#0C5BA8' : '#111'),
            'border:1px solid transparent',
            'border-radius:8px',
            'font-family:Menlo,Consolas,monospace',
            'font-size:12px',
            'font-weight:500',
            'cursor:pointer',
            'text-align:left',
            'outline:none',
            'transition:background 0.12s ease',
          ].join(';');
          var displayName = name.length > 26 ? name.slice(0, 23) + '…' : name;
          row.innerHTML = '<span>' + (isCurrent ? '✓ ' : '  ')
            + displayName.replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</span>'
            + '<span style="color:#9CA3AF;font-size:11px">' + size + ' GB</span>';
          row.title = name;
          row.addEventListener('mouseenter', function () {
            if (!isCurrent) row.style.background = '#F5F5F5';
          });
          row.addEventListener('mouseleave', function () {
            if (!isCurrent) row.style.background = 'transparent';
          });
          row.addEventListener('click', function (e) {
            e.stopPropagation();
            selectModel(name);
          });
          menu.appendChild(row);
        })(items[i]);
      }
    }

    D.body.appendChild(menu);
    // Register outside-click and Escape handlers on the next tick so
    // this initial click doesn't immediately close the menu.
    setTimeout(function () {
      D.addEventListener('click', outsideMenuClick, true);
      D.addEventListener('keydown', escapeMenuKey, true);
    }, 0);
  }

  // Send the model choice to Python via the chat-input bridge, same
  // pattern used by __CCDEL: and __CCPREVIEW:. Python detects the
  // __CCMODEL: prefix in the chat_input value and updates state.
  function selectModel(name) {
    var D = window.parent.document;
    var W = window.parent;
    hideModelMenu();
    var chatInput = D.querySelector('[data-testid="stChatInput"]');
    if (!chatInput) return;
    var textarea = chatInput.querySelector('textarea');
    if (!textarea) return;
    // Skip if user has unsent text — refuse to overwrite it.
    if ((textarea.value || '').trim() !== '') return;

    var origColor = textarea.style.color;
    var origCaret = textarea.style.caretColor;
    textarea.style.setProperty('color', 'transparent', 'important');
    textarea.style.setProperty('caret-color', 'transparent', 'important');
    try {
      var proto = W.HTMLTextAreaElement.prototype;
      var setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
      setter.call(textarea, '__CCMODEL:' + name);
      textarea.dispatchEvent(new Event('input', { bubbles: true }));
      setTimeout(function () {
        var enterEvt = new KeyboardEvent('keydown', {
          key: 'Enter', code: 'Enter', keyCode: 13, which: 13,
          bubbles: true, cancelable: true,
        });
        textarea.dispatchEvent(enterEvt);
        var btns = chatInput.querySelectorAll('button');
        for (var i = 0; i < btns.length; i++) {
          if (btns[i].id !== 'chat-upload-btn' && btns[i].id !== 'cc-model-pill') {
            btns[i].click();
            break;
          }
        }
        setTimeout(function () {
          textarea.style.color = origColor;
          textarea.style.caretColor = origCaret;
        }, 400);
      }, 50);
    } catch (err) {
      textarea.style.color = origColor;
      textarea.style.caretColor = origCaret;
    }
  }

  function runAll() {
    safeCall(ensureUploadBtn, 'ensureUploadBtn');
    safeCall(patchAccept, 'patchAccept');
    safeCall(syncChipRail, 'syncChipRail');
    safeCall(killBottomBg, 'killBottomBg');
    safeCall(disableChatMessageButtonKeyboard, 'disableChatMessageButtonKeyboard');
    safeCall(pushSignOutUp, 'pushSignOutUp');
    safeCall(ensureModelPill, 'ensureModelPill');
  }

  // Reset killBottomBg's sentinel so we re-paint transparent bg on
  // the next tick. Called when Streamlit reruns and may have given us
  // a fresh bottom container with default white styling.
  function invalidateBgSentinel() {
    var D = window.parent.document;
    var bottom = D.querySelector('[data-testid="stBottom"]')
              || D.querySelector('[data-testid="stBottomBlockContainer"]');
    if (bottom && bottom.dataset.ccBgKilled) delete bottom.dataset.ccBgKilled;
  }

  runAll();
  setTimeout(runAll, 300);
  setTimeout(runAll, 1200);
  // Heartbeat polling at a much longer interval (1.5s vs 700ms) since
  // the FAST PATH early-exits in each function make per-tick cost ~0
  // when nothing has changed. The MutationObserver below picks up
  // real Streamlit reruns immediately, so the longer interval doesn't
  // make recovery feel sluggish.
  setInterval(runAll, 1500);

  // React instantly to Streamlit rerunning the chat input area or the
  // sidebar. When children change, invalidate the bg sentinel so
  // killBottomBg re-runs on the next tick, and re-run setup.
  try {
    var D = window.parent.document;
    // Watch the sidebar shallowly so pushSignOutUp re-applies its
    // inline margin after each Streamlit rerun replaces the sign-out
    // button's wrapper. Shallow (subtree:false) keeps it cheap.
    var targets = [
      D.querySelector('[data-testid="stBottom"]'),
      D.querySelector('[data-testid="stMain"]'),
      D.querySelector('section[data-testid="stSidebar"]'),
    ].filter(Boolean);
    if (targets.length === 0) targets = [D.body];
    if (typeof MutationObserver !== 'undefined') {
      var lastRunAt = 0;
      var obs = new MutationObserver(function () {
        var now = Date.now();
        if (now - lastRunAt < 250) return;
        lastRunAt = now;
        invalidateBgSentinel();
        runAll();
      });
      for (var t = 0; t < targets.length; t++) {
        obs.observe(targets[t], { childList: true, subtree: false });
      }
    }
  } catch (err) { /* MutationObserver setup is best-effort */ }

})();
</script>
"""


_SIDEBAR_TOGGLE_JS = """
<script>
(function () {
  var CHEVRON_RIGHT = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18l6-6-6-6"/></svg>';

  function isCollapsed(sb) {
    if (!sb) return true;
    var rect = sb.getBoundingClientRect();
    if (rect.width < 100) return true;
    if (sb.style.visibility === 'hidden') return true;
    var tx = sb.style.transform || '';
    if (tx.indexOf('-100') !== -1) return true;
    if (sb.getAttribute('aria-expanded') === 'false') return true;
    return false;
  }

  function expandSidebar() {
    var D = window.parent.document;
    var sb = D.querySelector('section[data-testid="stSidebar"]');
    if (!sb) return;
    var sels = [
      '[data-testid="stSidebarCollapsedControl"] button',
      '[data-testid="collapsedControl"] button',
      'button[data-testid="stSidebarCollapseButton"]',
      'button[kind="headerNoPadding"]'
    ];
    for (var i = 0; i < sels.length; i++) {
      var el = D.querySelector(sels[i]);
      if (el && el.offsetParent !== null) { el.click(); return; }
    }
    sb.style.setProperty('transform', 'translateX(0)', 'important');
    sb.style.setProperty('visibility', 'visible', 'important');
    sb.style.setProperty('display', 'flex', 'important');
    sb.style.setProperty('min-width', '244px', 'important');
    sb.style.setProperty('width', '244px', 'important');
    sb.style.setProperty('margin-left', '0', 'important');
    sb.setAttribute('aria-expanded', 'true');
  }

  function ensureToggle() {
    var D = window.parent.document;
    if (!D || !D.body) return;
    var btn = D.getElementById('coebot-sidebar-toggle');
    if (!btn) {
      btn = D.createElement('button');
      btn.id = 'coebot-sidebar-toggle';
      btn.type = 'button';
      btn.title = 'Open sidebar';
      btn.setAttribute('aria-label', 'Open sidebar');
      btn.innerHTML = CHEVRON_RIGHT;
      btn.style.cssText = [
        'position:fixed','top:14px','left:14px','z-index:999999',
        'width:32px','height:32px','background:transparent','color:#0C5BA8',
        'border:none','padding:0','cursor:pointer','display:inline-flex',
        'align-items:center','justify-content:center',
        'transition:opacity 0.15s ease','outline:none'
      ].join(';');
      btn.addEventListener('mouseenter', function () { btn.style.opacity = '0.65'; });
      btn.addEventListener('mouseleave', function () { btn.style.opacity = '1'; });
      btn.addEventListener('click', expandSidebar);
      D.body.appendChild(btn);
    }
    var sb = D.querySelector('section[data-testid="stSidebar"]');
    var shouldShow = isCollapsed(sb) ? 'inline-flex' : 'none';
    // Only write to the DOM if the visibility actually needs to change.
    // Avoids invalidating layout on every polling tick.
    if (btn.style.display !== shouldShow) {
      btn.style.display = shouldShow;
    }
  }

  ensureToggle();
  setTimeout(ensureToggle, 300);
  setTimeout(ensureToggle, 1200);
  // Heartbeat at 1.5s instead of 600ms — the if-changed guard above
  // makes per-tick cost ~0 when the sidebar state is steady.
  setInterval(ensureToggle, 1500);
})();
</script>
"""


# CSS that fully hides the sidebar + sidebar-toggle. Applied only on the
# login page so the form gets the whole viewport.
_HIDE_SIDEBAR_CSS = """
<style>
section[data-testid="stSidebar"] { display: none !important; }
#coebot-sidebar-toggle { display: none !important; }
</style>
"""


def _get_store() -> UserStore:
    return UserStore(_USERS_PATH)


def _get_session_store() -> ActiveSessionStore:
    return ActiveSessionStore(_SESSION_PATH)


# ----------------------------------------------------------------------------
# Cached RAG singletons. Streamlit's @st.cache_resource keeps these alive
# across reruns so the embedding model loads exactly once per server.
# ----------------------------------------------------------------------------


@st.cache_resource(show_spinner=False)
def _settings() -> Settings:
    return get_settings()


@st.cache_resource(show_spinner="Loading embedding model — first run takes a few seconds")
def _embedder() -> Embedder:
    return Embedder(_settings().embedding_model)


@st.cache_resource(show_spinner=False)
def _vector_store() -> VectorStore:
    s = _settings()
    return VectorStore(persist_dir=s.chroma_persist_dir, collection_name=s.chroma_collection)


def _resolve_model_path(models_dir: Path, explicit_filename: str) -> Path:
    """Pick the GGUF file to load.

    If ``explicit_filename`` is set, use exactly that (relative to
    ``models_dir``). Otherwise, auto-detect the first ``.gguf`` file
    in the directory (alphabetical order).

    Raises:
        FileNotFoundError: with a UI-friendly message if no model
            file can be located.
    """
    if explicit_filename:
        path = models_dir / explicit_filename
        if not path.exists():
            raise FileNotFoundError(
                f"MODEL_FILENAME points to {explicit_filename} but that file "
                f"is not in {models_dir}. Place the .gguf file there or unset "
                "MODEL_FILENAME to auto-detect."
            )
        return path

    if not models_dir.exists():
        raise FileNotFoundError(
            f"Models directory does not exist: {models_dir}. "
            "Create it and drop a .gguf model file inside."
        )
    candidates = sorted(models_dir.glob("*.gguf"))
    if not candidates:
        raise FileNotFoundError(
            f"No .gguf model file found in {models_dir}. "
            "Download a chat-tuned GGUF model (e.g., Qwen 2.5 7B Instruct Q4_K_M) "
            "from HuggingFace and place it in that folder."
        )
    return candidates[0]


@st.cache_resource(show_spinner=False)
def _llm_client(model_filename: str) -> LlmClient:
    """Load the given GGUF as an LlmClient.

    The ``model_filename`` argument is part of the cache key, so
    selecting a different model in the UI causes Streamlit to return
    a NEW cached client (loading the new file) instead of reusing
    the previous one. Empty string triggers auto-detect of the first
    .gguf found in models_dir.
    """
    s = _settings()
    model_path = _resolve_model_path(s.models_dir, model_filename)
    return LlmClient(
        model_path=model_path,
        n_ctx=s.model_n_ctx,
        n_threads=s.model_n_threads or None,
        strip_think_tags=s.strip_think_tags,
        max_tokens=s.model_max_tokens,
        kv_cache_dir=s.kv_cache_dir if s.kv_cache_enabled else None,
        kv_cache_bytes=s.kv_cache_gb * 1024**3,
    )


_ICON_BY_EXT = {"pdf": "📄", "docx": "📝", "xlsx": "📊"}


def _render_attachment_chips(names: list[str], msg_idx: int) -> None:
    """Render attachment chips inside a chat bubble.

    Each chip is a Streamlit button keyed on (msg_idx, name) so clicks
    can mutate session_state.preview_doc and reuse _preview_dialog.
    """
    if not names:
        return
    max_visible = 6
    visible = names[:max_visible]
    per_row = 3

    rows_needed = (len(visible) + per_row - 1) // per_row
    for row in range(rows_needed):
        start = row * per_row
        end = min(start + per_row, len(visible))
        cols = st.columns(per_row)
        for i, name in enumerate(visible[start:end]):
            with cols[i]:
                ext = Path(name).suffix.lstrip(".").lower()
                icon = _ICON_BY_EXT.get(ext, "📄")
                label = name if len(name) <= 24 else name[:21] + "..."
                if st.button(
                    f"{icon} {label}",
                    key=f"att_{msg_idx}_{name}",
                    help=f"Click to preview {name}",
                    use_container_width=True,
                ):
                    full_path = _docs_dir() / name
                    if full_path.exists():
                        st.session_state.preview_doc = str(full_path)
                        st.rerun()
                    else:
                        st.toast(
                            f"{name} no longer exists on disk.", icon="⚠️"
                        )

    if len(names) > max_visible:
        st.caption(f"_+ {len(names) - max_visible} more attached_")


def _render_message(msg: dict, idx: int = 0) -> None:
    """Render one chat message bubble. Shared by history loop + inline render."""
    with st.chat_message(msg["role"]):
        attachments = msg.get("attachments") or []
        if attachments:
            _render_attachment_chips(attachments, msg_idx=idx)
        st.markdown(msg["content"])
        sources = msg.get("sources") or []
        if sources:
            with st.expander("Sources used", expanded=False):
                for src in sources:
                    # Handle both RetrievedChunk objects (live RAG) and
                    # plain dicts (loaded from disk).
                    if isinstance(src, dict):
                        src_path = src.get("source", "")
                        src_name = Path(str(src_path)).name
                        page_index = int(src.get("page_index", 0))
                        text = str(src.get("text", ""))
                    else:
                        src_name = src.source.name
                        page_index = src.page_index
                        text = src.text
                    st.caption(f"📄 **{src_name}** — p.{page_index + 1}")
                    snippet = text
                    if len(snippet) > 400:
                        snippet = snippet[:400] + "..."
                    st.text(snippet)


def _docs_dir() -> Path:
    return _PROJECT_ROOT / "data" / "documents"


_SUPPORTED_EXTS = (".pdf", ".docx", ".xlsx")

_FILE_MIME = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _indexed_files() -> list[Path]:
    """All supported documents sitting in the documents directory."""
    d = _docs_dir()
    if not d.exists():
        return []
    return sorted(
        p for p in d.iterdir() if p.is_file() and p.suffix.lower() in _SUPPORTED_EXTS
    )


@st.cache_data(show_spinner=False, max_entries=20)
def _file_data_url(path_str: str, mtime_ns: int, size: int) -> str:
    """Return a base64 data URL for ``path_str``.

    Cached on (path, mtime, size) so a re-encoded copy of the same file
    isn't re-computed on every Streamlit rerun.
    """
    path = Path(path_str)
    mime = _FILE_MIME.get(path.suffix.lower(), "application/octet-stream")
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


@st.cache_data(show_spinner=False, max_entries=20)
def _docx_to_html(path_str: str, mtime_ns: int, size: int) -> str:
    """Convert a DOCX to a self-contained, styled HTML document.

    Images embedded in the DOCX become inline base64 data URIs so the
    output is fully self-contained and can be served from a blob URL
    without any companion asset files. Cached on (path, mtime, size).
    """
    import mammoth

    with open(path_str, "rb") as fh:
        result = mammoth.convert_to_html(fh)
    body_html = result.value or "<p style='color:#9ca3af'>(empty document)</p>"

    title = Path(path_str).name
    safe_title = (
        title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    return (
        "<!DOCTYPE html>\n"
        "<html lang='en'>\n"
        "<head>\n"
        "<meta charset='utf-8'>\n"
        f"<title>{safe_title}</title>\n"
        "<style>\n"
        "  html, body { margin: 0; padding: 0; background: #f3f4f6;"
        "    font-family: 'Calibri', 'Inter', -apple-system, BlinkMacSystemFont,"
        "    'Segoe UI', sans-serif; color: #111827; }\n"
        "  body { padding: 40px 16px; }\n"
        "  .doc-page { max-width: 850px; margin: 0 auto; background: white;"
        "    padding: 64px 80px; border-radius: 4px;"
        "    box-shadow: 0 6px 24px rgba(15, 23, 42, 0.08); font-size: 14.5px;"
        "    line-height: 1.65; }\n"
        "  .doc-page h1 { font-size: 1.8em; margin: 1.2em 0 0.5em; }\n"
        "  .doc-page h2 { font-size: 1.45em; margin: 1.1em 0 0.45em; }\n"
        "  .doc-page h3 { font-size: 1.2em; margin: 1em 0 0.4em; }\n"
        "  .doc-page p { margin: 0.65em 0; }\n"
        "  .doc-page ul, .doc-page ol { margin: 0.5em 0; padding-left: 1.6em; }\n"
        "  .doc-page table { border-collapse: collapse; width: 100%;"
        "    margin: 1em 0; font-size: 0.95em; }\n"
        "  .doc-page th, .doc-page td { border: 1px solid #d1d5db;"
        "    padding: 8px 12px; text-align: left; vertical-align: top; }\n"
        "  .doc-page th { background: #f9fafb; font-weight: 600; }\n"
        "  .doc-page img { max-width: 100%; height: auto; display: block;"
        "    margin: 1em auto; }\n"
        "  .doc-page a { color: #0C5BA8; text-decoration: underline; }\n"
        "  .doc-page blockquote { border-left: 3px solid #d1d5db;"
        "    margin: 1em 0; padding: 0.3em 1em; color: #4b5563; }\n"
        "  @media (max-width: 600px) { .doc-page { padding: 32px 24px; } }\n"
        "</style>\n"
        "</head>\n"
        "<body>\n"
        f"<div class='doc-page'>{body_html}</div>\n"
        "</body>\n"
        "</html>"
    )


@st.cache_data(show_spinner=False, max_entries=20)
def _xlsx_to_html(path_str: str, mtime_ns: int, size: int) -> str:
    """Convert an XLSX workbook to a self-contained, styled HTML document.

    Every sheet becomes its own card with a sticky header row, alternating
    row colours, and horizontal scroll for wide tables. Cached on
    (path, mtime, size) so re-rendering across reruns is free.
    """
    import pandas as pd

    sheets = pd.read_excel(path_str, sheet_name=None)
    title = Path(path_str).name
    safe_title = (
        title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )

    sheet_blocks: list[str] = []
    if not sheets:
        sheet_blocks.append(
            "<div class='sheet'><div class='sheet-title'>(empty workbook)</div></div>"
        )
    else:
        for name, df in sheets.items():
            safe_name = (
                str(name)
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            if df is None or df.empty:
                body_html = (
                    "<div class='empty-sheet'>(empty sheet)</div>"
                )
            else:
                body_html = df.to_html(
                    index=False,
                    na_rep="",
                    classes="sheet-table",
                    border=0,
                    escape=True,
                )
            sheet_blocks.append(
                f"<div class='sheet'>"
                f"<div class='sheet-title'>{safe_name}</div>"
                f"<div class='sheet-table-wrap'>{body_html}</div>"
                f"</div>"
            )

    return (
        "<!DOCTYPE html>\n"
        "<html lang='en'>\n"
        "<head>\n"
        "<meta charset='utf-8'>\n"
        f"<title>{safe_title}</title>\n"
        "<style>\n"
        "  html, body { margin: 0; padding: 0; background: #f3f4f6;"
        "    font-family: 'Inter', -apple-system, BlinkMacSystemFont,"
        "    'Segoe UI', sans-serif; color: #111827; }\n"
        "  body { padding: 40px 16px; }\n"
        "  .workbook { max-width: 1200px; margin: 0 auto; }\n"
        "  .sheet { background: white; margin-bottom: 24px;"
        "    border-radius: 8px; overflow: hidden;"
        "    box-shadow: 0 4px 16px rgba(15, 23, 42, 0.06);"
        "    border: 1px solid #e5e7eb; }\n"
        "  .sheet-title { background: #f8f9fa; padding: 12px 20px;"
        "    font-weight: 600; font-size: 14px; color: #111827;"
        "    border-bottom: 1px solid #e5e7eb; }\n"
        "  .sheet-table-wrap { overflow: auto; max-height: 600px; }\n"
        "  table.sheet-table { border-collapse: collapse; width: 100%;"
        "    font-size: 13px; }\n"
        "  table.sheet-table thead th { background: #f9fafb;"
        "    position: sticky; top: 0; z-index: 1; font-weight: 600;"
        "    color: #374151; border-bottom: 2px solid #d1d5db; }\n"
        "  table.sheet-table th, table.sheet-table td {"
        "    border: 1px solid #e5e7eb; padding: 7px 12px;"
        "    text-align: left; white-space: nowrap;"
        "    vertical-align: top; }\n"
        "  table.sheet-table tbody tr:nth-child(even) td {"
        "    background: #fafbfc; }\n"
        "  table.sheet-table tbody tr:hover td { background: #eff6ff; }\n"
        "  .empty-sheet { padding: 40px 20px; text-align: center;"
        "    color: #9ca3af; font-style: italic; }\n"
        "</style>\n"
        "</head>\n"
        "<body>\n"
        f"<div class='workbook'>{''.join(sheet_blocks)}</div>\n"
        "</body>\n"
        "</html>"
    )


@st.cache_data(show_spinner=False, max_entries=20)
def _pdf_first_page_png(path_str: str, mtime_ns: int, size: int) -> str:
    """Render the first page of a PDF as a base64-encoded PNG.

    Cached on (path, mtime, size) — rasterising a PDF page is the
    expensive step we don't want to repeat across Streamlit reruns.
    """
    import io

    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(path_str)
    try:
        if len(pdf) == 0:
            return ""
        page = pdf[0]
        # scale=2 → ~144 DPI; crisp on retina without bloating the PNG.
        bitmap = page.render(scale=2)
        pil = bitmap.to_pil()
        buf = io.BytesIO()
        pil.save(buf, format="PNG", optimize=True)
        return base64.b64encode(buf.getvalue()).decode("ascii")
    finally:
        pdf.close()


# ============================================================================
# Login / signup
# ============================================================================


def _render_login(store: UserStore) -> None:
    """Render the login/signup page (no sidebar)."""
    st.markdown(_HIDE_SIDEBAR_CSS, unsafe_allow_html=True)

    if "auth_mode" not in st.session_state:
        st.session_state.auth_mode = "signin" if store.has_users() else "signup"

    _, center, _ = st.columns([1, 2, 1])
    with center:
        st.markdown(
            f"""
            <div class='login-card'>
              <div class='login-logo'>{PNM_LOGO_SVG}</div>
              <div class='login-title'>COEBOT</div>
              <div class='login-subtitle'>Local document analysis.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.session_state.auth_mode == "signin":
            _render_signin(store)
        else:
            _render_signup(store)

    st.markdown(
        f"<div class='version-tag'>v{__version__}</div>",
        unsafe_allow_html=True,
    )


def _render_signin(store: UserStore) -> None:
    with st.form("signin_form", clear_on_submit=False):
        st.markdown("<div class='form-label'>Username</div>", unsafe_allow_html=True)
        username = st.text_input(
            "Username",
            key="signin_username",
            label_visibility="collapsed",
        )
        st.markdown("<div class='form-label'>Password</div>", unsafe_allow_html=True)
        password = st.text_input(
            "Password",
            type="password",
            key="signin_password",
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button(
            "Sign In",
            use_container_width=True,
            type="primary",
        )

    if submitted:
        if store.authenticate(username, password):
            st.session_state.user = username
            st.session_state.recording = True
            _get_session_store().set_active_user(username)
            st.rerun()
        else:
            st.error("Invalid username or password.")

    if store.has_users():
        st.caption("Don't have an account?")
        if st.button("Create one", key="goto_signup", use_container_width=False):
            st.session_state.auth_mode = "signup"
            st.rerun()


def _render_signup(store: UserStore) -> None:
    if not store.has_users():
        st.caption("Welcome. Create the first local account for this device.")

    with st.form("signup_form", clear_on_submit=False):
        st.markdown("<div class='form-label'>Username</div>", unsafe_allow_html=True)
        username = st.text_input(
            "Username",
            key="signup_username",
            label_visibility="collapsed",
        )
        st.markdown("<div class='form-label'>Password</div>", unsafe_allow_html=True)
        password = st.text_input(
            "Password",
            type="password",
            key="signup_password",
            label_visibility="collapsed",
        )
        st.markdown(
            "<div class='form-label'>Confirm password</div>", unsafe_allow_html=True
        )
        confirm = st.text_input(
            "Confirm password",
            type="password",
            key="signup_confirm",
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button(
            "Create Account",
            use_container_width=True,
            type="primary",
        )

    if submitted:
        if password != confirm:
            st.error("Passwords don't match.")
            return
        try:
            store.register(username, password)
        except UserStoreError as exc:
            st.error(str(exc))
            return
        st.session_state.user = username
        st.session_state.recording = True
        _get_session_store().set_active_user(username)
        st.rerun()

    if store.has_users():
        st.caption("Already have an account?")
        if st.button("Sign in", key="goto_signin", use_container_width=False):
            st.session_state.auth_mode = "signin"
            st.rerun()


# ============================================================================
# Document preview
# ============================================================================


def _render_preview(doc_path_str: str) -> None:
    """Render a preview of the given document in the main content area."""
    path = Path(doc_path_str)

    header_col, close_col = st.columns([8, 1])
    with header_col:
        suffix = path.suffix.lower()
        icon = {".pdf": "📄", ".docx": "📝", ".xlsx": "📊"}.get(suffix, "📄")
        st.markdown(f"### {icon}  {path.name}")
    with close_col:
        if st.button("✕", key="preview_close", help="Close preview"):
            st.session_state.preview_doc = None
            st.rerun()

    if not path.exists():
        st.error("This file no longer exists on disk.")
        return

    if suffix == ".pdf":
        _render_pdf_preview(path)
    elif suffix == ".docx":
        _render_docx_preview(path)
    elif suffix == ".xlsx":
        _render_xlsx_preview(path)
    else:
        st.error(f"Cannot preview file type: {suffix}")




def _render_pdf_preview(path: Path) -> None:
    from doc_analyzer.parsers.pdf import parse_pdf

    try:
        data = path.read_bytes()
    except Exception as exc:
        st.error(f"Could not read PDF file: {exc}")
        return

    stat = path.stat()
    try:
        img_b64 = _pdf_first_page_png(str(path), stat.st_mtime_ns, stat.st_size)
    except Exception as exc:
        st.warning(f"Could not render PDF thumbnail: {exc}")
        img_b64 = ""

    pdf_b64 = base64.b64encode(data).decode("ascii")

    if img_b64:
        components.html(
            f"""
            <div style="display:flex; justify-content:center; padding:18px 0 8px 0;">
              <a id="cc-pdf-thumb-link" href="#"
                 title="Click to open in new tab"
                 style="display:block; cursor:pointer; text-decoration:none;
                        position:relative; width:78%; max-width:480px;
                        transition:transform 0.2s ease;"
                 onmouseover="this.style.transform='translateY(-4px) scale(1.01)';"
                 onmouseout="this.style.transform='translateY(0) scale(1)';">
                <div style="position:absolute; top:8px; left:8px; right:-8px; bottom:-8px;
                            background:white; border:1px solid #e5e7eb;
                            border-radius:14px; z-index:1;
                            box-shadow:0 2px 6px rgba(15,23,42,0.06);"></div>
                <div style="position:absolute; top:4px; left:4px; right:-4px; bottom:-4px;
                            background:white; border:1px solid #e5e7eb;
                            border-radius:14px; z-index:2;
                            box-shadow:0 2px 6px rgba(15,23,42,0.07);"></div>
                <img src="data:image/png;base64,{img_b64}"
                     alt="First page preview"
                     style="position:relative; z-index:3; width:100%; display:block;
                            border:1px solid #d1d5db; border-radius:14px;
                            background:white;
                            box-shadow:0 10px 28px rgba(15,23,42,0.12);" />
              </a>
            </div>
            <div style="text-align:center; margin-top:18px;">
              <a id="cc-pdf-btn-link" href="#"
                 style="display:inline-flex; align-items:center; gap:6px;
                        padding:9px 20px; border-radius:9999px;
                        background:#0C5BA8; color:white; text-decoration:none;
                        font-family:Inter,sans-serif; font-size:14px;
                        font-weight:500; transition:background 0.15s ease;"
                 onmouseover="this.style.background='#084a8c';"
                 onmouseout="this.style.background='#0C5BA8';">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                     stroke="currentColor" stroke-width="2.5" stroke-linecap="round"
                     stroke-linejoin="round">
                  <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
                  <polyline points="15 3 21 3 21 9"/>
                  <line x1="10" y1="14" x2="21" y2="3"/>
                </svg>
                Open in new tab
              </a>
            </div>
            <script>
            (function () {{
              try {{
                var b64 = "{pdf_b64}";
                var bin = atob(b64);
                var bytes = new Uint8Array(bin.length);
                for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
                var blob = new Blob([bytes], {{ type: 'application/pdf' }});
                var blobUrl = URL.createObjectURL(blob);
                var thumb = document.getElementById('cc-pdf-thumb-link');
                var btn = document.getElementById('cc-pdf-btn-link');
                [thumb, btn].forEach(function (el) {{
                  if (!el) return;
                  el.href = blobUrl;
                  el.target = '_blank';
                  el.rel = 'noopener noreferrer';
                }});
              }} catch (err) {{
                console.error('Failed to create blob URL for PDF:', err);
              }}
            }})();
            </script>
            """,
            height=720,
        )
    else:
        st.info("PDF thumbnail unavailable — use the download button below.")

    col_dl, _ = st.columns([1, 4])
    with col_dl:
        st.download_button(
            "⬇  Download PDF",
            data,
            file_name=path.name,
            mime="application/pdf",
            use_container_width=True,
        )

    with st.expander("Show extracted text", expanded=False):
        try:
            doc = parse_pdf(path)
        except Exception as exc:
            st.warning(f"Could not extract text: {exc}")
            return
        for i, page in enumerate(doc.pages, 1):
            st.markdown(f"**Page {i}**")
            st.text(page if page.strip() else "(empty page)")


def _render_docx_preview(path: Path) -> None:
    from doc_analyzer.parsers.docx import parse_docx

    try:
        data = path.read_bytes()
    except Exception as exc:
        st.error(f"Could not read DOCX file: {exc}")
        return

    stat = path.stat()
    try:
        html_doc = _docx_to_html(str(path), stat.st_mtime_ns, stat.st_size)
    except Exception as exc:
        st.warning(f"Could not render DOCX preview: {exc}")
        html_doc = ""

    html_b64 = base64.b64encode(html_doc.encode("utf-8")).decode("ascii") if html_doc else ""

    if html_b64:
        components.html(
            f"""
            <div style="display:flex; justify-content:center; padding:18px 0 8px 0;">
              <div style="position:relative; width:78%; max-width:480px;
                          transition:transform 0.2s ease;"
                   id="cc-docx-card"
                   onmouseover="this.style.transform='translateY(-4px) scale(1.01)';"
                   onmouseout="this.style.transform='translateY(0) scale(1)';">
                <div style="position:absolute; top:8px; left:8px; right:-8px; bottom:-8px;
                            background:white; border:1px solid #e5e7eb;
                            border-radius:14px; z-index:1;
                            box-shadow:0 2px 6px rgba(15,23,42,0.06);"></div>
                <div style="position:absolute; top:4px; left:4px; right:-4px; bottom:-4px;
                            background:white; border:1px solid #e5e7eb;
                            border-radius:14px; z-index:2;
                            box-shadow:0 2px 6px rgba(15,23,42,0.07);"></div>
                <div style="position:relative; z-index:3; border:1px solid #d1d5db;
                            border-radius:14px; overflow:hidden; background:white;
                            box-shadow:0 10px 28px rgba(15,23,42,0.12);
                            aspect-ratio: 8.5 / 11;">
                  <iframe id="cc-docx-thumb-iframe"
                          style="width:100%; height:100%; border:none;
                                 pointer-events:none; background:white;"
                          scrolling="no"
                          sandbox="allow-same-origin"
                          title="Document preview"></iframe>
                </div>
                <a id="cc-docx-thumb-link" href="#" target="_blank"
                   rel="noopener noreferrer"
                   title="Click to open in new tab"
                   style="position:absolute; inset:0; z-index:4; cursor:pointer;
                          border-radius:14px;"></a>
              </div>
            </div>
            <div style="text-align:center; margin-top:18px;">
              <a id="cc-docx-btn-link" href="#" target="_blank"
                 rel="noopener noreferrer"
                 style="display:inline-flex; align-items:center; gap:6px;
                        padding:9px 20px; border-radius:9999px;
                        background:#0C5BA8; color:white; text-decoration:none;
                        font-family:Inter,sans-serif; font-size:14px;
                        font-weight:500; transition:background 0.15s ease;"
                 onmouseover="this.style.background='#084a8c';"
                 onmouseout="this.style.background='#0C5BA8';">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                     stroke="currentColor" stroke-width="2.5" stroke-linecap="round"
                     stroke-linejoin="round">
                  <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
                  <polyline points="15 3 21 3 21 9"/>
                  <line x1="10" y1="14" x2="21" y2="3"/>
                </svg>
                Open in new tab
              </a>
            </div>
            <script>
            (function () {{
              try {{
                var b64 = "{html_b64}";
                var bin = atob(b64);
                var bytes = new Uint8Array(bin.length);
                for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
                var blob = new Blob([bytes], {{ type: 'text/html;charset=utf-8' }});
                var blobUrl = URL.createObjectURL(blob);
                var iframe = document.getElementById('cc-docx-thumb-iframe');
                var thumb = document.getElementById('cc-docx-thumb-link');
                var btn = document.getElementById('cc-docx-btn-link');
                if (iframe) iframe.src = blobUrl;
                [thumb, btn].forEach(function (el) {{
                  if (!el) return;
                  el.href = blobUrl;
                }});
              }} catch (err) {{
                console.error('Failed to create blob URL for DOCX:', err);
              }}
            }})();
            </script>
            """,
            height=720,
        )
    else:
        st.info("DOCX preview unavailable — use the download button below.")

    col_dl, _ = st.columns([1, 4])
    with col_dl:
        st.download_button(
            "⬇  Download DOCX",
            data,
            file_name=path.name,
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True,
        )

    with st.expander("Show extracted text", expanded=False):
        try:
            doc = parse_docx(path)
        except Exception as exc:
            st.warning(f"Could not extract text: {exc}")
            return
        if doc.metadata:
            meta_bits = " · ".join(
                f"**{k.title()}**: {v}" for k, v in doc.metadata.items()
            )
            st.caption(meta_bits)
        body = "\n\n".join(p for p in doc.pages if p.strip()) or "_(empty document)_"
        st.markdown(
            f"<div class='docx-preview'>{body.replace(chr(10), '<br>')}</div>",
            unsafe_allow_html=True,
        )


@st.dialog("Document Preview", width="large")
def _preview_dialog(doc_path_str: str) -> None:
    _render_preview(doc_path_str)


def _render_xlsx_preview(path: Path) -> None:
    try:
        data = path.read_bytes()
    except Exception as exc:
        st.error(f"Could not read XLSX file: {exc}")
        return

    stat = path.stat()
    try:
        html_doc = _xlsx_to_html(str(path), stat.st_mtime_ns, stat.st_size)
    except Exception as exc:
        st.warning(f"Could not render XLSX preview: {exc}")
        html_doc = ""

    html_b64 = base64.b64encode(html_doc.encode("utf-8")).decode("ascii") if html_doc else ""

    if html_b64:
        components.html(
            f"""
            <div style="display:flex; justify-content:center; padding:18px 0 8px 0;">
              <div style="position:relative; width:78%; max-width:480px;
                          transition:transform 0.2s ease;"
                   id="cc-xlsx-card"
                   onmouseover="this.style.transform='translateY(-4px) scale(1.01)';"
                   onmouseout="this.style.transform='translateY(0) scale(1)';">
                <div style="position:absolute; top:8px; left:8px; right:-8px; bottom:-8px;
                            background:white; border:1px solid #e5e7eb;
                            border-radius:14px; z-index:1;
                            box-shadow:0 2px 6px rgba(15,23,42,0.06);"></div>
                <div style="position:absolute; top:4px; left:4px; right:-4px; bottom:-4px;
                            background:white; border:1px solid #e5e7eb;
                            border-radius:14px; z-index:2;
                            box-shadow:0 2px 6px rgba(15,23,42,0.07);"></div>
                <div style="position:relative; z-index:3; border:1px solid #d1d5db;
                            border-radius:14px; overflow:hidden; background:white;
                            box-shadow:0 10px 28px rgba(15,23,42,0.12);
                            aspect-ratio: 8.5 / 11;">
                  <iframe id="cc-xlsx-thumb-iframe"
                          style="width:100%; height:100%; border:none;
                                 pointer-events:none; background:white;"
                          scrolling="no"
                          sandbox="allow-same-origin"
                          title="Workbook preview"></iframe>
                </div>
                <a id="cc-xlsx-thumb-link" href="#" target="_blank"
                   rel="noopener noreferrer"
                   title="Click to open in new tab"
                   style="position:absolute; inset:0; z-index:4; cursor:pointer;
                          border-radius:14px;"></a>
              </div>
            </div>
            <div style="text-align:center; margin-top:18px;">
              <a id="cc-xlsx-btn-link" href="#" target="_blank"
                 rel="noopener noreferrer"
                 style="display:inline-flex; align-items:center; gap:6px;
                        padding:9px 20px; border-radius:9999px;
                        background:#0C5BA8; color:white; text-decoration:none;
                        font-family:Inter,sans-serif; font-size:14px;
                        font-weight:500; transition:background 0.15s ease;"
                 onmouseover="this.style.background='#084a8c';"
                 onmouseout="this.style.background='#0C5BA8';">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                     stroke="currentColor" stroke-width="2.5" stroke-linecap="round"
                     stroke-linejoin="round">
                  <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
                  <polyline points="15 3 21 3 21 9"/>
                  <line x1="10" y1="14" x2="21" y2="3"/>
                </svg>
                Open in new tab
              </a>
            </div>
            <script>
            (function () {{
              try {{
                var b64 = "{html_b64}";
                var bin = atob(b64);
                var bytes = new Uint8Array(bin.length);
                for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
                var blob = new Blob([bytes], {{ type: 'text/html;charset=utf-8' }});
                var blobUrl = URL.createObjectURL(blob);
                var iframe = document.getElementById('cc-xlsx-thumb-iframe');
                var thumb = document.getElementById('cc-xlsx-thumb-link');
                var btn = document.getElementById('cc-xlsx-btn-link');
                if (iframe) iframe.src = blobUrl;
                [thumb, btn].forEach(function (el) {{
                  if (!el) return;
                  el.href = blobUrl;
                }});
              }} catch (err) {{
                console.error('Failed to create blob URL for XLSX:', err);
              }}
            }})();
            </script>
            """,
            height=720,
        )
    else:
        st.info("XLSX preview unavailable — use the download button below.")

    col_dl, _ = st.columns([1, 4])
    with col_dl:
        st.download_button(
            "⬇  Download XLSX",
            data,
            file_name=path.name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    with st.expander("Show sheets as tables", expanded=False):
        try:
            import pandas as pd

            sheets = pd.read_excel(path, sheet_name=None)
        except Exception as exc:
            st.warning(f"Could not parse XLSX: {exc}")
            return
        if not sheets:
            st.info("This workbook has no sheets.")
            return
        sheet_names = list(sheets.keys())
        tabs = st.tabs(sheet_names)
        for tab, name in zip(tabs, sheet_names):
            with tab:
                df = sheets[name]
                st.dataframe(df, use_container_width=True, hide_index=False)


# ============================================================================
# Main UI
# ============================================================================


def _render_main(user: str) -> None:
    # --- Preview dialog (opens when a chip body is clicked) ----------------
    if st.session_state.get("preview_doc"):
        _preview_dialog(st.session_state.preview_doc)

    # --- Sidebar -----------------------------------------------------------
    with st.sidebar:
        st.markdown(
            f"<div class='sidebar-logo'>{PNM_LOGO_SVG}</div>",
            unsafe_allow_html=True,
        )

        # New Chat button — saves the current chat (if any) and resets to
        # an empty state. Real button now (not just a static div) so it
        # can actually start a new conversation.
        if st.button(
            "＋  New Chat",
            key="new_chat_btn",
            use_container_width=True,
        ):
            _start_new_chat()
            st.rerun()

        # Recents list — rendered inside a native Streamlit scroll
        # container. Using st.container(height=...) lets React/Streamlit
        # manage the scrollable region rather than our JS reaching in
        # and wrapping rows after the fact. This is the fix for the
        # "delete chat → blank white page" race: the previous JS
        # approach competed with Streamlit's React reconciler during
        # the post-delete rerun, and any half-completed DOM mutation
        # could blank the viewport until a manual refresh.
        all_chats = _list_chats()
        if all_chats:
            st.markdown(
                "<div class='recents-header'>Recents</div>",
                unsafe_allow_html=True,
            )
            current_id = st.session_state.get("current_chat_id")
            with st.container(height=320, border=False):
                for chat in all_chats:
                    cid = chat["id"]
                    title = chat["title"]
                    display_title = title if len(title) <= 32 else title[:29] + "..."
                    is_current = cid == current_id
                    cols = st.columns([5, 1])
                    with cols[0]:
                        if st.button(
                            display_title,
                            key=f"open_chat_{cid}",
                            help=title,
                            use_container_width=True,
                            type="primary" if is_current else "secondary",
                        ):
                            _switch_to_chat(cid)
                            st.rerun()
                    with cols[1]:
                        if st.button(
                            "×",
                            key=f"del_chat_{cid}",
                            help="Delete this chat",
                        ):
                            _delete_chat_file(cid)
                            if is_current:
                                st.session_state.current_chat_id = None
                                st.session_state.current_chat_created_at = None
                                st.session_state.messages = []
                                st.session_state.pending_question = None
                                _save_current_chat_id(None)
                            st.rerun()

        # Memory panel — a popover (floating window) so opening it does
        # not push the sidebar content down. Native st.popover, same
        # crash-safe primitive as the mode/model pills.
        mem_records = _memory().load()
        with st.popover(
            f"🧠  Memory ({len(mem_records)})",
            use_container_width=True,
        ):
            st.markdown("##### What COEBOT remembers about you")
            if not mem_records:
                st.caption(
                    'Nothing yet. Say "remember: ..." / "ingat: ..." in a '
                    "chat, or just mention things about yourself — COEBOT "
                    "picks them up automatically."
                )
            else:
                for i, rec in enumerate(mem_records):
                    fact_col, del_col = st.columns([6, 1])
                    with fact_col:
                        st.markdown(rec["fact"])
                    with del_col:
                        if st.button(
                            "×",
                            key=f"mem_del_{i}",
                            help="Forget this",
                        ):
                            _memory().remove(rec["fact"])
                            st.rerun()
                st.divider()
                if st.button(
                    "🗑  Clear all memory",
                    key="mem_clear_all",
                    use_container_width=True,
                ):
                    _memory().clear()
                    st.rerun()

        # Profile block — user-row + Sign out grouped in a single
        # st.container() so they form ONE child of the sidebar's
        # vertical block. CSS then pushes the whole group to the bottom
        # via margin-top:auto. Without this grouping, margin-top:auto
        # on user-row alone pushes only it to the bottom and Sign out
        # (the next sibling) overflows past the sidebar's bottom edge.
        with st.container():
            st.markdown(
                "<div class='user-row'>"
                "<div class='left'>"
                f"<span class='user-avatar'>{user[:1].upper()}</span>"
                f"<span>{user}</span>"
                "</div>"
                "<span class='gear'>⚙</span>"
                "</div>",
                unsafe_allow_html=True,
            )
            if st.button("Sign out", key="signout", use_container_width=True):
                _persist_current_chat()
                _get_session_store().clear()
                _save_pending_attachments([])
                _save_current_chat_id(None)
                st.session_state.pop("user", None)
                st.session_state.pop("auth_mode", None)
                st.session_state.pop("preview_doc", None)
                st.session_state.pop("messages", None)
                st.session_state.pop("pending_question", None)
                st.session_state.pop("pending_attachments", None)
                st.session_state.pop("consumed_upload_ids", None)
                st.session_state.pop("current_chat_id", None)
                st.session_state.pop("current_chat_created_at", None)
                st.rerun()

    # --- Session-mode state ------------------------------------------------
    if "recording" not in st.session_state:
        st.session_state.recording = True
    if "current_chat_id" not in st.session_state:
        # Try to restore the chat the user was last viewing, so a
        # browser refresh lands them back where they were.
        last_id = _load_current_chat_id()
        loaded = _load_chat(last_id) if last_id else None
        if loaded is not None:
            st.session_state.current_chat_id = last_id
            st.session_state.current_chat_created_at = loaded.get("created_at")
            st.session_state.messages = list(loaded.get("messages", []))
        else:
            st.session_state.current_chat_id = None
            st.session_state.current_chat_created_at = None
            if "messages" not in st.session_state:
                st.session_state.messages = []
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "pending_question" not in st.session_state:
        st.session_state.pending_question = None
    if "pending_attachments" not in st.session_state:
        # Restore from disk so chips survive browser refresh.
        st.session_state.pending_attachments = _load_pending_attachments()
    if "consumed_upload_ids" not in st.session_state:
        st.session_state.consumed_upload_ids = set()
    if "selected_model_filename" not in st.session_state:
        # Persisted selection wins; else the config default (which may
        # be empty for auto-detect on first .gguf found).
        persisted = _load_selected_model_filename()
        st.session_state.selected_model_filename = (
            persisted or _settings().model_filename
        )

    if st.session_state.recording:
        hero_title = "COEBOT"
        hero_tagline = "Local document analysis."
        hero_tip = "Tip: Press Ctrl+B to quickly toggle the sidebar."
        pill_label = "●  Recording"
    else:
        hero_title = "○  Nobody"
        hero_tagline = "Who am I? I'm nobody."
        hero_tip = "Temporary session — won't be saved and nothing remembered."
        pill_label = "○  Nobody"

    # --- Hero (empty state) OR chat history --------------------------------
    if not st.session_state.messages:
        st.markdown(
            f"""
            <div class='hero'>
              <div class='hero-title'>{hero_title}</div>
              <div class='hero-tagline'>{hero_tagline}</div>
              <div class='hero-tip'>{hero_tip}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        for i, msg in enumerate(st.session_state.messages):
            _render_message(msg, idx=i)

    # --- Pending question — conversation-scoped routing --------------------
    # Documents belong to the conversation they were attached in.
    #   - This chat has attached documents → RAG scoped to ONLY those
    #     documents, grounded answer with page citations.
    #   - No documents in this chat → plain conversational chat, like a
    #     normal chatbot. The global index is never searched implicitly.
    if st.session_state.pending_question:
        question = st.session_state.pending_question
        st.session_state.pending_question = None

        # Documents attached anywhere in THIS conversation.
        chat_doc_names: list[str] = []
        for m in st.session_state.messages:
            for name in m.get("attachments") or []:
                if name not in chat_doc_names:
                    chat_doc_names.append(name)

        sources: list = []
        remember_match = None
        # One spinner for the whole pipeline. Text depends on whether
        # the selected model is already warm in the resource cache —
        # cold loads of large GGUFs take up to a minute.
        if "warm_models" not in st.session_state:
            st.session_state.warm_models = set()
        _sel_model = st.session_state.selected_model_filename
        _is_warm = _sel_model in st.session_state.warm_models
        if not _is_warm:
            _spinner_text = "Loading model — the first question can take up to a minute..."
        elif chat_doc_names:
            _spinner_text = (
                "COEBOT is reading your document(s) — full reads of large "
                "files can take a few minutes..."
            )
        else:
            _spinner_text = "COEBOT is thinking..."
        try:
            with st.spinner(_spinner_text):
                llm = _llm_client(_sel_model)
                st.session_state.warm_models.add(_sel_model)
                mem_facts = _memory().facts()
                remember_match = _REMEMBER_CMD_RE.match(question)
                if remember_match and not chat_doc_names:
                    # Explicit memory command — store instantly, no LLM.
                    fact = remember_match.group(1).strip()
                    if _memory().add(fact):
                        answer = Answer(
                            text=f"✅ Tersimpan / Saved to memory: *{fact}*",
                            sources=(),
                        )
                    else:
                        answer = Answer(
                            text="ℹ️ Sudah tersimpan sebelumnya / Already in memory.",
                            sources=(),
                        )
                elif chat_doc_names:
                    # DEEP-READ FIRST: feed the complete document(s) to
                    # the model when they fit the context budget. Falls
                    # back to excerpt retrieval for oversized documents.
                    existing_paths = [
                        p for p in (_docs_dir() / n for n in chat_doc_names) if p.exists()
                    ]
                    answer = None
                    if existing_paths:
                        answer = answer_full_documents(
                            question,
                            doc_paths=existing_paths,
                            llm=llm,
                            settings=_settings(),
                            memory_facts=mem_facts,
                        )
                    if answer is None:
                        # Full stored-path form — must match str(chunk.source)
                        # as written at ingestion (see VectorStore.query).
                        chat_doc_paths = [str(_docs_dir() / n) for n in chat_doc_names]
                        answer = answer_question(
                            question,
                            embedder=_embedder(),
                            store=_vector_store(),
                            llm=llm,
                            settings=_settings(),
                            source_paths=chat_doc_paths,
                            memory_facts=mem_facts,
                        )
                        answer = Answer(
                            text=answer.text
                            + "\n\n*(Documents were too large to read in full — "
                            "this answer is based on the most relevant retrieved "
                            "excerpts.)*",
                            sources=answer.sources,
                        )
                else:
                    # Recent turns give the model conversational memory.
                    history = [
                        {"role": m["role"], "content": m["content"]}
                        for m in st.session_state.messages[-10:]
                        if m.get("role") in ("user", "assistant")
                        and not str(m.get("content", "")).startswith("⚠️")
                    ]
                    answer = converse(history, llm=llm, memory_facts=mem_facts)
            response_text = answer.text
            sources = list(answer.sources)
        except FileNotFoundError as exc:
            # No .gguf in models/ (or MODEL_FILENAME points nowhere).
            response_text = f"⚠️ **No model available.** {exc}"
        except Exception as exc:  # noqa: BLE001 — surface any failure to the UI
            logger.exception("Chat pipeline failed")
            response_text = (
                "⚠️ **Something went wrong while generating the answer.**\n\n"
                f"`{exc}`"
            )
        assistant_msg = {
            "role": "assistant",
            "content": response_text,
            "sources": sources,
        }
        _render_message(assistant_msg, idx=len(st.session_state.messages))
        st.session_state.messages.append(assistant_msg)
        _persist_current_chat()

        # Auto-memory: when the user's message looks like it contains
        # personal information, distill one fact for long-term memory.
        # Runs AFTER the answer is already on screen; gated by a regex
        # so the extra (CPU-costly) LLM pass is rare.
        if (
            remember_match is None
            and not response_text.startswith("⚠️")
            and _PERSONAL_SIGNAL_RE.search(question)
        ):
            try:
                fact = extract_memory_fact(
                    question,
                    llm=_llm_client(st.session_state.selected_model_filename),
                )
                if fact and _memory().add(fact):
                    st.toast(f"Remembered: {fact}", icon="🧠")
            except Exception:  # noqa: BLE001 — memory is best-effort
                logger.debug("Memory extraction failed", exc_info=True)

    # --- Mode pill (centered above chat input) -----------------------------
    _left, center, _right = st.columns([4, 2, 4])
    with center, st.popover(pill_label, use_container_width=True):
        st.markdown("##### Session mode")

        rec_marker = "✓" if st.session_state.recording else "  "
        if st.button(
            f"{rec_marker}  ●  Recording",
            key="mode_recording",
            use_container_width=True,
        ):
            st.session_state.recording = True
            st.rerun()
        st.caption("Everything is saved to this device.")

        nob_marker = "✓" if not st.session_state.recording else "  "
        if st.button(
            f"{nob_marker}  ○  Nobody",
            key="mode_nobody",
            use_container_width=True,
        ):
            st.session_state.recording = False
            st.rerun()
        st.caption("Temporary session — nothing saved or remembered.")

    # --- Hidden model-source block -----------------------------------------
    # A hidden HTML block that carries model metadata for the custom
    # in-bar model pill (built entirely in JS). Rendered here in normal
    # flow so JS can read it on every tick. Not Streamlit-managed for
    # positioning — the JS reads it and builds its own UI in the chat bar.
    available_models = _list_available_models(_settings().models_dir)
    current_model = st.session_state.selected_model_filename
    if not current_model and available_models:
        current_model = available_models[0].name
    _model_items_html = []
    for path in available_models:
        size_gb = path.stat().st_size / (1024**3)
        is_current = "1" if path.name == current_model else "0"
        safe_name = path.name.replace("'", "&#39;").replace('"', "&quot;")
        _model_items_html.append(
            f"<span class='cc-model-item' "
            f"data-name='{safe_name}' "
            f"data-size='{size_gb:.1f}' "
            f"data-current='{is_current}'></span>"
        )
    _current_display = current_model if current_model else "No model"
    _safe_current = _current_display.replace("'", "&#39;").replace('"', "&quot;")
    st.markdown(
        "<div id='cc-model-source' style='display:none' "
        f"data-current-label='{_safe_current}'>"
        + "".join(_model_items_html)
        + "</div>",
        unsafe_allow_html=True,
    )

    # --- Hidden file uploader (triggered by paperclip in chat bar) --------
    # The uploader's key is STABLE so the paperclip's findFileInput()
    # always points at the same DOM input element across reruns. To
    # prevent re-processing the same UploadedFile on every rerun (which
    # would re-add already-sent files back into pending_attachments),
    # we track each upload's file_id in a session-state set and skip
    # any we've already consumed.
    uploads = st.file_uploader(
        "Upload document",
        type=["pdf", "docx", "xlsx"],
        accept_multiple_files=True,
        label_visibility="collapsed",
        key="doc_uploader",
    )
    if uploads:
        _docs_dir().mkdir(parents=True, exist_ok=True)
        attachment_changed = False
        for uf in uploads:
            fid = getattr(uf, "file_id", None) or f"{uf.name}|{uf.size}"
            if fid in st.session_state.consumed_upload_ids:
                continue
            st.session_state.consumed_upload_ids.add(fid)

            save_path = _docs_dir() / uf.name
            if not save_path.exists():
                with st.spinner(f"Indexing {uf.name}..."):
                    save_path.write_bytes(uf.getvalue())
                    try:
                        result = ingest_document(
                            save_path,
                            embedder=_embedder(),
                            store=_vector_store(),
                            settings=_settings(),
                        )
                        st.toast(
                            f"{uf.name} — {result.chunk_count} chunks, "
                            f"{result.page_count} pages",
                            icon="✅",
                        )
                    except Exception as exc:
                        save_path.unlink(missing_ok=True)
                        st.error(f"Could not index {uf.name}: {exc}")
                        continue
            if uf.name not in st.session_state.pending_attachments:
                st.session_state.pending_attachments.append(uf.name)
                attachment_changed = True
        if attachment_changed:
            _save_pending_attachments(st.session_state.pending_attachments)
            st.rerun()

    # --- Hidden chip source — JS mirrors these as small grey pills
    # --- inside the chat input bar (proper-chatbot pattern).
    # --- The rail now reflects pending_attachments (staged for next
    # --- message), NOT the full document library. Sending a message
    # --- clears the list; the underlying files remain on disk and
    # --- in ChromaDB so RAG retains memory of them.
    pending = st.session_state.pending_attachments
    visible_pending = [
        name for name in pending if (_docs_dir() / name).exists()
    ]
    if visible_pending:
        items = []
        for name in visible_pending[:8]:
            ext = Path(name).suffix.lstrip(".").lower() or "file"
            safe_name = name.replace("'", "&#39;").replace('"', "&quot;")
            items.append(
                f"<span class='cc-chip-item' data-name='{safe_name}'>{ext}</span>"
            )
        st.markdown(
            "<div id='cc-chip-source' style='display:none'>"
            + "".join(items)
            + "</div>",
            unsafe_allow_html=True,
        )

    # --- Chat input ----------------------------------------------------
    # --- The chip × delete uses the chat input itself as a JS-to-Python
    # --- bridge: it sets the value to "__CCDEL:<filename>" and submits.
    # --- Python detects the prefix here and performs the deletion. No
    # --- extra widgets to hide. The textarea is masked to transparent
    # --- text during the brief value-set + submit window.
    chat_value = st.chat_input("Message COEBOT ...")
    if chat_value and chat_value.startswith("__CCDEL:"):
        target_name = chat_value[len("__CCDEL:"):].strip()
        if target_name:
            file_path = _docs_dir() / target_name
            if file_path.exists():
                try:
                    _vector_store().delete_by_source(file_path)
                except Exception as exc:  # noqa: BLE001 - non-fatal; file still deleted below
                    logger.warning("Failed to delete %s from vector store: %s", target_name, exc)
                file_path.unlink(missing_ok=True)
            if target_name in st.session_state.pending_attachments:
                st.session_state.pending_attachments.remove(target_name)
                _save_pending_attachments(st.session_state.pending_attachments)
    if chat_value and chat_value.startswith("__CCPREVIEW:"):
        target_name = chat_value[len("__CCPREVIEW:"):].strip()
        if target_name:
            file_path = _docs_dir() / target_name
            if file_path.exists():
                st.session_state.preview_doc = str(file_path)
                st.rerun()
    if chat_value and chat_value.startswith("__CCMODEL:"):
        # Selection made in the custom in-bar model picker (built in JS).
        target_name = chat_value[len("__CCMODEL:"):].strip()
        if target_name:
            models_dir = _settings().models_dir
            if (models_dir / target_name).exists():
                st.session_state.selected_model_filename = target_name
                _save_selected_model_filename(target_name)
                st.rerun()
    if chat_value and not (
        chat_value.startswith("__CCDEL:")
        or chat_value.startswith("__CCPREVIEW:")
        or chat_value.startswith("__CCMODEL:")
    ):
        _ensure_chat_id()
        attached_names = list(st.session_state.pending_attachments)
        st.session_state.messages.append({
            "role": "user",
            "content": chat_value,
            "attachments": attached_names,
        })
        st.session_state.pending_attachments = []
        _save_pending_attachments([])
        st.session_state.pending_question = chat_value
        _persist_current_chat()
        st.rerun()

    # --- Sidebar toggle + chat-bar paperclip JS ---------------------------
    components.html(_SIDEBAR_TOGGLE_JS + _CHAT_UPLOAD_JS, height=0)


# ============================================================================
# Entry point
# ============================================================================


def render() -> None:
    st.set_page_config(
        page_title="COEBOT",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    # Animated PNM-colored background orbs — drift behind all content.
    st.markdown(
        """
        <div class='bg-orb bg-orb-blue'></div>
        <div class='bg-orb bg-orb-green'></div>
        <div class='bg-orb bg-orb-sky'></div>
        """,
        unsafe_allow_html=True,
    )

    store = _get_store()

    # Restore a persisted session if the browser was refreshed.
    if "user" not in st.session_state:
        active = _get_session_store().get_active_user()
        if active and store.get(active) is not None:
            st.session_state.user = active

    user = st.session_state.get("user")
    if not user:
        _render_login(store)
        return

    _render_main(user)


render()
