"""
RegMap crosswalk engine — HTTP API.

Serves the compliance control catalog as a microservice:
  GET  /health              — liveness + which methods are available
  GET  /frameworks          — every registered framework: coverage, licence access, hub flag
  GET  /pairs               — every framework pair this instance can answer, and by what route
  POST /map                 — rank a target framework's controls for a control / free-text intent
  POST /eval                — retrieval metrics for a pair (Recall@k / nDCG@k / MRR / MAP)
  POST /map/bulk            — map a whole control set; coverage % and the official gap list
  POST /exercise            — set a graded mapping exercise (candidates only, no answer)
  POST /exercise/grade      — score a submission against the official crosswalk and reveal
  POST /auth/register       — self-serve signup (free plan); sets an HttpOnly session cookie
  POST /auth/login          — sign in
  POST /auth/logout         — end the session server-side
  GET  /auth/session        — who am I (never 401s; a guest is a valid answer)
  POST /auth/keys           — issue an API key for the signed-in account
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
import base64
import hashlib
import hmac
import os
import random
import json as _json
import time
from pathlib import Path
from typing import List, Optional

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import auth
import billing
import catalog as cat
import compute_units as cu
from eval_crosswalk import rank_tfidf, rank_bm25, score, aggregate

HERE = Path(__file__).resolve().parent
# The product website. Defaults to the engine's own web/ so the engine still runs standalone; the
# unified entry point (../main.py) points this at the repo-level web/ shell so the whole platform
# shares one front end.
WEB = Path(os.environ.get("REGMAP_WEB_DIR") or (HERE / "web"))
EMB_CACHE = HERE / "catalog" / ".embeddings"   # derived vectors; gitignored, safe to delete
# Defaults to the retrained model. regmap-embedder (@0.1) stays on disk untouched because the DTRAP
# paper's figures are reproducible only against it -- point REGMAP_MODEL there to reproduce them.
MODEL = os.environ.get("REGMAP_MODEL", str((HERE.parent / "models" / "regmap-embedder-v2")))
DEVICE = os.environ.get("REGMAP_DEVICE") or None   # None => auto (cuda if visible, else cpu)

# Framework ids the operator holds a licence for. Default empty => licence-required content is refused.
LICENSED = {s.strip() for s in os.environ.get("REGMAP_LICENSED", "").split(",") if s.strip()}

# --- versioning (reproducibility): stamp what produced every result -------------------------------
VERSION = {
    "engine": os.environ.get("REGMAP_ENGINE_VERSION", "0.2"),
    "model": os.environ.get("REGMAP_MODEL_VERSION", "regmap-embedder@0.2"),
}

# --- usage metering (per-use hardware billing) ----------------------------------------------------
GPU_CU_MULT = float(os.environ.get("REGMAP_GPU_CU_MULT", "8"))
BILLABLE = {"/map", "/eval"}   # endpoints that consume model compute
_usage = {"requests": 0, "cpu_seconds": 0.0, "gpu_seconds": 0.0, "compute_units": 0.0, "by_path": {}}

# /docs, /redoc and /openapi.json expose the whole API surface, so they are served from
# admin-gated routes below rather than mounted publicly by FastAPI.
app = FastAPI(title="RegMap crosswalk engine", version=VERSION["engine"],
              docs_url=None, redoc_url=None, openapi_url=None)

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
    """Record attributed usage after a billable request completes.

    The Compute Unit is computed by the ENDPOINT (it depends on corpus size and how much work was
    actually done) and left on `request.state.work_units`; this middleware turns that into a charge,
    persists it against the account, and returns the derivation in headers. Wall-clock is still
    measured but only as cost-of-goods telemetry -- it is never the billed quantity.
    """
    t0 = time.perf_counter()
    resp = await call_next(request)
    units = getattr(request.state, "work_units", None)
    if units is None:
        return resp

    dt = time.perf_counter() - t0
    gpu = _on_gpu()
    charge = cu.quantise(units, gpu)
    principal = getattr(request.state, "principal", None)

    if principal:
        try:
            billing.record_usage(
                principal, request.url.path, charge, units, "gpu" if gpu else "cpu", round(dt, 4),
                detail=getattr(request.state, "billed_detail", None),
                engine_version=VERSION["engine"], model_version=VERSION["model"])
        except Exception as e:
            # A ledger failure must be loud: unbilled usage is lost revenue, not a cosmetic problem.
            print(f"BILLING-ERROR could not record usage for {principal.get('account_id')}: {e}",
                  flush=True)
            resp.headers["x-regmap-billing"] = "record-failed"

    resp.headers["x-regmap-compute-units"] = f"{charge:.4f}"
    resp.headers["x-regmap-work-units"] = f"{units:.4f}"
    resp.headers["x-regmap-device"] = "gpu" if gpu else "cpu"
    resp.headers["x-regmap-account"] = str(principal.get("account_id")) if principal else "unknown"
    print("METER " + _json.dumps({
        "account_id": principal.get("account_id") if principal else None,
        "api_key_id": principal.get("id") if principal else None,
        "path": request.url.path, "compute_units": charge, "work_units": round(units, 4),
        "device": "gpu" if gpu else "cpu", "seconds": round(dt, 4),
        "engine": VERSION["engine"], "model": VERSION["model"]}), flush=True)
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
    for w in billing.startup():
        print(f"[regmap] WARNING: {w}", flush=True)
    print(f"[regmap] billing: {'ENFORCED' if auth.REQUIRE_AUTH else 'open (REGMAP_REQUIRE_AUTH=false)'}"
          f" · db={'sqlite' if billing.is_sqlite() else 'postgres'}", flush=True)
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


def _require(fid, what, need_text=True):
    """Resolve a framework and enforce licence access. Raises HTTPException.

    `need_text=False` allows a mapping-only framework (ids and official mappings, no shippable control
    text — ISO 27001, PCI DSS, CIS, SCF). Those cannot be ranked but can still be looked up.
    """
    r = _resolve_fid(fid)
    if r is None:
        raise HTTPException(404, f"unknown {what} framework '{fid}' (see GET /frameworks)")
    access = _registry[r].get("access", "public")
    if access == "licence-required" and r not in LICENSED:
        raise HTTPException(403, f"'{r}' content requires a licence; set REGMAP_LICENSED to enable it")
    if need_text and r not in _controls:
        if cat.resolve(r, r)[0] is None and not any(r in p for p in cat.available_mappings()):
            raise HTTPException(409, f"framework '{r}' is registered but nothing is imported for it yet")
        raise HTTPException(409, f"'{r}' is mapping-only: its control text is not shippable, so it "
                                 f"cannot be ranked. Pass a `source_id` to get its official mappings.")
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
    """Liveness only, deliberately minimal and unauthenticated.

    k8s startup, readiness AND liveness probes all target this path, so requiring a credential here
    would leave every pod permanently unready and take the deployment down. The detail that used to
    live here -- model filesystem path, device, framework list -- moved to /health/detail behind the
    admin scope, because it is operator information.
    """
    return {"status": "ok"}


@app.get("/health/detail")
def health_detail(principal=Depends(auth.require_admin)):
    """Full diagnostic state. Admin scope."""
    return {"status": "ok", "version": VERSION, "embedder": bool(_model),
            "model": MODEL if _model else None,
            "device": str(_model.device) if _model is not None else None,
            "frameworks": list(_controls), "pairs": len(cat.reachable_pairs()),
            "method": "embed" if _model else "tfidf",
            "auth_enforced": auth.REQUIRE_AUTH,
            "billing_db": "sqlite" if billing.is_sqlite() else "postgres",
            "cu_model": cu.explain(cu.map_units(1000, 5), _on_gpu())}


@app.get("/usage")
def usage(principal=Depends(auth.require_admin)):
    """Operator view of this replica. Admin scope.

    Per-account billing figures come from the ledger via /me or /admin/accounts, not from here -- this
    is process-local and tells you nothing authoritative about a customer.
    """
    return {"version": VERSION, "scope": "this replica, since start",
            "billable": False,
            "billing_note": "process-local. Authoritative usage is in the ledger (see /me).",
            **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in _usage.items()}}


@app.get("/me")
def me(principal=Depends(auth.require_key)):
    """The caller's own account, plan, keys and current-period usage — read from the ledger.

    This is the figure a customer can reconcile a bill against, because it is derived from the same
    immutable usage_events rows the invoice is.
    """
    if principal["account_id"] == "anonymous":
        return {"account_id": "anonymous", "authenticated": False,
                "note": "auth is disabled on this instance (REGMAP_REQUIRE_AUTH=false); usage is "
                        "recorded against a shared anonymous account.",
                "usage": billing.period_usage("anonymous"),
                "plan": {"id": principal["plan_id"], "monthly_cu": principal["monthly_cu"]}}
    summary = billing.account_summary(principal["account_id"])
    if not summary:
        raise HTTPException(404, "account not found")
    a = summary["account"]
    used = summary["usage"]["compute_units"]
    allowance = float(a["monthly_cu"])
    return {
        "account_id": a["id"], "email": a["email"], "authenticated": True,
        "plan": {"id": a["plan_id"], "name": a["plan_name"], "monthly_cu": allowance,
                 "allow_overage": bool(a["allow_overage"]),
                 "overage_cu_price": float(a["overage_cu_price"])},
        "usage": summary["usage"],
        "remaining_cu": (None if allowance == float("inf") else round(max(0.0, allowance - used), 4)),
        "pct_used": (None if allowance == float("inf") else round(100 * used / allowance, 1)
                     if allowance else None),
        "by_path": summary["by_path"],
        "keys": [{k: v for k, v in key.items() if k != "key_hash"} for key in summary["keys"]],
        "version": VERSION,
    }


@app.get("/frameworks")
def frameworks():
    """The coverage roadmap. `controls: 0` means registered but not imported — render as coming soon.
    `access` is the licensing wall: public | paraphrase-only | licence-required."""
    out = []
    for fid, f in sorted(_registry.items(), key=lambda kv: (-kv[1]["controls"], kv[0])):
        access = f.get("access", "public")
        out.append({"id": fid, "name": f.get("name", fid), "family": f.get("family"),
                    "version": f.get("version"), "controls": f["controls"],
                    "planned_controls": int(f.get("planned", 0)),
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
    """Every pair answerable right now, and how.

    `route`     direct | inverted | derived via <hub>
    `rankable`  false for a mapping-only target: the official mappings are returned, but there is no
                control text to rank against (see GET /frameworks -> text).
    """
    out = []
    for a, b, route in cat.reachable_pairs(include_mapping_only=True):
        if _registry.get(a, {}).get("access") == "licence-required" and a not in LICENSED:
            continue
        if _registry.get(b, {}).get("access") == "licence-required" and b not in LICENSED:
            continue
        out.append({"source": a, "target": b, "route": route,
                    "source_framework": _registry.get(a, {}).get("name", a),
                    "target_framework": _registry.get(b, {}).get("name", b),
                    "authoritative": route in ("direct", "inverted"),
                    "rankable": b in _controls,
                    "source_controls": _registry.get(a, {}).get("controls", 0),
                    "target_controls": _registry.get(b, {}).get("controls", 0)})
    rankable = sum(1 for p in out if p["rankable"])
    return {"version": VERSION, "count": len(out), "rankable": rankable,
            "mapping_only": len(out) - rankable, "pairs": out}


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
def map_control(req: MapReq, request: Request,
                principal=Depends(auth.require_key)):
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

    # A mapping-only target (ISO 27001, PCI DSS, CIS, SCF) has no text to rank, but its official
    # mappings are still answerable from a source control id. Allow that case through.
    want = req.target or tgt
    lookup_only = bool(req.source_id) and (_resolve_fid(want) or "") not in _controls
    tgt = _require(want, "target", need_text=not lookup_only)
    if req.source or src:
        src = _require(req.source or src, "source")

    if lookup_only:
        if not src:
            raise HTTPException(400, "a mapping-only target needs `source` and `source_id`")
        # No encoding happens on this path -- it is a crosswalk lookup, so it must not be billed as
        # though the model ran.
        request.state.work_units = cu.MIN_CU
        request.state.billed_detail = f"{src}->{tgt} official-mapping lookup"
        ids, route = cat.official_targets(src, tgt, req.source_id)
        if ids is None:
            raise HTTPException(404, f"no mapping and no hub route from '{src}' to '{tgt}'")
        return {"source": src, "target": tgt,
                "source_framework": _registry[src].get("name", src),
                "target_framework": _registry[tgt].get("name", tgt),
                "query": {"text": None, "source_id": req.source_id},
                "method": "official-mapping", "version": VERSION,
                "text_available": False,
                "note": f"'{tgt}' control text is not shippable ("
                        f"{_registry[tgt].get('access')}), so results cannot be ranked. These are the "
                        f"official mapped identifiers.",
                "official": {"route": route, "authoritative": route in ("direct", "inverted"),
                             "provenance": "official", "target_ids": ids},
                "results": [{"id": i, "title": "", "text": "", "score": None, "official": True}
                            for i in ids]}

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

    # Charge for the retrieval this request implies, and refuse up front if the caller is out of
    # allowance -- so an over-quota request cannot consume the compute first.
    units = cu.map_units(len(_controls[tgt]), req.top_k)
    auth.enforce_quota(principal, cu.quantise(units, _on_gpu()))
    request.state.work_units = units
    request.state.billed_detail = f"{src or '-'}->{tgt} top_k={req.top_k}"

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
def eval_pair(req: EvalReq, request: Request,
              principal=Depends(auth.require_key)):
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

    # Evaluation encodes EVERY query against the whole corpus, making it the most expensive call in
    # the service. It is rate-limited in auth.RATE_LIMITS and bounded here.
    if len(gold) > EVAL_MAX_QUERIES:
        raise HTTPException(413, detail={
            "error": "evaluation set too large for a single request",
            "queries": len(gold), "max": EVAL_MAX_QUERIES,
            "remedy": "use regmap_engine/eval_retrain.py offline for full-corpus evaluation"})
    units = cu.eval_units(len(gold), len(corpus))
    auth.enforce_quota(principal, cu.quantise(units, _on_gpu()))
    request.state.work_units = units
    request.state.billed_detail = f"{src}->{tgt} queries={len(gold)} corpus={len(corpus)}"

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


# =====================================================================================================
# BULK MAPPING + GAP ANALYSIS  — the GRC-team surface
# =====================================================================================================

class BulkReq(BaseModel):
    source: str = Field(..., description="source framework id")
    target: str = Field(..., description="target framework id")
    source_ids: Optional[List[str]] = Field(
        None, description="controls to map; omit for the whole source framework (capped)")
    top_k: int = Field(5, ge=1, le=25)


# Bulk encodes one query per control, so it is by far the heaviest endpoint. Cap it rather than let a
# single request tie up a worker for minutes — the UI pages through instead.
BULK_MAX = int(os.environ.get("REGMAP_BULK_MAX", "150"))
# /eval encodes every query in the set against the full corpus, so it is bounded too.
EVAL_MAX_QUERIES = int(os.environ.get("REGMAP_EVAL_MAX_QUERIES", "200"))


@app.post("/map/bulk")
def map_bulk(req: BulkReq, request: Request,
             principal=Depends(auth.require_key)):
    """Map a whole control set in one pass and report coverage and gaps.

    Answers the question a GRC team actually has — "we comply with X, so where does that leave us
    against Y, and what is missing?" — rather than one control at a time.

    `gaps` are target provisions that NO control in the submitted set maps to, computed from the
    official crosswalk. That is the defensible number: it says nothing about the model, only about the
    published mapping, so it can go into a report.
    """
    src = _require(req.source, "source")
    tgt_resolved = _resolve_fid(req.target)
    rankable = (tgt_resolved or "") in _controls
    tgt = _require(req.target, "target", need_text=rankable)

    mapping, route = cat.resolve(src, tgt)
    ids = req.source_ids or sorted(_controls[src])
    truncated = len(ids) > BULK_MAX
    ids = ids[:BULK_MAX]

    tgt_ctl = _controls.get(tgt, {})
    # Worst case is every submitted control needing a ranking pass; gate on that so admission is
    # decided before any encoding happens.
    auth.enforce_quota(principal, cu.quantise(
        cu.bulk_units(len(ids), len(tgt_ctl) or 1, req.top_k), _on_gpu()))

    rows, covered = [], set()
    for sid in ids:
        if sid not in _controls[src]:
            continue
        official = sorted({t for t in (mapping or {}).get(sid, {}).get("targets", set())
                           if not tgt_ctl or t in tgt_ctl})
        covered.update(official)
        row = {"source_id": sid, "title": _controls[src][sid]["title"],
               "official": official, "official_count": len(official), "suggested": []}
        # Only rank when the target has text, and only for controls with no official answer — that is
        # where a suggestion adds something rather than restating the crosswalk.
        if rankable and not official and _model is not None and tgt in _emb:
            import numpy as np
            cids, mat = _emb[tgt]
            q = _model.encode([_controls[src][sid]["text"]], normalize_embeddings=True,
                              show_progress_bar=False)[0]
            sims = mat @ np.asarray(q)
            order = sorted(range(len(cids)), key=lambda i: -sims[i])[:req.top_k]
            row["suggested"] = [{"id": cids[i], "score": round(float(sims[i]), 4)} for i in order]
        rows.append(row)

    # Bill for what actually reached the encoder, not for every control submitted: controls answered
    # from the crosswalk cost a dictionary lookup, and charging model rates for them would overbill.
    ranked = sum(1 for r in rows if r["suggested"])
    units = cu.bulk_units(len(rows), len(tgt_ctl) or 1, req.top_k, n_ranked=ranked)
    request.state.work_units = units
    request.state.billed_detail = f"{src}->{tgt} controls={len(rows)} ranked={ranked}"

    universe = set(tgt_ctl) if tgt_ctl else {t for v in (mapping or {}).values() for t in v["targets"]}
    gaps = sorted(universe - covered)
    with_official = sum(1 for r in rows if r["official"])

    return {
        "source": src, "target": tgt, "route": route,
        "source_framework": _registry[src].get("name", src),
        "target_framework": _registry[tgt].get("name", tgt),
        "authoritative": route in ("direct", "inverted"),
        "rankable": rankable,
        "version": VERSION,
        "counts": {
            "controls_submitted": len(rows),
            "with_official_mapping": with_official,
            "without_official_mapping": len(rows) - with_official,
            "target_universe": len(universe),
            "target_covered": len(covered),
            "target_gaps": len(gaps),
        },
        "coverage_pct": round(100 * len(covered) / len(universe), 1) if universe else None,
        "gaps": [{"id": g, "title": tgt_ctl.get(g, {}).get("title", "")} for g in gaps],
        "rows": rows,
        "truncated": truncated,
        "cap": BULK_MAX,
        "note": (f"Only the first {BULK_MAX} controls were mapped; pass explicit source_ids to page "
                 f"through the rest." if truncated else None),
    }


# =====================================================================================================
# GRADED EXERCISE  — the learner surface
# =====================================================================================================
# The answer never reaches the browser. /exercise returns a shuffled candidate set plus a signed token
# describing what was asked; /exercise/grade re-derives the official answer from the catalog and scores
# the submission. The token is HMAC-signed so it cannot be edited to change the question, and it carries
# no answer, so decoding it reveals nothing the learner cannot already see.

_EX_SECRET = os.environ.get("REGMAP_EXERCISE_SECRET", "").encode() or os.urandom(32)


def _sign(payload):
    raw = _json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    body = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    sig = hmac.new(_EX_SECRET, body.encode(), hashlib.sha256).hexdigest()[:32]
    return body + "." + sig


def _unsign(token):
    try:
        body, sig = token.rsplit(".", 1)
    except ValueError:
        raise HTTPException(400, "malformed exercise token")
    expect = hmac.new(_EX_SECRET, body.encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(sig, expect):
        raise HTTPException(400, "exercise token failed verification (was it edited?)")
    pad = "=" * (-len(body) % 4)
    return _json.loads(base64.urlsafe_b64decode(body + pad))


class ExerciseReq(BaseModel):
    source: str
    target: str
    source_id: Optional[str] = Field(None, description="omit to be given a random control")
    distractors: int = Field(8, ge=2, le=20,
                             description="plausible wrong options mixed in with the correct ones")


@app.post("/exercise")
def exercise(req: ExerciseReq, request: Request,
             principal=Depends(auth.require_key)):
    """Set a graded control-mapping exercise. Returns candidates in random order and no answer.

    The candidate set is every official target plus `distractors` plausible wrong ones drawn from the
    model's nearest non-answers. Including all official targets matters: if candidates were only the
    model's top-k, any gold target the model missed would be unreachable and a perfect score
    impossible — that would grade the model, not the learner.
    """
    src = _require(req.source, "source")
    tgt = _require(req.target, "target")
    mapping, route = cat.resolve(src, tgt)
    if not mapping:
        raise HTTPException(404, f"no official mapping from '{src}' to '{tgt}' to grade against")

    tgt_ctl = _controls[tgt]
    gradable = [s for s, v in mapping.items()
                if s in _controls[src] and any(t in tgt_ctl for t in v["targets"])]
    if not gradable:
        raise HTTPException(404, "no control in this pair has an official target we hold")

    units = cu.exercise_units(len(tgt_ctl), req.distractors)
    auth.enforce_quota(principal, cu.quantise(units, _on_gpu()))
    request.state.work_units = units
    request.state.billed_detail = f"exercise {src}->{tgt} distractors={req.distractors}"

    sid = req.source_id or random.choice(sorted(gradable))
    if sid not in mapping or sid not in _controls[src]:
        raise HTTPException(404, f"'{sid}' has no official mapping to grade against")
    answer = sorted({t for t in mapping[sid]["targets"] if t in tgt_ctl})

    # Distractors are the model's nearest non-answers, so wrong options are genuinely tempting rather
    # than obviously absurd. Falls back to random sampling when no embedder is loaded.
    wrong = []
    if _model is not None and tgt in _emb:
        import numpy as np
        cids, mat = _emb[tgt]
        q = _model.encode([_controls[src][sid]["text"]], normalize_embeddings=True,
                          show_progress_bar=False)[0]
        sims = mat @ np.asarray(q)
        for i in sorted(range(len(cids)), key=lambda i: -sims[i]):
            if cids[i] not in answer:
                wrong.append(cids[i])
            if len(wrong) >= req.distractors:
                break
    else:
        pool = [c for c in tgt_ctl if c not in answer]
        wrong = random.sample(pool, min(req.distractors, len(pool)))

    candidates = list(answer) + wrong
    random.shuffle(candidates)
    token = _sign({"src": src, "tgt": tgt, "sid": sid, "cands": candidates})

    return {
        "token": token,
        "source": src, "target": tgt,
        "source_framework": _registry[src].get("name", src),
        "target_framework": _registry[tgt].get("name", tgt),
        "route": route, "authoritative": route in ("direct", "inverted"),
        "prompt": {"id": sid, "title": _controls[src][sid]["title"],
                   "text": _controls[src][sid]["text"]},
        "candidates": [{"id": c, "title": tgt_ctl[c]["title"], "text": tgt_ctl[c]["text"]}
                       for c in candidates],
        "instructions": ("Select every provision of " + _registry[tgt].get("name", tgt) +
                         " that this control maps to. There may be more than one, and some options do "
                         "not map at all."),
        "version": VERSION,
    }


class GradeReq(BaseModel):
    token: str
    selected: List[str] = Field(default_factory=list)


@app.post("/exercise/grade")
def exercise_grade(req: GradeReq,
                   principal=Depends(auth.require_key)):
    """Score a submission against the official crosswalk and reveal the answer.

    Graded on precision, recall and F1 rather than raw correctness, because the task is
    multi-relevant: selecting everything would score perfect recall and near-zero precision, and that
    is precisely the habit an auditor must not have.
    """
    p = _unsign(req.token)
    src, tgt, sid = p["src"], p["tgt"], p["sid"]
    if src not in _controls or tgt not in _controls:
        raise HTTPException(409, "the catalog changed since this exercise was set")

    mapping, route = cat.resolve(src, tgt)
    answer = {t for t in (mapping or {}).get(sid, {}).get("targets", set()) if t in _controls[tgt]}
    offered = set(p["cands"])
    picked = {s for s in req.selected if s in offered}   # ignore anything not actually offered

    tp = picked & answer
    fp = picked - answer
    fn = answer - picked
    precision = len(tp) / len(picked) if picked else 0.0
    recall = len(tp) / len(answer) if answer else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    PASS = 0.70

    ctl = _controls[tgt]

    def detail(ids):
        return [{"id": i, "title": ctl.get(i, {}).get("title", "")} for i in sorted(ids)]

    return {
        "source": src, "target": tgt, "source_id": sid, "route": route,
        "authoritative": route in ("direct", "inverted"),
        "score": {"precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3),
                  "pass_threshold": PASS, "passed": f1 >= PASS},
        "counts": {"official": len(answer), "selected": len(picked),
                   "correct": len(tp), "missed": len(fn), "incorrect": len(fp)},
        "correct": detail(tp), "missed": detail(fn), "incorrect": detail(fp),
        "official_answer": detail(answer),
        "nice_task": "T0267 - assess control implementation and map to requirements",
        "version": VERSION,
    }


# =====================================================================================================
# OPERATOR SURFACE  — admin scope only
# =====================================================================================================
# FastAPI's built-in /docs was disabled at construction because it publishes the entire API surface.
# These re-serve it behind the admin scope rather than removing the capability altogether.

@app.get("/openapi.json", include_in_schema=False)
def openapi_json(principal=Depends(auth.require_admin)):
    return JSONResponse(get_openapi(title=app.title, version=app.version, routes=app.routes))


@app.get("/docs", include_in_schema=False)
def docs(principal=Depends(auth.require_admin)):
    return get_swagger_ui_html(openapi_url="/openapi.json", title=app.title + " — API")


@app.get("/admin/accounts", include_in_schema=False)
def admin_accounts(principal=Depends(auth.require_admin)):
    """Every account and its current-period consumption."""
    out = []
    for a in billing.list_accounts():
        out.append({**a, "usage": billing.period_usage(a["id"])})
    return {"count": len(out), "accounts": out, "period": billing.period_now()}


@app.get("/admin/accounts/{account_id}", include_in_schema=False)
def admin_account(account_id: str, principal=Depends(auth.require_admin)):
    s = billing.account_summary(account_id)
    if not s:
        raise HTTPException(404, "account not found")
    s["keys"] = [{k: v for k, v in key.items() if k != "key_hash"} for key in s["keys"]]
    return s


class RebuildReq(BaseModel):
    account_id: str
    period: str = Field(..., description="YYYY-MM")


@app.post("/admin/reconcile", include_in_schema=False)
def admin_reconcile(req: RebuildReq, principal=Depends(auth.require_admin)):
    """Recompute a period counter from the immutable event log.

    This is the reconciliation path that makes the ledger trustworthy rather than merely believed: the
    event log is the source of truth, so a counter that has drifted for any reason — a partial write, a
    restore, a manual correction — can be rebuilt from the events an invoice cites.
    """
    before = billing.period_usage(req.account_id, req.period)
    after = billing.rebuild_period(req.account_id, req.period)
    return {"account_id": req.account_id, "before": before, "after": after,
            "drift_cu": round(after["compute_units"] - before["compute_units"], 6)}


@app.get("/pricing")
def pricing():
    """How a Compute Unit is derived, and what each call costs. Public on purpose.

    A metered API that will not state its cost function cannot be budgeted against, so the formula and
    worked examples are published rather than being something a customer has to take on trust.
    """
    gpu = _on_gpu()
    examples = {}
    for fid in list(_controls)[:6]:
        n = len(_controls[fid])
        examples[f"/map into {fid} ({n} controls)"] = cu.quantise(cu.map_units(n, 5), gpu)
    return {
        "version": VERSION,
        "unit": "Compute Unit (CU)",
        "formula": "compute_units = work_units x device_rate",
        "work_units": {
            "per_query_encode": cu.ENCODE_UNITS,
            "per_1000_corpus_vectors_scored": cu.SCORE_UNITS_PER_1K,
            "per_returned_result": cu.RESULT_UNITS_PER_ITEM,
        },
        "device_rate": {"cpu": 1.0, "gpu": cu.GPU_RATE},
        "minimum_charge_cu": cu.MIN_CU,
        "deterministic": True,
        "billed_on": "the shape of the request",
        "not_billed_on": ("elapsed time, so server load, queueing and cold caches never change what "
                          "you are charged"),
        "examples_cu": examples,
        "free_endpoints": ["/health", "/frameworks", "/pairs", "/frameworks/{id}/controls",
                           "/pricing", "/me"],
        "plans": [{"id": pid, "name": name, "monthly_cu": (None if mc == float("inf") else mc),
                   "allow_overage": ov, "overage_cu_price": pr}
                  for pid, name, mc, ov, pr in billing.DEFAULT_PLANS],
    }


# =====================================================================================================
# ACCOUNTS — self-serve registration and login
# =====================================================================================================
# Guests may browse the catalog freely (/frameworks, /pairs, /pricing, control listings and every page).
# Anything that runs the model — mapping, gap analysis, graded practice — requires an account, because
# it consumes compute that has to be attributed to someone.
#
# The session lives in an HttpOnly cookie rather than in localStorage: script on the page cannot read
# it, so an XSS bug cannot exfiltrate a login. API keys remain available for programmatic use.

SESSION_COOKIE = "regmap_session"
# Secure cookies require HTTPS. Left off by default so http://localhost works during development; turn
# it on for any real deployment, which is what REGMAP_SECURE_COOKIES exists for.
SECURE_COOKIES = os.environ.get("REGMAP_SECURE_COOKIES", "false").lower() in ("1", "true", "yes")


def _set_session_cookie(resp, token):
    resp.set_cookie(
        SESSION_COOKIE, token,
        max_age=billing.SESSION_DAYS * 86400,
        httponly=True,          # unreadable from JavaScript
        samesite="lax",         # sent on top-level navigation, not on cross-site POSTs
        secure=SECURE_COOKIES,
        path="/")


class RegisterReq(BaseModel):
    email: str
    password: str = Field(..., min_length=10,
                          description="at least 10 characters; stored only as an scrypt hash")
    name: Optional[str] = None


@app.post("/auth/register")
def auth_register(req: RegisterReq, request: Request):
    """Create an account and sign in. Lands on the free plan, so the new user is metered from the start."""
    aid, err = billing.register(req.email, req.password, req.name)
    if err:
        raise HTTPException(400, detail=err)
    token, _, lerr = billing.login(req.email, req.password,
                                   request.headers.get("user-agent"))
    if lerr:
        raise HTTPException(500, detail="account created but sign-in failed; try logging in")
    body = {"account_id": aid, "email": req.email.strip().lower(), "plan": "free",
            "message": "account created"}
    resp = JSONResponse(body)
    _set_session_cookie(resp, token)
    return resp


class LoginReq(BaseModel):
    email: str
    password: str


@app.post("/auth/login")
def auth_login(req: LoginReq, request: Request):
    if not billing.verify_session(request.cookies.get(SESSION_COOKIE)):
        pass  # no existing session; continue to authenticate
    token, aid, err = billing.login(req.email, req.password, request.headers.get("user-agent"))
    if err:
        # 401 with a deliberately vague message — see billing.login: the same text is returned for an
        # unknown email and a wrong password, so this cannot be used to enumerate accounts.
        raise HTTPException(401, detail=err)
    resp = JSONResponse({"account_id": aid, "email": req.email.strip().lower(),
                         "message": "signed in"})
    _set_session_cookie(resp, token)
    return resp


@app.post("/auth/logout")
def auth_logout(request: Request):
    """End the session server-side and clear the cookie.

    The session row is deleted rather than merely un-cookied, so a copied cookie stops working too.
    """
    n = billing.logout(request.cookies.get(SESSION_COOKIE))
    resp = JSONResponse({"message": "signed out", "sessions_ended": n})
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return resp


@app.get("/auth/session")
def auth_session(request: Request,
                 authorization: str = Header(None),
                 x_api_key: str = Header(None)):
    """Who am I? Never 401s — a guest is a valid state, not an error.

    The UI calls this on every page load to decide whether to show "Sign in" or the account, so it has
    to answer for anonymous visitors too.
    """
    p = auth.resolve(authorization, x_api_key, request.cookies.get(SESSION_COOKIE))
    if not p:
        return {"authenticated": False, "guest": True,
                "auth_enforced": auth.REQUIRE_AUTH,
                "guest_can": ["browse frameworks", "view coverage and pair routes", "read pricing"],
                "requires_account": ["/map", "/map/bulk", "/eval", "/exercise"]}
    used = billing.period_usage(p["account_id"])["compute_units"]
    allowance = float(p["monthly_cu"])
    return {
        "authenticated": True, "guest": False,
        "auth_enforced": auth.REQUIRE_AUTH,
        "account_id": p["account_id"], "email": p.get("email"),
        "via": p.get("auth", "session"),
        "admin": "admin" in {s.strip() for s in (p.get("scopes") or "").split(",") if s.strip()},
        "plan": {"id": p.get("plan_id"), "name": p.get("name"),
                 "monthly_cu": (None if allowance == float("inf") else allowance),
                 "allow_overage": bool(p.get("allow_overage"))},
        "usage_cu": round(used, 4),
        "remaining_cu": (None if allowance == float("inf") else round(max(0.0, allowance - used), 4)),
        "pct_used": (None if allowance in (0, float("inf")) else round(100 * used / allowance, 1)),
    }


class KeyReq(BaseModel):
    label: Optional[str] = None


@app.post("/auth/keys")
def auth_create_key(req: KeyReq, principal=Depends(auth.require_key)):
    """Issue an API key for the signed-in account, for programmatic use.

    Deliberately cannot grant the admin scope: an admin key is an operator action, issued through the
    CLI. Otherwise any registered user could self-elevate to the operator surface.
    """
    if principal["account_id"] == "anonymous":
        raise HTTPException(401, detail="sign in to create an API key")
    kid, raw = billing.create_key(principal["account_id"], req.label or "web", scopes="")
    return {"key_id": kid, "api_key": raw,
             "note": "Copy this now, only its hash is stored, so it cannot be shown again."}
