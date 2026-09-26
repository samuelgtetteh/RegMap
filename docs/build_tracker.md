# RegMap build tracker

The living status of what we are building now: RegMap as a two-pillar product. Start each session
here. Update the checkboxes and the log at the bottom as work lands. Sibling docs
`build_log.md` (hosted-SaaS engine build) and `progress_log.md` (research history) cover earlier phases.

Last updated: 2026-09-25. No em-dashes or en-dashes anywhere (founder style rule).

## What we are building

RegMap turns one proprietary asset, a curated, provenance-tagged map of how security frameworks'
controls line up, into **two products that share one ground truth**:

1. **Automate compliance** (for companies): map the controls you operate onto every framework you must
   satisfy, ranked and scored, with evidence and audit-ready reports. This is the crosswalk engine.
2. **Prove you can do the job** (for practitioners and teams): a full hands-on training platform where
   people do real compliance and security work and are graded against the same official ground truth,
   producing role-based, NICE-aligned evidence of skill.

Both pillars are a co-equal selling point in the business plan (`business_plan/business_plan.md`).

## The training platform (full scope)

Each track (Cybersecurity / SOC Analyst, IT Audit / GRC) is a complete learning experience, not just a
quiz. Every component maps to the same graded ground truth so progress is objective:

- [ ] **Reading material** concept briefs, the one resource that matters per topic.
- [ ] **Video tutorials** short walkthroughs per skill.
- [ ] **Graded labs** auto-graded exercises on real crosswalks (precision/recall). BUILT: `web/labs.html`.
- [ ] **Real-world practice** the learner creates actual systems and interacts with them (stand up a
      cloud environment, misconfigure/harden it, scan it, map findings to controls, assemble evidence),
      graded on what they built. Reuses the lab-environment work (`cloud-target-lab`, k8s lab sessions).
- [ ] **Gamification** XP, streaks, ranks, badges, leaderboards (TryHackMe / HackTheBox energy).
- [ ] **Evidence record** a shareable "performed these tasks, scored X" record tied to NICE work roles.
- [ ] **Saved progress / resume (required).** A student must be able to pause a lab, reading path, video,
      or real-world build and come back later to continue exactly where they left off. Reuse the saved-
      projects persistence pattern (`billing.py` `projects` table + `/projects` endpoints, keyed by
      account): add a learner-progress store (per user, per course/lab: position, answers, XP, streak,
      completion). This is a first-class RegMap University requirement, not an add-on.

## Status by area

### Platform / runtime
- [x] Consolidated the full build into this repo (commit `7635827`).
- [x] Single entry point `main.py` (`uvicorn main:app`); engine + platform routers on one app (`aa3e551`).
- [x] Single front end: the `web/` shell is the front door; engine APIs wired in (`169bea6`).
- [ ] Align the Docker image to `main:app` so the container serves the unified app (still `serve:app` / `app:app`).
- [x] **Decided the fate of the Identity and OT/ICS engines: repurpose them as continuous compliance
      monitoring** (confirm mapped controls are operating, not just documented). Surfaced on the console
      as coming-soon cards (Identity control monitoring, OT/ICS control monitoring); to be developed
      further. Artifacts remain present and load (`0b8e015`).

### Continuous monitoring (new pillar-1 capability, coming soon)
- [x] Console cards for Identity and OT/ICS control monitoring, framed as "confirm compliance is being
      met", marked coming soon.
- [ ] Build Identity control monitoring: watch auth/access signals, confirm AC/IA controls, flag drift.
- [ ] Build OT/ICS control monitoring: watch telemetry against control thresholds, flag breaches.
- [ ] Tie monitor findings back to the mapped controls and the evidence/report layer.

### Pre-launch checklist (do before publishing a live site)
- [ ] **Re-enable enforcement.** During pre-launch, quota (402) and rate limits (429) default OFF so
      nothing is blocked while we build (`REGMAP_ENFORCE_QUOTA` / `REGMAP_ENFORCE_RATE_LIMIT`, in
      `regmap_engine/auth.py`). The k8s deployment already sets both to `true`; make sure any other live
      deploy path (docker run, another host) sets them true too, or flip the defaults back to `true`.
- [ ] Turn on `REGMAP_REQUIRE_AUTH` and `REGMAP_SECURE_COOKIES` (behind TLS) for the live site.

### Front end
- [x] **LAYOUT LOCKED (2026-09-25, git tag `design-baseline-v1`).** The current layout is the final
      baseline. Spec + change protocol: `docs/design_system.md`. All future front-end work extends this
      system without diverging; retune token values but never rename tokens; bump the `?v=` cache-bust
      when CSS/JS changes; record visual changes in the design_system.md change log.
- [x] New design system `web/assets/site.css`: Linear + Vanta + Datadog, dark-first, proven cyber palette.
- [x] Generated SVG imagery (no icons): hero crosswalk, compliance coverage, training terminal, two tracks.
- [x] Homepage `web/index.html` rebuilt on the new system, two pillars, business-plan aligned.
- [x] New compliance console `web/console.html` at `/dashboard`, replacing the old detector monitor.
- [ ] Bring `compliance.html`, `labs.html`, `pricing.html` fully onto the new visual system.
- [ ] Expand `labs.html` into the full training experience (reading, video, labs, real-world builds).
- [ ] Account / sign-in surface in the shell (`account.html`), and gate paid items.

### Policy tab (new progress path, added 2026-09-25)
The Policy tab (`web/policies.html`, nav between Compliance and Labs) is a library of customizable,
industry-ready policies companies adopt. Shares the compliance ground truth: each policy maps to the
controls and frameworks it satisfies.
- [x] Page + nav + the first 10 essential IT policies (Acceptable Use, Information Security, Access
      Control, Password/Authentication, Data Classification, Incident Response, Backup/DR, Remote Access,
      Change Management, BYOD/Mobile), each with purpose, key contents, and mapped control families.
- [ ] Adopt a policy: view the full template text, edit/customize it in the browser.
- [ ] Industry tailoring: pick an industry (healthcare, finance, SaaS, defense) and generate a tailored set.
- [ ] Map each policy to the user's controls/frameworks (reuse the compliance engine).
- [ ] Versioning, approvals, and an export (DOCX/PDF) audit-ready policy pack.
- [ ] Grow the library beyond the first 10 (Data Retention, Vendor/Third-Party, Encryption, Physical
      Security, Privacy, Email/Communications, Vulnerability Management, Logging/Monitoring).

### Business / plan
- [x] Business plan reframed to two co-equal pillars; training is a major selling point (§1, 3, 7, 8, 10).
- [ ] Propagate the two-pillar framing to executive_summary, one_pager, pitch_deck_outline.
- [ ] Revisit the "three released open-source models" and OT/ICS grant angle after the detector decision.

### Billing / payments (from build_log.md, still open)
- [ ] Stripe payments (Phase C): subscriptions, overage, webhooks, self-serve signup, usage dashboard.
- [ ] Add training/skills plans (per-seat, team) to the pricing and billing model.

## Queued requests (raised mid-task; do after the current work)

- [ ] **Multi-page site: real independent pages for every placeholder link (raised 2026-09-25).** Build
      out the site like Google / Apple / Microsoft do: every link that currently points at `#` gets its
      own real, standalone page (its own URL, on the locked shell with nav + footer). For links with no
      content yet, ship a clean **"Page under construction"** page now, and finish the content later.
      Links needing pages (from `shell.js` footer + account bottom bar): Product (Coverage and gaps,
      Bring your own framework, Graded labs), Solutions (Automate compliance, Prove you can do the job,
      For GRC teams, For consultancies, For practitioners), Resources (Documentation, API reference,
      Benchmarks, Changelog, Status), Company (About, Careers, Contact, Security, Responsible disclosure),
      Legal (Privacy, Terms, Cookies, Licensing), Account bottom bar (Help, Privacy, Terms), and social
      (LinkedIn, GitHub, X). Approach: a reusable `web/page.html`-style "under construction" template (or
      one small page per route) that shows the title, a short line, and a link back home; then point the
      footer/nav hrefs at the real routes. Prioritise Legal (Privacy, Terms) and Contact first, since
      those are expected by users and auth flows. Do not gate anything on it.

- [ ] **Authentication for the project.** The founder wants auth. RegMap ALREADY has a purpose-built auth
      system (`regmap_engine/auth.py` + `billing.py` accounts/api_keys/sessions; `/auth/register`, `/login`,
      `/logout`, `/session`, `/keys`; scrypt passwords; guest browsing; `regmap_engine/web/account.html`).
      It is currently OFF in dev (`REGMAP_REQUIRE_AUTH=false`). The founder also has an auth build from a
      DIFFERENT project on this machine and asked to find it and port what is useful. NEXT STEP: locate
      that other auth, compare it with RegMap's existing auth, and recommend finish-existing vs port-parts
      (do not blindly replace the existing auth, it is wired into billing/quota/sessions). Decide, then
      wire an account UI into the current `web/` shell (login/register/account), since the shell has no
      account page yet.

## Session log

**2026-09-25** Consolidated the repo; built the single entry point; made the `web/` shell the one front
end and wired the engine pages; added the detector artifacts (then refocused away from them); reframed
the business plan to two pillars and elevated training as a major selling point; set a global no-dash
rule; began the full front-end redesign (new design system, generated SVG imagery, rebuilt homepage,
new compliance console). Next: finish the page redesigns and build out the training platform.

## Resume pointer

The unified app runs with `uvicorn main:app` (dev instance often on port 8010; production intent is
port 2500 / the container). Front end lives in `web/` (shell: `index.html` + `assets/{site.css,app.css,
shell.js,api.js}` + `img/*.svg`). The console is `web/console.html`. Next actions: finish moving
`compliance/labs/pricing` onto the new system, build the training platform components into `labs.html`,
and resolve the detector-code and Docker-image decisions.
