# System Landscape

How the pieces of this project fit together across repos and containers. Written
as a map to re-orient quickly after time away — not a design doc, so update it
whenever a piece moves rather than treating it as historical record.

## The four repos

| Repo | Location | Purpose |
|---|---|---|
| `ai-cybersecurity-portfolio` | this repo | The three ML projects (RegMap, Identity Anomaly, OT/ICS), the FastAPI backend that serves all three live, and Control Advisor (NIST 800-53 tool). |
| [`cloud-target-lab`](https://github.com/samuelgtetteh/cloud-target-lab) | `C:\Users\User\cloud-target-lab` | LocalStack-simulated AWS account. Stands in for a real cloud account so Control Advisor's cloud/IaC scan phase has something to scan. |
| [`live-target-lab`](https://github.com/samuelgtetteh/live-target-lab) | `C:\Users\User\live-target-lab` | Two standing services that synthesize login events and OT sensor telemetry and stream them to the live backend, so Identity Anomaly and OT/ICS can be watched against a continuous live-like source instead of a static test set. |
| `Project Include in document.docx` + `exhibits/` | this repo, `exhibits/` | The NIW petition exhibit documents. Numbers/claims in here must match whatever the notebooks and README currently say — they don't auto-update. |

Only the main repo is where the "real" project lives; the other two exist purely
to give the live backend something realistic to react to, since there's no
production deployment or real cloud account behind any of this.

## Runtime container map

```
                         ┌─────────────────────────────┐
                         │   backend (this repo)        │
                         │   image: regmap-api           │
                         │   container: RedMap            │
                         │   host port 2500 -> 8000        │
                         │                                  │
                         │   /regmap/*     (RegMap)          │
                         │   /identity/score (Identity Anomaly)
                         │   /ics/score      (OT/ICS)          │
                         └───────────▲──────────────▲──────────┘
                                     │              │
                     host.docker.internal:2500      │
                                     │              │
        ┌────────────────────────────┘              └───────────────────────┐
        │                                                                    │
┌───────┴────────────┐                                          ┌───────────┴─────────┐
│ identity-event-source│                                          │ ics-event-source    │
│ (live-target-lab)     │                                          │ (live-target-lab)    │
│ POSTs synthetic logins │                                          │ POSTs synthetic sensor│
│ every 3s, ~15% suspicious                                         │ readings every 3s,    │
└────────────────────────┘                                          │ ~15% attack spikes    │
                                                                     └───────────────────────┘

┌──────────────────────────────┐
│ cloud-target-lab               │
│ image: localstack/localstack:3.0│
│ host port 4566                  │
│ simulated S3 / EC2 / IAM          │
└───────────▲──────────────────────┘
             │
   control-advisor/scanner/cloud_scan.py
   --endpoint-url http://localhost:4566
   (run manually, not a standing container)
```

**Important quirk:** as of 2026-07-04 there were *two* `regmap-api` containers
running at once — `RedMap` (port 2500, the one everything above actually
points at) and an older orphaned one named `angry_clarke` (port 8001, stale
from an earlier manual test run). `angry_clarke` isn't wired into anything;
if backend behavior looks wrong, check `docker ps` and make sure you're
editing/rebuilding the image that `RedMap` is actually running, and consider
stopping `angry_clarke` to avoid confusing future-you.

## Backend endpoints (`backend/app.py`, in this repo)

- `app.include_router(identity_router)` → `backend/identity_api.py` → `POST /identity/score`
- `app.include_router(ics_router)` → `backend/ics_api.py` → `POST /ics/score`
- RegMap's own routes (compliance mapping)
- `/` redirects to `/docs` (Swagger UI) — this is the fastest way to manually poke any endpoint

Both `identity_api.py` and `ics_api.py` load their trained model artifacts from
`data/processed/` at startup (`autoencoder_hai.pth`, `scaler_hai.pkl`,
`autoencoder_hai_meta.txt` for ICS; feature/code mappings hardcoded for
Identity). If you retrain either model, the backend container needs a rebuild
to pick up new artifacts — it doesn't hot-reload them.

## Why live-target-lab synthesizes instead of replays

Explicit decision: rather than replaying rows from the original historical
CSVs (LANL auth log / HAI dataset) into the API, `live-target-lab` generates
**new** synthetic events each tick — normal traffic is real recorded baselines
perturbed with realistic per-feature noise (drawn from the actual trained
`scaler_hai.pkl` std devs for ICS; from the real category vocabulary for
Identity), and "attack"/"suspicious" events are constructed to genuinely look
anomalous to the model rather than just being labeled that way.

Two bugs already found and fixed here, worth remembering if new
"suspicious"/"attack" categories are ever added:

1. **ICS**: don't scale synthetic noise as a percentage of a sensor's raw
   value — some sensors have a huge raw magnitude but tiny real variance
   (`P4_ST_TT01`: baseline ~27,627, real std dev only ~31). Always derive
   noise from the sensor's actual trained std dev in `scaler_hai.pkl`, not
   from the reading's magnitude.
2. **Identity**: not every "weird-sounding" auth type is actually rare in the
   training data — `"?"` and `"MICROSOFT_AUTHENTICATION_PACKAGE_V1_0"` are
   both common, known values (mapped codes), so using them as "suspicious"
   barely moves the anomaly score. Only strings genuinely absent from
   `AUTH_TYPE_CODES` map to the unseen/unknown code the model actually
   reacts to. When in doubt, curl the endpoint directly and check the score
   before assuming a synthetic value "looks suspicious."

## Control Advisor (`control-advisor/` in this repo)

Standalone CLI tool (`control-advisor/cli.py`), not part of the FastAPI
backend. Run manually. Two things it can scan:

- **Local/WAN network** (`scanner/network_scan.py`) — always available, no
  external dependency.
- **Cloud/IaC** (`scanner/cloud_scan.py`) — needs an endpoint to hit. Point it
  at `cloud-target-lab` (`--endpoint-url http://localhost:4566`) for a
  simulated AWS account, or omit `--endpoint-url` to use boto3's normal
  credential chain against a real AWS account. Not currently wired into
  `cli.py`'s interactive menu — runs as a standalone script only.

The interview step (`interview.py` + `llm_interview.py`) runs a small local
LLM (Qwen2.5-1.5B-Instruct) to interpret free-text answers, with a
deterministic `GLOSSARY` + `seems_confused()` fallback for terms the LLM
can't reliably explain on its own — that fallback is intentional, not a
stopgap; more LLM prompting was tried first and didn't hold up.

## When something looks broken, check in this order

1. `docker ps` — is the container you think is serving traffic actually the
   one running (watch for stale duplicates like `angry_clarke`)?
2. `docker logs <container> --tail 30` — for the event sources, compare the
   `(injected normal/suspicious)` tag against the `OK`/`ALERT` the model
   actually returned. A mismatch means either the generator's synthetic data
   doesn't actually resemble what it claims, or the model/threshold changed
   underneath it.
3. Curl the endpoint directly with a hand-built payload — fastest way to
   isolate "is this a generator problem or a model problem."

## Logs

The backend has no application-level logging of its own (no `logging`/
`logger` calls anywhere in `backend/`) — every request that hits it (whether
from a manual curl/`Invoke-RestMethod` test, Swagger UI, or one of the
event-source containers) only shows up via uvicorn's default access log,
which goes to stdout. That means **all logging is just "whatever each
container prints to stdout,"** captured automatically by Docker's default
`json-file` driver:

```powershell
docker logs RedMap                  # backend: every request, any endpoint
docker logs identity-event-source   # synthetic identity events + OK/ALERT
docker logs ics-event-source        # synthetic sensor readings + OK/ALERT
docker logs cloud-target-lab        # LocalStack (simulated AWS) activity
```

`-f` to follow live, `--tail N` to limit, `--since 10m` to window by time.
Manual ad-hoc tests (curl, `Invoke-RestMethod`, Swagger UI) print only to
your own terminal and aren't captured anywhere else — redirect them yourself
(`... | Tee-Object -FilePath test.log`) if you want a record.

The underlying log files exist inside Docker Desktop's hidden WSL2 VM (e.g.
`/var/lib/docker/containers/<id>/<id>-json.log`), not as a normal `C:\` path
— always go through `docker logs` rather than hunting for the file directly.

Since `identity-event-source`, `ics-event-source`, and `cloud-target-lab` all
run indefinitely (`restart: unless-stopped`) with no log rotation configured,
their `json-file` logs grow unbounded over time. Not urgent, but if disk
usage ever becomes a problem, add `max-size`/`max-file` logging options to
the relevant `docker-compose.yml`.
