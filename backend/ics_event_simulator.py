"""
Replays real HAI sensor readings against the live OT/ICS Intrusion Detection
API, one reading at a time with a delay between each — simulating how a
SCADA historian would stream live sensor telemetry into this detector in
production. Reads sequentially from test2.csv starting just before its first
real attack window, so a live run naturally transitions from normal to
attack, and compares the live verdict to the file's actual attack label.

Run this alongside the backend (`uvicorn app:app --reload --port 8000` or
against the Docker container's exposed port).
"""
import argparse
import ast
import time
from datetime import datetime

import polars as pl
import requests

DATA_FILE = "../data/raw/test2.csv"
META_FILE = "../data/processed/autoencoder_hai_meta.txt"


def load_feature_order():
    meta = {}
    for line in open(META_FILE):
        key, _, value = line.partition("=")
        meta[key] = value
    return ast.literal_eval(meta["feature_cols"])


def score_reading(api_url: str, readings: dict) -> dict:
    resp = requests.post(f"{api_url}/ics/score", json={"readings": readings}, timeout=10)
    resp.raise_for_status()
    return resp.json()


def run(api_url: str, interval: float, start_row: int, iterations: int) -> None:
    feature_order = load_feature_order()
    df = pl.read_csv(DATA_FILE, separator=";", ignore_errors=True)
    window = df.slice(start_row, iterations)
    print(f"Loaded {len(window)} real sensor readings starting at row {start_row} of {DATA_FILE}")

    for row in window.iter_rows(named=True):
        timestamp = datetime.now().strftime("%H:%M:%S")
        readings = {f: float(row[f]) for f in feature_order}

        try:
            result = score_reading(api_url, readings)
        except requests.RequestException as exc:
            print(f"[{timestamp}] ERROR calling {api_url}: {exc}")
            time.sleep(interval)
            continue

        ground_truth_attack = bool(row["attack"])
        live_anomalous = result["is_anomaly"]
        agree = "agrees with" if live_anomalous == ground_truth_attack else "DISAGREES with"

        status = "ALERT" if live_anomalous else "OK"
        print(f"[{timestamp}] {status:>5} :: reconstruction_error={result['reconstruction_error']:.4f} "
              f"(threshold={result['threshold']})")
        print(f"           (live model {agree} the recorded label, "
              f"which marks this reading as {'an attack' if ground_truth_attack else 'normal'})")

        time.sleep(interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Replay real HAI sensor readings against the live OT/ICS API.")
    parser.add_argument("--api-url", default="http://localhost:8000", help="Base URL of the running backend API")
    parser.add_argument("--interval", type=float, default=2.0, help="Seconds between simulated readings")
    parser.add_argument("--start-row", type=int, default=1800, help="Row offset to start replaying from (default: just before test2.csv's first attack)")
    parser.add_argument("--iterations", type=int, default=50, help="Number of readings to replay")
    args = parser.parse_args()

    run(args.api_url, args.interval, args.start_row, args.iterations)
