# Admin access and analytics

Quick reference for reaching the site's administrator area and product analytics. See
`docs/analytics_tracker.md` for the full analytics roadmap.

## Admin dashboard URL

- **Path:** `/admin.html`
- **Local dev:** http://127.0.0.1:8010/admin.html
- **Production:** `https://<your-domain>/admin.html`

You must be **signed in** with an administrator account to see it; everyone else gets an
"Administrator access only" screen. When signed in as an admin, an **Admin** link also appears in the top
navigation, so you can reach the dashboard without typing the URL.

## How admin is granted

Admin is by **email**, not a separate credential. An account is an administrator when either:

- its email is in the `REGMAP_ADMIN_EMAILS` environment variable (comma-separated list), or
- it holds an `admin`-scoped API key.

Enforced server-side (`_require_admin` in `regmap_engine/serve.py`); `/auth/session` returns an `admin` flag
the UI uses to show admin surfaces.

### Grant yourself admin

Set the env var wherever the app runs, then sign in with that email:

```
REGMAP_ADMIN_EMAILS=stetteh@xl.net
# optional: stable IP hashing across restarts
REGMAP_ANALYTICS_SALT=<a long random string>
```

- Local dev example (how the dev server is started):
  `REGMAP_ADMIN_EMAILS=stetteh@xl.net python -m uvicorn main:app --host 127.0.0.1 --port 8010`
- Production: add `REGMAP_ADMIN_EMAILS` (and `REGMAP_ANALYTICS_SALT`) to the k8s deployment env before launch.

## Current admin account

- **Sign-in page:** `/account.html`
- **Email:** `stetteh@xl.net`

**Password: dev-only, change before production.** A throwaway password was set on the **local dev SQLite
database** during setup. It is intentionally NOT written here so it does not live in the repo. If you need it,
it was shared in the working session; sign in and change it under **Account -> Password**, or reset it via the
password-reset flow on `/account.html`. Production uses a separate database where you register this account
fresh with your own private password.

## Analytics API (admin only)

- `GET /analytics/summary?days=N` - totals, daily timeseries, top pages, events by type, device split,
  guest vs signed-in, signups (403 for non-admins).
- `GET /analytics/whoami` - `{ "admin": true|false }` for the current session (never 403s).
- `POST /analytics/collect` - event ingestion used by the site beacon (open to guests). Not for manual use.

## Security notes

- Never commit real production credentials or secrets to the repo. Keep `REGMAP_ADMIN_EMAILS`,
  `REGMAP_ANALYTICS_SALT`, and account passwords in environment/secret stores, not in files.
- Analytics is anonymous and first-party (random visitor id, salted IP hash, no raw IPs); only an admin can
  read aggregates.
