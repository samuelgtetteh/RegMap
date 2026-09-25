"""
Build small, labelled SAMPLE datasets from the target labs for publication on the Hugging Face Hub
(dataset repos). These are illustrative samples of what each lab generates/seeds — not the tools
themselves (the tools are on GitHub + GHCR).

  dist/hf/live-target-lab-events/    identity_events.jsonl + ics_readings.jsonl + README (card)
  dist/hf/cloud-target-lab-scenarios/ scenarios.csv + README (card)

Run:  venv\\Scripts\\python.exe scripts\\make_lab_datasets.py
"""
import csv
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIVE = Path("C:/Users/User/live-target-lab")
OUT = ROOT / "dist" / "hf"
sys.path.insert(0, str(LIVE))

import identity_generator as ig   # safe: streaming loop is under __main__
import ics_generator as ic

N = int(sys.argv[1]) if len(sys.argv) > 1 else 300   # rows per split; override: make_lab_datasets.py 5000


def build_live():
    d = OUT / "live-target-lab-events"; d.mkdir(parents=True, exist_ok=True)
    # identity events (~15% injected-suspicious bursts)
    with open(d / "identity_events.jsonl", "w", encoding="utf-8") as f:
        for _ in range(N):
            if random.random() < 0.15:
                u = random.choice(ig.SUSPICIOUS_USERS); pc = random.choice(ig.NORMAL_PCS)
                ev = ig.make_attack_event(u, pc); label = "malicious"
            else:
                ev = ig.make_normal_event(); label = "benign"
            f.write(json.dumps({**ev, "injected_label": label}) + "\n")
    # ics readings (generate_reading returns (readings, is_attack))
    with open(d / "ics_readings.jsonl", "w", encoding="utf-8") as f:
        for _ in range(N):
            readings, is_attack = ic.generate_reading()
            f.write(json.dumps({**{k: round(v, 4) for k, v in readings.items()},
                                "injected_label": "malicious" if is_attack else "benign"}) + "\n")
    _write(d / "README.md", _LIVE_CARD)
    print("live dataset:", d, "| 2 files x", N, "rows")


def build_cloud():
    d = OUT / "cloud-target-lab-scenarios"; d.mkdir(parents=True, exist_ok=True)
    rows = [
        ["s3_bucket", "acme-internal-backups", "private", "secure", "none"],
        ["s3_bucket", "acme-public-uploads", "public-read", "insecure", "public S3 bucket"],
        ["security_group", "sg-insecure-ssh", "SSH open to 0.0.0.0/0", "insecure", "unrestricted SSH ingress"],
        ["security_group", "sg-secure-web", "HTTPS public, SSH restricted", "secure", "none"],
        ["ec2_instance", "legacy-jump-box", "uses sg-insecure-ssh", "insecure", "exposed via insecure SG"],
        ["ec2_instance", "web-frontend", "uses sg-secure-web", "secure", "none"],
        ["iam_user", "svc-legacy-app", "inline policy Action:* Resource:*", "insecure", "admin-equivalent privileges"],
        ["iam_user", "alice-analyst", "scoped read-only policy", "secure", "none"],
    ]
    with open(d / "scenarios.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["resource_type", "name", "configuration", "posture", "expected_finding"])
        w.writerows(rows)
    _write(d / "README.md", _CLOUD_CARD)
    print("cloud dataset:", d, "|", len(rows), "scenarios")


def _write(p, s):
    p.write_text(s, encoding="utf-8")


_LIVE_CARD = """---
license: apache-2.0
task_categories:
- tabular-classification
tags:
- cybersecurity
- synthetic
- anomaly-detection
- identity
- ot-ics
---

# Live Target Lab — synthetic event samples

Labelled SAMPLE events produced by the [live-target-lab](https://github.com/samuelgtetteh/live-target-lab)
test harness, which continuously streams synthetic events to the Identity and OT/ICS detectors.

- `identity_events.jsonl` — synthetic login events; `injected_label` is the intended ground truth
  (`malicious` = a lateral-movement/credential-stuffing pattern, `benign` = ordinary login).
- `ics_readings.jsonl` — synthetic HAI sensor readings; `injected_label` marks readings with an
  injected spike (`malicious`) vs normal jitter (`benign`).

These are illustrative samples for exploration; the lab itself (which generates fresh data forever
and reports ground-truth feedback) is on GitHub and GHCR. Pairs with the detector models
[`stetteh/identity-anomaly`](https://huggingface.co/stetteh/identity-anomaly) and
[`stetteh/otics-anomaly`](https://huggingface.co/stetteh/otics-anomaly).
"""

_CLOUD_CARD = """---
license: apache-2.0
tags:
- cybersecurity
- cloud-security
- synthetic
---

# Cloud Target Lab — seeded scenario catalog

The mixed secure/insecure AWS resources that the
[cloud-target-lab](https://github.com/samuelgtetteh/cloud-target-lab) seeds into a LocalStack
fake-AWS to test cloud security scanners. `scenarios.csv` lists each resource, its configuration,
whether it is intentionally secure or insecure, and the finding a scanner should surface.

This is the scenario definition (ground truth for scanner testing); the lab that stands up a live
LocalStack and seeds these resources is on GitHub and GHCR.
"""

if __name__ == "__main__":
    build_live()
    build_cloud()
