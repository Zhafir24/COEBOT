# Security Policy

## Threat model

`doc_analyzer` is designed for enterprise local deployment. The threat model assumes:

- **Trusted host machine.** The user controls the machine, the filesystem, and the Ollama daemon.
- **Untrusted documents.** PDFs may contain malicious payloads (JavaScript, embedded files, exploits targeting parsers).
- **Untrusted prompts.** Users may inject prompts attempting to exfiltrate data or override system instructions.
- **No network egress required.** The application makes no outbound calls beyond `localhost:11434` (Ollama).

## In scope

- Parser exploits (malformed PDFs causing crashes, memory exhaustion, code execution).
- Prompt injection that causes the LLM to disregard system instructions.
- Path traversal in document loading.
- Information leakage between sessions (e.g., one user's documents appearing in another's responses).

## Out of scope

- Compromised host OS or Python interpreter.
- Attacks on the Ollama daemon itself (file a report with Ollama instead).
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

- Restrict the `data/documents/` directory permissions to the application user only.
- Run Ollama on `127.0.0.1` only (the default). Do not expose port 11434 to the network.
- Apply OS-level patches to the PDF rendering stack regularly.
- Review the `EMBEDDING_MODEL` choice — the default is from HuggingFace and downloaded on first run.
