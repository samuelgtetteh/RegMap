# Future papers — working pipeline

A tracked backlog of papers we can write from this body of work, to tackle **one at a time**.
Each card has: the contribution, what is genuinely *new*, the data/experiments needed, effort,
target venue(s), overlap risk, and status. Keep statuses current as we go.

## Ground rules (learned the hard way)
- **No overlap** with the three papers already in review — each new paper needs its own contribution,
  or it gets desk-rejected for overlapping work under review.
- **Anonymize + use the venue stylefile** from the start (double-blind for TMLR/DTRAP; the desk
  rejects we hit were: non-anonymized PDF, wrong/`article` stylefile, GitHub username in a footnote).
- Keep a per-venue, anonymized build (a `make_<venue>_version.py` like the DTRAP script) so the plain
  `article` draft is never submitted by accident.

## Already submitted (context — do not duplicate)
- **RegMap** — "Automated Regulatory Crosswalking: NIST SP 800-53 → HIPAA semantic retrieval" → DTRAP-2026-0121.
- **OT/ICS** — "Label Leakage in ICS Anomaly Detection (HAI autoencoder)" → DTRAP-2026-0120.
- **Identity** — "Access Breadth for Credential-Based Lateral Movement (LANL)" → TMLR (resubmitting anonymized).

---

## Tier A — fast (mostly writing from results we already have)

### P1. Honest evaluation of security anomaly detectors  ⭐ recommended first
- **Contribution:** a methodology paper synthesizing the recurring evaluation pitfalls across our three
  studies into one guide: (a) *label leakage* / feature-provenance auditing (OT/ICS), (b) *fragile
  categorical encoding* of nominal features (Identity), (c) *triage-not-classification* under extreme
  imbalance (recall@fixed-FPR, precision@K collapse), (d) session-disjoint splits + threshold
  calibration against distribution shift.
- **New vs existing:** it is *about* the evaluation methodology, with new cross-cutting analysis and a
  checklist/protocol — not a re-report of any single result.
- **Data/experiments:** none new required; reuse existing runs, maybe one small unifying table.
- **Effort:** Low.  **Venue:** USENIX **CSET** (best fit) · ACM **AISec** · DTRAP.
- **Overlap risk:** Low (framed as methodology).  **Status:** not started.

### P2. Perspective: "the right interpretable signal beats model complexity"
- **Contribution:** a short SoK/perspective tying identity (access breadth) + OT/ICS (simple AE beats
  add-ons) into one thesis for practitioners.
- **New vs existing:** cross-domain framing + practitioner guidance; light new content.
- **Effort:** Low.  **Venue:** IEEE **Security & Privacy magazine** · ACM **Queue** · SoK track.
- **Overlap risk:** Low–Medium (must not re-state the two papers' core results).  **Status:** not started.

## Tier B — medium (extend an existing result)

### P3. Multi-framework regulatory crosswalk benchmark (extends RegMap)  ⭐ high impact
- **Contribution:** generalize NIST 800-53↔HIPAA to **GDPR, PCI DSS, CMMC, ISO 27001**; release an
  open benchmark + leaderboard for automated crosswalking; compare embedding/lexical/LLM baselines.
- **New vs existing:** new datasets (other framework crosswalks), new benchmark + multi-pair results.
- **Data/experiments:** collect/curate official crosswalks for each pair; run the pipeline per pair;
  build eval harness. Medium data-wrangling.
- **Effort:** Medium.  **Venue:** DTRAP · **NLLP** (Natural Legal Language Processing) · benchmark track.
- **Overlap risk:** Low (clearly larger than the single-pair DTRAP paper).  **Status:** not started.

### P4. Systems/practice paper: the unified assess → detect → comply platform  ⭐ NIW-strong
- **Contribution:** architecture + practice report of the RegMap console — scan → CVE + KEV/EPSS →
  NIST-control mapping → live decisioning/response — with the reproducible target labs and the
  ~22-hour continuous run as measured evidence (precision/recall/specificity from the live trail).
- **New vs existing:** the integrated *system* and its operation; none of the three papers describe it.
- **Data/experiments:** mostly describe what's built; a clean measured run + maybe a small scan study.
- **Effort:** Medium.  **Venue:** DTRAP (Practice) · **ACSAC** · artifact/demo track.
- **Overlap risk:** Low.  **Status:** not started.

### P5. Reproducible benchmarking infrastructure (the target labs)
- **Contribution:** the **live-target-lab + cloud-target-lab** as open, ground-truth harnesses for
  evaluating detectors and cloud-posture scanners — the feedback-loop design and known-answer fixtures.
- **New vs existing:** the infrastructure + a demonstration that it reproduces detector metrics.
- **Effort:** Medium.  **Venue:** **CSET** · Datasets & Benchmarks track.
- **Overlap risk:** Low.  **Status:** not started.

## Tier C — higher effort (needs new experiments)

### P6. SWaT/WADI replication of the OT/ICS study
- **Contribution:** show the label-leakage + session-disjoint + calibration lessons generalize beyond
  HAI to another ICS testbed (external validity).
- **Data/experiments:** obtain SWaT/WADI; rerun the full pipeline; new results.
- **Effort:** High.  **Venue:** DTRAP · ACSAC · CSET.  **Status:** not started (in roadmap).

### P7. Real-log identity detection (Azure Entra / AWS CloudTrail)
- **Contribution:** port the access-breadth finding from LANL to real cloud identity logs; a deployment
  study with calibration to a real baseline.
- **Data/experiments:** build the log collector (discussed), gather real logs, evaluate.
- **Effort:** High.  **Venue:** DTRAP · ACSAC.  **Status:** not started (depends on the collector).

### P8. Exploit-aware prioritization study
- **Contribution:** quantify KEV+EPSS blended ranking vs. plain CVSS for remediation prioritization,
  using our scanner + the labs' known-answer fixtures.
- **Effort:** Medium–High.  **Venue:** DTRAP · WEIS (economics of security) · CSET.  **Status:** not started.

---

## Suggested order
1. **P1** (fast, no new experiments, CSET fit) — get another submission out soon.
2. **P4** (platform/practice) or **P3** (crosswalk benchmark) — highest impact / NIW value.
3. Then P5, P2, and the Tier-C empirical papers (P6–P8) as data/collectors come online.

## How we'll run each
For the chosen paper: draft **title → abstract → section skeleton → data/experiment list**, then write
it in `paper/<name>/`, generate the anonymized venue build, and submit. Update the card's **Status**
here (not started → drafting → submitted → decision).
