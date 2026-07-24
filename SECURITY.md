# Security Policy

## Threat model

COEBOT (`doc_analyzer`) is designed for enterprise local deployment. The threat model assumes:

- **Trusted host machine.** The user controls the machine, the filesystem, the GGUF model files, and the running Python process.
- **Untrusted documents.** PDFs, DOCXs, and XLSXs may contain malicious payloads (JavaScript, embedded files, exploits targeting parsers).
- **Untrusted prompts.** Users may inject prompts attempting to exfiltrate data or override system instructions.
- **No network egress required at runtime.** After the first-run embedding-model download, the application makes no outbound calls whatsoever.

## In scope

- Parser exploits (malformed PDFs/DOCXs/XLSXs causing crashes, memory exhaustion, code execution).
- Prompt injection that causes the LLM to disregard system instructions.
- Path traversal in document loading or model selection.
- Information leakage between users (e.g., one user's documents or memory facts appearing in another's responses).
- Credential handling of the local user store (scrypt hashing, session token isolation).

## Out of scope

- Compromised host OS or Python interpreter.
- Vulnerabilities in third-party libraries (`llama-cpp-python`, `chromadb`, `openpyxl`, etc.) — report upstream to those projects.
- Model hallucination (mitigated by retrieval grounding, not preventable).
- Denial of service via large documents (rate-limited at the application layer).

## Reporting a vulnerability

**Do not open a public GitHub issue.**

Email security reports to: zhafirdhafin7@gmail.com

Include:

1. A description of the vulnerability and impact.
2. Steps to reproduce, with the smallest possible test case.
3. Affected version (commit SHA or release tag).
4. Suggested mitigation if you have one.

You can expect:

- An acknowledgment within 72 hours.
- An assessment and remediation plan within 14 days.
- A coordinated disclosure once a fix ships.

## Hardening guidance for operators

- Restrict the `data/documents/`, `data/chats/`, `data/users.json`, and `data/memory.json` files' permissions to the application user only.
- The Starlette server binds to `127.0.0.1` on port 80 by default (see `launch-windows.ps1`). Do **not** change the bind address to `0.0.0.0` without a firewall in front — the app has no rate limiting or CSRF hardening for network exposure.
- Apply OS-level patches to the PDF/DOCX/XLSX rendering stack regularly.
- Review the `EMBEDDING_MODEL` choice — the default is from HuggingFace and downloaded on first run.
- Never commit `*.gguf`, `data/chats/`, `data/users.json`, or `data/memory.json` — the shipped `.gitignore` already blocks these paths.
