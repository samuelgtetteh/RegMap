# Retraining the embedder — NEXT UP (not started)

**Status: data prepared, nothing trained.** Written 2026-08-02.

Everything needed is on disk in `data/processed/retrain-v2/`. Rebuild it any time with
`python regmap_engine/build_training_data.py --write`.

---

## Why now

The released model was fine-tuned on **159 pairs from one framework pair**. Today's imports changed the
inputs by an order of magnitude:

| | released `@0.1` | available now |
|---|---|---|
| labelled pairs | 159 | **1,459** (9.2×) |
| framework pairs | 1 | **5** with text on both sides |
| control texts (unlabelled) | ~193 | **1,544** |

The paper's own central finding is that **in-domain paired data is the primary driver** of mapping
quality. So the cheapest available improvement is to feed the same method far more of exactly the thing
it responds to — no new technique required.

---

## The files, and what each is for

```
data/processed/retrain-v2/
  manifest.json              provenance, counts, seed, exclusions, the number to beat
  query-holdout/             PRODUCT metric — train 1003 / val 250 / test 206
    train.jsonl val.jsonl test.jsonl
  strict/                    GENERALISATION metric — train 614 / val 28 / test 62
    train.jsonl val.jsonl test.jsonl
  corpus/<framework>.jsonl   ranking corpora: nist_80053 1016 · nist_csf2 207 · nist_80172 103 ·
                             nist_80171 97 · nist_ssdf 61 · hipaa_security 60
```

Row format is ready for `MultipleNegativesRankingLoss` as-is, plus traceability fields:

```json
{"anchor": "<source control text>", "positive": "<target control text>",
 "source": "nist_80053", "source_id": "AC-1",
 "target": "hipaa_security", "target_id": "164.308(a)(3)",
 "mapping": "nist_80053__hipaa_security", "provenance": "official"}
```

### Two protocols, because one number cannot answer both questions
- **`query-holdout`** — hold out *source* controls; the target corpus stays fully visible. That is how
  retrieval works in the product and it mirrors the paper's group-split. **Use this to decide whether the
  product got better.**
- **`strict`** — every control id is assigned to one split *globally*, and a pair is kept only if both
  endpoints agree. Nothing in test was seen in training in either role. **Use this to claim
  generalisation.**

Why `strict` is needed: mappings compose through hubs, so a control appears in several mappings in
different roles. `AC-2` is a *target* in CSF→800-53 and a *source* in 800-53→HIPAA — hold it out of only
the second and the model has still optimised a representation for its exact text. Invisible unless you
split on control identity globally.

⚠️ **`strict` is small and will stay small**: 755 of 1,459 pairs span splits and are discarded, leaving a
**62-pair test set**. Confidence intervals will be wide; do not over-read small differences. This is a
real limitation of the data, not a bug in the split.

Both splits are **leakage-checked in code** (`check_leakage`) and both currently report CLEAN. Seed 42,
matching the released model and the paper so splits stay comparable.

---

## Order of work

1. **Eval harness first, before any training.** `eval_crosswalk.py` has no held-out split, so a retrained
   model will score ~0.95 on memorised data and tell you nothing. Build the harness to read
   `retrain-v2/*/test.jsonl` and report per-mapping *and* pooled Recall@k / nDCG@k / MRR / MAP with
   bootstrap CIs. **Nothing else on this list is meaningful until this exists.**
2. **Retrain, same recipe.** MiniLM + MNRL, notebook 02's hyperparameters (batch 16, 10 epochs, linear
   warmup 10%, AdamW lr 2e-5). Minutes on CPU. Establishes whether 9× data alone moves the needle.
3. **Hard-negative mining.** Currently only random in-batch negatives. With 1,544 controls you can mine
   controls the model ranks highly but that are *not* mapped. Usually the largest gain available without
   new data or a bigger model.
4. **Cross-encoder reranker.** Retrieve top-50 with the bi-encoder, rescore jointly. Often a bigger jump
   than upgrading the embedder, and the cost is bounded to top-k.
5. **Bigger base model** (mpnet / BGE / E5 / gte, 768-dim). Better retrieval, but slower inference,
   larger image, and roughly 3× the cold encode — already ~27 s at 1,544 controls, so the build-time
   embedding cache stops being optional.
6. **Domain-adaptive pretraining** — continue MLM/TSDAE on the 1,544 control texts unlabelled first.
   Regulatory language is unusual enough that this often helps.
7. **Augmentation** (back-translation, LLM paraphrase) — *test, don't assume*: Bianchi found it helped
   cross-standard matching and **hurt** control-to-metric.

### The largest expansion available is content, not modelling
**1,365 pairs are excluded** because their targets have no shippable text — ISO 27001 (389), PCI DSS
(551), SCF (363), CIS (62). Writing **original short intent paraphrases** for those control ids is legal
(the ids and mappings are already ours to use via NIST's public-domain OLIR) and would simultaneously:
- make those frameworks **semantically searchable** instead of mapping-only, and
- unlock those 1,365 pairs **as training data**, taking the corpus to ~2,800 pairs.

That is a bigger lever than any modelling change on this list.

---

## Rules for the retrain

- **Do not overwrite `models/regmap-embedder/`.** It is the artifact the DTRAP submission describes;
  overwriting it makes the paper's numbers unreproducible. Train to `models/regmap-embedder-v2/` and bump
  `REGMAP_MODEL_VERSION`.
- **The number to beat is the paper's held-out multi-relevant R@5 = 0.797.** Do **not** compare against
  `eval_crosswalk.py` output (R@5 0.906) — that has no held-out split and is inflated by training
  leakage. `/eval` already self-reports `benchmark: false` for this reason.
- **The serving plumbing already handles a model swap correctly.** The embedding cache is keyed on
  `REGMAP_MODEL_VERSION` + control text, so a new model invalidates it automatically and re-encodes —
  no stale-vector risk. But the model is baked into the Docker image and tracked in Git LFS, so each
  version costs ~87 MB of history plus an image rebuild (`warm_cache.py` re-warms at build time).
- Re-run `build_training_data.py --write` after any catalog change, so the splits reflect current content.

---

## Not doing yet
Nothing on this page is implemented. The only work done is data preparation:
`regmap_engine/build_training_data.py` and its output.
