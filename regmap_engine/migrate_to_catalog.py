"""
One-time migration: pair-per-directory  ->  catalog (frameworks + mappings).

Reads every regmap_engine/crosswalks/<pair>/ directory and splits it into canonical framework catalogs
plus id-only mappings. See catalog.py for why.

The interesting part is CONFLICT RESOLUTION. The same control appears in several pair directories with
different text (verified: NIST 800-53 appeared in 2 pairs, 22 overlapping ids, 22 disagreements). We
cannot silently pick one, so each pair directory declares a trust tier and the highest tier wins:

    official import (provenance "official*")  >  human  >  model  >  sample

Ties break toward the longer text (fuller control statements beat truncated paraphrases). Every
conflict is reported so the choice is auditable rather than accidental.

    python regmap_engine/migrate_to_catalog.py            # report only, writes nothing
    python regmap_engine/migrate_to_catalog.py --write
"""
import argparse
import json
import re
from pathlib import Path

import catalog as cat

HERE = Path(__file__).resolve().parent
CROSSWALKS = HERE / "crosswalks"

# Map a pair directory's framework names onto stable framework ids. Extend as pairs are added.
FRAMEWORK_IDS = [
    (r"800-?53",                    "nist_80053"),
    (r"csf\s*2|cybersecurity fram", "nist_csf2"),
    (r"hipaa",                      "hipaa_security"),
    (r"800-?171",                   "nist_80171"),
    (r"27001",                      "iso_27001"),
    (r"pci",                        "pci_dss4"),
    (r"soc\s*2",                    "soc2"),
    (r"cis",                        "cis_v8"),
]

# The framework registry seeded on migration: what the product covers and what it intends to cover.
# `access` gates licensed content per tenant; `hub` marks a composition hub (roadmap §2.3).
SEED_REGISTRY = {
    "nist_80053":     dict(name="NIST SP 800-53 Rev.5", family="US federal", version="Rev.5",
                           access="public", hub=True,
                           license_note="NIST publications are U.S. Government works (public domain)."),
    "hipaa_security": dict(name="HIPAA Security Rule (45 CFR Part 164 Subpart C)", family="Healthcare",
                           version="2013", access="public",
                           license_note="US federal regulation (public domain)."),
    "nist_csf2":      dict(name="NIST CSF 2.0", family="US federal", version="2.0", access="public",
                           hub=True,
                           license_note="NIST publications are U.S. Government works (public domain)."),
    "nist_80171":     dict(name="NIST SP 800-171 Rev.3", family="US federal", version="Rev.3",
                           access="public",
                           license_note="NIST publications are U.S. Government works (public domain)."),
    "iso_27001":      dict(name="ISO/IEC 27001:2022", family="International", version="2022",
                           access="paraphrase-only",
                           license_note="ISO text is copyrighted: map control IDs + own paraphrase only."),
    "pci_dss4":       dict(name="PCI DSS 4.0", family="Payments", version="4.0",
                           access="paraphrase-only",
                           license_note="PCI SSC text is copyrighted: IDs + own paraphrase only."),
    "soc2":           dict(name="SOC 2 (Trust Services Criteria)", family="International",
                           version="2017 TSC", access="paraphrase-only",
                           license_note="AICPA TSC text is copyrighted: IDs + own paraphrase only."),
    "cis_v8":         dict(name="CIS Controls v8", family="International", version="8",
                           access="paraphrase-only",
                           license_note="CIS content requires attribution; check redistribution terms."),
    "hitrust_csf":    dict(name="HITRUST CSF", family="Healthcare", version="v11",
                           access="licence-required",
                           license_note="BLOCKED: proprietary. Acquire a HITRUST licence before shipping."),
    "cobit":          dict(name="COBIT 2019", family="International", version="2019",
                           access="licence-required",
                           license_note="BLOCKED: proprietary (ISACA). Acquire a licence before shipping."),
    "gdpr":           dict(name="GDPR", family="Privacy", version="2016/679", access="public",
                           license_note="EU regulation text is publicly available."),
    "fedramp":        dict(name="FedRAMP", family="US federal", version="Rev.5 baselines",
                           access="public", license_note="US Government work (public domain)."),
    "cmmc":           dict(name="CMMC 2.0", family="US federal", version="2.0", access="public",
                           license_note="US Government work (public domain)."),
}

TIER = {"official": 3, "human": 2, "model": 1, "sample": 0}


def fid_for(name):
    n = (name or "").lower()
    for pat, fid in FRAMEWORK_IDS:
        if re.search(pat, n):
            return fid
    return re.sub(r"[^a-z0-9]+", "_", n).strip("_") or None


def tier_of(meta):
    p = (meta.get("provenance") or "").lower()
    if "sample" in p:
        return TIER["sample"]
    for k, v in TIER.items():
        if k in p:
            return v
    return TIER["model"]


def title_of(text):
    """Pair files store 'Title: statement'; recover the title for display without losing the text."""
    head = (text or "").split(":", 1)[0].strip()
    return head if 0 < len(head) <= 90 else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="write the catalog (default: report only)")
    a = ap.parse_args()

    pairs = sorted(p for p in CROSSWALKS.iterdir() if (p / "meta.json").exists()) \
        if CROSSWALKS.is_dir() else []
    if not pairs:
        raise SystemExit("no pair directories found under crosswalks/")

    controls = {}   # fid -> id -> {"id","title","text","_tier","_from"}
    mappings = {}   # (a_fid, b_fid) -> {sid: {"targets": set, "provenance": str}}
    conflicts = []

    for d in pairs:
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        sf, tf = fid_for(meta.get("source_framework")), fid_for(meta.get("target_framework"))
        tier = tier_of(meta)
        if not sf or not tf:
            print(f"  ! skip {d.name}: cannot map framework names to ids")
            continue
        print(f"  {d.name}: {sf} -> {tf}  (trust tier {tier})")

        for side, fid in (("source", sf), ("corpus", tf)):
            f = d / f"{side}.jsonl"
            if not f.is_file():
                continue
            for r in (json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()):
                cid, text = r["id"], (r.get("text") or "").strip()
                cur = controls.setdefault(fid, {}).get(cid)
                cand = {"id": cid, "title": title_of(text), "text": text, "_tier": tier,
                        "_from": d.name}
                if cur is None:
                    controls[fid][cid] = cand
                elif cur["text"] != text:
                    # same control, two different statements — record and let trust tier decide
                    win = cand if (tier, len(text)) > (cur["_tier"], len(cur["text"])) else cur
                    conflicts.append((fid, cid, cur["_from"], d.name, win["_from"]))
                    controls[fid][cid] = win

        gf = d / "gold.jsonl"
        if gf.is_file():
            key = (sf, tf)
            m = mappings.setdefault(key, {})
            for r in (json.loads(l) for l in gf.read_text(encoding="utf-8").splitlines() if l.strip()):
                prov = r.get("provenance", "model")
                if "sample" in prov.lower():
                    prov = "sample"
                e = m.setdefault(r["source_id"], {"targets": set(), "provenance": prov})
                e["targets"].update(r["target_ids"])

    print(f"\nframework catalogs: {len(controls)}")
    for fid, cs in sorted(controls.items()):
        print(f"  {fid:<18} {len(cs):>4} controls")
    print(f"\nmappings: {len(mappings)}")
    for (x, y), m in sorted(mappings.items()):
        pairs_n = sum(len(v['targets']) for v in m.values())
        provs = sorted({v['provenance'] for v in m.values()})
        print(f"  {x} -> {y:<16} {len(m):>4} sources · {pairs_n:>4} mappings · {','.join(provs)}")

    if conflicts:
        print(f"\ntext conflicts resolved by trust tier: {len(conflicts)}")
        for fid, cid, f1, f2, win in conflicts[:5]:
            print(f"  {fid}:{cid}  {f1} vs {f2}  -> kept {win}")
        if len(conflicts) > 5:
            print(f"  … and {len(conflicts) - 5} more")

    if not a.write:
        print("\n(report only — re-run with --write to create the catalog)")
        return

    registry = {}
    for fid, seed in SEED_REGISTRY.items():
        registry[fid] = dict(seed)
    for fid in controls:                       # anything imported but unseeded still gets an entry
        registry.setdefault(fid, dict(name=fid, family="Unclassified", access="public",
                                      license_note=""))

    cat.CATALOG.mkdir(parents=True, exist_ok=True)
    cat.REGISTRY.write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8")
    for fid, cs in controls.items():
        cat.save_controls(fid, {k: {"id": v["id"], "title": v["title"], "text": v["text"]}
                                for k, v in cs.items()})
    for (x, y), m in mappings.items():
        cat.save_mapping(x, y, m)

    print(f"\nwrote {cat.CATALOG}")
    print(f"  frameworks.json      {len(registry)} registered")
    print(f"  frameworks/*/        {len(controls)} catalogs")
    print(f"  mappings/*.jsonl     {len(mappings)} mappings")


if __name__ == "__main__":
    main()
