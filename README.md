# RegMap — compliance crosswalk engine (product)

Standalone project to develop **RegMap** into a product: map any control/requirement in framework X to the
equivalent provisions in framework Y — ranked, scored, provenance-tagged, gap-aware — as an **API + web UI**
in one container, deployable from laptop to Kubernetes.

**All development lives in [`regmap_engine/`](regmap_engine/).** The rest of the tree supports it.

> 🔖 **Resuming work? Start at [`docs/build_log.md`](docs/build_log.md)** — the single resume file: what's
> built, what's next, and open decisions. Plan: [`docs/hosted_saas_roadmap.md`](docs/hosted_saas_roadmap.md)
> (hosted multi-tenant SaaS on managed K8s, metered compute).

```
regmap-platform/
├── regmap_engine/          ← THE PRODUCT (develop here)
│   ├── serve.py            API (/map /eval /pairs /health /usage) + serves the web UI
│   ├── eval_crosswalk.py   retrieval benchmark (Recall@k / nDCG / MRR / MAP; TF-IDF · BM25 · embedder)
│   ├── import_olir.py      turn an official OLIR/crosswalk export into a pair
│   ├── crosswalks/         framework pairs (source.jsonl · corpus.jsonl · gold.jsonl · meta.json)
│   ├── web/                the product website (index.html + assets/) served by serve.py
│   ├── docker/             self-contained image (any-env CPU/GPU, non-root, metered) + SHIP.md
│   └── k8s/                Deployment · Service · HPA · NetworkPolicy (+ opt-in GPU · KEDA)
├── models/regmap-embedder/ fine-tuned embedder (serve.py loads ../models/regmap-embedder)
├── data/
│   ├── raw/                official NIST 800-53 ↔ HIPAA crosswalk (feed import_olir.py)
│   └── processed/          training/eval pairs
├── notebooks/              embedder fine-tune (retrain / improve = engine Tier 2)
├── paper/regmap/           research + eval methodology + results (the benchmark, reproducibility)
├── scripts/                model-release packager
└── docs/                   the plans: product_master_plan · product_roadmap · regmap_expansion_plan · deploy status
```

## Quickstart
```bash
pip install -r regmap_engine/docker/requirements.txt          # + torch (see docker/ for CPU/GPU)

# run the product (API + website) locally
uvicorn serve:app --app-dir regmap_engine --host 0.0.0.0 --port 8000
#   UI:  http://localhost:8000/        API docs: http://localhost:8000/docs

# benchmark the engine on the bundled pair (embedder vs TF-IDF/BM25)
python regmap_engine/eval_crosswalk.py regmap_engine/crosswalks/nist_csf2__nist_80053 --model models/regmap-embedder

# containerize (any environment) and deploy
docker build -f regmap_engine/docker/Dockerfile -t regmap-engine .   # from this root
kubectl apply -k regmap_engine/k8s
```

## Expand it (the roadmap — see docs/)
- **Tier 1 · Breadth:** add framework pairs. Start with official mappings: run `import_olir.py` on
  `data/raw/nist_800_53_rev5_hipaa_crosswalk_full.csv` to build the authoritative NIST 800-53 ↔ HIPAA pair,
  then ISO 27001 ↔ NIST via NIST **OLIR**. Ship the multi-pair benchmark (`paper/regmap/`).
- **Tier 2 · Depth:** retrieve-then-**rerank** (cross-encoder), bigger/LLM embedders, hard-negative mining;
  retrain via `notebooks/`. Bidirectional & many-to-many; calibration + abstention.
- **Tier 3 · Workflow:** gap analysis, auto-generated audit evidence (RIRAG), continuous compliance (map deltas).
- **Tier 4 · Productize:** coverage/gap **dashboards** (extend `web/`), versioned crosswalks, human-in-the-loop
  verification UI, metered **API** (already in `serve.py`: `/usage`, `x-regmap-compute-units`).

Full detail: `docs/product_master_plan.md` (§2 Pillar A), `docs/regmap_expansion_plan.md`,
`docs/regmap_engine_deploy_status.md`.

## Licensing note
NIST/gov content is public domain. ISO/PCI/SOC2 → map **IDs + paraphrase**, not verbatim text.
**HITRUST & COBIT require licenses** before shipping their control content.
