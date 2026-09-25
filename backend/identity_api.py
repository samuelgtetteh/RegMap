"""
Live scoring endpoint for the Hybrid Identity Anomaly Detector (Isolation Forest).

The trained model (data/processed/isolation_forest_model.pkl + scaler.pkl) expects
9 features per login event, in this exact order (confirmed via scaler.feature_names_in_):
    hour, day_of_week, is_weekend, hourly_count, unique_pcs,
    logon_type_code, auth_type_code, orientation_code, success_code

Two of those were originally computed as whole-dataset batch aggregates (hourly_count,
unique_pcs) and the categorical codes were assigned by pd.factorize with no saved mapping.
Both are reconstructed here: category codes are recovered exactly from
data/processed/lanl_auth_with_anomalies.csv (which retains both the raw string and the
code it was assigned during training), and the aggregates are replaced with live rolling
counters that accumulate as real events stream in, in place of the original one-shot
whole-batch computation.
"""
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Optional

import joblib
import pandas as pd
from fastapi import APIRouter, Request
from pydantic import BaseModel

from verdict_store import record_verdict_safe

router = APIRouter(prefix="/identity", tags=["identity"])

# Anchored to this file's location, not the process CWD, so the model resolves
# identically whether launched from backend/, the repo root, or inside Docker.
DATA_PROCESSED = Path(__file__).resolve().parent.parent / "data" / "processed"
MODEL_PATH = DATA_PROCESSED / "isolation_forest_model.pkl"
SCALER_PATH = DATA_PROCESSED / "scaler.pkl"

model = joblib.load(MODEL_PATH)
scaler = joblib.load(SCALER_PATH)

FEATURE_ORDER = [
    "hour", "day_of_week", "is_weekend", "hourly_count", "unique_pcs",
    "logon_type_code", "auth_type_code", "orientation_code", "success_code",
]

AUTH_TYPE_CODES = {
    "NTLM": 0, "?": 1, "Negotiate": 2, "Kerberos": 3,
    "MICROSOFT_AUTHENTICATION_PACKAGE_V1_0": 4,
    "MICROSOFT_AUTHENTICATION_PAC": 5,
    "MICROSOFT_AUTHENTICATION_PACKAGE": 6,
    "MICROSOFT_AUTHENTICATION_PACKAG": 7,
    "MICROSOFT_AUTHENTICATION_PACKAGE_V1": 8,
    "MICROSOFT_AUTHENTICATION_PACKAGE_": 9,
    "MICROSOFT_AUTHENTICATION_PA": 10,
}
LOGON_TYPE_CODES = {
    "Network": 0, "Service": 1, "Batch": 2, "?": 3, "Interactive": 4,
    "NetworkCleartext": 5, "NewCredentials": 6, "Unlock": 7, "RemoteInteractive": 8,
}
ORIENTATION_CODES = {"LogOn": 0, "LogOff": 1, "TGS": 2, "AuthMap": 3, "TGT": 4}
SUCCESS_CODES = {"Success": 0, "Fail": 1}
UNKNOWN_CODE = -1

# In-memory rolling state — resets on restart. A production deployment would back
# this with Redis or similar so counts survive restarts and are shared across replicas.
#
# Per user we keep only the (timestamp, src_pc) of events within the last hour, so
# both derived features are a true SLIDING WINDOW: hourly_count is events in the
# trailing hour and unique_pcs is distinct PCs in that same window. An earlier
# version keyed hourly_count on (user, hour_of_day 0-23), which silently collided
# across days and accumulated forever — and its per-user PC set only ever grew,
# so memory was unbounded. Pruning aged-out entries on each event (plus a periodic
# sweep for users that never return) fixes both the semantics and the growth.
WINDOW = timedelta(hours=1)
_SWEEP_EVERY = 1000  # sweep one-shot users out roughly every N scored events

_lock = Lock()
_recent_events: dict[str, deque] = defaultdict(deque)
_event_counter = 0


class LoginEvent(BaseModel):
    src_user: str
    src_pc: str
    auth_type: str
    logon_type: str
    orientation: str
    success: str
    timestamp: Optional[datetime] = None


class AnomalyResult(BaseModel):
    is_anomaly: bool
    anomaly_score: float
    hourly_count: int
    unique_pcs: int


@router.post("/score", response_model=AnomalyResult)
def score_event(event: LoginEvent, request: Request) -> AnomalyResult:
    ts = event.timestamp or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    hour = ts.hour
    day_of_week = ts.weekday()
    is_weekend = 1 if day_of_week in (5, 6) else 0

    global _event_counter
    with _lock:
        cutoff = ts - WINDOW
        events = _recent_events[event.src_user]
        events.append((ts, event.src_pc))
        while events and events[0][0] < cutoff:
            events.popleft()
        hourly_count = len(events)
        unique_pcs = len({pc for _, pc in events})

        # Periodically drop users whose most recent event has aged out of the
        # window, so single-appearance users don't leak memory forever.
        _event_counter += 1
        if _event_counter % _SWEEP_EVERY == 0:
            stale = [u for u, dq in _recent_events.items() if not dq or dq[-1][0] < cutoff]
            for u in stale:
                del _recent_events[u]

    row = {
        "hour": hour,
        "day_of_week": day_of_week,
        "is_weekend": is_weekend,
        "hourly_count": hourly_count,
        "unique_pcs": unique_pcs,
        "logon_type_code": LOGON_TYPE_CODES.get(event.logon_type, UNKNOWN_CODE),
        "auth_type_code": AUTH_TYPE_CODES.get(event.auth_type, UNKNOWN_CODE),
        "orientation_code": ORIENTATION_CODES.get(event.orientation, UNKNOWN_CODE),
        "success_code": SUCCESS_CODES.get(event.success, UNKNOWN_CODE),
    }
    features_df = pd.DataFrame([row], columns=FEATURE_ORDER)

    scaled = scaler.transform(features_df)
    score = float(model.decision_function(scaled)[0])
    is_anomaly = score < 0

    # Record layer: persist the verdict keyed by src_user, so the Decide layer can
    # later apply per-account windowed rules (e.g. repeated anomalies from one user).
    request.state.verdict_id = record_verdict_safe(
        model="identity", flagged=is_anomaly, score=round(score, 6),
        subject=event.src_user, event_time=ts,
        detail={"src_pc": event.src_pc, "auth_type": event.auth_type,
                "logon_type": event.logon_type, "success": event.success,
                "hourly_count": hourly_count, "unique_pcs": unique_pcs},
    )

    return AnomalyResult(
        is_anomaly=is_anomaly,
        anomaly_score=round(score, 6),
        hourly_count=hourly_count,
        unique_pcs=unique_pcs,
    )


@router.get("/health")
def health():
    return {"status": "ok"}
