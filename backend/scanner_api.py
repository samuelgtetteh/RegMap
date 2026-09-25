"""
SecureScan API (Phase 1): expose asset discovery + CVE mapping over HTTP, wired into the same app
as the detectors. Findings are recorded to the verdict store (model="scan") so they show up in the
live decisioning trail.

Endpoints (prefix /scan):
  POST /scan            — discover a host, map CVEs, return the report (and record it by default)
  GET  /scan/engines    — which scan engines are usable here + the authorization posture
  GET  /scan/authorize  — check whether a given target is authorized to scan (without scanning)

Safety: every scan passes through scanner.authz — loopback/private by default, anything else only
with an explicit opt-in (SCAN_ALLOW_ANY). An unauthorized target returns 403, not a scan.
"""
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from securescan import authz, catalog, discovery, engines, enrich, importers

router = APIRouter(prefix="/scan", tags=["securescan"])


def _parse_ports(spec: Optional[str]) -> Optional[List[int]]:
    """Parse '22,80,443' or '1-1024' (or a mix) into a sorted unique port list. None -> engine default."""
    if not spec:
        return None
    out: set = set()
    for token in spec.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            lo, hi = token.split("-", 1)
            out.update(range(int(lo), int(hi) + 1))
        else:
            out.add(int(token))
    return sorted(p for p in out if 0 < p <= 65535)


class ScanRequest(BaseModel):
    target: str = Field(..., description="host or IP to scan (must be authorized)")
    ports: Optional[str] = Field(None, description="e.g. '22,80,443' or '1-1024'; default = engine's common set")
    engine: str = Field("auto", description="auto | socket | nmap")
    with_cves: bool = Field(True, description="map discovered services to CVEs via NVD")
    max_per_service: int = Field(5, ge=1, le=20, description="max CVEs per service")
    record: bool = Field(True, description="record the scan to the verdict trail (model=scan)")
    timeout: float = Field(0.7, gt=0, le=10, description="per-port connect timeout (seconds)")
    delay: float = Field(0.0, ge=0, le=5, description="polite delay between ports (seconds)")


@router.post("")
def run_scan(req: ScanRequest):
    """Discover a single host, optionally map CVEs, and return the report. 403 if the target is
    not authorized; 400 on a bad engine / port spec."""
    try:
        ports = _parse_ports(req.ports)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid ports spec (use '22,80' or '1-1024')")
    target = "".join((req.target or "").split())  # tolerate stray whitespace in the target
    try:
        report = discovery.scan_and_report(
            target, ports=ports, engine=req.engine, with_cves=req.with_cves,
            max_per_service=req.max_per_service, timeout=req.timeout, delay=req.delay)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except engines.EngineUnavailable as e:
        raise HTTPException(status_code=400, detail=str(e))
    if req.with_cves:
        _enrich_report(report)
    if req.record:
        report["verdict_id"] = discovery.record_report(report)
    return report


def _enrich_report(report: dict) -> None:
    """Attach CISA KEV + EPSS + a blended risk score to every CVE in a scan report (in place)."""
    ids = [c["cve_id"] for p in report.get("ports", []) for c in (p.get("cves") or []) if c.get("cve_id")]
    if not ids:
        return
    enr = enrich.enrich_cves(ids)
    host_max_risk = 0.0
    for p in report.get("ports", []):
        for c in (p.get("cves") or []):
            e = enr.get((c.get("cve_id") or "").upper(), {})
            c["in_kev"] = e.get("in_kev", False)
            c["epss"] = e.get("epss")
            c["risk"] = enrich.risk_score(c.get("cvss_score"), c["in_kev"], c["epss"])
            host_max_risk = max(host_max_risk, c["risk"])
    report["host_max_risk"] = host_max_risk
    report["kev_count"] = sum(1 for p in report.get("ports", []) for c in (p.get("cves") or []) if c.get("in_kev"))


@router.get("/catalog")
def scan_catalog():
    """The full scan-engine catalog (all recommended engines) with per-engine availability and
    how-to-enable — so the UI can list every option honestly. See also GET /scan/engines for the
    engines currently executable for a direct scan."""
    return {"catalog": catalog.describe(), "summary": catalog.summary()}


class ImportReq(BaseModel):
    filename: str = Field("", description="original filename (helps detect the format)")
    content: str = Field(..., description="the report file's text content")


@router.post("/import")
def import_report(req: ImportReq):
    """Ingest another scanner's report (Nessus .nessus / OpenVAS XML / nuclei JSON), normalize the
    findings, and enrich the CVEs with KEV + EPSS + a blended risk score. This is the bridge to
    proven scanners: they find the vulns, we prioritize and (via the advisor) map to controls."""
    try:
        parsed = importers.detect_and_parse(req.filename, req.content or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    findings = parsed["findings"]
    all_ids = sorted({c for f in findings for c in f.get("cve_ids", [])})
    enr = enrich.enrich_cves(all_ids) if all_ids else {}
    kev_total = 0
    for f in findings:
        kevs = [c for c in f.get("cve_ids", []) if enr.get(c.upper(), {}).get("in_kev")]
        epss_vals = [enr.get(c.upper(), {}).get("epss") or 0.0 for c in f.get("cve_ids", [])]
        f["in_kev"] = bool(kevs)
        f["epss"] = max(epss_vals) if epss_vals else None
        f["risk"] = enrich.risk_score(f.get("cvss"), f["in_kev"], f["epss"])
        kev_total += len(kevs)
    findings.sort(key=lambda f: f.get("risk", 0), reverse=True)
    return {"format": parsed["format"], "count": len(findings), "cve_count": len(all_ids),
            "kev_count": kev_total, "findings": findings}


@router.get("/engines")
def scan_engines():
    """Engines usable in this environment + the current authorization posture."""
    return {"engines": engines.available(), "default": engines.get_engine("auto").NAME,
            "authorization": authz.describe()}


@router.get("/authorize")
def check_authorization(target: str = Query(..., description="host or IP")):
    """Whether `target` may be scanned here (does not scan)."""
    ok, reason = authz.is_authorized(target)
    return {"target": target, "authorized": ok, "reason": reason}
