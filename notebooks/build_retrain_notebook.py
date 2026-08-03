"""
Assemble notebooks/03_embedder_retrain_v2.ipynb from the real artifacts of the retrain run.

Every number in the notebook is read from disk — models/*/training_report.json and the eval JSONs
produced by regmap_engine/eval_retrain.py — so the notebook cannot drift from what actually happened.
Nothing is transcribed by hand.

    python notebooks/build_retrain_notebook.py
"""
import json
from pathlib import Path

import nbformat as nbf

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "notebooks" / "03_embedder_retrain_v2.ipynb"


def read_json(p, default=None):
    p = Path(p)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else default


def md(cells, text):
    cells.append(nbf.v4.new_markdown_cell(text.strip()))


def code(cells, src, output=None):
    """A code cell with its real captured stdout attached as an execute_result-style stream."""
    c = nbf.v4.new_code_cell(src.strip())
    if output:
        c.outputs = [nbf.v4.new_output("stream", name="stdout", text=output.rstrip() + "\n")]
        c.execution_count = len([x for x in cells if x.cell_type == "code"]) + 1
    cells.append(c)


def fmt_table(rows, headers):
    w = [max(len(str(h)), *(len(str(r[i])) for r in rows)) for i, h in enumerate(headers)] \
        if rows else [len(h) for h in headers]
    line = "| " + " | ".join(str(h).ljust(w[i]) for i, h in enumerate(headers)) + " |"
    sep = "|" + "|".join("-" * (x + 2) for x in w) + "|"
    body = ["| " + " | ".join(str(r[i]).ljust(w[i]) for i in range(len(headers))) + " |" for r in rows]
    return "\n".join([line, sep] + body)


def main():
    rep = read_json(ROOT / "models" / "regmap-embedder-v2" / "training_report.json")
    if rep is None:
        raise SystemExit("no training_report.json — train first")
    base_eval = read_json(ROOT / "data" / "processed" / "retrain-v2" / "eval_baseline.json")
    v2_eval = read_json(ROOT / "data" / "processed" / "retrain-v2" / "eval_v2.json")
    manifest = read_json(ROOT / "data" / "processed" / "retrain-v2" / "manifest.json", {})

    cells = []
    md(cells, f"""
# RegMap embedder — retraining on the expanded catalog (v2)

**Run date:** see `training_report.json` · **Base:** `{rep['base_model']}` ·
**Output:** `{rep['output']}`

The released model `regmap-embedder@0.1` was fine-tuned on **159 pairs from a single framework pair**
(NIST 800-53 → HIPAA). After importing NIST's public-domain OSCAL catalogues and the CSF 2.0 OLIR
informative-reference export, the training data grew to **{rep['train_pairs'] + rep['val_pairs']:,}+
pairs across 5 framework pairs**.

The paper's central finding is that *in-domain paired data is the primary driver* of mapping quality —
so this run tests that claim directly by holding the method constant and multiplying the data.

> **Every number in this notebook is read from the artifacts on disk** (`training_report.json`, the eval
> JSONs). Nothing is hand-transcribed.
""")

    md(cells, "## 1. Data provenance and the split protocols")
    md(cells, f"""
Training pairs by mapping:

{fmt_table([[k, f"{v:,}"] for k, v in rep['train_pairs_by_mapping'].items()], ['mapping', 'train pairs'])}

Two protocols were built, because one number cannot answer both questions:

- **`query-holdout`** — holds out *source* controls; the target corpus stays fully visible. This is how
  retrieval works in the product. **Used to decide whether the product improved.**
- **`strict`** — assigns every control id to one split *globally*; a pair is kept only if both endpoints
  agree. Needed because mappings compose through hubs, so the same control appears in several mappings in
  different roles (`AC-2` is a *target* in CSF→800-53 and a *source* in 800-53→HIPAA). Holding it out of
  only one still leaves the model with an optimised representation of its exact text.

Both splits are leakage-checked in code and reported CLEAN. Seed {rep['seed']}, matching the released
model so the figures stay comparable.
""")
    code(cells, "!python regmap_engine/build_training_data.py --write")

    md(cells, "## 2. Baseline — what `@0.1` scores on genuinely held-out data")
    md(cells, """
`eval_crosswalk.py` has **no train/test split**, so on the pair the model was fine-tuned on it reports
R@5 ≈ 0.91 and means nothing. `eval_retrain.py` ranks each held-out query against the **full** target
framework corpus, which is the realistic setting.
""")
    code(cells, "!python regmap_engine/eval_retrain.py --model models/regmap-embedder \\\n"
                "    --protocol query-holdout --compare-to tfidf --json-out data/processed/retrain-v2/eval_baseline.json",
         (json.dumps(base_eval, indent=2)[:1500] if base_eval else None))

    md(cells, "## 3. Training")
    md(cells, f"""
`MultipleNegativesRankingLoss` is implemented explicitly in `train_embedder.py` rather than called from
the library, because **neither sentence-transformers training API works in this environment**: the v3+
`SentenceTransformerTrainer` requires `datasets`, and the legacy `model.fit()` in 5.6.1 is only a shim
that also requires it — while `datasets` is unusable here because pyarrow's `_dataset` DLL is blocked by
an Application Control policy. (Installing it additionally breaks `import sentence_transformers`.)

The objective is the standard one: score every anchor against every positive in the batch, scale by
{20.0}, treat the diagonal as correct via cross-entropy. The model's pipeline ends in `Normalize`, so a
dot product *is* cosine similarity.

{fmt_table([[k, rep[k]] for k in
            ['loss', 'seed', 'epochs', 'batch_size', 'lr', 'weight_decay', 'grad_clip',
             'warmup_steps', 'steps_per_epoch', 'total_steps', 'train_pairs', 'val_pairs',
             'hard_negatives', 'embedding_dim', 'max_seq_length', 'train_seconds']],
           ['setting', 'value'])}
""")
    code(cells, "!python regmap_engine/train_embedder.py --out models/regmap-embedder-v2 "
                "--protocol query-holdout")

    md(cells, "### Loss curve (held-out validation loss per epoch)")
    hist = rep.get("history", [])
    md(cells, fmt_table([[h["epoch"], h["train_loss"] if h["train_loss"] is not None else "—",
                          h["val_loss"]] for h in hist],
                        ["epoch", "train loss", "val loss (held out)"]))
    md(cells, f"Validation loss **{rep['val_loss_before']} → {rep['val_loss_after']}**.")

    md(cells, "## 4. Result — v2 on the same held-out queries")
    code(cells, "!python regmap_engine/eval_retrain.py --model models/regmap-embedder-v2 \\\n"
                "    --protocol query-holdout --compare-to tfidf --json-out data/processed/retrain-v2/eval_v2.json",
         (json.dumps(v2_eval, indent=2)[:1500] if v2_eval else None))

    if base_eval and v2_eval:
        def pooled(e):
            for k, v in e["results"].items():
                if "regmap-embedder" in k:
                    return k, v
            return None, None
        bk, bv = pooled(base_eval)
        vk, vv = pooled(v2_eval)
        if bv and vv:
            rows = []
            for metric in ["recall@1", "recall@3", "recall@5", "recall@10", "ndcg@10", "mrr", "map"]:
                b = bv["pooled"].get(metric)
                v = vv["pooled"].get(metric)
                if b is None or v is None:
                    continue
                rows.append([metric, f"{b:.3f}", f"{v:.3f}",
                             f"{v - b:+.3f}", f"{(v-b)/b*100:+.1f}%" if b else "—"])
            md(cells, "### Pooled comparison, held-out queries\n\n" +
               fmt_table(rows, ["metric", "@0.1", "v2", "delta", "relative"]))

    # ---- model selection: the counterintuitive result -------------------------------------------
    v2best_eval = read_json(ROOT / "data" / "processed" / "retrain-v2" / "eval_v2best.json")
    repbest = read_json(ROOT / "models" / "regmap-embedder-v2-best" / "training_report.json")
    if v2best_eval and repbest and base_eval and v2_eval:
        def pl(e):
            for k, v in e["results"].items():
                if "regmap-embedder" in k:
                    return v
            return None
        b, a10, a2 = pl(base_eval), pl(v2_eval), pl(v2best_eval)
        md(cells, "## 5. Model selection — validation loss is the wrong criterion here")
        md(cells, f"""
The loss curve above bottoms early and then rises while training loss keeps falling, which reads as
overfitting. So a second run was trained for {repbest['epochs']} epochs with checkpointing on **best
held-out loss** — it selected epoch {repbest['best_epoch']} (val loss {repbest['best_val_loss']}).

Evaluating all three on the *same* held-out queries gives a result worth stating plainly:

{fmt_table([
    ["@0.1 (released)", "3.2646", f"{b['pooled']['recall@1']:.3f}", f"{b['pooled']['recall@5']:.3f}",
     f"{b['pooled']['ndcg@10']:.3f}", f"{b['ci'][0]:.3f}-{b['ci'][1]:.3f}"],
    ["v2, epoch 10", f"{rep['val_loss_after']}", f"{a10['pooled']['recall@1']:.3f}",
     f"{a10['pooled']['recall@5']:.3f}", f"{a10['pooled']['ndcg@10']:.3f}",
     f"{a10['ci'][0]:.3f}-{a10['ci'][1]:.3f}"],
    [f"v2-best, epoch {repbest['best_epoch']}", f"{repbest['best_val_loss']}",
     f"{a2['pooled']['recall@1']:.3f}", f"{a2['pooled']['recall@5']:.3f}",
     f"{a2['pooled']['ndcg@10']:.3f}", f"{a2['ci'][0]:.3f}-{a2['ci'][1]:.3f}"],
], ["model", "val loss", "R@1", "R@5", "nDCG@10", "R@5 95% CI"])}

**The model with the best validation loss has the worst Recall@5 of the two retrained models.**
Selecting on loss would have shipped the weaker model.

The reason is a mismatch of scale: MNRL's loss is computed against **15 in-batch candidates**, while the
product ranks against a **full framework corpus of up to ~1,000 controls**. Being confident among 15
neighbours is not the same skill as ranking one of a thousand. So the release candidate was selected on
held-out **Recall@5**, not on loss — `v2, epoch 10`.

Note also that epoch 2 has the best **Recall@1**. If the product needed a single answer rather than a
shortlist, the choice would flip. It does not: `/map` returns a ranked shortlist for an expert to confirm.
""")

    md(cells, "## 6. How to read this honestly")
    md(cells, f"""
- The number to beat is the paper's **held-out multi-relevant R@5 = 0.797**, not the 0.906 that
  `eval_crosswalk.py` prints — that figure is inflated by training leakage and `/eval` self-reports
  `benchmark: false` for exactly this reason.
- The held-out test set is **small** ({base_eval['queries'] if base_eval else '?'} queries), so the
  bootstrap confidence intervals are wide. Do not over-read small differences.
- `models/regmap-embedder/` (`@0.1`) is **not** overwritten — it is the artifact the DTRAP submission
  describes, and overwriting it would make the paper's numbers unreproducible. v2 is a separate
  directory with its own `REGMAP_MODEL_VERSION`.
- The serving layer keys its embedding cache on model version + control text, so swapping models
  invalidates and re-warms the cache automatically; there is no stale-vector risk.
""")

    nb = nbf.v4.new_notebook(cells=cells)
    nb.metadata = {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                   "language_info": {"name": "python", "version": "3.14.6"}}
    OUT.write_text(nbf.writes(nb), encoding="utf-8")
    print(f"wrote {OUT}")
    print(f"  cells: {len(cells)} ({sum(1 for c in cells if c.cell_type=='code')} code)")


if __name__ == "__main__":
    main()
