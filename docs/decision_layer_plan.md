# Decision Layer → AI Platform — build plan & checkpoint

Implements Track C (real-time Record → Decide → Act decisioning layer) and Track E
(LLM/agentic platform) from `docs/development_roadmap.md`. This is the build the user
chose to start first. It turns the current stateless RedMap scorer into an operational
decisioning system, and becomes the basis for a new **Exhibit 16**. Started 2026-07-11.

## Why this is unblocked now
Per the roadmap dependency analysis, Track C depends only on the existing containerized
system (done) — it needs nothing from the research track. Track E (AI layer) sits on top
of C. Existing assets that make E cheap: the local **Qwen2.5-1.5B-Instruct** model
(`models/qwen2.5-1.5b-instruct`, already used by Control Advisor) and the fine-tuned
**RegMap embedder** (`models/regmap-embedder`) for RAG.

## Current backend (starting point)
`backend/app.py` mounts `/map` (RegMap retrieval) + routers `/identity/score`
(Isolation Forest) and `/ics/score` (autoencoder). Each returns a structured verdict but
**persists nothing** (Exhibit 14 §3: "stateless scorer"). All three verdicts are the raw
material the decision layer records and acts on.

## Architecture (from Exhibit 14 §9: Record → Decide → Act)
- **Record** — every verdict is written to a durable store (append-only trail),
  independent of any test client.
- **Decide** — a policy layer evaluates recorded verdicts against rules (e.g. any anomaly;
  repeated anomalies from one subject within a window; low-confidence compliance mapping).
- **Act** — a decision triggers a response (alert, ticket, webhook, page). Start with
  logged/stubbed actions + a webhook.
- Arrangement: inline first (simplest), with a clean seam to move to a decoupled
  stream-consumer later (the more production-grade pattern noted in Exhibit 14 §9).
- **AI layer (Track E)** — LLM-assisted triage of the anomaly queue (Qwen) + RAG over
  regulatory text (RegMap embedder) to explain/contextualize each decision.

## Phases & progress
- [x] **C1 — Record + production logging/feedback.** (DONE 2026-07-11) `backend/verdict_store.py`
  (stdlib SQLite, thread-safe). Two tables: `verdicts` (model decision + request metadata +
  ground_truth) and `requests` (audit of non-scored traffic). `record_verdict_safe(...)` wired into
  `/identity/score` (subject=src_user), `/ics/score`, `/map` (flag top-1 sim < 0.5); each stashes
  `request.state.verdict_id`.
  - **App middleware** (`app.py`) logs EVERY request: enriches the verdict row with
    latency/status/client/path and returns `X-Verdict-Id` header; audits non-scored requests.
  - **Feedback loop** (production-decoupled): `POST /decision/verdicts/{id}/feedback {ground_truth}`
    (synonyms normalized to malicious/benign) — any live client (analyst/SOAR/ticket/simulator) labels
    a decision by its X-Verdict-Id. `GET /decision/metrics` computes precision/recall/specificity from
    the DB (persists the Exhibit 14 tally). Also `GET /decision/verdicts` (filters incl. labeled),
    `GET /decision/requests`, `GET /decision/stats`.
  - Verified end-to-end via TestClient (header → feedback → metrics → audit; 422 bad label, 404 missing
    id). Reproducible: `notebooks/08_decision_layer_record.ipynb` (executed). `.gitignore` updated to
    exclude `data/*.db*` (runtime trail, not source). DB path via `$VERDICT_DB`, default `data/verdicts.db`.
  - **Live-lab feedback wiring — DONE 2026-07-11** (separate repo `C:\Users\User\live-target-lab`):
    `identity_generator.py` and `ics_generator.py` now read `X-Verdict-Id` from each `/score` response
    and POST their known injected label to `/decision/verdicts/{id}/feedback` (best-effort, `FEEDBACK`
    env toggle; README updated). Verified end-to-end by routing the real generator code through the
    backend TestClient — all verdicts auto-labelled, `/decision/metrics` populated. **Not yet committed/
    pushed in that repo, and the container must be rebuilt (`docker compose up -d --build`) to take
    effect on the running live-lab.**
- [x] **C2 — Decide.** DONE 2026-07-11 (code + verified + committed; live redeploy = C2.6, optional).
  `backend/policy.py` rules engine (identity_burst / ics_sustained / high_severity + outcome
  weighting/suppression); `alerts` table in verdict_store; `GET /decision/alerts` + `POST
  /decision/evaluate`. See the C2 build tracker below.
- [x] **C3 — Act.** DONE 2026-07-11 (code+verified+committed; live redeploy = C3.6). `backend/actions.py`
  pluggable responders (log/ticket/webhook, severity-routed) dispatched inline by `policy.evaluate`;
  every action recorded in an `actions` audit table; `GET /decision/actions` + `POST
  /decision/alerts/{id}/close`. See C3 build tracker below.
- [x] **E — AI platform.** DONE 2026-07-12. `backend/ai_triage.py` + `GET /decision/alerts/{id}/triage`:
  local Qwen LLM triage summary per alert + RAG over the HIPAA corpus (RegMap embedder); lazy, gated,
  best-effort (degrades to RAG + templated summary when the LLM is unavailable, e.g. in-container).
- [ ] **Exhibit 16** — document the running decisioning system with measured evidence,
  mirroring the Exhibit 14 style.

## C2 build tracker (IN PROGRESS — resume anchor)
Started 2026-07-11. Build in small steps; each step's checkbox is flipped the moment it lands,
so a fresh session can resume from the first unchecked box.

**Design.** The Decide layer reads the recorded verdict trail and produces durable *alerts*
(derived decisions) via configurable rules. Persistence lives in `verdict_store.py` (owns the DB);
rule logic lives in a new `backend/policy.py`.

Rules (all windowed on `recorded_at`; window default 300s, overridable by env):
1. **identity_burst** — a single `subject` (src_user) with >= `IDENTITY_BURST_MIN` (default 3)
   flagged identity verdicts within the window → alert. This is the lateral-movement / credential-
   stuffing / access-breadth signal.
2. **ics_sustained** — >= `ICS_SUSTAINED_MIN` (default 3) flagged ics verdicts within the window →
   alert. Mirrors the OT/ICS paper's min-run alarm filtering (sustained events, not single blips).
3. **high_severity** — any single flagged verdict whose score is beyond an extreme threshold
   (`ICS_SEVERE_ERROR` default 1.0 for ics reconstruction error; identity score <= `IDENTITY_SEVERE`
   default -0.1) → immediate alert.
4. **outcome weighting** — severity is adjusted by the subject's historical ground truth: if a
   subject's past flagged verdicts were mostly benign (chronic false positives) downweight/suppress;
   if mostly malicious, escalate. Uses `subject_outcome_history()`.

Alert = {id, created_at, rule, model, subject, severity(low|medium|high), window_seconds,
verdict_count, verdict_ids(JSON), detail(JSON), status(open|closed)}. Dedup: don't open a new alert
if an open alert with the same (rule, subject) exists newer than the window (avoid re-alerting an
ongoing burst). `evaluate(now)` is idempotent and safe to call repeatedly.

**Build checklist (resume from first unchecked):**
- [x] **C2.1** DONE — `verdict_store.py`: `alerts` table + `record_alert`, `query_alerts`,
  `open_alert_exists`, `recent_verdicts`, `subject_outcome_history`. (not yet committed)
- [x] **C2.2** DONE — `backend/policy.py`: env-overridable config; rules identity_burst /
  ics_sustained / high_severity + `_weight_severity` (outcome weighting/suppression); idempotent
  `evaluate(now=None)`. (not yet committed)
- [x] **C2.3** DONE — `backend/decision_api.py`: `GET /decision/alerts` (status/model/auto_evaluate)
  + `POST /decision/evaluate`. (not yet committed)
- [x] **C2.4** DONE — verified via TestClient: identity_burst (guest, n=12), ics_sustained (n=4) +
  one deduped high_severity(ics), idempotent re-evaluate (0 new), and outcome-weighted SUPPRESSION
  (svc@DOM1 burst suppressed by benign history). Dockerfile updated to COPY policy.py.
- [x] **C2.5** DONE — committed + pushed (see git log). 
- [x] **C2.6** DONE — RedMap rebuilt (image with policy.py) + recreated with the persistent volume;
  C2 is LIVE. Confirmed at scale from the running live-lab: 1,167 verdicts all auto-labelled; 5 alerts
  (3 identity_burst for the attacker accounts w/ escalated severity from malicious history,
  ics_sustained, high_severity); live metrics precision 0.992 / recall 0.977 / specificity 0.994.

**RESUME POINTER (C2):** ✅ C2 FULLY DONE + DEPLOYED LIVE (committed `81f3eb2`). Next phase → **C3 (Act)**:
`backend/actions.py` — pluggable responders (log / webhook / ticket stub) dispatched when an alert
fires, with the actions themselves recorded for audit; add `POST /decision/alerts/{id}/close` and an
`actions` table. Then **Phase E (AI)**: Qwen triage summary per alert + RegMap-embedder RAG over
regulations. (These live numbers are strong evidence for the eventual Exhibit 16.)

## C3 build tracker (Act) — IN PROGRESS (resume anchor)
Started 2026-07-11. Build in small steps; flip each checkbox as it lands.

**Design.** When Decide (C2) creates an alert, Act runs one or more *responders* and records each
in a durable `actions` audit table. Responders are pluggable and chosen by severity (routing):
- `log` — always; a structured record of the response (baseline).
- `ticket` — medium/high; creates a ticket stub (recorded; a real deployment calls a tracker).
- `webhook` — high (and only if `ACTION_WEBHOOK_URL` is set); POSTs the alert JSON (stdlib urllib,
  no new dependency), best-effort.
Dispatch is INLINE (policy.evaluate → actions.dispatch for each new alert) — the simplest Record→
Decide→Act chain; Exhibit 14 §9 notes a decoupled stream consumer is the more production-grade
arrangement, and `actions.dispatch(alert)` is the seam where that swap happens. Analysts close an
alert via `POST /decision/alerts/{id}/close`. Everything is best-effort: a responder failure is
recorded as status=failed and never breaks scoring or evaluation.

**Build checklist (resume from first unchecked):**
- [x] **C3.1** DONE — `verdict_store.py`: `actions` table + `record_action`, `query_actions`,
  `get_alert`, `close_alert`. (not committed yet)
- [x] **C3.2** DONE — `backend/actions.py`: log/ticket/webhook responders (stdlib urllib), severity
  ROUTING, best-effort `dispatch(alert)` recording each action.
- [x] **C3.3** DONE — `policy.evaluate` dispatches for each new alert; `GET /decision/actions` +
  `POST /decision/alerts/{id}/close`. Also renamed dedup to `recent_alert_exists` (any status →
  a closed alert stays sticky for the window).
- [x] **C3.4** DONE — verified: burst→high alert→log+ticket fired, webhook skipped (no URL); close
  works and is sticky (no re-fire); missing-id close → 404.
- [x] **C3.5** DONE — committed + pushed (see git log). Dockerfile now COPYs actions.py.
- [x] **C3.6** DONE — RedMap rebuilt with actions.py + recreated on the persistent volume; C3 LIVE.
  Confirmed: evaluate created 5 alerts from the live stream and fired responders for each — log ok,
  ticket ok (SEC-N refs), webhook skipped (unconfigured).

**RESUME POINTER (C3/Track C):** ✅ TRACK C COMPLETE + DEPLOYED LIVE. Full Record→Decide→Act pipeline
running (`9bf7710`). Next → **Phase E (AI platform)** — the final track:
- per-alert **triage summary** via the local Qwen model (`models/qwen2.5-1.5b-instruct`, already used
  by Control Advisor `scanner/llm_interview.py`);
- **RAG** over the regulation corpus using the RegMap embedder (`models/regmap-embedder`) to attach the
  most relevant NIST/HIPAA control/obligation context to each alert;
- likely `backend/ai_triage.py` + `GET /decision/alerts/{id}/triage` (lazy, cached). Keep it optional/
  best-effort (model load is heavy) and env-gated so the core pipeline never depends on it.
Then consider **Exhibit 16** documenting the live decisioning system (the live metrics + alerts +
actions are strong evidence).

## Phase E build tracker (AI platform) — IN PROGRESS (resume anchor)
Started 2026-07-12. The final track: per-alert AI triage grounded by RAG over the compliance corpus.

**Design.** `backend/ai_triage.py` produces, for a given alert, a short analyst triage summary +
the most relevant compliance controls:
- **RAG** — retrieve top-k HIPAA provisions for the alert using the RegMap embedder
  (`models/regmap-embedder`) over the same corpus as `/map` (`data/processed/training_pairs.csv`).
- **LLM summary** — the local Qwen model (`models/qwen2.5-1.5b-instruct`, same loader as Control
  Advisor `scanner/llm_interview.py`: AutoTokenizer/AutoModelForCausalLM, chat template, greedy).
- Everything is **lazy** (heavy models load on first triage call), **gated** (`AI_TRIAGE_ENABLED`,
  `AI_TRIAGE_LLM`), and **best-effort**: if the LLM is disabled/absent, a deterministic templated
  summary + the RAG context is still returned. The core pipeline never imports the heavy models.
- **Container note:** the RedMap image ships `regmap-embedder` + training_pairs.csv (so RAG +
  templated summary work live) but NOT Qwen (~3 GB) — so in the container `llm_used=false` unless we
  choose to add Qwen to the image. Full LLM triage runs locally where the model is present.

**Build checklist:**
- [x] **E.1** DONE — `backend/ai_triage.py`: lazy retriever (RegMap embedder over HIPAA corpus) +
  lazy Qwen + best-effort `triage(alert)` → `{enabled, summary, related_controls, llm_used}`.
- [x] **E.2** DONE — `GET /decision/alerts/{id}/triage`; Dockerfile COPYs ai_triage.py.
- [x] **E.3** DONE — verified: (a) RAG+templated (LLM off) returns 3 relevant HIPAA provisions
  (top: "Unique User Identification") + templated summary; (b) full LLM triage with Qwen produces a
  grounded SOC summary citing the retrieved controls. 
- [x] **E.4** DONE — committed + pushed.

**RESUME POINTER (E):** ✅ PHASE E DONE. Full decisioning platform (Record→Decide→Act + AI triage)
built, verified, committed. Optional: rebuild RedMap so the live container serves /triage (RAG +
templated works in-container now; full LLM needs Qwen added to the image, ~3 GB — a deliberate
choice, deferred). **Next: build Exhibit 16** documenting the live decisioning system as NIW evidence
(coverage/metrics/alerts/actions/triage), mirroring the Exhibit 14 style.

## Phase E2 build tracker — LLM triage prioritization via a sidecar (IN PROGRESS)
Started 2026-07-12. Make the LLM *improve how decisions are handled* (queue ordering), safely.

**Principle:** the LLM is ADVISORY, never authoritative (hallucination + prompt-injection risk — it
reads attacker-controlled fields). It re-ranks/labels; deterministic rules + humans enforce.

**Design:**
- Every alert gets a DETERMINISTIC default priority from severity at creation (high=4, medium=2,
  low=1; scale 1-5), so the queue is ordered instantly with no LLM in the hot path.
- The LLM REFINES priority + disposition (escalate | monitor | likely_false_positive) + rationale
  on demand via `POST /decision/alerts/{id}/reassess` (and batch `POST /decision/reassess`).
  Priority is CLAMPED to a severity floor (high>=3, medium>=2, low>=1) so the model can re-rank but
  never bury a high-severity alert.
- LLM access via `backend/llm_client.py`: call the **sidecar** service (`LLM_SERVICE_URL`) if set,
  else fall back to in-process Qwen (dev). `ai_triage` is refactored to use this one client.
- **Sidecar** (`llm-service/`): its own container hosting Qwen behind `POST /generate`; keeps the API
  image lean and isolates the model. RedMap reaches it via `LLM_SERVICE_URL`.

**Build checklist:**
- [x] **E2.1** DONE — `backend/llm_client.py` (`generate()` → sidecar via `LLM_SERVICE_URL` else
  in-process Qwen; `available()`); `ai_triage` refactored to use it.
- [x] **E2.2** DONE — `ai_triage.assess(alert)` → `{priority, disposition, rationale, llm_used}`
  (RAG context + subject history + LLM JSON, validated + clamped to severity floor).
- [x] **E2.3** DONE — `verdict_store`: alerts priority/disposition/rationale (+migration); default
  priority from severity at creation (high=4/med=2/low=1); `set_disposition`; queue ORDER BY priority.
- [x] **E2.4** DONE — `decision_api`: `POST /decision/alerts/{id}/reassess` + `POST /decision/reassess`.
- [x] **E2.5** DONE — `llm-service/` shared sidecar (app + Dockerfile + requirements + README). Per the
  user's steer, the model is **mounted** (`-v models/qwen2.5-1.5b-instruct:/model`), NOT copied/
  re-downloaded; one instance serves the whole project (backend now; Control Advisor can adopt it).
- [x] **E2.6** DONE — 32-test suite green (LLM off in tests → deterministic); local-LLM reassess
  verified: disposition=escalate, priority clamped to floor, guardrails hold. Dockerfile COPYs
  llm_client.py.

**RESUME POINTER (E2):** ✅ E2 CODE COMPLETE + VERIFIED + committed. **Sidecar deploy DEFERRED by
decision (2026-07-12):** this machine is too constrained to run a heavier model or a resident LLM
sidecar smoothly — measured ~1.3 GB free host RAM, a ~7.6 GB Docker VM cap, 4 CPU cores, and only an
Intel Iris Xe iGPU (no CUDA). So we **keep Qwen2.5-1.5B** and do NOT run the sidecar container for now.
The decision layer runs fine without it: locally `llm_client` loads the model in-process; in the
RedMap container triage/reassess degrade gracefully to RAG + templated summary + deterministic
priority. The `llm-service` image is built and ready.

**To deploy + upgrade on a better machine (recorded recipe):**
- Honest local ceiling on THIS box would have been Qwen2.5-**7B**-Instruct **Q4_K_M** GGUF (~4.7 GB,
  Apache-2.0) via a llama.cpp sidecar; 14B-Q4 only with a real GPU / more RAM. See [[llm-upgrade-path]].
1. Download the GGUF into `models/` (e.g. `models/qwen2.5-7b-instruct-gguf/`).
2. Switch `llm-service` to a llama.cpp engine (llama-cpp-python) pointed at the GGUF (backend unchanged).
3. `docker build -t llm-service llm-service`; run it with the model mounted on port 2600.
4. Recreate RedMap adding `-e LLM_SERVICE_URL=http://host.docker.internal:2600` (+ the VERDICT_DB volume).
5. Point Control Advisor at the same sidecar too (one model, many consumers).

## Design decisions
- SQLite via stdlib (no new heavy dep); path from env `VERDICT_DB`, default
  `data/verdicts.db`. A production note (Redis/Postgres, decoupled stream) is documented,
  not implemented — same honest-scope framing as the rest of the portfolio.
- Recording must not change scoring behaviour or break the live-validation tests
  (Exhibit 14): it is additive and side-effecting only.

## Deployment (2026-07-11)
C1 is DEPLOYED and running live, not just verified in tests:
- Portfolio committed/pushed (`76d5091` decision layer, `d2b7bad` Dockerfile+dockerignore fix);
  live-target-lab committed/pushed (`7166802`).
- Dockerfile now copies `verdict_store.py` + `decision_api.py`; `.dockerignore` excludes
  `data/raw/` + `data/*.db`. Backend image `regmap-api` rebuilt (8.83 GB).
- `RedMap` recreated from the new image with a **persistent trail volume**:
  `docker run -d --name RedMap -p 2500:8000 -e VERDICT_DB=/verdicts/verdicts.db -v redmap_verdicts:/verdicts regmap-api`
  (use `MSYS_NO_PATHCONV=1` from git-bash or the leading `/verdicts` gets mangled). db_path
  confirmed `/verdicts/verdicts.db` on volume `redmap_verdicts`.
- Live-lab containers rebuilt (`docker compose up -d --build`); they now stream events AND
  auto-label the trail via feedback. Confirmed live: `/decision/stats`, `/decision/metrics`
  populating from real streamed events (all verdicts labelled).

## Resume pointer
**Last done:** C1 (Record) + production logging/feedback loop complete, verified, AND deployed live
(2026-07-11); notebook 08 executed; both repos pushed; RedMap + live-lab running the new code with a
persistent verdict volume. Backend logs every request, returns X-Verdict-Id, accepts ground-truth
feedback, computes live precision/recall from the DB.
SWaT dataset verified & acquired (106 MB zip, `data/raw/SWaT Dataset Secure Water Treatment
System.zip`; normal/attack/merged CSVs, 51 tags + Normal/Attack label; official iTrust
request also submitted for citable provenance).
**Next:** implement **C2 (Decide)** — `backend/policy.py` with per-subject windowed rules over
the recorded trail (start: N flagged identity verdicts from one subject within a window →
a derived alert), plus `GET /decision/alerts`. Then C3 (Act), then E (AI layer: Qwen triage +
RegMap-embedder RAG). Notebooks as needed per phase. Related: [[development-roadmap-status]].

---

## AQ — Analyst case-management workflow (Tier 1+2) — DONE 2026-07-12
Built the human-in-the-loop layer on the alert queue, all driven from the browser console.
- Store: alert lifecycle (assignee/resolution/resolved_at; status open|acknowledged|closed),
  `alert_events` (audit trail), `suppressions` (allowlist); fns verdicts_by_ids,
  update_alert, record/query_alert_events, label_alert_verdicts, add/query/remove/is_suppressed.
- Policy honours the allowlist (is_suppressed) before raising a subject.
- actions: manual_action + safe stubs disable_account / step_up_auth; MANUAL_ACTIONS.
- API: GET /decision/alerts/{id} (detail), POST /acknowledge /assign /note /resolve /suppress
  /act, GET /actions/available, GET+DELETE /suppressions. Overview keeps acknowledged visible.
- Dashboard: case drawer (evidence + toolbar + triage + subject history + audit trail).
- Feedback loop: resolve TP→malicious / FP→benign labels the alert's verdicts → trains
  outcome-weighting. LLM advisory-only; posture actions are recorded stubs (no attack surface).
- Tests: 17 pass. Exhibit 17 built. DEPLOYED: RedMap rebuilt + recreated (image in sync).

**Next (bookmarked, NOT started):** `docs/browser_control_plan.md` — settings menu for the
hard-coded limits + run compliance audit/scanner from the browser + full browser control plane.
Deferred to a fresh session (usage-limit checkpoint). Related: [[browser-control-plan]].
