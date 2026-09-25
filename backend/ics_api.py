"""
Live scoring endpoint for the OT/ICS Intrusion Detector (autoencoder on HAI sensor data).

Model: data/processed/autoencoder_hai.pth + scaler_hai.pkl — retrained without the
attack-label columns that were originally leaked into the feature set (see
notebooks/04_ot_ics_intrusion_detection.ipynb, cell 3). Trained on 59 real sensor/
actuator tags only; input_dim/encoding_dim/threshold/feature order are read directly
from data/processed/autoencoder_hai_meta.txt, which was written from the exact
variables used at training time (not re-derived/guessed here).

A live sensor feed won't necessarily report every one of the 59 tags on every tick, so
any field missing from a request is filled from BASELINE_READING (a real recorded
normal row) — see the comment on that constant for why a per-feature statistical mean
was tried first and rejected.
"""
import ast
from pathlib import Path
from typing import Dict

import joblib
import torch
import torch.nn as nn
from fastapi import APIRouter, Request
from pydantic import BaseModel

from verdict_store import record_verdict_safe

router = APIRouter(prefix="/ics", tags=["ics"])

# Anchored to this file's location, not the process CWD, so artifacts resolve
# identically whether launched from backend/, the repo root, or inside Docker.
DATA_PROCESSED = Path(__file__).resolve().parent.parent / "data" / "processed"

meta = {}
for line in (DATA_PROCESSED / "autoencoder_hai_meta.txt").read_text().splitlines():
    key, _, value = line.partition("=")
    meta[key] = value

INPUT_DIM = int(meta["input_dim"])
ENCODING_DIM = int(meta["encoding_dim"])
THRESHOLD = float(meta["threshold"])
FEATURE_ORDER = ast.literal_eval(meta["feature_cols"])


class Autoencoder(nn.Module):
    def __init__(self, input_dim, encoding_dim=32):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, 128), nn.ReLU(),
            nn.Linear(128, 64), nn.ReLU(),
            nn.Linear(64, encoding_dim),
        )
        self.decoder = nn.Sequential(
            nn.Linear(encoding_dim, 64), nn.ReLU(),
            nn.Linear(64, 128), nn.ReLU(),
            nn.Linear(128, input_dim),
        )

    def forward(self, x):
        return self.decoder(self.encoder(x))


scaler = joblib.load(DATA_PROCESSED / "scaler_hai.pkl")
model = Autoencoder(INPUT_DIM, ENCODING_DIM)
model.load_state_dict(torch.load(DATA_PROCESSED / "autoencoder_hai.pth", map_location="cpu"))
model.eval()

# A real observed normal reading (train1.csv, row 1000, attack=0), used as the fallback
# for any field missing from a request. The per-feature training MEAN was tried first
# and rejected: averaging each of the 59 sensors independently doesn't yield a
# physically realistic *combined* operating point for a turbine that runs in a handful
# of distinct regimes, so an all-means vector actually scores as anomalous (0.082,
# ~9x over threshold) despite representing no real attack. A real recorded row avoids
# that trap and reliably scores well under threshold (~0.0016).
BASELINE_READING = {
    "P1_B2004": 0.0983, "P1_B2016": 0.9481, "P1_B3004": 399.2321, "P1_B3005": 1110.3986,
    "P1_B4002": 32.0, "P1_B4005": 0.0, "P1_B400B": 32.9705, "P1_B4022": 35.3325,
    "P1_FCV01D": 0.0, "P1_FCV01Z": 0.2838, "P1_FCV02D": 100.0, "P1_FCV02Z": 95.5368,
    "P1_FCV03D": 53.7863, "P1_FCV03Z": 54.3228, "P1_FT01": 115.6234, "P1_FT01Z": 579.1716,
    "P1_FT02": 6.1417, "P1_FT02Z": 31.9776, "P1_FT03": 310.936, "P1_FT03Z": 1111.5228,
    "P1_LCV01D": 21.9717, "P1_LCV01Z": 21.7834, "P1_LIT01": 395.0419, "P1_PCV01D": 30.7836,
    "P1_PCV01Z": 31.4728, "P1_PCV02D": 12.0, "P1_PCV02Z": 12.0102, "P1_PIT01": 0.8943,
    "P1_PIT02": 0.2153, "P1_TIT01": 35.8032, "P1_TIT02": 37.146, "P2_24Vdc": 28.0246,
    "P2_Auto": 1.0, "P2_Emgy": 0.0, "P2_On": 1.0, "P2_SD01": 20.0, "P2_SIT01": 814.0,
    "P2_TripEx": 0.0, "P2_VT01e": 11.8639, "P2_VXT02": -3.2829, "P2_VXT03": -1.2577,
    "P2_VYT02": 0.4135, "P2_VYT03": 1.8313, "P3_LCP01D": 4.0, "P3_LCV01D": 0.0,
    "P3_LH": 70.0, "P3_LL": 10.0, "P3_LT01": 68.95255, "P4_HT_FD": -0.0001,
    "P4_HT_LD": -0.0072, "P4_HT_PO": 0.0724, "P4_HT_PS": 0.0, "P4_LD": 300.9802,
    "P4_ST_FD": -0.003, "P4_ST_LD": 298.0324, "P4_ST_PO": 287.1274, "P4_ST_PS": 50.9871,
    "P4_ST_PT01": 9916.0, "P4_ST_TT01": 27627.0,
}


class SensorReading(BaseModel):
    readings: Dict[str, float]


class IcsResult(BaseModel):
    is_anomaly: bool
    reconstruction_error: float
    threshold: float
    missing_fields: list[str]


@router.post("/score", response_model=IcsResult)
def score_reading(payload: SensorReading, request: Request) -> IcsResult:
    missing = [f for f in FEATURE_ORDER if f not in payload.readings]
    row = [payload.readings.get(f, BASELINE_READING[f]) for f in FEATURE_ORDER]

    scaled = scaler.transform([row])
    with torch.no_grad():
        x = torch.tensor(scaled, dtype=torch.float32)
        recon = model(x)
        error = torch.mean((recon - x) ** 2).item()
    is_anomaly = error > THRESHOLD

    # Record layer: persist the verdict. Score is the reconstruction error; a single
    # shared sensor stream has no per-account subject, so subject is left null.
    request.state.verdict_id = record_verdict_safe(
        model="ics", flagged=is_anomaly, score=round(error, 6),
        subject=None,
        detail={"threshold": THRESHOLD, "missing_field_count": len(missing)},
    )

    return IcsResult(
        is_anomaly=is_anomaly,
        reconstruction_error=round(error, 6),
        threshold=THRESHOLD,
        missing_fields=missing,
    )


@router.get("/example", response_model=Dict[str, float])
def example_reading():
    """Returns a real recorded normal reading that can be POSTed to /ics/score
    as-is — useful for exploring the endpoint without needing to source HAI
    sensor data yourself."""
    return BASELINE_READING


@router.get("/health")
def health():
    return {"status": "ok"}
