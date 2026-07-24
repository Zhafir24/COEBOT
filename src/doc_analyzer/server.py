"""COEBOT HTTP backend — Starlette ASGI app, no UI framework.

Replaces the Streamlit layer entirely. The frontend is a static
single-page app in ``doc_analyzer/webui``; this module exposes the
JSON API it talks to and serves its assets. All heavy lifting stays in
the existing engine modules (pipeline, llm client, memory, auth,
retrieval) — this file only wires HTTP to them.

Run:  uvicorn doc_analyzer.server:app --host 127.0.0.1 --port 80

Design notes:
- Zero dependencies beyond what the venv already has (starlette,
  uvicorn, python-multipart and itsdangerous arrive with chromadb).
- One in-process model at a time: generation is serialized with a
  lock, mirroring the single-user desktop deployment.
- "Private" (Nobody) mode is enforced SERVER-side per request: when a
  send is private, nothing is persisted and memory is neither read
  nor written — same guarantees the Streamlit UI had.
- Sessions: username in an itsdangerous-signed cookie. The secret is
  generated once into data/session_secret.txt so sessions survive
  restarts without any config.
"""

from __future__ import annotations

import contextlib
import logging
import re
import secrets
import threading
from pathlib import Path

from itsdangerous import BadSignature, URLSafeSerializer
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from doc_analyzer import store_chats as cs
from doc_analyzer.auth.store import UserStore, UserStoreError
from doc_analyzer.config import get_settings
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

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_WEBUI_DIR = Path(__file__).resolve().parent / "webui"
_FONTS_DIR = Path(__file__).resolve().parent / "webui" / "fonts"
_LOGO_PATH = _PROJECT_ROOT / "static" / "pnm-logo.svg"
_USERS_PATH = _PROJECT_ROOT / "data" / "users.json"
_SECRET_PATH = _PROJECT_ROOT / "data" / "session_secret.txt"

_REMEMBER_CMD_RE = re.compile(
    r"^\s*(?:remember|ingat|ingatlah)\s*[:,]?\s+(.+)$", re.IGNORECASE | re.DOTALL
)
_PERSONAL_SIGNAL_RE = re.compile(
    r"\b(nama saya|panggil saya|saya suka|saya tidak suka|saya lebih suka|"
    r"saya bekerja|saya seorang|pekerjaan saya|proyek saya|aku suka|"
    r"my name|call me|i am|i'm|i like|i love|i hate|i prefer|i work|"
    r"i'm working on|my job|my project|my role)\b",
    re.IGNORECASE,
)
_SUPPORTED_EXTS = (".pdf", ".docx", ".xlsx")


# --- singletons (replace st.cache_resource) ----------------------------

_settings = get_settings()
_users = UserStore(_USERS_PATH)
_lock = threading.Lock()  # serialize generation + ingestion
_llm_clients: dict[str, LlmClient] = {}
_embedder: Embedder | None = None
_vector_store: VectorStore | None = None
_memory: UserMemory | None = None

# Background ingestion tracking. Each pending upload gets an Event that
# is set() once its ingestion thread finishes. The retrieval-fallback
# path in _run_pipeline waits on these events so a big document uploaded
# right before a question doesn't return empty search results.
_ingest_events: dict[str, threading.Event] = {}
_ingest_errors: dict[str, str] = {}
_ingest_state_lock = threading.Lock()  # guards the dicts above only


def _get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        _embedder = Embedder(_settings.embedding_model)
    return _embedder


def _get_store() -> VectorStore:
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore(
            persist_dir=_settings.chroma_persist_dir,
            collection_name=_settings.chroma_collection,
        )
    return _vector_store


def _get_memory() -> UserMemory:
    global _memory
    if _memory is None:
        _memory = UserMemory(_PROJECT_ROOT / "data" / "memory.json")
    return _memory


def _resolve_model_path(filename: str) -> Path:
    d = _settings.models_dir
    if filename:
        p = d / Path(filename).name  # basename only — no traversal
        if p.exists():
            return p
        raise FileNotFoundError(f"Model file not found: {filename}")
    ggufs = sorted(d.glob("*.gguf")) if d.exists() else []
    if not ggufs:
        raise FileNotFoundError(
            "No .gguf file found in the models directory. "
            "Download a model and place it in models/."
        )
    return ggufs[0]


def _get_llm(filename: str) -> LlmClient:
    key = filename or "__auto__"
    if key not in _llm_clients:
        _llm_clients[key] = LlmClient(
            model_path=_resolve_model_path(filename),
            n_ctx=_settings.model_n_ctx,
            n_threads=_settings.model_n_threads or None,
            n_gpu_layers=_settings.model_n_gpu_layers,
            strip_think_tags=_settings.strip_think_tags,
            max_tokens=_settings.model_max_tokens,
            kv_cache_dir=_settings.kv_cache_dir if _settings.kv_cache_enabled else None,
            kv_cache_bytes=_settings.kv_cache_gb * 1024**3,
        )
    return _llm_clients[key]


# --- sessions ----------------------------------------------------------


def _secret() -> str:
    if _SECRET_PATH.exists():
        return _SECRET_PATH.read_text(encoding="utf-8").strip()
    _SECRET_PATH.parent.mkdir(parents=True, exist_ok=True)
    s = secrets.token_hex(32)
    _SECRET_PATH.write_text(s, encoding="utf-8")
    return s


_signer = URLSafeSerializer(_secret(), salt="coebot-session")
_COOKIE = "coebot_session"


def _session_user(request: Request) -> str | None:
    raw = request.cookies.get(_COOKIE)
    if not raw:
        return None
    try:
        data = _signer.loads(raw)
    except BadSignature:
        return None
    user = data.get("u")
    return user if user and _users.get(user) is not None else None


def _login_response(payload: dict, username: str, *, remember: bool = True) -> JSONResponse:
    resp = JSONResponse(payload)
    resp.set_cookie(
        _COOKIE,
        _signer.dumps({"u": username}),
        httponly=True,
        samesite="lax",
        # "Remember me" unchecked → session cookie (cleared on browser close).
        max_age=60 * 60 * 24 * 30 if remember else None,
    )
    return resp


def _require_user(request: Request) -> str | None:
    return _session_user(request)


def _unauth() -> JSONResponse:
    return JSONResponse({"error": "not signed in"}, status_code=401)


# --- API endpoints ------------------------------------------------------


async def api_register(request: Request) -> JSONResponse:
    body = await request.json()
    username = str(body.get("username") or "").strip()
    password = str(body.get("password") or "")
    try:
        _users.register(username, password)
    except UserStoreError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return _login_response({"user": username}, username)


async def api_login(request: Request) -> JSONResponse:
    body = await request.json()
    username = str(body.get("username") or "").strip()
    password = str(body.get("password") or "")
    if not _users.authenticate(username, password):
        return JSONResponse({"error": "Invalid username or password"}, status_code=401)
    return _login_response(
        {"user": username}, username, remember=bool(body.get("remember", True))
    )


async def api_logout(request: Request) -> JSONResponse:
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(_COOKIE)
    return resp


def _models_payload() -> dict:
    d = _settings.models_dir
    models = sorted(p.name for p in d.glob("*.gguf")) if d.exists() else []
    selected = cs.load_selected_model()
    if selected not in models:
        selected = models[0] if models else ""
    return {"models": models, "selected": selected}


async def api_bootstrap(request: Request) -> JSONResponse:
    user = _require_user(request)
    if not user:
        return JSONResponse(
            {"user": None, "has_users": _users.has_users()}, status_code=200
        )
    current_id = cs.load_current_chat_id()
    current = cs.load_chat(current_id) if current_id else None
    return JSONResponse(
        {
            "user": user,
            "has_users": True,
            "chats": cs.list_chats(),
            "current_chat": current,
            "pending": cs.load_pending(),
            "memory": _get_memory().facts(),
            **_models_payload(),
        }
    )


async def api_chats(request: Request) -> JSONResponse:
    if not _require_user(request):
        return _unauth()
    return JSONResponse({"chats": cs.list_chats()})


async def api_chat_get(request: Request) -> JSONResponse:
    if not _require_user(request):
        return _unauth()
    chat = cs.load_chat(request.path_params["chat_id"])
    if chat is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    cs.save_current_chat_id(chat["id"])
    return JSONResponse(chat)


async def api_chat_delete(request: Request) -> JSONResponse:
    if not _require_user(request):
        return _unauth()
    chat_id = request.path_params["chat_id"]
    ok = cs.delete_chat(chat_id)
    if cs.load_current_chat_id() == chat_id:
        cs.save_current_chat_id(None)
    return JSONResponse({"ok": ok})


async def api_chat_favorite(request: Request) -> JSONResponse:
    if not _require_user(request):
        return _unauth()
    body = await request.json()
    ok = cs.set_favorite(request.path_params["chat_id"], bool(body.get("on")))
    return JSONResponse({"ok": ok})


async def api_select_model(request: Request) -> JSONResponse:
    if not _require_user(request):
        return _unauth()
    body = await request.json()
    name = Path(str(body.get("model") or "")).name
    models = _models_payload()["models"]
    if name and name not in models:
        return JSONResponse({"error": "unknown model"}, status_code=400)
    cs.save_selected_model(name)
    return JSONResponse({"ok": True, "selected": name})


async def api_pending(request: Request) -> JSONResponse:
    if not _require_user(request):
        return _unauth()
    body = await request.json()
    names = [str(n) for n in (body.get("names") or [])]
    if not body.get("private"):
        cs.save_pending(names)
    return JSONResponse({"ok": True})


def _background_ingest(save_path: Path, name: str) -> None:
    """Ingest a saved file on a worker thread and signal completion.

    Runs under _lock so it serializes with generation. Any failure
    removes the file so a retry is possible and records the error for
    the retrieval path to surface.
    """
    try:
        with _lock:
            ingest_document(
                save_path,
                embedder=_get_embedder(),
                store=_get_store(),
                settings=_settings,
            )
        logger.info("Background ingestion complete: %s", name)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Background ingestion failed for %s", name)
        save_path.unlink(missing_ok=True)
        with _ingest_state_lock:
            _ingest_errors[name] = str(exc)
    finally:
        with _ingest_state_lock:
            ev = _ingest_events.get(name)
        if ev is not None:
            ev.set()


def _wait_for_ingestion(names: list[str], *, timeout: float = 300.0) -> None:
    """Block until every listed doc has finished background ingestion.

    Called from the retrieval-fallback path in _run_pipeline so a big
    document uploaded seconds ago doesn't return empty search results.
    """
    with _ingest_state_lock:
        events = [_ingest_events.get(n) for n in names]
    for ev in events:
        if ev is not None and not ev.is_set():
            ev.wait(timeout=timeout)


async def api_upload(request: Request) -> JSONResponse:
    if not _require_user(request):
        return _unauth()
    form = await request.form()
    uf = form.get("file")
    if uf is None:
        return JSONResponse({"error": "no file"}, status_code=400)
    name = Path(uf.filename or "upload").name
    if Path(name).suffix.lower() not in _SUPPORTED_EXTS:
        return JSONResponse(
            {"error": "Only PDF, DOCX and XLSX files are supported"}, status_code=400
        )
    cs.DOCS_DIR.mkdir(parents=True, exist_ok=True)
    save_path = cs.DOCS_DIR / name
    data = await uf.read()
    if save_path.exists():
        return JSONResponse({"name": name, "existing": True})

    # Save the bytes synchronously so the file is on disk and deep-read
    # can use it immediately if the user asks a question right away.
    save_path.write_bytes(data)

    # Kick ingestion off to a background thread so the UI returns to the
    # user instantly (the CPU-bound embedding step happens while they
    # type their question). Retrieval-mode questions later on will wait
    # for this to finish via _wait_for_ingestion().
    with _ingest_state_lock:
        _ingest_events[name] = threading.Event()
        _ingest_errors.pop(name, None)
    threading.Thread(
        target=_background_ingest, args=(save_path, name), daemon=True
    ).start()
    return JSONResponse({"name": name, "status": "indexing"})


def _run_pipeline(
    question: str, messages: list[dict], private: bool, model: str
) -> tuple[str, list]:
    """The exact decision tree the Streamlit UI used."""
    chat_doc_names: list[str] = []
    for m in messages:
        for name in m.get("attachments") or []:
            if name not in chat_doc_names:
                chat_doc_names.append(name)

    llm = _get_llm(model)
    mem_facts = [] if private else _get_memory().facts()

    remember_match = _REMEMBER_CMD_RE.match(question)
    if remember_match and not chat_doc_names:
        if private:
            answer = Answer(
                text=(
                    "○ Mode Private — tidak ada yang disimpan. / "
                    "Private mode — nothing is saved or remembered "
                    "in a temporary session."
                ),
                sources=(),
            )
        elif _get_memory().add(remember_match.group(1).strip()):
            answer = Answer(
                text=f"✅ Tersimpan / Saved to memory: *{remember_match.group(1).strip()}*",
                sources=(),
            )
        else:
            answer = Answer(
                text="ℹ️ Sudah tersimpan sebelumnya / Already in memory.",
                sources=(),
            )
        return answer.text, list(answer.sources)

    if chat_doc_names:
        existing_paths = [
            p for p in (cs.DOCS_DIR / n for n in chat_doc_names) if p.exists()
        ]
        answer = None
        if existing_paths:
            answer = answer_full_documents(
                question,
                doc_paths=existing_paths,
                llm=llm,
                settings=_settings,
                memory_facts=mem_facts,
            )
        if answer is None:
            # Deep-read didn't fit — we need retrieval. If any attached
            # doc was uploaded seconds ago and its background ingestion
            # is still running, wait for it now so search hits real
            # chunks instead of an empty index.
            _wait_for_ingestion(chat_doc_names)
            chat_doc_paths = [str(cs.DOCS_DIR / n) for n in chat_doc_names]
            answer = answer_question(
                question,
                embedder=_get_embedder(),
                store=_get_store(),
                llm=llm,
                settings=_settings,
                source_paths=chat_doc_paths,
                memory_facts=mem_facts,
            )
            answer = Answer(
                text=answer.text
                + "\n\n*(Documents were too large to read in full — this "
                "answer is based on the most relevant retrieved excerpts.)*",
                sources=answer.sources,
            )
        return answer.text, list(answer.sources)

    history = [
        {"role": m["role"], "content": m["content"]}
        for m in messages[-10:]
        if m.get("role") in ("user", "assistant")
        and not str(m.get("content", "")).startswith("⚠️")
    ]
    answer = converse(history, llm=llm, memory_facts=mem_facts)
    return answer.text, list(answer.sources)


def _send_sync(body: dict) -> dict:
    question = str(body.get("question") or "").strip()
    private = bool(body.get("private"))
    model = Path(str(body.get("model") or "")).name
    attachments = [str(n) for n in (body.get("attachments") or [])]
    chat_id = body.get("chat_id") or cs.new_chat_id()

    stored = None if private else cs.load_chat(chat_id)
    messages: list[dict] = list((stored or {}).get("messages") or [])
    # In private mode the client supplies the in-memory transcript.
    if private:
        messages = [m for m in (body.get("messages") or []) if isinstance(m, dict)]

    user_msg = {
        "role": "user",
        "content": question,
        "ts": cs.now_iso(),
        "attachments": attachments,
    }
    messages.append(user_msg)

    try:
        with _lock:
            text, sources = _run_pipeline(question, messages, private, model)
    except FileNotFoundError as exc:
        text, sources = f"⚠️ **No model available.** {exc}", []
    except Exception as exc:  # noqa: BLE001 — surfaced to the UI
        logger.exception("Chat pipeline failed")
        text, sources = (
            f"⚠️ **Something went wrong while generating the answer.**\n\n`{exc}`",
            [],
        )

    assistant_msg = {
        "role": "assistant",
        "content": text,
        "ts": cs.now_iso(),
        "sources": sources,
    }
    messages.append(assistant_msg)

    title = cs.derive_title(messages)
    if not private:
        chat = cs.persist_messages(chat_id, messages)
        cs.save_current_chat_id(chat_id)
        cs.save_pending([])
        title = chat["title"]

        remember_match = _REMEMBER_CMD_RE.match(question)
        if (
            remember_match is None
            and not text.startswith("⚠️")
            and _PERSONAL_SIGNAL_RE.search(question)
        ):
            try:
                fact = extract_memory_fact(question, llm=_get_llm(model))
                if fact:
                    _get_memory().add(fact)
            except Exception:  # noqa: BLE001 — memory is best-effort
                logger.debug("Memory extraction failed", exc_info=True)

    return {
        "chat_id": chat_id,
        "title": title,
        "user_message": cs.serialize_message(user_msg),
        "assistant_message": cs.serialize_message(assistant_msg),
        "private": private,
    }


async def api_send(request: Request) -> JSONResponse:
    if not _require_user(request):
        return _unauth()
    body = await request.json()
    if not str(body.get("question") or "").strip():
        return JSONResponse({"error": "empty question"}, status_code=400)
    import anyio

    result = await anyio.to_thread.run_sync(lambda: _send_sync(body))
    return JSONResponse(result)


async def api_memory(request: Request) -> JSONResponse:
    if not _require_user(request):
        return _unauth()
    mem = _get_memory()
    if request.method == "GET":
        return JSONResponse({"facts": mem.facts()})
    body = await request.json()
    if body.get("clear"):
        mem.clear()
    elif body.get("delete") is not None:
        mem.remove(str(body["delete"]))
    elif body.get("add"):
        mem.add(str(body["add"]).strip())
    return JSONResponse({"facts": mem.facts()})


async def index(request: Request) -> FileResponse:
    # no-cache: the browser must always revalidate the shell so UI updates
    # land on a plain reload (assets are cache-busted via ?v= versions).
    return FileResponse(
        _WEBUI_DIR / "index.html",
        headers={"Cache-Control": "no-cache"},
    )


async def logo(request: Request) -> FileResponse:
    return FileResponse(_LOGO_PATH, media_type="image/svg+xml")


routes = [
    Route("/", index),
    Route("/logo.svg", logo),
    Route("/api/register", api_register, methods=["POST"]),
    Route("/api/login", api_login, methods=["POST"]),
    Route("/api/logout", api_logout, methods=["POST"]),
    Route("/api/bootstrap", api_bootstrap),
    Route("/api/chats", api_chats),
    Route("/api/chats/{chat_id}", api_chat_get),
    Route("/api/chats/{chat_id}", api_chat_delete, methods=["DELETE"]),
    Route("/api/chats/{chat_id}/favorite", api_chat_favorite, methods=["POST"]),
    Route("/api/model", api_select_model, methods=["POST"]),
    Route("/api/pending", api_pending, methods=["POST"]),
    Route("/api/upload", api_upload, methods=["POST"]),
    Route("/api/send", api_send, methods=["POST"]),
    Route("/api/memory", api_memory, methods=["GET", "POST"]),
    Mount("/assets", StaticFiles(directory=str(_WEBUI_DIR)), name="assets"),
    Mount("/fonts", StaticFiles(directory=str(_FONTS_DIR)), name="fonts"),
]

def _prewarm() -> None:
    """Load the embedder + vector store on server boot so the FIRST
    document upload doesn't pay the ~2–3s SentenceTransformer cold-start
    cost. Runs on a background thread so uvicorn's startup isn't blocked.
    """
    def _warm() -> None:
        try:
            logger.info("Pre-warming embedder + vector store...")
            emb = _get_embedder()
            emb.encode(["warmup"])  # triggers _ensure_loaded()
            _get_store()             # opens the ChromaDB connection
            logger.info("Pre-warm complete.")
        except Exception:  # noqa: BLE001 — startup optimization only
            logger.warning("Pre-warm failed; first upload will be slower", exc_info=True)

    threading.Thread(target=_warm, daemon=True).start()


@contextlib.asynccontextmanager
async def _lifespan(_app):
    _prewarm()
    yield


app = Starlette(routes=routes, lifespan=_lifespan)
