"""
Import an official NIST OLIR / CSF-2.0 informative-reference export into the crosswalk pair format.

NIST publishes authoritative crosswalks (e.g., CSF 2.0 -> SP 800-53) as downloadable exports
(CSV/JSON/XLSX) via the National Online Informative References (OLIR) program and the CSF 2.0
reference tool. NIST content is public domain. This importer converts such an export into the
three-file pair format read by eval_crosswalk.py and the RegMap engine, tagging every mapping
provenance="official".

Because OLIR export column names vary by release, this is a thin, column-mapped importer: point it at
your downloaded file and tell it which columns hold the source id / source text / target id / target
text. It then writes source.jsonl, corpus.jsonl, gold.jsonl into the output pair directory.

Example (CSV with headers):
    python regmap_engine/import_olir.py \
        --infile csf2_to_80053.csv --format csv \
        --source-id "Focal Document Element" --source-text "Focal Document Element Description" \
        --target-id "Reference Document Element" --target-text "Reference Document Element Description" \
        --out regmap_engine/crosswalks/nist_csf2__nist_80053 \
        --source-framework "NIST CSF 2.0 (subcategories)" --target-framework "NIST SP 800-53 Rev.5 (controls)"

Download the export first from the NIST CSF 2.0 Reference Tool / OLIR catalog:
    https://csrc.nist.gov/projects/olir   and   https://www.nist.gov/cyberframework
"""
import argparse
import csv
import json
from pathlib import Path


def read_rows(infile, fmt):
    p = Path(infile)
    if fmt == "csv":
        with open(p, newline="", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    if fmt == "json":
        data = json.loads(p.read_text(encoding="utf-8"))
        # accept either a list of row dicts or {"mappings":[...]}
        return data.get("mappings", data) if isinstance(data, dict) else data
    raise SystemExit(f"unsupported --format {fmt} (use csv or json)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--infile", required=True)
    ap.add_argument("--format", choices=["csv", "json"], default="csv")
    ap.add_argument("--source-id", required=True)
    ap.add_argument("--source-text", required=True)
    ap.add_argument("--target-id", required=True)
    ap.add_argument("--target-text", required=True)
    ap.add_argument("--out", required=True, help="output pair directory")
    ap.add_argument("--source-framework", required=True)
    ap.add_argument("--target-framework", required=True)
    a = ap.parse_args()

    rows = read_rows(a.infile, a.format)
    source, corpus, gold = {}, {}, {}
    for r in rows:
        sid, stext = str(r.get(a.source_id, "")).strip(), str(r.get(a.source_text, "")).strip()
        tid, ttext = str(r.get(a.target_id, "")).strip(), str(r.get(a.target_text, "")).strip()
        if not sid or not tid:
            continue
        source.setdefault(sid, stext)
        corpus.setdefault(tid, ttext)
        gold.setdefault(sid, set()).add(tid)

    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    (out / "meta.json").write_text(json.dumps({
        "source_framework": a.source_framework, "target_framework": a.target_framework,
        "description": f"Official crosswalk imported from {Path(a.infile).name}.",
        "provenance": "official (NIST OLIR / CSF reference)", "direction": "source -> target",
        "license_note": "NIST publications are U.S. Government works (public domain)."}, indent=2), encoding="utf-8")
    with open(out / "source.jsonl", "w", encoding="utf-8") as f:
        for sid, t in source.items():
            f.write(json.dumps({"id": sid, "text": t}) + "\n")
    with open(out / "corpus.jsonl", "w", encoding="utf-8") as f:
        for cid, t in corpus.items():
            f.write(json.dumps({"id": cid, "text": t}) + "\n")
    with open(out / "gold.jsonl", "w", encoding="utf-8") as f:
        for sid, tids in gold.items():
            f.write(json.dumps({"source_id": sid, "target_ids": sorted(tids), "provenance": "official"}) + "\n")
    print(f"wrote {a.out}: {len(source)} source · {len(corpus)} corpus · {len(gold)} mapped source items (provenance=official)")


if __name__ == "__main__":
    main()
