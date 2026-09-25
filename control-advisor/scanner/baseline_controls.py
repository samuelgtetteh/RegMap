"""
Baseline controls every environment needs regardless of what the network scan
finds. A port scan can never discover "do you have backups," "is there an
incident response plan," or "are personnel trained" — these are foundational
NIST 800-53 controls that apply universally, not tied to any specific
discovered host or service. They're surfaced separately from scan-driven
findings (see interview.py) precisely so a report never implies "we only need
these because we found a database" when the real answer is "every environment
needs this regardless."
"""
from pathlib import Path

import pandas as pd

CORPUS_CSV = Path(__file__).parent.parent.parent / "data" / "processed" / "labeled_pairs.csv"

# Selected for being foundational security hygiene that no scan can detect —
# not an exhaustive baseline (that's effectively the whole 800-53 catalog),
# but the set most universally applicable regardless of environment specifics.
BASELINE_CONTROL_IDS = [
    "AC-2",   # Account Management
    "AC-6",   # Least Privilege
    "AC-7",   # Unsuccessful Logon Attempts
    "AT-2",   # Literacy Training and Awareness
    "AU-2",   # Event Logging
    "AU-6",   # Audit Record Review, Analysis, and Reporting
    "CM-2",   # Baseline Configuration
    "CM-8",   # System Component Inventory
    "CP-2",   # Contingency Plan
    "CP-9",   # System Backup
    "IA-2",   # Identification and Authentication (Organizational Users)
    "IA-5",   # Authenticator Management
    "IR-4",   # Incident Handling
    "IR-8",   # Incident Response Plan
    "PL-2",   # System Security and Privacy Plans
    "PS-3",   # Personnel Screening
    "RA-3",   # Risk Assessment
    "RA-5",   # Vulnerability Monitoring and Scanning
    "SC-7",   # Boundary Protection
    "SI-2",   # Flaw Remediation
    "SI-3",   # Malicious Code Protection
]


def load_baseline_controls():
    df = pd.read_csv(CORPUS_CSV)
    unique = df.drop_duplicates(subset=["nist_control_id"]).set_index("nist_control_id")
    controls = []
    for control_id in BASELINE_CONTROL_IDS:
        if control_id in unique.index:
            controls.append({
                "control_id": control_id,
                "control_text": unique.loc[control_id, "nist_text"][:300],
                "score": 0.5,  # neutral base score; interview.py's context rules do the real weighting
            })
    return controls
