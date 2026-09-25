"""
RegMap billing spine — accounts, API keys, attributed usage, quotas.

This is the layer the engine was missing: before it, compute was metered but attributed to nobody, so
`/usage` was diagnostics rather than billing. Everything here exists to answer one question defensibly:
**who consumed what, and are they allowed more?**

    DATABASE_URL=postgresql+psycopg://user:pass@host/regmap   # production
    DATABASE_URL=sqlite:///./regmap.db                        # default (development ONLY)

SQLITE IS USABLE FOR NOW, BUT ONLY BECAUSE THE LEDGER IS ON A VOLUME. The image declares `/data` and
`k8s/pvc.yaml` binds a PersistentVolumeClaim there, so the database survives restarts and rescheduling
(verified by deleting the pod and reading the ledger back unchanged). The remaining limit is
concurrency: SQLite is single-writer, so `deployment.yaml` is pinned to `replicas: 1` and the HPA is
deliberately excluded from the kustomization. Point DATABASE_URL at managed Postgres before scaling
past one replica.

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
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import (Boolean, Column, DateTime, Float, ForeignKey, Integer, MetaData, String,
                        Table, Text, create_engine, func, insert, inspect, select, text, update)

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
    # Null for accounts created by the operator CLI (API-key only). Set by self-serve
    # registration. Never stores the password itself -- see hash_password().
    Column("password_hash", String(255)),
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

# Saved compliance projects: a named crosswalk the user returns to. The full working state (target,
# controls, and the per-control review/status/notes) lives in `data` as JSON, so opening a project
# restores exactly where the analyst left off.
projects = Table(
    "projects", metadata,
    Column("id", String(40), primary_key=True),
    Column("account_id", String(40), index=True, nullable=False),
    Column("name", String(200), nullable=False),
    Column("target_fid", String(64)),
    Column("source_kind", String(16), default="custom"),   # custom | catalog
    Column("data", Text),                                   # JSON: {target, top_k, controls, decisions}
    Column("created_at", DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)),
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


def _migrate():
    """Add columns that exist in the model but not yet in the database.

    `metadata.create_all()` creates missing TABLES but never alters existing ones, so a deployment that
    upgrades across a schema change keeps its old table definitions and fails at insert time. That is a
    bug only an UPGRADE reveals -- a fresh install works perfectly -- and it is exactly how
    `password_hash` broke registration on a volume created by an earlier build.

    Deliberately conservative: it only ever ADDs nullable columns. Adding NOT NULL to a populated table
    needs a default and a backfill, which is a real migration and should be written explicitly rather
    than guessed at here. Anything it cannot handle safely is reported instead of attempted.
    """
    insp = inspect(engine())
    existing_tables = set(insp.get_table_names())
    added, needs_attention = [], []
    for table in metadata.sorted_tables:
        if table.name not in existing_tables:
            continue                                  # create_all handles brand-new tables
        have = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in have:
                continue
            if not col.nullable and col.default is None and col.server_default is None:
                needs_attention.append(f"{table.name}.{col.name} (NOT NULL, needs a backfill)")
                continue
            ddl = col.type.compile(engine().dialect)
            with engine().begin() as c:
                c.execute(text(f'ALTER TABLE {table.name} ADD COLUMN {col.name} {ddl}'))
            added.append(f"{table.name}.{col.name}")
    return added, needs_attention


def startup(replicas_hint=None):
    """Create tables if absent, migrate columns, seed plans, and warn about unsafe configurations."""
    metadata.create_all(engine())
    added, needs_attention = _migrate()
    with engine().begin() as c:
        have = {r[0] for r in c.execute(select(plans.c.id))}
        for pid, name, cu, over, price in DEFAULT_PLANS:
            if pid not in have:
                c.execute(insert(plans).values(id=pid, name=name, monthly_cu=cu,
                                               allow_overage=over, overage_cu_price=price))
    warnings = []
    if added:
        warnings.append("schema migrated, added column(s): " + ", ".join(added))
    for item in needs_attention:
        warnings.append("MANUAL MIGRATION REQUIRED for " + item)
    if is_sqlite():
        warnings.append(
            "billing ledger is SQLite. Durable only if it sits on a mounted volume (the image "
            "declares /data and k8s/pvc.yaml binds it). SQLite is single-writer, so keep replicas at 1 "
            "and the HPA disabled; move DATABASE_URL to managed Postgres before scaling.")
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


# ---- saved projects ------------------------------------------------------------------------------
def create_project(account_id, name, target_fid=None, source_kind="custom", data=None):
    pid = "proj_" + secrets.token_hex(8)
    now = datetime.now(timezone.utc)
    with engine().begin() as c:
        c.execute(insert(projects).values(
            id=pid, account_id=account_id, name=(name or "Untitled")[:200], target_fid=target_fid,
            source_kind=source_kind, data=json.dumps(data or {}), created_at=now, updated_at=now))
    return pid


def list_projects(account_id):
    with engine().begin() as c:
        rows = c.execute(
            select(projects.c.id, projects.c.name, projects.c.target_fid, projects.c.updated_at)
            .where(projects.c.account_id == account_id)
            .order_by(projects.c.updated_at.desc())).mappings().all()
    return [dict(r) for r in rows]


def get_project(account_id, pid):
    with engine().begin() as c:
        row = c.execute(select(projects).where(
            projects.c.id == pid, projects.c.account_id == account_id)).mappings().first()
    if not row:
        return None
    d = dict(row)
    try:
        d["data"] = json.loads(d.get("data") or "{}")
    except Exception:
        d["data"] = {}
    return d


def update_project(account_id, pid, name=None, target_fid=None, data=None):
    vals = {"updated_at": datetime.now(timezone.utc)}
    if name is not None:
        vals["name"] = name[:200]
    if target_fid is not None:
        vals["target_fid"] = target_fid
    if data is not None:
        vals["data"] = json.dumps(data)
    with engine().begin() as c:
        r = c.execute(update(projects).where(
            projects.c.id == pid, projects.c.account_id == account_id).values(**vals))
    return r.rowcount


def delete_project(account_id, pid):
    with engine().begin() as c:
        r = c.execute(projects.delete().where(
            projects.c.id == pid, projects.c.account_id == account_id))
    return r.rowcount


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


# ---- passwords + sessions ------------------------------------------------------------------------
# Browser users log in; programmatic callers use API keys. Both resolve to the same principal, so every
# downstream check (quota, metering, scopes) is identical regardless of how the caller authenticated.
#
# Passwords are hashed with scrypt from the standard library -- memory-hard, so a stolen database is
# expensive to attack offline, and no third-party dependency is needed. Never store or log the password.
#
# Sessions are opaque random tokens stored server-side rather than signed claims, because that makes
# logout and revocation immediate: deleting the row ends the session. A signed cookie cannot be
# un-issued.

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 14, 8, 1
SESSION_DAYS = int(os.environ.get("REGMAP_SESSION_DAYS", "14"))

sessions = Table(
    "sessions", metadata,
    Column("token_hash", String(64), primary_key=True),   # sha256 of the cookie value
    Column("account_id", String(40), ForeignKey("accounts.id"), nullable=False, index=True),
    Column("created_at", DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("user_agent", String(255)),
)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time comparison against the stored parameters, so old hashes keep working if the cost
    factors are raised later."""
    try:
        scheme, n, r, p, salt_hex, want = stored.split("$")
        if scheme != "scrypt":
            return False
        dk = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex),
                            n=int(n), r=int(r), p=int(p), dklen=len(want) // 2)
        return hmac.compare_digest(dk.hex(), want)
    except Exception:
        return False


def register(email, password, name=None, plan_id="free"):
    """Create an account with a password. Returns (account_id, error).

    Registration is self-serve and lands on the free plan, so a new user immediately has a quota and is
    metered like anyone else -- there is no unmetered path into the system.
    """
    email = (email or "").strip().lower()
    if "@" not in email or len(email) < 5:
        return None, "enter a valid email address"
    if not password or len(password) < 10:
        return None, "password must be at least 10 characters"
    with engine().begin() as c:
        if c.execute(select(accounts.c.id).where(accounts.c.email == email)).first():
            return None, "an account with that email already exists"
        aid = "acct_" + secrets.token_hex(10)
        c.execute(insert(accounts).values(id=aid, email=email, name=name, plan_id=plan_id,
                                          active=True, password_hash=hash_password(password)))
    return aid, None


def set_password(account_id, password):
    with engine().begin() as c:
        c.execute(update(accounts).where(accounts.c.id == account_id)
                  .values(password_hash=hash_password(password)))


def login(email, password, user_agent=None):
    """Verify credentials and open a session. Returns (raw_token, account_id, error)."""
    email = (email or "").strip().lower()
    with engine().begin() as c:
        row = c.execute(select(accounts.c.id, accounts.c.password_hash, accounts.c.active)
                        .where(accounts.c.email == email)).mappings().first()
    # Deliberately identical message for "no such user" and "wrong password", so the endpoint cannot be
    # used to discover which email addresses are registered.
    if not row or not row["password_hash"] or not verify_password(password, row["password_hash"]):
        return None, None, "email or password is incorrect"
    if not row["active"]:
        return None, None, "this account is deactivated"
    raw = secrets.token_urlsafe(32)
    with engine().begin() as c:
        c.execute(insert(sessions).values(
            token_hash=hashlib.sha256(raw.encode()).hexdigest(), account_id=row["id"],
            expires_at=datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS),
            user_agent=(user_agent or "")[:255]))
    return raw, row["id"], None


def verify_session(raw):
    """Resolve a session cookie to the same principal shape verify_key() returns, or None."""
    if not raw:
        return None
    th = hashlib.sha256(raw.encode()).hexdigest()
    with engine().begin() as c:
        row = c.execute(
            select(sessions.c.account_id, sessions.c.expires_at, accounts.c.active, accounts.c.email,
                   accounts.c.plan_id, plans.c.monthly_cu, plans.c.allow_overage,
                   plans.c.overage_cu_price, plans.c.name)
            .select_from(sessions.join(accounts, sessions.c.account_id == accounts.c.id)
                                 .join(plans, accounts.c.plan_id == plans.c.id))
            .where(sessions.c.token_hash == th)).mappings().first()
        if not row or not row["active"]:
            return None
        exp = row["expires_at"]
        if exp.tzinfo is None:                      # SQLite returns naive datetimes
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            c.execute(sessions.delete().where(sessions.c.token_hash == th))
            return None
    d = dict(row)
    d["id"] = None                    # a session is not an API key
    d["scopes"] = ""                  # admin scope is deliberately key-only, never granted by login
    d["auth"] = "session"
    return d


def logout(raw):
    if not raw:
        return 0
    with engine().begin() as c:
        r = c.execute(sessions.delete()
                      .where(sessions.c.token_hash == hashlib.sha256(raw.encode()).hexdigest()))
    return r.rowcount


def purge_expired_sessions():
    with engine().begin() as c:
        r = c.execute(sessions.delete().where(sessions.c.expires_at < datetime.now(timezone.utc)))
    return r.rowcount
