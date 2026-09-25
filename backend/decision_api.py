"""
Decision-layer API (Track C).

Phase C1 exposes the recorded verdict trail; the logging/feedback extension adds a
complete request audit, a ground-truth feedback channel, and live detection metrics.
Later phases (Decide/Act) add /decision/alerts and action endpoints on this router.

Endpoints read/write the durable trail in verdict_store — the authoritative real-time
record the stateless scorer lacked (Exhibit 14 section 3). Ground truth is decoupled
from scoring: any live client (analyst UI, SOAR, ticket-resolution webhook, or a test
event source) attaches the true label to a specific decision via /verdicts/{id}/feedback,
using the X-Verdict-Id the backend returns on every scored response.
"""
import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import actions
import ai_triage
import policy
import settings as app_settings
from verdict_store import (add_suppression, close_alert, enforce_retention, get_alert,
                           label_alert_verdicts, max_verdict_id, metrics, query_actions,
                           query_alert_events, query_alerts, query_requests, query_suppressions,
                           query_verdicts, record_alert_event, remove_suppression,
                           set_disposition, set_ground_truth, stats, subject_outcome_history,
                           update_alert, verdicts_by_ids, verdicts_since)

# analyst resolution -> the ground-truth label fed back to the alert's contributing verdicts
_RESOLUTION_FEEDBACK = {"true_positive": "malicious", "false_positive": "benign",
                        "benign": "benign", "malicious": "malicious"}

router = APIRouter(prefix="/decision", tags=["decision"])


def _overview() -> dict:
    """One aggregated snapshot for the live dashboard: system stats, per-model metrics, the open
    alert queue (priority-sorted), the most recent verdicts, and recent responder actions."""
    # Active queue = open + acknowledged (in-progress); closed/resolved drop off.
    active = [a for a in query_alerts(status=None, limit=200)
              if a.get("status") in ("open", "acknowledged")][:25]
    return {
        "stats": stats(),
        "metrics": {"all": metrics(), "identity": metrics("identity"), "ics": metrics("ics")},
        "alerts": active,
        "recent_verdicts": query_verdicts(limit=25),
        "actions": query_actions(limit=15),
    }


@router.get("/verdicts")
def get_verdicts(
    model: Optional[str] = Query(None, description="identity | ics | regmap"),
    subject: Optional[str] = Query(None, description="e.g. a source user"),
    flagged: Optional[bool] = Query(None, description="filter to anomalies only"),
    labeled: Optional[bool] = Query(None, description="filter to verdicts with ground truth"),
    limit: int = Query(100, ge=1, le=1000),
):
    """Most-recent-first slice of the recorded verdict trail (incl. request metadata
    and any attached ground truth)."""
    return query_verdicts(model=model, subject=subject, flagged=flagged,
                          labeled=labeled, limit=limit)


@router.get("/requests")
def get_requests(limit: int = Query(100, ge=1, le=1000)):
    """Audit of non-scored requests (health checks, errors, validation failures)."""
    return query_requests(limit=limit)


@router.get("/stats")
def get_stats():
    """Coverage totals: verdicts, flagged, labelled, audited requests, per model, + retention caps."""
    return stats()


@router.get("/settings")
def get_settings():
    """The user-editable operational limits/thresholds (grouped, with type/range/help and current
    values) plus the flat effective map. Powers the dashboard settings panel (BC.1)."""
    return {"groups": app_settings.describe(), "values": app_settings.effective()}


class SettingsUpdate(BaseModel):
    values: dict  # {SETTING_KEY: value} — validated against the registry (type + range)


@router.patch("/settings")
def patch_settings(body: SettingsUpdate):
    """Persist one or more setting overrides; takes effect on the next verdict/evaluate (no
    restart). Rejects unknown keys or out-of-range values (nothing is written if any is invalid)."""
    try:
        eff = app_settings.update(body.values)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"updated": sorted(body.values), "values": eff}


class SettingsReset(BaseModel):
    keys: Optional[list] = None  # None = reset everything to defaults


@router.post("/settings/reset")
def reset_settings_endpoint(body: SettingsReset = SettingsReset()):
    """Revert overrides to their coded/env defaults (all keys, or a named subset)."""
    try:
        eff = app_settings.reset(body.keys)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"reset": body.keys or "all", "values": eff}


@router.post("/retention/enforce")
def retention_enforce():
    """Immediately trim the log tables to their FIFO caps (oldest evicted). Trimming also happens
    automatically on insert (batched) and at startup; this is a manual/on-demand trigger."""
    return enforce_retention()


@router.get("/metrics")
def get_metrics(model: Optional[str] = Query(None, description="identity | ics | regmap")):
    """Live confusion matrix + precision/recall/specificity over labelled verdicts."""
    return metrics(model=model)


class Feedback(BaseModel):
    ground_truth: str  # 'malicious' | 'benign' (synonyms accepted)


@router.post("/verdicts/{verdict_id}/feedback")
def submit_feedback(verdict_id: int, feedback: Feedback):
    """Attach the true label to a recorded verdict — the feedback loop that lets the
    decision layer measure and improve its decisions. verdict_id is the value returned
    in the X-Verdict-Id response header of the original scored request."""
    try:
        updated = set_ground_truth(verdict_id, feedback.ground_truth)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if not updated:
        raise HTTPException(status_code=404, detail=f"no verdict with id {verdict_id}")
    return {"verdict_id": verdict_id, "ground_truth": feedback.ground_truth, "recorded": True}


@router.get("/alerts")
def get_alerts(
    status: Optional[str] = Query("open", description="open | closed (null for all)"),
    model: Optional[str] = Query(None, description="identity | ics | regmap"),
    auto_evaluate: bool = Query(True, description="run the policy rules before returning"),
    limit: int = Query(100, ge=1, le=1000),
):
    """Derived decisions (Decide layer). By default runs the policy rules over the current
    window first, so the result reflects the live trail. Pass status= (omit for all)."""
    if auto_evaluate:
        policy.evaluate()
    return query_alerts(status=None if status in (None, "", "all") else status,
                        model=model, limit=limit)


@router.post("/evaluate")
def run_evaluate():
    """Explicitly run the policy rules over the current window; returns any new alert ids."""
    created = policy.evaluate()
    return {"created_alert_ids": created, "count": len(created)}


@router.get("/actions")
def get_actions(
    alert_id: Optional[int] = Query(None, description="filter to one alert's actions"),
    limit: int = Query(100, ge=1, le=1000),
):
    """Audit of responses the Act layer took (log / ticket / webhook) per alert."""
    return query_actions(alert_id=alert_id, limit=limit)


@router.post("/alerts/{alert_id}/close")
def close(alert_id: int):
    """Analyst resolution: mark an alert closed (removes it from the open queue)."""
    if not close_alert(alert_id):
        raise HTTPException(status_code=404, detail=f"no alert with id {alert_id}")
    return {"alert_id": alert_id, "status": "closed"}


@router.get("/alerts/{alert_id}")
def alert_detail(alert_id: int):
    """Full case view for one alert: the alert itself, the contributing verdicts (evidence),
    the subject's ground-truth outcome history, the responder actions taken, and the analyst
    audit trail. This is what the console opens when you click an alert."""
    alert = get_alert(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail=f"no alert with id {alert_id}")
    return {
        "alert": alert,
        "evidence": verdicts_by_ids(alert.get("verdict_ids") or []),
        "subject_history": subject_outcome_history(alert.get("subject"), alert.get("model")),
        "actions": query_actions(alert_id=alert_id, limit=100),
        "events": query_alert_events(alert_id),
    }


class Acknowledge(BaseModel):
    actor: Optional[str] = "analyst"
    note: Optional[str] = None


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: int, body: Acknowledge = Acknowledge()):
    """Take ownership: mark the case acknowledged (in-progress) and journal it. Keeps the alert
    in the queue but records that a human is on it."""
    if get_alert(alert_id) is None:
        raise HTTPException(status_code=404, detail=f"no alert with id {alert_id}")
    update_alert(alert_id, status="acknowledged", assignee=body.actor)
    record_alert_event(alert_id, "acknowledge", actor=body.actor, note=body.note)
    return {"alert_id": alert_id, "status": "acknowledged", "assignee": body.actor}


class Assign(BaseModel):
    assignee: str
    actor: Optional[str] = "analyst"


@router.post("/alerts/{alert_id}/assign")
def assign_alert(alert_id: int, body: Assign):
    """Assign the case to a named analyst."""
    if get_alert(alert_id) is None:
        raise HTTPException(status_code=404, detail=f"no alert with id {alert_id}")
    update_alert(alert_id, assignee=body.assignee)
    record_alert_event(alert_id, "assign", actor=body.actor,
                       note=f"assigned to {body.assignee}", detail={"assignee": body.assignee})
    return {"alert_id": alert_id, "assignee": body.assignee}


class Note(BaseModel):
    note: str
    actor: Optional[str] = "analyst"


@router.post("/alerts/{alert_id}/note")
def add_note(alert_id: int, body: Note):
    """Append a free-text note to the case history."""
    if get_alert(alert_id) is None:
        raise HTTPException(status_code=404, detail=f"no alert with id {alert_id}")
    eid = record_alert_event(alert_id, "note", actor=body.actor, note=body.note)
    return {"alert_id": alert_id, "event_id": eid}


class Resolve(BaseModel):
    resolution: str = "true_positive"  # true_positive | false_positive | benign
    note: Optional[str] = None
    actor: Optional[str] = "analyst"
    apply_feedback: bool = True        # write ground truth to the contributing verdicts


@router.post("/alerts/{alert_id}/resolve")
def resolve_alert(alert_id: int, body: Resolve):
    """Close a case with a disposition. When apply_feedback is set (default), the resolution is
    written back as ground truth on every contributing verdict — true_positive -> malicious,
    false_positive/benign -> benign — which trains the Decide layer's outcome-weighting. This is
    the loop-closing decision a premium triage console is built around."""
    if get_alert(alert_id) is None:
        raise HTTPException(status_code=404, detail=f"no alert with id {alert_id}")
    resolution = body.resolution.strip().lower()
    if resolution not in _RESOLUTION_FEEDBACK:
        raise HTTPException(status_code=422,
                            detail=f"resolution must be one of {sorted(_RESOLUTION_FEEDBACK)}")
    labeled = 0
    if body.apply_feedback:
        labeled = label_alert_verdicts(alert_id, _RESOLUTION_FEEDBACK[resolution])
    update_alert(alert_id, status="closed", resolution=resolution,
                 resolved_at=datetime.now(timezone.utc).isoformat())
    record_alert_event(alert_id, "resolve", actor=body.actor, note=body.note,
                       detail={"resolution": resolution, "verdicts_labeled": labeled,
                               "feedback_applied": body.apply_feedback})
    return {"alert_id": alert_id, "status": "closed", "resolution": resolution,
            "verdicts_labeled": labeled}


class Suppress(BaseModel):
    window_hours: Optional[float] = 24   # None/0 = indefinite
    reason: Optional[str] = None
    actor: Optional[str] = "analyst"
    any_model: bool = False              # True = mute the subject across all models
    close: bool = True                   # also close the current alert


@router.post("/alerts/{alert_id}/suppress")
def suppress_alert(alert_id: int, body: Suppress):
    """Allowlist the alert's subject (mute future alerts for it) for a window, optionally closing
    the current alert. Use for a confirmed known-good source (e.g. a service account) that keeps
    tripping the rules. The Decide layer consults the allowlist before raising the subject again."""
    alert = get_alert(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail=f"no alert with id {alert_id}")
    subject = alert.get("subject")
    if not subject:
        raise HTTPException(status_code=422, detail="alert has no subject to suppress")
    until = None
    if body.window_hours and body.window_hours > 0:
        until = (datetime.now(timezone.utc) + timedelta(hours=body.window_hours)).isoformat()
    model = None if body.any_model else alert.get("model")
    sup_id = add_suppression(subject, model=model, until=until, reason=body.reason,
                             actor=body.actor)
    record_alert_event(alert_id, "suppress", actor=body.actor, note=body.reason,
                       detail={"subject": subject, "model": model, "until": until,
                               "suppression_id": sup_id})
    if body.close:
        update_alert(alert_id, status="closed", resolution="suppressed",
                     resolved_at=datetime.now(timezone.utc).isoformat())
    return {"alert_id": alert_id, "suppression_id": sup_id, "subject": subject,
            "model": model, "until": until, "closed": body.close}


class ManualAction(BaseModel):
    action: str                          # log | ticket | webhook | disable_account | step_up_auth
    actor: Optional[str] = "analyst"


@router.post("/alerts/{alert_id}/act")
def take_action(alert_id: int, body: ManualAction):
    """Fire one responder on demand (analyst-triggered). Posture-changing actions
    (disable_account / step_up_auth) are recorded stubs — no live side effect — so the console is
    powerful without becoming an attack surface. See actions.MANUAL_ACTIONS for the menu."""
    alert = get_alert(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail=f"no alert with id {alert_id}")
    if body.action not in actions.MANUAL_ACTIONS:
        raise HTTPException(status_code=422,
                            detail=f"action must be one of {actions.MANUAL_ACTIONS}")
    result = actions.manual_action(alert, body.action, actor=body.actor)
    record_alert_event(alert_id, "action", actor=body.actor,
                       note=f"ran {body.action} -> {result['status']}", detail=result)
    return {"alert_id": alert_id, **result}


@router.get("/actions/available")
def available_actions():
    """The manual response menu the console offers (so the UI stays in sync with the backend)."""
    return {"actions": actions.MANUAL_ACTIONS}


# --- suppression / allowlist management ---
@router.get("/suppressions")
def get_suppressions(active_only: bool = Query(True)):
    """Current allowlist entries (muted subjects)."""
    return query_suppressions(active_only=active_only)


@router.delete("/suppressions/{suppression_id}")
def delete_suppression(suppression_id: int):
    """Lift an allowlist entry (the subject can alert again)."""
    if not remove_suppression(suppression_id):
        raise HTTPException(status_code=404, detail=f"no suppression with id {suppression_id}")
    return {"suppression_id": suppression_id, "removed": True}


@router.post("/alerts/{alert_id}/reassess")
def reassess_alert(alert_id: int):
    """LLM-assisted (advisory) re-prioritization of one alert. Stores {priority, disposition,
    rationale}; priority is clamped to the severity floor. Kept out of the scoring/evaluate hot
    path — invoke explicitly (analyst action or a scheduled sweep)."""
    alert = get_alert(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail=f"no alert with id {alert_id}")
    a = ai_triage.assess(alert)
    set_disposition(alert_id, a["priority"], a["disposition"], a["rationale"])
    return {"alert_id": alert_id, **a}


@router.post("/reassess")
def reassess_open(limit: int = Query(50, ge=1, le=500)):
    """Reassess the open-alert queue in bulk (advisory). Returns the new priority/disposition per
    alert. Note: with an in-process LLM this is slow for many alerts; a sidecar LLM makes it cheap."""
    updated = []
    for alert in query_alerts(status="open", limit=limit):
        a = ai_triage.assess(alert)
        set_disposition(alert["id"], a["priority"], a["disposition"], a["rationale"])
        updated.append({"alert_id": alert["id"], "priority": a["priority"],
                        "disposition": a["disposition"], "llm_used": a["llm_used"]})
    return {"reassessed": len(updated), "alerts": updated}


@router.get("/alerts/{alert_id}/triage")
def alert_triage(alert_id: int):
    """AI triage (Track E): a concise analyst summary + the most relevant compliance controls
    for this alert (RAG over the corpus; LLM-written when the local model is available, else a
    templated summary). Heavy models load lazily on first call."""
    alert = get_alert(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail=f"no alert with id {alert_id}")
    return {"alert_id": alert_id, **ai_triage.triage(alert)}


@router.get("/overview")
def get_overview():
    """Aggregated snapshot powering the dashboard (single call; also the SSE payload shape)."""
    return _overview()


@router.get("/stream")
async def stream():
    """Server-Sent Events feed for the live dashboard. Pushes an initial overview, then every
    ~1.5s pushes any new verdicts plus a refreshed overview — one persistent connection, no
    client polling."""
    async def gen():
        last = max_verdict_id()
        yield f"data: {json.dumps({'type': 'init', 'overview': _overview()})}\n\n"
        while True:
            await asyncio.sleep(1.5)
            new = verdicts_since(last, limit=200)
            if new:
                last = new[-1]["id"]
            yield f"data: {json.dumps({'type': 'tick', 'new_verdicts': new, 'overview': _overview()})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/health")
def health():
    return {"status": "ok"}
