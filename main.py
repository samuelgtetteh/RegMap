"""
RegMap — single entry point for the whole platform.

The business plan puts the crosswalk engine at the center ("a working mapping
engine served as an API") and the scanning and evidence layer "around" it. This
module composes both into one ASGI app so there is exactly one way to start the
business:

    uvicorn main:app --host 0.0.0.0 --port 8000

What lives where, and why there is no route conflict:

  * The engine (regmap_engine/serve.py) is the base app and owns the front door.
    It brings the product website, billing, auth, metering, quotas and the
    canonical POST /map (rich, multi-framework, catalogue-backed). Everything
    below is added onto that same app, so it inherits the same request pipeline.

  * The surrounding platform (backend/) is a set of routers, each already
    carrying its own distinct prefix (/identity, /ics, /decision, /scan,
    /advisor, /agent), so none of them collide with the engine's routes. The
    engine's older prototype /map (nist_control -> HIPAA) is superseded by the
    catalogue /map and is deliberately not carried over; nothing calls it.

  * The compliance console (backend/dashboard) is served at /dashboard, since
    the engine already owns "/", "/assets" and "/<page>.html" for the product
    site. The console is self-contained and reaches the platform routers by
    their absolute paths, which resolve here.

Both package directories are flat module trees imported by bare name, and there
are no module-name collisions between them (verified), so putting both on
sys.path is unambiguous. Each platform surface is included defensively: a missing
optional dependency or model artifact disables just that surface rather than
taking the whole service down, so the single start point stays reliable.
"""
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for _p in (ROOT / "regmap_engine", ROOT / "backend"):
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

# The single front end is the repo-level web/ shell (the "Prove you can do the job" site), not the
# engine's standalone pages. serve.py reads this at import, so it must be set before the import below.
os.environ.setdefault("REGMAP_WEB_DIR", str(ROOT / "web"))

# The engine is the product; build on its app rather than beside it. sys.path
# must be set before this import, hence the placement.
from serve import app  # noqa: E402

from fastapi import HTTPException, Request  # noqa: E402
from fastapi.responses import HTMLResponse  # noqa: E402


# --- the surrounding platform: one router per surface, included defensively -----
_PLATFORM = [
    ("identity_api", "/identity   identity anomaly detector"),
    ("ics_api",      "/ics        OT/ICS intrusion detector"),
    ("decision_api", "/decision   record / decide / act decision layer"),
    ("scanner_api",  "/scan       SecureScan asset + CVE discovery"),
    ("advisor_api",  "/advisor    Control Advisor (scan, interview, evidence export)"),
    ("agent_api",    "/agent      on-prem scan agent"),
]
_loaded, _skipped = [], []
for _mod_name, _desc in _PLATFORM:
    try:
        _mod = __import__(_mod_name)
        app.include_router(_mod.router)
        _loaded.append(_desc)
    except Exception as _e:  # optional surface: degrade, do not crash the app
        _skipped.append(f"{_desc}  (unavailable: {_e})")


# --- the compliance console (Monitor . Assess . Help) ---------------------------
_DASHBOARD = ROOT / "backend" / "dashboard" / "index.html"


@app.get("/dashboard", include_in_schema=False)
def console():
    """The live compliance console that surrounds the engine (Monitor, Assess, Help).

    Served here because the engine owns the product site at "/"; this is the
    operator-facing app, reachable from the product once signed in.
    """
    if not _DASHBOARD.is_file():
        raise HTTPException(404, "console is not installed in this build")
    return HTMLResponse(_DASHBOARD.read_text(encoding="utf-8"))


# --- platform request auditing --------------------------------------------------
# The detectors record a verdict and stash its id on request.state; a live client
# attaches ground truth later through the returned X-Verdict-Id header, so that id
# has to be surfaced. This is scoped to platform paths on purpose: engine paths
# are metered by the engine's own middleware and must not also be written into the
# verdict trail.
try:
    from verdict_store import update_verdict_meta, record_request
    _VERDICTS = True
except Exception as _e:
    _VERDICTS = False
    _skipped.append(f"/decision request auditing  (unavailable: {_e})")

_PLATFORM_PREFIXES = ("/identity", "/ics", "/decision", "/scan", "/advisor", "/agent")


@app.middleware("http")
async def _platform_audit(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    if not _VERDICTS:
        return response
    path = request.url.path
    latency_ms = round((time.perf_counter() - start) * 1000, 3)
    client = request.client.host if request.client else None
    verdict_id = getattr(request.state, "verdict_id", None)
    if verdict_id:
        update_verdict_meta(verdict_id, latency_ms=latency_ms,
                            status=response.status_code, client=client, path=path)
        response.headers["X-Verdict-Id"] = str(verdict_id)
    elif path.startswith(_PLATFORM_PREFIXES):
        record_request(request.method, path, client, response.status_code, latency_ms)
    return response


# --- startup banner: state plainly what this one process is serving -------------
@app.on_event("startup")
def _banner():
    print("[regmap] single entry point: crosswalk engine + surrounding platform", flush=True)
    print("[regmap] front door '/'  ·  console '/dashboard'  ·  API docs '/docs' (admin)", flush=True)
    for _d in _loaded:
        print(f"[regmap]   + {_d}", flush=True)
    for _s in _skipped:
        print(f"[regmap]   - {_s}", flush=True)


# Convenience for `python main.py` (equivalent to the uvicorn command above).
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
