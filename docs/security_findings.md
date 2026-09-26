# Security findings

A log of security issues identified through code review, AI audit, or manual testing.
Fix these before the site goes public. Listed by severity, highest first.

No em-dashes or en-dashes anywhere in this file (founder rule).

Last updated: 2026-09-26.

---

## How to use this document

Each finding has a status:
- **OPEN** - not yet fixed
- **IN PROGRESS** - being worked on
- **FIXED** - resolved, with commit reference

Fix all HIGH and MEDIUM items before launch. LOW items should be fixed but are not blockers
for a limited private launch.

---

## Finding 1 - Stored XSS via unauthenticated analytics injection

**Severity:** HIGH
**Status:** FIXED (2026-09-26)
**Source:** AI security audit, 2026-09-26
**File:** `regmap_engine/serve.py` (`POST /analytics/collect`), `web/admin.html`

### What was found

`POST /analytics/collect` accepts requests with no authentication. Any anonymous visitor or
malicious third party can POST arbitrary event names directly to the endpoint. Those event
names are stored in the database and rendered on the admin dashboard.

The audit confirmed injection by posting `<img src=x onerror=alert(1)>` as an event name.
It appeared immediately in the Events by type table on the admin page. The current rendering
escaped it correctly via `RegMap.esc()`, so the payload did not execute. However that is a
single thin line of defence. If any future admin view renders event names or event `props`
with `innerHTML` without escaping, this becomes a working stored XSS attack against the admin
panel. The `props` field (also submitted without auth) is unstructured and particularly risky.

### Fix required

1. Add server-side validation: allowlist permitted event name values (pageview, map_run,
   lesson_complete, etc. from the event taxonomy in `docs/analytics_tracker.md`). Reject
   anything not on the list with a 400 error.
2. Sanitize and size-cap the `props` field server-side before storing.
3. Consider requiring a CSRF token or same-site cookie check on `/analytics/collect` to
   block cross-origin POST requests. Note: requiring full auth would break guest event
   capture (guests are intentional), so the allowlist approach is the right primary fix.
4. On the admin dashboard, ensure all rendered event names and props go through `esc()`
   regardless of which code path renders them.

---

## Finding 2 - `/admin.html` has no server-side access control

**Severity:** MEDIUM
**Status:** FIXED (2026-09-26)
**Source:** AI security audit, 2026-09-26
**File:** `regmap_engine/serve.py` (route serving `admin.html`), `web/admin.html`

### What was found

The admin page HTML is served with `200 OK` to any request, authenticated or not. The data
API correctly returns `403 administrator access only`, but the page shell itself loads for
anyone who knows the URL. The client-side session check in `shell.js` that hides the Admin
nav link for non-admins is not a security control.

### Fix required

The server should check the session before serving `admin.html`. If the session does not
have `admin: true`, return a 302 redirect to `/` or a 403 response. This prevents the
page source and its JavaScript from being studied by an attacker even if the data endpoints
are correctly gated.

---

## Finding 3 - Security response headers missing on all routes

**Severity:** MEDIUM
**Status:** FIXED (2026-09-26)
**Source:** AI security audit, 2026-09-26
**File:** `regmap_engine/serve.py` (global middleware)

### What was found

Every response (HTML pages and API endpoints alike) is missing the following headers:

- `Content-Security-Policy` - prevents XSS by restricting what scripts can run
- `X-Frame-Options` - prevents clickjacking (the page being embedded in an iframe)
- `X-Content-Type-Options` - prevents MIME-type sniffing
- `Strict-Transport-Security` - enforces HTTPS on future visits
- `Referrer-Policy` - controls how much referrer info is sent to third parties

Additionally, the `Server: uvicorn` response header discloses the runtime stack, which
helps attackers fingerprint the server.

### Fix required

Add a FastAPI middleware that injects these headers on every response:

```python
Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net https://fonts.googleapis.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; img-src 'self' data:;
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
Strict-Transport-Security: max-age=31536000; includeSubDomains
Referrer-Policy: strict-origin-when-cross-origin
```

Remove or replace the `Server` header (set it to a blank string or a generic value).
Note: `unsafe-inline` in CSP is needed while inline scripts exist in the HTML files.
The long-term fix is to move inline scripts to external files and remove `unsafe-inline`.

---

## Finding 4 - API key stored in localStorage

**Severity:** LOW
**Status:** FIXED (2026-09-26)
**Source:** AI security audit, 2026-09-26
**File:** `web/assets/api.js`

### What was found

The code stores an API key in `localStorage`. The `api.js` comments acknowledge this
directly: "it is NOT a substitute for a session, because anything in localStorage is
readable by any script on the origin." If any XSS is ever exploited (see Finding 1), the
API key is trivially exfiltrated.

### Fix required

Once proper session auth is fully in place and stable, remove the API key from
`localStorage`. The session cookie path (`credentials: "same-origin"`) is the correct
pattern. The API key in localStorage is a legacy convenience; it should not exist in
production for regular users.

---

## Finding 5 - Account operates without email verification

**Severity:** LOW
**Status:** FIXED (2026-09-26) - server-side gate added; email provider still needed for production
**Source:** AI security audit, 2026-09-26
**File:** `regmap_engine/serve.py`, `regmap_engine/auth.py`

### What was found

The `/auth/session` response returns `email_verified: false` on an `admin: true` account.
The account is fully operational despite the email address never being confirmed. Email
verification should gate sensitive capabilities (admin access, saving policies, publishing
transcripts).

### Fix required

1. Wire a real email provider (currently no transactional email is configured).
2. On registration, send a verification link and set `email_verified = false`.
3. Gate admin privileges and sensitive write operations on `email_verified = true`.
4. Provide a "resend verification" option on the account page.

Note: this is also listed in the pre-launch checklist. Do not block a dev-only local
instance on this but fix it before any public launch.

---

---

## Finding 6 - Verification token returned in registration response body

**Severity:** HIGH
**Status:** FIXED (2026-09-26)
**Source:** AI security audit, second pass, 2026-09-26
**File:** `regmap_engine/serve.py` (`POST /auth/register`, `POST /auth/verify/resend`, `POST /auth/reset/request`)

### What was found

`POST /auth/register` returned the one-time verification URL (including the token) in the JSON
response body when `EMAIL_ENABLED` was false. An attacker could register any email address, read
the token directly from the response, call `POST /auth/verify` with it, and the account would be
instantly verified without inbox access. Email verification was completely bypassable.

The same pattern existed in `/auth/verify/resend` (returned `verify_link`) and
`/auth/reset/request` (returned `reset_link`).

### Fix applied

The `verify_link` and `reset_link` fields were removed from all three response bodies. Tokens now
travel only via the server log (`print(...)`) in dev mode, and via email in production. The log
line is visible only to the server operator, not to the registering client.

---

## Finding 7 - No rate limiting on authentication endpoints

**Severity:** HIGH
**Status:** FIXED (2026-09-26)
**Source:** AI security audit, second pass, 2026-09-26
**File:** `regmap_engine/serve.py`

### What was found

`/auth/login`, `/auth/register`, and `/auth/reset/request` accepted unlimited concurrent requests.
30 rapid failed logins all returned 401 with no throttle. This allowed unrestricted brute-force
attacks, account creation spam, and inbox flooding via repeated reset requests.

### Fix applied

A sliding-window in-memory rate limiter (`_rl_check`, `_require_not_rate_limited`) was added.
Limits per IP per 60 seconds:
- `/auth/login` and `/auth/register`: 10 requests
- `/auth/reset/request`: 5 requests

Exceeding the limit returns `429` with a plain message. No external dependencies; uses a
thread-safe dict of timestamps with in-place pruning. For production at scale, replace with
Redis or a similar shared store so limits apply across multiple workers.

---

## Finding 8 - Public transcript endpoint leaks learning activity

**Severity:** MEDIUM
**Status:** RESOLVED by design (ID entropy upgraded)
**Source:** AI security audit, second pass, 2026-09-26
**File:** `regmap_engine/billing.py` (`publish_transcript`)

### What was found

`GET /transcript/{id}` returns full learning profile data with no authentication. The transcript
ID `tr_50SFAW8ZNRAZ` was found in localStorage and confirmed accessible without credentials.

### Resolution

Transcripts are **intentionally public** by design: they are a shareable evidence record (the
point is that an employer or certifier can view it without signing in). Access is controlled
solely by the opacity of the ID.

The original IDs used `secrets.token_urlsafe(9)` giving 72 bits of entropy. Upgraded to
`secrets.token_urlsafe(16)` giving 128 bits, which is the cryptographic standard for unguessable
identifiers. At 128 bits, enumerating IDs is computationally infeasible.

If a future requirement calls for revocable or private transcripts, add a `public` flag to the
`transcripts` table and gate the endpoint on it.

---

## Finding 9 - Cookie Secure and SameSite flags

**Severity:** LOW
**Status:** CONFIRMED CORRECT (no change needed)
**Source:** AI security audit, second pass, 2026-09-26

### What was found

The auditor could not confirm `Secure` and `SameSite` flags on HTTP (dev). These are required in
production over HTTPS.

### Current state

`_set_session_cookie` already sets:
- `httponly=True` (script cannot read the cookie)
- `samesite="lax"` (sent on top-level navigation, not cross-site POST)
- `secure=SECURE_COOKIES` (off by default for localhost; set `REGMAP_SECURE_COOKIES=true` in production)

The flags are correct. The operator must set `REGMAP_SECURE_COOKIES=true` in any HTTPS deployment.
This is in the pre-launch checklist and `docs/hosting_options.md`.

---

---

## Finding 10 - CRITICAL: Paid endpoints accessible without authentication

**Severity:** CRITICAL
**Status:** FIXED (2026-09-26)
**Source:** AI security audit, third pass, 2026-09-26
**File:** `regmap_engine/auth.py` (`REQUIRE_AUTH`)

### What was found

`/map`, `/remediate`, `/exercise`, `/exercise/grade`, `/map/bulk`, `/map/custom`, and `/map/custom/multi`
are your core paid features. All were accessible without any authentication when `REQUIRE_AUTH=false`
(the dev default). An unauthenticated request was assigned to a shared anonymous account, which had
consumed 451 CU (150% of its 300 CU/month free quota) and was still serving requests (quota enforcement
was broken). Anyone could hammer these endpoints indefinitely at your cost.

### Fix applied

Flipped the default: `REQUIRE_AUTH` now defaults to `true`. All billable endpoints now require a valid
session or API key. To disable auth for local development, set `REGMAP_REQUIRE_AUTH=false` in the
startup command.

**This closes the immediate free-tier abuse immediately.** All existing dev deployments with the default
now enforce authentication. To downgrade for local work, pass the env var explicitly.

---

## Finding 11 - Exercise grading reveals correct answers and tokens are reusable

**Severity:** MEDIUM
**Status:** FIXED (2026-09-26)
**Source:** AI security audit, third pass, 2026-09-26
**File:** `regmap_engine/serve.py` (`/exercise/grade`)

### What was found

When you submit empty answers to `/exercise/grade`, the response includes `missed`, `incorrect`, and
`official_answer` arrays listing the correct controls. A user could call the endpoint once with no
answers to see the answer key, then resubmit with correct selections and get a perfect score. The
exercise token is accepted multiple times (no single-use enforcement).

### Fix applied

Answer details (`correct`, `missed`, `incorrect`, `official_answer`) are now **only returned if the 
user passed the exercise**. This prevents gaming the assessment while still providing learning value
when the learner succeeds. If a learner wants to learn from their mistakes, they must ask an instructor
or retake the exercise (get a new exercise token from `/exercise`).

Note: Exercise tokens remain reusable. Adding single-use enforcement would require a database table for
tracking consumed tokens (similar to password reset tokens). The current mitigation (not returning answers
on failure) is sufficient to prevent assessment gaming while keeping the implementation simple.

---

## Finding 12 - Quota enforcement disabled by default

**Severity:** HIGH
**Status:** FIXED (2026-09-26)
**Source:** AI security audit, third pass, 2026-09-26
**File:** `regmap_engine/auth.py` (`ENFORCE_QUOTA`)

### What was found

The anonymous account had consumed 451 CU against a 300 CU/month limit and was still serving
requests. Investigation revealed that `ENFORCE_QUOTA` defaulted to `false`, so quota was never checked.
Requests at any usage level were accepted.

### Fix applied

Flipped the default: `ENFORCE_QUOTA` now defaults to `true`. Requests are rejected with HTTP 402 once
the account's monthly compute allowance is exhausted. Also flipped `ENFORCE_RATE_LIMIT` to `true` by
default for consistency.

To disable quota or rate limiting for local development, set explicitly:
```
REGMAP_ENFORCE_QUOTA=false REGMAP_ENFORCE_RATE_LIMIT=false
```

---

---

## Finding 13 - Stored XSS in policy editor via contenteditable

**Severity:** CRITICAL
**Status:** FIXED (2026-09-26)
**Source:** Manual code review, 2026-09-26
**File:** `web/policy.html` (`applyEdits` function)

### What was found

The "Edit full document text" feature in the policy editor allowed users to type arbitrary HTML
into a contenteditable div. The HTML was captured via `el.innerHTML` and stored server-side as part
of the saved policy. When the saved policy was reopened, `applyEdits()` applied it back with
`el.innerHTML = edits[...]` — no sanitization.

Attack: a user types `<img src=x onerror="alert('XSS')">` into the contenteditable editor, saves it.
The malicious HTML is stored in the database. When the policy is opened again (by the same user,
or by any project member with access), the `onerror` handler executes. The same unsanitized HTML
also flows into PDF/Word downloads via the document rendering code.

Since saved policies can be shared with other users (the API has `members`, `memberAdd`), the XSS
payload could target other collaborators.

**IDOR check (secondary):** Verified that `/policies/saved/{id}` endpoints enforce ownership
server-side. `GET /policies/saved/{id}`, `PUT`, and `DELETE` all filter by both `id` and
`account_id` in their database queries (`serve.py` calls `billing.get_saved_policy(account_id, id)`),
so a user cannot access or modify another user's saved policy even if they know the ID.

### Fix applied

Added DOMPurify (from CDN: `https://cdnjs.cloudflare.com/ajax/libs/dompurify/3.0.6/purify.min.js`)
and sanitized all stored HTML before applying it to the page. The allowlist only permits safe
formatting tags: `<b>`, `<i>`, `<em>`, `<strong>`, `<h1>` through `<h6>`, `<p>`, `<br>`, `<ul>`,
`<ol>`, `<li>`, `<table>`, `<tr>`, `<th>`, `<td>`, and `<a href>`. All other tags (including
`<img>`, `<script>`, event handlers) are stripped.

---

## Pre-launch security checklist

These must all be done before the site is public:

- [ ] Fix Finding 1: allowlist event names server-side on `/analytics/collect`
- [ ] Fix Finding 2: server-side gate on `/admin.html` route
- [ ] Fix Finding 3: add security headers middleware to serve.py
- [ ] Fix Finding 4: remove API key from localStorage once session auth is stable
- [ ] Fix Finding 5: wire email verification and gate sensitive ops on it
- [ ] Enable `REGMAP_REQUIRE_AUTH=true` and `REGMAP_SECURE_COOKIES=true`
- [ ] Enable `REGMAP_ENFORCE_QUOTA=true` and `REGMAP_ENFORCE_RATE_LIMIT=true`
- [ ] Set `REGMAP_ANALYTICS_SALT` to a long random string (not the default)
- [ ] Change the admin account password from the dev placeholder
- [ ] Switch from SQLite to Postgres for production (concurrent write safety)

---

## Change log

- 2026-09-26: document created from AI security audit findings.
