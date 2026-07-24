"""Command-line entry point.

Currently a thin placeholder that prints the version. Full CLI lands in
Phase 3 once the chat orchestrator exists.
"""

from __future__ import annotations

import sys

from doc_analyzer import __version__


def main(argv: list[str] | None = None) -> int:
    """Entry point referenced by ``[project.scripts]`` in pyproject.toml."""
    args = sys.argv[1:] if argv is None else argv

    if args and args[0] in {"-v", "--version"}:
        print(f"doc_analyzer {__version__}")
        return 0

    print(f"doc_analyzer {__version__}")
    print("Start the COEBOT web UI with start_coebot.bat (or: uvicorn doc_analyzer.server:app)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
