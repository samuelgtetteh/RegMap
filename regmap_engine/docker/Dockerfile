# RegMap crosswalk engine — self-contained API image, portable to ANY environment (CPU or GPU).
#
# Build from the REPO ROOT (the context must see both the engine and the released model).
#
#   # (1) Any-environment default — GPU-capable build that ALSO runs on a plain CPU host:
#   docker build -f regmap_engine/docker/Dockerfile -t regmap-engine:0.1 .
#
#   # (2) Slim CPU-only image (smaller, no CUDA libs) — pass the CPU wheel index:
#   docker build -f regmap_engine/docker/Dockerfile \
#     --build-arg TORCH_INDEX=https://download.pytorch.org/whl/cpu -t regmap-engine:0.1-cpu .
#
#   # (3) Pin a specific CUDA build (e.g. CUDA 12.4):
#   docker build -f regmap_engine/docker/Dockerfile \
#     --build-arg TORCH_INDEX=https://download.pytorch.org/whl/cu124 -t regmap-engine:0.1-cu124 .
#
# Run:
#   docker run --rm -p 8000:8000 regmap-engine:0.1                 # CPU host
#   docker run --rm --gpus all -p 8000:8000 regmap-engine:0.1     # GPU host (needs NVIDIA Container Toolkit)
#   curl localhost:8000/health        # -> reports the device it actually loaded on (cpu / cuda:0)
#
# The fine-tuned embedder is baked in (models/regmap-embedder). To keep the image small, drop that COPY
# and mount it at runtime: -v "$PWD/models/regmap-embedder:/app/models/regmap-embedder". No model present
# -> the service still runs and falls back to TF-IDF.
FROM python:3.11-slim

# Empty (default) => install torch from PyPI: a GPU-capable build that also runs on CPU (portable).
# Override with a PyTorch wheel index for a slim CPU-only image or a specific CUDA build (see header).
ARG TORCH_INDEX=""

WORKDIR /app

COPY regmap_engine/docker/requirements.txt ./requirements.txt
RUN if [ -n "$TORCH_INDEX" ]; then \
        pip install --no-cache-dir torch --index-url "$TORCH_INDEX"; \
    else \
        pip install --no-cache-dir torch; \
    fi \
 && pip install --no-cache-dir -r requirements.txt

# The engine (code + framework catalog) and the released embedder.
COPY regmap_engine /app/regmap_engine
COPY models/regmap-embedder-v2 /app/models/regmap-embedder-v2

# Version stamp for reproducibility — surfaced in /health, /usage and every /map response.
ARG ENGINE_VERSION=0.2
ARG MODEL_VERSION=regmap-embedder@0.2

# Standalone: the model is local, so forbid any runtime call-home to Hugging Face.
# Device is auto-detected at startup (cuda if visible, else cpu); force it with REGMAP_DEVICE if needed.
ENV REGMAP_MODEL=/app/models/regmap-embedder-v2 \
    REGMAP_ENGINE_VERSION=${ENGINE_VERSION} \
    REGMAP_MODEL_VERSION=${MODEL_VERSION} \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    PYTHONUNBUFFERED=1

# Pre-compute the embedding cache so a container starts in seconds instead of re-encoding the whole
# catalog (~1,400 controls and growing) on every boot. This MUST happen here, while still root: /app is
# root-owned and the runtime user cannot write the cache, so without this every start would re-encode.
# The result is verified — a silent miss here would only show up as slow k8s rollouts much later.
RUN cd /app/regmap_engine \
 && python warm_cache.py \
 && test -n "$(ls catalog/.embeddings/*.npz 2>/dev/null)" \
      || (echo "embedding cache was not written" >&2; exit 1)

# Run as a non-root user (security: smaller blast radius, passes image scanners' root check).
# The engine only reads /app at runtime, so root ownership is left in place deliberately.
RUN useradd -m -u 10001 appuser
USER appuser

WORKDIR /app/regmap_engine
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"

CMD ["uvicorn", "serve:app", "--host", "0.0.0.0", "--port", "8000"]
