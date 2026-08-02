# RegMap paper — expansion plan & resume checkpoint

**Purpose:** single source of truth for expanding the RegMap paper to the same scholarly
standard as the OT/ICS and Identity papers. Written so any session can resume from the
**Progress tracker** below. Started 2026-07-11.

---

## What the paper is
- **Title:** *Automated Regulatory Crosswalking: Fine-Tuned Semantic Retrieval for NIST SP 800-53 to HIPAA Mapping*
- **Author (apply per memory [[paper-author-affiliation]]):**
  `\author{Samuel Gbli Tetteh}`
  `\affil{Jarvis College of Computing and Digital Media, DePaul University, Chicago, USA \\ \texttt{stetteh@depaul.edu}}`
  (NOTE: current `paper.tex` still has the bare `\author{Samuel Gbli Tetteh}` with NO `\affil` and NO `authblk` affiliation — must be fixed. The leading "D " typo seen elsewhere should NOT be reproduced.)
- **Method:** frame NIST SP 800-53 → HIPAA Security Rule mapping as semantic retrieval;
  fine-tune `all-MiniLM-L6-v2` with in-batch multiple-negatives ranking loss (MNRL);
  rank HIPAA provisions by cosine similarity; compare vs base MiniLM, BM25, TF-IDF.
- **Data:** official crosswalk → 222 positive pairs over 133 NIST controls; corpus of 60
  HIPAA provisions; hold out 15% of pairs (seed 42) → 34 test queries vs full 60-provision corpus.
- **Headline results (single-relevant, from `results_regmap.json`):**
  Fine-tuned R@5 **0.735** (CI 0.588–0.882) vs base 0.500, TF-IDF 0.500, BM25 0.353.
  Fine-tuned R@10 0.824, MRR 0.463, MAP 0.463. Multi-relevant numbers ALSO already computed
  (fine-tuned R@5 0.797, MAP 0.668) — currently UNUSED in the manuscript; surface them.

## Files
- `paper/regmap/paper.tex`  — the manuscript (currently ~109 lines, skeletal). gitignored.
- `paper/regmap/eval_regmap.py` — evaluation script (produces results_regmap.json + figures).
- `paper/regmap/results_regmap.json` — all metrics with bootstrap CIs (single + multi relevant).
- `paper/regmap/references.bib` — bibliography.
- `paper/regmap/build_paper.py` — builds paper.docx (+ venue variants). Do NOT rely on it to
  regenerate paper.tex; the .tex is hand-authored like the other two papers.
- `paper/regmap/figures/` — recall_at_k.png, metric_bars.png, eq_*.png.
- `notebooks/06_regmap_paper_evaluation.ipynb` — existing base eval notebook.
- Reproduce: `venv\Scripts\python.exe paper\regmap\eval_regmap.py`

## Reference PDFs the user supplied (positioning anchors)
1. **Bianchi, Petrillo, Martinelli, Petrocchi (2026)** — "Automated Compliance Mapping in Cloud
   Security with Domain-Adapted Sentence Transformers." *Procedia Computer Science* (KES 2026),
   arXiv:2607.06364. **Near-twin method** (fine-tuned Sentence Transformers + MNRL, control-to-metric
   AND cross-standard control-to-control) but on EU cloud standards (EUCS, BSI C5, ENS, SecNumCloud)
   via Cisco CCF hub + EMERALD metrics; nDCG@10; data augmentation (back-translation, LLM paraphrase).
   Key finding: in-domain training data is the primary driver; augmentation helps cross-standard,
   hurts control-to-metric.
2. **Gokhan, Wang, Gurevych, Briscoe (2024)** — "RegNLP in Action: Facilitating Compliance Through
   Automated Information Retrieval and Answer Generation." arXiv:2409.05677. Defines RegNLP framing;
   ObliQA dataset (27,869 Qs from ADGM financial regs); RIRAG task; RePASs metric; retrieval baselines
   (BM25, DRAGON+, SPLADE, ColBERTv2, NV-Embed-v2, BGE-EN-ICL) with recall@10 / MAP@10.

### Positioning thesis (how RegMap differs — use in Related Work + Intro)
- Bianchi maps **EU cloud** standards to each other/metrics; RegMap maps **US NIST 800-53 → HIPAA
  Security Rule** (healthcare), a different framework pair with an **official government crosswalk**
  as ground truth (not derived via a hub).
- Both use fine-tuned SBERT + MNRL → RegMap independently corroborates Bianchi's central claim
  ("in-domain paired data is the primary performance driver") on a new domain — a *complementary*
  replication, which is a strength to state explicitly, not a weakness.
- RegMap is deliberately **compact & reproducible** (one small model, one crosswalk, released artifact)
  vs Bianchi's 5-model × 4-scenario sweep — position as the minimal, auditable counterpart.
- Gokhan gives the RegNLP subfield umbrella + retrieval-metric conventions (recall@k, MAP) to cite.
- Additional refs to add from Bianchi's bibliography that fit NIST/US framing:
  **Agarwal et al. (IEEE CLOUD 2021)** — AI-assisted security-controls mapping to **NIST 800-53**
  (most directly comparable prior work); **Ahmed, Wei, Al-Shaer (ACM SACMAT 2024)** — LLM prompting
  to translate CIS controls to metrics.

---

## Gap analysis (current skeleton vs scholarly standard)
The other two papers each run ~4,600–4,750 words with: Abstract, Introduction (+Contributions),
Background, (Threat/Problem framing), 3–4-part Related Work, Dataset, Method, Evaluation Setup,
Results (multiple tables + analysis subsections), Discussion, Limitations & Future Work, Conclusion,
reproducibility footnote. RegMap currently has one-paragraph sections and no:
- Contributions list; Background; Problem Definition (formal IR framing — Bianchi has a clean one to mirror);
- Related-Work positioning against Bianchi/Gokhan/Agarwal (the single biggest scholarly gap);
- Multi-relevant results table (numbers already exist in JSON, unused);
- Stricter **group-split-by-control** evaluation (paper's own Discussion admits pair-split is a weakness);
- **nDCG@k** (needed to compare like-for-like with Bianchi's nDCG@10);
- Discussion depth, Limitations section, reproducibility footnote + released-artifact statement;
- DePaul author affiliation block.

---

## Phased plan & Progress tracker
Update the checkboxes and the "Last done / Next" line at the bottom after each work session.

- [x] **Phase 0 — Resume infra.** This file + memory note `regmap-paper-status`. (DONE 2026-07-11)
- [x] **Phase 1 — Cheap durable wins (no experiments).** (DONE 2026-07-11)
  - [x] Applied DePaul `\affil` author block to `paper.tex`.
  - [x] Added refs to `references.bib`: `bianchi26`, `gokhan24`, `agarwal21`, `ahmed24`.
- [x] **Phase 2 — Expand manuscript prose (uses existing results).** (DONE 2026-07-11 — full rewrite of paper.tex)
  - [x] Introduction + explicit Contributions list.
  - [x] Background (crosswalking; why semantic retrieval; RegNLP).
  - [x] Problem Definition (formal query/doc IR framing; single- vs multi-relevant).
  - [x] Related Work: folded in Bianchi (near-twin, complementary), Gokhan (RegNLP), Agarwal (NIST), Ahmed.
  - [x] Dataset & Task expanded (crosswalk provenance, split protocol, full-corpus distractors).
  - [x] Method (equations kept; MNRL in-batch negatives explained; training config deferred to artifact — NOT invented, since eval_regmap.py loads a pre-trained model dir and the hyperparameters are not on record).
  - [x] Evaluation Setup (Recall@k, MRR, MAP; bootstrap 1000 / 95% CI).
  - [x] Results: added **multi-relevant table** (Table 2, from JSON) + single-relevant (Table 1) + analysis.
  - [x] Discussion / Limitations & Future Work / Conclusion.
  - [x] Reproducibility footnote (GitHub + notebooks 06/06b — 06b still to be created in Phase 4).
  - NOTE: nDCG@k and group-split are currently written as *Future Work* in the Limitations section. When Phase 3 computes them, MOVE those results into the Results section and update the Limitations text.
- [x] **Phase 3 — Additional experiments (run code).** (DONE 2026-07-11)
  - [x] Group-split-by-control (`paper/regmap/eval_extras.py`, new file; splits on `nist_control_id`, seed 42). Result: fine-tuned R@5 0.848 (CI 0.727-0.970) — gain UNDIMINISHED vs pair-split 0.735.
  - [x] nDCG@{5,10} added for pair-split + group-split. Fine-tuned pair-split nDCG@10 0.544; group-split 0.677.
  - [x] Appended `ndcg_pair_split` and `group_split` keys to results_regmap.json; updated paper.tex (nDCG col in Table 1; new group-split Table 3 + "Robustness" subsection; Evaluation Setup + Limitations updated so nDCG/group-split are reported, not future work).
  - Run to reproduce: `venv\Scripts\python.exe paper\regmap\eval_extras.py` (loads model 4x, ~1-2 min CPU).
- [x] **Phase 4 — Notebook 06b** (DONE 2026-07-11). `notebooks/06b_regmap_extended_evaluation.ipynb`
      created, executed (0 errors), outputs embedded; group-split R@5 output = 0.848 (CI 0.727-0.970),
      matches paper exactly.
- [x] **Phase 5 — README + progress log + commit** (DONE 2026-07-11). Root README updated (RegMap
      robustness note + notebooks 06b/07b in layout); progress_log.md dated entry added; committed as
      `08bfd9e` (6 files: README, progress_log, this plan, docs/publishing/*, notebook 06b). NOT pushed yet.

### Target venue
Per `docs/publishing/publishing_recommendations.xlsx`: **Cambridge *Natural Language Processing***
(formerly *Natural Language Engineering*) — free for DePaul (Cambridge Full APC waiver), Scopus/WoS
indexed, IR in scope. Backup: Cambridge *Data & Policy*; ACM DTRAP.

---

## Resume pointer
**STATUS: SUBMITTED to ACM DTRAP on 2026-07-11** (from `paper/regmap/paper_dtrap.tex`, anonymized
acmart version generated by `paper/make_dtrap_versions.py`). Awaiting review; see the
`papers-submission-status` memory and the 2026-07-11 (evening) progress-log entry for watch-fors.
**Last done:** ALL PHASES (0-5) COMPLETE (2026-07-11). Committed `08bfd9e` and pushed.
**Remaining polish (optional, before submission):**
1. **Push** the commit (`git push origin main`) when ready — currently local only.
2. **Verify the 4 new .bib entries** against primary sources: arXiv IDs 2607.06364 (Bianchi) and
   2409.05677 (Gokhan) — CONFIRMED 2026-07-11 against the shared PDFs (both IDs correct; Agarwal
   IEEE CLOUD 2021 pp. 136-146 and Ahmed SACMAT 2024 pp. 93-104 match Bianchi's reference list).
   ~~Recover fine-tuning hyperparameters~~ DONE 2026-07-11: recovered from notebooks/02 (batch 16,
   10 epochs, linear warmup 10% of steps, library-default AdamW lr 2e-5, MNRL; 159/29/34
   train/val/test, all seed 42) and written into the Method "Training configuration" paragraph.
   Also added (quality parity with Bianchi): dataset-composition table (Table 1 analog) in §Dataset,
   and the formal DCG/nDCG definition in §Evaluation Setup.
3. **Overleaf compile** of `paper/regmap/paper.tex` + proofread (no local TeX toolchain here).
4. Optional: add a §2d to the gitignored local runbook `paper/README.md` (build guide), mirroring §2b/§2c.
5. Consider the augmentation ablation (back-translation / LLM paraphrase) named in Future Work if a
   reviewer wants parity with Bianchi's augmentation study.
**Target venue:** Cambridge *Natural Language Processing* (free via DePaul Cambridge APC waiver).

### Phase 3 result numbers (for README/progress log — single-relevant)
- Pair-split nDCG@10: fine-tuned 0.544, base 0.434, TF-IDF 0.412, BM25 0.273.
- Group-split-by-control (33 q from 20 controls): fine-tuned R@5 0.848 (CI 0.727-0.970), R@10 0.939,
  MRR/MAP 0.597, nDCG@10 0.677; base R@5 0.545; TF-IDF 0.424; BM25 0.455. Gain undiminished vs pair-split.
