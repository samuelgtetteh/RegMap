"""
Tally detection quality from saved event-source logs.

The identity and OT/ICS live sources each print, per event, both what the
generator INTENDED (injected normal / suspicious / attack) and what the model
actually DECIDED (OK / ALERT). This script parses those saved log lines and
turns the visual OK/ALERT-vs-injected comparison into hard numbers: a
confusion matrix plus recall, specificity, precision and accuracy.

Usage:
    python tally_detection.py <path>

    <path> may be a single .log file or a directory (e.g. a folder produced by
    snapshot_logs.ps1); every .log file in a directory is tallied separately.

Definitions used here:
    positive  = an event the generator injected as suspicious/attack
    negative  = an event the generator injected as normal
    predicted positive = the model returned ALERT
    predicted negative = the model returned OK
"""
import argparse
import re
import sys
from pathlib import Path

# Matches e.g. "ALERT (injected suspicious)" or "   OK (injected normal)".
LINE_RE = re.compile(r"\b(ALERT|OK)\b.*?\(injected (normal|suspicious|attack)\)")

POSITIVE_KINDS = {"suspicious", "attack"}


def tally_file(path):
    """Return counts dict for one log file, or None if it has no scored events."""
    tp = fp = tn = fn = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = LINE_RE.search(line)
        if not m:
            continue
        status, kind = m.group(1), m.group(2)
        is_positive = kind in POSITIVE_KINDS
        predicted_positive = status == "ALERT"
        if is_positive and predicted_positive:
            tp += 1
        elif is_positive and not predicted_positive:
            fn += 1
        elif not is_positive and predicted_positive:
            fp += 1
        else:
            tn += 1
    total = tp + fp + tn + fn
    if total == 0:
        return None
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn, "total": total}


def _pct(numer, denom):
    return f"{100.0 * numer / denom:.1f}%" if denom else "n/a"


def print_report(name, c):
    tp, fp, tn, fn = c["tp"], c["fp"], c["tn"], c["fn"]
    print(f"\n=== {name} ===")
    print(f"  events scored:        {c['total']}")
    print(f"  injected anomalies:   {tp + fn}   (ALERT={tp}, missed/OK={fn})")
    print(f"  injected normal:      {tn + fp}   (OK={tn}, false ALERT={fp})")
    print(f"  ---")
    print(f"  recall (detection):   {_pct(tp, tp + fn)}   [caught {tp} of {tp + fn} anomalies]")
    print(f"  specificity:          {_pct(tn, tn + fp)}   [correct on {tn} of {tn + fp} normals]")
    print(f"  precision:            {_pct(tp, tp + fp)}   [of {tp + fp} ALERTs, {tp} were real]")
    print(f"  accuracy:             {_pct(tp + tn, c['total'])}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", help="A .log file, or a directory of .log files (e.g. a snapshot folder)")
    args = parser.parse_args()

    target = Path(args.path)
    if not target.exists():
        print(f"Path not found: {target}", file=sys.stderr)
        sys.exit(1)

    files = [target] if target.is_file() else sorted(target.glob("*.log"))
    if not files:
        print(f"No .log files found in {target}", file=sys.stderr)
        sys.exit(1)

    any_scored = False
    for f in files:
        counts = tally_file(f)
        if counts is None:
            continue
        any_scored = True
        print_report(f.name, counts)

    if not any_scored:
        print("No scored events (no 'injected ...' lines) found in the given log(s).", file=sys.stderr)
        sys.exit(1)
    print()


if __name__ == "__main__":
    main()
