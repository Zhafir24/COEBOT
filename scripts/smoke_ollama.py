"""Smoke test: verify Ollama is reachable and the configured model responds.

Run with:
    python scripts/smoke_ollama.py

Exits 0 on success, 1 on any failure. Used in development to confirm
the local stack before running the full pipeline.
"""

from __future__ import annotations

from ollama import Client

from doc_analyzer.config import get_settings


def main() -> int:
    settings = get_settings()
    print(f"Ollama host:  {settings.ollama_host}")
    print(f"Ollama model: {settings.ollama_model}")
    print(f"Timeout:      {settings.ollama_timeout_seconds}s")
    print()

    client = Client(host=settings.ollama_host, timeout=settings.ollama_timeout_seconds)

    print("==> Listing installed models...")
    try:
        models = client.list()
    except Exception as exc:
        print(f"FAIL: could not reach Ollama at {settings.ollama_host}: {exc}")
        return 1

    tags = [m.model for m in models.models if m.model is not None]
    if not tags:
        print("FAIL: Ollama is reachable but has no models installed.")
        return 1
    for tag in tags:
        print(f"  - {tag}")
    print()

    if settings.ollama_model not in tags:
        print(
            f"FAIL: configured model {settings.ollama_model!r} is not installed.\n"
            f"      Pull it with: ollama pull {settings.ollama_model}"
        )
        return 1

    print(f"==> Sending a tiny test prompt to {settings.ollama_model}...")
    try:
        response = client.chat(
            model=settings.ollama_model,
            messages=[
                {"role": "user", "content": "Reply with the single word: ready"},
            ],
            options={"temperature": 0.0, "num_predict": 32},
            think=settings.ollama_think,
        )
    except Exception as exc:
        print(f"FAIL: chat call raised: {exc}")
        return 1

    content = response.message.content or ""
    print(f"Response: {content.strip()!r}")
    if not content.strip():
        print(
            "FAIL: model returned empty content. If this is a thinking model, "
            "set OLLAMA_THINK=false or pick a different model."
        )
        return 1
    print()
    print("OK: Ollama is reachable and the model responded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
