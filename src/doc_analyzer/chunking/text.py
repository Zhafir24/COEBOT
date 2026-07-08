"""Text chunking.

Splits a Document's text into overlapping fixed-size character windows.

Why characters and not tokens? Token boundaries depend on the tokenizer
which varies by LLM family. Character windows are predictable across
models. The default ``chunk_size=800`` corresponds to ~200 tokens for
English, which leaves comfortable headroom in any modern LLM's context.

The window is a simple sliding window with stride ``chunk_size -
chunk_overlap``. Simpler than recursive separator splitting and
predictable: every chunk is at most ``chunk_size`` characters, and
adjacent chunks share exactly ``chunk_overlap`` characters of context.
"""

from __future__ import annotations

from doc_analyzer.models import Chunk, Document


def chunk_document(
    document: Document,
    *,
    chunk_size: int,
    chunk_overlap: int,
) -> list[Chunk]:
    """Split ``document`` into a list of overlapping :class:`Chunk` objects.

    Args:
        document: The source document.
        chunk_size: Maximum characters per chunk. Must be > 0.
        chunk_overlap: Characters of overlap between adjacent chunks
            from the same page. Must be >= 0 and strictly less than
            ``chunk_size``.

    Returns:
        Chunks in source order. Empty pages contribute no chunks.

    Raises:
        ValueError: if ``chunk_size`` or ``chunk_overlap`` are invalid.
    """
    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be positive, got {chunk_size}")
    if chunk_overlap < 0:
        raise ValueError(f"chunk_overlap must be non-negative, got {chunk_overlap}")
    if chunk_overlap >= chunk_size:
        raise ValueError(
            f"chunk_overlap ({chunk_overlap}) must be smaller than chunk_size ({chunk_size})"
        )

    chunks: list[Chunk] = []
    counter = 0
    for page_index, page_text in enumerate(document.pages):
        for piece in _split_text(page_text, chunk_size, chunk_overlap):
            chunks.append(
                Chunk(
                    text=piece,
                    source=document.source,
                    page_index=page_index,
                    chunk_index=counter,
                )
            )
            counter += 1
    return chunks


def _split_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Sliding window over the source text with the given overlap."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    step = chunk_size - chunk_overlap  # > 0 by validation
    pieces: list[str] = []
    for start in range(0, len(text), step):
        end = min(start + chunk_size, len(text))
        piece = text[start:end]
        if piece.strip():
            pieces.append(piece)
        if end == len(text):
            break
    return pieces
