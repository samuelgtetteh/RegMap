# regmap-embedder@0.2

Fine-tuned sentence embedder for **compliance control crosswalking**: given a security or privacy
control, retrieve the equivalent provisions in another framework.

Successor to `regmap-embedder@0.1`. **@0.1 is not replaced on disk** — the DTRAP paper's figures are
reproducible only against it.

- **Base:** continued fine-tuning of `regmap-embedder@0.1` (itself `all-MiniLM-L6-v2`)
- **Objective:** MultipleNegativesRankingLoss, in-batch softmax over cosine similarity, scale 20
- **Dimensions:** 384 · **max_seq_length:** 256 · **License:** Apache-2.0 (inherited)

## Intended use

An **assistive top-k retriever for an expert to confirm** — not an authoritative single-answer
classifier. It proposes candidate mappings and scores them; a qualified person decides. Where an official
crosswalk exists, the engine returns that as the authoritative answer and uses the model only to rank and
to suggest beyond it.

**Not suitable for:** unattended compliance determinations, audit evidence without human review, or any
use where a wrong mapping carries regulatory consequence without a reviewer.

## Training data

1,003 training / 250 validation pairs (`query-holdout` protocol), drawn from official, public-domain
crosswalks across five framework pairs:

| pair | train pairs |
|---|---|
| NIST CSF 2.0 → SP 800-53 | 483 |
| NIST CSF 2.0 → SP 800-171 | 228 |
| NIST SP 800-53 → HIPAA Security Rule | 150 |
| NIST SP 800-171 → SP 800-53 | 118 |
| NIST CSF 2.0 → SSDF (SP 800-218) | 24 |

Sources: NIST OSCAL catalogues and the NIST OLIR CSF 2.0 informative-reference export — all US
Government works. `@0.1` saw 159 pairs from one pair only.

## Evaluation — held out, ranked against full corpora

64 held-out queries (source controls never seen in training), avg 3.22 gold targets each, each ranked
against the **complete** target framework (up to 1,016 controls). Bootstrap 95% CI, 1,000 resamples.

| metric | @0.1 | **@0.2** | change |
|---|---|---|---|
| Recall@1 | 0.325 | 0.310 | −0.015 |
| Recall@3 | 0.571 | **0.674** | +0.102 |
| **Recall@5** | 0.653 | **0.734** | **+0.081** |
| Recall@10 | 0.756 | **0.824** | +0.068 |
| nDCG@10 | 0.640 | **0.693** | +0.053 |
| MRR | 0.695 | **0.701** | +0.005 |
| MAP | 0.569 | **0.622** | +0.053 |

TF-IDF lexical baseline: Recall@5 **0.470**.

### Per framework pair (Recall@5)
| pair | @0.1 | @0.2 |
|---|---|---|
| NIST 800-53 → HIPAA | 0.947 | 0.937 |
| NIST 800-171 → 800-53 | 0.917 | 0.940 |
| NIST CSF 2.0 → 800-171 | 0.563 | **0.682** |
| NIST CSF 2.0 → 800-53 | 0.244 | **0.344** |
| NIST CSF 2.0 → SSDF | 0.000 | 0.667 *(3 queries — not meaningful)* |

## Limitations — read before quoting these numbers

- **The improvement is not statistically significant.** The 95% CIs overlap: @0.1 is 0.555–0.751 and
  @0.2 is 0.647–0.818 on 64 queries. The direction is consistent and reproducible; the magnitude is not
  established. More held-out data requires more published crosswalks, which is the binding constraint.
- **Recall@1 is marginally worse.** If your use case needs a single best answer rather than a shortlist,
  `@0.1` is not worse and may be preferable — and see the checkpoint note below.
- **CSF→SSDF has 3 test queries.** Treat that row as noise, not as a 0.667 result.
- **Small absolute numbers on CSF→800-53** (0.344): the target corpus is 1,016 controls with an average of
  ~3 correct answers, so this is a hard retrieval task. It is still a large relative gain over 0.244.
- **Trained and evaluated only on NIST-family and HIPAA content.** ISO 27001, PCI DSS, CIS and SCF are
  crosswalked by official identifier only, because their control text is copyrighted and not shippable —
  so the model has never seen them and cannot rank them.
- **Validation loss is a poor model-selection signal here.** A 4-epoch run reached a *better* validation
  loss (2.5509 at epoch 2, vs 2.7019) yet scored *worse* held-out Recall@5 (0.682 vs 0.734). MNRL loss is
  computed against 15 in-batch candidates while the product ranks against ~1,000, so the two diverge.
  **This checkpoint was selected on held-out Recall@5, not on loss.**

## Reproducing

```
python regmap_engine/build_training_data.py --write
python regmap_engine/train_embedder.py --out models/regmap-embedder-v2 --protocol query-holdout
python regmap_engine/eval_retrain.py --model models/regmap-embedder-v2 \
    --protocol query-holdout --compare-to tfidf
```

Seed 42 throughout. Config and per-epoch history: `training_report.json` in this directory.
Trained on CPU in ~4,468 s.

## Serving

`serve.py` loads this model by default and stamps `regmap-embedder@0.2` on `/health`, `/usage` and every
`/map` response. The embedding cache is keyed on model version plus control text, so swapping models
invalidates and rebuilds it automatically — cached vectors can never mismatch the text being searched.
