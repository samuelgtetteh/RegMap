"""
RegMap catalog — the hub-and-spoke control graph behind "all compliance in one place".

WHY THIS EXISTS
The original data model was one directory per framework *pair*, each carrying its own private copy of
both frameworks' control text (source.jsonl + corpus.jsonl). That does not scale to a full catalog:

  * N frameworks need up to N*(N-1)/2 pair directories (20 frameworks -> 190).
  * Each pair re-states the control text, so one framework ends up with many divergent copies. This
    already happened: NIST 800-53 appeared in two pairs with 22 overlapping IDs and *all 22* had
    different text. For an auditability product, that is the value proposition inverted.

So control text lives ONCE per framework, and mappings reference controls by id:

    catalog/
      frameworks.json                    registry: id, name, version, family, licence, access
      frameworks/<fid>/controls.jsonl    {"id","title","text"}          — canonical, one per framework
      mappings/<a>__<b>.jsonl            {"source_id","target_ids","provenance"}

Any framework pair is then answerable three ways, in this precedence order:
  1. DIRECT     — an official mapping a->b exists.
  2. INVERTED   — an official mapping b->a exists; invert it.
  3. COMPOSED   — no direct mapping, but a->H and H->b exist for some hub H (NIST OLIR / SCF).
                  This is what makes breadth cheap: add one mapping to the hub, gain a pair with
                  every other framework already on it.
Composed mappings are tagged provenance="derived" and are NEVER presented as authoritative.

`as_pair()` returns the (meta, source, corpus, gold) tuple the existing evaluator and API already
consume, so eval_crosswalk.py and serve.py keep working against the new model unchanged.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CATALOG = HERE / "catalog"
REGISTRY = CATALOG / "frameworks.json"
FRAMEWORKS = CATALOG / "frameworks"
MAPPINGS = CATALOG / "mappings"

# Provenance ranking — how much an auditor should trust a mapping. Used to pick a winner when more
# than one route exists, and surfaced to the UI so users see why a mapping is there.
PROVENANCE_RANK = {"official": 3, "human": 2, "model": 1, "derived": 1, "sample": 0}


def _jsonl(p):
    return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def _write_jsonl(p, rows):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


# ---- registry ------------------------------------------------------------------------------------
def load_registry():
    """All known frameworks, whether or not their catalog is populated yet.

    A framework is listed even with 0 controls: the registry is the product's coverage roadmap, and
    the UI uses `controls`==0 to render "coming soon" instead of silently promising coverage.
    """
    if not REGISTRY.is_file():
        return {}
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    for fid, f in reg.items():
        f["id"] = fid
        f["controls"] = len(load_controls(fid))
    return reg


def framework(fid):
    return load_registry().get(fid)


def load_controls(fid):
    """Canonical control catalog for one framework: {id: {"id","title","text"}}."""
    p = FRAMEWORKS / fid / "controls.jsonl"
    if not p.is_file():
        return {}
    return {r["id"]: r for r in _jsonl(p)}


def save_controls(fid, controls):
    _write_jsonl(FRAMEWORKS / fid / "controls.jsonl",
                 [controls[k] for k in sorted(controls)])


# ---- mappings ------------------------------------------------------------------------------------
def mapping_path(a, b):
    return MAPPINGS / f"{a}__{b}.jsonl"


def load_mapping(a, b):
    """Mapping a->b as {source_id: {"targets": set, "provenance": str}}, or None.

    Tries the direct file, then inverts b->a. Inversion is lossless for set-valued mappings and is
    how one official export serves both directions (the bidirectional requirement in the roadmap).
    """
    p = mapping_path(a, b)
    if p.is_file():
        out = {}
        for r in _jsonl(p):
            e = out.setdefault(r["source_id"], {"targets": set(), "provenance": r.get("provenance", "model")})
            e["targets"].update(r["target_ids"])
        return out
    rp = mapping_path(b, a)
    if rp.is_file():
        out = {}
        for r in _jsonl(rp):
            for t in r["target_ids"]:
                e = out.setdefault(t, {"targets": set(), "provenance": r.get("provenance", "model")})
                e["targets"].add(r["source_id"])
        return out
    return None


def save_mapping(a, b, mapping, provenance="official"):
    _write_jsonl(mapping_path(a, b), [
        {"source_id": s, "target_ids": sorted(v["targets"] if isinstance(v, dict) else v),
         "provenance": (v.get("provenance", provenance) if isinstance(v, dict) else provenance)}
        for s, v in sorted(mapping.items())])


def available_mappings():
    """Every mapping file on disk, as (a, b) framework-id tuples."""
    if not MAPPINGS.is_dir():
        return []
    out = []
    for p in sorted(MAPPINGS.glob("*__*.jsonl")):
        a, _, b = p.stem.partition("__")
        if a and b:
            out.append((a, b))
    return out


def hubs():
    """Framework ids flagged as mapping hubs (NIST OLIR, SCF), most-connected first."""
    reg = load_registry()
    hs = [fid for fid, f in reg.items() if f.get("hub")]
    conn = {h: sum(1 for a, b in available_mappings() if h in (a, b)) for h in hs}
    return sorted(hs, key=lambda h: -conn[h])


def compose(a, b, hub):
    """Derive a->b by routing through `hub`. Returns a mapping dict or None.

    For each control in `a`, take its hub controls, then the union of what those hub controls map to
    in `b`. Correctness depends entirely on the two official legs; the result is advisory, so it is
    tagged provenance="derived" and carries the route for display.
    """
    leg1, leg2 = load_mapping(a, hub), load_mapping(hub, b)
    if not leg1 or not leg2:
        return None
    out = {}
    for sid, e1 in leg1.items():
        targets = set()
        for h in e1["targets"]:
            if h in leg2:
                targets.update(leg2[h]["targets"])
        if targets:
            out[sid] = {"targets": targets, "provenance": "derived", "via": hub}
    return out or None


def resolve(a, b):
    """Best available mapping a->b. Returns (mapping, route) where route is 'direct'|'inverted'|
    'derived via <hub>', or (None, None) if the pair is unreachable."""
    if mapping_path(a, b).is_file():
        return load_mapping(a, b), "direct"
    if mapping_path(b, a).is_file():
        return load_mapping(a, b), "inverted"
    for h in hubs():
        if h in (a, b):
            continue
        m = compose(a, b, h)
        if m:
            return m, f"derived via {h}"
    return None, None


def has_text(fid):
    """Can this framework be searched semantically, or only crosswalked by identifier?

    Copyrighted frameworks (ISO 27001, PCI DSS, CIS, SCF) arrive as *mappings only*: NIST's OLIR
    crosswalk is a US Government work so the correspondence is freely usable, but the control text is
    not ours to ship. Such a framework has ids and official mappings but no statements to embed.
    """
    return bool(load_controls(fid))


def reachable_pairs(include_mapping_only=False):
    """Every (a, b, route) the product can answer today — direct, inverted, or hub-composed.

    This is the honest coverage number for the UI: it counts what actually resolves, not what the
    registry aspires to.

    By default only pairs where both frameworks have control text, i.e. pairs that can be *ranked*.
    With include_mapping_only=True, also returns pairs whose target is mapping-only: those cannot be
    ranked, but their official mappings are still lookup-able by control id — which is most of the
    value for an auditor asking "which ISO clause covers this?".
    """
    reg = load_registry()
    full = [f for f in reg if has_text(f)]
    targets = full if not include_mapping_only else list(reg)
    out = []
    for a in full:            # the source must have text: you look up *from* a real control
        for b in targets:
            if a == b:
                continue
            m, route = resolve(a, b)
            if m:
                out.append((a, b, route))
    return out


def mapping_only_pairs():
    """Pairs answerable by official mapping alone, because the target has no shippable text."""
    return [(a, b, r) for a, b, r in reachable_pairs(include_mapping_only=True)
            if not has_text(b)]


def official_targets(a, b, source_id):
    """The authoritative mapping for one control, without needing the target's text.

    This is the path that makes mapping-only frameworks usable: it answers "what does <control> map to
    in <framework>?" straight from the official crosswalk, returning identifiers only.
    Returns (target_ids, route), or (None, None) if the pair has no route at all.
    """
    m, route = resolve(a, b)
    if m is None:
        return None, None
    entry = m.get(source_id)
    if not entry:
        return [], route
    targets = sorted(entry["targets"])
    known = load_controls(b)
    if known:                 # when we hold the target catalog, restrict to ids we actually have
        targets = [t for t in targets if t in known]
    return targets, route


# ---- compatibility shim: present a catalog pair the way the old format did ------------------------
def as_pair(a, b):
    """(meta, source, corpus, gold) — drop-in replacement for eval_crosswalk.load_pair().

    Lets the existing evaluator and API consume the catalog with no changes: `source` is framework a's
    controls, `corpus` is framework b's, `gold` is the resolved mapping restricted to both catalogs.
    """
    reg = load_registry()
    ca, cb = load_controls(a), load_controls(b)
    if not ca or not cb:
        raise KeyError(f"framework catalog empty or missing: {a if not ca else b}")
    m, route = resolve(a, b)
    if m is None:
        raise KeyError(f"no mapping and no hub route from '{a}' to '{b}'")

    source = {cid: c["text"] for cid, c in ca.items()}
    corpus = {cid: c["text"] for cid, c in cb.items()}
    gold = {}
    for sid, e in m.items():
        if sid not in source:
            continue
        t = {x for x in e["targets"] if x in corpus}
        if t:
            gold[sid] = t

    provs = {e.get("provenance", "model") for e in m.values()}
    meta = {
        "source_framework": reg.get(a, {}).get("name", a),
        "target_framework": reg.get(b, {}).get("name", b),
        "source_id": a, "target_id": b,
        "description": f"{reg.get(a,{}).get('name',a)} -> {reg.get(b,{}).get('name',b)} ({route}).",
        "provenance": min(provs, key=lambda p: PROVENANCE_RANK.get(p, 0)) if provs else "model",
        "route": route,
        "direction": "source -> target",
        "license_note": reg.get(b, {}).get("license_note", ""),
    }
    return meta, source, corpus, gold


if __name__ == "__main__":  # quick inspection: what does the product cover right now?
    reg = load_registry()
    print(f"{len(reg)} frameworks registered · "
          f"{sum(1 for f in reg.values() if f['controls'])} with a populated catalog\n")
    for fid, f in sorted(reg.items(), key=lambda kv: (-kv[1]["controls"], kv[0])):
        state = f"{f['controls']:>5} controls" if f["controls"] else "    — not yet imported"
        print(f"  {fid:<22} {state}   {f.get('access','public'):<8} {f['name']}")
    print(f"\nmappings on disk: {len(available_mappings())}")
    for a, b in available_mappings():
        print(f"  {a} -> {b}")
    rp = reachable_pairs()
    print(f"\nanswerable pairs: {len(rp)}")
    for a, b, route in rp:
        print(f"  {a} -> {b}   [{route}]")
