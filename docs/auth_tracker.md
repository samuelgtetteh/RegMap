# Auth tracker

Plan and status for authentication on RegMap. Decision (2026-09-25): keep the existing integrated auth
(it is wired to billing), add email verification and password reset, and surface the billing link
(plan, usage, keys) in a new account UI on the current `web/` shell. No em-dashes or en-dashes.

## What exists already (integrated auth, keep this)

`regmap_engine/auth.py` + `billing.py`: email + scrypt passwords, opaque server-side sessions (HttpOnly
cookie), API keys with scopes, guest browsing, and a paywall, all tied to `accounts` -> `plans` -> quota
and metering. Endpoints: `/auth/register`, `/auth/login`, `/auth/logout`, `/auth/session`, `/auth/keys`.
Not built yet: email verification, password reset, and an account page in the NEW shell (only the old
`regmap_engine/web/account.html` exists).

The standalone `auth_service/` (from ai-cybersecurity-portfolio) is inferior (username/password, PBKDF2,
not integrated) and is NOT being used.

## Security bar: best-practice, Google-grade where feasible

Target modern best practice. Realistic now vs roadmap:
- **Now:** scrypt (memory-hard) hashing; email verification; password reset (token, single-use, expiring);
  TOTP two-factor (Google Authenticator compatible) with recovery codes; brute-force protection
  (per-account + per-IP login lockout with backoff); opaque server-side sessions (HttpOnly, SameSite,
  Secure), revocable, with "sign out everywhere"; password strength minimum; identical error messages
  (no account enumeration); an auth audit trail.
- **Roadmap (need external setup or are large):** OAuth / "Sign in with Google" (needs a Google OAuth
  client); passkeys / WebAuthn (FIDO2) for phishing-resistant login; breached-password check
  (HaveIBeenPwned k-anonymity); risk/anomaly scoring; SSO/SAML for enterprise.

Honest note: we cannot literally match Google (their scale, OAuth ecosystem, hardware-key and ML risk
systems). We can match the security fundamentals a serious product needs, and leave clean seams for the
roadmap items.

## Build plan

### A. Backend enhancements (billing.py + serve.py) DONE 2026-09-25, verified
- [x] `accounts.email_verified` flag, plus lockout (`failed_logins`, `lockout_until`) and 2FA columns
      (`totp_secret`, `totp_enabled`, `recovery_codes`); added by `_migrate`.
- [x] `auth_tokens` table (token_hash, account_id, kind, expires_at, used_at).
- [x] `create_auth_token` / `consume_auth_token` / `set_email_verified` / `account_by_email` /
      `check_password` / `open_session` in billing; login lockout after 5 fails for 15 min.
- [x] Endpoints: `POST /auth/verify`, `/auth/verify/resend`, `/auth/reset/request`, `/auth/reset`,
      `/auth/password`. Register issues a verify token; verify/reset links are returned in dev responses
      and logged (gated by `REGMAP_EMAIL_ENABLED`).
- [x] `email_verified` surfaced in `/auth/session`.
- [x] **TOTP 2FA DONE 2026-09-25, verified.** Hand-rolled RFC 6238 (Google Authenticator compatible),
      no dependency. Endpoints: `/auth/totp/setup` (secret + otpauth URI), `/auth/totp/enable` (confirm a
      code, returns 8 one-time recovery codes), `/auth/totp/disable` (password-gated), `/auth/login/totp`
      (finish a 2FA login with a code or recovery code). `totp_enabled` surfaced in the session. Verified:
      enrol, login prompts for the code, TOTP and recovery-code logins work, wrong code is rejected.

### B. Account UI on the new shell
- [ ] `web/account.html` (data-page="account"): signed-out = sign in + register; signed-in = account
      (email, verification status, plan, usage/remaining CU, API keys, sign out), password change, and a
      reset flow. Uses the existing `/auth/*` + `/me`.
- [ ] Nav auth state in `shell.js`: "Sign in" when a guest, the account (email / remaining CU) when
      signed in; add an Account entry. Call `/auth/session` on load.

### C. Billing link
- [ ] Account page shows plan, CU used and remaining, and API keys from `/me` (already billing-backed);
      an Upgrade call to action (Stripe is Phase C in build_log.md).

## The only gate (product rule, 2026-09-25)

Guests can use every feature; login is not required to work. The single difference for signed-in users:
- **Save progress:** signed-in users can save their work (projects). Guests keep their work only in the
  page and lose it on reload (no save). Enforce: `POST/PUT /projects` require a real account (reject the
  anonymous principal), not `REGMAP_REQUIRE_AUTH`.
- **Download files:** downloading an export requires being signed in. A guest can instead opt to have the
  file **emailed** to an address they give. Enforce: `GET /projects/{id}/export` requires a real account;
  add an "email me the file" path for guests (needs the email sender, so this is pending email infra like
  verification/reset).
- [x] Gate save (POST/PUT/DELETE /projects) on a real account. DONE, verified (guest 401).
- [x] Gate download (export) on a real account. DONE, verified (guest 401). Email-it option pending email infra.
- [ ] Frontend: prompt to sign in at the save/download moment; guest export offers "email it instead".

## Notes / decisions
- **Login is NOT required to use features.** Everything works for guests; the only differences are the
  two gates above (save progress, and download vs email). `REGMAP_REQUIRE_AUTH` stays false; the gates are
  enforced per-action (reject the anonymous principal) rather than by blocking the whole API.
- Enforcement (quota/rate limits) also stays OFF for pre-launch, per the earlier decision.
- Email verification and password reset need a real email sender before launch; until then, dev returns
  the links directly.

## Change log
- 2026-09-25: created; decision to enhance the integrated auth (option 3) and link the account UI to billing.
