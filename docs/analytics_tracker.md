# Analytics tracker

The plan for RegMap's product analytics: capture how people use the site and turn it into evidence that the
product is useful (for the founder, for investors, and for an EB-2 NIW record). Start here for anything on
analytics. Sibling docs: `build_tracker.md` (whole product), `compliance_tab_tracker.md`, `auth_tracker.md`.
No em-dashes or en-dashes (founder rule).

Created 2026-09-26.

## Goal

Answer, with data, "is RegMap useful and being used?" Show acquisition, activation, engagement, retention,
and the value delivered (crosswalks run, coverage measured, policies adopted, skills proven), and make that
legible on one admin dashboard.

## Principles

- **Admin only.** All analytics query endpoints and the dashboard are restricted to a site administrator.
  Regular users never see aggregate analytics. Enforced server-side (`_require_admin`), not just hidden in UI.
- **Privacy-respecting.** Store an anonymous visitor id (random, first-party), not names or full IPs. IPs are
  hashed with a salt (or reduced to a coarse prefix); user agents are stored truncated. Account id is attached
  only when the visitor is signed in. A future cookie/consent banner covers non-essential analytics.
- **First-party, self-hosted.** Events go to our own backend and database; no third-party trackers, so the
  data is ours and privacy is under our control.
- **Cheap to write, easy to read.** Ingestion is a single lightweight endpoint; the dashboard reads
  pre-aggregated SQL. Heavy history rolls up over time.

## Architecture

- **Client beacon** (`shell.js` + `assets/analytics.js`): assigns a first-party `visitor_id` (localStorage),
  sends a `pageview` on load, and exposes `window.rmTrack(name, props)` for feature events. Uses
  `navigator.sendBeacon` where available so it never blocks navigation.
- **Ingestion**: `POST /analytics/collect` accepts a batch of events, stamps server-side time, the account id
  (from the session cookie if signed in), a hashed IP, and truncated UA, and writes rows. No auth required to
  send (guests are the point), but it is rate-limited and size-capped.
- **Storage**: an `analytics_events` table (append-only). Daily rollups into `analytics_daily` later for scale.
- **Query**: admin-only `GET /analytics/*` endpoints return aggregates. Dashboard at `web/admin.html`.

## Event taxonomy (what we capture)

- **pageview**: path, referrer, title. The backbone of traffic metrics.
- **session_start**: first event in a visit (derived, or sent when a new visit begins).
- **auth**: `signup`, `login`, `verify_email`, `enable_2fa` (names only, no secrets).
- **compliance**: `map_run` (source, target, method), `bulk_run`, `custom_run` (control count), `multi_run`,
  `remediate`, `export` (format), `review_action` (accept/reject/status), `evidence_add`.
- **projects**: `project_save`, `project_open`, `recheck`, `share_member_add`, `comment_add`, `approve`.
- **university**: `lesson_open` (type), `lesson_complete`, `lab_pass` (score, nice_task), `transcript_publish`.
- **policy**: `policy_open`, `policy_customize`, `policy_download` (format), `policy_save`.
- **outbound / cta**: `cta_click` (which button), `nav_click`, `signin_prompt_shown`.

Each event carries: name, path, `visitor_id`, `account_id?`, `props` (JSON), timestamp, hashed IP, UA class.

## KPIs (the evidence of usefulness)

- **Acquisition**: unique visitors, new vs returning, top pages, referrers, over time.
- **Activation**: signups, first meaningful action (first map/lab/policy), signup-to-activation rate.
- **Engagement**: events per visitor, sessions per visitor, most-used features, depth (pages/visit),
  time-on-site (approx from event spacing).
- **Value delivered**: total crosswalks run, controls mapped, coverage analyses, exports produced, policies
  downloaded/saved, lessons completed, labs passed, transcripts published.
- **Retention**: returning-visitor rate, weekly active accounts, streaks (University).
- **Funnel**: visit -> signup -> activation -> repeat use, with drop-off at each step.
- **Segments**: signed-in vs guest, device (mobile/desktop), by page/section.

## Phases

### Phase 1 (build now): capture + core admin dashboard  DONE 2026-09-26, verified
- [x] `analytics_events` table + helpers (`record_events`, `analytics_query`) in `billing.py`.
- [x] `POST /analytics/collect` ingestion (account from session cookie, salted IP hash, UA class, 50/req cap).
- [x] `_require_admin` gate (admin API-key scope, or `REGMAP_ADMIN_EMAILS` env allow-list); `/auth/session`
      now returns `admin`; `GET /analytics/whoami` for the UI.
- [x] Client beacon in `shell.js`: first-party `visitor_id`, `pageview` on every page, `window.rmTrack`,
      via `navigator.sendBeacon`.
- [x] Admin-only `GET /analytics/summary?days=N`: totals, daily timeseries, top pages, events by name,
      guest vs signed-in, device split, signups.
- [x] `web/admin.html` dashboard (KPI cards, timeseries bars, top pages, events, devices, segments; range
      7/30/90). Non-admins see "Administrator access only". Admin nav link shown only to admins in `shell.js`.
- Verified end to end: events ingest (guest + batched), admin gets full summary, non-admin gets 403.
- **Operator note:** set `REGMAP_ADMIN_EMAILS=you@example.com` (comma-separated) to grant admin. Optionally
  set `REGMAP_ANALYTICS_SALT` for stable IP hashing across restarts. Added to k8s env before launch.

### Phase 2: feature + value events
- [ ] Wire the compliance, university, and policy events above via `rmTrack`.
- [ ] "Value delivered" panel (crosswalks run, exports, policies, lessons, labs).
- [ ] Funnel view (visit -> signup -> activation -> repeat).

### Phase 3: depth, retention, segments
- [ ] Sessionization and returning-visitor / WAU / MAU metrics.
- [ ] Retention cohorts (by signup week) and University streak analytics.
- [ ] Referrer and campaign (UTM) capture; top acquisition sources.
- [ ] Device, and coarse geo (from hashed-IP region lookup) if justified.

### Phase 4: scale + operations
- [ ] Daily rollup job (`analytics_daily`) and retention/pruning of raw events.
- [ ] Export analytics (CSV) for the record; scheduled email digest to the admin.
- [ ] Rate limiting and bot filtering on ingestion.

### Phase 5: trust + compliance of the analytics itself
- [ ] Cookie/consent banner for non-essential analytics; respect Do-Not-Track.
- [ ] Document data handling in the Privacy policy; data-subject deletion covers analytics.
- [ ] Access log of admin analytics access (who viewed what).

## Notes / decisions
- Admin designation: `REGMAP_ADMIN_EMAILS` (comma-separated) is the simplest control now; an `admin` API-key
  scope also grants access. Later, an `accounts.is_admin` flag with an admin UI.
- Pre-launch, enforcement (rate limits) is off globally; turn on ingestion rate limiting before launch.

## Change log
- 2026-09-26: created; Phase 1 defined and started.
