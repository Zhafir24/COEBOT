# syntax=docker/dockerfile:1.6
# ============================================================
# COEBOT — Docker image (CPU inference, linux/amd64)
#
# Two-stage build:
#   * builder stage compiles llama-cpp-python from PyPI sdist
#     (no prebuilt Linux wheel exists for the pinned version, and
#     compiling with GGML_NATIVE=OFF produces a portable AVX2
#     binary that runs on any modern x86_64 CPU).
#   * runtime stage installs the wheel + the rest of the app
#     without the build toolchain, keeping the final image
#     roughly 1 GB smaller.
#
# Apple Silicon (arm64) is NOT covered by this image; see
# README section "Docker install" for the caveat.
# ============================================================

FROM python:3.12-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        ninja-build \
        git \
    && rm -rf /var/lib/apt/lists/*

# GGML_NATIVE=OFF forces a portable binary (no AVX-512, no CPU-family
# specific opt-in) so the resulting wheel runs on any modern x86_64
# host, mirroring what the release ZIP ships.
ENV CMAKE_ARGS="-DGGML_NATIVE=OFF"
ENV FORCE_CMAKE=1

RUN pip wheel --wheel-dir=/wheels "llama-cpp-python==0.3.32"


# ============================================================
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/opt/hf-cache

WORKDIR /app

# Copy the prebuilt engine wheel from the builder stage.
COPY --from=builder /wheels/ /wheels/

# Copy the project manifest + sources first so the pip layer can be
# cached whenever only static/ changes below. LICENSE is referenced by
# pyproject.toml's [project] table so pip refuses to build metadata
# without it.
COPY pyproject.toml README.md LICENSE /app/
COPY src/ /app/src/

# Install the compiled engine wheel, then the rest of the project
# (which pulls torch, transformers, chromadb, sentence-transformers,
# starlette, uvicorn, etc.). No build tools in this stage.
#
# Editable install (-e) keeps the source at /app/src so the app's
# _PROJECT_ROOT = Path(__file__).parent.parent.parent resolves to /app
# instead of site-packages/../../, matching the directory layout the
# rest of the code assumes for data/, models/, static/, webui/.
RUN pip install --no-cache-dir /wheels/llama_cpp_python-*.whl \
    && pip install --no-cache-dir -e .

# Pre-download the sentence-transformers embedding model into a shared
# HF cache. The app hard-codes HF_HUB_OFFLINE=1 at import time, so this
# offline-time bundling is REQUIRED for first upload to work inside the
# container. Downloaded to HF_HOME so both root (build time) and coebot
# (runtime) can read it.
RUN mkdir -p "${HF_HOME}" \
    && python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')" \
    && chmod -R a+rX "${HF_HOME}"

# Copy remaining runtime assets (PNM logo served at /logo.svg).
COPY static/ /app/static/

# Runtime helper: chown the bind-mounted directories once the volumes
# are visible so the non-root user can write to them.
COPY docker/entrypoint.sh /usr/local/bin/coebot-entrypoint
RUN chmod +x /usr/local/bin/coebot-entrypoint

# Non-root user for runtime. UID 1001 avoids common host-user clashes.
RUN useradd --create-home --uid 1001 coebot \
    && chown -R coebot:coebot /app

# Pre-create empty data + models directories so they exist before the
# host bind mount, and so a container run without any mounts still
# starts up (writing to the container filesystem — non-persistent but
# useful for a first-run smoke test).
RUN mkdir -p /app/data/chats /app/data/documents /app/data/chroma_db \
             /app/data/cache /app/models \
    && chown -R coebot:coebot /app/data /app/models

EXPOSE 80

# Health check: probe the JSON bootstrap endpoint. --start-period gives
# the model load + Python startup ~90 s of grace before failures count.
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD python -c "import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://localhost:80/api/bootstrap', timeout=3).status == 200 else 1)" \
        || exit 1

ENTRYPOINT ["/usr/local/bin/coebot-entrypoint"]
CMD ["python", "-m", "uvicorn", "doc_analyzer.server:app", "--host", "0.0.0.0", "--port", "80"]
