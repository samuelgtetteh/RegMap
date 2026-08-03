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

## ⚠️ Set this up first: version control

**There is no git repository here, and none in the parent directory.** No history, no diffs, no rollback,
no way to see what a session changed. For a build meant to pause and resume, this is the single biggest
risk — a bad edit is unrecoverable.

- [ ] `git init` + first commit of the current tree (`.gitignore` already exists and is sane)
- [ ] Decide remote (the old parent repo pushed to `origin/main`; this folder is a detached copy)
- [ ] Commit at the end of every session, so the log below and the history agree

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
- [ ] **Replace the `SAMPLE` CSF↔800-53 pair** — `crosswalks/nist_csf2__nist_80053/` is 12 controls and
      self-labelled SAMPLE in its `meta.json`. Needs the CSF 2.0 OLIR export **downloaded** first
      (https://csrc.nist.gov/projects/olir) — not on disk, unlike the HIPAA CSV
- [ ] **Add ISO 27001 ↔ 800-53** via OLIR (Phase 0 target in `product_roadmap.md` is 2–3 live pairs)
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

**Next action — first student exercise (`web/learn.html`).** Everything needed already exists: pick a
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
