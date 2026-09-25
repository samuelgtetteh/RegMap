# Project Roadmap

Phase-wise progression plan for the portfolio, agreed as the plan of record.
Planning document only — no phase is implemented until explicitly started.
Ordered so evaluation rigor comes first (strengthens every exhibit), then the
real-time response capability, then packaging.

```
Phase 0 (prep) ──► Phase 1 (rigor) ──► Publication Track (paper)
                        │         └───► Phase 3 (packaging)
                        └──► Phase 2 (response) ──┘
Phase 4 ── runs in parallel, anytime
```
(The paper draws on Phase 1; if it becomes the integrated systems paper, it also
waits on Phase 2.)

---

## Phase 0 — Clean baseline (prerequisite, small)
Everything below assumes a committed starting point.
- Commit outstanding work: identity-generator behavioural-attack fix (`live-target-lab`), `docs/logs/tally_detection.py`, Exhibit 14.
- Reproducibility: commit the one evidence snapshot behind Exhibit 14's numbers (`docs/logs/2026-07-05_120350/`), which is otherwise gitignored.
- Remove the stray `awesome_wright` container.
- **Done when:** clean `git status` across all repos; exhibit numbers reproducible from committed data.

---

## Phase 1 — Scientific Credibility & Evaluation Rigor  (start here)
**Objective:** move each model from "it works" to "rigorously evaluated," with metrics an expert reviewer would accept. **This phase is now also the results engine for the scientific paper (see Publication Track), so its outputs must be publication-quality — every figure and table should be paper-ready, and each model must be positioned against prior published results on the same dataset.**

- **OT/ICS (biggest payoff):** HAI ships attack labels → fully supervised. ROC + PR curves, AUC/AP; **threshold justification** (curve of recall/precision/FP-rate vs. threshold, replacing the hand-picked 95th percentile); per-attack-type breakdown; error analysis.
- **Identity Anomaly:** unsupervised → the unlock is labels. Check whether the LANL copy includes red-team ground truth (`redteam.txt`); if so, evaluate the Isolation Forest against real compromise events → real ROC/AUC/PR (biggest credibility win available). Otherwise, formalize the synthetic behavioural-burst attacks into a labelled test set.
- **RegMap:** add rigor cheaply — baseline comparison (fine-tuned Sentence-BERT vs. off-the-shelf vs. keyword/BM25); bootstrap confidence intervals on the 34-query test set; error analysis of misses.
- **Cross-cutting:** fixed seeds, documented splits, confidence intervals, short methodology writeup.

**Deliverables:** an evaluation notebook per model producing curves + tables; publication-quality figures; **a comparison against prior published results on each dataset (LANL, HAI, NIST↔HIPAA crosswalk)**; a rigor section added to Exhibits 11–13 (or a new Evaluation & Benchmarking exhibit). All artifacts feed the Publication Track.
**Done when:** every model has curves, an AUC/AP number, a baseline comparison, a prior-work comparison, and a quantitatively justified threshold.

---

## Publication Track — Three Scientific Papers (one per model)
**Scope decision (made):** publish a separate focused paper for each model rather than one integrated paper. Papers are authored as Word documents, kept local (`paper/` is gitignored). Goal: arXiv preprint baseline + a peer-reviewed venue (Computers & Security / USENIX CSET / IEEE Access / MDPI); submit to one venue at a time. Each paper's rigor comes from Phase 1's paper-aware evaluation.

**Paper 1 — OT/ICS (`paper/ot_ics/`) — DRAFTED.**
"Label Leakage in ICS Anomaly Detection: A Reproducible Re-Evaluation of an Autoencoder Detector on the HAI Testbed." Contribution: the label-leakage pitfall + rigorous leakage-free evaluation (ROC AUC 0.929, threshold-calibration finding, baselines). Ground truth: HAI attack labels. Remaining: finish citation verification; optional eTaPR for like-for-like HAI comparison.

**Paper 2 — Identity (`paper/identity/`) — APPROACH TO DECIDE.**
Hybrid identity anomaly detection on LANL auth logs. **Blocker:** the available LANL data has no red-team ground truth, so a detection-accuracy evaluation is not possible without acquiring labels. Two paths: (a) obtain LANL red-team labels and do a supervised evaluation; or (b) reframe as a systems/methodology paper — batch→streaming adaptation, rolling-window behavioural features, live validation harness — with qualitative analysis instead of accuracy metrics.

> **★ ACTION ITEM — Red-team ground truth (BLOCKED: data window mismatch).**
> **Finding (2026-07-05):** our processed LANL slices cover only the very start of
> the dataset — the 500k-row slice spans time 1–5118 (~1.4 h) and the 2M-row slice
> time 1–20376 (~5.7 h), both within day 1. LANL red-team events do not begin until
> ~day 2 (time ~150,000+), so **there is zero red-team overlap in our data**, and the
> raw `auth.txt` is **not stored locally**. Aligning red-team labels therefore
> requires re-acquiring the raw dataset, not just downloading `redteam.txt`.
>
> **To unlock the rigorous Identity paper (needs a large manual download):**
> 1. Download `auth.txt.gz` (~12 GB compressed) and `redteam.txt` from
>    https://csr.lanl.gov/data/cyber1/ (too large to pull inside the agent session).
> 2. Re-slice `auth.txt` to the red-team window (≈ time 150,000–750,000).
> 3. Re-engineer the same features; train on a normal sub-window; evaluate the
>    detector against the red-team labels (ROC/AUC, PR/AP, operating point).
>
> **Fallbacks if the download isn't done:** (b) reframe Identity as a
> systems/methodology + reproducibility paper (batch→streaming, behavioural
> features, live validation, qualitative analysis) — no accuracy claims; or
> (c) semi-synthetic evaluation: inject the live-target-lab behavioural-burst
> attacks into held-out normal LANL data and measure detection, clearly labelled
> as controlled/synthetic rather than real red-team.

**Paper 3 — RegMap (`paper/regmap/`) — FEASIBLE, NOT BUILT.**
"Automated regulatory crosswalking: fine-tuned semantic retrieval for NIST 800-53 → HIPAA mapping." Contribution: task framing + fine-tuning gains over baselines (off-the-shelf SBERT, keyword/BM25), Recall@k / MRR / MAP with confidence intervals. Ground truth: the NIST↔HIPAA crosswalk. Strong and quick to make rigorous.

**Honest contribution framing** (methods are established, so novelty is applied/systems/reproducibility, not new algorithms).

**Recommended order:** OT/ICS (done) → RegMap (fastest, clean ground truth) → Identity (after deciding its approach).

**Done when:** each model has a submission-ready manuscript with defensible results, prior-work comparison, and a clear contribution claim.

---

## Phase 2 — Real-Time Decisioning Layer
**Objective:** turn detection into autonomous response — realize Exhibit 14 §9.
**Locked design:** Hybrid architecture · TimescaleDB/Postgres single store · Grafana dashboard. See `docs/phase2_plan.md` for the detailed build plan.

- **2a Record** — RedMap writes every verdict to Postgres.
- **2b Decide** — decision-service applies config-driven windowed rules.
- **2c Act** — alert log + webhook (+ optional simulated autonomous response).
- **2d See** — Grafana dashboards over Postgres (rates + live alerts table).

**Deliverables:** verdict persistence + decision-service + Grafana; new evidence → **Exhibit 15: Operational Response**.
**Done when:** an injected attack flows end-to-end — persisted verdict → fired alert → dashboard update — demonstrably and on screen.

---

## Phase 3 — Petition Packaging & Narrative Coherence
**Objective:** consolidate all technical work into a submission-ready petition. Consumes outputs of Phases 1–2.
- Consistency audit: every number/claim matches across personal statement, README, notebooks, and all exhibits.
- Prong mapping: each exhibit tied to a proposed-endeavor pathway and to the three NIW prongs.
- Fold in Phase 1 evaluation figures and Phase 2 response evidence.
- Master portfolio-index exhibit; verify every claim has backing evidence and every exhibit is referenced.

**Deliverables:** submission-ready exhibit set + a claim→evidence consistency matrix.
**Done when:** a reviewer can trace every claim to evidence with no contradictory numbers.

---

## Phase 4 — Productionization & Maintenance (parallelizable, lower priority)
**Objective:** engineering-maturity signals.
- Shrink the backend image (CPU-only torch → ~1–2 GB from 8.8 GB).
- CI: GitHub Actions running the pytest suite + `ruff` on push.
- Basic auth / rate-limiting on the API; model-version metadata endpoint.
- **Done when:** green CI, slim reproducible deploy.
