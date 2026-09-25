"""
Authentication, authorisation and rate limiting for the RegMap engine.

Provides the FastAPI dependencies the billable endpoints hang off:

    principal = Depends(require_key)     any active key
    principal = Depends(require_admin)   a key carrying the "admin" scope

AUTH IS OPT-IN BY CONFIGURATION, AND THAT IS DELIBERATE
`REGMAP_REQUIRE_AUTH` defaults to **false** so a self-hosted or air-gapped deployment keeps working
exactly as before — that tier pays for a licence, not per request, and forcing keys on it would break
it for no benefit. Set it to true for the hosted service. When it is false the endpoints resolve an
"anonymous" principal on the `free` plan, so metering and quotas still function and the code path is
identical in both modes rather than being untested in one of them.

RATE LIMITING IS PER PROCESS — READ THIS BEFORE RELYING ON IT
The limiter below is an in-memory token bucket, so with N replicas a caller effectively gets N times
the limit, and every restart forgets all state. That is honest protection against a runaway script and
nothing more. Real multi-tenant limiting needs shared state (Redis) and is not pretended here.
"""
import os
import threading
import time
from collections import defaultdict

from fastapi import Cookie, Depends, Header, HTTPException, Request

import billing

REQUIRE_AUTH = os.environ.get("REGMAP_REQUIRE_AUTH", "false").lower() in ("1", "true", "yes")

# Enforcement switches for quota (402) and rate limiting (429).
# PRE-LAUNCH: these default to OFF so nothing is blocked while we build. The live deployment turns them
# back ON explicitly (see regmap_engine/k8s/deployment.yaml). BEFORE PUBLISHING a live site, either keep
# them set to true in the deploy env or flip these defaults back to "true".
ENFORCE_QUOTA = os.environ.get("REGMAP_ENFORCE_QUOTA", "false").lower() in ("1", "true", "yes")
ENFORCE_RATE_LIMIT = os.environ.get("REGMAP_ENFORCE_RATE_LIMIT", "false").lower() in ("1", "true", "yes")

# Requests per minute per key, per endpoint class. Cheap reads are ungated.
RATE_LIMITS = {
    "/map": int(os.environ.get("REGMAP_RATE_MAP", "120")),
    "/exercise": int(os.environ.get("REGMAP_RATE_MAP", "120")),
    "/exercise/grade": int(os.environ.get("REGMAP_RATE_MAP", "120")),
    # Both of these can encode hundreds of texts per call, so they are limited far harder.
    "/map/bulk": int(os.environ.get("REGMAP_RATE_BULK", "10")),
    "/eval": int(os.environ.get("REGMAP_RATE_EVAL", "4")),
}

_buckets = defaultdict(list)      # (identity, path) -> [timestamps]
_lock = threading.Lock()

ANONYMOUS = {
    "id": None, "account_id": "anonymous", "scopes": "", "email": None, "plan_id": "free",
    "monthly_cu": float(os.environ.get("REGMAP_ANON_MONTHLY_CU", "300")),
    "allow_overage": False, "overage_cu_price": 0.0, "name": "Anonymous (auth disabled)",
}


def _bearer(authorization, x_api_key):
    """Accept either `Authorization: Bearer rk_...` or `X-API-Key: rk_...`."""
    if authorization:
        parts = authorization.split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1].strip()
        return authorization.strip()
    return (x_api_key or "").strip() or None


def rate_limit(identity, path):
    """Sliding-window limiter. Raises 429 with Retry-After when exceeded."""
    if not ENFORCE_RATE_LIMIT:
        return
    limit = RATE_LIMITS.get(path)
    if not limit:
        return
    now = time.monotonic()
    key = (identity, path)
    with _lock:
        hits = [t for t in _buckets[key] if now - t < 60.0]
        if len(hits) >= limit:
            retry = max(1, int(60.0 - (now - hits[0])) + 1)
            _buckets[key] = hits
            raise HTTPException(
                429, detail=f"rate limit exceeded for {path}: {limit} requests/minute",
                headers={"Retry-After": str(retry)})
        hits.append(now)
        _buckets[key] = hits


SESSION_COOKIE = "regmap_session"


def resolve(authorization=None, x_api_key=None, session=None):
    """Identify the caller from either credential type, or return None.

    Browser users log in and carry a session cookie; programmatic callers send an API key. Both produce
    the same principal shape, so quota, metering and scope checks downstream never need to care which
    was used. The API key is tried first, so an explicit key always wins over an ambient cookie.
    """
    raw = _bearer(authorization, x_api_key)
    if raw:
        p = billing.verify_key(raw)
        if p:
            p["auth"] = "api_key"
            return p
    if session:
        return billing.verify_session(session)
    return None


def require_key(request: Request,
                authorization: str = Header(None),
                x_api_key: str = Header(None),
                regmap_session: str = Cookie(None)):
    """Resolve the caller, enforce the rate limit, and check quota before any work runs.

    Attaches the principal to `request.state` so the endpoint and the metering middleware can both see
    it without re-querying.
    """
    principal = resolve(authorization, x_api_key, regmap_session)

    if REQUIRE_AUTH:
        if not principal:
            raise HTTPException(401, detail=(
                "sign in or send an API key. Guests can browse the catalog, but mapping, gap analysis "
                "and practice require an account."), headers={"WWW-Authenticate": "Bearer"})
    else:
        # Auth not enforced: still honour a credential when one is present, so a self-hosted operator
        # can opt into per-account attribution without switching the whole service into enforced mode.
        principal = principal or dict(ANONYMOUS)

    identity = principal.get("id") or principal["account_id"]
    rate_limit(identity, request.url.path)
    request.state.principal = principal
    return principal


def require_admin(principal=Depends(require_key)):
    """Admin scope. Refuses the anonymous principal outright, even when auth is disabled —
    otherwise turning auth off would silently expose the operator surface."""
    scopes = {s.strip() for s in (principal.get("scopes") or "").split(",") if s.strip()}
    if "admin" not in scopes:
        raise HTTPException(403, detail="this endpoint requires a key with the 'admin' scope")
    return principal


def enforce_quota(principal, estimate_cu):
    """Reject before doing the work if the caller is out of allowance.

    402 rather than 403: the caller is authenticated and permitted, they simply owe money — which is
    the distinction a client library needs in order to react correctly.
    """
    if not ENFORCE_QUOTA:
        # Development / pre-launch: never block on allowance. Usage is still metered for visibility.
        return {"allowance": float("inf"), "used": 0.0, "estimate": estimate_cu, "remaining": float("inf")}
    allowed, info = billing.check_quota(principal, estimate_cu)
    if not allowed:
        raise HTTPException(402, detail={
            "error": "monthly compute allowance exhausted",
            "plan": principal.get("plan_id"),
            "allowance_cu": info["allowance"],
            "used_cu": round(info["used"], 4),
            "this_request_cu": round(info["estimate"], 4),
            "remedy": "upgrade the plan or enable overage billing",
        })
    return info
