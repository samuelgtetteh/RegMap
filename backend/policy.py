"""
Decide layer (Track C, Phase C2): a policy/rules engine over the recorded verdict trail.

The Record layer (C1) captures every verdict; this layer reads a trailing window of that
trail and produces durable *alerts* — the derived decisions the Act layer (C3) will respond
to. Rules are deliberately simple and configurable (env-overridable), and crucially they can
weight decisions by each subject's HISTORICAL ground-truth outcomes (the feedback loop from
C1): a subject whose flagged verdicts have consistently turned out benign is a chronic false
positive and gets suppressed; one with confirmed-malicious history gets escalated. That is the
concrete payoff of persisting verdicts + feedback rather than reacting to raw scores.

Rules (all windowed on recorded_at):
  1. identity_burst  — >= IDENTITY_BURST_MIN flagged identity verdicts from one subject in the
     window (lateral-movement / credential-stuffing / access-breadth signal).
  2. ics_sustained   — >= ICS_SUSTAINED_MIN flagged ICS verdicts in the window (sustained event,
     mirroring the OT/ICS paper's min-run alarm filtering — not a single blip).
  3. high_severity   — a single verdict with an extreme score.

evaluate() is idempotent: an open alert for the same (rule, subject) within the window blocks a
duplicate, so it is safe to call on every /decision/alerts read or after every verdict.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

import actions
import settings
from verdict_store import (get_alert, is_suppressed, recent_alert_exists, record_alert,
                           recent_verdicts, subject_outcome_history)

# Thresholds are read LIVE from the settings store (settings.get) at evaluate() time, so a user
# can retune the policy from the dashboard without a restart (BC.1). Defaults live in the registry.


def _weight_severity(base: str, subject: Optional[str], model: str) -> Optional[str]:
    """Adjust a base severity by the subject's historical outcomes. Returns None to SUPPRESS
    (chronic false positive), or an escalated/de-escalated severity string."""
    suppress_min = settings.get("DECISION_SUPPRESS_MIN")
    h = subject_outcome_history(subject, model)
    mal, ben = h["malicious"], h["benign"]
    total = mal + ben
    if total >= suppress_min and mal == 0 and ben > 0:
        return None                       # consistently benign in the past -> suppress
    if mal > ben and mal > 0:
        return "high"                     # confirmed-bad history -> escalate
    if total >= suppress_min and ben > mal:
        return "low"                      # mostly benign -> de-escalate
    return base


def evaluate(now: Optional[datetime] = None) -> list[int]:
    """Scan the trailing window, apply the rules, dedup against open alerts, and persist any
    new alerts. Returns the ids of alerts created on this call."""
    window_seconds = settings.get("DECISION_WINDOW_SECONDS")
    identity_burst_min = settings.get("IDENTITY_BURST_MIN")
    ics_sustained_min = settings.get("ICS_SUSTAINED_MIN")
    ics_severe_error = settings.get("ICS_SEVERE_ERROR")
    identity_severe = settings.get("IDENTITY_SEVERE")
    now = now or datetime.now(timezone.utc)
    since = (now - timedelta(seconds=window_seconds)).isoformat()
    flagged = recent_verdicts(since, flagged_only=True)
    created: list[int] = []

    # rule 1: identity_burst — group flagged identity verdicts by subject
    by_subject: dict = defaultdict(list)
    for v in flagged:
        if v["model"] == "identity" and v["subject"]:
            by_subject[v["subject"]].append(v)
    for subject, vs in by_subject.items():
        if len(vs) < identity_burst_min:
            continue
        if is_suppressed(subject, "identity"):
            continue  # analyst-allowlisted subject (e.g. a known-good service account)
        if recent_alert_exists("identity_burst", subject, since):
            continue
        severity = _weight_severity("high", subject, "identity")
        if severity is None:
            continue  # suppressed as a chronic false positive
        created.append(record_alert(
            "identity_burst", "identity", subject, severity, window_seconds,
            [v["id"] for v in vs],
            detail={"reason": f"{len(vs)} flagged logins from {subject} within {window_seconds}s",
                    "history": subject_outcome_history(subject, "identity")}))

    # rule 2: ics_sustained — ICS has no per-account subject; count flagged ICS in the window
    ics = [v for v in flagged if v["model"] == "ics"]
    if len(ics) >= ics_sustained_min and not recent_alert_exists("ics_sustained", None, since):
        created.append(record_alert(
            "ics_sustained", "ics", None, "high", window_seconds,
            [v["id"] for v in ics],
            detail={"reason": f"{len(ics)} sustained ICS anomalies within {window_seconds}s"}))

    # rule 3: high_severity — a single verdict with an extreme score, alerted immediately
    # (don't wait for N). Dedup key: identity by subject; ICS by a constant so a stream of
    # severe readings raises one open alert per window rather than storming.
    for v in flagged:
        score = v["score"]
        if score is None:
            continue
        if v["model"] == "ics" and score >= ics_severe_error:
            key = "ics"
        elif v["model"] == "identity" and v["subject"] and score <= identity_severe:
            key = v["subject"]
        else:
            continue
        if is_suppressed(key, v["model"]):
            continue  # analyst-allowlisted subject
        if recent_alert_exists("high_severity", key, since):
            continue
        created.append(record_alert(
            "high_severity", v["model"], key, "high", window_seconds, [v["id"]],
            detail={"score": score, "reason": "single verdict with an extreme anomaly score"}))

    # Act layer (C3): fire responders for each newly-created alert (inline, best-effort).
    for alert_id in created:
        try:
            actions.dispatch(get_alert(alert_id))
        except Exception:
            pass

    return created
