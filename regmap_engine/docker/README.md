# RegMap crosswalk engine — Docker

Packages the crosswalk engine (`regmap_engine/`) + the fine-tuned embedder as a single API image.

## Build & run
```bash
# from the repo root (the build context must see the engine AND the model)
docker build -f regmap_engine/docker/Dockerfile -t regmap-engine:0.1 .
docker run --rm -p 8000:8000 regmap-engine:0.1
```
Or use the helper: `regmap_engine/docker/build.ps1` (Windows) / `build.sh` (Linux/mac).

## API
Interactive docs at `http://localhost:8000/docs`. Endpoints:

| Method | Path      | Purpose |
|--------|-----------|---------|
| GET    | `/health` | liveness + whether the embedder loaded (`embed`) or fell back to `tfidf` |
| GET    | `/pairs`  | crosswalk pairs baked in (name, frameworks, item counts) |
| POST   | `/map`    | `{ "text": "...", "pair": "nist_csf2__nist_80053", "top_k": 5 }` → ranked target controls |
| POST   | `/eval`   | `{ "pair": "nist_csf2__nist_80053" }` → Recall@k / nDCG@k / MRR / MAP per method |

```bash
curl -s localhost:8000/map -H 'content-type: application/json' \
  -d '{"text":"encrypt data at rest","pair":"nist_csf2__nist_80053","top_k":3}'
```

## Hosting / shipping this as a standalone system
See **[SHIP.md](SHIP.md)** — the file manifest and two deploy modes (ship source vs. ship one prebuilt
image tarball), plus hosting-platform notes (ports, RAM, offline). Use `save-image.ps1` / `save-image.sh`
to produce `dist/regmap-engine-0.1.tar` — a single self-contained file that needs no internet on the host.

## Notes
- The embedder is baked in (`models/regmap-embedder`, ~90 MB). To keep the image slim, drop the model
  `COPY` in the Dockerfile and mount it at runtime instead — see the header comment in `Dockerfile`.
- `torch` is installed CPU-only (from the PyTorch CPU index) so the image stays a few hundred MB, not GBs.
- No model present → the service still runs on TF-IDF; `/health` reports `"method":"tfidf"`.
