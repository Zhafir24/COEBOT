# Contributing

Thanks for your interest in improving `doc_analyzer`. This project takes correctness seriously — read this guide before opening a PR.

## Development setup

Follow the install steps in [README.md](README.md), then verify your environment:

```bash
pytest               # all tests should pass
ruff check src tests # no lint errors
mypy src             # no type errors
```

## Quality standards

Every PR must:

1. **Pass all CI checks.** No exceptions, no `# type: ignore` without a comment explaining why.
2. **Include tests** for new behavior. Coverage must stay at or above 80%.
3. **Not break the public API** without a major-version bump.
4. **Have a clear commit message** explaining *why*, not just *what*.

## Branch & commit conventions

- Branch off `main`. Name branches `feat/`, `fix/`, `chore/`, or `docs/`.
- Keep commits focused. One logical change per commit.
- Reference the issue number if applicable: `fix(parser): handle encrypted PDF (#42)`.

## Code style

- Formatted by `ruff format` (PEP 8 compatible, line length 100).
- Type hints required on all public functions.
- `from __future__ import annotations` at the top of every module.
- Prefer `pathlib.Path` over `os.path`.
- Use `pydantic` for data validation at module boundaries.

## Testing philosophy

- **Unit tests** — fast, isolated, no real services. Use mocks for Ollama and ChromaDB.
- **Integration tests** — marked with `@pytest.mark.integration`. Touch real services. Run with `pytest -m integration`.
- **Test the failure paths.** Encrypted PDFs, empty files, oversized inputs, malformed Unicode.

## Reviewing checklist (for maintainers)

- [ ] Tests cover the change and the documented edge cases
- [ ] No new dependencies without justification
- [ ] No secrets, paths, or PII in test fixtures
- [ ] Public API changes documented in CHANGELOG.md
- [ ] Performance regression check if touching the RAG pipeline

## Reporting bugs

Open a GitHub issue with:

1. Minimal reproduction steps
2. Expected vs actual behavior
3. Environment (OS, Python version, Ollama version, model)
4. Relevant logs (with secrets redacted)
