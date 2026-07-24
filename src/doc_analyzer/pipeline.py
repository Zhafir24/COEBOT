"""RAG pipeline orchestrator.

Two top-level functions:

- :func:`ingest_pdf` — parse a PDF, chunk it, embed the chunks, write to
  the vector store.
- :func:`answer_question` — embed the question, retrieve top-k chunks,
  build a grounded prompt, ask the LLM, return the answer with citations.

Both are plain functions. There are no agent loops, no tool-use,
no autonomous decisions. Each call is one pass through the pipeline.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from doc_analyzer.chunking.text import chunk_document
from doc_analyzer.config import Settings
from doc_analyzer.embeddings.encoder import Embedder
from doc_analyzer.llm.client import ChatMessage, LlmClient
from doc_analyzer.models import Document
from doc_analyzer.parsers.docx import parse_docx
from doc_analyzer.parsers.pdf import parse_pdf
from doc_analyzer.parsers.xlsx import parse_xlsx
from doc_analyzer.retrieval.store import RetrievedChunk, VectorStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class IngestResult:
    """Summary of one ingestion run."""

    source: Path
    page_count: int
    chunk_count: int


@dataclass(frozen=True, slots=True)
class Answer:
    """The pipeline's response to a question."""

    text: str
    sources: tuple[RetrievedChunk, ...]


# Shared response-formatting contract. Appended to every system prompt so
# answers read like a professional assistant (ChatGPT/Claude level) instead
# of dense fragment dumps. The frontend renders full Markdown — headings,
# tables, nested lists — so everything requested here displays properly.
_STYLE_GUIDE = (
    "\n\n"
    "=== RESPONSE FORMAT (strict — write in Markdown) ===\n"
    "\n"
    "OPENING\n"
    "- Answer the question in the FIRST sentence — no preamble, no "
    "'Certainly!', 'Of course!', 'Baik,', 'Berikut adalah penjelasan…'.\n"
    "- Never restate the question. Never announce the structure ('Saya "
    "akan menjelaskan dalam tiga bagian…').\n"
    "\n"
    "LENGTH — match the response to the depth the user asked for\n"
    "- Casual/simple questions get short answers (a few sentences).\n"
    "- Requests containing 'research', 'kajian', 'analisis mendalam', "
    "'analisis komprehensif', 'buatkan makalah', 'bahas secara "
    "menyeluruh', 'jelaskan lengkap', 'review lengkap', 'ringkasan "
    "lengkap', 'summary lengkap', or that clearly want depth: write a "
    "long, thorough, multi-section response. Cover every relevant angle, "
    "give examples, discuss trade-offs and edge cases. Do NOT self-"
    "shorten. Use the full output budget the topic warrants.\n"
    "- When analyzing an attached document: be thorough. Cover the full "
    "scope, cite pages, and only stop when the analysis is complete.\n"
    "- Never truncate a long answer to look tidy. Better to be long and "
    "complete than short and superficial.\n"
    "\n"
    "STRUCTURE\n"
    "- For short answers: plain prose, no headings, no bullets.\n"
    "- For medium answers: a short intro sentence + one bullet list with "
    "**bold labels**.\n"
    "- For long/research answers: use '### ' headings for each major "
    "topic, with several paragraphs and/or lists inside each section. "
    "Multiple headings are welcome when the content genuinely needs "
    "them — do not artificially limit heading count.\n"
    "- Headings MUST use '### ' (three hashes). NEVER use '# ' or '## '. "
    "Never write a bold line as a fake heading.\n"
    "- Do NOT open a section with a heading that only restates the "
    "question ('### Perbandingan' when the user asked to compare).\n"
    "\n"
    "LISTS\n"
    "- All items in one list must be parallel: all start with a noun, OR "
    "all start with a verb, OR all follow the '**Label:** desc' pattern. "
    "Do not mix styles inside one list.\n"
    "- Numbered lists ONLY for ordered steps or ranked items. Everything "
    "else uses bullets ('- ').\n"
    "- Keep each bullet on a single logical point in 1–2 sentences. Use "
    "nested bullets (indent 2 spaces) sparingly, only when a bullet has "
    "genuine sub-parts.\n"
    "- Never write a list of one item.\n"
    "\n"
    "TABLES\n"
    "- Use a Markdown table whenever you compare 2+ items across 2+ "
    "attributes, or present rows of parallel data. Do NOT write these as "
    "bullets like '- Item A: X, Y, Z / - Item B: X, Y, Z'.\n"
    "- Keep tables narrow (≤4 columns) and cells short (≤8 words). If "
    "cells need more, use prose after the table.\n"
    "\n"
    "EMPHASIS\n"
    "- Bold sparingly. Only for: term being defined, critical numbers, "
    "action words in steps, the '**Label:**' pattern in labeled bullets.\n"
    "- Never bold entire sentences. Never bold for decoration.\n"
    "- Use `code font` for filenames, commands, exact values, identifiers.\n"
    "- Do not use emoji unless the user's own message contains them.\n"
    "\n"
    "PARAGRAPHS AND WHITESPACE\n"
    "- 3–5 sentences per paragraph is a good rhythm. Break very long "
    "thoughts, but do not artificially chop natural prose into fragments.\n"
    "- Leave a blank line between every heading, paragraph, list, and "
    "table. No walls of text.\n"
    "\n"
    "CLOSING\n"
    "- A concluding synthesis IS appropriate for long/research answers — "
    "add a '### Kesimpulan' (or '### Conclusion') section that draws "
    "together the analysis in 1–2 short paragraphs. Skip it for short or "
    "medium answers where nothing needs summarizing.\n"
    "- No 'Semoga membantu!' / 'Hope this helps!' / 'Let me know if you "
    "have any questions.'\n"
    "\n"
    "LANGUAGE\n"
    "- Match the user's language exactly (Indonesian → Indonesian, "
    "English → English). Headings and labels in the same language.\n"
    "\n"
    "=== END RESPONSE FORMAT ==="
)

_SYSTEM_PROMPT = (
    "You are a careful document analyst. Ground your answer in the context "
    "excerpts provided below — do not invent facts that are not in them. "
    "Cite source page numbers in square brackets like [p.3] for every fact "
    "you use. Respond in the same language as the user's question.\n"
    "- For broad requests (summarize, analyze, compare, review): work with "
    "the excerpts you have. Give the most thorough analysis the excerpts "
    "support, organized clearly, and note that it is based on retrieved "
    "portions of the document(s) rather than the full text.\n"
    "- Only when the user asks for a SPECIFIC fact that is absent from the "
    "excerpts, say the provided documents do not contain that information "
    "(in the user's language). Never refuse a broad request just because "
    "the excerpts are partial." + _STYLE_GUIDE
)

_CHAT_SYSTEM_PROMPT = (
    "You are COEBOT, a helpful, professional assistant. Respond in the same "
    "language the user writes in (Indonesian or English). Be concise, clear, "
    "and friendly. If the user wants you to analyze a document, remind them "
    "they can attach one with the paperclip button." + _STYLE_GUIDE
)

_FULL_DOC_SYSTEM_PROMPT = (
    "You are a careful document analyst. The user's document(s) are provided "
    "IN FULL below, with page markers like [p.3]. Ground every claim in the "
    "documents and cite pages in square brackets like [p.3] — include the "
    "document name when more than one document is provided. Respond in the "
    "same language as the user's question. Be thorough and well-organized."
    + _STYLE_GUIDE
)


def _with_memory(system_prompt: str, memory_facts: Sequence[str] | None) -> str:
    """Append the user's stored memory facts to a system prompt.

    Used only for plain conversation. Document modes place memory late
    in the USER prompt instead (see :func:`_memory_block`): the KV cache
    reuses prompts by token prefix, so anything that changes over time —
    and memory grows with use — must sit AFTER the expensive-to-process
    document text, not before it in the system message.
    """
    if not memory_facts:
        return system_prompt
    lines = "\n".join(f"- {fact}" for fact in memory_facts)
    return (
        f"{system_prompt}\n\n"
        f"Known facts about the user (apply them when relevant):\n{lines}"
    )


def _memory_block(memory_facts: Sequence[str] | None) -> str:
    """Render memory facts as a prompt section placed after document text."""
    if not memory_facts:
        return ""
    lines = "\n".join(f"- {fact}" for fact in memory_facts)
    return f"KNOWN FACTS ABOUT THE USER (apply when relevant):\n{lines}\n\n"


_SUPPORTED_SUFFIXES = (".pdf", ".docx", ".xlsx")


def _parse_by_extension(path: Path, *, password: str | None) -> Document:
    """Dispatch to the right parser based on the file's suffix."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return parse_pdf(path, password=password)
    if suffix == ".docx":
        return parse_docx(path)
    if suffix == ".xlsx":
        return parse_xlsx(path)
    raise ValueError(
        f"Unsupported file type {suffix!r}. Supported: {', '.join(_SUPPORTED_SUFFIXES)}"
    )


_PARSE_CACHE_DIR = (
    Path(__file__).resolve().parent.parent.parent / "data" / "cache" / "parsed"
)


def _parse_cached(path: Path) -> Document:
    """Parse a document with a persistent on-disk cache.

    Keyed by (absolute path, mtime, size), so editing or replacing the
    file naturally invalidates its cache entry. Deep-read mode calls
    this on every question; without the cache each question re-parses
    the PDF/DOCX from scratch.
    """
    import hashlib
    import json

    try:
        stat = path.stat()
        key = hashlib.sha1(
            f"{path.resolve()}|{stat.st_mtime_ns}|{stat.st_size}".encode()
        ).hexdigest()
        cache_file = _PARSE_CACHE_DIR / f"{key}.json"
        if cache_file.exists():
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            return Document(
                source=Path(data["source"]),
                pages=tuple(data["pages"]),
                metadata=dict(data.get("metadata", {})),
            )
    except Exception:  # noqa: BLE001 — cache read is best-effort
        logger.warning("Parse-cache read failed for %s", path, exc_info=True)

    document = _parse_by_extension(path, password=None)

    try:
        _PARSE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "source": str(document.source),
            "pages": list(document.pages),
            "metadata": document.metadata,
        }
        cache_file.write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:  # noqa: BLE001 — cache write is best-effort
        logger.warning("Parse-cache write failed for %s", path, exc_info=True)
    return document


def ingest_document(
    file_path: Path | str,
    *,
    embedder: Embedder,
    store: VectorStore,
    settings: Settings,
    password: str | None = None,
) -> IngestResult:
    """Read, chunk, embed, and persist one document.

    Supports PDF (.pdf), Word (.docx), and Excel (.xlsx).
    """
    file_path = Path(file_path)
    logger.info("Ingesting %s", file_path)

    document = _parse_by_extension(file_path, password=password)
    chunks = chunk_document(
        document,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )

    if chunks:
        embeddings = embedder.encode([c.text for c in chunks])
        store.add(chunks, embeddings)

    return IngestResult(
        source=file_path,
        page_count=document.page_count,
        chunk_count=len(chunks),
    )


# Backward-compatible alias for older code/tests calling ``ingest_pdf``.
ingest_pdf = ingest_document


def answer_question(
    question: str,
    *,
    embedder: Embedder,
    store: VectorStore,
    llm: LlmClient,
    settings: Settings,
    source_paths: Sequence[str] | None = None,
    memory_facts: Sequence[str] | None = None,
) -> Answer:
    """Answer ``question`` using retrieval-augmented generation.

    Args:
        source_paths: If given, retrieval is scoped to documents whose
            stored source path is in this list (the documents attached
            to the current conversation). ``None`` searches all
            indexed documents.
        memory_facts: Stored user-memory facts to expose to the model.

    Returns an :class:`Answer` with the model's text and the chunks that
    were used as context. Empty store → "no documents indexed" answer
    without an LLM call.
    """
    question = question.strip()
    if not question:
        return Answer(
            text="Please enter a question.",
            sources=(),
        )

    if store.count == 0:
        return Answer(
            text="No documents have been indexed yet. Upload a PDF first.",
            sources=(),
        )

    query_embedding = embedder.encode([question])[0]
    if source_paths and len(source_paths) > 1:
        # Multiple attached documents: retrieve per-document so every
        # document is represented. A single pooled query lets whichever
        # document is semantically closest to the phrasing claim all
        # top-k slots, which makes comparison tasks impossible.
        per_doc_k = max(2, settings.retrieval_top_k // len(source_paths))
        hits = []
        for path in source_paths:
            hits.extend(
                store.query(query_embedding, top_k=per_doc_k, source_paths=[path])
            )
    else:
        hits = store.query(
            query_embedding,
            top_k=settings.retrieval_top_k,
            source_paths=source_paths,
        )

    if not hits:
        return Answer(
            text="The provided documents do not contain enough information to answer this question.",
            sources=(),
        )

    prompt = _build_prompt(question, hits, memory_facts=memory_facts)
    messages: list[ChatMessage] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    response_text = llm.chat(messages)
    return Answer(text=response_text, sources=tuple(hits))


def answer_full_documents(
    question: str,
    *,
    doc_paths: Sequence[Path],
    llm: LlmClient,
    settings: Settings,
    memory_facts: Sequence[str] | None = None,
) -> Answer | None:
    """Answer by reading the ENTIRE attached document(s) into context.

    Deep-read mode: instead of retrieving excerpts, the full text of
    every document (with page markers) is placed in the prompt, letting
    the model perform whole-document analysis and comparison.

    Returns:
        An :class:`Answer` (with empty ``sources`` — citations are
        inline as ``[p.N]``), or ``None`` when the documents do not fit
        the context budget, signaling the caller to fall back to
        retrieval-based answering.
    """
    question = question.strip()
    if not question:
        return Answer(text="Please enter a question.", sources=())

    blocks: list[str] = []
    for path in doc_paths:
        document = _parse_cached(Path(path))
        pages = [
            f"[p.{i + 1}]\n{text.strip()}"
            for i, text in enumerate(document.pages)
            if text.strip()
        ]
        blocks.append(
            f"===== DOCUMENT: {Path(path).name} =====\n" + "\n\n".join(pages)
        )
    # Memory facts and the question go AFTER the document text: the KV
    # cache matches prompts by token prefix, so the huge document block
    # stays reusable across questions and across memory growth.
    prompt = (
        "DOCUMENTS:\n"
        + "\n\n".join(blocks)
        + f"\n\n{_memory_block(memory_facts)}QUESTION: {question}\n\nANSWER:"
    )

    # Budget check with the model's real tokenizer: the prompt must fit
    # alongside the system prompt / chat template (~overhead) and the
    # response budget inside the context window.
    overhead = 400
    budget = settings.model_n_ctx - settings.model_max_tokens - overhead
    if budget <= 0 or llm.count_tokens(prompt) > budget:
        logger.info("Deep-read skipped: documents exceed context budget")
        return None

    messages: list[ChatMessage] = [
        {"role": "system", "content": _FULL_DOC_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    return Answer(text=llm.chat(messages), sources=())


def converse(
    history: Sequence[ChatMessage],
    *,
    llm: LlmClient,
    memory_facts: Sequence[str] | None = None,
) -> Answer:
    """Plain conversational chat — no retrieval, no citations.

    Used when the current conversation has no attached documents, so
    COEBOT behaves like a normal chatbot instead of forcing every
    message through document retrieval.

    Args:
        history: Conversation turns (role/content), oldest first,
            ending with the user's newest message.
        memory_facts: Stored user-memory facts to expose to the model.
    """
    if not history:
        return Answer(text="Please enter a message.", sources=())
    messages: list[ChatMessage] = [
        {"role": "system", "content": _with_memory(_CHAT_SYSTEM_PROMPT, memory_facts)},
        *history,
    ]
    response_text = llm.chat(messages, temperature=0.6)
    return Answer(text=response_text, sources=())


_EXTRACT_SYSTEM_PROMPT = (
    "You extract long-term memory facts about the user. From the user's "
    "message, extract at most ONE short fact worth remembering across "
    "conversations (their name, role, employer, preferences, or ongoing "
    "projects). Write it as a third-person statement in the user's "
    "language, under 20 words. If there is nothing worth remembering, "
    "reply exactly: NONE"
)


def extract_memory_fact(user_message: str, *, llm: LlmClient) -> str | None:
    """Distill one memorable fact from a user message, or None.

    Cheap single-purpose LLM call (small prompt, tiny output budget).
    Callers should gate invocation with a heuristic so this does not
    run on every message.
    """
    text = user_message.strip()
    if not text:
        return None
    messages: list[ChatMessage] = [
        {"role": "system", "content": _EXTRACT_SYSTEM_PROMPT},
        {"role": "user", "content": text},
    ]
    result = llm.chat(messages, temperature=0.1, num_predict=60).strip()
    if not result or result.upper().startswith("NONE"):
        return None
    return result


def _build_prompt(
    question: str,
    hits: list[RetrievedChunk],
    *,
    memory_facts: Sequence[str] | None = None,
) -> str:
    """Assemble the user-side prompt with grounded context."""
    context_blocks: list[str] = []
    for i, hit in enumerate(hits, start=1):
        # Page numbers are 1-indexed in the prompt to match how users
        # read documents, even though page_index is 0-based internally.
        context_blocks.append(
            f"[Excerpt {i} | p.{hit.page_index + 1} of {hit.source.name}]\n{hit.text}"
        )
    context = "\n\n".join(context_blocks)
    return (
        f"CONTEXT:\n{context}\n\n"
        f"{_memory_block(memory_facts)}QUESTION: {question}\n\nANSWER:"
    )
