"""doc_analyzer — local document analysis chatbot.

A retrieval-augmented generation (RAG) system that runs entirely on
the user's machine. No external API calls, no telemetry.
"""

from __future__ import annotations

import os

# Force HuggingFace libraries into offline mode BEFORE any submodule
# imports sentence-transformers, transformers, or huggingface_hub.
# Without these, the libraries try to "check for updates" on the Hub
# every time a model loads — which requires internet and was the
# cause of upload failures in airplane mode (the embedding step in
# ingest_document hangs on the Hub check). The model is cached locally
# at ~/.cache/huggingface/hub/, so offline mode reads from cache only.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

__version__ = "0.1.0"
__all__ = ["__version__"]
