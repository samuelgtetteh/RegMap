"""
Operator CLI for accounts, API keys and usage.

Account creation is a CLI operation rather than an HTTP endpoint deliberately: a public signup route
that mints credentials is an abuse surface, and until there is a payment flow and email verification
(Phase C) an operator should be the one creating accounts.

    python scripts/regmap_admin.py init
    python scripts/regmap_admin.py account create --email you@example.com --plan pro
    python scripts/regmap_admin.py key create --account acct_... --label "laptop" --scopes admin
    python scripts/regmap_admin.py key revoke --key key_...
    python scripts/regmap_admin.py usage --account acct_...
    python scripts/regmap_admin.py reconcile --account acct_... --period 2026-08
    python scripts/regmap_admin.py accounts

Set DATABASE_URL to point at the same ledger the engine uses, or the CLI will manage a different one.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "regmap_engine"))

import billing  # noqa: E402


def cmd_init(a):
    warnings = billing.startup()
    print(f"ledger ready at {billing.DATABASE_URL}")
    print(f"  plans: {', '.join(p[0] for p in billing.DEFAULT_PLANS)}")
    for w in warnings:
        print(f"\n  WARNING: {w}")


def cmd_account_create(a):
    billing.startup()
    aid = billing.create_account(a.email, a.name, a.plan)
    print(f"account : {aid}")
    print(f"  email : {a.email}")
    print(f"  plan  : {a.plan}")
    print(f"\nnext: python scripts/regmap_admin.py key create --account {aid}")


def cmd_key_create(a):
    billing.startup()
    kid, raw = billing.create_key(a.account, a.label, a.scopes or "")
    print(f"key id : {kid}")
    print(f"scopes : {a.scopes or '(none)'}")
    print("\n  " + raw)
    print("\n  ^ Copy this now. Only its hash is stored, so it cannot be shown again.")
    print("\nuse it with:")
    print(f'  curl -H "Authorization: Bearer {raw[:14]}..." http://localhost:8000/me')


def cmd_key_revoke(a):
    billing.startup()
    n = billing.revoke_key(a.key)
    print(f"revoked {n} key(s)" if n else "no such key")


def cmd_usage(a):
    billing.startup()
    s = billing.account_summary(a.account)
    if not s:
        print("no such account"); return
    acc, u = s["account"], s["usage"]
    allowance = float(acc["monthly_cu"])
    print(f"{acc['email']}  ({acc['id']})")
    print(f"  plan          : {acc['plan_name']} ({acc['plan_id']})")
    print(f"  period        : {u['period']}")
    print(f"  compute units : {u['compute_units']:.4f}"
          + (f" / {allowance:g}" if allowance != float('inf') else " / unlimited"))
    print(f"  requests      : {u['requests']}")
    if allowance not in (0, float("inf")):
        print(f"  used          : {100 * u['compute_units'] / allowance:.1f}%")
    if s["by_path"]:
        print("  by endpoint:")
        for r in s["by_path"]:
            print(f"    {r['period']}  {r['path']:<18} {float(r['cu']):>10.4f} CU  {r['n']:>5} calls")
    print("  keys:")
    for k in s["keys"]:
        state = "active" if k["active"] else "REVOKED"
        print(f"    {k['id']}  {k['prefix']}…  {state:<8} scopes={k['scopes'] or '-'}"
              f"  last_used={k['last_used_at'] or 'never'}")


def cmd_reconcile(a):
    billing.startup()
    before = billing.period_usage(a.account, a.period)
    after = billing.rebuild_period(a.account, a.period)
    drift = after["compute_units"] - before["compute_units"]
    print(f"counter  : {before['compute_units']:.4f} CU / {before['requests']} requests")
    print(f"rebuilt  : {after['compute_units']:.4f} CU / {after['requests']} requests")
    print(f"drift    : {drift:+.6f} CU"
          + ("  (counter was correct)" if abs(drift) < 1e-9 else "  <-- counter had drifted"))


def cmd_accounts(a):
    billing.startup()
    rows = billing.list_accounts()
    if not rows:
        print("no accounts yet"); return
    print(f"{'account':<26}{'email':<32}{'plan':<10}{'active':<8}{'CU this period':>15}")
    print("-" * 91)
    for r in rows:
        u = billing.period_usage(r["id"])
        print(f"{r['id']:<26}{r['email']:<32}{r['plan_id']:<10}"
              f"{str(bool(r['active'])):<8}{u['compute_units']:>15.4f}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init").set_defaults(fn=cmd_init)
    sub.add_parser("accounts").set_defaults(fn=cmd_accounts)

    acc = sub.add_parser("account").add_subparsers(dest="sub", required=True)
    c = acc.add_parser("create"); c.set_defaults(fn=cmd_account_create)
    c.add_argument("--email", required=True); c.add_argument("--name")
    c.add_argument("--plan", default="free",
                   choices=[p[0] for p in billing.DEFAULT_PLANS])

    key = sub.add_parser("key").add_subparsers(dest="sub", required=True)
    c = key.add_parser("create"); c.set_defaults(fn=cmd_key_create)
    c.add_argument("--account", required=True); c.add_argument("--label")
    c.add_argument("--scopes", help="comma-separated; 'admin' unlocks the operator endpoints")
    c = key.add_parser("revoke"); c.set_defaults(fn=cmd_key_revoke)
    c.add_argument("--key", required=True)

    c = sub.add_parser("usage"); c.set_defaults(fn=cmd_usage)
    c.add_argument("--account", required=True)

    c = sub.add_parser("reconcile"); c.set_defaults(fn=cmd_reconcile)
    c.add_argument("--account", required=True); c.add_argument("--period", required=True)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
