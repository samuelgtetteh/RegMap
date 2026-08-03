"""
RegMap crosswalk engine — HTTP API.

Serves the compliance control catalog as a microservice:
  GET  /health              — liveness + which methods are available
  GET  /frameworks          — every registered framework: coverage, licence access, hub flag
  GET  /pairs               — every framework pair this instance can answer, and by what route
  POST /map                 — rank a target framework's controls for a control / free-text intent
  POST /eval                — retrieval metrics for a pair (Recall@k / nDCG@k / MRR / MAP)
  GET  /usage               — cumulative metered compute (see the billing caveat below)

Backed by `catalog.py` (hub-and-spoke: control text once per framework, mappings by id), so a pair is
answerable direct, inverted, or derived through a hub. Corpora are embedded **once per framework**, not
once per pair — with the old pair-per-directory layout a framework appearing in k pairs was embedded k
times.

The embedder is loaded once at startup from $REGMAP_MODEL. Without it the service still answers on TF-IDF.

Licence gating: frameworks marked `licence-required` in the registry (HITRUST, COBIT) are refused unless
their id is listed in $REGMAP_LICENSED. Default-deny, so unlicensed content cannot ship by accident.

BILLING CAVEAT: /usage is in-memory and per-replica, and Compute Units are wall-clock — see
docs/hosted_saas_roadmap.md. Do not invoice from this; the customer-attributed meter is Phase B.

Run locally:  uvicorn serve:app --host 0.0.0.0 --port 8000
"""
import hashlib
import os
import json as _json
import time
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import catalog as cat
from eval_crosswalk import rank_tfidf, rank_bm25, score, aggregate

HERE = Path(__file__).resolve().parent
WEB = HERE / "web"                 # the RegMap product website (served by this engine)
EMB_CACHE = HERE / "catalog" / ".embeddings"   # derived vectors; gitignored, safe to delete
MODEL = os.environ.get("REGMAP_MODEL", str((HERE.parent / "models" / "regmap-embedder")))
DEVICE = os.environ.get("REGMAP_DEVICE") or None   # None => auto (cuda if visible, else cpu)

# Framework ids the operator holds a licence for. Default empty => licence-required content is refused.
LICENSED = {s.strip() for s in os.environ.get("REGMAP_LICENSED", "").split(",") if s.strip()}

# --- versioning (reproducibility): stamp what produced every result -------------------------------
VERSION = {
    "engine": os.environ.get("REGMAP_ENGINE_VERSION", "0.2"),
    "model": os.environ.get("REGMAP_MODEL_VERSION", "regmap-embedder@0.1"),
}

# --- usage metering (per-use hardware billing) ----------------------------------------------------
GPU_CU_MULT = float(os.environ.get("REGMAP_GPU_CU_MULT", "8"))
BILLABLE = {"/map", "/eval"}   # endpoints that consume model compute
_usage = {"requests": 0, "cpu_seconds": 0.0, "gpu_seconds": 0.0, "compute_units": 0.0, "by_path": {}}

app = FastAPI(title="RegMap crosswalk engine", version=VERSION["engine"])

# --- website (this product's UI is part of regmap_engine) -----------------------------------------
if (WEB / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=str(WEB / "assets")), name="assets")


@app.get("/", include_in_schema=False)
def home():
    """RegMap product home. The interactive API is at /docs."""
    f = WEB / "index.html"
    return HTMLResponse(f.read_text(encoding="utf-8")) if f.is_file() else HTMLResponse(
        "<h1>RegMap crosswalk engine</h1><p>API at <a href='/docs'>/docs</a></p>")


@app.get("/{page}.html", include_in_schema=False)
def web_page(page: str):
    """Any web/<page>.html — add a page by dropping a file, no route change needed."""
    if "/" in page or "\\" in page or ".." in page:
        raise HTTPException(status_code=404, detail="page not found")
    f = WEB / f"{page}.html"
    if not f.is_file():
        raise HTTPException(status_code=404, detail="page not found")
    return HTMLResponse(f.read_text(encoding="utf-8"))


def _on_gpu():
    try:
        return _model is not None and "cuda" in str(_model.device)
    except Exception:
        return False


@app.middleware("http")
async def _meter(request: Request, call_next):
    t0 = time.perf_counter()
    resp = await call_next(request)
    if request.url.path in BILLABLE:
        dt = time.perf_counter() - t0
        gpu = _on_gpu()
        cu = dt * (GPU_CU_MULT if gpu else 1.0)
        _usage["requests"] += 1
        _usage["gpu_seconds" if gpu else "cpu_seconds"] += dt
        _usage["compute_units"] += cu
        _usage["by_path"][request.url.path] = _usage["by_path"].get(request.url.path, 0) + 1
        resp.headers["x-regmap-compute-units"] = f"{cu:.4f}"
        resp.headers["x-regmap-device"] = "gpu" if gpu else "cpu"
        # NOTE: no account id — this cannot be invoiced from. See Phase B in the roadmap.
        print("METER " + _json.dumps({"path": request.url.path, "seconds": round(dt, 4),
              "device": "gpu" if gpu else "cpu", "compute_units": round(cu, 4),
              "engine": VERSION["engine"]}), flush=True)
    return resp


_registry = {}       # fid -> registry entry (name, family, access, hub, controls)
_controls = {}       # fid -> {cid: {"id","title","text"}}
_emb = {}            # fid -> (ids, matrix)   — one embedding pass per framework
_model = None


def _load_model():
    global _model
    try:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(MODEL, device=DEVICE)  # device=None => auto-select cuda/cpu
        return True
    except Exception as e:
        print(f"[regmap] embedder unavailable ({e}); using TF-IDF fallback")
        _model = None
        return False


def _signature(controls):
    """Cache key for one framework's embeddings: the model plus the exact text encoded.

    Any edit to a control statement, or a change of model, produces a different signature and so a
    miss — the cache can never serve vectors that do not match the text being searched.
    """
    h = hashlib.sha256()
    h.update(VERSION["model"].encode("utf-8"))
    for cid in sorted(controls):
        h.update(cid.encode("utf-8"))
        h.update(controls[cid]["text"].encode("utf-8"))
    return h.hexdigest()[:16]


def _embed_framework(fid, controls):
    """Embed one framework's catalog, reusing a cached matrix when the signature matches.

    Encoding dominates startup and grows with the catalog. Measured at 1,441 controls on CPU: ~27 s to
    encode from cold vs ~9 s warm (and the warm figure is mostly loading the model), so the cache is
    worth ~17 s per start today and more as frameworks are added. Only new or edited content is encoded.

    The image pre-warms this at build time — see docker/Dockerfile. At runtime the container is
    non-root against a root-owned /app, so a write here fails; that is logged, not fatal, and the
    engine simply encodes in-process.
    """
    import numpy as np
    cids = sorted(controls)
    sig = _signature(controls)
    path = EMB_CACHE / f"{fid}.{sig}.npz"
    if path.is_file():
        try:
            z = np.load(path, allow_pickle=False)
            if list(z["ids"]) == cids:
                return cids, z["mat"], "cached"
        except Exception as e:
            print(f"[regmap] ignoring unreadable embedding cache {path.name}: {e}")

    mat = np.asarray(_model.encode([controls[c]["text"] for c in cids],
                                   normalize_embeddings=True, show_progress_bar=False))
    try:
        EMB_CACHE.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, ids=np.array(cids), mat=mat)
        for old in EMB_CACHE.glob(f"{fid}.*.npz"):       # drop superseded signatures
            if old != path:
                old.unlink(missing_ok=True)
    except Exception as e:
        print(f"[regmap] could not write embedding cache for {fid}: {e}")
    return cids, mat, "encoded"


@app.on_event("startup")
def _startup():
    global _registry
    t0 = time.perf_counter()
    _load_model()
    _registry = cat.load_registry()
    stats = []
    for fid, f in _registry.items():
        if not f.get("controls"):
            continue                                  # registered but not yet imported
        _controls[fid] = cat.load_controls(fid)
        if _model is not None:
            cids, mat, how = _embed_framework(fid, _controls[fid])
            _emb[fid] = (cids, mat)
            stats.append(f"{fid}:{len(cids)}{'*' if how == 'encoded' else ''}")
    dev = str(_model.device) if _model is not None else "cpu (tfidf)"
    n = sum(len(c) for c in _controls.values())
    print(f"[regmap] ready in {time.perf_counter()-t0:.1f}s · "
          f"model={'on' if _model else 'off (TF-IDF)'} · device={dev} · "
          f"{len(_controls)} frameworks / {n} controls · pairs={len(cat.reachable_pairs())}")
    if stats:
        print(f"[regmap] embeddings: {' '.join(stats)}   (* = encoded this boot, else cache hit)")


# --- framework resolution + licence gating --------------------------------------------------------
def _resolve_fid(name):
    """Accept a framework id, or a legacy/loose name, and return the canonical id."""
    if not name:
        return None
    if name in _registry:
        return name
    cands = [f for f in _registry if f.startswith(name) or name.startswith(f)]
    return cands[0] if len(cands) == 1 else None


def _require(fid, what):
    """Resolve a framework and enforce licence access. Raises HTTPException."""
    r = _resolve_fid(fid)
    if r is None:
        raise HTTPException(404, f"unknown {what} framework '{fid}' (see GET /frameworks)")
    access = _registry[r].get("access", "public")
    if access == "licence-required" and r not in LICENSED:
        raise HTTPException(403, f"'{r}' content requires a licence; set REGMAP_LICENSED to enable it")
    if r not in _controls:
        raise HTTPException(409, f"framework '{r}' is registered but its catalog is not imported yet")
    return r


def _split_pair(pair):
    """Legacy support: '<source>__<target>' as used by the old pair-directory API."""
    a, _, b = (pair or "").partition("__")
    return (_resolve_fid(a), _resolve_fid(b)) if a and b else (None, None)


def _tfidf_scored(query, corpus, top_k):
    """Rank one query with TF-IDF, keeping the cosine scores.

    eval_crosswalk.rank_tfidf returns ids only (its callers just need an ordering), and its shape is
    depended on by /eval and the paper's scripts — so /map gets its own scored variant rather than
    changing that contract. Without this the fallback path returns no scores at all and the UI has
    nothing to show but a rank.
    """
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    cids = list(corpus)
    texts = [corpus[c] for c in cids]
    vec = TfidfVectorizer(stop_words="english").fit(texts + [query])
    sims = cosine_similarity(vec.transform([query]), vec.transform(texts))[0]
    order = sorted(range(len(cids)), key=lambda i: -sims[i])[:top_k]
    return [(cids[i], float(sims[i])) for i in order]


@app.get("/health")
def health():
    return {"status": "ok", "version": VERSION, "embedder": bool(_model),
            "model": MODEL if _model else None,
            "device": str(_model.device) if _model is not None else None,
            "frameworks": list(_controls), "pairs": len(cat.reachable_pairs()),
            "method": "embed" if _model else "tfidf"}


@app.get("/usage")
def usage():
    """Cumulative metered compute since start. NOT invoiceable — in-memory, per-replica, and CU is
    wall-clock. The customer-attributed meter is Phase B (docs/hosted_saas_roadmap.md)."""
    return {"version": VERSION, "gpu_cu_multiplier": GPU_CU_MULT,
            "billable": False, "billing_note": "in-memory, per-replica, no account attribution",
            **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in _usage.items()}}


@app.get("/frameworks")
def frameworks():
    """The coverage roadmap. `controls: 0` means registered but not imported — render as coming soon.
    `access` is the licensing wall: public | paraphrase-only | licence-required."""
    out = []
    for fid, f in sorted(_registry.items(), key=lambda kv: (-kv[1]["controls"], kv[0])):
        access = f.get("access", "public")
        out.append({"id": fid, "name": f.get("name", fid), "family": f.get("family"),
                    "version": f.get("version"), "controls": f["controls"],
                    "access": access, "hub": bool(f.get("hub")),
                    "available": bool(f["controls"]) and (access != "licence-required" or fid in LICENSED),
                    "license_note": f.get("license_note", "")})
    return {"version": VERSION, "count": len(out),
            "populated": sum(1 for f in out if f["controls"]), "frameworks": out}


@app.get("/frameworks/{fid}/controls")
def framework_controls(fid: str, include_text: bool = False):
    """Control ids + titles for one framework — powers the control picker and the practice exercises.
    `include_text=true` adds the full control statement (much larger payload)."""
    f = _require(fid, "")
    ctl = _controls[f]
    return {"framework": f, "name": _registry[f].get("name", f), "count": len(ctl),
            "controls": [{"id": c["id"], "title": c["title"],
                          **({"text": c["text"]} if include_text else {})}
                         for c in ctl.values()]}


@app.get("/pairs")
def pairs():
    """Every pair answerable right now, and how: direct | inverted | derived via <hub>."""
    out = []
    for a, b, route in cat.reachable_pairs():
        if _registry.get(a, {}).get("access") == "licence-required" and a not in LICENSED:
            continue
        if _registry.get(b, {}).get("access") == "licence-required" and b not in LICENSED:
            continue
        out.append({"source": a, "target": b, "route": route,
                    "source_framework": _registry.get(a, {}).get("name", a),
                    "target_framework": _registry.get(b, {}).get("name", b),
                    "authoritative": route in ("direct", "inverted"),
                    "source_controls": _registry.get(a, {}).get("controls", 0),
                    "target_controls": _registry.get(b, {}).get("controls", 0)})
    return {"version": VERSION, "count": len(out), "pairs": out}


class MapReq(BaseModel):
    target: Optional[str] = Field(None, description="target framework id (see GET /frameworks)")
    text: Optional[str] = Field(None, description="free-text control / requirement intent to map")
    source: Optional[str] = Field(None, description="optional source framework id")
    source_id: Optional[str] = Field(None, description="optional control id in `source`; its text "
                                                       "becomes the query and the official mapping "
                                                       "is returned alongside the ranking")
    pair: Optional[str] = Field(None, description="legacy: '<source>__<target>'")
    top_k: int = Field(5, ge=1, le=25)


@app.post("/map")
def map_control(req: MapReq):
    """Rank a target framework's controls for a control or free-text intent.

    Pass `source` + `source_id` and the response also carries the **official** mapping and flags which
    ranked results are in it. That single flag serves both audiences: an auditor sees model suggestions
    against the authoritative answer, and a learner's attempt can be graded against it.
    """
    src, tgt = (None, None)
    if req.pair and not req.target:
        src, tgt = _split_pair(req.pair)
        if not tgt:
            raise HTTPException(404, f"unknown pair '{req.pair}' (see GET /pairs)")
    tgt = _require(req.target or tgt, "target")
    if req.source or src:
        src = _require(req.source or src, "source")

    # the query text: an explicit control from the source framework, or free text
    if req.source_id:
        if not src:
            raise HTTPException(400, "source_id requires `source`")
        c = _controls[src].get(req.source_id)
        if c is None:
            raise HTTPException(404, f"control '{req.source_id}' not in '{src}'")
        query = c["text"]
    elif req.text:
        query = req.text
    else:
        raise HTTPException(400, "provide `text`, or `source` + `source_id`")

    # the authoritative answer, when a route exists between the two frameworks
    official, official_ids = None, set()
    if src:
        m, route = cat.resolve(src, tgt)
        if m is not None:
            if req.source_id:
                official_ids = {t for t in m.get(req.source_id, {}).get("targets", set())
                                if t in _controls[tgt]}
            official = {"route": route, "authoritative": route in ("direct", "inverted"),
                        "provenance": (m.get(req.source_id) or {}).get("provenance"),
                        "target_ids": sorted(official_ids)}

    ctl = _controls[tgt]
    if _model is not None and tgt in _emb:
        import numpy as np
        cids, mat = _emb[tgt]
        q = _model.encode([query], normalize_embeddings=True, show_progress_bar=False)[0]
        sims = mat @ np.asarray(q)
        order = sorted(range(len(cids)), key=lambda i: -sims[i])[:req.top_k]
        results = [{"id": cids[i], "title": ctl[cids[i]]["title"], "text": ctl[cids[i]]["text"],
                    "score": round(float(sims[i]), 4), "official": cids[i] in official_ids}
                   for i in order]
        method = "embed"
    else:  # TF-IDF fallback — scored, so the UI behaves the same with or without the embedder
        ranked = _tfidf_scored(query, {c: v["text"] for c, v in ctl.items()}, req.top_k)
        results = [{"id": c, "title": ctl[c]["title"], "text": ctl[c]["text"],
                    "score": round(s, 4), "official": c in official_ids} for c, s in ranked]
        method = "tfidf"

    return {"source": src, "target": tgt,
            "source_framework": _registry.get(src, {}).get("name") if src else None,
            "target_framework": _registry[tgt].get("name", tgt),
            "query": {"text": query, "source_id": req.source_id},
            "method": method, "version": VERSION,
            "official": official, "results": results}


class EvalReq(BaseModel):
    source: Optional[str] = None
    target: Optional[str] = None
    pair: Optional[str] = Field(None, description="legacy: '<source>__<target>'")
    k: List[int] = Field(default_factory=lambda: [1, 3, 5, 10])


@app.post("/eval")
def eval_pair(req: EvalReq):
    """Retrieval metrics for a pair. NOTE: this scores every gold query with no held-out split, so on a
    pair the embedder was fine-tuned on the numbers are inflated by leakage. It is a smoke test, not a
    benchmark — see docs/build_log.md Findings."""
    src, tgt = req.source, req.target
    if req.pair and not (src and tgt):
        src, tgt = _split_pair(req.pair)
    if not (src and tgt):
        raise HTTPException(400, "provide `source` + `target` (or legacy `pair`)")
    src, tgt = _require(src, "source"), _require(tgt, "target")

    try:
        meta, source, corpus, gold = cat.as_pair(src, tgt)
    except KeyError as e:
        raise HTTPException(404, str(e))

    out = {"source": src, "target": tgt, "route": meta["route"], "provenance": meta["provenance"],
           "queries": len(gold), "version": VERSION, "benchmark": False,
           "note": "no held-out split — smoke test only, not a benchmark", "methods": {}}
    methods = {"tfidf": rank_tfidf(source, corpus), "bm25": rank_bm25(source, corpus)}
    if _model is not None and tgt in _emb:
        import numpy as np
        cids, mat = _emb[tgt]
        ranked = {}
        for sid, txt in source.items():
            q = _model.encode([txt], normalize_embeddings=True, show_progress_bar=False)[0]
            sims = mat @ np.asarray(q)
            ranked[sid] = [cids[i] for i in sorted(range(len(cids)), key=lambda i: -sims[i])]
        methods["embed"] = ranked
    for name, ranked in methods.items():
        if ranked is None:
            continue
        pq = [score(ranked[sid], gold[sid], req.k) for sid in gold if sid in ranked]
        if pq:
            out["methods"][name] = {k: round(v, 4) for k, v in aggregate(pq).items()}
    return out
