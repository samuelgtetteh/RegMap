"""
NVD 2.0 API client — map a CPE / keyword to known CVEs.

Best-effort and cached:
  * Results are cached on disk (data/cache/nvd/) so repeat lookups are free and the tool works
    offline after a first run — important given NVD's aggressive rate limits.
  * Rate-limited politely (NVD allows ~5 requests / 30s without a key, ~50 with one). Set
    NVD_API_KEY to go faster.
  * Never raises: a network/parse failure returns an empty list with an error note, so a scan
    still produces a report (just without CVEs for that service).
"""
import hashlib
import json
import os
import time
from pathlib import Path
from typing import List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = Path(os.environ.get("NVD_CACHE_DIR", BASE_DIR / "data" / "cache" / "nvd"))
NVD_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
API_KEY = os.environ.get("NVD_API_KEY", "").strip()
CACHE_TTL = int(os.environ.get("NVD_CACHE_TTL", 7 * 24 * 3600))  # seconds
_MIN_INTERVAL = 0.6 if API_KEY else 6.0  # polite spacing between live calls
_last_call = [0.0]


def _cache_path(kind: str, value: str) -> Path:
    h = hashlib.sha1(f"{kind}:{value}".encode("utf-8")).hexdigest()[:20]
    return CACHE_DIR / f"{kind}_{h}.json"


def _read_cache(path: Path) -> Optional[list]:
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - blob.get("ts", 0) <= CACHE_TTL:
            return blob.get("cves")
    except (OSError, ValueError):
        pass
    return None


def _write_cache(path: Path, cves: list) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"ts": time.time(), "cves": cves}), encoding="utf-8")
    except OSError:
        pass


def _parse_cvss(cve: dict) -> tuple:
    """Extract (baseScore, severity, vector) preferring CVSS v3.1 > v3.0 > v2."""
    metrics = cve.get("metrics", {})
    for key in ("cvssMetricV31", "cvssMetricV30"):
        arr = metrics.get(key) or []
        if arr:
            data = arr[0].get("cvssData", {})
            return (data.get("baseScore"), data.get("baseSeverity"), data.get("vectorString"))
    arr = metrics.get("cvssMetricV2") or []
    if arr:
        data = arr[0].get("cvssData", {})
        return (data.get("baseScore"), arr[0].get("baseSeverity"), data.get("vectorString"))
    return (None, None, None)


def _normalize(data: dict, limit: int) -> List[dict]:
    out = []
    for vuln in data.get("vulnerabilities", [])[:limit]:
        cve = vuln.get("cve", {})
        cid = cve.get("id", "")
        descs = cve.get("descriptions", [])
        desc = next((d["value"] for d in descs if d.get("lang") == "en"), "")
        score, severity, vector = _parse_cvss(cve)
        out.append({
            "cve_id": cid,
            "description": desc[:300],
            "cvss_score": score,
            "severity": severity or _severity_from_score(score),
            "cvss_vector": vector,
            "url": f"https://nvd.nist.gov/vuln/detail/{cid}" if cid else None,
        })
    return out


def _severity_from_score(score) -> Optional[str]:
    if score is None:
        return None
    if score >= 9.0:
        return "CRITICAL"
    if score >= 7.0:
        return "HIGH"
    if score >= 4.0:
        return "MEDIUM"
    return "LOW"


def _request(params: dict, limit: int) -> List[dict]:
    """Perform one throttled NVD request. Returns [] on any failure. Requires `requests`."""
    try:
        import requests
    except Exception:
        return []
    # throttle
    wait = _MIN_INTERVAL - (time.time() - _last_call[0])
    if wait > 0:
        time.sleep(wait)
    headers = {"apiKey": API_KEY} if API_KEY else {}
    try:
        resp = requests.get(NVD_URL, params={**params, "resultsPerPage": limit},
                            headers=headers, timeout=30)
        _last_call[0] = time.time()
        resp.raise_for_status()
        return _normalize(resp.json(), limit)
    except Exception:
        return []


def lookup(mode: str, value: str, limit: int = 5, use_cache: bool = True) -> List[dict]:
    """Look up CVEs for a query. mode = 'cpe' (value is a cpeName) or 'keyword'."""
    if not value:
        return []
    path = _cache_path(mode, value)
    if use_cache:
        cached = _read_cache(path)
        if cached is not None:
            return cached[:limit]
    params = {"cpeName": value} if mode == "cpe" else {"keywordSearch": value}
    cves = _request(params, limit)
    if cves:
        _write_cache(path, cves)
    return cves
