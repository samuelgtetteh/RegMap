# Phase 2 — Real-Time Decisioning: Detailed Build Plan

Turns live *detection* into live *response*, realizing Exhibit 14 §9.
**Locked design decisions:** Hybrid architecture · TimescaleDB/Postgres single
store · Grafana dashboard. Planning document — not yet implemented.

## Final architecture
```
live-target-lab ──events──► RedMap ──writes verdict row──► TimescaleDB (Postgres)
   (identity, ics)          (scores)                          │            │
                                              decision-service │            │ Grafana
                                              (reads new verdicts,          (Postgres datasource:
                                               applies rules) ──writes──► alerts   rate graphs +
                                                     │                              live alert table)
                                          alert log + webhook
```
RedMap stays a scorer that also **records** each verdict. A separate
**decision-service** reads new verdicts, applies rules, and fires alerts.
**Grafana** reads the store and shows it live.

## Component / repo layout (proposed)
New folder in the **main repo** (core product, not a test lab) — suggested `realtime/`:
- `realtime/docker-compose.yml` — brings up **db** (timescaledb), **redmap** (built from `../backend`), **decision-service**, **grafana** on one network.
- `realtime/db/init.sql` — schema, auto-applied on first DB boot.
- `realtime/decision_service/` — consumer app + `Dockerfile`.
- `realtime/rules.yaml` — decision rules (edit without code changes).
- `realtime/grafana/provisioning/` — datasource + dashboard JSON (auto-provisioned).
- `realtime/.env` — DB creds, webhook URL (gitignored, like cloud-target-lab).
- `realtime/README.md`.
- **Backend change:** `backend/verdict_store.py`; `identity_api`/`ics_api` write a verdict row after scoring; new `DATABASE_URL` env. Writes are **best-effort** (try/except + log) so a DB hiccup never breaks scoring.

## 2a — Record
- Stand up **TimescaleDB** (`timescale/timescaledb`); `init.sql` creates:
  - `verdicts` hypertable: `ts, model, is_anomaly, score, threshold, entity, detail(jsonb)`.
  - `alerts` table: `ts, rule, model, entity, severity, window_count, delivered, payload(jsonb)`.
- RedMap writes one `verdicts` row per scored event (identity → entity=src_user; ics → entity=sensor/na).
- **Done when:** `SELECT count(*) FROM verdicts` grows as the event sources run.

## 2b — Decide
- **decision-service** polls new verdicts (~1–2 s cursor; optional LISTEN/NOTIFY later) and applies `rules.yaml`:
  - any `is_anomaly` → candidate alert;
  - **stateful:** ≥ N anomalies from one entity within window M → escalate severity;
  - per-model tuning (e.g., ICS error beyond X → critical);
  - **dedup/cooldown** so one burst = one alert.
- Writes `alerts` rows.
- **Done when:** injected burst → one escalated alert row; normal traffic → none.

## 2c — Act
- On each alert: structured **alert log** line (stdout) + **webhook** POST (graceful failure, mark `delivered`).
- Optional **simulated autonomous response** — log "would disable account X / isolate host Y" to demonstrate the closed loop without doing anything real.
- **Done when:** an alert shows in decision-service logs and arrives at the webhook sink.

## 2d — See (Grafana)
- Grafana with **provisioned** Postgres datasource + "Real-Time Threat Detection" dashboard (auto-refresh 5 s):
  - time series: events/min and anomalies/min per model;
  - stat tiles: total events, total anomalies, alerts fired;
  - **live recent-alerts table** (ts, model, entity, rule, severity) — the compelling visual;
  - recent anomalous verdicts; top-N flagged entities.
- **Done when:** start event sources → dashboard shows anomalies and alerts appearing live.

## Honesty caveat (for the exhibit)
RedMap never receives the "injected" label (only the generator knows it), so
**Grafana shows operational activity — anomaly rates, alerts fired — not
recall/precision.** Detection *accuracy* stays measured by the labelled tally
(Exhibit 14). Grafana proves the system *operates and responds live*; the tally
proves it is *accurate*. Keep those two claims separate.

## Evidence → Exhibit 15
Screenshots of the live Grafana dashboard, the decision-service firing an alert,
the webhook sink receiving it, and DB row growth → a new **Exhibit 15:
Operational Response / Real-Time Decisioning**.

## Sequence & effort
2a → 2b → 2c → 2d, each independently testable. Rough: 2a M · 2b M · 2c S · 2d M.

## Assumed defaults (change on request)
- Location: `realtime/` in the main repo (not a separate repo).
- Demo webhook target: a throwaway sink (e.g., webhook.site) unless a real Slack/Discord channel is preferred.
- Include the simulated auto-response action (logged only): yes.

## Prerequisites
- Phase 0 baseline (commit current work) recommended first.
- Build order when started: begin with **2a (Record)** — smallest, lowest-risk slice.
