"""
CVE enrichment — prioritize findings beyond CVSS (SecureScan Phase 2).

Adds two out-of-the-box signals to any set of CVE ids:
  * CISA KEV  — is this CVE in the Known-Exploited-Vulnerabilities catalog (actively exploited)?
  * EPSS      — FIRST's Exploit Prediction Scoring System probability (0-1) it will be exploited.
(OSV is exposed in the catalog for package/SBOM findings but not needed for host-CVE enrichment.)

Both are cached on disk and best-effort (never raise) so a scan still completes offline. This is a
lightweight, honest version of the "threat-aware prioritization" commercial scanners charge for.
"""
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Dict, List

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = Path(os.environ.get("SCAN_CACHE_DIR", BASE_DIR / "data" / "cache" / "enrich"))
KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
EPSS_URL = "https://api.first.org/data/v1/epss"
KEV_TTL = int(os.environ.get("KEV_TTL", 24 * 3600))
EPSS_TTL = int(os.environ.get("EPSS_TTL", 24 * 3600))
_kev_cache = {"ts": 0.0, "ids": None}


def _http_json(url: str, params: dict = None, timeout: int = 30):
    try:
        import requests
        r = requests.get(url, params=params or {}, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def _kev_disk() -> Path:
    return CACHE_DIR / "cisa_kev.json"


def _load_kev() -> set:
    """Set of CVE ids in the CISA KEV catalog (in-memory + disk cached; best-effort)."""
    now = time.time()
    if _kev_cache["ids"] is not None and now - _kev_cache["ts"] <= KEV_TTL:
        return _kev_cache["ids"]
    # disk cache
    try:
        blob = json.loads(_kev_disk().read_text(encoding="utf-8"))
        if now - blob.get("ts", 0) <= KEV_TTL:
            ids = set(blob.get("ids", []))
            _kev_cache.update(ts=now, ids=ids)
            return ids
    except (OSError, ValueError):
        pass
    data = _http_json(KEV_URL)
    ids = set()
    if data:
        for v in data.get("vulnerabilities", []):
            cid = v.get("cveID")
            if cid:
                ids.add(cid.upper())
    if ids:
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            _kev_disk().write_text(json.dumps({"ts": now, "ids": sorted(ids)}), encoding="utf-8")
        except OSError:
            pass
    _kev_cache.update(ts=now, ids=ids)
    return ids


def _epss_cache_path(cve: str) -> Path:
    return CACHE_DIR / f"epss_{hashlib.sha1(cve.encode()).hexdigest()[:16]}.json"


def _epss_scores(cve_ids: List[str]) -> Dict[str, float]:
    """EPSS probability per CVE (cached per id). Batches the uncached ones into one request."""
    out, need = {}, []
    now = time.time()
    for cid in cve_ids:
        p = _epss_cache_path(cid)
        try:
            blob = json.loads(p.read_text(encoding="utf-8"))
            if now - blob.get("ts", 0) <= EPSS_TTL:
                out[cid] = blob.get("epss")
                continue
        except (OSError, ValueError):
            pass
        need.append(cid)
    for i in range(0, len(need), 100):  # EPSS accepts a comma list
        batch = need[i:i + 100]
        data = _http_json(EPSS_URL, params={"cve": ",".join(batch)})
        got = {}
        if data:
            for row in data.get("data", []):
                try:
                    got[row["cve"]] = float(row["epss"])
                except (KeyError, TypeError, ValueError):
                    pass
        for cid in batch:
            score = got.get(cid)
            out[cid] = score
            try:
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                _epss_cache_path(cid).write_text(json.dumps({"ts": now, "epss": score}), encoding="utf-8")
            except OSError:
                pass
    return out


def enrich_cves(cve_ids: List[str]) -> Dict[str, dict]:
    """Return {cve_id: {in_kev: bool, epss: float|None}} for the given ids. Best-effort."""
    ids = sorted({c.upper() for c in cve_ids if c})
    if not ids:
        return {}
    kev = _load_kev()
    epss = _epss_scores(ids)
    return {cid: {"in_kev": cid in kev, "epss": epss.get(cid)} for cid in ids}


def risk_score(cvss, in_kev: bool, epss) -> float:
    """A blended priority score (0-100): CVSS-weighted, boosted by known-exploitation and EPSS.
    A poor-man's VPR so the queue surfaces what actually matters, not just high CVSS."""
    base = (cvss or 0.0) * 10.0            # 0-100 from CVSS
    if in_kev:
        base = max(base, 90.0)             # actively exploited -> floor high
    if epss:
        base += float(epss) * 20.0         # up to +20 from exploit probability
    return round(min(base, 100.0), 1)
