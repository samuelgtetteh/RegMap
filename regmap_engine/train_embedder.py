"""
Retrain the RegMap embedder on the expanded catalog.

Reproduces the objective and hyperparameters that produced regmap-embedder@0.1 (recorded in
notebooks/02: MiniLM base, MultipleNegativesRankingLoss, batch 16, 10 epochs, linear warmup over 10% of
steps, AdamW lr 2e-5, seed 42) and feeds it 9.2x the data — 1,459 pairs over 5 framework pairs instead
of 159 over 1.

WHY THE LOSS IS IMPLEMENTED HERE RATHER THAN CALLED FROM THE LIBRARY
Neither sentence-transformers training API works on this machine:
  * SentenceTransformerTrainer (v3+) requires `datasets`
  * the legacy model.fit() in 5.6.1 is only a shim that ALSO requires `datasets`
and `datasets` is unusable because pyarrow's `_dataset` DLL is blocked by an Application Control policy.
Installing it additionally breaks `import sentence_transformers` outright, so it must stay uninstalled.

Torch itself is fine, and MNRL is short, so the loop below implements it explicitly. The objective is
the standard one: for a batch of (anchor, positive) pairs, score every anchor against every positive in
the batch, scale by 20, and treat the diagonal as the correct answer via cross-entropy. Other rows'
positives are the in-batch negatives. The model's own pipeline (Transformer -> Pooling -> Normalize)
already yields unit-norm vectors, so a dot product IS cosine similarity.

    python train_embedder.py --out ../models/regmap-embedder-v2
    python train_embedder.py --out ../models/regmap-embedder-v2-hn --hard-negatives
"""
import argparse
import json
import math
import random
import time
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data" / "processed" / "retrain-v2"
SEED = 42
SCALE = 20.0          # sentence-transformers' MNRL default


def load(protocol, split):
    return [json.loads(l) for l in (DATA / protocol / f"{split}.jsonl").read_text(
        encoding="utf-8").splitlines() if l.strip()]


def load_corpus(fid):
    rows = [json.loads(l) for l in (DATA / "corpus" / f"{fid}.jsonl").read_text(
        encoding="utf-8").splitlines() if l.strip()]
    return {r["id"]: r["text"] for r in rows}


def encode_batch(model, texts, device):
    """Tokenise + forward, keeping gradients (model.encode() runs under no_grad)."""
    prep = getattr(model, "preprocess", None) or model.tokenize
    features = prep(texts)
    features = {k: (v.to(device) if hasattr(v, "to") else v) for k, v in features.items()}
    return model(features)["sentence_embedding"]


def mine_hard_negatives(model, rows, per_pair=1, top_k=30):
    """A control the current model ranks highly that is NOT gold.

    MNRL's in-batch negatives are random, so most are trivially easy and contribute little gradient.
    A hard negative sits near the decision boundary, which is where the model actually needs to learn.
    """
    import numpy as np
    gold = defaultdict(set)
    for r in rows:
        gold[(r["source"], r["source_id"], r["target"])].add(r["target_id"])
    corpora, enc = {}, {}
    for fid in {r["target"] for r in rows}:
        corpora[fid] = load_corpus(fid)
        ids = sorted(corpora[fid])
        enc[fid] = (ids, np.asarray(model.encode([corpora[fid][i] for i in ids],
                                                 normalize_embeddings=True, batch_size=64,
                                                 show_progress_bar=False)))
    out, found = [], 0
    for r in rows:
        ids, mat = enc[r["target"]]
        v = model.encode([r["anchor"]], normalize_embeddings=True, show_progress_bar=False)[0]
        sims = mat @ np.asarray(v)
        g = gold[(r["source"], r["source_id"], r["target"])]
        negs = []
        for i in sorted(range(len(ids)), key=lambda i: -sims[i])[:top_k]:
            if ids[i] not in g:
                negs.append(corpora[r["target"]][ids[i]])
                if len(negs) >= per_pair:
                    break
        out.append(negs)
        found += len(negs)
    return out, found


def val_loss(model, rows, batch, device):
    """Mean MNRL loss on the held-out val split — the honest signal that training is helping."""
    import torch
    model.eval()
    tot, n = 0.0, 0
    with torch.no_grad():
        for i in range(0, len(rows) - batch + 1, batch):
            chunk = rows[i:i + batch]
            a = encode_batch(model, [r["anchor"] for r in chunk], device)
            p = encode_batch(model, [r["positive"] for r in chunk], device)
            scores = a @ p.T * SCALE
            labels = torch.arange(len(chunk), device=device)
            tot += float(torch.nn.functional.cross_entropy(scores, labels)); n += 1
    model.train()
    return tot / max(n, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=str(HERE.parent / "models" / "regmap-embedder"))
    ap.add_argument("--from-scratch", action="store_true",
                    help="start from the original base encoder instead of the released model")
    ap.add_argument("--out", required=True)
    ap.add_argument("--protocol", default="query-holdout")
    ap.add_argument("--epochs", type=int, default=10)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--hard-negatives", action="store_true")
    a = ap.parse_args()

    import torch
    from torch.optim import AdamW
    from sentence_transformers import SentenceTransformer

    random.seed(SEED); torch.manual_seed(SEED)

    base = "sentence-transformers/all-MiniLM-L6-v2" if a.from_scratch else a.base
    model = SentenceTransformer(base)
    device = model.device
    print(f"base model      : {base}")
    print(f"device          : {device}")

    train_rows = load(a.protocol, "train")
    val_rows = load(a.protocol, "val")
    print(f"protocol        : {a.protocol}")
    print(f"train pairs     : {len(train_rows)}")
    print(f"val pairs       : {len(val_rows)}  (held out)")
    per_mapping = defaultdict(int)
    for r in train_rows:
        per_mapping[r["mapping"]] += 1
    for m, n in sorted(per_mapping.items()):
        print(f"    {m:<32} {n}")

    negs, n_found = None, 0
    if a.hard_negatives:
        t0 = time.perf_counter()
        negs, n_found = mine_hard_negatives(model, train_rows)
        print(f"hard negatives  : {n_found} mined in {time.perf_counter()-t0:.0f}s")

    idx = list(range(len(train_rows)))
    steps_per_epoch = len(idx) // a.batch
    total_steps = steps_per_epoch * a.epochs
    warmup = math.ceil(total_steps * 0.10)
    opt = AdamW(model.parameters(), lr=a.lr, weight_decay=0.01)

    def lr_at(step):                       # linear warmup then linear decay, as ST does
        if step < warmup:
            return step / max(1, warmup)
        return max(0.0, (total_steps - step) / max(1, total_steps - warmup))

    sched = torch.optim.lr_scheduler.LambdaLR(opt, lr_at)
    print(f"batch/epochs/lr : {a.batch} / {a.epochs} / {a.lr}")
    print(f"steps           : {total_steps} ({steps_per_epoch}/epoch, warmup {warmup})")

    v0 = val_loss(model, val_rows, a.batch, device)
    print(f"val loss before : {v0:.4f}")
    history = [{"epoch": 0, "train_loss": None, "val_loss": round(v0, 4)}]
    best_val, best_epoch = v0, 0

    model.train()
    t0 = time.perf_counter()
    for epoch in range(1, a.epochs + 1):
        random.shuffle(idx)
        run, nb = 0.0, 0
        for s in range(steps_per_epoch):
            chunk = [train_rows[i] for i in idx[s * a.batch:(s + 1) * a.batch]]
            hn = [negs[i] for i in idx[s * a.batch:(s + 1) * a.batch]] if negs else None

            anc = encode_batch(model, [r["anchor"] for r in chunk], device)
            pos = encode_batch(model, [r["positive"] for r in chunk], device)
            cands = pos
            if hn and any(hn):
                extra = [(h[0] if h else r["positive"]) for h, r in zip(hn, chunk)]
                cands = torch.cat([pos, encode_batch(model, extra, device)], dim=0)

            scores = anc @ cands.T * SCALE
            labels = torch.arange(len(chunk), device=device)
            loss = torch.nn.functional.cross_entropy(scores, labels)

            opt.zero_grad(); loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step(); sched.step()
            run += float(loss); nb += 1

        v = val_loss(model, val_rows, a.batch, device)
        best = v < best_val - 1e-6
        print(f"  epoch {epoch:>2}/{a.epochs}  train_loss={run/max(nb,1):.4f}  val_loss={v:.4f}"
              f"  lr={sched.get_last_lr()[0]:.2e}{'  <- best' if best else ''}")
        history.append({"epoch": epoch, "train_loss": round(run / max(nb, 1), 4),
                        "val_loss": round(v, 4), "best": best})
        # Keep the best epoch by held-out loss. Without this the run saves whatever the last epoch
        # happened to be, which on this data is well past the optimum (train loss keeps falling while
        # val loss rises from about epoch 3).
        if best:
            best_val, best_epoch = v, epoch
            model.save(str(Path(a.out)))

    secs = time.perf_counter() - t0
    out = Path(a.out)
    if best_epoch == 0:
        # never improved on the starting point: save anyway so the run is inspectable, but say so
        print("WARNING: no epoch beat the starting validation loss; saving the final state")
        model.save(str(out))

    report = {
        "base_model": base, "output": str(out), "protocol": a.protocol,
        "loss": "MultipleNegativesRankingLoss (explicit in-batch softmax, scale 20.0)",
        "seed": SEED, "epochs": a.epochs, "batch_size": a.batch, "lr": a.lr,
        "weight_decay": 0.01, "grad_clip": 1.0,
        "warmup_steps": warmup, "steps_per_epoch": steps_per_epoch, "total_steps": total_steps,
        "train_pairs": len(train_rows), "val_pairs": len(val_rows),
        "train_pairs_by_mapping": dict(sorted(per_mapping.items())),
        "hard_negatives": bool(a.hard_negatives), "hard_negatives_mined": n_found,
        "train_seconds": round(secs, 1),
        "embedding_dim": model.get_sentence_embedding_dimension(),
        "max_seq_length": model.max_seq_length,
        "val_loss_before": round(v0, 4),
        "val_loss_after": history[-1]["val_loss"],
        "best_epoch": best_epoch, "best_val_loss": round(best_val, 4),
        "saved_checkpoint": f"epoch {best_epoch} (best held-out loss)",
        "history": history,
    }
    (out / "training_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\ntrained in      : {secs:.0f}s")
    print(f"val loss        : {v0:.4f} -> {history[-1]['val_loss']:.4f} "
          f"(best {best_val:.4f} @ epoch {best_epoch})")
    print(f"saved           : {out}")


if __name__ == "__main__":
    main()
