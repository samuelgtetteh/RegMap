"""
Turn a discovered service into something the NVD can be queried with.

Two query strategies:
  * If the engine gave us a CPE (nmap does), query NVD by cpeName — the precise path.
  * Otherwise (socket engine, or nmap without a CPE) fall back to an NVD keyword search built from
    product/service + version.

The heuristics are intentionally conservative: a keyword search with too little signal (e.g. just
"http") is noisy, so `query_for` returns None when there isn't enough to make a useful query.
"""
import re
from typing import Optional


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def query_for(finding) -> Optional[dict]:
    """Return {'mode': 'cpe'|'keyword', 'value': ...} for an NVD lookup, or None if the finding is
    too vague to query usefully. `finding` is a PortFinding (or a dict-like with the same keys)."""
    get = finding.get if isinstance(finding, dict) else lambda k, d="": getattr(finding, k, d)
    cpe = _clean(get("cpe", ""))
    if cpe.startswith("cpe:"):
        # NVD 2.0 wants a 2.3 formatted string; nmap sometimes emits 2.2 ("cpe:/a:..."). Convert.
        return {"mode": "cpe", "value": _to_cpe23(cpe)}
    product = _clean(get("product", ""))
    version = _clean(get("version", ""))
    service = _clean(get("service", ""))
    # A product name (optionally + version) is a decent keyword; a bare well-known service isn't.
    base = product or (service if service and version else "")
    if not base:
        return None
    kw = f"{base} {version}".strip()
    if len(kw) < 3:
        return None
    return {"mode": "keyword", "value": kw}


def _to_cpe23(cpe: str) -> str:
    """Best-effort CPE 2.2 -> 2.3 conversion; passes through if already 2.3."""
    if cpe.startswith("cpe:2.3:"):
        return cpe
    if cpe.startswith("cpe:/"):
        # cpe:/a:vendor:product:version -> cpe:2.3:a:vendor:product:version:*:*:*:*:*:*:*
        parts = cpe[len("cpe:/"):].split(":")
        parts += ["*"] * (11 - len(parts))
        return "cpe:2.3:" + ":".join(parts[:11])
    return cpe
