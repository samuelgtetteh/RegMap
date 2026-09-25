"""
Replays real historical LANL login events against the live Identity Anomaly
API, one at a time with a delay between each — simulating how a SIEM or
identity provider would stream live authentication events into this
detector in production. Uses real recorded events (including genuine
anomalies flagged by the original batch analysis) rather than synthetic
data, and compares the live API's verdict to that original ground truth so
you can see whether the live, stateful version agrees with the offline
batch analysis it was adapted from.

Run this alongside the backend (`uvicorn app:app --reload --port 8000` or
against the Docker container's exposed port).
"""
import argparse
import time
from datetime import datetime

import pandas as pd
import requests

DATA_FILE = "../data/processed/lanl_auth_with_anomalies.csv"


def load_events(start_row: int, count: int) -> pd.DataFrame:
    cols = ["src_user", "src_pc", "auth_type", "logon_type", "orientation", "success", "anomaly"]
    return pd.read_csv(DATA_FILE, usecols=cols, skiprows=range(1, start_row + 1), nrows=count)


def score_event(api_url: str, row) -> dict:
    payload = {
        "src_user": row["src_user"],
        "src_pc": row["src_pc"],
        "auth_type": row["auth_type"],
        "logon_type": row["logon_type"],
        "orientation": row["orientation"],
        "success": row["success"],
    }
    resp = requests.post(f"{api_url}/identity/score", json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()


def run(api_url: str, interval: float, start_row: int, iterations: int) -> None:
    events = load_events(start_row, iterations)
    print(f"Loaded {len(events)} real login events starting at row {start_row} of {DATA_FILE}")

    for _, row in events.iterrows():
        timestamp = datetime.now().strftime("%H:%M:%S")
        try:
            result = score_event(api_url, row)
        except requests.RequestException as exc:
            print(f"[{timestamp}] ERROR calling {api_url}: {exc}")
            time.sleep(interval)
            continue

        ground_truth_anomalous = bool(row["anomaly"])
        live_anomalous = result["is_anomaly"]
        agree = "agrees with" if live_anomalous == ground_truth_anomalous else "DISAGREES with"

        status = "ALERT" if live_anomalous else "OK"
        print(f"[{timestamp}] {status:>5} :: {row['src_user']} on {row['src_pc']} "
              f"({row['auth_type']}/{row['logon_type']}, {row['success']}) "
              f"score={result['anomaly_score']:.3f}")
        print(f"           (live model {agree} original batch analysis, "
              f"which flagged this event as {'anomalous' if ground_truth_anomalous else 'normal'})")

        time.sleep(interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Replay real LANL login events against the live Identity Anomaly API.")
    parser.add_argument("--api-url", default="http://localhost:8000", help="Base URL of the running backend API")
    parser.add_argument("--interval", type=float, default=2.0, help="Seconds between simulated events")
    parser.add_argument("--start-row", type=int, default=0, help="Row offset in the dataset to start replaying from")
    parser.add_argument("--iterations", type=int, default=50, help="Number of events to replay")
    args = parser.parse_args()

    run(args.api_url, args.interval, args.start_row, args.iterations)
