"""
Import a NIST OSCAL catalog (JSON) into the RegMap framework catalog.

NIST publishes machine-readable, public-domain OSCAL catalogs at
https://github.com/usnistgov/oscal-content — SP 800-53, SP 800-171, SP 800-172, SP 800-218, CSF 2.0.
This importer turns one into `catalog/frameworks/<fid>/controls.jsonl`.

It also extracts the mapping that some catalogs carry implicitly: SP 800-171 Rev 3 links every
requirement to the SP 800-53 controls that satisfy it, via `links[rel=reference]` pointing at
back-matter resources whose titles ARE 800-53 control ids. That yields an official 800-171 -> 800-53
mapping for free, with `--map-to`.

    python import_oscal.py --infile data/raw/oscal/nist_80053_rev5.json --fid nist_80053
    python import_oscal.py --infile data/raw/oscal/nist_80171_rev3.json --fid nist_80171 \
        --map-to nist_80053

ID CANONICALISATION is the fiddly part and the whole reason mappings join at all. The same control is
written `ac-2` in OSCAL, `AC-02` in back-matter titles, `AC-2` in the OLIR crosswalk CSV, and
`AC-2(3)` vs `ac-2.3` vs `AC-02(03)` for enhancements. Everything is normalised to the OLIR/human form
(`AC-2`, `AC-2(3)`) so ids imported from different sources refer to the same control.
"""
import argparse
import json
import re
from pathlib import Path

import catalog as cat


# ---- id canonicalisation -------------------------------------------------------------------------
def canon_id(raw, family=None):
    """Normalise a control id to the human/OLIR form: AC-2, AC-2(3), 03.01.01, GV.OC-01."""
    s = str(raw or "").strip()
    if not s:
        return ""
    # SP 800-171 OSCAL ids: SP_800_171_03.01.01 -> 03.01.01
    m = re.match(r"^SP_800_171_(.+)$", s)
    if m:
        return m.group(1)
    # already a CSF-style id (GV.OC-01) — leave alone
    if re.match(r"^[A-Z]{2}\.[A-Z]{2}-\d+$", s):
        return s
    # dotted numeric (800-171 style) — leave alone
    if re.match(r"^\d+\.\d+\.\d+$", s):
        return s
    # 800-53 family: ac-2 / ac-2.3 / AC-02 / AC-02(03) -> AC-2 / AC-2(3)
    m = re.match(r"^([A-Za-z]{2})[-_]?0*(\d+)(?:[.(]0*(\d+)\)?)?$", s)
    if m:
        fam, num, enh = m.group(1).upper(), int(m.group(2)), m.group(3)
        return f"{fam}-{num}({int(enh)})" if enh else f"{fam}-{num}"
    return s


# ---- OSCAL traversal ----------------------------------------------------------------------------
def clean_prose(s):
    """Strip OSCAL markup that would otherwise be embedded as if it were control language.

    OSCAL leaves parameter placeholders inline as `{{ insert: param, ac-01_odp.01 }}`. Embedding that
    literally adds meaningless tokens to every control and dilutes the signal, so it is replaced with
    the human phrasing NIST's own crosswalk exports use ("[Assignment: organization-defined]").
    """
    s = re.sub(r"\{\{\s*insert:\s*param[^}]*\}\}", "[Assignment: organization-defined]", s or "")
    s = re.sub(r"\[\s*Assignment:\s*organization-defined\s*\]"
               r"(\s*\[\s*Assignment:\s*organization-defined\s*\])+",
               "[Assignment: organization-defined]", s)   # collapse runs of adjacent placeholders
    return re.sub(r"\s+", " ", s).strip()


def _prose(parts, want="statement", depth=0):
    """Flatten an OSCAL control statement. Statements nest (statement -> item -> item), and the
    useful text is spread across levels, so collect prose depth-first in document order."""
    out = []
    for p in parts or []:
        if depth == 0 and p.get("name") != want:
            continue
        if p.get("prose"):
            t = clean_prose(p["prose"])
            if t:
                out.append(t)
        out.extend(_prose(p.get("parts"), want, depth + 1))
    return out


def _controls(node, out, include_enhancements):
    """Walk groups/controls. Nested controls are enhancements (AC-2(1) lives inside AC-2)."""
    for c in node.get("controls", []) or []:
        out.append(c)
        if include_enhancements:
            _controls(c, out, include_enhancements)
    for g in node.get("groups", []) or []:
        _controls(g, out, include_enhancements)
    return out


def load_catalog(path, include_enhancements=True):
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    cata = doc.get("catalog", doc)
    raw = _controls(cata, [], include_enhancements)
    back = {r["uuid"]: r for r in (cata.get("back-matter", {}) or {}).get("resources", [])}
    return cata, raw, back


def title_of(c):
    t = (c.get("title") or "").strip()
    # CSF 2.0 sets title == id for subcategories; the real label is the statement, so drop the echo
    return "" if t == (c.get("id") or "").strip() else t


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--infile", required=True)
    ap.add_argument("--fid", required=True, help="framework id in the registry")
    ap.add_argument("--map-to", help="also extract link-derived mappings to this framework id")
    ap.add_argument("--no-enhancements", action="store_true",
                    help="skip control enhancements (AC-2(1) etc.)")
    ap.add_argument("--write", action="store_true", help="write (default: report only)")
    a = ap.parse_args()

    cata, raw, back = load_catalog(a.infile, not a.no_enhancements)
    print(f"OSCAL: {cata.get('metadata',{}).get('title','?')}")
    print(f"  {len(raw)} control nodes · {len(back)} back-matter resources")

    controls, skipped = {}, 0
    for c in raw:
        cid = canon_id(c.get("id"))
        text = " ".join(_prose(c.get("parts")))
        if not cid or not text:
            skipped += 1
            continue
        t = title_of(c)
        controls[cid] = {"id": cid, "title": t,
                         "text": f"{t}: {text}" if t else text}

    print(f"  -> {len(controls)} controls with statements ({skipped} nodes had none)")
    for cid in list(controls)[:3]:
        print(f"     {cid:<12} {controls[cid]['text'][:78]}")

    # ---- link-derived mapping (800-171 -> 800-53) ------------------------------------------------
    mapping = {}
    if a.map_to:
        for c in raw:
            sid = canon_id(c.get("id"))
            if sid not in controls:
                continue
            targets = set()
            for l in c.get("links", []) or []:
                if l.get("rel") != "reference":
                    continue
                res = back.get(str(l.get("href", "")).lstrip("#"))
                if not res:
                    continue
                tid = canon_id(res.get("title"))
                # only keep things that look like a control id of the target framework
                if re.match(r"^[A-Z]{2}-\d+(\(\d+\))?$", tid):
                    targets.add(tid)
            if targets:
                mapping[sid] = {"targets": targets, "provenance": "official"}
        pairs = sum(len(v["targets"]) for v in mapping.values())
        print(f"  -> mapping {a.fid} -> {a.map_to}: {len(mapping)} sources · {pairs} mappings")
        for sid in list(mapping)[:3]:
            print(f"     {sid:<12} -> {sorted(mapping[sid]['targets'])[:6]}")

    if not a.write:
        print("\n(report only — re-run with --write)")
        return

    cat.save_controls(a.fid, controls)
    print(f"\nwrote catalog/frameworks/{a.fid}/controls.jsonl  ({len(controls)} controls)")
    if mapping:
        cat.save_mapping(a.fid, a.map_to, mapping)
        print(f"wrote catalog/mappings/{a.fid}__{a.map_to}.jsonl")


if __name__ == "__main__":
    main()
