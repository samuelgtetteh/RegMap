"""
Simulates a stream of compliance-audit events hitting the RegMap API,
mimicking a CI/CD pipeline checking new/changed controls against HIPAA
in real time. Run this alongside `uvicorn app:app --reload --port 8000`.
"""
import argparse
import time
from datetime import datetime

import requests

NIST_SAMPLES = [
    "Develop, document, and disseminate access control policies and procedures.",
    "Implement mechanisms to monitor and control communications at external and internal boundaries.",
    "Regularly test and validate security controls to ensure effectiveness.",
    "Conduct periodic risk assessments to identify vulnerabilities.",
    "Enforce a limit of consecutive invalid logon attempts by a user.",
    "Encrypt information at rest and in transit using approved cryptographic mechanisms.",
    "Establish and maintain an incident response capability.",
    "Ensure that audit records are retained for a defined time period.",
]

ALERT_THRESHOLD = 0.5


def check_control(api_url: str, control: str) -> list[dict]:
    resp = requests.post(f"{api_url}/map", json={"nist_control": control}, timeout=10)
    resp.raise_for_status()
    return resp.json()


def run(api_url: str, interval: float, iterations: int | None) -> None:
    count = 0
    while iterations is None or count < iterations:
        control = NIST_SAMPLES[count % len(NIST_SAMPLES)]
        timestamp = datetime.now().strftime("%H:%M:%S")
        try:
            mappings = check_control(api_url, control)
        except requests.RequestException as exc:
            print(f"[{timestamp}] ERROR calling {api_url}: {exc}")
            time.sleep(interval)
            count += 1
            continue

        top = mappings[0] if mappings else None
        status = "OK" if top and top["score"] >= ALERT_THRESHOLD else "ALERT: low-confidence mapping"
        print(f"[{timestamp}] {status} :: {control[:70]}")
        for m in mappings:
            print(f"    -> ({m['score']:.4f}) {m['hipaa_citation'][:90]}")

        count += 1
        time.sleep(interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulate real-time compliance events against the RegMap API.")
    parser.add_argument("--api-url", default="http://localhost:8000", help="Base URL of the running RegMap API")
    parser.add_argument("--interval", type=float, default=5.0, help="Seconds between simulated events")
    parser.add_argument("--iterations", type=int, default=None, help="Number of events to send (default: run forever)")
    args = parser.parse_args()

    run(args.api_url, args.interval, args.iterations)
