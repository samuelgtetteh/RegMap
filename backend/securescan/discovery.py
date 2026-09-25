"""
SecureScan orchestration: discover -> map CVEs -> report -> record.

Ties the pieces together:
  1. authz gate (never scan an unauthorized target),
  2. a pluggable engine discovers open ports/services,
  3. each service is turned into an NVD query (cpe / keyword) and enriched with CVEs,
  4. the result is a structured report, optionally recorded to the verdict store as model="scan"
     so it flows through the same Record -> Decide -> Act -> dashboard platform as the detectors.
"""
import concurrent.futures
import ipaddress
from datetime import datetime, timezone
from typing import List, Optional

from . import authz, cpe, nvd, engines


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def scan_host(target: str, ports: Optional[List[int]] = None, engine: str = "auto",
              timeout: float = 0.7, delay: float = 0.0, banner: bool = True):
    """Authorize + run one host discovery. Returns a HostScan. Raises PermissionError if the
    target is not authorized (the caller maps that to 403)."""
    ip = authz.assert_authorized(target)
    eng = engines.get_engine(engine)
    return eng.scan(target, ip=ip, ports=ports, timeout=timeout, delay=delay, banner=banner)


def scan_network(target: str, engine: str = "auto", ports: Optional[List[int]] = None,
                 timeout: float = 0.6, max_hosts: int = 256, deep: bool = False) -> dict:
    """Discovery for a single host OR a CIDR range — the one engine that feeds both the
    vulnerability view and compliance mapping. Returns a raw scan_report (no CVEs yet;
    analyze.analyze() adds CVEs + KEV/EPSS + control mapping). Caller must authorize `target`.

    Single host -> uses the requested engine (nmap gives versions for good CVE lookups).
    Range       -> threaded socket connect-scan for discovery. When `deep` is set AND nmap is
                   available, each DISCOVERED host is then re-scanned with nmap on its open ports
                   to add product/version/CPE — so a whole subnet yields CVEs, not just ports."""
    single = target
    try:
        net = ipaddress.ip_network(target, strict=False)
        is_range = net.num_addresses > 1
        if not is_range:
            single = str(net.network_address)   # a bare IP or /32 -> the host itself
    except ValueError:
        is_range = False                          # a hostname

    if not is_range:
        hs = scan_host(single, ports=ports, engine=engine, timeout=timeout)
        svcs = [{"port": p.port, "service": p.service, "product": p.product,
                 "version": p.version, "cpe": p.cpe} for p in hs.ports]
        return {"cidr": None, "ip": hs.ip, "engine": hs.engine, "up": hs.up,
                "ports": [p.dict() for p in hs.ports],
                "hosts_scanned": 1, "hosts_found": 1 if hs.up else 0,
                "results": [{"ip": hs.ip, "open_ports": [p.port for p in hs.ports], "services": svcs}]}

    sock = engines.get_engine("socket")   # range discovery uses the dependency-free connect scan
    all_hosts = [str(h) for h in net.hosts()][:max_hosts]
    results = []

    deep_ok = False
    if deep:
        try:
            engines.get_engine("nmap")   # only deep-scan if nmap is actually available
            deep_ok = True
        except Exception:
            deep_ok = False

    def _one(ip):
        hs = sock.scan(ip, ip=ip, ports=ports, timeout=timeout, banner=False)
        if not (hs.up and hs.ports):
            return None
        found = [p.port for p in hs.ports]
        if deep_ok:
            try:  # re-scan just the discovered ports with nmap for versions/CPE
                dh = scan_host(ip, ports=found, engine="nmap", timeout=max(timeout, 1.0))
                return {"ip": ip, "open_ports": [p.port for p in dh.ports],
                        "services": [{"port": p.port, "service": p.service, "product": p.product,
                                      "version": p.version, "cpe": p.cpe} for p in dh.ports]}
            except Exception:
                pass   # fall back to the socket-level result for this host
        return {"ip": ip, "open_ports": found,
                "services": [{"port": p.port, "service": p.service} for p in hs.ports]}

    with concurrent.futures.ThreadPoolExecutor(max_workers=(12 if deep_ok else 64)) as ex:
        for r in ex.map(_one, all_hosts):
            if r:
                results.append(r)
    return {"cidr": str(net), "engine": "nmap" if deep_ok else "socket", "deep": deep_ok,
            "hosts_scanned": len(all_hosts), "hosts_found": len(results), "results": results}


def enrich_with_cves(hostscan, max_per_service: int = 5, use_cache: bool = True) -> dict:
    """Attach CVEs to each discovered port and compute host-level risk. Returns a report dict."""
    ports_out = []
    host_max = None
    cve_total = 0
    for pf in hostscan.ports:
        q = cpe.query_for(pf)
        cves = nvd.lookup(q["mode"], q["value"], limit=max_per_service, use_cache=use_cache) if q else []
        scores = [c["cvss_score"] for c in cves if c.get("cvss_score") is not None]
        pmax = max(scores) if scores else None
        if pmax is not None:
            host_max = pmax if host_max is None else max(host_max, pmax)
        cve_total += len(cves)
        row = pf.dict()
        row.update({"query": q, "cve_count": len(cves), "max_cvss": pmax, "cves": cves})
        ports_out.append(row)
    return {
        "target": hostscan.target, "ip": hostscan.ip, "engine": hostscan.engine,
        "up": hostscan.up, "scanned_at": _now(), "error": hostscan.error,
        "ports": ports_out, "open_ports": len(ports_out),
        "cve_total": cve_total, "host_max_cvss": host_max,
        "flagged": bool(host_max is not None and host_max >= 7.0),  # high/critical present
    }


def scan_and_report(target: str, ports: Optional[List[int]] = None, engine: str = "auto",
                    with_cves: bool = True, max_per_service: int = 5,
                    timeout: float = 0.7, delay: float = 0.0, use_cache: bool = True) -> dict:
    """Full pipeline: discover, and (optionally) enrich with CVEs. Returns the report."""
    hostscan = scan_host(target, ports=ports, engine=engine, timeout=timeout, delay=delay)
    if not with_cves:
        report = {"target": hostscan.target, "ip": hostscan.ip, "engine": hostscan.engine,
                  "up": hostscan.up, "scanned_at": _now(), "error": hostscan.error,
                  "ports": [p.dict() for p in hostscan.ports], "open_ports": len(hostscan.ports),
                  "cve_total": 0, "host_max_cvss": None, "flagged": False}
    else:
        report = enrich_with_cves(hostscan, max_per_service=max_per_service, use_cache=use_cache)
    return report


def record_report(report: dict) -> Optional[int]:
    """Record the scan as a verdict (model="scan") so it appears in the live trail/dashboard.
    Flagged when a high/critical CVE is present; score = the host's max CVSS. Best-effort."""
    try:
        from verdict_store import record_verdict_safe
    except Exception:
        return None
    top = []
    for p in report.get("ports", []):
        for c in (p.get("cves") or [])[:2]:
            top.append({"port": p["port"], "service": p.get("service"),
                        "cve_id": c["cve_id"], "cvss": c.get("cvss_score")})
    detail = {
        "ip": report.get("ip"), "engine": report.get("engine"),
        "open_ports": report.get("open_ports"), "cve_total": report.get("cve_total"),
        "host_max_cvss": report.get("host_max_cvss"),
        "services": [f"{p['port']}/{p.get('service') or '?'}" for p in report.get("ports", [])],
        "top_cves": top[:10],
    }
    return record_verdict_safe(model="scan", flagged=report.get("flagged", False),
                               score=report.get("host_max_cvss"), subject=report.get("ip"),
                               detail=detail)
