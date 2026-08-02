"""
Generic multi-framework crosswalk evaluator — the reusable engine behind RegMap's expansion from
one pair (NIST 800-53 -> HIPAA) to *any* framework pair.

Given a crosswalk pair directory (see `regmap_engine/README.md` for the format), it ranks each source
control against the target framework's corpus and reports retrieval quality (Recall@k, MRR, MAP,
nDCG@k) for every available method. TF-IDF always runs (scikit-learn); BM25 and a sentence-embedding
model run if their libraries/weights are present, so the harness works today and improves as you add them.

    python regmap_engine/eval_crosswalk.py regmap_engine/crosswalks/nist_csf2__nist_80053
    python regmap_engine/eval_crosswalk.py <pair_dir> --model all-MiniLM-L6-v2 --k 1 3 5 10
"""
import argparse
import json
import math
from pathlib import Path


def _load_jsonl(p):
    return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def load_pair(pair_dir):
    d = Path(pair_dir)
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    source = {r["id"]: r["text"] for r in _load_jsonl(d / "source.jsonl")}
    corpus = {r["id"]: r["text"] for r in _load_jsonl(d / "corpus.jsonl")}
    gold = {}
    for r in _load_jsonl(d / "gold.jsonl"):
        gold.setdefault(r["source_id"], set()).update(r["target_ids"])
    # keep only source items that have at least one gold mapping into this corpus
    gold = {sid: {t for t in tids if t in corpus} for sid, tids in gold.items()}
    gold = {sid: tids for sid, tids in gold.items() if tids and sid in source}
    return meta, source, corpus, gold


# ---- metrics (multi-relevant aware) --------------------------------------------------------------
def _dcg(rels):
    return sum(rel / math.log2(i + 2) for i, rel in enumerate(rels))


def score(ranked_ids, relevant, ks):
    """ranked_ids: corpus ids best-first. relevant: set of gold target ids. Returns per-query metrics."""
    rels = [1 if cid in relevant else 0 for cid in ranked_ids]
    out = {}
    for k in ks:
        topk = rels[:k]
        out[f"recall@{k}"] = (sum(topk) / len(relevant)) if relevant else 0.0   # multi-relevant coverage
        out[f"hit@{k}"] = 1.0 if any(topk) else 0.0                              # single-relevant success
        ideal = _dcg(sorted(rels, reverse=True)[:k]) or 1.0
        out[f"ndcg@{k}"] = _dcg(topk) / ideal
    # MRR + MAP
    rr = 0.0
    for i, rel in enumerate(rels):
        if rel:
            rr = 1.0 / (i + 1); break
    out["mrr"] = rr
    hits = 0; ap = 0.0
    for i, rel in enumerate(rels):
        if rel:
            hits += 1; ap += hits / (i + 1)
    out["map"] = ap / len(relevant) if relevant else 0.0
    return out


def aggregate(per_query):
    keys = per_query[0].keys()
    return {k: sum(q[k] for q in per_query) / len(per_query) for k in keys}


# ---- ranking methods -----------------------------------------------------------------------------
def rank_tfidf(source, corpus):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    cids = list(corpus); ctexts = [corpus[c] for c in cids]
    sids = list(source); stexts = [source[s] for s in sids]
    vec = TfidfVectorizer(stop_words="english").fit(ctexts + stexts)
    C = vec.transform(ctexts); Q = vec.transform(stexts)
    sim = cosine_similarity(Q, C)
    return _rank_from_sim(sids, cids, sim)


def rank_bm25(source, corpus):
    try:
        from rank_bm25 import BM25Okapi
    except Exception:
        return None
    cids = list(corpus)
    tok = [corpus[c].lower().split() for c in cids]
    bm = BM25Okapi(tok)
    ranked = {}
    for s, txt in source.items():
        scores = bm.get_scores(txt.lower().split())
        ranked[s] = [cids[i] for i in sorted(range(len(cids)), key=lambda i: -scores[i])]
    return ranked


def rank_embed(source, corpus, model_name):
    try:
        from sentence_transformers import SentenceTransformer
        import numpy as np
    except Exception:
        return None
    try:
        m = SentenceTransformer(model_name)
    except Exception as e:
        print(f"  (embedder '{model_name}' unavailable: {e})"); return None
    cids = list(corpus)
    C = m.encode([corpus[c] for c in cids], normalize_embeddings=True, show_progress_bar=False)
    ranked = {}
    for s, txt in source.items():
        q = m.encode([txt], normalize_embeddings=True, show_progress_bar=False)[0]
        sims = C @ q
        ranked[s] = [cids[i] for i in sorted(range(len(cids)), key=lambda i: -sims[i])]
    return ranked


def _rank_from_sim(sids, cids, sim):
    ranked = {}
    for i, s in enumerate(sids):
        order = sorted(range(len(cids)), key=lambda j: -sim[i][j])
        ranked[s] = [cids[j] for j in order]
    return ranked


def evaluate(ranked, gold, ks):
    pq = [score(ranked[sid], gold[sid], ks) for sid in gold if sid in ranked]
    return aggregate(pq), len(pq)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pair_dir")
    ap.add_argument("--model", default="all-MiniLM-L6-v2", help="sentence-transformers model or local dir")
    ap.add_argument("--k", nargs="+", type=int, default=[1, 3, 5, 10])
    a = ap.parse_args()

    meta, source, corpus, gold = load_pair(a.pair_dir)
    print(f"Pair: {meta['source_framework']} -> {meta['target_framework']}")
    print(f"  provenance: {meta.get('provenance','?')}")
    print(f"  {len(source)} source items · {len(corpus)} corpus items · {len(gold)} evaluable queries\n")

    methods = {"TF-IDF": rank_tfidf(source, corpus),
               "BM25": rank_bm25(source, corpus),
               f"Embed ({a.model})": rank_embed(source, corpus, a.model)}

    hdr = ["method"] + [f"R@{k}" for k in a.k] + [f"nDCG@{max(a.k)}", "MRR", "MAP"]
    print("  ".join(h.ljust(20 if i == 0 else 7) for i, h in enumerate(hdr)))
    for name, ranked in methods.items():
        if ranked is None:
            print(name.ljust(20) + "  (not available — install the library / provide weights)"); continue
        agg, n = evaluate(ranked, gold, a.k)
        cells = [name.ljust(20)] + [f"{agg[f'recall@{k}']:.3f}".ljust(7) for k in a.k]
        cells += [f"{agg[f'ndcg@{max(a.k)}']:.3f}".ljust(7), f"{agg['mrr']:.3f}".ljust(7), f"{agg['map']:.3f}"]
        print("  ".join(cells))
    print("\nRecall@k = multi-relevant coverage (share of gold targets found in top-k), averaged over queries.")


if __name__ == "__main__":
    main()
