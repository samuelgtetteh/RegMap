# Product master plan — unified compliance + hands-on cyber training platform

Single source of truth for turning this work into a shippable product. Two pillars on one platform:
1. **RegMap Compliance Engine** — automated crosswalking / gap analysis across *all* major frameworks.
2. **Learn-by-doing training** — students and analysts learn defensive cyber roles (SOC, vuln mgmt,
   audit, compliance) by *doing* them against safe, auto-graded targets.
Both run on the assets already built (the Assess/Monitor/Compliance console, the target labs, the
released models). Related: [[assess-console-redesign]], [[future-papers-pipeline]], [[platform-build-status]],
`docs/regmap_expansion_plan.md`, `docs/future_papers.md`.

---

## 1. Vision & positioning
A browser-based platform where you can (i) **map, audit, and prove compliance** across any framework,
and (ii) **learn the defensive cyber roles hands-on** with auto-graded labs. Wedge: the under-served
**defense + audit + compliance** side (competitors lean offensive/pentest) with **real ground-truth
auto-grading** and **multi-framework compliance** built in.

---

## 2. Pillar A — RegMap Compliance Engine: cover ALL known frameworks
Goal: given any control/requirement in framework X, retrieve the equivalent provisions in framework Y,
score coverage, and surface gaps — for **every framework a security/GRC team actually faces**.

### 2.1 Framework coverage (target catalog)
- **US federal/gov:** NIST SP 800-53, NIST SP 800-171, NIST CSF 2.0, FedRAMP, CMMC 2.0, FISMA, CJIS, IRS 1075.
- **Healthcare:** HIPAA Security Rule, HITRUST CSF, HITECH.
- **Payments/finance:** PCI DSS 4.0, SOX ITGC, GLBA, NYDFS 500.
- **Privacy:** GDPR, CCPA/CPRA, ISO 27701, LGPD, PIPEDA.
- **International/general:** ISO/IEC 27001 & 27002, ISO 27017/27018, SOC 2 (Trust Services Criteria),
  CIS Controls v8, COBIT.
- **Cloud / EU:** ENISA EUCS, BSI C5, ENS, SecNumCloud, UK Cyber Essentials.
- **Sector:** NERC CIP (energy), TISAX (automotive), FDA medical-device guidance.

### 2.2 Ground-truth strategy (so mappings are trustworthy, not hallucinated)
- **Prefer official mappings** as ground truth: **NIST OLIR** (Online Informative References) publishes
  many authoritative crosswalks; the **Secure Controls Framework (SCF)** is a meta-crosswalk across
  100+ frameworks; CIS, HITRUST, and PCI publish cross-references.
- Where no official mapping exists: the fine-tuned embedder proposes candidates + a **confidence score**;
  **human-in-the-loop verification** confirms before it becomes "authoritative."
- Every mapping carries a **provenance tag** (official crosswalk vs model-suggested vs human-verified) —
  critical for auditability.

### 2.3 Engine roadmap (the RegMap tiers, folded in)
- **Tier 1 — Breadth:** add framework pairs, starting with ones that have official mappings
  (ISO 27001 ↔ NIST 800-53 via OLIR; PCI ↔ NIST; NIST CSF ↔ 800-53). Ship a **multi-pair benchmark +
  leaderboard** (this is paper **P3**). Use **SCF/OLIR** as the mapping hub so pairs compose (X→hub→Y).
- **Tier 2 — Depth:** retrieve-then-**rerank** (cross-encoder), larger/LLM embedders (BGE, NV-Embed),
  hard-negative mining, augmentation ablation (back-translation / LLM paraphrase), **bidirectional &
  many-to-many** mapping, **calibration + abstention**.
- **Tier 3 — From mapping to workflow (RegNLP/RIRAG):** generate control-implementation/answer text
  with citations; **gap analysis**; **auto-generated audit evidence**; **continuous compliance** (when a
  framework revises, map only the deltas).
- **Tier 4 — Productize:** coverage/gap **dashboards**, **versioned crosswalks**, human-in-the-loop
  verification UI, an **API** other tools call, and the scan→control mapping already in the console.

---

## 3. Pillar B — Learn-by-doing training
### 3.1 Role tracks (lesson → hands-on lab → auto-graded challenge → score/badge/cert)
- **SOC Analyst (Tier 1):** read the live feed, triage alerts, mark TP/FP, escalate → graded vs the
  live-target-lab's **injected ground-truth labels**.
- **Vulnerability Management:** scan, interpret CVE/KEV/EPSS, prioritize, remediate → graded.
- **Security Auditor / Compliance:** scan the cloud-target-lab, map findings to a chosen framework
  (any from §2.1), write the audit/gap report, find the seeded gaps → graded vs known findings.
- **(later)** Threat modeling, detection engineering, incident response basics.

### 3.2 Auto-grading (the moat)
The target labs already know the right answers (injected labels / seeded findings), so exercises are
**auto-graded** cheaply: compare the learner's actions/answers to ground truth → score + targeted
feedback. This is the single hardest part of a training product, already solved by the labs.

### 3.3 AI tutor
The released models (RegMap embedder, detectors) power an **assistant** that explains a finding, why a
CVE is high-priority (KEV/EPSS), or which control a gap maps to — adaptive hints without giving away answers.

---

## 4. Architecture (reuse-first)
- **Workbench:** the existing Assess/Monitor/Compliance console (the new Tenable-style UI).
- **Sandbox:** the target labs (live + cloud) as the safe, known-answer environment.
- **Engine:** RegMap + the scan→CVE→KEV/EPSS→control pipeline.
- **Learning layer (new, thin):** accounts/roles, content model (tracks→lessons→labs), auto-grader,
  progress/badges/certs, instructor/classroom mode.
- **Isolation:** v1 = shared read-only lab + per-user scoring; v2 = ephemeral per-user containers
  (Docker/LXC already proven).
- **Auth:** finish the started `auth_service/` (student / instructor / org roles).
- **Packaging & deploy:** each service ships as a **standalone container** (built: `regmap_engine/` →
  `docker/` image, any-env CPU/GPU, metered). Deploy path scales with need: **single VM / Docker Compose
  or a managed container host** for the MVP → **Kubernetes** for scale (`regmap_engine/k8s/`: Deployment +
  Service + HPA + NetworkPolicy; opt-in GPU tier + **KEDA scale-to-zero** so idle GPU costs nothing;
  namespace-per-tenant for isolation + billing; per-session lab **Pods/Jobs** with NetworkPolicy). Same
  manifests run on **k3s** on customer hardware for the on-prem/self-host tier. Adopt K8s when GPU cost,
  many isolated lab sessions, or multi-tenant isolation demand it (Phase 1–2) — not before.

---

## 5. MVP (ship soon)
Launchable slice:
1. Landing page + signup + auth (student/instructor).
2. Content model + **3 auto-graded labs** — one per track (SOC triage · vuln prioritization · a
   compliance/audit lab using **one** framework pair, e.g. scan → map to NIST 800-53/HIPAA).
3. Progress dashboard + first badge.
4. Shared sandbox + per-user scoring (isolation deferred).
5. RegMap covering **2–3 framework pairs** at launch (NIST↔HIPAA live; add ISO↔NIST via OLIR).
Deploy on cloud (or Proxmox for the beta). Launch **free to students** via the DePaul network.

## 6. Phased shipping plan
- **Phase 0 (wks 1–4):** MVP above; free student beta.
- **Phase 1 (wks 5–10):** 10–15 labs; **certificates**; **classroom mode** (assign labs, track cohorts);
  RegMap to ~6 frameworks via SCF/OLIR hub. **Move to Kubernetes** for autoscaling + GPU scale-to-zero
  (metering → per-tenant billing via Prometheus/DCGM); manifests in `regmap_engine/k8s/`.
- **Phase 2:** per-user isolated sandboxes (**per-session K8s Pods/Jobs + NetworkPolicy**); **teams/orgs**
  (namespace-per-tenant); paid tiers; RegMap full catalog (§2.1).
- **Phase 3:** AI tutor + adaptive hints; RIRAG evidence generation; continuous-compliance monitoring.

## 7. Business / go-to-market
- **Freemium:** free individual (a few labs + 1 framework) → paid for full tracks/certs + all frameworks.
- **Usage-based compute (pay for the hardware you use):** subscription covers *features/seats*; the
  *hardware* is metered. Every scan / crosswalk / graded-lab run spends **Compute Units (CU)** — CPU-seconds
  normalized so CPU and GPU bill on one meter (GPU-second = `REGMAP_GPU_CU_MULT`× a CPU-second, default 8×,
  faster wall-clock). Each plan includes a monthly CU allowance; past it, compute is billed per use.
  - Tiers: **Student** free (shared CPU, 300 CU/mo, no GPU) · **Pro** $19/mo (2,000 CU/mo incl., then
    metered, GPU on-demand) · **Teams/Classroom** per-seat + pooled credits + metered overage ·
    **GRC/Enterprise** custom: **self-host on their own hardware → compute is free**, or managed metered GPU.
  - Enablement (**partial — do not treat billing as built**): `regmap_engine/serve.py` meters each request
    (`x-regmap-compute-units`/`x-regmap-device` headers, a `METER {…}` event per request, cumulative
    `GET /usage`). Reproducibility: engine/model **version** stamped in `/health`, `/usage`, and every
    `/map` response. See `regmap_engine/docker/SHIP.md`.
    - ⚠️ **What this does NOT do (verified 2026-08-02):** it meters *the machine, not the customer*. The
      `METER` event carries **no account id**, so compute cannot be attributed to a payer; `/usage` is
      in-memory and **per-replica** (lost on restart, never aggregated across the 1→5 HPA replicas); the CU
      is whole-request **wall-clock**, so it bills queueing and the same work costs different amounts under
      load; and quota allowances below are **unenforceable** because the middleware only observes. There is
      no auth, no database, and no payments anywhere in the codebase.
    - **Delivery model (decided 2026-08-02):** hosted multi-tenant SaaS on managed K8s (EKS/AKS), metered
      compute, incl. paid per-user practice environments. The billing spine that makes the tiers above real
      is specified in **`docs/hosted_saas_roadmap.md`** (gap list · architecture · Phases A–E).
- **B2B:** university **classroom licenses**; **SOC-team onboarding/training**; **GRC teams** for the
  compliance engine (crosswalk + gap + evidence).
- **Distribution:** DePaul + network for beta; papers + open models as top-of-funnel; the compliance
  engine can also sell standalone to GRC/audit teams.
- **Differentiators:** defense/audit/compliance focus · real ground-truth auto-grading · every framework
  · real tools (nmap, live CVE/KEV/EPSS, real control mapping) · AI tutor from own models · auditable
  provenance on every mapping.

## 8. Risks / honest constraints
- **Multi-tenant isolation** is the main new engineering — mitigate by launching shared+scored, adding
  isolation later.
- **Framework licensing:** some framework *texts* (ISO, PCI) are copyrighted — map **control IDs +
  paraphrased intent**, not verbatim text; rely on OLIR/SCF for redistributable mappings.
  - **🔴 ACTION — acquire licenses for HITRUST CSF and COBIT (ISACA) before including their control
    content.** Their content is proprietary (unlike public-domain NIST) and cannot be used commercially
    without a license. Needed in **Phase 2** when the full framework catalog goes in — get the licenses
    (or defer those two frameworks) before shipping them. Green-stack MVP (NIST/gov + your models) needs
    no permissions.
- **Content authoring** effort scales with labs — auto-grading + a lab template keep it cheap.
- **Safety/authz:** learners only ever scan the provided labs (existing authz gate enforces this).

## 9. Immediate next actions (pick order)
1. Lock this plan (this file) + a landing page to validate demand.
2. Scaffold the **learning layer**: content schema (tracks/lessons/labs) + auto-grader reading lab
   ground truth + **one** working graded lab wired into the console.
3. RegMap **Tier 1**: scaffold the OLIR/SCF-based multi-framework data format + eval harness; add the
   first new pair (ISO 27001 ↔ NIST 800-53).
