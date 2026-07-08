"""Shared data models used across the pipeline.

All inter-module data passes through these types. Keeping them frozen
and validated catches the largest class of integration bugs at
module boundaries.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Document(BaseModel):
    """A single parsed source document.

    `pages` is one string per page in source order. Empty pages are
    preserved as empty strings so page numbers stay stable.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: Path = Field(..., description="Filesystem path the document was loaded from.")
    pages: tuple[str, ...] = Field(..., description="Text per page, in source order.")
    metadata: dict[str, str] = Field(
        default_factory=dict,
        description="Arbitrary metadata (title, author, etc.) extracted by the parser.",
    )

    @field_validator("pages")
    @classmethod
    def _at_least_one_page(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) == 0:
            raise ValueError("Document must have at least one page.")
        return value

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def full_text(self) -> str:
        """All page text concatenated with double newlines between pages."""
        return "\n\n".join(self.pages)


class Chunk(BaseModel):
    """A retrievable text unit produced by the chunker.

    Page index is the 0-based source page this chunk originated from.
    Used to attribute citations back to the source document.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str = Field(..., min_length=1)
    source: Path
    page_index: int = Field(..., ge=0)
    chunk_index: int = Field(..., ge=0, description="Position within the source document.")
