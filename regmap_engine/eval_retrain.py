"""
Held-out evaluation for the embedder. The only numbers worth quoting.

`eval_crosswalk.py` scores every gold query with no train/test split, so on a pair the model was
fine-tuned on it reports ~0.9 and means nothing. This reads the held-out splits built by
build_training_data.py and ranks each test query against the FULL target framework corpus, which is the
realistic setting: in the product you rank against everything, not a shortlist.

    python eval_retrain.py --model ../models/regmap-embedder --protocol query-holdout
    python eval_retrain.py --model ../models/regmap-embedder-v2 --protocol strict --compare-to tfidf

Reports multi-relevant Recall@k / nDCG@k / MRR / MAP, per mapping and pooled, with bootstrap 95% CIs
(1,000 resamples, seed 42 — the paper's convention, so figures are comparable).
"""
import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

from eval_crosswalk import score, aggregate

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data" / "processed" / "retrain-v2"
BOOTSTRAP, SEED = 1000, 42


def load_split(protocol, split):
    """Group held-out rows into queries with their full gold target set."""
    rows = [json.loads(l) for l in (DATA / protocol / f"{split}.jsonl").read_text(
        encoding="utf-8").splitlines() if l.strip()]
    queries = {}
    for r in rows:
        key = (r["mapping"], r["source_id"])
        q = queries.setdefault(key, {"anchor": r["anchor"], "target": r["target"],
                                     "source": r["source"], "gold": set()})
        q["gold"].add(r["target_id"])
    return queries


def load_corpus(fid):
    p = DATA / "corpus" / f"{fid}.jsonl"
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    return {r["id"]: r["text"] for r in rows}


def ci(values, rng):
    """Bootstrap 95% CI of the mean. Small test sets make these wide; that is the point of showing them."""
    if not values:
        return (0.0, 0.0, 0.0)
    n = len(values)
    means = []
    for _ in range(BOOTSTRAP):
        means.append(sum(values[rng.randrange(n)] for _ in range(n)) / n)
    means.sort()
    return (sum(values) / n, means[int(.025 * BOOTSTRAP)], means[int(.975 * BOOTSTRAP)])


def rank_with_model(model, queries, corpora, ks):
    import numpy as np
    # Encode each target corpus once, not per query.
    enc = {}
    for fid, corpus in corpora.items():
        ids = sorted(corpus)
        mat = model.encode([corpus[i] for i in ids], normalize_embeddings=True,
                           show_progress_bar=False, batch_size=64)
        enc[fid] = (ids, np.asarray(mat))
    per_query = {}
    for key, q in queries.items():
        ids, mat = enc[q["target"]]
        v = model.encode([q["anchor"]], normalize_embeddings=True, show_progress_bar=False)[0]
        sims = mat @ np.asarray(v)
        order = sorted(range(len(ids)), key=lambda i: -sims[i])
        per_query[key] = score([ids[i] for i in order], q["gold"], ks)
    return per_query


def rank_with_tfidf(queries, corpora, ks):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    per_query = {}
    for fid, corpus in corpora.items():
        ids = sorted(corpus)
        texts = [corpus[i] for i in ids]
        qs = [(k, q) for k, q in queries.items() if q["target"] == fid]
        if not qs:
            continue
        vec = TfidfVectorizer(stop_words="english").fit(texts + [q["anchor"] for _, q in qs])
        C = vec.transform(texts)
        sims = cosine_similarity(vec.transform([q["anchor"] for _, q in qs]), C)
        for row, (k, q) in enumerate(qs):
            order = sorted(range(len(ids)), key=lambda i: -sims[row][i])
            per_query[k] = score([ids[i] for i in order], q["gold"], ks)
    return per_query


def report(name, per_query, ks, queries):
    rng = random.Random(SEED)
    print(f"\n  {name}")
    print("    " + "-" * 84)
    pooled = list(per_query.values())
    by_mapping = defaultdict(list)
    for (mapping, _), m in per_query.items():
        by_mapping[mapping].append(m)

    hdr = f"    {'set':<32}{'n':>4}" + "".join(f"{'R@'+str(k):>9}" for k in ks) + \
          f"{'nDCG@'+str(max(ks)):>11}{'MRR':>8}{'MAP':>8}"
    print(hdr)
    for label, ms in list(by_mapping.items()) + [("POOLED", pooled)]:
        agg = aggregate(ms)
        cells = "".join(f"{agg[f'recall@{k}']:>9.3f}" for k in ks)
        print(f"    {label:<32}{len(ms):>4}{cells}"
              f"{agg[f'ndcg@{max(ks)}']:>11.3f}{agg['mrr']:>8.3f}{agg['map']:>8.3f}")
    # CIs on the headline metric only — that is what gets quoted.
    k = 5 if 5 in ks else max(ks)
    mean, lo, hi = ci([m[f"recall@{k}"] for m in pooled], rng)
    print(f"    pooled R@{k} = {mean:.3f}  (95% CI {lo:.3f}-{hi:.3f}, {len(pooled)} queries,"
          f" {BOOTSTRAP} resamples)")
    return {"pooled_r@%d" % k: mean, "ci": (lo, hi), "n": len(pooled),
            "pooled": {m: round(v, 4) for m, v in aggregate(pooled).items()}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", help="path or name of a sentence-transformers model")
    ap.add_argument("--protocol", default="query-holdout", choices=["query-holdout", "strict"])
    ap.add_argument("--split", default="test", choices=["test", "val"])
    ap.add_argument("--k", nargs="+", type=int, default=[1, 3, 5, 10])
    ap.add_argument("--compare-to", nargs="*", default=[], choices=["tfidf"])
    ap.add_argument("--json-out")
    a = ap.parse_args()

    queries = load_split(a.protocol, a.split)
    corpora = {fid: load_corpus(fid) for fid in {q["target"] for q in queries.values()}}
    print(f"protocol={a.protocol} split={a.split}  {len(queries)} held-out queries")
    for fid, c in sorted(corpora.items()):
        print(f"    corpus {fid:<16} {len(c)} controls")
    avg_gold = sum(len(q['gold']) for q in queries.values()) / len(queries)
    print(f"    avg gold targets/query: {avg_gold:.2f}  (multi-relevant)")

    results = {}
    if "tfidf" in a.compare_to:
        results["TF-IDF"] = report("TF-IDF (lexical baseline)",
                                   rank_with_tfidf(queries, corpora, a.k), a.k, queries)
    if a.model:
        from sentence_transformers import SentenceTransformer
        m = SentenceTransformer(a.model)
        results[a.model] = report(f"{a.model}", rank_with_model(m, queries, corpora, a.k),
                                  a.k, queries)

    if a.json_out:
        Path(a.json_out).write_text(json.dumps(
            {"protocol": a.protocol, "split": a.split, "queries": len(queries),
             "results": {k: {kk: vv for kk, vv in v.items()} for k, v in results.items()}},
            indent=2, default=list), encoding="utf-8")
        print(f"\n  wrote {a.json_out}")


if __name__ == "__main__":
    main()
