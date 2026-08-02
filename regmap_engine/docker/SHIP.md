# Shipping & hosting the RegMap crosswalk engine (standalone)

This is a **standalone system**: everything the service needs is either in this repo or pulled once at
build time and then frozen into the image. There is no external database, no license server, and (when
shipped as an image) no runtime internet dependency.

---

## 1. What was downloaded for this phase
**Nothing.** This phase authored 9 files (`serve.py` + the `docker/` folder). No assets were fetched.

Dependencies are pulled **at `docker build` time**, not committed to the repo:

| Pulled at build time | From | Approx size |
|---|---|---|
| `torch` (CPU‑only) | `download.pytorch.org/whl/cpu` | ~190 MB |
| `sentence-transformers`, `transformers`, `tokenizers`, `huggingface-hub`, `scikit-learn`, `scipy`, `numpy`, `fastapi`, `uvicorn`, pydantic, … | PyPI | ~250 MB combined |

The one **large asset that already lives in the repo** (not downloaded this phase — it's your trained
model) is `models/regmap-embedder/` (**88 MB**, `model.safetensors` is 87 MB of it). That is the only
heavy file you author; everything else is code or pip-fetched.

> The image sets `HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1` — the baked-in model is loaded from a
> local path, so the running container never calls out to Hugging Face.

---

## 2. Files you must ship — two modes

### Mode A — ship the source, host builds the image  *(host needs internet at build)*
Ship the **build context** (the `.dockerignore` already trims it to just these):

```
regmap_engine/
  serve.py  eval_crosswalk.py  import_olir.py  README.md
  crosswalks/**                      # the framework pairs
  docker/Dockerfile  docker/requirements.txt
models/regmap-embedder/**            # 88 MB — the fine-tuned weights (the only heavy file)
.dockerignore                        # so the build context stays small
```
On the host:
```
docker build -f regmap_engine/docker/Dockerfile -t regmap-engine:0.1 .
docker run --rm -p 8000:8000 regmap-engine:0.1
```
Total transfer to host ≈ **~90 MB** (mostly the model); the ~450 MB of deps download on the host.

### Mode B — ship ONE prebuilt image tarball  *(host needs NO internet — true standalone)* ✅ recommended for hosting
Build + export on your machine:
```
regmap_engine/docker/save-image.ps1        # Windows  → dist/regmap-engine-0.1.tar
regmap_engine/docker/save-image.sh         # Linux/mac
```
Ship the **single file** `dist/regmap-engine-0.1.tar` (~**500–700 MB**: OS layer + python + torch + all
deps + your model, frozen together). On the host:
```
docker load -i regmap-engine-0.1.tar
docker run --rm -p 8000:8000 regmap-engine:0.1
```
No source, no pip, no Hugging Face, no internet. This is the mode to use for an air-gapped or
locked-down hosting platform.

---

## 2a. CPU or GPU — one image, any environment
The default build installs torch from PyPI: a **GPU-capable build that also runs on a plain CPU host**, so
the same image is portable. Device is auto-detected at startup (`cuda` if visible, else `cpu`) and reported
by `/health`. Force it with `-e REGMAP_DEVICE=cpu|cuda`.

| Target | Build | Run |
|---|---|---|
| **Any (default)** — GPU if present, else CPU | `docker build -f regmap_engine/docker/Dockerfile -t regmap-engine:0.1 .` | `docker run -p 8000:8000 regmap-engine:0.1` |
| **GPU host** (NVIDIA) | *(same image)* | `docker run --gpus all -p 8000:8000 regmap-engine:0.1` |
| **Slim CPU-only** (no CUDA libs, smaller) | `--build-arg TORCH_INDEX=https://download.pytorch.org/whl/cpu` | `docker run -p 8000:8000 regmap-engine:0.1-cpu` |
| **Pinned CUDA** (e.g. 12.4) | `--build-arg TORCH_INDEX=https://download.pytorch.org/whl/cu124` | `docker run --gpus all …` |

GPU at runtime needs the **NVIDIA Container Toolkit** on the host + `--gpus all`; no code or image change.

## 3. Hosting-platform notes
- **Any container host** (Fly.io, Render, Railway, AWS ECS/App Runner, Azure Container Apps, GCP Cloud
  Run, a Proxmox LXC with Docker, a bare VM): they all accept either a registry image or a tarball.
  - Registry route: `docker tag regmap-engine:0.1 <registry>/regmap-engine:0.1 && docker push …`, then
    point the platform at that image. (This replaces Mode B's tarball with a registry pull.)
  - Tarball route: use Mode B where the platform lets you `docker load` (self-managed VM/LXC).
- **Port:** the container listens on `8000`. Map/expose it (`-p 8000:8000`) or set the platform's port to 8000.
- **Resources:** runs CPU-only (~1 vCPU / **1.5–2 GB RAM**) *or* on GPU when one is present + `--gpus all`
  (auto-detected; `/health` shows `device`). First request after boot warms the model (~2–4 s on CPU).
- **Persistence:** none required — the engine is stateless. Crosswalk pairs are read-only inside the image.
- **Scaling:** stateless, so run N replicas behind the platform's load balancer; no shared state.
- **TLS/auth:** none built in (it's an internal API). Put it behind the platform's HTTPS + an API
  gateway / reverse proxy if exposing publicly.

---

## 4. Where this sits in the product plan
Add to **Phase 0 / workstream B** of `docs/product_roadmap.md`:

- [x] Engine generalized to multi-framework pairs (`regmap_engine/`)
- [x] Engine exposed as an HTTP API (`serve.py`)
- [x] **Standalone containerization + ship manifest** (this folder) — Mode B tarball is the deploy artifact
- [ ] Publish `regmap-engine:0.1` to a registry (or hand off the tarball) and stand it up on the host
- [ ] Replace the sample CSF↔800‑53 pair with the official OLIR import (`import_olir.py`)
- [ ] Wire the hosted engine's `/map` into the app's Assess/RegMap UI (call the API instead of in-proc)
