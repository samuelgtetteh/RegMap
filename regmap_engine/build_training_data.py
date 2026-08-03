"""
Export the framework catalog into training/eval datasets for retraining the embedder.

Produces nothing new from thin air — it materialises what `catalog/` already holds into the shape
sentence-transformers wants, with an explicit, leakage-checked split. Run it, then train from the files.

    python build_training_data.py                       # report only
    python build_training_data.py --write

Output: data/processed/retrain-v2/
    manifest.json                     provenance, counts, seed, exclusions
    <protocol>/train.jsonl            {"anchor","positive",...traceability fields}
    <protocol>/val.jsonl
    <protocol>/test.jsonl
    corpus/<framework>.jsonl          {"id","text"} — the ranking corpus for eval

WHY TWO PROTOCOLS
They answer different questions and a single number cannot serve both:

  `query-holdout`  Hold out SOURCE controls; the target corpus stays fully visible. This mirrors how
                   retrieval actually works in the product (you rank against the whole framework) and
                   mirrors the paper's group-split-by-control. It is the **product quality** metric.

  `strict`         Every control id is assigned to exactly one split, globally across all mappings, and
                   a pair is kept only if BOTH endpoints landed in the same split. Nothing in test was
                   ever seen during training, in either role. It is the **generalisation** metric.

The strict protocol exists because mappings compose through hubs, so the same control appears in
several mappings in different roles. NIST 800-53 AC-2 is a *target* in CSF->800-53 and a *source* in
800-53->HIPAA; hold it out of only the second and the model has still optimised a representation for
its exact text. That is real leakage, and it is invisible unless you split on control identity globally.
Expect `strict` to be much smaller and its scores much lower. Both facts are correct.

WHAT IS EXCLUDED
Mappings whose target has no shippable control text (ISO 27001, PCI DSS, CIS, SCF) cannot be training
examples — there is no text to embed. Those ids are recorded in the manifest as recoverable-later: write
original paraphrases and they become trainable, which is the single largest expansion available.
"""
import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

import catalog as cat

OUT = Path(__file__).resolve().parent.parent / "data" / "processed" / "retrain-v2"
SEED = 42                      # matches the released model and the paper, so splits stay comparable
VAL_FRAC, TEST_FRAC = 0.15, 0.15


def collect():
    """All (source, target) pairs where both endpoints have real text, plus what we had to skip."""
    usable, skipped = [], []
    for a, b in cat.available_mappings():
        ca, cb = cat.load_controls(a), cat.load_controls(b)
        m = cat.load_mapping(a, b)
        if not ca or not cb:
            n = sum(len(v["targets"]) for v in m.values())
            skipped.append({"mapping": f"{a}__{b}", "pairs": n,
                            "reason": f"'{b if not cb else a}' has no shippable control text",
                            "access": cat.load_registry().get(b, {}).get("access")})
            continue
        for sid, entry in m.items():
            if sid not in ca:
                continue
            for tid in sorted(entry["targets"]):
                if tid not in cb:
                    continue
                usable.append({
                    "anchor": ca[sid]["text"], "positive": cb[tid]["text"],
                    "source": a, "source_id": sid, "target": b, "target_id": tid,
                    "mapping": f"{a}__{b}", "provenance": entry.get("provenance", "official"),
                })
    return usable, skipped


def split_query_holdout(pairs, rng):
    """Hold out source controls per mapping. Target corpus stays visible (that is how retrieval works)."""
    by_mapping = defaultdict(set)
    for p in pairs:
        by_mapping[p["mapping"]].add((p["source"], p["source_id"]))
    assign = {}
    for mapping, keys in by_mapping.items():
        ks = sorted(keys); rng.shuffle(ks)
        n_val = max(1, int(len(ks) * VAL_FRAC)); n_test = max(1, int(len(ks) * TEST_FRAC))
        for i, k in enumerate(ks):
            assign[(mapping, k)] = "val" if i < n_val else "test" if i < n_val + n_test else "train"
    out = defaultdict(list)
    for p in pairs:
        out[assign[(p["mapping"], (p["source"], p["source_id"]))]].append(p)
    return out


def split_strict(pairs, rng):
    """One split per control identity, globally. Keep a pair only if both endpoints agree."""
    controls = set()
    for p in pairs:
        controls.add((p["source"], p["source_id"]))
        controls.add((p["target"], p["target_id"]))
    ks = sorted(controls); rng.shuffle(ks)
    n_val = int(len(ks) * VAL_FRAC); n_test = int(len(ks) * TEST_FRAC)
    where = {}
    for i, k in enumerate(ks):
        where[k] = "val" if i < n_val else "test" if i < n_val + n_test else "train"
    out, dropped = defaultdict(list), 0
    for p in pairs:
        sa = where[(p["source"], p["source_id"])]
        sb = where[(p["target"], p["target_id"])]
        if sa != sb:
            dropped += 1                    # spans two splits -> would leak; discard
            continue
        out[sa].append(p)
    return out, dropped, where


def check_leakage(splits, key):
    """Assert the held-out side really is held out. Cheap insurance against a silent split bug."""
    sets = {s: {key(p) for p in ps} for s, ps in splits.items()}
    problems = []
    for a in ("val", "test"):
        for b in ("train",):
            overlap = sets.get(a, set()) & sets.get(b, set())
            if overlap:
                problems.append(f"{a}/{b} share {len(overlap)} keys e.g. {sorted(overlap)[:3]}")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    pairs, skipped = collect()
    reg = cat.load_registry()
    print(f"usable training pairs: {len(pairs)}  (from {len({p['mapping'] for p in pairs})} mappings)")
    for m in sorted({p["mapping"] for p in pairs}):
        print(f"    {m:<34} {sum(1 for p in pairs if p['mapping']==m):>5}")
    if skipped:
        print(f"\nexcluded (no shippable target text): {sum(s['pairs'] for s in skipped)} pairs")
        for s in skipped:
            print(f"    {s['mapping']:<34} {s['pairs']:>5}   {s['access']}")

    protocols = {}
    rng = random.Random(SEED)
    q = split_query_holdout(pairs, random.Random(SEED))
    protocols["query-holdout"] = (q, check_leakage(q, lambda p: (p["mapping"], p["source"], p["source_id"])), None)

    s, dropped, _ = split_strict(pairs, random.Random(SEED))
    protocols["strict"] = (s, check_leakage(s, lambda p: (p["source"], p["source_id"])), dropped)

    print()
    for name, (sp, problems, dropped) in protocols.items():
        tot = sum(len(v) for v in sp.values())
        print(f"{name}: train={len(sp['train'])} val={len(sp['val'])} test={len(sp['test'])}"
              f"  (total {tot}{f', {dropped} dropped as cross-split' if dropped else ''})")
        print(f"    leakage check: {'CLEAN' if not problems else 'FAILED -> ' + '; '.join(problems)}")

    if not a.write:
        print("\n(report only — re-run with --write)")
        return

    OUT.mkdir(parents=True, exist_ok=True)
    for name, (sp, _, _) in protocols.items():
        d = OUT / name; d.mkdir(exist_ok=True)
        for part in ("train", "val", "test"):
            with open(d / f"{part}.jsonl", "w", encoding="utf-8") as f:
                for p in sp[part]:
                    f.write(json.dumps(p, ensure_ascii=False) + "\n")

    cdir = OUT / "corpus"; cdir.mkdir(exist_ok=True)
    for fid in sorted(f for f in reg if cat.has_text(f)):
        ctl = cat.load_controls(fid)
        with open(cdir / f"{fid}.jsonl", "w", encoding="utf-8") as f:
            for cid in sorted(ctl):
                f.write(json.dumps({"id": cid, "text": ctl[cid]["text"]}, ensure_ascii=False) + "\n")

    (OUT / "manifest.json").write_text(json.dumps({
        "built_for": "retraining regmap-embedder beyond @0.1",
        "seed": SEED, "val_frac": VAL_FRAC, "test_frac": TEST_FRAC,
        "usable_pairs": len(pairs),
        "pairs_by_mapping": {m: sum(1 for p in pairs if p["mapping"] == m)
                             for m in sorted({p["mapping"] for p in pairs})},
        "protocols": {n: {k: len(v) for k, v in sp.items()} for n, (sp, _, _) in protocols.items()},
        "excluded": skipped,
        "corpora": {fid: len(cat.load_controls(fid)) for fid in sorted(reg) if cat.has_text(fid)},
        "baseline_to_beat": {
            "model": "regmap-embedder@0.1", "trained_on_pairs": 159,
            "note": "held-out multi-relevant R@5 0.797 per the DTRAP paper. Do NOT compare against "
                    "eval_crosswalk.py numbers, which have no held-out split.",
        },
        "do_not_overwrite": "models/regmap-embedder is the artifact the DTRAP paper describes. "
                            "Train to models/regmap-embedder-v2 and bump REGMAP_MODEL_VERSION.",
    }, indent=2), encoding="utf-8")

    print(f"\nwrote {OUT}")
    for p in sorted(OUT.rglob("*.jsonl")):
        print(f"    {p.relative_to(OUT)}  {sum(1 for _ in p.open(encoding='utf-8'))} rows")


if __name__ == "__main__":
    main()
