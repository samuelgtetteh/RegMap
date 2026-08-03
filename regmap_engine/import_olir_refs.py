"""
Import the NIST CSF 2.0 Informative References export into RegMap mappings.

NIST publishes, per CSF 2.0 subcategory, the elements of ~20 other frameworks that address the same
outcome (the OLIR programme). The export is an XLSX:

    https://csrc.nist.gov/extensions/nudp/services/json/csf/download?olirids=all
    -> sheet "CSF 2.0", columns: Function | Category | Subcategory | Implementation Examples |
                                Informative References
    reference cell = one "Framework Name: element id" per line

This is the cheapest breadth in the whole product: one public-domain NIST export yields official
mappings from CSF 2.0 to many frameworks at once, and CSF 2.0 is a hub, so each one composes with
everything else already on the hub.

LICENSING — why some frameworks get a mapping but no control text:
NIST's crosswalk is a US Government work, so the *mapping* (which ISO clause or PCI requirement
corresponds to a CSF outcome) is freely usable. The *control text* of ISO 27001, PCI DSS and CIS is
copyrighted and is NOT in this export and NOT shipped by us. Those frameworks therefore land as
mapping-only: their ids are known and crosswalkable, but they cannot be semantically searched until
someone supplies licensed text or writes an original paraphrase. `--mapping-only` records that
honestly instead of inventing text.

    python import_olir_refs.py --infile ../data/raw/oscal/csf_olir_all.xlsx
    python import_olir_refs.py --infile ../data/raw/oscal/csf_olir_all.xlsx --write
"""
import argparse
import re
from pathlib import Path

import catalog as cat
from import_oscal import canon_id

# Framework label in the export -> registry framework id. Labels carry versions that change between
# releases ("SP 800-53 Rev 5.1.1" then "5.2.0"), so match on a pattern, not equality.
LABEL_TO_FID = [
    (r"^SP\s*800-53",            "nist_80053"),
    (r"^SP\s*800-171",           "nist_80171"),
    (r"^SSDF|^SP\s*800-218",     "nist_ssdf"),
    (r"^ISO/IEC\s*27001",        "iso_27001"),
    (r"^PCI\s*DSS",              "pci_dss4"),
    (r"^CIS\s*Controls",         "cis_v8"),
    (r"^SCF$",                   "scf"),
]

# Frameworks whose control text we cannot ship (copyrighted / licence-required). Mappings are fine.
MAPPING_ONLY = {"iso_27001", "pci_dss4", "cis_v8", "scf"}


def fid_for(label):
    for pat, fid in LABEL_TO_FID:
        if re.search(pat, label, re.I):
            return fid
    return None


def parse_element(fid, raw):
    """Turn the element id in a reference line into the target framework's canonical id.

    Each source writes ids its own way, so normalise per framework rather than globally:
      SP 800-53      "AC-2", "AC-02(03)"        -> AC-2, AC-2(3)   (canon_id)
      SP 800-171     "03.01.01"                 -> unchanged
      ISO 27001      "Mandatory Clause: 4.1",
                     "Annex A Controls: A.5.1"  -> "4.1", "A.5.1"
      PCI DSS        "12.1.1"                   -> unchanged
      CIS            "4.1"                      -> unchanged
    """
    s = str(raw or "").strip().rstrip(",;.")
    if not s:
        return None
    # Some labels contain a colon themselves ("ISO/IEC 27001:2022"), so splitting the line on its first
    # colon leaks the version into the element. Strip a leading 4-digit year here.
    s = re.sub(r"^\d{4}\s*:\s*", "", s).strip()
    # The export uses several spellings for "which part of the standard", none of them part of the id.
    s = re.sub(r"^(Mandatory\s+Clauses?|Annex\s+A\s+Controls?|Controls?|Clause)\s*:?\s*", "",
               s, flags=re.I).strip()
    # Literal placeholders meaning "nothing corresponds" must not become control ids.
    if s.lower() in ("none", "n/a", "na", "-", ""):
        return None
    if fid == "iso_27001":
        return s or None
    if fid in ("nist_80053", "nist_ssdf"):
        c = canon_id(s)
        return c if re.match(r"^[A-Z]{2,3}[-.]\d", c) else None
    return s or None


def read_refs(path):
    """Yield (subcategory_id, framework_label, element_id) from the CSF 2.0 sheet."""
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["CSF 2.0"] if "CSF 2.0" in wb.sheetnames else wb.worksheets[0]
    for row in ws.iter_rows(values_only=True):
        cells = list(row) + [None] * 5
        sub, refs = cells[2], cells[4]
        if not sub or not refs:
            continue
        m = re.match(r"^([A-Z]{2}\.[A-Z]{2}-\d+)", str(sub).strip())
        if not m:
            continue
        sid = m.group(1)
        for line in str(refs).split("\n"):
            line = line.strip()
            if ":" not in line:
                continue
            label, _, element = line.partition(":")
            yield sid, label.strip(), element.strip()
    wb.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--infile", required=True)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    known = cat.load_controls("nist_csf2")
    if not known:
        raise SystemExit("import the CSF 2.0 catalog first (import_oscal.py --fid nist_csf2)")

    mappings, unknown, dropped = {}, {}, 0
    for sid, label, element in read_refs(a.infile):
        fid = fid_for(label)
        if not fid:
            unknown[label] = unknown.get(label, 0) + 1
            continue
        el = parse_element(fid, element)
        if not el:
            dropped += 1
            continue
        if sid not in known:                       # subcategory not in our CSF catalog
            dropped += 1
            continue
        m = mappings.setdefault(fid, {})
        m.setdefault(sid, {"targets": set(), "provenance": "official"})["targets"].add(el)

    print(f"CSF 2.0 informative references -> {len(mappings)} mapped frameworks\n")
    tgt_catalogs = {f: cat.load_controls(f) for f in mappings}
    for fid, m in sorted(mappings.items()):
        pairs = sum(len(v["targets"]) for v in m.values())
        have = tgt_catalogs.get(fid) or {}
        if have:
            allt = {t for v in m.values() for t in v["targets"]}
            hit = len({t for t in allt if t in have})
            join = f"{hit}/{len(allt)} target ids exist in our catalog"
        else:
            join = "MAPPING-ONLY — no control text (licence)" if fid in MAPPING_ONLY \
                   else "no catalog imported yet"
        print(f"  nist_csf2 -> {fid:<14} {len(m):>4} subcategories · {pairs:>5} mappings   {join}")

    if unknown:
        print(f"\n  not mapped to a registry framework ({len(unknown)} labels):")
        for k, v in sorted(unknown.items(), key=lambda kv: -kv[1])[:10]:
            print(f"    {v:>5}x  {k}")
    print(f"\n  dropped reference lines: {dropped}")

    if not a.write:
        print("\n(report only — re-run with --write)")
        return

    for fid, m in mappings.items():
        cat.save_mapping("nist_csf2", fid, m)
        print(f"wrote catalog/mappings/nist_csf2__{fid}.jsonl")


if __name__ == "__main__":
    main()
