"""Tests for the persistent user memory store."""

from __future__ import annotations

from pathlib import Path

from doc_analyzer.memory import _MAX_FACTS, UserMemory


def _mem(tmp_path: Path) -> UserMemory:
    return UserMemory(tmp_path / "memory.json")


class TestAdd:
    def test_add_and_load(self, tmp_path: Path) -> None:
        mem = _mem(tmp_path)
        assert mem.add("User prefers IEEE-style analysis")
        records = mem.load()
        assert len(records) == 1
        assert records[0]["fact"] == "User prefers IEEE-style analysis"
        assert "created_at" in records[0]

    def test_newest_first(self, tmp_path: Path) -> None:
        mem = _mem(tmp_path)
        mem.add("first fact")
        mem.add("second fact")
        assert mem.facts() == ["second fact", "first fact"]

    def test_duplicate_rejected_case_insensitive(self, tmp_path: Path) -> None:
        mem = _mem(tmp_path)
        assert mem.add("Works at PNM")
        assert not mem.add("works at pnm")
        assert len(mem.load()) == 1

    def test_empty_and_whitespace_rejected(self, tmp_path: Path) -> None:
        mem = _mem(tmp_path)
        assert not mem.add("")
        assert not mem.add("   \n\t ")
        assert mem.load() == []

    def test_oversized_rejected(self, tmp_path: Path) -> None:
        mem = _mem(tmp_path)
        assert not mem.add("x" * 500)

    def test_whitespace_normalized(self, tmp_path: Path) -> None:
        mem = _mem(tmp_path)
        mem.add("likes   \n  concise answers")
        assert mem.facts() == ["likes concise answers"]

    def test_cap_drops_oldest(self, tmp_path: Path) -> None:
        mem = _mem(tmp_path)
        for i in range(_MAX_FACTS + 5):
            mem.add(f"fact number {i}")
        records = mem.load()
        assert len(records) == _MAX_FACTS
        assert records[0]["fact"] == f"fact number {_MAX_FACTS + 4}"
        assert all(r["fact"] != "fact number 0" for r in records)


class TestRemoveAndClear:
    def test_remove_existing(self, tmp_path: Path) -> None:
        mem = _mem(tmp_path)
        mem.add("keep me")
        mem.add("delete me")
        assert mem.remove("delete me")
        assert mem.facts() == ["keep me"]

    def test_remove_missing_returns_false(self, tmp_path: Path) -> None:
        mem = _mem(tmp_path)
        mem.add("something")
        assert not mem.remove("not there")

    def test_clear(self, tmp_path: Path) -> None:
        mem = _mem(tmp_path)
        mem.add("a")
        mem.add("b")
        mem.clear()
        assert mem.load() == []


class TestRobustness:
    def test_missing_file_loads_empty(self, tmp_path: Path) -> None:
        assert _mem(tmp_path).load() == []

    def test_corrupt_file_loads_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "memory.json"
        path.write_text("{not valid json", encoding="utf-8")
        assert UserMemory(path).load() == []

    def test_facts_limit(self, tmp_path: Path) -> None:
        mem = _mem(tmp_path)
        for i in range(20):
            mem.add(f"fact {i}")
        assert len(mem.facts(limit=15)) == 15
