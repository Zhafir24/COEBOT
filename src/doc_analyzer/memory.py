"""Persistent user memory.

Small facts about the user (name, role, preferences, ongoing projects)
stored as JSON on the local disk. Facts are injected into the system
prompt of every answer mode so COEBOT "knows" the user better the more
it is used. Fully local — nothing leaves the machine — and fully
user-controlled: the UI exposes view/delete/clear.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_MAX_FACTS = 50
_MAX_FACT_LEN = 300


class UserMemory:
    """Load/store user facts in a JSON file, newest first."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> list[dict]:
        """Return all stored fact records (newest first)."""
        if not self._path.exists():
            return []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("Could not read memory file %s", self._path)
            return []
        if not isinstance(data, list):
            return []
        return [r for r in data if isinstance(r, dict) and r.get("fact")]

    def facts(self, limit: int = 15) -> list[str]:
        """Return up to ``limit`` fact strings for prompt injection."""
        return [str(r["fact"]) for r in self.load()[:limit]]

    def add(self, fact: str) -> bool:
        """Store a fact. Returns False for empty/duplicate/oversized input."""
        fact = " ".join(fact.split()).strip()
        if not fact or len(fact) > _MAX_FACT_LEN:
            return False
        records = self.load()
        if any(r["fact"].strip().lower() == fact.lower() for r in records):
            return False
        records.insert(
            0,
            {
                "fact": fact,
                "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
            },
        )
        self._write(records[:_MAX_FACTS])
        return True

    def remove(self, fact: str) -> bool:
        """Delete the record matching ``fact`` exactly. Returns success."""
        records = self.load()
        kept = [r for r in records if r["fact"] != fact]
        if len(kept) == len(records):
            return False
        self._write(kept)
        return True

    def clear(self) -> None:
        """Delete every stored fact."""
        self._write([])

    def _write(self, records: list[dict]) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(self._path.suffix + ".tmp")
            tmp.write_text(
                json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            tmp.replace(self._path)
        except OSError:
            logger.warning("Could not write memory file %s", self._path)
