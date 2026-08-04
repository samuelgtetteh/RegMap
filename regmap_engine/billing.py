"""
RegMap billing spine — accounts, API keys, attributed usage, quotas.

This is the layer the engine was missing: before it, compute was metered but attributed to nobody, so
`/usage` was diagnostics rather than billing. Everything here exists to answer one question defensibly:
**who consumed what, and are they allowed more?**

    DATABASE_URL=postgresql+psycopg://user:pass@host/regmap   # production
    DATABASE_URL=sqlite:///./regmap.db                        # default (development ONLY)

⚠️ SQLITE IS NOT SAFE FOR PRODUCTION HERE. `k8s/deployment.yaml` mounts no volume, so a SQLite file
lives in the container's writable layer and is destroyed on every restart, rollout and scale event —
silently discarding the usage records you bill from. Worse, with more than one replica each pod would
keep its own private ledger. Set DATABASE_URL to managed Postgres before charging anyone. `startup()`
logs a warning when it detects this combination.

DESIGN NOTES

*Keys are stored hashed.* A leaked database must not yield usable credentials, so only
sha256(secret) is persisted; the plaintext key is shown once at creation and never recoverable.

*Usage is double-entry.* Every billable call writes an immutable `usage_events` row AND increments a
`usage_periods` counter in the same transaction. The counter makes quota checks a single indexed read;
the event log makes any invoice auditable back to individual requests. If they ever disagree, the event
log is the truth and the counter can be rebuilt from it (`rebuild_period`).

*Quotas are checked before work, charged after.* An estimate gates admission so an over-quota caller is
rejected without consuming GPU; the actual cost is recorded once the work is done. The estimate and the
charge use the same deterministic function, so they agree unless the request changed shape.
"""
import hashlib
import os
import secrets
from datetime import datetime, timezone

from sqlalchemy import (Boolean, Column, DateTime, Float, ForeignKey, Integer, MetaData, String,
                        Table, Text, create_engine, func, insert, select, update)

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./regmap.db")

_engine = None
metadata = MetaData()

# ---- schema --------------------------------------------------------------------------------------
# Plans are rows, not code, so pricing can change without a deploy.
plans = Table(
    "plans", metadata,
    Column("id", String(32), primary_key=True),
    Column("name", String(64), nullable=False),
    Column("monthly_cu", Float, nullable=False),          # included allowance
    Column("allow_overage", Boolean, nullable=False, default=False),
    Column("overage_cu_price", Float, nullable=False, default=0.0),
    Column("created_at", DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)),
)

accounts = Table(
    "accounts", metadata,
    Column("id", String(40), primary_key=True),
    Column("email", String(255), nullable=False, unique=True),
    Column("name", String(255)),
    Column("plan_id", String(32), ForeignKey("plans.id"), nullable=False),
    Column("active", Boolean, nullable=False, default=True),
    Column("created_at", DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)),
)

api_keys = Table(
    "api_keys", metadata,
    Column("id", String(40), primary_key=True),
    Column("account_id", String(40), ForeignKey("accounts.id"), nullable=False, index=True),
    # sha256 of the secret. The plaintext is returned once at creation and never stored.
    Column("key_hash", String(64), nullable=False, unique=True, index=True),
    Column("prefix", String(16), nullable=False),          # shown in UIs so a key is identifiable
    Column("label", String(120)),
    Column("scopes", String(255), nullable=False, default=""),   # comma-separated; "admin" is special
    Column("active", Boolean, nullable=False, default=True),
    Column("created_at", DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)),
    Column("last_used_at", DateTime(timezone=True)),
    Column("revoked_at", DateTime(timezone=True)),
)

# Immutable audit log. One row per billable request — this is what an invoice must be traceable to.
usage_events = Table(
    "usage_events", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("account_id", String(40), ForeignKey("accounts.id"), nullable=False, index=True),
    Column("api_key_id", String(40)),
    Column("period", String(7), nullable=False, index=True),      # YYYY-MM
    Column("path", String(64), nullable=False),
    Column("compute_units", Float, nullable=False),
    Column("work_units", Float, nullable=False),
    Column("device", String(8), nullable=False),
    Column("seconds", Float, nullable=False),        # cost-of-goods telemetry, NOT the billed quantity
    Column("detail", Text),
    Column("engine_version", String(32)),
    Column("model_version", String(64)),
    Column("created_at", DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)),
)

# Rolled-up counter so a quota check is one indexed read rather than a scan of the event log.
usage_periods = Table(
    "usage_periods", metadata,
    Column("account_id", String(40), ForeignKey("accounts.id"), primary_key=True),
    Column("period", String(7), primary_key=True),
    Column("compute_units", Float, nullable=False, default=0.0),
    Column("requests", Integer, nullable=False, default=0),
    Column("updated_at", DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)),
)

DEFAULT_PLANS = [
    # id, name, monthly CU, overage allowed, price per CU past the allowance
    ("free", "Free", 300.0, False, 0.0),
    ("pro", "Pro", 5000.0, True, 0.002),
    ("team", "Team", 25000.0, True, 0.0015),
    ("selfhost", "Self-hosted", float("inf"), True, 0.0),
]


# ---- lifecycle -----------------------------------------------------------------------------------
def engine():
    global _engine
    if _engine is None:
        kw = {"future": True}
        if DATABASE_URL.startswith("sqlite"):
            # check_same_thread=False: uvicorn serves requests from a threadpool.
            kw["connect_args"] = {"check_same_thread": False}
        _engine = create_engine(DATABASE_URL, **kw)
    return _engine


def is_sqlite():
    return DATABASE_URL.startswith("sqlite")


def startup(replicas_hint=None):
    """Create tables if absent, seed plans, and warn loudly about unsafe configurations."""
    metadata.create_all(engine())
    with engine().begin() as c:
        have = {r[0] for r in c.execute(select(plans.c.id))}
        for pid, name, cu, over, price in DEFAULT_PLANS:
            if pid not in have:
                c.execute(insert(plans).values(id=pid, name=name, monthly_cu=cu,
                                               allow_overage=over, overage_cu_price=price))
    warnings = []
    if is_sqlite():
        warnings.append(
            "billing DB is SQLite. The k8s Deployment mounts no volume, so this file is destroyed on "
            "every restart/rollout and is per-replica. DO NOT BILL FROM THIS. Set DATABASE_URL to "
            "managed Postgres for production.")
    return warnings


# ---- keys ----------------------------------------------------------------------------------------
def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def create_account(email, name=None, plan_id="free"):
    aid = "acct_" + secrets.token_hex(10)
    with engine().begin() as c:
        c.execute(insert(accounts).values(id=aid, email=email, name=name, plan_id=plan_id,
                                          active=True))
    return aid


def create_key(account_id, label=None, scopes=""):
    """Return (key_id, plaintext_secret). The secret is not recoverable afterwards."""
    raw = "rk_" + secrets.token_urlsafe(32)
    kid = "key_" + secrets.token_hex(8)
    with engine().begin() as c:
        c.execute(insert(api_keys).values(
            id=kid, account_id=account_id, key_hash=_hash(raw), prefix=raw[:11],
            label=label, scopes=scopes, active=True))
    return kid, raw


def revoke_key(key_id):
    with engine().begin() as c:
        r = c.execute(update(api_keys).where(api_keys.c.id == key_id)
                      .values(active=False, revoked_at=datetime.now(timezone.utc)))
    return r.rowcount


def verify_key(raw):
    """Resolve a plaintext key to its account and plan, or None.

    Looks up by hash, so a stolen database yields no usable credential. Also rejects keys whose
    account has been deactivated, not just revoked keys — otherwise closing an account would leave its
    keys working.
    """
    if not raw:
        return None
    with engine().begin() as c:
        row = c.execute(
            select(api_keys.c.id, api_keys.c.account_id, api_keys.c.scopes, api_keys.c.active,
                   accounts.c.active.label("acct_active"), accounts.c.email, accounts.c.plan_id,
                   plans.c.monthly_cu, plans.c.allow_overage, plans.c.overage_cu_price, plans.c.name)
            .select_from(api_keys.join(accounts, api_keys.c.account_id == accounts.c.id)
                                 .join(plans, accounts.c.plan_id == plans.c.id))
            .where(api_keys.c.key_hash == _hash(raw))).mappings().first()
        if not row or not row["active"] or not row["acct_active"]:
            return None
        c.execute(update(api_keys).where(api_keys.c.id == row["id"])
                  .values(last_used_at=datetime.now(timezone.utc)))
    return dict(row)


# ---- usage + quota -------------------------------------------------------------------------------
def period_now():
    return datetime.now(timezone.utc).strftime("%Y-%m")


def period_usage(account_id, period=None):
    period = period or period_now()
    with engine().begin() as c:
        row = c.execute(select(usage_periods.c.compute_units, usage_periods.c.requests)
                        .where(usage_periods.c.account_id == account_id,
                               usage_periods.c.period == period)).first()
    return {"period": period, "compute_units": float(row[0]) if row else 0.0,
            "requests": int(row[1]) if row else 0}


def check_quota(principal, estimate):
    """Decide admission BEFORE the work runs.

    Returns (allowed, info). Rejecting up front is the point: an over-quota caller must not be able to
    consume GPU seconds and then be told no.
    """
    used = period_usage(principal["account_id"])["compute_units"]
    allowance = float(principal["monthly_cu"])
    projected = used + estimate
    if projected <= allowance:
        return True, {"used": used, "allowance": allowance, "estimate": estimate,
                      "overage": False, "remaining": allowance - projected}
    if principal["allow_overage"]:
        over = projected - max(allowance, used)
        return True, {"used": used, "allowance": allowance, "estimate": estimate,
                      "overage": True, "overage_cu": round(over, 4),
                      "overage_cost": round(over * float(principal["overage_cu_price"]), 6)}
    return False, {"used": used, "allowance": allowance, "estimate": estimate,
                   "overage": False, "remaining": max(0.0, allowance - used)}


def record_usage(principal, path, compute_units, work_units, device, seconds, detail=None,
                 engine_version=None, model_version=None):
    """Write the immutable event and bump the rollup counter in ONE transaction.

    Doing both atomically is what keeps the audit log and the quota counter consistent; if they ever
    diverge the event log is authoritative and the counter is rebuildable from it.
    """
    period = period_now()
    with engine().begin() as c:
        c.execute(insert(usage_events).values(
            account_id=principal["account_id"], api_key_id=principal.get("id"), period=period,
            path=path, compute_units=compute_units, work_units=work_units, device=device,
            seconds=seconds, detail=detail, engine_version=engine_version,
            model_version=model_version))
        existing = c.execute(select(usage_periods.c.compute_units)
                             .where(usage_periods.c.account_id == principal["account_id"],
                                    usage_periods.c.period == period)).first()
        if existing is None:
            c.execute(insert(usage_periods).values(
                account_id=principal["account_id"], period=period,
                compute_units=compute_units, requests=1,
                updated_at=datetime.now(timezone.utc)))
        else:
            c.execute(update(usage_periods)
                      .where(usage_periods.c.account_id == principal["account_id"],
                             usage_periods.c.period == period)
                      .values(compute_units=usage_periods.c.compute_units + compute_units,
                              requests=usage_periods.c.requests + 1,
                              updated_at=datetime.now(timezone.utc)))


def rebuild_period(account_id, period):
    """Recompute a period counter from the event log — the reconciliation path.

    Exists because the event log is the source of truth: if a counter is ever wrong (a partial write, a
    restore, a manual fix) this makes it correct again rather than requiring anyone to trust it.
    """
    with engine().begin() as c:
        agg = c.execute(select(func.coalesce(func.sum(usage_events.c.compute_units), 0.0),
                               func.count(usage_events.c.id))
                        .where(usage_events.c.account_id == account_id,
                               usage_events.c.period == period)).first()
        cu, n = float(agg[0]), int(agg[1])
        exists = c.execute(select(usage_periods.c.account_id)
                           .where(usage_periods.c.account_id == account_id,
                                  usage_periods.c.period == period)).first()
        if exists:
            c.execute(update(usage_periods)
                      .where(usage_periods.c.account_id == account_id,
                             usage_periods.c.period == period)
                      .values(compute_units=cu, requests=n,
                              updated_at=datetime.now(timezone.utc)))
        else:
            c.execute(insert(usage_periods).values(account_id=account_id, period=period,
                                                   compute_units=cu, requests=n,
                                                   updated_at=datetime.now(timezone.utc)))
    return {"period": period, "compute_units": cu, "requests": n}


def account_summary(account_id):
    with engine().begin() as c:
        a = c.execute(select(accounts, plans.c.name.label("plan_name"), plans.c.monthly_cu,
                             plans.c.allow_overage, plans.c.overage_cu_price)
                      .select_from(accounts.join(plans, accounts.c.plan_id == plans.c.id))
                      .where(accounts.c.id == account_id)).mappings().first()
        keys = c.execute(select(api_keys.c.id, api_keys.c.prefix, api_keys.c.label,
                                api_keys.c.scopes, api_keys.c.active, api_keys.c.last_used_at)
                         .where(api_keys.c.account_id == account_id)).mappings().all()
        recent = c.execute(select(usage_events.c.period, usage_events.c.path,
                                  func.sum(usage_events.c.compute_units).label("cu"),
                                  func.count(usage_events.c.id).label("n"))
                           .where(usage_events.c.account_id == account_id)
                           .group_by(usage_events.c.period, usage_events.c.path)
                           .order_by(usage_events.c.period.desc())).mappings().all()
    if not a:
        return None
    return {"account": dict(a), "keys": [dict(k) for k in keys],
            "usage": period_usage(account_id), "by_path": [dict(r) for r in recent]}


def list_accounts():
    with engine().begin() as c:
        rows = c.execute(select(accounts.c.id, accounts.c.email, accounts.c.name,
                                accounts.c.plan_id, accounts.c.active)).mappings().all()
    return [dict(r) for r in rows]
