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
| Python | works (`python` on PATH) |
| `scikit-learn` / TF-IDF path | ✅ working — eval runs |
| `sentence-transformers` + `torch` | ❌ **not installed** — engine falls back to TF-IDF locally |
| `rank_bm25` | ❌ not installed (also missing from `docker/requirements.txt`) |
| `venv/` | ❌ absent — docs reference `venv\Scripts\python.exe` from the parent repo |
| Model weights | ✅ present on disk (`models/regmap-embedder/model.safetensors`) |

- [ ] Create `venv` + install `regmap_engine/docker/requirements.txt` **plus torch** (multi-GB download;
      needed to run the fine-tuned embedder locally instead of the TF-IDF fallback)
- [ ] Add `rank_bm25` to `docker/requirements.txt` (the BM25 baseline `eval_crosswalk.py` advertises
      cannot run in the container without it)

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
- [ ] **Re-run the eval with the embedder** once torch is installed, to confirm the model beats TF-IDF on
      this pair as served (not just in the paper's held-out protocol)
- [ ] **Replace the `SAMPLE` CSF↔800-53 pair** — `crosswalks/nist_csf2__nist_80053/` is 12 controls and
      self-labelled SAMPLE in its `meta.json`. Needs the CSF 2.0 OLIR export **downloaded** first
      (https://csrc.nist.gov/projects/olir) — not on disk, unlike the HIPAA CSV
- [ ] **Add ISO 27001 ↔ 800-53** via OLIR (Phase 0 target in `product_roadmap.md` is 2–3 live pairs)
- [ ] **UI that actually calls the engine** — `web/index.html:31-36` is a hardcoded fake result block
      (invented scores IA-5 0.88 / IA-2 0.74 / AC-17 0.61). Replace with a real query box →
      `POST /map` → ranked results + score + provenance badge. **This is what turns the brochure into a demo.**
- [ ] **Stop advertising uncovered frameworks** — `web/index.html:59-61` lists ~20 frameworks; back them
      with real pairs or gate them as "coming soon"
- [ ] Serve a per-pair provenance/coverage indicator in the UI (the auditability selling point) —
      `as_pair()` already returns `route` and `provenance` per pair, so the data is there
- [ ] **Point `serve.py` at the catalog** instead of `crosswalks/` — swap `load_pair` for
      `catalog.as_pair`, add `GET /frameworks` (registry + coverage) and make `/pairs` report
      `reachable_pairs()`. This is what lets the UI offer a real *any framework → any framework* picker
- [ ] Retire `crosswalks/` once `serve.py` reads the catalog (keep until then; it is the migration source)

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

**Next action:** `git init` + first commit — there is now real work worth protecting.

**Then, in order:**
1. **Point `serve.py` at the catalog** (`catalog.as_pair`, `GET /frameworks`, `/pairs` →
   `reachable_pairs()`). Small change, and it is what makes an any→any framework picker possible.
2. **The real UI** — replace the hardcoded fake result block at `web/index.html:31-36` with a live
   framework picker → `POST /map` → ranked results + score + provenance/route badge. Turns the brochure
   into a demo for both audiences.
3. **First student exercise** — "map this control", auto-graded against the 222 official mappings that
   already exist. No new labelling needed.
4. Then Phase B (persistence → API keys → attributed metering → CU redesign → quotas).

**Cheap breadth win when ready:** import any framework's official mapping *to 800-53 or CSF 2.0* (both
flagged `hub: true`) and every framework already on that hub becomes reachable for free.

**Blocked / needs input:** EKS vs AKS · whether a free tier exists at all · CSF 2.0 and ISO 27001 need
OLIR exports **downloaded** (not on disk) · HITRUST + COBIT need licences before their content ships ·
`provisioner/` must be recovered from the parent repo for Phase D (practice environments).
