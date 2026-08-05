# Build log — hosted SaaS, metered compute

**This is the resume file. Start every session here; end every session by updating it.**

Tracks the build defined in `docs/hosted_saas_roadmap.md` (decision: hosted multi-tenant SaaS on managed
K8s, metered compute, incl. paid practice environments). Same convention as
`docs/regmap_expansion_plan.md`: tick the boxes, then update **Resume pointer** at the bottom.

How to use it:
- One line per task, `[ ]` → `[x]`, with the **evidence** (command run, numbers seen, file written).
- Anything surprising goes in **Findings** — that's what future-you forgets.
- Update **Resume pointer** last. It should be enough to restart cold with no other context.

---

## Version control — done

- [x] `git init` on `main` (2026-08-02). **Git LFS** tracks `*.safetensors` / `*.docx` / `*.pdf`, so the
      87 MB model does not bloat history on every Tier-2 retrain.
- [x] Committing at the end of each work chunk, so this log and the history agree.
- [ ] **No remote configured** — nothing is pushed, so this tree is still the only copy. Decide a remote.

---

## Environment state (2026-08-02)

| | Status |
|---|---|
| `torch` | ✅ **2.12.1+cpu** — was already installed on this machine |
| `sentence-transformers` | ✅ 5.6.1 (installed 2026-08-02) |
| `transformers` | ✅ 5.14.1 |
| `scikit-learn` / TF-IDF | ✅ 1.9.0 |
| `rank_bm25` | ✅ installed — the BM25 baseline runs for the first time |
| `numpy` / `fastapi` | ✅ 2.5.0 / 0.139.0 |
| Model weights | ✅ **loads** — 384-dim, max_seq 256, cpu |

Interpreter: `C:\Users\User\AppData\Local\Programs\Python\Python314\python.exe` (3.14.6). **No venv** —
torch was already there globally, so `sentence-transformers` went into the same interpreter rather than a
fresh venv needing its own multi-GB torch copy.

- [x] Added `rank_bm25` to `docker/requirements.txt` — it was missing, so the container could never report
      the BM25 column that the CLI and `/eval` advertise.

### Measured with the embedder active (2026-08-02)
`eval_crosswalk.py` on `nist_80053__hipaa`, all three methods, 133 queries:

| method | R@1 | R@5 | R@10 | nDCG@10 | MAP |
|---|---|---|---|---|---|
| TF-IDF | 0.223 | 0.486 | 0.592 | 0.439 | 0.391 |
| BM25 | 0.172 | 0.397 | 0.481 | 0.340 | 0.304 |
| **regmap-embedder** | **0.478** | **0.906** | **0.965** | **0.816** | **0.756** |

⚠️ **Inflated — not a benchmark.** This is the pair the embedder was fine-tuned on and the harness has no
held-out split (Findings #1). It confirms the model loads and dominates lexical retrieval, nothing more.
The defensible held-out figure is the paper's multi-relevant R@5 **0.797**.

**Product effect**, same query (`AC-1` → HIPAA), TF-IDF vs embedder: coverage **60% → 100%** — all 5
official mappings retrieved, 4 of them in the top 4. Screenshot-verified in the UI.

---

## Phase A — Foundation *(prerequisite under every pricing model; fully unblocked)*

### A0 · Catalog architecture — "all compliance in one place" *(DONE 2026-08-02)*
The pair-per-directory format could not reach a full framework catalog. It is now hub-and-spoke.

- [x] **Diagnosed the blocker.** Each pair directory carried its own private copy of both frameworks'
      control text. NIST 800-53 existed in **two** pairs with 22 overlapping ids and **all 22 had
      different text** — the catalog had already drifted at two pairs. At 20 frameworks that is up to 190
      directories and 20 conflicting copies of 800-53: one control answering differently depending on the
      route taken. Fatal for an auditability product.
- [x] **Built `regmap_engine/catalog.py`** — control text lives once per framework; mappings reference ids:
      `catalog/frameworks.json` (registry) · `catalog/frameworks/<fid>/controls.jsonl` ·
      `catalog/mappings/<a>__<b>.jsonl`. Resolves a pair three ways in precedence order: **direct** →
      **inverted** (one official export serves both directions) → **derived via hub** (X→H→Y, the
      SCF/OLIR hub idea in `product_master_plan.md` §2.3). Derived mappings are tagged
      `provenance:"derived"` and never presented as authoritative.
- [x] **Built `regmap_engine/migrate_to_catalog.py`** and migrated. Conflict resolution is by declared
      trust tier (official > human > model > sample, ties to longer text), and every conflict is
      reported rather than silently resolved. All 22 x 800-53 conflicts went to the official OLIR import
      over the sample — correct outcome, and auditable.
- [x] **Verified lossless.** `catalog.as_pair()` is a drop-in for `eval_crosswalk.load_pair()`. The
      direct pair reproduces the pre-migration numbers **exactly** (TF-IDF R@1 0.223 · R@5 0.486 ·
      MAP 0.391), so no data was lost or altered. Inverted and derived routes also evaluate.
- [x] **Payoff measured: 2 mappings on disk → 6 answerable pairs.** 2 direct, 2 free from inversion,
      and 2 genuinely new (`nist_csf2 ↔ hipaa_security`, derived via the 800-53 hub). Every future
      framework mapped to a hub gains pairs with everything already on it — breadth stops being O(N²).
- [x] **Registry seeded with 13 frameworks** carrying an `access` gate for the licensing wall:
      `public` (NIST/gov/GDPR — ship freely) · `paraphrase-only` (ISO/PCI/SOC2/CIS — IDs + own
      paraphrase, never verbatim) · `licence-required` (**HITRUST, COBIT — blocked until licensed**).
      Unpopulated frameworks report `controls: 0` so the UI can say "coming soon" instead of
      silently promising coverage.

### A1 · Content and UI

- [x] **Build the authoritative NIST 800-53 → HIPAA pair.** DONE 2026-08-02.
      `crosswalks/nist_80053__hipaa/` — **133 source controls · 60 HIPAA provisions · 222 gold pairs**,
      all `provenance:"official"`, avg 1.67 targets/control, zero empty texts. Reproduces the DTRAP
      paper's dataset exactly (paper states 222 pairs / 133 controls / 60 provisions).
      Command:
      ```
      python regmap_engine/import_olir.py \
        --infile "data/raw/nist_800_53_rev5_hipaa_crosswalk_full.csv" --format csv \
        --source-id "Focal Document Element" --source-text "Focal Document Element Description" \
        --target-id "Reference Document Element" --target-text "Reference Document Element Description" \
        --out regmap_engine/crosswalks/nist_80053__hipaa \
        --source-framework "NIST SP 800-53 Rev.5 (controls)" \
        --target-framework "HIPAA Security Rule (45 CFR Part 164 Subpart C)"
      ```
- [x] **Verified the engine reads it.** `eval_crosswalk.py` on the new pair: 133 evaluable queries,
      TF-IDF multi-relevant R@5 **0.486**, nDCG@10 0.439, MAP 0.391. (Embedder/BM25 unavailable locally —
      see Environment. **Do not quote these as a benchmark** — see Findings #1.)
- [x] **Re-ran the eval with the embedder.** DONE 2026-08-02 — see the table above. The model dominates
      both lexical baselines as served, and the API reports `method: embed`.
- [x] **Replaced the `SAMPLE` CSF↔800-53 pair.** DONE 2026-08-02 via the downloaded sources: the CSF 2.0
      OSCAL catalog gives **207 real controls** (was 12) and the OLIR informative-reference export gives
      **738 official CSF 2.0 → 800-53 mappings** (was 21 sample ones), with 209/210 target ids joining the
      catalog. Also added 800-171 Rev 3 (97 controls, plus its own official 800-53 mapping extracted from
      OSCAL back-matter) and SSDF (61).
- [x] **Phase 0's "2–3 live pairs" target is exceeded: 18 answerable pairs from 9 mappings.**
- [ ] **ISO 27001 is mapping-only, not searchable.** The OLIR export supplies 488 official CSF 2.0 → ISO
      27001 mappings (ids), but ISO's control *text* is copyrighted and cannot be shipped — so ISO can be
      crosswalked by identifier and not semantically searched. Same for PCI DSS (551), SCF (363), CIS (62).
      Making these useful needs either a licence or original paraphrases, plus an API route that returns
      official mapping ids without ranking. See `data/raw/SOURCES.md`
- [x] **UI that actually calls the engine.** DONE 2026-08-02, rendered and screenshot-verified in headless
      Chrome (not just contract-tested).
      - **`web/crosswalk.html`** — the working tool: any→any framework pickers from `/frameworks`, a route
        badge from `/pairs`, a searchable control picker from the new `GET /frameworks/{fid}/controls`, or
        free text. Results render with score meters, `official` markers, and **live coverage tiles**
        (official mappings · found in top-k · coverage % · route). Lands on a worked example rather than
        an empty page.
      - **`web/index.html`** — the fake result block is gone. The homepage demo now issues a real
        `POST /map` on load. It returns **AC-17 Remote Access @ 0.343** for "multi-factor authentication
        for remote access" — the correct answer. (The removed fake block claimed IA-5 @ 0.88; the invented
        numbers were also misleadingly high.)
      - **`web/assets/api.js`** — shared client that surfaces the engine's error *detail*, so a 403 shows
        its reason rather than a bare status.
      - Added `GET /frameworks/{fid}/controls` (licence-gated, verified 403 on HITRUST).
      - **TF-IDF now returns real scores.** `rank_tfidf` discards its cosine scores, so the fallback path
        rendered every score as "—". Added `_tfidf_scored` in `serve.py` for `/map` rather than changing
        `rank_tfidf`, whose shape `/eval` and the paper's scripts depend on. Regression-checked: `/eval`
        still returns R@1 0.223 · R@5 0.486 exactly.
- [x] **Stopped advertising uncovered frameworks.** The coverage section is now driven by `/frameworks`:
      "3 of 13 frameworks live · 205 controls indexed", grouped by family, with `coming soon` on
      unimported frameworks and **`licence required`** on HITRUST/COBIT. It cannot overstate coverage
      because it renders whatever the registry reports.
- [ ] Serve a per-pair provenance/coverage indicator in the UI (the auditability selling point) —
      `as_pair()` already returns `route` and `provenance` per pair, so the data is there
- [x] **`serve.py` now reads the catalog** (engine 0.2). DONE 2026-08-02, all endpoints run-tested
      against a live server. Corpora are embedded **once per framework** rather than once per pair.
      - `GET /frameworks` — 13 registered, 3 populated, with `access` + `available` + `hub` flags so the
        UI can render "coming soon" instead of promising absent coverage
      - `GET /pairs` — 6 answerable pairs, each with `route` and `authoritative`
      - `POST /map` — takes `target` + `text`, **or `source` + `source_id`**, in which case the response
        also carries the **official mapping** and flags each ranked result `official: true|false`
      - `POST /eval` — reports `benchmark: false` + a note, so its leaky numbers can't be misread
      - **Licence gate enforced at the API boundary**: `licence-required` frameworks return **403**
        unless listed in `$REGMAP_LICENSED`. Default-deny — verified HITRUST returns 403
      - **Legacy `{"text","pair"}` shape still works** (`k8s/test.sh`, `docker/README.md` unaffected)
      - `/usage` now self-reports `billable: false` with the reason, so it can't be mistaken for invoiceable
      - Verified consistent with the CLI: `/eval` returns R@1 0.223 · R@5 0.486, matching
        `eval_crosswalk.py` on the same pair
- [ ] Retire `crosswalks/` — `serve.py` no longer reads it, but keep it as the migration source until the
      catalog has been through a few more imports

### A1b · Site structure *(DONE 2026-08-02)*
- [x] **Split the one-page site into a page per nav title.** `#frameworks` and `#deploy` were anchors on
      the homepage; they are now real pages, and each nav entry maps to a `<body data-page="…">`.
      - **`frameworks.html`** — live coverage: summary stats (frameworks live / controls indexed /
        answerable pairs / official vs derived routes), framework cards by family with versions and hub
        flags, a **pair matrix** (from ↓ / to →, cells reading official · official ⇄ · derived · —) that
        makes the hub payoff visible, and a licensing legend for the three access tiers.
      - **`deploy.html`** — a live "what this instance is running" strip from `/health`, container build
        and run, CPU/CUDA build args, k8s apply, a **configuration table** for every `REGMAP_*` env var,
        and a "before this is a paid service" section stating plainly that there is no auth, the meter is
        not invoiceable, and there are no quotas.
      - **`index.html`** trimmed to a landing page: hero, live demo, how-it-works, and three cards routing
        to the new pages (the coverage card carries the real counts, so it can't overstate either).
- [x] **Took `/docs` and `/health` out of the public nav** — they expose engine internals and are meant to
      be admin-only. ⚠️ This is *not* access control; both are still reachable by URL. Real gating is
      specified in **Phase B7** below, including why `/health` must be split rather than gated.

### A1c · Docker image brought current *(DONE 2026-08-02)*
The images in Docker Desktop were all stale — testing against them tested a product from before any of
today's work.

- **Diagnosed `regmap-engine:0.1`** (8.72 GB local, any-env): no `catalog.py`, **`web/` completely
  empty** (it had never shipped the website at all, so `/` returned the inline fallback), and one pair
  with 12 gold mappings — not even the 800-53↔HIPAA pair. `ghcr.io/samuelgtetteh/regmap-engine:0.1-cpu`
  is the same vintage; its digest `sha256:aebf4f73…237b1` matches the k8s pin exactly.
- **`RegMap_Engine` container exit 137 was NOT a crash.** `OOMKilled=false` and the logs end with a
  clean `Shutting down` → `Application shutdown complete`. It was SIGKILLed after graceful shutdown —
  Docker Desktop stopping, or a `docker stop` timeout. Nothing to fix.
- [x] **Added `.dockerignore`** — there was none, so `COPY regmap_engine` baked in `__pycache__`,
      the dead `crosswalks/`, and would have shipped a host-built `.embeddings/`. ⚠️ Patterns need
      `**/` — a bare `__pycache__/` matches only the context root, and the host builds
      **cpython-314** `.pyc` files while the image runs **3.11**. Verified: 0 host `.pyc` files in the
      image now (the `cpython-311` ones left are generated in-image by the warm step, which is fine).
- [x] **Pre-warm the embedding cache at build time** (`warm_cache.py`, invoked from the Dockerfile with
      a `test -n` guard so a silent miss fails the build). Required because the container is non-root
      against a root-owned `/app` — at runtime the cache write fails, so without this it would
      re-encode the whole catalog on **every** boot.
- [x] **Bumped the Dockerfile `ENGINE_VERSION` default 0.1 → 0.2.** The `ENV` from that ARG overrides
      `serve.py`'s own default, so a rebuild would otherwise have reported engine 0.1 with 0.2 code.
- [x] **Built and verified `regmap-engine:0.2-cpu`** (2.18 GB, slim CPU — matches the k8s tier):
      starts in **5.2 s** with all 5 cache hits · engine 0.2 · embedder on · 5 frameworks /
      1,441 controls · 18 pairs · all four web pages 200 · `/map` returns official flags
      (AC-1→HIPAA: 4 of 5 official found) · HITRUST 403 · metering headers present · runs as
      uid 10001.

**Startup cost, measured** (correcting an earlier over-estimate of "minutes"): 1,441 controls encode in
**~27 s** cold; warm start is **~9 s** locally and **5.2 s** in the container, mostly model load. So the
cache is worth ~17-20 s per start today, and grows with the catalog.

- [ ] ⚠️ **`k8s/deployment.yaml` is still digest-pinned to the stale 0.1-cpu image.** Deploying it now
      ships the pre-catalog product with no website. Push `0.2-cpu` to GHCR and re-pin before any k8s
      work. Requires registry credentials
- [ ] Rebuild the any-env/GPU variant (`regmap-engine:0.2`) — only the slim CPU image was rebuilt

### A2 · Two audiences *(the product serves both — see roadmap §Audiences)*
- [ ] **GRC / IT teams:** bulk map a control set, coverage + gap report, export evidence
- [ ] **Students:** browse a framework catalog, guided "map this control" exercise, auto-graded against
      the official mapping. **The official mappings are already the grading ground truth** — 222 for
      800-53↔HIPAA — so auto-grading needs no new labelling effort. This is the cheapest possible first
      lab and it reuses Phase A content wholesale

## Phase B — Billing spine *(strict order; each depends on the last)*

- [ ] **Persistence** — Postgres + migrations. Schema: `accounts · api_keys · plans · usage_events ·
      usage_periods · subscriptions`. *The service has zero persistence today.*
- [ ] **API keys** — `Authorization: Bearer rk_…`, hashed at rest, per-account, revocable. Gate `/map` and
      `/eval`; leave `/health` open for k8s probes
- [ ] **Attributed metering** — resolve key → `account_id`; stamp it on every `METER` event and persist a
      `usage_events` row; monthly rollup. Retire in-memory `_usage` as a billing source
- [ ] **CU redesign** — `CU = work_units × device_rate`, deterministic per request (see roadmap). Keep true
      hardware seconds (timed around the `encode` calls only) as cost-of-goods telemetry, not the invoice line
- [ ] **Quota enforcement** — pre-request check of period usage vs plan allowance; `402` or metered overage.
      Period boundaries + resets
- [ ] **Harden `/eval`** — authenticated, rate-limited, bounded (cap queries × corpus per call). Currently
      the most expensive call in the service and open to the internet

### B7 · Admin-only endpoints *(decided 2026-08-02, deferred to this phase)*
Operator and diagnostic surfaces should not be public. They are already **out of the site nav** — that
stops advertising them, but it is **not** access control; they remain reachable by URL.

- [ ] **`/health` — split it, do not simply gate it.** ⚠️ `k8s/deployment.yaml` points **startupProbe,
      readinessProbe and livenessProbe** all at `/health` (lines 39-47). Putting auth in front of it would
      make every pod fail its probes and never go ready — it would take the whole deployment down. Correct
      shape:
      - public `/health` → `{"status":"ok"}` **only**, so the probes keep working
      - admin-only detail → today's payload leaks the **model filesystem path**, device, framework list and
        engine/model versions (`status · version · embedder · model · device · frameworks · pairs · method`)
- [ ] **`/docs`, `/redoc`, `/openapi.json`** — admin-only, or disabled in production via FastAPI's
      `docs_url=None` / `openapi_url=None`. Right now the full API schema is public
- [ ] **`/usage`** — admin-only; it is operator telemetry. Per-tenant usage belongs behind the customer's
      own account instead (B3)
- [ ] **`/eval`** — admin or paid-tier only (see the hardening item above)
- [ ] Decide the mechanism: an admin role/scope in the same `api_keys` table (B2) is the cheapest option
      that avoids maintaining a second auth system

## Phase C — Payments & self-service
- [ ] Stripe: plan subscriptions + usage records for overage; webhooks → `subscriptions`
- [ ] Signup / login / API-key management
- [ ] Usage dashboard (CU used vs allowance, invoice history)
- [ ] Publish price-per-call (possible only once CU is deterministic)

## Phase D — Practice environments *(the paid draw — blocked)*
- [ ] **Recover or rebuild `provisioner/`** — described as verified end-to-end in
      `regmap_engine_deploy_status.md` but **absent from this repo**. Its `rbac.yaml`, in-cluster
      `deployment.yaml`, and `README.md` were never created even in the parent
- [ ] Gate "Start session" behind control-plane auth + quota (billable before it starts)
- [ ] Real lab workloads (the engine image currently stands in for a lab target)
- [ ] Per-namespace infra metering → reconcile to CU

## Phase E — Cloud productionisation
- [ ] **Decide EKS vs AKS** (drives registry, managed Postgres, GPU instance types, IaC) — open decision
- [ ] Managed Postgres · ingress + TLS · secrets management
- [ ] Registry: image is a **private GHCR** package; decide GHCR-with-pull-secret vs ECR/ACR
- [ ] GPU node pool + KEDA scale-to-zero (manifests exist, untested — needs real GPU hardware)
- [ ] Hardening: pin dep versions (currently ranges), digest-pin base image (floating `python:3.11-slim`),
      SBOM, image signing, multi-arch

---

## Findings

1. **`eval_crosswalk.py` has no train/test split** — it scores every gold query, so on a pair the embedder
   was fine-tuned on (which `nist_80053__hipaa` is) the embedder's numbers will be **inflated by
   leakage**. Fine as a product smoke test; **never quote it as a benchmark.** The defensible numbers are
   the paper's held-out protocol (`paper/regmap/eval_regmap.py`, 34 held-out queries, and the
   group-split-by-control run in `eval_extras.py`).
2. **`data/raw/nist_800_53_rev5_hipaa_crosswalk_full (2).csv` is byte-identical** to
   `nist_800_53_rev5_hipaa_crosswalk_full.csv` — a duplicate download. Safe to delete, left in place for now.
3. The CSV is a true OLIR-format export; `import_olir.py`'s docstring example already names its exact
   columns, so the import needed no code changes.
4. `serve.py` embeds every pair's corpus **at startup** (`serve.py:125`), so **adding a pair requires a
   restart** — a customer cannot upload their own crosswalk without a redeploy. Matters for Phase D.
5. `serve.py` uses the deprecated `@app.on_event("startup")` with an unpinned `fastapi>=0.110,<1.0` —
   will break on a future FastAPI. Fold into the Phase E pinning work.

---

## Session log

**2026-08-02** — Decided delivery model (hosted SaaS + metered CU). Wrote `docs/hosted_saas_roadmap.md`;
corrected the `product_master_plan.md` §7 claim that billing was "built"; cross-linked `product_roadmap.md`
and `regmap_engine_deploy_status.md`. Started Phase A: imported the official 800-53↔HIPAA pair (222 gold
pairs, matches the paper) and verified the engine evaluates it. Created this log.

---

## Resume pointer

**Product target (restated 2026-08-02):** all compliance frameworks in one place, serving **both** GRC/IT
teams doing the work **and** students getting job-ready. Paid access, hosted SaaS, metered compute.
The research paper is explicitly **not** a current priority.

**Where we are:** Phase A0 complete — the data model is now a hub-and-spoke catalog that can actually
reach a full framework set, migrated losslessly, with 13 frameworks registered and licence gating in
place. Real content: 800-53↔HIPAA with **222 official mappings**. **6 answerable pairs from 2 mappings.**
Nothing in Phases B–E started. **No git repository yet.**

**Version control:** ✅ `git init` done 2026-08-02, baseline commit `027394a` on `main`. **Git LFS** tracks
`*.safetensors` / `*.docx` / `*.pdf` — the 87 MB model is in LFS, because Tier-2 retraining would otherwise
add ~87 MB to history per retrain and that needs a history rewrite to undo. No remote configured yet.

**The product is now demoable.** A visitor can land on `/`, see a real ranked mapping, open
`/crosswalk.html`, pick any two covered frameworks and any control, and see the model's ranking measured
against the official crosswalk. Nothing on the site is fabricated any more.

**RETRAIN: DONE 2026-08-03. `regmap-embedder@0.2` is shipped and serving.**

| model | val loss | R@1 | R@5 | nDCG@10 | R@5 95% CI |
|---|---|---|---|---|---|
| `@0.1` released | 3.2646 | 0.325 | 0.653 | 0.640 | 0.555–0.751 |
| **`@0.2` epoch 10 — SHIPPED** | 2.7019 | 0.310 | **0.734** | **0.693** | 0.647–0.818 |
| `v2-best` epoch 2 | **2.5509** | **0.334** | 0.682 | 0.664 | 0.591–0.774 |

64 held-out queries, ranked against full corpora. TF-IDF baseline R@5 0.470.

⚠️ **Two things not to forget:**
1. **The CIs overlap** — the gain is directionally consistent and reproducible but **not statistically
   significant** at n=64. R@1 got slightly worse. Do not quote it as significant.
2. **Validation loss picked the WRONG model.** The best-loss checkpoint (epoch 2) scored *worse* R@5.
   MNRL loss is computed against 15 in-batch candidates while the product ranks against ~1,000 controls,
   so they diverge. **Select on held-out R@5, never on loss.** `train_embedder.py` carries this warning
   inline; the best-checkpoint save it does is a diagnostic, not the release candidate.

Where the gain landed (and it is the right place): CSF→800-53 **0.244 → 0.344**, CSF→800-171
**0.563 → 0.682**, while 800-53→HIPAA held at 0.937 — breadth without catastrophic forgetting.

Artifacts: `models/regmap-embedder-v2/` + `MODEL_CARD.md` + `training_report.json` ·
`notebooks/03_embedder_retrain_v2.ipynb` (generated from the artifacts, 20 cells) ·
`data/processed/retrain-v2/eval_{baseline,v2,v2best}.json` ·
`docs/RegMap Platform - Progress Report.docx` · `docs/Exhibit 11B ….docx` (also copied into
`ai-cybersecurity-portfolio/exhibits/`). Image rebuilt as **`regmap-engine:0.3-cpu`**.
`models/regmap-embedder/` (@0.1) is deliberately untouched — the DTRAP figures need it.

**A2 DONE 2026-08-04 — both audience surfaces are built.**

- [x] **`web/learn.html` — the graded student exercise** (`aud-map-01`). Answer stays server-side:
      `POST /exercise` returns shuffled candidates and an **HMAC-signed token** carrying only the question
      and the candidate list; `POST /exercise/grade` re-derives the official answer from the catalog.
      Verified the response leaks no answer key, the token payload is `{src,tgt,sid,cands}` only, and a
      forged token is rejected with 400.
      Graded on **precision/recall/F1**, pass at F1 >= 0.70 — so "select everything" scores P 0.143 /
      F1 0.25 and **fails**, which is exactly the habit an auditor must not have. Candidates always
      include every official target, so a perfect score is reachable (verified F1 1.0); otherwise the
      exercise would be grading the model rather than the learner. Only pairs with an
      **authoritative** route are offered — grading against a derived route would mark a learner against
      a guess. Outcome colouring on reveal: correct / missed / does-not-map. Tagged NICE T0267.
- [x] **`web/gaps.html` + `POST /map/bulk` — the GRC surface.** Maps a whole control set in one pass and
      reports coverage plus the **official gap list**, computed by set difference over the published
      crosswalk — so the gap number says nothing about the model and can go into a report. Controls with
      no official entry get model suggestions, clearly labelled non-authoritative. CSV export tags every
      row `official` / `model-suggested` / `gap`. Capped at `REGMAP_BULK_MAX` (150) because bulk encodes
      one query per control; the response says so rather than silently truncating.
      Measured: HIPAA -> 800-53 covers **133 of 1,016** controls, **883 gaps**, 13.1%.
      CSF 2.0 -> 800-53 (first 150 of 207): 78 of 150 have an official mapping, 184 covered, 18.1%.
- [x] Both wired into the nav; all six pages' JS validated; both screenshot-verified rendering real data.

**PHASE B — DONE 2026-08-04. (Superseded next-action text below.)** Both buyer-facing surfaces now exist, so the thing that
gates revenue is next and it is strictly ordered: persistence -> API keys -> attributed metering -> CU
redesign -> quotas -> Stripe. Fold in B7 (admin-gate `/docs` and `/usage`; **split** `/health` rather
than gating it, because the k8s probes hit it) and rate-limit `/eval` and `/map/bulk`, which are now the
two most expensive calls and both unauthenticated.

**Also worth doing cheaply:** a LICENSE file (the public repo has none, which reads as all-rights-reserved
and undercuts Exhibit 11B's "freely usable" claim) and a README refresh (it still describes the
pre-catalog layout).

**Superseded — the old next-action text, kept for context:** pick a
random control from the source framework, hide the `official` flags, let the learner select which target
provisions they think map, then score their selection against `official.target_ids` and reveal. That is
**UI work only** — the answer key is already in the `/map` response, so there is no labelling and no
modelling to do. This is the cheapest possible first lab and it is the student half of the product.

**Then, in order:**
1. **Bulk / gap view for GRC teams** — map a whole control set in one pass, report coverage and gaps,
   export. This is the teams half, and it needs a new endpoint (`POST /map/bulk`).
2. Then Phase B (persistence → API keys → attributed metering → CU redesign → quotas).

**Startup cost to watch:** with the embedder on, boot takes ~30-40 s because every framework catalog is
encoded at startup. Fine now (205 controls), but it scales with the catalog and will hurt k8s readiness
probes and scale-up latency. Cache embeddings to disk (keyed by framework + model version) before the
catalog grows much — this belongs in Phase E, but note it now.

**Known cosmetic debt:** `crosswalks/` is now dead code for the API (kept as the migration source), and
`docker/README.md` still documents the old `pair`-only `/map` shape (the shape still works, but the doc
does not mention `source`/`source_id`/`target`).

**Cheap breadth win when ready:** import any framework's official mapping *to 800-53 or CSF 2.0* (both
flagged `hub: true`) and every framework already on that hub becomes reachable for free.

**Blocked / needs input:** EKS vs AKS · whether a free tier exists at all · CSF 2.0 and ISO 27001 need
OLIR exports **downloaded** (not on disk) · HITRUST + COBIT need licences before their content ships ·
`provisioner/` must be recovered from the parent repo for Phase D (practice environments).

---

## Phase D · lab sessions — teardown design PROVEN on real k8s *(2026-08-02)*

Design: `docs/lab_sessions_design.md`. Rig + manifests: `regmap_engine/k8s/labs/`.

**The commercial question was "what guarantees a lab stops when the credit runs out?"** Answer: not our
provisioner — its failure mode is silently burning money. Expiry is enforced by the cluster in layers,
with `Job` + `activeDeadlineSeconds` as the guarantee (kubelet kills it, no service of ours involved),
`ResourceQuota`/`LimitRange` as containment, and an in-cluster `CronJob` sweeper that works when our
services are dead. Credits are **held up front and refunded on teardown**, with the deadline *derived
from the payment*, so overspend is structurally impossible rather than merely monitored.

- [x] **Built the local rig on `kind`, not Docker Desktop.** Decisive reason: Docker Desktop's cluster
      uses kindnet, which **does not enforce NetworkPolicy** — policies apply and silently do nothing, so
      isolation would have looked correct while being absent. kind with `disableDefaultCNI` + Calico
      enforces it. Secondary reason: enabling Docker Desktop k8s restarts the Docker engine and would
      have stopped every other running container.
- [x] **`test-teardown.sh`: 9/9 passing** — deadline enforced (`DeadlineExceeded`), pod terminated, no SA
      token, **NetworkPolicy actually blocking egress**, metadata endpoint blocked, non-root +
      read-only rootfs, quota rejecting an over-limit pod, and the sweeper deleting an expired namespace
      from inside the cluster.
- [x] Installed `kind` v0.32.0 to `~/bin`; cluster `regmap-labs` = 1 control-plane + 2 workers labelled
      `regmap.io/pool=labs`, so labs land off the control-plane node as they would in cloud.

**Correction to an existing doc:** `regmap_engine_deploy_status.md` lists NetworkPolicy as "verified
running". That most likely meant "applied without error" on a CNI that ignores it. Treat as unverified.

- [ ] **Provisioner service** — still absent from this repo. When recovered or rebuilt it must be
      re-verified against this design: it was built around Deployments + a TTL reaper, i.e. layer 3 only,
      which is the mechanism this design deliberately does *not* rely on
- [ ] **Credit ledger + auth gate are Phase B.** The K8s loop is now *proven* but cannot be *sold* until
      accounts, credits and authentication exist. Sessions should be another `usage_events` row type —
      do not build a second billing system
- [ ] Lab sessions bill on **wall-clock × tier** (renting hardware), which is deliberately different
      from the API's deterministic work units. Do not unify the two meters
- [ ] Decide `MAX_SESSION_SECONDS`, idle-kill vs bill-as-paid, and warm-pool vs cold-start
- [ ] Real lab workloads — `regmap-engine:0.2-cpu` is only a stand-in
- [ ] Tear down the kind cluster when finished: `kind delete cluster --name regmap-labs`

---

## Download audit — are the raw files actually wired in? *(2026-08-02)*

Asked directly, audited rather than assumed. Answer at the time of asking: **no** — 6 of 13 data files
were wired, and **1,464 official mappings were unreachable**. Both largely fixed.

### Fixed
- [x] **`nist_80172_rev3.json` imported** — downloaded but never used. 103 controls. Also fixed
      `canon_id` to strip the `SP_800_172_3_0_0_` prefix (it only handled 800-171), so ids are
      `03.01.01E` rather than `SP_800_172_3_0_0_03.01.01E`.
- [x] **Mapping-only frameworks are now reachable — the big one.** ISO 27001, PCI DSS, CIS v8 and SCF
      had official mappings on disk but could not be served at all, because `as_pair()` needs both
      catalogs to have text and theirs is copyrighted. Added `catalog.official_targets()` plus a
      `/map` path that returns official mapped **identifiers** without ranking.
      **Answerable pairs: 18 → 34** (18 rankable + 16 mapping-only). `/pairs` now reports `rankable`
      per pair, and `GET /frameworks` reports `text: full | mapping-only`.
      Verified: `CSF PR.AA-01 → ISO 27001` = `5.15, 5.16, 5.18, 8.2, 8.5` (direct);
      `800-53 AC-2 → PCI DSS` resolves through the CSF hub and is correctly flagged non-authoritative.
- [x] **Fixed a real parsing bug found by doing this.** The OLIR label `ISO/IEC 27001:2022` contains a
      colon, and the parser split each line on its *first* colon — so the version leaked into the
      element and ISO ids came out as `2022: Annex A Controls: 5.15`. Also 63 literal `"None"`
      placeholders were becoming control ids. ISO mappings went 488 → **389**, which is a correctness
      gain, not a loss.

### Still not wired — deliberately
- [ ] **The four `nist_80053_baseline_*.json` files** are OSCAL **profiles**, not catalogs: they *select*
      control ids (149 at LOW, 370 at HIGH) rather than defining controls. They answer "is this control
      required at MODERATE?", which is a **control-selection/tagging** feature, not a crosswalk — so it
      needs a different model (a baseline attribute on 800-53 controls), not a framework entry.
      `import_oscal.py` handles `catalog` roots only and would need a separate profile importer.
- [ ] **`csf_pf_to_80053r5.xlsx`** — its `CSF to SP 800-53r5` sheet is **CSF v1.1**, superseded by the
      2.0 mappings already imported. Its `PF to SP 800-53r5` sheet (16,732 rows) is the **NIST Privacy
      Framework**, which is genuinely new content and is not in the registry at all yet.
- [ ] `nist_800_53_rev5_hipaa_crosswalk.csv` — a shorter earlier export of a file already imported.
- [ ] `nist_800_53_rev5_hipaa_crosswalk_full (2).csv` — byte-identical duplicate, safe to delete.

### Consequence
- [ ] **`regmap-engine:0.2-cpu` is now stale again** — it was built before 800-172, the mapping-only
      support and the ISO id fix. Rebuild before using it to test (its embedding cache is baked at
      build time, so a rebuild also re-warms it).

---

## Real labs for the k8s test — investigated *(2026-08-02)*

**Yes, two real labs exist** in the local images (from the parent platform), and both are genuine
auto-graded labs, not placeholders:

| lab | what it is | state |
|---|---|---|
| `cloud-target-lab:0.1` | Seeds **LocalStack** with real misconfigurations via boto3 — public S3 bucket `acme-public-uploads`, an insecure EC2 security group with a `legacy-jump-box`, IAM issues — then `verify.py` grades what the learner found. **This is the compliance/audit lab** and it maps directly onto RegMap: "public bucket → which 800-53 control? → which HIPAA/ISO clause?" | **best fit, blocked — see below** |
| `live-target-lab:0.1` | `identity_generator.py` streams synthetic logins forever at the Identity Anomaly detector, mixing normal traffic with behavioural attack bursts (one account across many machines). Knows which events it made anomalous, so grading ground truth is free | **ran in k8s, but does not compose standalone** |

### Proven: real lab images run under the full session constraints
- [x] Built `k8s/labs/lab-soc-triage.yaml` — a 2-container Job (detector + generator) and ran it in a
      session namespace. **Both containers reached Ready**, on a worker node, under `restricted` Pod
      Security forced to **uid 10001** (both images default to root), read-only rootfs, no SA token,
      default-deny egress. Intra-pod localhost traffic worked and the detector answered `/health` 200.
      So the session template works with real labs, not just the engine standing in.
- The session namespace was later gone and the Job with it, consistent with the sweeper reaping on
  expiry — though that CronJob's logs had already rotated (history limit 1), so the *verified* sweeper
  evidence remains the earlier `sess-test01` run.

### Blocker 1 — `live-target-lab` targets the platform API, not the standalone detector
The generator hardcodes `{API_URL}/identity/score` and `{API_URL}/decision/verdicts/{id}/feedback` —
those are **platform-mounted prefixes**. The standalone `identity-anomaly:0.1` image serves `/score` and
`/health` only, so every event 404s. Options: run the full platform backend, or put a small
path-rewriting adapter in front of the detector. Not a k8s problem.

### Blocker 2 — `cloud-target-lab` needs LocalStack, which has two problems here
- [ ] **The local `localstack/localstack:3.0` image is corrupted.** Blob
      `sha256:8444ed98…3f0a` is missing, so `kind load` fails both directly and via `docker save`
      (the archive came out 0.40 GB against a reported 1.67 GB). `docker pull` reports "up to date" and
      does not repair it. A clean re-pull needs `docker rmi --force`, which is blocked by container
      `1b8df3e82a2b` from **another project** — not ours to delete.
- [ ] **LocalStack will not run as non-root**: as uid 10001 it dies with
      `TimeoutError: gave up waiting for edge server on 0.0.0.0:4566`. So a LocalStack lab needs the
      namespace relaxed from `restricted` to **`baseline`** Pod Security and LocalStack run as root.
      That is defensible for a deliberately-vulnerable target inside a namespace with no SA token,
      default-deny egress and a quota — but it must be a **conscious per-lab decision**, exactly as
      `lab_sessions_design.md` requires.

### Next
- [ ] Decide the adapter-vs-platform question for the SOC lab, or start with the cloud lab instead
- [ ] Repair the LocalStack image (needs the other project's container stopped) and add a
      `baseline`-PSS session variant for labs that need root
- [ ] A lab needs a **catalog entry** (id, image(s), PSS level, tier, ports, grading hook) so the
      provisioner can instantiate one by name rather than by hand-substituted YAML

---

## Machine state at pause — 2026-08-03 (ephemeral, NOT code)

Running when work stopped. None of this is required to resume; recreate as needed.

| what | how to restore / remove |
|---|---|
| Container `regmap-v3-test` on **:8141** — `regmap-engine:0.3-cpu`, healthy, serving `@0.2` | `docker start regmap-v3-test` · or `docker run -d -p 8141:8000 regmap-engine:0.3-cpu` |
| Local uvicorn on **:8140** (repo working tree) | `cd regmap_engine && python -m uvicorn serve:app --port 8140` |
| kind cluster **`regmap-labs`** — 3 nodes, Calico, session sweeper deployed | rebuild per `k8s/labs/kind-cluster.yaml` · remove with `kind delete cluster --name regmap-labs` |
| `kind` v0.32.0 installed at `~/bin/kind.exe` | re-download from the kubernetes-sigs release page |

Images built: `regmap-engine:0.3-cpu` (current, `@0.2` model) · `regmap-engine:0.2-cpu` (previous,
`@0.1`) · `regmap-engine:0.1` (8.72 GB, pre-catalog, **stale — do not test against it**).

### Environment gotchas that will waste time if forgotten
- **`datasets` must stay uninstalled.** pyarrow's `_dataset` DLL is blocked by an Application Control
  policy on this machine, and installing `datasets` breaks `import sentence_transformers` outright. This
  is why `train_embedder.py` implements MNRL directly instead of using either library training API.
- **Git Bash `ps` cannot see Windows python processes.** A background training run looked dead when it was
  not, and two runs competed for CPU. Use `Get-CimInstance Win32_Process` to check.
- **`Compress-Archive` silently skips hidden directories** — it produced a "backup" with no `.git` at all.
  Use `[IO.Compression.ZipFile]::CreateFromDirectory`.
- **`localstack/localstack:3.0` in the local Docker store is corrupted** (missing blob
  `sha256:8444ed98…3f0a`); a forced re-pull is blocked by a container belonging to another project.
  This blocks the `found-cloud-01` lab.

### Backup
`C:\Users\User\regmap-platform-backup_2026-08-02_2214.zip` — 167.9 MB, 343 entries, `.git` verified
inside. **Predates the retrain**, so it does not contain `models/regmap-embedder-v2/` or the documents.
Still **no git remote** — this tree plus that zip are the only copies.

---

## Phase B — billing spine · DONE 2026-08-04

Built and end-to-end verified. New modules: `billing.py` (ledger), `auth.py` (keys, scopes, rate
limits, quota gate), `compute_units.py` (the billable unit), `scripts/regmap_admin.py` (operator CLI).

### B1 Persistence — `billing.py`
- [x] SQLAlchemy Core (no ORM), dual-dialect. `DATABASE_URL` selects SQLite (dev) or Postgres (prod).
      Tables: `plans · accounts · api_keys · usage_events · usage_periods`. Plans are **rows not code**,
      so pricing changes without a deploy.
- [x] ⚠️ **Startup warns loudly on SQLite**, because `k8s/deployment.yaml` mounts **no volume** — a
      SQLite ledger lives in the container's writable layer, is destroyed on every restart/rollout, and
      is per-replica. That would silently discard the records you bill from. Verified the warning fires.

### B2 API keys
- [x] `Authorization: Bearer rk_…` or `X-API-Key`. **Only sha256 is stored** — plaintext is shown once
      at creation and is unrecoverable, so a leaked database yields no usable credential.
- [x] Scopes (`admin`), revocation, `last_used_at`. Verified: no key **401**, bogus key **401**, valid
      key **200**, revoked key **401**. Deactivating an *account* also invalidates its keys.
- [x] `REGMAP_REQUIRE_AUTH` defaults **false** so the self-hosted tier keeps working unchanged; that
      tier pays for a licence, not per request. Verified both modes, and **admin endpoints are refused
      even with auth disabled** — otherwise turning auth off would expose the operator surface.

### B4 Compute Units — deterministic *(the important correction)*
- [x] `CU = work_units(request) × device_rate`. Work units count encodes and corpus vectors scored.
      The old meter was whole-request **wall-clock**, which charged the customer for *our* queueing,
      could not be predicted, and could not be estimated before the work ran.
- [x] **Measured proof**: the same request billed **0.5500 CU** three times while wall-clock varied
      **2.4×** (0.038s → 0.092s). CU scales with corpus as designed: 60 controls → 0.55, 1,016 → 1.028.
- [x] Wall-clock is still recorded per event, but as **cost-of-goods telemetry**, never the billed figure.
- [x] `GET /pricing` publishes the formula and worked examples. A metered API that will not state its
      cost function cannot be budgeted against.

### B3 Attributed metering
- [x] Every billable request writes an immutable `usage_events` row **and** bumps `usage_periods` in one
      transaction. Events are the source of truth; the counter makes quota checks a single indexed read.
- [x] `POST /admin/reconcile` rebuilds a counter from the events. **Verified**: corrupted a counter to
      99,999 CU and rebuilt it to the correct 4.9520.
- [x] A ledger write failure logs `BILLING-ERROR` and sets `x-regmap-billing: record-failed` — unbilled
      usage is lost revenue, not a cosmetic problem.
- [x] `GET /me` gives a customer their own plan, usage and remaining allowance, from the same rows an
      invoice would cite. `key_hash` is never exposed.

### B5 Quotas
- [x] Checked from an **estimate before the work runs**, so an out-of-allowance caller cannot consume
      GPU and then be told no. **402** (not 403 — authenticated and permitted, simply owes money).
- [x] Verified: free account at 299.9/300 CU → **402**, and the rejected call **consumed nothing**.
      A pro account at 4999.9/5000 with overage enabled → **200**.
- [x] `/map/bulk` gates on the worst case before looping, then bills only the controls that actually
      reached the encoder — charging model rates for a crosswalk dictionary hit would overbill.

### B6 Hardening
- [x] Rate limits per key per endpoint: `/map` 120/min, `/map/bulk` 10/min, `/eval` 4/min. Verified
      **429 with `Retry-After: 59`** on the 5th `/eval` call.
- [x] `/eval` bounded by `REGMAP_EVAL_MAX_QUERIES` (200) → **413** with a pointer to the offline harness.
- [x] ⚠️ **The limiter is per process.** With N replicas a caller gets N× the limit and restarts forget
      all state. Honest protection against a runaway script; real multi-tenant limiting needs Redis.

### B7 Admin gating
- [x] **`/health` split, not gated** — all three k8s probes target it, so requiring a credential would
      leave every pod unready. Public `/health` now returns `{"status":"ok"}` **only**; the model
      filesystem path, device and framework list moved to `/health/detail` behind `admin`.
- [x] `/docs`, `/openapi.json` disabled at construction and re-served behind `admin` (401 unauth,
      200 with an admin key). `/usage` → admin. New `/admin/accounts`, `/admin/accounts/{id}`,
      `/admin/reconcile`.

### NOT done — and deliberately not faked
- [ ] **No payment capture.** The ledger computes what is owed including overage, but nothing charges a
      card. Stripe needs a real account and keys; scaffolding an untested webhook would be worse than
      leaving it absent. **This is Phase C.**
- [ ] No self-serve signup — accounts are created by the operator CLI on purpose, since a public route
      that mints credentials is an abuse surface until payment and email verification exist.
- [ ] Postgres is untested here (no server available); only the SQLite path has been exercised.
- [ ] The image has not been rebuilt with the billing deps yet.

**NEXT ACTION — Phase C: payments.** Stripe subscriptions plus usage records for overage, webhooks →
`subscriptions`, self-serve signup, and a usage dashboard. Needs your Stripe account. Also outstanding
and cheap: a LICENSE file, and a README refresh.

---

## Production-grade verification on SQLite — 2026-08-04

Decision: stay on SQLite for now; Postgres when real users arrive. That is workable, but only because
the ledger was made **durable** — an ephemeral billing database makes any billing test meaningless.

### What changed to make SQLite viable
- [x] **Dockerfile**: `/data` created and chowned to uid 10001, declared as `VOLUME`, and
      `DATABASE_URL` defaults to `sqlite:////data/regmap.db`. The runtime user is non-root against a
      root-owned `/app`, so the ledger could not have lived there; and without the volume it would sit
      in the container's writable layer and vanish on every restart.
- [x] **`k8s/pvc.yaml`** (new): 1Gi ReadWriteOnce claim, mounted at `/data`.
- [x] **`deployment.yaml` pinned to `replicas: 1`** with the reason inline. SQLite is single-writer and
      the PVC is ReadWriteOnce, so a second replica either fails to schedule or splits the ledger.
- [x] **HPA removed from `kustomization.yaml`** and the file itself carries a DO-NOT-APPLY warning.
      Autoscaling with a SQLite ledger would silently corrupt billing — this was live in the
      kustomization and would have been applied.
- [x] **`scripts/regmap_admin.py` now ships in the image** (`.dockerignore` excluded `scripts/`), since
      accounts and keys are provisioned by an operator inside the running container.
- [x] Rebuilt as **`regmap-engine:0.4-cpu`**.

### `scripts/smoke_test.sh` — 40/40 passing
Black-box over HTTP against the deployed container, so it tests what a customer hits. Creates its own
volume and account, and removes both on exit.

| group | covered |
|---|---|
| auth | no key 401 · bogus 401 · valid 200 · `X-API-Key` also accepted · revoked 401 |
| public surface | `/health` 200 and body is exactly `{"status":"ok"}` · `/pricing` · `/frameworks` |
| admin gating | `/health/detail` 403→200 · `/docs` 401→200 · `/usage` 403 · `/admin/accounts` 403→200 |
| **billing determinism** | same request billed **0.5500 CU three times**; scales 0.5500 (60 ctl) → 1.0280 (1016 ctl); correct account on the charge |
| ledger | `/me` usage moves 4.878 → 5.428 CU; `key_hash` never exposed |
| quota | over-quota **402**, and the rejected request **consumed nothing** (still 299.9 CU) |
| rate limit | `/eval` **429** after 4/min with `Retry-After` |
| **durability** | ledger identical across a container restart; key still valid afterwards |
| reconciliation | counter corrupted to 99,999 CU, rebuilt to 61.15 from the event log |
| product | all six pages 200 · exercise sets · bulk gap analysis runs |

### Kubernetes — deployed and verified on kind
- [x] `kubectl apply -k regmap_engine/k8s` → namespace, PVC **Bound**, Service, NetworkPolicy,
      Deployment rolled out on `regmap-labs-worker`.
- [x] Account provisioned in-cluster, driven through the **Service** via port-forward, 5 requests
      recorded (2.75 CU).
- [x] **Ledger survived pod replacement**: deleted the pod, k8s rescheduled it, and the new pod read
      back `2.75|5` unchanged from the PVC. That is the property that makes SQLite acceptable for now.

### Environment gotchas found (cost real time)
- **Git Bash rewrites POSIX paths.** `docker exec … /app/scripts/x.py` arrived as
  `C:/Program Files/Git/app/scripts/x.py`. `MSYS_NO_PATHCONV=1` and `MSYS2_ARG_CONV_EXCL='*'` are now
  set at the top of `smoke_test.sh`.
- **Long `&&` chains hide failures in tests.** A broken chain made a passing durability check report
  `LEDGER LOST DATA` when the data was intact. Rewritten with explicit variables.
- **`kubectl` context drifts.** Docker Desktop's own Kubernetes became the active context after a
  restart, so `kubectl` was talking to an 8-node desktop cluster rather than kind. Check
  `kubectl config current-context` before believing cluster output.

### Still not covered
- [ ] **Postgres** — untested by design for now; multi-replica and HPA stay disabled until then.
- [ ] **Payment capture** — the ledger computes what is owed; nothing charges a card (Phase C).
- [ ] GPU tier, KEDA scale-to-zero, multi-replica behaviour.

---

## Accounts: registration, login, guest browsing — DONE 2026-08-04

Requirement: registration and login, guests can audit the site, and paywalled items need only a login
for now (not payment).

### The gap this closed
`api.js` sent **no credential at all**. With `REGMAP_REQUIRE_AUTH=true` the pages loaded but every
billable call 401'd, so the paywall worked for curl and broke the website. The product was only usable
in open mode.

### Built
- [x] **Passwords** — `hashlib.scrypt` (stdlib, memory-hard), per-user salt, stored as
      `scrypt$n$r$p$salt$hash`. Never the password itself. `verify_password` reads the stored cost
      factors, so they can be raised later without invalidating existing hashes.
- [x] **Sessions** — a `sessions` table holding **sha256 of an opaque random token**, not signed claims.
      Chosen so logout and revocation are immediate: deleting the row ends the session, whereas a signed
      cookie cannot be un-issued.
- [x] **HttpOnly cookie** (`SameSite=Lax`, `Secure` via `REGMAP_SECURE_COOKIES`). Script cannot read it,
      so an XSS bug cannot exfiltrate a login — which is exactly why the session is a cookie and not a
      token in localStorage.
- [x] **`auth.resolve()`** accepts an API key **or** a session cookie and returns the same principal
      shape, so quota, metering and scope checks never care which was used. An explicit key wins over an
      ambient cookie.
- [x] Endpoints: `/auth/register`, `/auth/login`, `/auth/logout`, `/auth/session`, `/auth/keys`.
      `/auth/session` **never 401s** — a guest is a valid answer, and the nav calls it on every page.
- [x] **`web/account.html`** — sign in / register side by side when signed out; plan, allowance,
      remaining CU, usage-by-endpoint, API keys and sign-out when signed in.
- [x] Session state in the header on every page (remaining CU, or a Sign in button).
- [x] `api.js` sends `credentials: "same-origin"` and turns 401/402/403/429/413 into sentences a user
      can act on instead of a bare status code.

### Verified end to end (container, auth enforced, :8400)
| | |
|---|---|
| guest browses `/frameworks`, `/pairs`, `/pricing`, all pages | **200** |
| guest hits `POST /map` | **401** |
| weak password / bad email / duplicate email | **422 / 400 / 400** |
| registration → session cookie | **200**, `HttpOnly` confirmed |
| signed in: `/map`, `/exercise`, `/map/bulk` | **200** |
| signed in: `/admin/accounts`, `/docs` | **403** — login is not admin |
| logout, then `/map` | **200 → 401** (session deleted server-side) |
| wrong password vs unknown email | both **401**, *identical* message — no account enumeration |
| self-issued API key on `/map` | **200** |
| self-issued API key on `/admin/accounts` | **403** — a user cannot self-elevate |

### Deliberate boundaries
- **Login grants access, not admin.** `verify_session` hard-codes empty scopes, so admin is API-key-only
  and issued by the operator CLI. Otherwise anyone who registered could reach the operator surface.
- **`/auth/keys` cannot mint an admin key** for the same reason.
- Registration lands on the **free plan (300 CU)**, so a new user is metered from the first request —
  there is no unmetered path into the system.

- [ ] Not done: email verification, password reset, and payment capture. A registered user is
      authenticated, not paid — which matches the current requirement but must change before charging.
