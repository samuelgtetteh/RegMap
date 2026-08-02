"""
RegMap crosswalk engine — HTTP API.

Serves the multi-framework compliance crosswalk as a microservice:
  GET  /health              — liveness + which methods are available
  GET  /pairs               — the crosswalk pairs this instance has loaded
  POST /map                 — given free-text control intent, rank a target framework's controls
  POST /eval                — retrieval metrics for a loaded pair (Recall@k / nDCG@k / MRR / MAP)

The embedder (sentence-transformers) is loaded once at startup from $REGMAP_MODEL (default:
the released fine-tuned model dir). If the model/library is unavailable it degrades to TF-IDF.

Run locally:  uvicorn serve:app --host 0.0.0.0 --port 8000
"""
import os
import json as _json
import time
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from eval_crosswalk import load_pair, rank_tfidf, rank_bm25, score, aggregate

HERE = Path(__file__).resolve().parent
CROSSWALKS = HERE / "crosswalks"
WEB = HERE / "web"                 # the RegMap product website (served by this engine)
MODEL = os.environ.get("REGMAP_MODEL", str((HERE.parent / "models" / "regmap-embedder")))
DEVICE = os.environ.get("REGMAP_DEVICE") or None   # None => auto (cuda if visible, else cpu)

# --- versioning (reproducibility): stamp what produced every result -------------------------------
VERSION = {
    "engine": os.environ.get("REGMAP_ENGINE_VERSION", "0.1"),
    "model": os.environ.get("REGMAP_MODEL_VERSION", "regmap-embedder@0.1"),
}

# --- usage metering (per-use hardware billing) ----------------------------------------------------
# GPU seconds cost more than CPU seconds; a Compute Unit (CU) normalizes them so one meter bills both.
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
        # one structured billable event per request — a hosting platform scrapes these into billing
        print("METER " + _json.dumps({"path": request.url.path, "seconds": round(dt, 4),
              "device": "gpu" if gpu else "cpu", "compute_units": round(cu, 4),
              "engine": VERSION["engine"]}), flush=True)
    return resp

_pairs = {}          # name -> (meta, source, corpus, gold)
_corpus_emb = {}     # name -> (ids, matrix)
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


@app.on_event("startup")
def _startup():
    _load_model()
    if CROSSWALKS.is_dir():
        for d in sorted(p for p in CROSSWALKS.iterdir() if (p / "meta.json").exists()):
            try:
                meta, source, corpus, gold = load_pair(d)
                _pairs[d.name] = (meta, source, corpus, gold)
                if _model is not None:
                    import numpy as np
                    cids = list(corpus)
                    mat = _model.encode([corpus[c] for c in cids], normalize_embeddings=True,
                                        show_progress_bar=False)
                    _corpus_emb[d.name] = (cids, np.asarray(mat))
            except Exception as e:
                print(f"[regmap] skip pair {d.name}: {e}")
    dev = str(_model.device) if _model is not None else "cpu (tfidf)"
    print(f"[regmap] ready · model={'on' if _model else 'off (TF-IDF)'} · device={dev} · pairs={list(_pairs)}")


@app.get("/health")
def health():
    return {"status": "ok", "version": VERSION, "embedder": bool(_model),
            "model": MODEL if _model else None,
            "device": str(_model.device) if _model is not None else None,
            "pairs": list(_pairs), "method": "embed" if _model else "tfidf"}


@app.get("/usage")
def usage():
    """Cumulative metered compute since start — the basis for per-use hardware billing.
    compute_units (CU) normalize CPU vs GPU seconds (GPU-second = GPU_CU_MULT x CPU-second)."""
    return {"version": VERSION, "gpu_cu_multiplier": GPU_CU_MULT,
            **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in _usage.items()}}


@app.get("/pairs")
def pairs():
    return [{"name": n, **m[0], "source_items": len(m[1]), "corpus_items": len(m[2])}
            for n, m in _pairs.items()]


class MapReq(BaseModel):
    text: str = Field(..., description="free-text control / requirement intent to map")
    pair: str = Field(..., description="crosswalk pair name (see GET /pairs)")
    top_k: int = Field(5, ge=1, le=25)


@app.post("/map")
def map_control(req: MapReq):
    if req.pair not in _pairs:
        raise HTTPException(404, f"unknown pair '{req.pair}' (see GET /pairs)")
    meta, source, corpus, gold = _pairs[req.pair]
    if _model is not None and req.pair in _corpus_emb:
        import numpy as np
        cids, mat = _corpus_emb[req.pair]
        q = _model.encode([req.text], normalize_embeddings=True, show_progress_bar=False)[0]
        sims = mat @ np.asarray(q)
        order = sorted(range(len(cids)), key=lambda i: -sims[i])[:req.top_k]
        results = [{"id": cids[i], "text": corpus[cids[i]], "score": round(float(sims[i]), 4)} for i in order]
        method = "embed"
    else:  # TF-IDF fallback over {this text} vs corpus
        ranked = rank_tfidf({"_q": req.text}, corpus)["_q"][:req.top_k]
        results = [{"id": cid, "text": corpus[cid]} for cid in ranked]
        method = "tfidf"
    return {"pair": req.pair, "target_framework": meta.get("target_framework"),
            "method": method, "version": VERSION, "results": results}


class EvalReq(BaseModel):
    pair: str
    k: List[int] = Field(default_factory=lambda: [1, 3, 5, 10])


@app.post("/eval")
def eval_pair(req: EvalReq):
    if req.pair not in _pairs:
        raise HTTPException(404, f"unknown pair '{req.pair}'")
    meta, source, corpus, gold = _pairs[req.pair]
    out = {"pair": req.pair, "queries": len(gold), "methods": {}}
    methods = {"tfidf": rank_tfidf(source, corpus), "bm25": rank_bm25(source, corpus)}
    if _model is not None and req.pair in _corpus_emb:
        import numpy as np
        cids, mat = _corpus_emb[req.pair]
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
        out["methods"][name] = {k: round(v, 4) for k, v in aggregate(pq).items()}
    return out
