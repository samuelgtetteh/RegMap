# Progress Log

Dated entries of what changed each working session, so a new day can start by
reading the latest entry instead of reconstructing context from scratch.
Newest entry at the top.

## 2026-07-17 — Identity + OT/ICS detectors shipped as standalone systems (like RegMap)

Packaged and PUBLISHED the other two models the same way as RegMap (open, Apache-2.0, out-of-box):
- Identity Anomaly Detector: HF stetteh/identity-anomaly · GitHub Release v0.1-identity · Docker ghcr.io/samuelgtetteh/identity-anomaly:0.1/:latest (serving POST /score). packaging/identity/ (identity_score.py 9-feat+rolling window, serve.py, card, Dockerfile) + scripts/make_identity_release.py. Verified: burst -> anomaly.
- OT/ICS Intrusion Detector: HF stetteh/otics-anomaly · GitHub Release v0.1-otics · Docker ghcr.io/samuelgtetteh/otics-anomaly:0.1/:latest (serving POST /score, GET /example). packaging/otics/ (otics_score.py autoencoder+baseline, serve.py, card, Dockerfile) + scripts/make_otics_release.py. Verified: tampered reading -> anomaly.
- Exhibits 12A (Identity) + 13A (OT/ICS) standalone-release addenda; README table of all 3 released models; petition insert expanded to all 3 (+combined paragraph).
- All GHCR packages still PRIVATE by default — user to make public + link to repo (3 packages: regmap-embedder, identity-anomaly, otics-anomaly).

## 2026-07-17 — RegMap shipped as a public model (GitHub Release + Hugging Face + GHCR)

Packaged and PUBLISHED the fine-tuned RegMap embedder so anyone can use it out of the box:
- GitHub Release: v0.1-regmap (regmap-embedder-release.zip = model + HIPAA corpus + inference wrapper + serve.py + Dockerfile).
- Hugging Face: https://huggingface.co/stetteh/regmap-embedder (model + model card + corpus; verified model.safetensors 90MB present).
- Docker/GHCR: ghcr.io/samuelgtetteh/regmap-embedder:0.1 and :latest — a serving image (FastAPI POST /map -> top-k HIPAA controls, 2.17GB, CPU torch). Verified locally (MFA control -> 164.312(d)). NOTE: GHCR packages are PRIVATE by default — make public + link to the repo in the package settings to show on the repo Packages tab.
- Packaging source: packaging/regmap/ (LICENSE Apache-2.0, README model card with honest metrics — assistive top-k retriever recall@5~0.74, regmap_map.py, serve.py, Dockerfile, PUBLISHING.md); scripts/make_regmap_release.py builds dist/ (git-ignored).
- Exhibits added/updated: 11A (RegMap reusable+published), 18 (Vulnerability-to-Compliance Assessment Tool), 19 (Integrated Security Platform), 15 refreshed.

## 2026-07-16 — Unify scan tools: one "Assess" workflow + Help page (retire standalone SecureScan)

Retired the duplication (two scanners, two tabs). SecureScan's engine now feeds compliance mapping;
the standalone SecureScan tab is gone. Nav is now **Monitor · Assess · Help**.
- Backend (commit 7932786): `securescan/analyze.py` (shared analyzer: any scan_report → per-host
  ports→CVEs+KEV/EPSS + service/port→NIST category → control_mapper), `securescan/discovery.
  scan_network` (one engine for single host OR CIDR range), `advisor_api` rewired to
  securescan.scan_network + analyze (dropped control-advisor network_scan) + `POST /advisor/ingest`
  (ingest a SecureScan/agent scan report and analyze it — the "ingest + verify" path).
- UI: `view-scan` removed; `view-advisor` → **`view-assess`**, an industry-standard stepper
  (1 Scan & findings → 2 Interview → 3 Report). Step 1 offers **Scan from server / Use an agent /
  Import a report** + questionnaire-only mode. After a scan, `renderFindings()` shows the unified
  findings (hosts, ports, CVEs with **KEV/EPSS** + mapped categories) to VERIFY, with
  "Generate compliance package →" (or stop = scan-only). Engine catalog + import folded in.
  Agent path now calls `/advisor/ingest` so it also gets CVEs/KEV, not just controls.
- New **Help** page (`view-help`) with full site usage instructions; ☰ menu About → Help.
- Tests: advisor tests updated for the rewire + `/advisor/ingest`; 71 pass (only the pre-existing
  incomplete auth_service test fails).

## 2026-07-16 — SecureScan Phase 2: engine catalog + KEV/EPSS enrichment + import (Nessus/OpenVAS/nuclei)

Phase 2, reframed (per the Nessus/OpenVAS comparison) as ORCHESTRATE + INGEST + our compliance/
prioritization layer — not a Nessus clone.
- `securescan/catalog.py`: single source of truth for all engines (discovery: socket/nmap/masscan/
  naabu/rustscan; vuln: nuclei/grype; cloud: prowler/scoutsuite; passive: zeek/p0f; import:
  nessus/openvas/nuclei; enrichment: nvd/cisa_kev/epss/osv) with per-engine AVAILABILITY detection
  (shutil.which / lib check) + how-to-enable. Nothing faked as available.
- `securescan/enrich.py`: CISA KEV (known-exploited) + FIRST EPSS (exploit probability), cached,
  best-effort; `risk_score()` blends CVSS + KEV floor + EPSS → a poor-man's VPR. Wired into
  `POST /scan` CVE results (each CVE gets in_kev/epss/risk; host_max_risk + kev_count).
- `securescan/importers.py`: parse Nessus .nessus XML / OpenVAS-GVM XML / nuclei JSON(L) →
  normalized findings {host,name,severity,cvss,cve_ids}; stdlib only, defensive.
- scanner_api: `GET /scan/catalog`, `POST /scan/import` (parse + enrich + rank by risk).
- UI (SecureScan): engine-catalog panel (status badges + enable hints), "Import a scan report"
  upload (KEV/risk table), and KEV + EPSS badges on live scan CVEs.
- Honest framing: SecureScan orchestrates best-of-breed engines and ingests Nessus/OpenVAS output;
  our original contribution is CVE->NIST 800-53 mapping + KEV/EPSS prioritization + the advisor.
- Tests: +4 (catalog, importers on samples, enrichment mocked, import endpoint). 70 pass.
- CLI engines (masscan/naabu/nuclei/grype/prowler/…) are DETECTED + documented but execution
  wiring is not shipped (can't verify without the binaries) — availability shows in the catalog.

## 2026-07-12 — LLM-driven conversational interview (Qwen) — replaces the form

The interview regressed to a static free-text form interpreted only by the embedder; the intended
design is a Qwen-driven CONVERSATION. Rebuilt as a stateful chat (guided + embedder-extraction, the
user's chosen options): Qwen asks ONE contextual question at a time and clarifies when unsure, the
RegMap embedder extracts each answer to a structured field, and a checklist guarantees full
coverage for the compliance mapping. Degrades to canonical question text if the LLM is absent.
- advisor_api: `POST /advisor/interview/start` + `/reply` (stateful sessions `_INTERVIEWS`),
  `GET /advisor/interview/{sid}`. Qwen via control-advisor `llm_interview._generate` (SHARED with
  draft_language → one model instance); `_question_for`/`_clarify_for` with canonical fallback;
  `_next_field` = BASE_ORDER (sector, regulated_data, internet_facing, maturity, deployment_model,
  cloud_providers, has_ot_ics, remote_workforce, endpoints_managed) then adaptive FOLLOWUP triggers;
  embedder extraction via semantic_answer; clarify at most once per field; background model warmup
  on session start.
- Dashboard: chat UI (assistant/user bubbles, one question at a time, "thinking" indicator,
  captured-facts chips, Enter to send) replacing the all-questions form; on completion → context
  feeds the report step.
- Deploy decision (user): **mount** the local Qwen model read-only into the container (no image
  bloat) — recreate RedMap with `-v <repo>/models/qwen2.5-1.5b-instruct:/app/models/qwen2.5-1.5b-instruct:ro`.
  Runs on CPU (~7-12s/turn on the 1.5B model; first turn slower due to load; warmup mitigates).
- Tests: +2 (interview flow to completion; clarify-once-then-advance), model/embedder stubbed +
  warmup stubbed so CI stays fast. 66 pass (only the pre-existing incomplete auth_service test fails).

## 2026-07-12 — Scan target fixes (whitespace + oversized range)

Two bugs the user hit in the Advisor scan (screenshots):
- `10.0.0.1 / 24` (spaces around the slash) failed with "could not resolve …" — the target was
  treated as a hostname. Fix: `_normalize_target()` strips all whitespace and canonicalizes a CIDR
  to its network form ("10.0.0.1 / 24" -> "10.0.0.0/24"); applied in advisor `/scan` and SecureScan.
- "Discover environment" auto-filled `172.17.0.0/16` (the container's bridge netmask) -> "over the
  256 limit". Fix: `/advisor/environment` now caps each interface's `suggested_range` to a **/24**.
- Also: exposed a **Max hosts** field in the Advisor server-scan form (default 256, up to 4096;
  physical only) and raised the API cap to 4096; UI trims whitespace before sending.

## 2026-07-12 — Advisor Phase 1 (conversational interview) + on-prem scan agent

Two things the user flagged after the control-plane redesign.
**(1) Interview UX restored to conversational free-text.** The redesign had regressed it to
radio/checkbox ticks; the design is natural-language. Now each question is a free-text box and the
RegMap embedder interprets it (no LLM), company name first, with an inline "understood: X" review.
- `POST /advisor/interpret {responses:{qid:text}}` → per-question resolved value(s) + label +
  confidence via `semantic_answer` (embedder). Enriched the expanded yes/no descriptions so binary
  questions interpret reliably. Committed 9a5d3e7.

**(2) On-prem scan AGENT (scan a private network a cloud console can't reach).** A cloud host can
scan any internet-reachable target's PERIMETER, but not devices inside a NAT'd LAN. The agent is a
small pure-Python script the user runs on a host INSIDE the target network; it scans locally and
submits results back, which are mapped to NIST controls and feed the Advisor.
- `backend/agent/agent.py` — self-contained stdlib TCP connect scanner (port→category table),
  auto-detects local /24 or takes a target; fetches job config, scans, POSTs results. User-run
  (explicit approval), token-scoped, prints what it does.
- `backend/agent_api.py` (`/agent`): POST /jobs (token-scoped job + ready-to-run commands),
  GET /agent.py (download), GET /jobs/{id}/config?token (agent scope), POST /jobs/{id}/results
  (token-auth → control_mapper), GET /jobs/{id} (console polls; returns scan+recommendations when
  complete, never the token), GET /jobs.
- UI: Advisor scan step now has a **scan-method selector** — *Scan from server (target/WAN)* vs
  *Use an agent*. Server path notes that a WAN/public-IP scan = perimeter only. Agent path creates
  a job, shows PowerShell/bash run commands, and polls until results arrive → Start interview.
- Tests: `tests/test_agent.py` (2) job lifecycle + token auth + script download. Suite green.

## 2026-07-12 — Native Windows run for true physical-LAN scanning (Docker can't give a LAN IP)

User asked to give the Docker container the same IP as the physical LAN. That is NOT possible on
Docker Desktop for Windows (4.80, WSL2) over Wi-Fi: containers run in a NAT'd Linux VM; macvlan
(the only way to put a container on the physical L2) is unsupported on Docker Desktop and doesn't
work over Wi-Fi. TCP scanning works via NAT, but no LAN IP / proper host discovery.
- Fix: `run_native.ps1` — runs the backend natively on Windows via the existing venv (uvicorn
  app:app from backend/). The process then has the host's real LAN identity.
- PROVEN: native `/advisor/environment` reports 10.0.0.71 / 10.0.0.0/24, outbound 10.0.0.71,
  docker:False (vs the container's 172.17.x); native scan of 10.0.0.1 → up, ports 53/80/443.
- Launcher: `.\run_native.ps1 [-Port 2500] [-AllowAny]`; VERDICT_DB=data/verdicts_native.db (host),
  binds 0.0.0.0 so it's reachable on the LAN. Stop the RedMap container first if sharing port 2500.
  nmap.exe not on host → socket engine (works); install nmap for the richer engine (optional).
- Alternative (not set up): WSL2 mirrored networking (.wslconfig networkingMode=mirrored) can make
  WSL share the host IP; fiddly/version-dependent. Native run is the reliable path.

## 2026-07-12 — Scan fixes: physical/WAN scanning, network-type picker, modes, authz warning

Diagnosed why scanning "wasn't working" and fixed the UX. Root causes: (1) WAN targets returned
403 (no SCAN_ALLOW_ANY on the container), (2) the UI defaulted to 127.0.0.1 (the container
itself). The physical LAN was actually reachable all along — the bridged container reaches the
host LAN (10.0.0.0/24) via Docker NAT (verified: scanned the gateway, got open ports).
- **RedMap recreated with `SCAN_ALLOW_ANY=1`** (user-authorized) so any target can be scanned;
  the UI now gates every scan behind an "I am authorized to scan this target" checkbox + a
  persistent authorized-use warning banner (SecureScan + Advisor).
- **advisor_api**: `GET /advisor/providers` (physical FIRST, then aws [wired via boto3], azure/gcp/
  other [planned, honest `implemented:false`]); `POST /advisor/scan` takes `provider` and returns
  501 for unwired providers; `GET /advisor/questions?expanded=true` adds environment-determining
  questions (deployment_model, cloud_providers, has_ot_ics, remote_workforce, endpoints_managed);
  `_classify_environment` derives a profile; `POST /advisor/report` now supports TEMPLATE-ONLY
  mode (no scan → baseline controls + questionnaire) and returns the environment profile.
- **Advisor UI**: a **mode selector** — "Scan my environment" vs "Generate a compliance template"
  (questionnaire-only, no scan); a **network-type picker** (physical first + AWS/Azure/GCP/Other,
  planned ones disabled with a note); an always-available **Discover environment** button that
  auto-fills the detected LAN range; authorization warning + ack; expanded interview in template
  mode; environment-profile shown on the report.
- **SecureScan UI**: authorized-use warning + ack checkbox + a Discover-environment button.
- Tests: 4 new advisor tests (providers, expanded questions, 501, template-only report). Suite:
  61 pass. Note: Azure/GCP scanning are UI options but not yet implemented (need provider SDKs).
- Reminder: dashboard is still unauthenticated — with SCAN_ALLOW_ANY on, do NOT expose it beyond
  localhost until BC.4 (login/auth) is built.

## 2026-07-12 — Browser control plane: menu + multi-tool UI + Compliance Advisor wired in

Redesigned the RegMap browser interface into a full **control plane** — a menu + tool navigation
with multiple views, so everything the app can do runs from the browser. Also reconciled the
pre-existing `control-advisor/` toolkit by wrapping it behind an API + UI (the "PowerShell tool in
the browser" the user asked for: scan → interview questions → downloadable documents).
- `backend/advisor_api.py` (new, `/advisor`): wraps control-advisor — `GET /environment`
  (detect_environment), `POST /scan` (network_scan/cloud_scan + control_mapper → NIST 800-53 via
  the RegMap embedder), `GET /questions` + `POST /followups` (the interview as an ADAPTIVE FORM;
  triggers evaluated server-side, no LLM needed), `POST /report` (prioritize → DOCX/XLSX/JSON via
  docx_report/xlsx_report/report_export), `GET /report/{id}/{fmt}` downloads, `GET /health`.
  Authorization reuses securescan.authz (SCAN_ALLOW_ANY opt-in). LLM language (exec summary +
  drafted policy) is OPTIONAL (`with_language`) and degrades to a templated summary when Qwen is
  absent — so it's fast and works without the LLM in the image. control-advisor imported by adding
  its `scanner/` dir to sys.path.
- `backend/dashboard/index.html`: turned the single dashboard into a **multi-view SPA** — a `☰`
  dropdown menu (Monitor/SecureScan/Compliance Advisor/Settings/Export trail/API/About) + tool
  nav tabs + hash routing. Views: **Monitor** (the existing live SSE console), **SecureScan**
  (target/ports/engine form → per-port results + CVEs w/ CVSS pills), **Compliance Advisor**
  (3-step stepper: detect env & scan → adaptive interview form → generate report w/ exec summary,
  a prioritized controls table, and DOCX/XLSX/JSON download buttons). Settings stays a drawer,
  reachable from the menu.
- `tests/test_advisor.py` (5): health, base questions, adaptive followups, scan+map (mocked),
  full report generation + downloads (real docx/xlsx/json builders, no LLM). Full suite: 57 pass.
- Dockerfile: installs python-docx/openpyxl/psutil/boto3; COPYs `backend/advisor_api.py`,
  `control-advisor/scanner`, and `data/processed/labeled_pairs.csv` (control-advisor's corpus).
- This delivers browser-control BC.2/BC.3 intent (run scans/audits + everything from the page).
  BC.4 (real auth/login before mutating actions) still pending — flagged as important for a
  cloud-hosted deployment before exposing scanning/config broadly.

## 2026-07-12 — SecureScan Phase 1 (asset discovery + CVE mapping), platform-integrated

New tool `backend/securescan/` + `/scan` API: discover open ports/services on an authorized host,
map each service to CVEs (NVD), record findings into the same verdict trail as the detectors
(`model="scan"`). Built per docs/securescan_roadmap.md P1.
- **Pluggable engines** (`securescan/engines/`): `socket` (pure-Python TCP connect scan — default,
  NO external binary, runs in any cloud container, low-noise) + optional `nmap` (service/version +
  CPE; installed in the image, auto-selected when present).
- **`authz.py`**: scans restricted to loopback/private by default; `ALLOWED_SCAN_TARGETS` extends;
  `SCAN_ALLOW_ANY=1` is the deliberate opt-in for a cloud deploy meant to "scan any environment it
  is called into". Unauthorized target → 403 (never scanned).
- **`nvd.py`**: NVD 2.0 client with on-disk cache, polite rate-limit, optional `NVD_API_KEY`,
  CVSS v3.1/3.0/2 parsing; best-effort (never raises → degrades offline).
- **`cpe.py`** (CPE 2.2→2.3 / keyword query), **`discovery.py`** (authz→discover→enrich→report;
  `record_report` → verdict store, flagged if host max CVSS ≥ 7).
- **API** `backend/scanner_api.py` mounted in app.py: `POST /scan`, `GET /scan/engines`,
  `GET /scan/authorize`. Tests `tests/test_scanner.py` (9). Notebook `10_asset_cve_scan.ipynb`.
- Dockerfile installs nmap + python-nmap + requests; COPYs `backend/securescan`.
- Answered the user's tooling question first (low-noise/cloud-appropriate scanning: cloud-API
  inventory, SBOM/agent, passive, lighter active scanners, OSV/KEV/EPSS enrichment) — recommended
  pluggable engines; built socket+nmap now, others slot in later.
- ⚠️ FOUND pre-existing `control-advisor/scanner/` (network_scan/cloud_scan/control_mapper/…) —
  earlier scanning work to reconcile before P2/P3 (see roadmap doc); our package renamed
  `securescan` to avoid the name collision.
- Full suite: 52 pass. Deployed: image rebuilt (adds nmap) + RedMap recreated; `/scan` verified
  live. Bookmarked BC.4 (File/Edit/View/Settings menu + user login/auth).

## 2026-07-12 — BC.1: live settings menu (personalize limits from the browser)

Executed BC.1 of the browser-control plan: users can now retune the app's hard-coded limits from
the dashboard, applied live (no restart). The key refactor the plan called out is done — modules
no longer freeze env values at import; they read a live settings store at point-of-use.
- `backend/settings.py` (new): REGISTRY = single source of truth (type/range/label/help/default)
  for retention caps, policy thresholds, REGMAP_FLAG_THRESHOLD, AI_TRIAGE_LLM toggle; get()/
  effective()/update() (validated)/reset()/describe().
- `backend/verdict_store.py`: `settings` table + LOCK-FREE cache (preloaded at import, atomic
  swap on write → hot-path reads never deadlock the non-reentrant Lock); get_setting[_int/float/
  bool], set_setting_values, reset_settings, all_settings_raw. Retention (_auto_trim_locked,
  enforce_retention, stats) reads caps live.
- `policy.py` reads thresholds live in evaluate()/_weight_severity; `app.py` reads the regmap
  flag cutoff live; `llm_client.py` reads AI_TRIAGE_LLM live (`_local_enabled`).
- API: GET /decision/settings (grouped+values), PATCH /decision/settings (validated, live),
  POST /decision/settings/reset. UI: ⚙ header button → settings drawer (number inputs honour
  min/max/step, bool = toggle, "overridden" markers, Save + Reset-all).
- Tests: 20 pass (added describe/effective, live+validated update, live policy retune).
- DEPLOYED: settings.py added to Dockerfile; image rebuilt; RedMap recreated; verified live
  (PATCH MAX_VERDICTS→250k reflected in /stats, reset restored). docs/browser_control_plan.md
  marked BC.1 DONE (BC.2 job runner + BC.3 full control plane remain).

## 2026-07-12 — Analyst case-management workflow (Tier 1+2) + Exhibit 17

Turned the read-only alert queue (why/close) into a full human-in-the-loop case-management
workflow, driven entirely from the browser console. Everything committed + deployed (RedMap
rebuilt & recreated from the fresh image).
- `verdict_store.py`: alert lifecycle fields (`assignee`/`resolution`/`resolved_at`, status now
  open|acknowledged|closed) + migration; new `alert_events` table (case audit trail) + new
  `suppressions` table (allowlist). Fns: `verdicts_by_ids` (evidence), `update_alert`,
  `record_alert_event`/`query_alert_events`, `label_alert_verdicts` (loop-closing feedback),
  `add_suppression`/`query_suppressions`/`remove_suppression`/`is_suppressed`.
- `policy.py`: honours the allowlist — `is_suppressed(subject,model)` skips identity_burst /
  high_severity for allowlisted subjects.
- `actions.py`: `manual_action(alert,type)` on-demand responder + safe posture-change STUBS
  (`disable_account`, `step_up_auth` — recorded, no live IdP wired); `MANUAL_ACTIONS`.
- `decision_api.py`: `GET /decision/alerts/{id}` (detail: evidence + subject history + actions +
  events); POST `/acknowledge`, `/assign`, `/note`, `/resolve` (TP→malicious / FP→benign labels
  the evidence = trains the Decide layer), `/suppress`, `/act`; `GET /actions/available`;
  `GET`/`DELETE /suppressions`. `_overview` now keeps acknowledged (in-progress) alerts visible.
- `dashboard/index.html`: click a row → slide-in **case drawer** — meta, decision toolbar
  (Acknowledge/Assign/True-positive/False-positive/Suppress/Note/Close + Response:
  Ticket/Webhook/Disable-account/Step-up), AI-triage (on demand), evidence table, subject
  outcome history, response actions, and the case audit trail. Esc/backdrop closes.
- Design principles carried through: analyst decision is authoritative + feeds back to improve
  the system; LLM stays advisory; posture-changing actions are safe stubs (no attack surface).
- Tests: `tests/test_decision_layer.py` now 17 (added drill-down, ack/assign/note journal, TP
  resolution labels evidence, suppression blocks re-alert, manual-action stub recorded).
- Exhibit: `exhibits/build_exhibit17.py` → "Exhibit 17 Analyst Case-Management Workflow.docx".
- Bookmarked next: `docs/browser_control_plan.md` — make the whole project configurable/runnable
  from the browser (settings menu for hard-coded limits, run compliance audit/scanner from the
  page). Deferred to a fresh session (usage-limit checkpoint).

## 2026-07-12 — Live monitoring dashboard (SSE) replaces Swagger

Built a real-time operations console served at `/` (Swagger moved to background at /docs) so the
live decisioning is visible without clicking API endpoints.
- `backend/dashboard/index.html`: self-contained SSE console — status bar (LIVE pulse, events,
  events/min, open alerts, log-vs-cap), 3 process cards (Identity/OT-ICS/Compliance w/ live
  precision/recall), live decision feed (verdicts stream in, flagged highlighted), priority-sorted
  alert queue (why=triage / close / reassess), response-actions ticker.
- `GET /decision/overview` (aggregated snapshot) + `GET /decision/stream` (SSE push, init +
  incremental new verdicts every ~1.5s); `verdict_store.verdicts_since`/`max_verdict_id`; `/` serves
  the dashboard. Dockerfile COPYs backend/dashboard. 35 tests pass.
- DEPLOYED live: RedMap rebuilt + recreated (restart-persistent, verdict volume); dashboard at
  http://localhost:2500/ , SSE confirmed pushing. Open the URL to watch decisions in real time.

## 2026-07-12 — Decision layer: FIFO retention (bounded live-monitoring log)

The verdict trail is a live-monitoring log and was growing unbounded (~24.5k rows and counting).
Added a FIFO cap so the high-volume tables keep only the most recent N rows, oldest evicted first.
- `verdict_store.py`: env-configurable caps `MAX_VERDICTS` (100k), `MAX_REQUESTS` (100k),
  `MAX_ACTIONS` (50k), `RETENTION_TRIM_EVERY` (100); 0 = unbounded. Trim = `DELETE WHERE id <=
  MAX(id)-cap` (FIFO by autoincrement id). Batched auto-trim on insert (record_verdict/request/action),
  plus `enforce_retention()` run at startup (bounds an already-large DB) and exposed via
  `POST /decision/retention/enforce`; caps shown in `/decision/stats`.
- Eviction never affects detection: metrics/Decide use a recent window far smaller than any cap.
- Verified: pytest FIFO test (trims to cap, keeps newest, evicts oldest) — 33 tests pass; manual run
  of 500 inserts at cap=50 held the table at exactly 50 (ids 451-500).
- DEPLOYED 2026-07-12: RedMap rebuilt + recreated with `--restart unless-stopped` and the
  `redmap_verdicts` volume; retention is live (caps shown in /decision/stats), the ~25.7k trail was
  preserved, and the container now also serves the full decision layer (triage + reassess). The
  default 100k cap bounds future growth (doesn't shrink 25.7k); set MAX_VERDICTS lower to bound tighter.

## 2026-07-12 — Decision layer, Phase E2: LLM triage prioritization + shared sidecar

Makes the LLM *improve how decisions are handled* (queue ordering), safely and via a shared model.
- **Principle:** LLM is ADVISORY, never authoritative (hallucination + prompt-injection risk). It
  re-ranks/labels; deterministic rules + humans enforce. Kept OUT of the scoring/evaluate hot path.
- Every alert gets a deterministic default priority from severity at creation (high=4/med=2/low=1,
  scale 1-5); the queue orders by priority. The LLM REFINES priority + disposition
  (escalate|monitor|likely_false_positive) + rationale on demand via `POST /decision/alerts/{id}/
  reassess` (and batch `/decision/reassess`), CLAMPED to a severity floor so it can't bury a high alert.
- `backend/llm_client.py`: single LLM access point — prefers the sidecar (`LLM_SERVICE_URL`), falls
  back to in-process Qwen; `ai_triage` refactored onto it and given `assess(alert)` (RAG context +
  subject-outcome history + validated/clamped LLM JSON).
- **`llm-service/`**: a shared sidecar hosting ONE Qwen instance behind `POST /generate`. Per the
  user's steer, the existing model is **mounted** (not copied/re-downloaded); one instance is meant to
  serve the whole project (backend now; Control Advisor can adopt it later).
- Verified: 32-test suite green (LLM disabled in tests → deterministic default + clamp); local-LLM
  reassess produced disposition=escalate with priority clamped to the high floor. Dockerfiles updated
  (backend COPYs llm_client.py; sidecar mounts the model). Deploy of the sidecar container is the
  optional heavy last step (commands in docs/decision_layer_plan.md).

## 2026-07-12 — Decision layer, Phase E: AI triage (RAG + local LLM) — Track C+E complete

- `backend/ai_triage.py` + `GET /decision/alerts/{id}/triage`: for a given alert, retrieve the most
  relevant HIPAA provisions via the fine-tuned RegMap embedder (RAG over the /map corpus) and write a
  concise SOC triage summary with the local Qwen model (models/qwen2.5-1.5b-instruct, same loader as
  Control Advisor). Lazy (models load on first call), gated (`AI_TRIAGE_ENABLED`/`AI_TRIAGE_LLM`),
  best-effort (degrades to a templated summary + RAG context when the LLM is off/absent).
- Verified: (a) LLM-off → 3 relevant provisions (top "Unique User Identification") + templated
  summary; (b) LLM-on → Qwen produced a grounded what/why/next-action triage citing the retrieved
  controls. Dockerfile COPYs ai_triage.py.
- Container note: image ships regmap-embedder + corpus (RAG + templated work live) but NOT Qwen
  (~3 GB), so in-container `llm_used=false` unless Qwen is added to the image (deferred choice).
- This completes the full decisioning platform (Record → Decide → Act → AI triage). Reproducible
  walk-throughs: notebooks 08 (Record) + 09 (Decide/Act); decision-layer pytest suite (7 tests).
  Next: Exhibit 16 (document the live system as NIW evidence).

## 2026-07-11 (late) — Decision layer, Phase C3: Act (response layer)

- `backend/actions.py`: pluggable responders — `log` (always), `ticket` (medium/high, stub),
  `webhook` (high, only if `ACTION_WEBHOOK_URL` set; stdlib urllib, no new dep) — chosen by severity
  ROUTING. `dispatch(alert)` runs them and records each in a new `actions` audit table; best-effort
  (a responder failure is recorded status=failed, never breaks the pipeline).
- `policy.evaluate` now dispatches inline for each newly-created alert (Record→Decide→Act end to end;
  the dispatch() boundary is the seam for a decoupled stream consumer later). Dedup renamed to
  `recent_alert_exists` (any status) so an analyst's close stays sticky for the window.
- `verdict_store.py`: `actions` table + `record_action`/`query_actions`/`get_alert`/`close_alert`.
  `decision_api.py`: `GET /decision/actions` + `POST /decision/alerts/{id}/close`.
- Verified via TestClient: high alert → log+ticket fired (webhook skipped, unconfigured); close works
  and is sticky; missing-id → 404. Dockerfile COPYs actions.py.
- **Deployed live (C3.6):** RedMap rebuilt with actions.py + recreated on the persistent volume.
  Confirmed: evaluate created 5 alerts from the live stream and fired responders for each (log ok,
  ticket ok with SEC-N refs, webhook skipped/unconfigured). **Track C (Record→Decide→Act) is now
  complete and running live.** Next/final track: Phase E (AI platform — Qwen triage + RegMap RAG).

## 2026-07-11 (late) — Decision layer, Phase C2: Decide (policy/rules engine)

- `backend/policy.py`: rules over the recorded trail → durable `alerts`. Rules: **identity_burst**
  (>= N flagged logins from one src_user in a window), **ics_sustained** (>= N flagged ICS ticks),
  **high_severity** (single extreme-score verdict; ICS deduped to one/window, identity per subject).
  **Outcome weighting** uses the C1 feedback labels: chronic-false-positive subjects are suppressed,
  confirmed-malicious ones escalated. `evaluate()` is idempotent (dedup vs open alerts).
- `alerts` table + `record_alert`/`query_alerts`/`open_alert_exists`/`recent_verdicts`/
  `subject_outcome_history` in `verdict_store.py`. `GET /decision/alerts` (auto-evaluates) +
  `POST /decision/evaluate` in `decision_api.py`. Env-overridable thresholds.
- Verified via TestClient: burst→alert, sustained ICS→alert, idempotent re-eval, and benign-history
  SUPPRESSION all correct. Dockerfile updated to COPY policy.py.
- **Deployed live (C2.6):** RedMap rebuilt with policy.py + recreated on the persistent volume.
  Confirmed at scale from the running live-lab: 1,167 verdicts all auto-labelled; 5 alerts
  (identity_burst for the 3 attacker accounts w/ severity escalated by malicious history,
  ics_sustained, high_severity); live metrics precision 0.992 / recall 0.977 / specificity 0.994
  computed from the DB. Next phase: C3 (Act).

## 2026-07-11 (late) — Decision layer, Phase C1: Record + production logging/feedback

Started Track C (Record → Decide → Act) from `docs/development_roadmap.md`; plan +
checkpoint in `docs/decision_layer_plan.md`. Turned the stateless RedMap scorer into a
system that keeps an authoritative record of what it observed and decided.
- `backend/verdict_store.py` (stdlib SQLite): `verdicts` + `requests` tables; record/query/
  stats/metrics + ground-truth feedback. `backend/decision_api.py`: `/decision/verdicts`,
  `/requests`, `/stats`, `/metrics`, `POST /verdicts/{id}/feedback`.
- `backend/app.py` middleware logs every request, enriches each verdict with
  latency/status/client/path, and returns an `X-Verdict-Id` header; `/map`, `/identity/score`,
  `/ics/score` stash the verdict id. Ground truth is decoupled from scoring (a live analyst/
  SOAR/simulator attaches it by X-Verdict-Id) → `/decision/metrics` computes live
  precision/recall/specificity from the DB (persists the Exhibit 14 tally).
- SWaT dataset verified & acquired (106 MB CSV zip in data/raw/ + official iTrust request).
- `.gitignore`: exclude `data/*.db*` (runtime trail, not source). Reproducible in
  `notebooks/08_decision_layer_record.ipynb` (executed).
- **live-target-lab (separate repo):** `identity_generator.py` + `ics_generator.py` now read
  `X-Verdict-Id` and POST their known injected label to `/decision/.../feedback` (best-effort,
  `FEEDBACK` env toggle) so the live-lab auto-labels the trail. Verified end-to-end via TestClient.
- Next: C2 (Decide) — windowed policy rules over the trail, now able to weight by historical outcomes.

## 2026-07-11 (evening, cont.) — NIW evidence build-out + forward development roadmap

- Prepared **Exhibit 15: Summary of Research Progress and Body of Work** (`exhibits/Exhibit 15
  Research Progress and Body of Work.docx`, via `exhibits/build_exhibit15.py`) — a cumulative
  NIW exhibit quantifying the whole body of work (31 commits/9 active days, 78 files, 48 Python
  modules/8k+ lines, 10 notebooks, 3 manuscripts/~16k words/88 refs) and headlining the three
  papers now under peer review. All metrics measured from the repo; papers stated only as
  "submitted; under review" (never accepted/published).
- Added dated "under peer review" update notes to Exhibits 11/12/13 and the third-person
  "Project Include" narrative (`exhibits/apply_review_updates.py`, idempotent; originals backed up
  to `exhibits/_pre_review_update_backup/`).
- Drafted **`docs/development_roadmap.md`** — the post-submission plan to implement all five forward
  tracks (deepen science incl. synthesis paper; open-source benchmark+badges; Record→Decide→Act
  decisioning layer → Exhibit 16; recognition; LLM/agentic platform) in dependency-ordered phases.
  Key precedence: arXiv preprints first (unblock recognition); SWaT/WADI is a lead-time data request
  (kick off early, doesn't block synthesis); badges gated on paper acceptance; platform (E) follows
  the decisioning layer (C). Status: drafted, no phase started.

## 2026-07-11 (evening) — ALL THREE PAPERS SUBMITTED for peer review

- **Identity** → **TMLR** (OpenReview). Reviews expected ≤4 weeks, decision ~2 months.
- **OT/ICS** → **ACM DTRAP** (Manuscript Central), submitted from `paper/ot_ics/paper_dtrap.tex` —
  ACM acmart large-format, double-anonymized (generated by `paper/make_dtrap_versions.py`, which has a
  built-in identifying-string leak check; re-run it if paper.tex changes).
- **RegMap** → **ACM DTRAP**, from `paper/regmap/paper_dtrap.tex` (same pipeline). Earlier the same day
  the manuscript got a final quality pass to match the Bianchi/Gokhan exemplar bar: recovered real
  training hyperparameters (batch 16, 10 epochs, warmup 10%, AdamW lr 2e-5) from notebook 02 into the
  Method section, added a dataset-composition table (222 pairs / 159 train / 29 val / 34 test), and a
  formal DCG/nDCG definition.
- Cover letters drafted for both DTRAP submissions; CCS concepts + keywords baked into both dtrap files.
- Pending: DePaul library answer on ACM Open (APC coverage); Zhen Huang arXiv endorsement (code PPTQJN).
- Camera-ready reminders are in the header comments of both `paper_dtrap.tex` files (drop
  `anonymous,review`, restore GitHub URL, generate CCSXML at dl.acm.org/ccs, fix the "D Jarvis"
  affiliation typo in the ot_ics/identity originals).

## 2026-07-11 (later) — RegMap paper: full scholarly expansion + nDCG & group-split robustness

RegMap (NIST SP 800-53 → HIPAA) paper brought to the same standard as the other two.
Plan + resume checkpoint: `docs/regmap_expansion_plan.md`.

Manuscript (local `paper/regmap/paper.tex`, gitignored; this log is the committed record):
- Rewrote the ~1.5-page skeleton into a full manuscript: Introduction + Contributions, Background
  (crosswalking, why semantic retrieval, RegNLP), 4-part Related Work, Problem Definition, expanded
  Dataset/Method/Evaluation, single- AND multi-relevant results tables, Discussion, Limitations, Conclusion.
- Applied the DePaul author affiliation block; added references `bianchi26` (KES 2026, near-twin
  fine-tuned-SBERT method on EU cloud standards — positioned as complementary), `gokhan24` (RegNLP),
  `agarwal21` (NIST 800-53 mapping), `ahmed24` (CIS controls).

New experiments (`paper/regmap/eval_extras.py`; appended to `results_regmap.json`; mirrored in the
self-contained tracked notebook `notebooks/06b_regmap_extended_evaluation.ipynb`):
- nDCG@{5,10} on the pair-split (fine-tuned nDCG@10 0.544 vs base 0.434) to align with the
  cloud-compliance literature's metric.
- Stricter **group-split-by-control** (no control in both train and test; 33 queries from 20 controls):
  fine-tuned single-relevant Recall@5 **0.848** (95% CI 0.727–0.970), nDCG@10 0.677 — the fine-tuning
  gain is **undiminished** vs the pair-split (0.735), evidence the model learned framework-level
  correspondence rather than memorized phrasing.

Target venue: Cambridge *Natural Language Processing* (free via DePaul's Cambridge APC waiver;
see `docs/publishing/publishing_recommendations.xlsx`).

## 2026-07-11

**Identity paper: full scholarly expansion + two reproducibility fixes that changed the
headline. Robust-signal reframing (title changed).**

Expansion (local `paper/identity/`, gitignored; this log is the committed record):
- `paper.tex` rewritten from the ~600-word draft to a full ~4,600-word manuscript: Background,
  Threat Model, expanded 4-part Related Work (positioning vs Euler, LMDetect, Bowman's UA rule),
  Dataset (day-2 window + subsampling treatment), Method, and a Results section with per-feature
  attribution, feature-group ablation, leave-one-out, distributions, access-breadth rule, ranking
  (recall@FPR / precision@K), subsample invariance, and a prior-work positioning subsection; plus
  Discussion, Limitations, Conclusion.
- Added `euler` (King & Huang, TOPS 2023) and `lmdetect` (Zhou et al., arXiv 2411.10279) to
  `references.bib`; woven throughout.

New experiments (`paper/identity/eval_extras.py`; results appended to `results_identity.json`;
mirrored in self-contained tracked notebook `notebooks/07b_identity_extended_evaluation.ipynb`):
- Per-feature univariate AUC, feature-group Isolation Forests, leave-one-out, red-vs-normal
  distributions, access-breadth threshold rule, recall@FPR / precision@K, subsample invariance.

**Two determinism bugs found and fixed (this is why the headline moved):**
1. **Nondeterministic categorical encoding.** `sample[col].unique()` order is not stable in polars;
   since Isolation Forest treats the integer codes as ordinal, the ensemble AUC varied run-to-run
   (0.85-0.90). Fixed by sorting categories before encoding.
2. **Nondeterministic row order.** Streaming joins don't preserve order and IF samples rows by index,
   so the ensemble AUC still drifted. Fixed by a total-order row sort on all raw columns.
   After both fixes, base `auc` == extras `all_9.auc` == **0.900** exactly; fully reproducible.
   (The count features unique_pcs/hourly_count were always deterministic, so the central finding
   never depended on the bug.)

**Headline change (thesis reframed, user-approved "robust-signal framing"):**
- The old draft claimed access breadth (0.905) *beats* the ensemble (0.853). The 0.853 was an
  artifact of the buggy encoding. Corrected deterministic numbers: **ensemble AUC 0.900**
  (CI 0.893-0.908); **access breadth alone 0.905** (matches ensemble); **auth_type 0.931**
  (nominally highest but a fragile ordinal encoding of an unordered categorical -- documented as
  the fragility we hit); **login volume 0.423** (below chance -- noisiest accounts are legitimate
  service accounts, max 65,781 logins / 4,358 machines).
- **New operational finding that carries the paper:** at 10% FPR, access breadth recovers **0.96**
  of red-team logins vs the ensemble's **0.65** -- access breadth *dominates* in the low-FPR triage
  regime even though AUCs tie. Near-parameter-free rule (unique_pcs >= 20 machines) catches 47/48 at
  10% FPR.
- Title changed: "Access Breadth over Ensembles" -> **"Access Breadth as a Robust Signal for
  Credential-Based Lateral Movement: A Red-Team Feature-Attribution Study on the LANL Dataset."**
  Affiliation + artifact footnote (notebooks 07 + 07b) added.
- Verification: 44-point automated check passes; base==extras consistency confirmed; all citations
  resolve; figures present; stale 0.853 / "beats the ensemble" claims removed.

## 2026-07-10

**OT/ICS paper: full manuscript expansion + peer-review revision with new
experiments. Two major findings.**

Paper expansion (local `paper/ot_ics/`, gitignored — this log is the committed
record):
- `paper.tex` hand-expanded from the ~1,500-word generated draft to a full
  ~7,500-word manuscript (Background, Threat Model, dedicated pitfall sections,
  Experimental Setup, expanded Results, Limitations). **`paper.tex` is now
  hand-authored — do NOT re-run `build_latex.py` for ot_ics or it will clobber
  it.** The `.docx` variants still contain the old short text (out of sync).
- Added `kus22` (CPSS '22 "False Sense of Security"), `aslam24` (ImpAE, SSCE
  2024), `abshari26` (CPS anomaly-detection survey) to `references.bib`; all
  cited in the body. Target venue recommendation on record: USENIX CSET first
  (evaluation/reproducibility genre; HAI's home venue), IEEE Access fallback.
- Two peer reviews performed (mine: evidentiary gaps; external AI review:
  narrative framing — partially unreliable, two comments already satisfied in
  text, one fabricated quote). Merged into an 11-item revision plan, executed.

New experiments (`paper/ot_ics/eval_extras.py`, `leakage_attribution.py`;
results appended to `results_ot_ics.json`; runbook updated in `paper/README.md`):
- **Finding 1 — leaked model quantified exactly.** The original leaked artifact
  was preserved (`autoencoder_hai_leaky_backup.pth`, 63 inputs = 59 sensors +
  `attack`,`attack_P1/P2/P3`): ROC AUC = 1.000000, AP = 1.000000 exactly;
  100% recall @ 1% FPR (clean model: 64.2%). Label channels: MSE 50.1 on
  attacks vs 1.4e-4 on normals (5 orders of magnitude). **Deeper result: the
  contamination is model-deep** — sensor-channel errors ALONE still give AUC
  1.0 (leaked inputs steer the latent code), so a leaked model cannot be
  salvaged at scoring time; only retraining fixes it. New figure
  `figures/leakage_channels.png`.
- **Finding 2 — second pitfall: cross-session normal contamination.** Notebook
  04 pooled ALL FOUR files' normal rows before the 80/20 split, so ~80% of
  test-file normals (and the scaler) were seen in training by the deployed
  model. A strict session-disjoint retrain (identical arch/hypers: 50 epochs,
  batch 256, Adam lr=1e-3, seed 42; trained on 495,021 train-file normals;
  new artifacts `autoencoder_hai_strict.pth`/`scaler_hai_strict.pkl`) scores
  **AUC 0.869 / AP 0.682** vs the pooled 0.929/0.733. The paper now reports
  the full honesty ladder: leaked 1.000 -> pooled 0.929 -> strict 0.869.
- Nominal-vs-realized FPR calibration: percentile thresholds calibrated on
  held-out same-session normals overshoot on test-session normals by 2.1x
  (90th pct) to 26.2x (99.9th); default threshold: 9.1% same-session -> 20.1%
  test-session. The STRICT model is worse: nominal 5% -> realized 75.4% (15x),
  nominal 1% -> 53.4% (53x). Honest training improves ranking, worsens
  fixed-threshold calibration.
- Temporal alarm aggregation (min-run-length k): at p99 threshold, k=10 cuts
  alert episodes 1,788 -> 179 (10x) with segment recall 89.5% -> 84.2%; at the
  default threshold 7,946 -> 247 (32x), still catching 36/38 attack segments.
  38 labelled attack segments total in test1+test2.
- Per-process AUC per method: AE 0.932/0.979/0.897 (P1/P2/P3) vs PCA
  0.881/0.903/0.725 vs IF 0.806/0.837/0.719 — baselines fail hardest on P3.
- Block bootstrap (1-h blocks, 500 resamples): AUC 0.929 CI95 [0.893, 0.960];
  AP 0.733 CI95 [0.613, 0.827].
- Label structure: 5,169 test rows carry multiple per-process labels
  (why P1+P2+P3 counts = 22,696 > 17,527 global attacks); 0 unattributed;
  no attack_P4 column exists in HAI 21.03.
- Paper also gained: affiliation, artifact-URL footnote (GitHub + notebook 05),
  SWaT/WADI leakage warning, threshold-provenance paragraph (default 0.009223
  = 95th pct of pooled-split validation normals ~= 90.8th pct of train-session
  normals), threat-model->triage bridge, eTaPR reframed as thesis validation.
- Verification: 72-point automated check — every paper number matches
  `results_ot_ics.json`; all citations resolve; all 5 figures exist; no
  dangling refs.

**Consistency updates applied (dual-protocol presentation, user-approved):**
- `README.md`: Results-at-a-Glance row now "0.929 (pooled) / 0.869
  (session-disjoint)"; OT/ICS section rewritten around the honesty ladder
  (leaked 1.000000 exact -> pooled 0.929 w/ CI -> strict 0.869), calibration
  inflation note, alarm-aggregation row; repo layout lists notebook 05b.
- `Exhibit 13` DOCX: inserted new §4.4 "Protocol Audit: Leakage Quantified
  Exactly and a Session-Disjoint Re-Evaluation (July 2026)" (patched in place
  via python-docx; two paragraphs covering both findings, ladder, calibration,
  alarm filtering — framed as evidence of scientific rigor for NIW).
- `notebooks/05b_ot_ics_extended_evaluation.ipynb` (tracked, self-contained):
  mirrors eval_extras.py + leakage_attribution.py — leaked-model exact eval +
  channel attribution figure, strict retrain (loads deterministic artifact if
  present), nominal-vs-realized FPR, temporal aggregation, per-process AUC,
  block bootstrap. Executed with outputs embedded. Paper artifact footnote
  updated to cite notebooks 05 + 05b.

**Real-time decisioning plan, three scientific papers, and OT/ICS number corrections.**

Planning (committed):
- `docs/roadmap.md` — full phased plan (Phase 0 baseline → Phase 1 evaluation
  rigor → Phase 2 real-time decisioning → Phase 3 packaging → Phase 4 prod).
  Scope decision recorded: **a separate scientific paper per model** (not one
  integrated paper). arXiv baseline; Computers & Security / USENIX CSET /
  IEEE Access / MDPI as candidate venues (submit to one at a time).
- `docs/phase2_plan.md` — detailed real-time decisioning design, locked as
  **Hybrid architecture + TimescaleDB/Postgres single store + Grafana** (not yet
  built; Phase 2).

Scientific papers (drafts are LOCAL in `paper/` — that folder is gitignored per
request; this log is the referenceable record of what was done):
- `paper/ot_ics/` — "Label Leakage in ICS Anomaly Detection … HAI Testbed."
  Rigorous eval via `eval_ot_ics.py` on the canonical HAI test files
  (test1+test2, 444,600 samples, 17,527 attacks): **ROC AUC 0.929**, AP 0.733;
  beats PCA-recon (0.854) and Isolation Forest (0.804). Threshold-sensitivity,
  per-process breakdown, point-wise + point-adjusted metrics. 7 rendered
  equations; 27 verified references; 5-part Related Work; generalization-gap
  discussion (random split 5% FPR vs. session-disjoint test files 20% FPR).
- `paper/regmap/` — "Automated Regulatory Crosswalking … NIST 800-53 → HIPAA."
  Rigorous eval via `eval_regmap.py`: fine-tuning lifts Recall@5 0.500 → **0.735**
  and beats BM25 (0.353) and TF-IDF (0.500), bootstrap 95% CIs. 5 equations;
  25 verified references; 4-part Related Work.
- `paper/identity/` — "Access Breadth over Ensembles: A Red-Team Evaluation …
  LANL." Required acquiring the raw `auth.txt.gz` (7.6 GB) + `redteam.txt.gz`
  (the processed slices are day-1 only and predate red-team activity). Window
  [150000, 500000] extracted to `data/raw/auth_window.csv` (61.5M rows, 46
  red-team logins); `eval_identity.py` fits an Isolation Forest on the window's
  normal events and scores against red-team labels. Result: **AUC 0.803**
  (CI 0.786–0.819); central finding — **access breadth (unique_pcs) alone AUC
  0.905** beats the full ensemble; login volume is below chance. Paper reframed
  around this: 4 equations, 4-part Related Work, 25 verified references.
  All three papers are now drafted (local in `paper/`).

Citations: all foundational references verified against primary sources this
session (arXiv / ACM DL / IEEE / USENIX / Springer / ACL & IR anthologies).

Corrections (committed):
- **OT/ICS numbers in README + Exhibit 13** reconciled. Finding: the old
  "84.3% recall, 0.61 precision, 95th percentile" are NOT wrong — they are a
  valid *random train/test split* result (confirmed from the classification-report
  images: recall 15433/18303=0.843, precision 15433/25204=0.612). They differ
  from the canonical test-file eval (AUC 0.929, ~20% FPR) due to cross-session
  distribution shift. README now presents BOTH protocols and leads with AUC 0.929;
  Exhibit 13 gained a §4.3 rigorous re-evaluation and clarified captions.
- `train2.csv` actually contains 776 attack rows (so the 18,303 total = 776 +
  11,538 + 5,989); canonical test = test1+test2 = 17,527 attacks.

Papers finalized (local `paper/`; see `paper/README.md` for the full runbook):
- **eTaPR** computed for OT/ICS via `faster-eTaPR` (compute_etapr.py, with a documented
  sklearn compat shim): eTaPR-F1 ~0.32 (test1) / 0.61 (test2) at the 99th-pct
  threshold — below the HAICon leaderboard (0.84–0.94 on HAI 21.03), as expected
  for a plain autoencoder; added to the paper with honest caveats.
- **references.bib** synced to the full verified reference lists for all three papers
  (generator: scratchpad/generate_bib.py; 29 / 25 / 25 entries).
- **LaTeX / arXiv**: `paper.tex` generated per paper (arXiv-ready `article` class,
  native math, booktabs tables, figures, `\citep` against references.bib; generator
  scratchpad/build_latex.py). Verified 0 double-escape artifacts and every `\citep`
  key resolves in the bib. Compile on Overleaf/arXiv (no local TeX toolchain here).
- **Venue variants**: `paper_{cs,cset,ieee,mdpi}.docx` for each paper via the
  build_paper.py venue flag (title-page label; swap the LaTeX documentclass for a
  venue's real template).

Reproducible notebooks (tracked, on GitHub, with metrics + figures embedded):
- `notebooks/05_ot_ics_paper_evaluation.ipynb`
- `notebooks/06_regmap_paper_evaluation.ipynb`
- `notebooks/07_identity_redteam_evaluation.ipynb`

Identity red-team result (notebook 07): context-aware Isolation Forest **AUC 0.803**
(95% CI 0.786–0.819) on 48 real red-team logins; notable honest finding — the
single feature `unique_pcs` (distinct machines per account) alone scores **AUC
0.905**, out-performing the full model, because lateral movement is strongly
signalled by access breadth. The Identity paper is being reframed around this.

Reproduce a paper's numbers: run the corresponding notebook (05/06/07), or
`python paper/<name>/eval_*.py` then `python paper/<name>/build_paper.py`.

## 2026-07-04

**Live test environment for Identity Anomaly and OT/ICS, end to end.**

- Diagnosed and fixed a bug in `live-target-lab/identity_generator.py`: its
  "suspicious" auth types (`"?"`, `"MICROSOFT_AUTHENTICATION_PACKAGE_V1_0"`)
  were actually common, known values in the training data, so they barely
  moved the anomaly score. Confirmed via direct curl testing against the live
  API that only genuinely unrecognized auth strings (which map to the
  model's unseen/unknown code) trigger a real alert. Replaced them with
  `TotallyUnrecognizedAuth`, `LegacyProtocolXYZ`, `UnverifiedCustomAuth`.
- Rebuilt and restarted `identity-event-source`; verified live via a
  streaming log monitor that injected-suspicious events now score
  `ALERT`/negative, matching the behavior already confirmed for
  `ics-event-source` (attack ticks scoring reconstruction error 9-136+
  against a 0.009223 threshold, normal ticks staying under 0.005).
- Initialized git, committed, and pushed `live-target-lab` to its own new
  repo: https://github.com/samuelgtetteh/live-target-lab (kept separate
  from `cloud-target-lab` — different purpose, confirmed with the user
  rather than merging them).
- Wrote [`docs/system_landscape.md`](system_landscape.md): a map of how the
  4 repos (this one, `cloud-target-lab`, `live-target-lab`, the exhibit
  docs) and their containers fit together, the runtime port/wiring diagram,
  why the event sources synthesize instead of replay, both generator bugs
  found and fixed (ICS noise scaling, identity auth-type vocabulary) so they
  aren't rediscovered from scratch later, and a "when something looks
  broken, check in this order" section.
- Found a stale duplicate backend container (`angry_clarke`, image
  `regmap-api`, port 8001) left running from an earlier manual test,
  separate from the one everything actually points at (`RedMap`, port
  2500). Documented it as a known quirk rather than deleting it outright.
- Worked through PowerShell-specific testing gotchas (bash-style `\` line
  continuation and `-H`/`-d` flags don't work the same way in PowerShell)
  and documented working `curl.exe` one-liners and native
  `Invoke-RestMethod` equivalents for hitting `/identity/score` and
  `/ics/score` manually.
- Built log tooling under `docs/logs/` (gitignored output, tracked scripts):
  - `snapshot_logs.ps1` — one-time dump of each container's full log
    history into a timestamped folder.
  - `start_live_logging.ps1` — continuously tails all 4 containers into
    separate per-container files in real time, for as long as it runs.

**Open items for next session:**
- `angry_clarke` (stale duplicate `regmap-api` container on port 8001) is
  still running — stop it if it's confirmed unused, to stop confusing
  `docker ps` output.
- `control-advisor/scanner/cloud_scan.py` (cloud/IaC scan against
  `cloud-target-lab`) is still standalone-only — not wired into
  `cli.py`'s interactive menu.
- The compound-negation misclassification in the Control Advisor interview
  LLM flow (e.g. "no, anyone can open them" read as "yes") is a known,
  unresolved limitation — revisit if it keeps recurring.
- Two leftover files from an earlier, since-abandoned approach are sitting
  untracked in the working tree and were deliberately left out of today's
  commit: `backend/ics_event_simulator.py` and
  `backend/identity_event_simulator.py` (one-shot CSV-replay simulators,
  superseded by `live-target-lab`'s synthesize-based generators). Also
  `nb03_temp.json` at the repo root looks like a stray scratch file from
  earlier notebook work. None of the three are referenced by anything
  currently in use — worth deleting once confirmed safe, rather than
  carrying them forward indefinitely.
