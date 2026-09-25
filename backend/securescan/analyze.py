"""
Shared analysis core — the single pipeline both the vulnerability view and the compliance view use.

Given a scan report from ANY discovery source (SecureScan's socket/nmap engines, the on-prem agent,
or an imported scanner), this produces one unified result:
  * per-host ports -> CVEs (NVD) enriched with CISA KEV + EPSS + a blended risk score, and
  * a service/port -> NIST-category derivation feeding control_mapper for 800-53 recommendations.

This is what lets SecureScan "feed its output to compliance mapping": one scan, one analysis, two
views (vulnerabilities and controls). Retires the duplicate control-advisor network scanner.
"""
import sys
from pathlib import Path

from . import cpe, enrich, nvd

# make control_mapper importable (control-advisor toolkit)
_CA = Path(__file__).resolve().parent.parent.parent / "control-advisor" / "scanner"
if _CA.is_dir() and str(_CA) not in sys.path:
    sys.path.insert(0, str(_CA))

# port/service -> control-advisor category, so discovered assets can drive control_mapper
_PORT_CAT = {
    21: "file_share", 22: "remote_access", 23: "remote_access", 25: "email", 53: "network_service",
    80: "web", 110: "email", 135: "windows", 139: "file_share", 143: "email", 389: "directory",
    443: "web", 445: "file_share", 636: "directory", 1433: "database", 1521: "database",
    3306: "database", 3389: "remote_access", 5432: "database", 5900: "remote_access",
    6379: "database", 8000: "web", 8080: "web", 8443: "web", 9200: "database", 11211: "database",
    27017: "database", 161: "network_service", 5985: "remote_access", 2375: "windows",
}
_SVC_CAT = {
    "http": "web", "https": "web", "http-alt": "web", "http-proxy": "web", "https-alt": "web",
    "ssh": "remote_access", "telnet": "remote_access", "rdp": "remote_access",
    "ms-wbt-server": "remote_access", "vnc": "remote_access", "wsman": "remote_access",
    "smb": "file_share", "microsoft-ds": "file_share", "netbios-ssn": "file_share", "ftp": "file_share",
    "nfs": "file_share", "mysql": "database", "postgresql": "database", "ms-sql-s": "database",
    "oracle": "database", "redis": "database", "mongodb": "database", "elasticsearch": "database",
    "memcached": "database", "smtp": "email", "imap": "email", "pop3": "email", "submission": "email",
    "ldap": "directory", "ldaps": "directory", "domain": "network_service", "dns": "network_service",
    "snmp": "network_service", "msrpc": "windows",
}


def category_for(port, service):
    return _PORT_CAT.get(port) or _SVC_CAT.get((service or "").lower())


def _iter_hosts(scan_report: dict) -> list:
    """Normalize either shape into [{ip, ports:[{port,service,product,version,cpe}]}]:
      * multi-host (agent / network scan): scan_report['results'] with services/open_ports
      * single-host (SecureScan): scan_report['ip'] + scan_report['ports']"""
    hosts = []
    results = scan_report.get("results")
    if results is not None:
        for r in results:
            ports = []
            for s in r.get("services", []) or []:
                ports.append({"port": s.get("port"), "service": s.get("service", ""),
                              "product": s.get("product", ""), "version": s.get("version", ""),
                              "cpe": s.get("cpe", "")})
            if not ports:
                for p in r.get("open_ports", []) or []:
                    ports.append({"port": p, "service": "", "product": "", "version": "", "cpe": ""})
            hosts.append({"ip": r.get("ip"), "ports": ports,
                          "categories": r.get("categories", []) or []})   # cloud carries these directly
    elif scan_report.get("ports") is not None:
        hosts.append({"ip": scan_report.get("ip"), "ports": scan_report["ports"], "categories": []})
    return hosts


def analyze(scan_report: dict, with_cves: bool = True, max_per_service: int = 3) -> dict:
    """Turn a scan report into {hosts(ports+cves), categories, recommendations, cve_total,
    kev_count, host_max_risk}. Best-effort; never raises on the enrichment/mapping side."""
    hosts = _iter_hosts(scan_report)
    all_ids, out_hosts = [], []
    for h in hosts:
        cats, ports_out = set(h.get("categories") or []), []
        for p in h["ports"]:
            c = category_for(p.get("port"), p.get("service"))
            if c:
                cats.add(c)
            cves = []
            if with_cves:
                q = cpe.query_for(p)
                if q:
                    cves = nvd.lookup(q["mode"], q["value"], limit=max_per_service)
                    all_ids.extend(cv["cve_id"] for cv in cves if cv.get("cve_id"))
            ports_out.append({**p, "category": c, "cves": cves})
        out_hosts.append({"ip": h.get("ip"), "categories": sorted(cats), "ports": ports_out})

    enr = enrich.enrich_cves(all_ids) if all_ids else {}
    total = kev = 0
    max_risk = 0.0
    for h in out_hosts:
        for p in h["ports"]:
            for cv in p["cves"]:
                e = enr.get((cv.get("cve_id") or "").upper(), {})
                cv["in_kev"] = e.get("in_kev", False)
                cv["epss"] = e.get("epss")
                cv["risk"] = enrich.risk_score(cv.get("cvss_score"), cv["in_kev"], cv["epss"])
                total += 1
                kev += 1 if cv["in_kev"] else 0
                max_risk = max(max_risk, cv["risk"])

    categories = sorted({c for h in out_hosts for c in h["categories"]})
    recommendations = {"cidr": scan_report.get("cidr"), "hosts": []}
    try:
        import control_mapper
        recommendations = control_mapper.recommend_for_scan(
            {"cidr": scan_report.get("cidr"),
             "results": [{"ip": h["ip"], "categories": h["categories"]} for h in out_hosts]})
    except Exception:
        pass

    return {"hosts": out_hosts, "categories": categories, "recommendations": recommendations,
            "cve_total": total, "kev_count": kev, "host_max_risk": max_risk}
