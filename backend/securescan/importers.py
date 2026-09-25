"""
Ingest other scanners' reports (SecureScan Phase 2).

Rather than reimplement vulnerability detection, let a proven scanner find the vulns and ingest its
report here — then apply our layer (KEV/EPSS enrichment + NIST-control mapping). Supports:
  * Tenable Nessus  (.nessus XML)
  * OpenVAS / Greenbone GVM (report XML)
  * nuclei          (JSON or JSONL output)

Everything normalizes to a common finding:
  {source, host, name, severity, cvss, cve_ids: [...]}
Parsers are defensive and stdlib-only (xml.etree, json); a malformed file yields [] rather than a
crash.
"""
import json
import re
import xml.etree.ElementTree as ET
from typing import List

_SEV_FROM_NESSUS = {"0": "info", "1": "low", "2": "medium", "3": "high", "4": "critical"}
_CVE_RE = re.compile(r"CVE-\d{4}-\d{4,7}", re.I)


def _sev_from_cvss(cvss) -> str:
    try:
        c = float(cvss)
    except (TypeError, ValueError):
        return "info"
    if c >= 9.0:
        return "critical"
    if c >= 7.0:
        return "high"
    if c >= 4.0:
        return "medium"
    if c > 0:
        return "low"
    return "info"


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def parse_nessus(content: str) -> List[dict]:
    findings = []
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return findings
    for host in root.iter("ReportHost"):
        hostname = host.get("name") or ""
        for item in host.findall("ReportItem"):
            cves = [e.text.strip() for e in item.findall("cve") if e.text]
            cvss = None
            for tag in ("cvss3_base_score", "cvss_base_score"):
                el = item.find(tag)
                if el is not None and el.text:
                    cvss = _num(el.text)
                    break
            sev = _SEV_FROM_NESSUS.get(item.get("severity", "0"), "info")
            findings.append({"source": "nessus", "host": hostname,
                             "name": item.get("pluginName") or "", "severity": sev,
                             "cvss": cvss, "cve_ids": cves})
    return findings


def parse_openvas(content: str) -> List[dict]:
    findings = []
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return findings
    for res in root.iter("result"):
        host_el = res.find("host")
        host = (host_el.text or "").strip() if host_el is not None else ""
        name_el = res.find("name")
        name = (name_el.text or "").strip() if name_el is not None else ""
        sev_el = res.find("severity")
        cvss = _num(sev_el.text) if sev_el is not None else None
        cves = []
        for ref in res.iter("ref"):
            if (ref.get("type") or "").lower() == "cve" and ref.get("id"):
                cves.append(ref.get("id").strip())
        # fall back to scraping CVE ids from any text under the result
        if not cves:
            cves = sorted(set(m.group(0).upper() for m in _CVE_RE.finditer(ET.tostring(res, encoding="unicode"))))
        findings.append({"source": "openvas", "host": host, "name": name,
                         "severity": _sev_from_cvss(cvss), "cvss": cvss, "cve_ids": cves})
    return findings


def parse_nuclei(content: str) -> List[dict]:
    findings = []
    rows = []
    content = content.strip()
    if not content:
        return findings
    try:  # JSON array
        data = json.loads(content)
        rows = data if isinstance(data, list) else [data]
    except ValueError:  # JSONL
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    for r in rows:
        info = r.get("info", {}) if isinstance(r, dict) else {}
        classification = info.get("classification") or {}
        cves = classification.get("cve-id") or classification.get("cve_id") or []
        if isinstance(cves, str):
            cves = [cves]
        host = r.get("host") or r.get("matched-at") or r.get("matched_at") or ""
        findings.append({"source": "nuclei", "host": host,
                         "name": info.get("name") or r.get("template-id") or r.get("template_id") or "",
                         "severity": (info.get("severity") or "info").lower(),
                         "cvss": _num((classification.get("cvss-score") or classification.get("cvss_score"))),
                         "cve_ids": [c.upper() for c in cves if c]})
    return findings


def detect_and_parse(filename: str, content: str) -> dict:
    """Pick a parser by filename/content and return {format, findings}. Raises ValueError if the
    format isn't recognized."""
    name = (filename or "").lower()
    head = content.lstrip()[:400]
    if name.endswith(".nessus") or "NessusClientData" in head:
        return {"format": "nessus", "findings": parse_nessus(content)}
    if name.endswith(".json") or name.endswith(".jsonl") or head[:1] in "[{":
        return {"format": "nuclei", "findings": parse_nuclei(content)}
    if head.startswith("<"):
        # XML: distinguish Nessus vs OpenVAS by root/content
        if "NessusClientData" in content[:2000]:
            return {"format": "nessus", "findings": parse_nessus(content)}
        return {"format": "openvas", "findings": parse_openvas(content)}
    raise ValueError("unrecognized report format (expected .nessus / OpenVAS XML / nuclei JSON)")
