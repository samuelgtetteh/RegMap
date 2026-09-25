"""
Flattens the JSON-shaped scan + baseline recommendations into a single CSV a
user can open in Excel/Sheets and work through directly — adds empty `status`
and `notes` columns for tracking remediation, since a report you can only read
is less useful than one you can act on.
"""
import csv


def _priority_sort_key(priority):
    return {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}.get(priority, 4)


def to_rows(final_report, baseline_recommendations, drafts=None):
    drafts = drafts or {}
    rows = []
    for host in final_report["hosts"]:
        for category, controls in host["recommended_controls"].items():
            for c in controls:
                rows.append({
                    "source": "scan_finding",
                    "host_ip": host["ip"],
                    "category": category,
                    "control_id": c["control_id"],
                    "control_text": c["control_text"],
                    "priority": c["priority"],
                    "adjusted_score": c["adjusted_score"],
                    "reasons": "; ".join(c["reasons"]),
                    "draft_language": drafts.get(c["control_id"], ""),
                    "status": "",
                    "notes": "",
                })

    for c in baseline_recommendations:
        rows.append({
            "source": "baseline",
            "host_ip": "",
            "category": "baseline",
            "control_id": c["control_id"],
            "control_text": c["control_text"],
            "priority": c["priority"],
            "adjusted_score": c["adjusted_score"],
            "reasons": "; ".join(c["reasons"]),
            "draft_language": drafts.get(c["control_id"], ""),
            "status": "",
            "notes": "",
        })

    rows.sort(key=lambda r: (_priority_sort_key(r["priority"]), -r["adjusted_score"]))
    return rows


def write_csv(final_report, baseline_recommendations, path, drafts=None):
    rows = to_rows(final_report, baseline_recommendations, drafts=drafts)
    fieldnames = ["source", "host_ip", "category", "control_id", "control_text",
                  "priority", "adjusted_score", "reasons", "draft_language", "status", "notes"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)
