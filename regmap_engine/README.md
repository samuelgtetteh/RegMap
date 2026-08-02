# RegMap engine — multi-framework crosswalking

The reusable engine that generalizes RegMap from one pair (NIST 800-53 → HIPAA) to **any** framework
pair. Add a pair by dropping in three files; the evaluator and (later) the product read the same format.

## Crosswalk pair format
```
regmap_engine/crosswalks/<pair_name>/
  meta.json      { source_framework, target_framework, description, provenance, direction, license_note }
  source.jsonl   one per line: {"id": "<control id>", "text": "<control / requirement intent>"}
  corpus.jsonl   one per line: {"id": "<control id>", "text": "<control intent>"}      (the target framework)
  gold.jsonl     one per line: {"source_id": "<id>", "target_ids": ["...","..."], "provenance": "official|human|model|sample"}
```
- **Map control IDs + paraphrased intent, never copyrighted standard text.** NIST content is public
  domain; for ISO/PCI/SOC2/etc. use IDs + your own short paraphrase (see `docs/product_master_plan.md`
  licensing). Every gold row carries a **provenance** tag.

## Evaluate a pair
```
venv\Scripts\python.exe regmap_engine\eval_crosswalk.py regmap_engine\crosswalks\nist_csf2__nist_80053
# use the released fine-tuned model as the embedder:
venv\Scripts\python.exe regmap_engine\eval_crosswalk.py regmap_engine\crosswalks\nist_csf2__nist_80053 --model models\regmap-embedder
```
Reports Recall@k / nDCG@k / MRR / MAP for TF-IDF (always), BM25 (if `rank_bm25` installed), and the
embedder (if `sentence-transformers` + weights available). Recall@k = multi-relevant coverage.

## Add the authoritative NIST CSF ↔ 800-53 mapping (replace the sample)
The bundled `nist_csf2__nist_80053` pair is a small **SAMPLE**. Replace it with the official mapping:
```
venv\Scripts\python.exe regmap_engine\import_olir.py --help
```
NIST publishes the CSF 2.0 informative references / OLIR crosswalks (public domain). Download the export,
point the importer at it, and it writes `source.jsonl` / `corpus.jsonl` / `gold.jsonl` with
`provenance:"official"`.

## Ship as a container (API)
`serve.py` exposes the engine as an HTTP API (`/map`, `/eval`, `/pairs`, `/health`); the build lives in
[`docker/`](docker/):
```
docker build -f regmap_engine/docker/Dockerfile -t regmap-engine:0.1 .   # run from repo root
docker run --rm -p 8000:8000 regmap-engine:0.1                            # docs at :8000/docs
```
The embedder is baked in; with no model present the service still runs on TF-IDF. See `docker/README.md`.

## Run on Kubernetes
Manifests live in [`k8s/`](k8s/) — CPU Deployment + Service + HPA + NetworkPolicy (core set), plus opt-in
GPU Deployment and KEDA scale-to-zero. Test locally on **Docker Desktop's built-in Kubernetes** (uses the
local image, no registry):
```
docker build -f regmap_engine/docker/Dockerfile -t regmap-engine:0.1 .   # if not built
kubectl apply -k regmap_engine/k8s
kubectl -n regmap port-forward svc/regmap-engine 8010:80                  # then curl :8010/health
```
Or run `regmap_engine/k8s/test.sh` / `test.ps1` (applies, waits, curls `/health` `/map` `/usage`). See
`k8s/README.md`.

## Roadmap fit
This is **Tier 1** of `docs/regmap_expansion_plan.md` and workstream **B** of `docs/product_roadmap.md`:
add pairs (NIST CSF, ISO 27001, PCI DSS, SOC 2, CIS, CMMC/800-171, GDPR, …), compose them through the
NIST OLIR / Secure Controls Framework hub, and ship the multi-pair benchmark (paper **P3**).
```
```
