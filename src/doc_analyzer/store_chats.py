"""Chat persistence — plain JSON files, no UI-framework dependency.

One file per chat in ``data/chats/<uuid>.json``:

    {
      "id": "...", "title": "...", "favorite": false,
      "created_at": iso, "updated_at": iso,
      "messages": [{"role", "content", "ts", "attachments", "sources"}]
    }

Ported from the retired Streamlit UI so the HTTP backend and any future
frontend share one storage layer. Messages now carry a ``ts`` ISO
timestamp (older chats without one render without times).
"""

from __future__ import annotations

import contextlib
import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CHATS_DIR = _PROJECT_ROOT / "data" / "chats"
CURRENT_CHAT_PATH = _PROJECT_ROOT / "data" / "current_chat.json"
PENDING_PATH = _PROJECT_ROOT / "data" / "pending_attachments.json"
SELECTED_MODEL_PATH = _PROJECT_ROOT / "data" / "selected_model.json"
DOCS_DIR = _PROJECT_ROOT / "data" / "documents"

_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def new_chat_id() -> str:
    return str(uuid.uuid4())


def _chat_path(chat_id: str) -> Path | None:
    """Validated path for a chat id — refuses anything but a UUID."""
    if not _ID_RE.match(chat_id or ""):
        return None
    return CHATS_DIR / f"{chat_id}.json"


def derive_title(messages: list[dict[str, Any]]) -> str:
    """First user message becomes the title, truncated to ~50 chars."""
    for msg in messages:
        if msg.get("role") == "user":
            text = (msg.get("content") or "").strip().replace("\n", " ")
            if text:
                return text if len(text) <= 50 else text[:47] + "..."
    return "New chat"


def serialize_message(msg: dict[str, Any]) -> dict[str, Any]:
    """JSON-safe copy of a message (sources become plain dicts)."""
    out = {
        "role": msg.get("role"),
        "content": msg.get("content"),
    }
    if msg.get("ts"):
        out["ts"] = msg["ts"]
    if msg.get("attachments"):
        out["attachments"] = list(msg["attachments"])
    sources = msg.get("sources") or []
    if sources:
        plain = []
        for s in sources:
            if isinstance(s, dict):
                plain.append(s)
            else:  # RetrievedChunk-like object
                plain.append(
                    {
                        "source": str(getattr(s, "source", "")),
                        "page_index": getattr(s, "page_index", None),
                        "text": getattr(s, "text", ""),
                    }
                )
        out["sources"] = plain
    return out


def write_chat(chat: dict[str, Any]) -> None:
    path = _chat_path(chat["id"])
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(chat, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def load_chat(chat_id: str) -> dict[str, Any] | None:
    path = _chat_path(chat_id)
    if path is None or not path.exists():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return loaded if isinstance(loaded, dict) else None


def delete_chat(chat_id: str) -> bool:
    path = _chat_path(chat_id)
    if path is None or not path.exists():
        return False
    try:
        path.unlink()
        return True
    except OSError:
        return False


def persist_messages(
    chat_id: str,
    messages: list[dict[str, Any]],
    *,
    created_at: str | None = None,
    favorite: bool | None = None,
) -> dict[str, Any]:
    """Write the full chat; preserves created_at/favorite of an
    existing file unless overridden. Returns the stored chat dict."""
    existing = load_chat(chat_id) or {}
    now = now_iso()
    chat = {
        "id": chat_id,
        "title": derive_title(messages),
        "favorite": (favorite if favorite is not None else bool(existing.get("favorite"))),
        "created_at": created_at or existing.get("created_at") or now,
        "updated_at": now,
        "messages": [serialize_message(m) for m in messages],
    }
    write_chat(chat)
    return chat


def set_favorite(chat_id: str, on: bool) -> bool:
    chat = load_chat(chat_id)
    if chat is None:
        return False
    chat["favorite"] = bool(on)
    write_chat(chat)
    return True


def list_chats() -> list[dict[str, Any]]:
    """Chat summaries, newest first."""
    if not CHATS_DIR.exists():
        return []
    items: list[dict[str, Any]] = []
    for p in CHATS_DIR.glob("*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            items.append(
                {
                    "id": d.get("id") or p.stem,
                    "title": d.get("title") or "Untitled",
                    "favorite": bool(d.get("favorite")),
                    "created_at": d.get("created_at"),
                    "updated_at": d.get("updated_at"),
                }
            )
        except (OSError, json.JSONDecodeError):
            continue
    items.sort(key=lambda c: (c.get("updated_at") or "", c["id"]), reverse=True)
    return items


# --- device-level pointers (same semantics as the old UI) -------------


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, data: Any) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass


def load_current_chat_id() -> str | None:
    data = _read_json(CURRENT_CHAT_PATH, {})
    value = data.get("chat_id") if isinstance(data, dict) else None
    return str(value) if value else None


def save_current_chat_id(chat_id: str | None) -> None:
    if chat_id is None:
        with contextlib.suppress(OSError):
            CURRENT_CHAT_PATH.unlink(missing_ok=True)
        return
    _write_json(CURRENT_CHAT_PATH, {"chat_id": chat_id})


def load_pending() -> list[str]:
    data = _read_json(PENDING_PATH, [])
    return [str(x) for x in data] if isinstance(data, list) else []


def save_pending(names: list[str]) -> None:
    _write_json(PENDING_PATH, list(names))


def load_selected_model() -> str:
    return str(_read_json(SELECTED_MODEL_PATH, {}).get("model_filename") or "")


def save_selected_model(filename: str) -> None:
    _write_json(SELECTED_MODEL_PATH, {"model_filename": filename})
