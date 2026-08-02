# Master product roadmap — everything, phased

The single, comprehensive roadmap tying every workstream together: the **product** (learn-by-doing +
all-frameworks compliance engine), the **RegMap** expansion tiers, the **detection platform**, the
**research papers**, and **business/infra**. Detail lives in companion docs; this is the timeline and
the critical path. (The older `docs/roadmap.md` is the historical portfolio/evaluation plan — mostly
complete; this file supersedes it for the product phase.)

**Companion docs:** `docs/product_master_plan.md` (product), `docs/regmap_expansion_plan.md` (RegMap),
`docs/future_papers.md` (papers), `docs/development_roadmap.md` (platform),
**`docs/hosted_saas_roadmap.md`** (how paid access actually gets built — see note below).

> **2026-08-02 — delivery model decided: hosted multi-tenant SaaS on managed K8s (EKS/AKS) with metered
> compute.** Users pay for the crosswalk API *and* for isolated K8s environments they spin up to practise
> cyber-security skills. This does not change the phases below, but it adds a **billing spine** they assume
> exists and that does not: there is no auth, no persistence, no per-customer usage attribution, and no
> payments anywhere in the codebase. Phase 1 · F ("per-request metering → usage-based billing") is
> therefore larger than one bullet implies. See **`docs/hosted_saas_roadmap.md`** for the verified gap list,
> the target architecture, and Phases A–E.
**Memory:** [[platform-build-status]], [[assess-console-redesign]], [[future-papers-pipeline]],
[[regmap-paper-status]], [[papers-submission-status]].

---

## North Star
One platform where you **learn the defensive cyber roles hands-on** and **map/audit/prove compliance
across every major framework** — real tools, real ground truth, auto-graded, AI-assisted.

## The five workstreams
- **A · Product / Learning** — tracks, labs, auto-grading, accounts, classroom, certs.
- **B · Compliance Engine (RegMap)** — all frameworks, crosswalks, gap analysis, evidence.
- **C · Detection Platform** — the Assess/Monitor/Compliance console, scanning, decisioning, labs.
- **D · Research / Papers** — P1–P8 (`docs/future_papers.md`).
- **E · Business / Infra** — auth, isolation, deploy, pricing, go-to-market.

---

## Phase 0 — Foundation & MVP  (≈ weeks 1–4)  → *ship a free student beta*
**Goal:** a launchable slice that proves the loop: learn → do → auto-graded → score.
- **A:** content model (tracks→lessons→labs schema); **3 auto-graded labs** (SOC triage · vuln
  prioritization · one compliance/audit lab); progress dashboard + first badge.
- **B:** RegMap live for **2–3 pairs** (NIST 800-53↔HIPAA already; add NIST CSF↔800-53, ISO 27001↔800-53
  via NIST **OLIR**). Mapping **provenance tags** (official / model / human-verified). Engine ships as a
  **standalone container** — `regmap_engine/serve.py` API + `regmap_engine/docker/`; deploy artifact is the
  prebuilt image tarball (`docker/save-image.*` → `dist/regmap-engine-0.1.tar`, no internet on host). See
  `regmap_engine/docker/SHIP.md`.
- **C:** console stable as the learner workbench; labs (live + cloud) wired as sandbox + grader source.
- **D:** submit **P1** (honest-evaluation methodology → CSET) — fast, no new experiments.
- **E:** finish `auth_service/` (student/instructor roles); landing page + signup; deploy (cloud or
  Proxmox beta); **shared sandbox + per-user scoring** (isolation deferred).
- **Exit:** students sign up, complete 3 graded labs, see scores; RegMap maps ≥3 frameworks.

## Phase 1 — Depth & Classroom  (≈ weeks 5–12)  → *usable in a course*
- **A:** 10–15 labs; **certificates**; **instructor / classroom mode** (assign labs, track a cohort,
  gradebook).
- **B (RegMap Tier 1–2):** scale to **~8–10 frameworks** via the **SCF/OLIR hub** so pairs compose
  (X→hub→Y); add **cross-encoder reranking** + larger/LLM embedder baselines; ship the **multi-pair
  benchmark + leaderboard**.
- **C:** deep-scan + exploit-aware prioritization polished; agent/import hardened; report exports.
- **D:** write **P3** (multi-framework crosswalk benchmark) and **P4** (unified-platform practice paper).
- **E:** basic **teams/orgs**; usage analytics; pricing page; first paid pilots (university dept / SOC team).
- **F · Infra:** move services to **Kubernetes** (`regmap_engine/k8s/` is the first, testable on Docker
  Desktop K8s): HPA for the CPU tier, **KEDA scale-to-zero** for the GPU tier (idle GPU = $0), per-request
  metering (`/usage`, `x-regmap-compute-units`) reconciled to infra metering (Prometheus/DCGM per
  namespace) → **usage-based billing**. Namespace-per-tenant isolation; same manifests on k3s = on-prem tier.
- **Exit:** an instructor runs a real cohort; RegMap covers common frameworks; benchmark public.

## Phase 2 — Scale & Monetize  (≈ months 4–6)  → *paid product*
- **A:** role certifications; leaderboards; skill assessments; a lab template so new labs are cheap.
- **B (RegMap Tier 2–3):** **full framework catalog** (see below); **bidirectional / many-to-many**
  mapping; **calibration + abstention**; **gap-analysis** reports; **RIRAG** evidence generation
  (control-implementation text with citations).
- **C:** **per-user isolated sandboxes** (ephemeral Docker/LXC) — the main new engineering; real cloud
  providers (Azure/GCP) for audit labs.
- **D:** P5 (target-labs reproducibility); start Tier-C empirical papers (P6 SWaT, P8 KEV/EPSS).
- **E:** self-serve billing; team/enterprise tiers; **GRC/audit teams** as a second buyer for the
  compliance engine (standalone); partnerships (universities, bootcamps).
- **Exit:** paying individuals + ≥1 org/university contract; isolation live; catalog complete.

## Phase 3 — Intelligence & Continuous Compliance  (≈ months 6–12)
- **A:** adaptive **AI tutor** (own models) — hints, explanations, auto-feedback; personalized paths.
- **B (RegMap Tier 3–4):** **continuous compliance** (map only the *deltas* on framework revisions);
  **versioned crosswalks**; human-in-the-loop verification UI; public **API**.
- **C:** real-telemetry collectors (SOC track on real logs — ties to **P7** Azure/CloudTrail); OT-passive.
- **D:** P2 perspective; P7 real-log identity; P6/P8 as data lands.
- **E:** scale GTM; recognized certs; marketplace of community-authored labs.

---

## Framework coverage rollout (workstream B)
1. **Have:** NIST 800-53 → HIPAA.
2. **Phase 0:** + NIST CSF 2.0, ISO 27001 (official NIST **OLIR** mappings).
3. **Phase 1:** + PCI DSS 4.0, SOC 2, CIS Controls v8, NIST 800-171 / CMMC (via SCF/OLIR hub).
4. **Phase 2:** + GDPR, FedRAMP, HITRUST, GLBA/NYDFS, ISO 27017/18/27701, COBIT — full catalog.
5. **Phase 3:** sector (NERC CIP, TISAX), EU cloud (EUCS/C5/ENS), continuous/versioned crosswalks.
> Map **control IDs + paraphrased intent**, never copyrighted framework text; lean on OLIR/SCF for
> redistributable mappings; every mapping carries a **provenance tag**.

## Critical path & dependencies
- **Auth (E)** → gates everything user-facing (Phase 0 blocker).
- **Auto-grader + content model (A)** → gates all labs; build once, reuse.
- **SCF/OLIR hub (B)** → unlocks many framework pairs cheaply (Phase 1).
- **Per-user isolation (C/E)** → gates true scale/monetization (Phase 2); ship shared+scored first.
- **RIRAG / evidence (B)** → the compliance engine's enterprise value (Phase 2–3).

## Success metrics (per phase)
- **P0:** beta signups; % completing ≥1 graded lab; ≥3 frameworks live.
- **P1:** cohorts run; labs completed; benchmark stars/cites; first pilots.
- **P2:** paying users + org contracts; frameworks in catalog; isolation uptime.
- **P3:** retention; certs issued; API/GRC customers; continuous-compliance deployments.

## Immediate next actions
1. **Auth** (finish `auth_service/`) + landing page.
2. **Learning layer:** content schema + auto-grader (reads lab ground truth) + **1 graded lab**.
3. **RegMap Tier 1:** OLIR/SCF data format + eval harness + first new pair (ISO 27001 ↔ NIST 800-53).
4. **P1** submission (parallel, low effort).
