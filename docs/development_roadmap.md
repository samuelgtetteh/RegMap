# Post-Submission Development Roadmap

Forward plan for developing the portfolio **after** all three papers were submitted
for peer review (2026-07-11). Supersedes the forward-looking parts of `docs/roadmap.md`,
whose earlier phases (evaluation rigor → live response → packaging) are now largely
complete. Written 2026-07-11. Planning document — a phase is not started until
explicitly agreed. Update the **Status** boxes and the **Resume pointer** as work proceeds.

Goal: implement **all five** development tracks, in a dependency-respecting order, so
nothing is built before the thing it depends on.

---

## The five tracks (the "what")
- **Track A — Deepen the science.** Cross-dataset replication (SWaT/WADI), multi-seed
  variance, temporal/graph models, unknown-attack eval; the multi-framework RegMap
  extension (GDPR/PCI/CMMC); and the keystone **synthesis/position paper** on evaluation
  pitfalls in ML security (leakage, protocol, calibration) across all three domains.
- **Track B — Community resources.** Package the reproducible evaluation harness +
  protocols + splits as an **open-source benchmark library**; pursue ACM/USENIX
  **artifact-evaluation badges**.
- **Track C — Real-time decisioning layer.** Build the Record → Decide → Act pipeline
  already scoped in Exhibit 14 §9 → a new Exhibit 16.
- **Track D — Independent recognition.** arXiv **preprints**; **peer-review service**;
  **talks/presentations**; **letters of adoption**.
- **Track E — Broadened AI platform.** LLM/agentic layer — RAG over regulations,
  LLM-assisted triage of the anomaly queue — on top of Track C.

---

## Dependency analysis (the "needs input from" question)
"X → Y" means Y needs X first.

| Item | Hard dependency | Soft dependency (strengthened by) |
|---|---|---|
| D-preprints | cs.CR endorsement for OT/ICS (in progress); none for TMLR paper | — |
| D-review service | D-preprints / a public record | acceptance of a paper |
| D-talks | D-preprints or synthesis paper exists | — |
| D-letters of adoption | **B-benchmark released and used** | — |
| A-synthesis paper | the 3 core papers (DONE) | A-SWaT replication, A-multi-seed |
| A-multi-seed variance | none (cheap) | — |
| A-SWaT/WADI replication | **SWaT/WADI data access request** (external lead time) | — |
| A-identity graph paper | CERT corpus download (public) | — |
| A-RegMap multi-framework | GDPR/PCI/CMMC crosswalk data | — |
| B-benchmark package | existing eval code/protocols (DONE) | A-deepening (richer content) |
| B-artifact badges | **paper acceptance (external)** + B-benchmark | — |
| C-decisioning layer | existing containerized system (DONE) | — |
| E-AI/agentic platform | **C-decisioning layer** | A-RegMap multi-framework (richer corpus) |

**Key takeaways from the graph:**
1. **D-preprints have no upstream dependency and unlock the whole recognition track** → do first.
2. **SWaT/WADI is a lead-time item** (data request), so *kick off the request early* even
   though the experiment runs later; the synthesis paper does NOT hard-depend on it
   (it already has cross-domain evidence from the 3 submitted papers), so SWaT never blocks it.
3. **Artifact badges are externally gated** on paper acceptance — cannot be pursued now; park until decisions arrive.
4. **The platform (E) sits on the decisioning layer (C)** — C strictly precedes E.
5. **Benchmark (B) precedes letters-of-adoption (D)** — you need users before they can vouch.

---

## Phased plan (the "when")

### Phase 1 — Visibility + lead-time kickoffs  *(start immediately; all parallel, no upstream deps)*
- [ ] **D:** Post arXiv preprints of all three papers (OT/ICS pending cs.CR endorsement; TMLR paper allows preprints; RegMap → cs.CL, confirm endorsement need).
- [ ] **A:** Submit SWaT + WADI data-access requests to iTrust/SUTD (long lead time — start the clock now).
- [ ] **A:** Multi-seed variance runs for OT/ICS + Identity (cheap; strengthens both submitted papers and the synthesis paper).
- [ ] **D:** Begin peer-review service sign-ups now that a public record exists (accrues over time).

### Phase 2 — Synthesis paper + open-source benchmark  *(co-developed; reinforce each other)*
- [ ] **A:** Write the synthesis/position paper on evaluation pitfalls (uses the 3 submitted papers as primary evidence; fold in SWaT results only if the data has arrived).
- [ ] **B:** Package the evaluation harness + protocols (session-disjoint, group-split, leakage audit, bootstrap CIs) as an open-source benchmark library the paper points to.
- Dependency note: benchmark packages existing code (ready now); synthesis reuses done work — neither blocks on Phase 1's SWaT item.

### Phase 3 — Operational platform  *(engineering track; can run parallel to Phase 2 if bandwidth allows)*
- [ ] **C:** Build Record → Decide → Act decisioning layer → **Exhibit 16**.
- [ ] **A (prereq for E):** RegMap multi-framework extension (GDPR/PCI/CMMC) — do before/with E to give the RAG layer a richer corpus.
- [ ] **E:** LLM/agentic layer (RAG over regulations, LLM-assisted anomaly-queue triage) on top of the decisioning layer.

### Phase 4 — Additional papers  *(independent; schedule by interest/bandwidth)*
- [ ] **A:** OT/ICS SWaT/WADI cross-dataset paper (once data arrives — from Phase 1 request).
- [ ] **A:** Identity graph-structural model paper (CERT insider-threat corpus).
- [ ] **A:** RegMap multi-framework paper (if not already written for Phase 3).

### Phase 5 — Recognition harvest  *(accrues continuously from Phase 1; partly externally gated)*
- [ ] **D:** Conference/workshop talks (once preprints/synthesis exist).
- [ ] **B:** Artifact-evaluation badges (**when paper acceptances arrive** — external timeline).
- [ ] **D:** Letters of adoption (after the benchmark has real users).

---

## What can run in parallel vs. what is strictly serial
- **Strictly serial chains:** preprints → review-service/talks; core papers → synthesis;
  eval code → benchmark → (acceptance) → badges; system → decisioning (C) → AI platform (E).
- **Fully parallelizable at any time:** the recognition track (D) once preprints are up;
  the engineering track (C→E) is independent of the research track (A/B) and can proceed
  alongside it if you have the bandwidth.
- **Externally gated (waiting on others):** SWaT/WADI data access; paper acceptances (badges).

---

## Resume pointer
**Status (2026-07-11):** User chose to start with **Track C (decisioning layer) → E (AI platform)**
first — it's independent of the research track and unblocked. That build has its own detailed
plan + checkpoint in **`docs/decision_layer_plan.md`**; **Phase C1 (Record layer) is DONE**
(verdict persistence + `/decision` API + notebook 08).
- **SWaT dataset acquired** (a 106 MB CSV copy: `data/raw/SWaT Dataset Secure Water Treatment
  System.zip`), and an official iTrust request was also submitted for citable provenance →
  the Phase-1/Phase-4 SWaT cross-dataset replication is now data-ready.
- Still not started: arXiv preprints (Phase 1, D-track) and the synthesis paper (Phase 2).
**Next:** continue the decision layer (C2 Decide → C3 Act → E AI) per `docs/decision_layer_plan.md`;
and, in parallel when ready, Phase 1 arXiv preprints. Related: [[papers-submission-status]],
[[regmap-paper-status]]; `docs/roadmap.md` (earlier, now-complete plan).
