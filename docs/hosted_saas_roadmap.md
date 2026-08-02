# Hosted SaaS — metered compute: architecture & roadmap

**Decision (2026-08-02):** ship as a **hosted, multi-tenant SaaS on managed Kubernetes (AWS EKS or Azure
AKS)** where users pay for **metered compute**. Two billable products on one meter:

1. **Crosswalk API + UI** — `regmap_engine/serve.py` (`/map`, `/eval`) as a metered service.
2. **Practice environments** — on demand, a user spins up an **isolated K8s environment** to practise
   defensive cyber-security skills (the Pillar B labs), billed for the hardware it consumes while alive.

This supersedes the "sell the container / self-host" framing for the near term. The model will be tuned as
we go. Related: `product_master_plan.md` (§4 architecture, §7 pricing), `product_roadmap.md` (Phase 1 · F),
`regmap_engine_deploy_status.md` (what's built), `build_log.md` (**the resume file — start there**).

---

## Audiences — one product, two buyers (restated 2026-08-02)

The goal is **every compliance framework in one place**, used by:

- **GRC / IT / audit teams** — do the actual work: map a control set across frameworks, score coverage,
  find gaps, export evidence. They pay for breadth, provenance, and time saved.
- **Students / career-changers** — learn the skills that make them job-ready on day one: what controls
  exist, how frameworks relate, how to run an audit and a gap analysis. They pay (or a university pays)
  for guided practice with real artefacts.

These are not two products. They are the same catalog and the same engine with different surfaces, and the
overlap is the cheap part: **the official mappings are simultaneously the product's answer key and the
students' grading ground truth.** 222 official 800-53↔HIPAA mappings exist today, so an auto-graded
"map this control" exercise needs no new labelling effort — the hardest part of a training product
(per `product_master_plan.md` §3.2, the moat) is already paid for by the compliance content.

Design consequence: build the **catalog and the mapping API once**, then two thin surfaces on top —
a *work* surface (bulk, gap reports, export) and a *learn* surface (browse, exercise, score).

---

## Breadth architecture — why this is hub-and-spoke, not pairs

"All compliance in one place" is impossible on a pair-per-directory model, and this was verified, not
assumed: NIST 800-53 existed in two pair directories with 22 overlapping control ids and **all 22 had
different text**. The catalog had already drifted at two pairs. At 20 frameworks that is up to 190
directories and 20 conflicting copies of 800-53 — the same control answering differently depending on
which mapping you arrived through, which inverts the auditability the product sells.

Implemented 2026-08-02 (`regmap_engine/catalog.py`, migrated by `migrate_to_catalog.py`):

```
catalog/frameworks.json                 registry — id, name, family, version, access, hub
catalog/frameworks/<fid>/controls.jsonl  control text ONCE per framework
catalog/mappings/<a>__<b>.jsonl          id-only mappings + provenance
```

A pair resolves in precedence order: **direct** → **inverted** (one official export serves both
directions) → **derived via hub** (X→H→Y; 800-53 and CSF 2.0 are flagged `hub: true`). Derived mappings
are tagged `provenance:"derived"` and never shown as authoritative.

Measured payoff: **2 mappings on disk answer 6 framework pairs.** Breadth stops being O(N²) — import one
official mapping onto a hub and every framework already on that hub becomes reachable for free. This is
`product_master_plan.md` §2.3's "use SCF/OLIR as the mapping hub so pairs compose," made concrete.

### The licensing wall is a product feature, not an afterthought
"All frameworks" is legally bounded, so the registry carries an `access` gate per framework:

| `access` | Meaning | Frameworks |
|---|---|---|
| `public` | Ship content freely | NIST 800-53 · CSF 2.0 · 800-171 · HIPAA · GDPR · FedRAMP · CMMC |
| `paraphrase-only` | Map **IDs + own paraphrase**, never verbatim text | ISO 27001 · PCI DSS 4.0 · SOC 2 · CIS v8 |
| `licence-required` | **Blocked until licensed** | HITRUST CSF · COBIT |

Enforce this at the API boundary alongside the Phase B auth work, so a tenant without a HITRUST licence
cannot retrieve HITRUST content. Frameworks with an empty catalog report `controls: 0` so the UI shows
"coming soon" rather than silently promising coverage it lacks.

---

## Why this doc exists

`product_master_plan.md` §7 states metering is already "enabled" by `serve.py`. **It is not.** The engine
meters *the machine*, not *the customer*. A sweep of the tree for payment / persistence / tenant / account
code returns only comments and marketing copy. There is no database, no API key, no account model. The
roadmap therefore had a hole exactly at the revenue step; this doc closes it.

---

## The gap, precisely (verified against the code 2026-08-02)

| # | Gap | Evidence |
|---|-----|----------|
| 1 | **No authentication** — anyone reaching the port gets unlimited model use | no auth of any kind in `serve.py` |
| 2 | **Meter can't attribute compute to a payer** — `METER` events carry no account id | `serve.py:92-94` |
| 3 | **`/usage` is unbillable** — in-memory, per-replica, lost on restart, nothing aggregates across pods | `serve.py:44`; `k8s/hpa.yaml:15-16` scales 1→5 |
| 4 | **CU is not a defensible invoice line** — it is whole-request wall-clock, so it includes queueing; identical work bills differently under load, and the 8× GPU multiplier scales that noise too | `serve.py:79-84` |
| 5 | **Quotas unenforceable** — §7 sells CU allowances; the middleware only observes. No limit check, no period boundary, no reset, no way to reject | `serve.py:77-95` |
| 6 | **`/eval` is an open denial-of-wallet endpoint** — encodes every source item against the full corpus, plus TF-IDF and BM25 over everything, unauthenticated | `serve.py:194`, `serve.py:199-202` |
| 7 | **Nothing to sell access to** — no signup, plans, dashboard, or payments; the UI is a brochure with hardcoded scores over one 12-control sample pair | `web/index.html:31-36`, `crosswalks/*/meta.json` |

**Already done and reusable:** container + GHCR image, digest-pinned manifests, HPA/NetworkPolicy,
CPU/GPU auto-detect, version stamping on every response, the fine-tuned embedder, the pair format and
eval harness. The hard infrastructure exists — it just sits under a service that cannot tell two users apart.

---

## Target architecture (AWS / Azure)

```
   users ──► ingress + TLS ──► control plane (new)          ──► Postgres (RDS / Azure Database)
                               · accounts, API keys              accounts · api_keys · plans
                               · quota check (pre-request)       usage_events · usage_periods
                               · Stripe subscriptions            subscriptions
                               · usage dashboard
                                     │
                    ┌────────────────┴─────────────────┐
                    ▼                                  ▼
            regmap-engine (metered)            session provisioner
            EKS/AKS · HPA · GPU pool           namespace-per-session
            /map /eval                         Deployment+Svc+NetPol+Quota+TTL
                    │                                  │
                    └──────────► usage events ◄────────┘
                        app-level CU  +  infra seconds
                        (Prometheus / DCGM per namespace)
```

- **Control plane is new code** and is the keystone: identity, quota, payment, dashboard.
- **Namespace-per-session** gives both isolation and the billing dimension (infra metering per namespace).
- **Managed Postgres** — the service currently has *zero* persistence; this is the first dependency to add.
- **GPU node pool** with scale-to-zero (KEDA manifests exist, unwired) so idle GPU costs nothing.

---

## Compute Units, redefined (design fix for gap #4)

Wall-clock billing is not defensible: the customer pays more when *we* are oversubscribed. Replace it.

> **CU = work_units × device_rate**, where `work_units` is a **deterministic** function of the request and
> `device_rate` reflects the hardware tier (CPU 1×, GPU `REGMAP_GPU_CU_MULT`).

- `/map` → `work_units = f(top_k, corpus_size)`; `/eval` → `f(n_queries × corpus_size)`.
- **Reproducible:** the same request always costs the same, so a customer can predict and audit the bill,
  and we can publish a price per call. Version-stamped responses already support the audit story.
- **Separately**, keep measuring true hardware seconds (instrumented around the `encode` calls only, *not*
  the whole request) as **cost-of-goods telemetry** for margin analysis — not as the invoice line.
- Reconcile app-level CU against infra seconds (Prometheus + DCGM per namespace) to catch drift.

---

## Phases

### Phase A — Foundation (unblocks everything; needed under any pricing model)
- **Real crosswalk content.** Build the authoritative 800-53↔HIPAA pair from
  `data/raw/nist_800_53_rev5_hipaa_crosswalk_full.csv` via `import_olir.py` (222 official pairs, 133
  controls, `provenance:"official"`) — no download required. Then CSF 2.0 and ISO 27001 via NIST OLIR.
  *Today there is one pair, self-labelled `SAMPLE`, 12 controls.*
- **A UI that actually calls the engine.** Replace the hardcoded result block in `web/index.html` with a
  real query → `POST /map` → ranked results with scores and provenance badges.
- **Stop advertising uncovered frameworks** in `web/index.html` until pairs exist behind them.

### Phase B — Billing spine (makes "paid access" possible at all)
1. **Persistence** — Postgres + migrations; schema per the diagram above.
2. **API keys** — `Authorization: Bearer rk_…`, hashed at rest, per-account, revocable. Gate `/map` and
   `/eval`; leave `/health` open for liveness probes.
3. **Attributed metering** — resolve key → `account_id`; stamp it on every `METER` event and persist a
   `usage_events` row. Roll up into `usage_periods` (monthly). Retire in-memory `_usage` as a billing source.
4. **CU redesign** — implement the deterministic unit above.
5. **Quota enforcement** — pre-request check of period usage vs plan allowance; `402` or metered overage
   per plan. Period boundaries and resets.
6. **Harden `/eval`** — authenticated, rate-limited, and bounded (cap corpus × queries per call).

### Phase C — Payments & self-service
- Stripe: subscriptions for plan/seats + usage records for metered overage; webhooks → `subscriptions`.
- Signup, login, key management, and a **usage dashboard** (CU consumed vs allowance, invoice history).
- Publish the price per call now that CU is deterministic.

### Phase D — Practice environments (the paid draw)
- **Recover or rebuild `provisioner/`.** `regmap_engine_deploy_status.md` describes it as verified
  end-to-end (namespace + Deployment + Service + NetworkPolicy + ResourceQuota + TTL reaper, plus a
  session UI), but **it is not in this repo** — only referenced. It is the keystone of the paid product as
  described. Its `rbac.yaml`, in-cluster `deployment.yaml`, and `README.md` were never created.
- Wire "Start session" behind the control plane's auth + quota, so a session is billable before it starts.
- Real lab workloads (currently the sample engine image stands in for a lab target).
- Per-namespace infra metering → reconcile to CU.

### Phase E — Cloud productionisation
- EKS or AKS (pick one — see open decisions); managed Postgres; ingress + TLS; secrets management.
- Registry: the image is currently a **private GHCR** package; decide GHCR-with-pull-secret vs ECR/ACR.
- GPU node pool + KEDA scale-to-zero (manifests exist, untested — needs real GPU hardware).
- Hardening carried over from `regmap_engine_deploy_status.md` §6: pin dependency versions (currently
  ranges), digest-pin the base image (currently floating `python:3.11-slim`), SBOM, image signing,
  multi-arch.

---

## Dependencies & blockers

- **`provisioner/` is absent from this repo** — Phase D cannot start until it is recovered from the parent
  repo or rebuilt. Everything in `deploy_status.md` about it is unverifiable from here.
- **`auth_service/` is absent too.** The master plan §4 assumes it provides identity; standalone, the
  control plane must own auth. Decide whether to recover it or build fresh (recommend: build fresh, scoped
  to API keys + accounts, rather than inherit a half-finished service).
- **Multi-tenant isolation** is the main new engineering, as §8 already warns.
- **HITRUST CSF and COBIT need licences** before their control content ships (§8). NIST/gov content is
  public domain and usable now — Phase A is entirely in the clear.
- **GPU tier needs real hardware** to test; not reproducible on Docker Desktop.

## Open decisions
1. **AWS (EKS) or Azure (AKS)?** Drives registry, managed Postgres, GPU instance types, and IaC.
2. **Free tier?** §7 offers Student free at 300 CU/mo — decide whether unauthenticated/free access exists
   at all, given gap #6 makes free GPU access a cost risk.
3. **Session pricing:** per-second while alive, or a flat price per session with a TTL cap?
4. **Crosswalk API vs practice environments — which ships paid first?** They share Phases B and C but
   diverge at D.

---

## Status

- **2026-08-02** — this doc created; hosted-SaaS + metered-CU model chosen. Product target restated as
  **all frameworks, two audiences (GRC teams + students)**; paper deprioritised.
  Phase A started: official 800-53↔HIPAA pair imported (222 mappings), and the data model migrated from
  pairs to the **hub-and-spoke catalog** above (lossless — direct pair reproduces pre-migration metrics
  exactly). 13 frameworks registered with licence gating; 6 answerable pairs from 2 mappings.
  **Live task list and resume pointer: `docs/build_log.md`.**
