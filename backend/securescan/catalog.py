"""
Scan-engine catalog (SecureScan Phase 2).

Rather than reimplement a vulnerability scanner, SecureScan orchestrates best-of-breed engines and
ingests other scanners' output, then adds the layer that is our own contribution (CVE->NIST 800-53
control mapping + KEV/EPSS prioritization + the compliance advisor).

This module is the single source of truth for WHICH engines exist, WHAT each is for, and WHETHER
it is usable in the current environment (binary/lib present) with clear "how to enable" guidance —
so the UI can list every option and honestly show its status. Engines that need an external binary
are detected via shutil.which; nothing is faked as available.
"""
import shutil

from .engines import nmap_scan


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


# kind: discovery | vuln | cloud | passive | import | enrichment
# status is computed by describe(): 'ready' (usable now) or 'install' (needs the requirement).
_CATALOG = [
    # --- discovery ---
    {"id": "socket", "name": "Built-in TCP connect scan", "kind": "discovery",
     "builtin": True, "requires": None,
     "note": "Pure-Python, no dependencies; runs anywhere (incl. the agent). Low-noise."},
    {"id": "nmap", "name": "Nmap (service/version + CPE)", "kind": "discovery",
     "check": lambda: nmap_scan.is_available(), "requires": "the nmap binary + python-nmap",
     "enable": "install nmap (nmap.org / apt install nmap) — it's already in the Docker image",
     "note": "Richer service/version detection and CPE strings for precise CVE lookups."},
    {"id": "masscan", "name": "Masscan (fast port sweep)", "kind": "discovery",
     "check": lambda: _have("masscan"), "requires": "the masscan binary",
     "enable": "apt install masscan (or build from robertdavidgraham/masscan)",
     "note": "Very fast large-range port discovery; hand off open ports to nmap for detail."},
    {"id": "naabu", "name": "naabu (ProjectDiscovery port scan)", "kind": "discovery",
     "check": lambda: _have("naabu"), "requires": "the naabu binary",
     "enable": "go install github.com/projectdiscovery/naabu/v2/cmd/naabu@latest",
     "note": "Fast, scriptable port discovery."},
    {"id": "rustscan", "name": "RustScan (fast discovery -> nmap)", "kind": "discovery",
     "check": lambda: _have("rustscan"), "requires": "the rustscan binary",
     "enable": "install rustscan (github.com/RustScan/RustScan)",
     "note": "Fast port discovery that pipes results into nmap."},
    # --- vuln ---
    {"id": "nuclei", "name": "nuclei (templated vuln checks)", "kind": "vuln",
     "check": lambda: _have("nuclei"), "requires": "the nuclei binary",
     "enable": "go install github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest",
     "note": "Community templates for real, targeted vulnerability checks (HTTP-centric)."},
    {"id": "grype", "name": "Grype (SBOM -> CVEs)", "kind": "vuln",
     "check": lambda: _have("grype"), "requires": "the grype binary (+ syft for SBOMs)",
     "enable": "install grype (anchore.com/grype)",
     "note": "Maps installed software / SBOM to CVEs with zero network probing."},
    # --- cloud posture ---
    {"id": "prowler", "name": "Prowler (cloud posture)", "kind": "cloud",
     "check": lambda: _have("prowler"), "requires": "the prowler CLI + cloud credentials",
     "enable": "pip install prowler; configure AWS/Azure/GCP credentials",
     "note": "Control-plane posture checks across AWS/Azure/GCP."},
    {"id": "scoutsuite", "name": "ScoutSuite (multi-cloud audit)", "kind": "cloud",
     "check": lambda: _have("scout"), "requires": "ScoutSuite + cloud credentials",
     "enable": "pip install scoutsuite; configure cloud credentials",
     "note": "Multi-cloud security posture assessment."},
    # --- passive (safe for fragile OT/ICS) ---
    {"id": "zeek", "name": "Zeek (passive traffic analysis)", "kind": "passive",
     "check": lambda: _have("zeek"), "requires": "the zeek binary + a SPAN/mirror port",
     "enable": "install zeek (zeek.org); feed it mirrored traffic",
     "note": "Sends NO packets to targets — the safe option for fragile OT/ICS networks."},
    {"id": "p0f", "name": "p0f (passive OS fingerprinting)", "kind": "passive",
     "check": lambda: _have("p0f"), "requires": "the p0f binary",
     "enable": "apt install p0f",
     "note": "Fingerprints hosts from observed traffic; sends nothing."},
    # --- import (ingest another scanner's report — always available: upload a file) ---
    {"id": "import_nessus", "name": "Import Nessus report (.nessus)", "kind": "import",
     "builtin": True, "requires": None,
     "note": "Ingest a Tenable Nessus scan and map its findings to controls + KEV/EPSS."},
    {"id": "import_openvas", "name": "Import OpenVAS / GVM report (XML)", "kind": "import",
     "builtin": True, "requires": None,
     "note": "Ingest a Greenbone/OpenVAS report and map its findings."},
    {"id": "import_nuclei", "name": "Import nuclei output (JSON/JSONL)", "kind": "import",
     "builtin": True, "requires": None,
     "note": "Ingest nuclei results and map them."},
    # --- enrichment (out-of-the-box; HTTP, cached) ---
    {"id": "nvd", "name": "NVD CVE lookup", "kind": "enrichment", "builtin": True, "requires": None,
     "note": "Maps discovered service versions/CPEs to CVEs (set NVD_API_KEY for higher limits)."},
    {"id": "cisa_kev", "name": "CISA KEV (known-exploited)", "kind": "enrichment",
     "builtin": True, "requires": "internet access",
     "note": "Flags CVEs that are being actively exploited in the wild."},
    {"id": "epss", "name": "EPSS (exploit probability)", "kind": "enrichment",
     "builtin": True, "requires": "internet access",
     "note": "FIRST EPSS score: probability a CVE will be exploited — prioritize beyond CVSS."},
    {"id": "osv", "name": "OSV.dev (open-source vulns)", "kind": "enrichment",
     "builtin": True, "requires": "internet access",
     "note": "Vulnerabilities for open-source packages (pairs with SBOM/Grype)."},
]

_KIND_ORDER = ["discovery", "vuln", "cloud", "passive", "import", "enrichment"]
_KIND_LABEL = {"discovery": "Discovery", "vuln": "Vulnerability", "cloud": "Cloud posture",
               "passive": "Passive (OT-safe)", "import": "Import external scanner",
               "enrichment": "Enrichment / prioritization"}


def _status(e: dict) -> str:
    if e.get("builtin"):
        return "ready"
    try:
        return "ready" if e["check"]() else "install"
    except Exception:
        return "install"


def describe() -> list:
    """Grouped catalog with per-engine status, for the UI."""
    groups = {k: [] for k in _KIND_ORDER}
    for e in _CATALOG:
        groups[e["kind"]].append({
            "id": e["id"], "name": e["name"], "kind": e["kind"], "status": _status(e),
            "requires": e.get("requires"), "enable": e.get("enable"), "note": e.get("note"),
        })
    return [{"kind": k, "label": _KIND_LABEL[k], "engines": groups[k]} for k in _KIND_ORDER if groups[k]]


def summary() -> dict:
    """Counts of ready vs install-needed, for a quick headline."""
    ready = install = 0
    for e in _CATALOG:
        if _status(e) == "ready":
            ready += 1
        else:
            install += 1
    return {"ready": ready, "needs_install": install, "total": len(_CATALOG)}
