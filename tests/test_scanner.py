"""
Tests for SecureScan (asset discovery + CVE mapping). No nmap binary and no network required: the
socket engine is exercised against a real in-process listener, and NVD is stubbed/parsed from a
sample payload. The API is tested on a minimal app carrying only the scanner router, so the heavy
model load in backend/app.py is not triggered.
"""
import socket
import threading

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import scanner_api
from securescan import authz, catalog, cpe, discovery, enrich, importers, nvd
from securescan.engines.base import HostScan, PortFinding

_NESSUS = ('<NessusClientData_v2><Report name="r"><ReportHost name="10.0.0.5">'
           '<ReportItem port="443" severity="4" pluginID="1" pluginName="Log4Shell">'
           '<cve>CVE-2021-44228</cve><cvss3_base_score>10.0</cvss3_base_score>'
           '</ReportItem></ReportHost></Report></NessusClientData_v2>')
_OPENVAS = ('<report><results><result><host>10.0.0.6</host><name>SSH weak</name>'
            '<severity>7.5</severity><nvt><refs><ref type="cve" id="CVE-2020-1234"/></refs></nvt>'
            '</result></results></report>')
_NUCLEI = ('[{"template-id":"cve-2021-44228","host":"http://10.0.0.7","info":{"name":"Log4j",'
           '"severity":"critical","classification":{"cve-id":["CVE-2021-44228"]}}}]')


@pytest.fixture(scope="module")
def listener():
    """A localhost TCP listener on an ephemeral port, so the socket engine finds a real open port."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(8)
    port = srv.getsockname()[1]
    stop = threading.Event()

    def accept_loop():
        srv.settimeout(0.3)
        while not stop.is_set():
            try:
                c, _ = srv.accept()
                c.close()
            except OSError:
                pass

    t = threading.Thread(target=accept_loop, daemon=True)
    t.start()
    yield port
    stop.set()
    srv.close()


@pytest.fixture(scope="module")
def client():
    app = FastAPI()
    app.include_router(scanner_api.router)
    return TestClient(app)


# --- authorization guard ---------------------------------------------------------

def test_authz_allows_private_denies_public(monkeypatch):
    monkeypatch.delenv("SCAN_ALLOW_ANY", raising=False)
    monkeypatch.delenv("ALLOWED_SCAN_TARGETS", raising=False)
    assert authz.is_authorized("127.0.0.1")[0] is True
    assert authz.is_authorized("192.168.1.10")[0] is True
    assert authz.is_authorized("8.8.8.8")[0] is False


def test_authz_allow_any_opt_in(monkeypatch):
    monkeypatch.setenv("SCAN_ALLOW_ANY", "1")
    assert authz.is_authorized("8.8.8.8")[0] is True       # explicit cloud opt-in
    monkeypatch.setenv("SCAN_ALLOW_ANY", "0")
    assert authz.is_authorized("8.8.8.8")[0] is False


def test_authz_extra_allowlist(monkeypatch):
    monkeypatch.setenv("SCAN_ALLOW_ANY", "0")
    monkeypatch.setenv("ALLOWED_SCAN_TARGETS", "203.0.113.0/24")
    assert authz.is_authorized("203.0.113.5")[0] is True
    assert authz.is_authorized("203.0.114.5")[0] is False


# --- socket engine ---------------------------------------------------------------

def test_socket_scan_detects_open_port(listener):
    rep = discovery.scan_and_report("127.0.0.1", ports=[listener], engine="socket", with_cves=False)
    assert rep["up"] is True and rep["open_ports"] == 1
    assert rep["ports"][0]["port"] == listener


def test_scan_host_rejects_unauthorized(monkeypatch):
    monkeypatch.setenv("SCAN_ALLOW_ANY", "0")
    with pytest.raises(PermissionError):
        discovery.scan_host("8.8.8.8", ports=[80], engine="socket")


# --- CPE / NVD query building ----------------------------------------------------

def test_cpe_query_for():
    # a CPE from nmap -> cpe query
    q = cpe.query_for(PortFinding(port=22, cpe="cpe:/a:openbsd:openssh:8.9"))
    assert q["mode"] == "cpe" and q["value"].startswith("cpe:2.3:")
    # product + version -> keyword query
    q2 = cpe.query_for(PortFinding(port=80, service="http", product="nginx", version="1.18.0"))
    assert q2["mode"] == "keyword" and "nginx" in q2["value"]
    # a bare well-known service with no version -> too vague, no query
    assert cpe.query_for(PortFinding(port=80, service="http")) is None


# --- NVD response normalization (no network) -------------------------------------

def test_nvd_normalize_parses_cvss():
    sample = {"vulnerabilities": [{"cve": {
        "id": "CVE-2024-9999",
        "descriptions": [{"lang": "en", "value": "a sample flaw"}],
        "metrics": {"cvssMetricV31": [{"cvssData": {
            "baseScore": 9.8, "baseSeverity": "CRITICAL", "vectorString": "AV:N/AC:L"}}]},
    }}]}
    out = nvd._normalize(sample, 5)
    assert out[0]["cve_id"] == "CVE-2024-9999"
    assert out[0]["cvss_score"] == 9.8 and out[0]["severity"] == "CRITICAL"
    assert out[0]["url"].endswith("CVE-2024-9999")


# --- enrichment (NVD stubbed) ----------------------------------------------------

def test_enrich_flags_high_cvss(monkeypatch):
    monkeypatch.setattr(nvd, "lookup", lambda mode, value, limit=5, use_cache=True: [
        {"cve_id": "CVE-2024-0001", "description": "x", "cvss_score": 9.8,
         "severity": "CRITICAL", "cvss_vector": None, "url": None}])
    hs = HostScan(target="h", ip="192.168.0.5", up=True, engine="socket",
                  ports=[PortFinding(port=22, service="ssh", product="OpenSSH", version="7.4")])
    rep = discovery.enrich_with_cves(hs)
    assert rep["cve_total"] == 1 and rep["host_max_cvss"] == 9.8 and rep["flagged"] is True
    assert rep["ports"][0]["cves"][0]["cve_id"] == "CVE-2024-0001"


# --- API -------------------------------------------------------------------------

# --- Phase 2: engine catalog, importers, enrichment ---

def test_engine_catalog(client):
    d = client.get("/scan/catalog").json()
    kinds = {g["kind"] for g in d["catalog"]}
    assert {"discovery", "vuln", "import", "enrichment"} <= kinds
    disc = next(g for g in d["catalog"] if g["kind"] == "discovery")["engines"]
    assert any(e["id"] == "socket" and e["status"] == "ready" for e in disc)  # builtin always ready
    imp = next(g for g in d["catalog"] if g["kind"] == "import")["engines"]
    assert all(e["status"] == "ready" for e in imp)                            # import = upload a file
    assert d["summary"]["total"] >= 15 and d["summary"]["ready"] >= 3


def test_importers_parse_samples():
    n = importers.parse_nessus(_NESSUS)
    assert n and n[0]["host"] == "10.0.0.5" and "CVE-2021-44228" in n[0]["cve_ids"] and n[0]["severity"] == "critical"
    o = importers.parse_openvas(_OPENVAS)
    assert o and o[0]["host"] == "10.0.0.6" and "CVE-2020-1234" in o[0]["cve_ids"]
    u = importers.parse_nuclei(_NUCLEI)
    assert u and "CVE-2021-44228" in u[0]["cve_ids"] and u[0]["severity"] == "critical"
    # auto-detect
    assert importers.detect_and_parse("scan.nessus", _NESSUS)["format"] == "nessus"
    assert importers.detect_and_parse("out.json", _NUCLEI)["format"] == "nuclei"


def test_enrichment_mocked(monkeypatch, tmp_path):
    monkeypatch.setattr(enrich, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(enrich, "_kev_cache", {"ts": 0.0, "ids": None})

    def fake_http(url, params=None, timeout=30):
        if "known_exploited" in url:
            return {"vulnerabilities": [{"cveID": "CVE-2021-44228"}]}
        return {"data": [{"cve": "CVE-2021-44228", "epss": "0.97"}]}
    monkeypatch.setattr(enrich, "_http_json", fake_http)
    out = enrich.enrich_cves(["CVE-2021-44228", "CVE-2000-0001"])
    assert out["CVE-2021-44228"]["in_kev"] is True and out["CVE-2021-44228"]["epss"] == 0.97
    assert out["CVE-2000-0001"]["in_kev"] is False
    # risk: KEV floors high, EPSS adds on top
    assert enrich.risk_score(10.0, True, 0.97) >= 90 and enrich.risk_score(2.0, False, None) == 20.0


def test_import_endpoint_enriches(client, monkeypatch):
    monkeypatch.setattr(scanner_api.enrich, "enrich_cves",
                        lambda ids: {"CVE-2021-44228": {"in_kev": True, "epss": 0.97}})
    r = client.post("/scan/import", json={"filename": "scan.nessus", "content": _NESSUS})
    assert r.status_code == 200
    b = r.json()
    assert b["format"] == "nessus" and b["count"] == 1 and b["kev_count"] == 1
    f = b["findings"][0]
    assert f["in_kev"] is True and f["risk"] >= 90
    assert client.post("/scan/import", json={"filename": "x.txt", "content": "not a report"}).status_code == 400


def test_api_scan_and_authz(client, listener, monkeypatch):
    monkeypatch.setenv("SCAN_ALLOW_ANY", "0")
    # a scan of an authorized target with an open port
    r = client.post("/scan", json={"target": "127.0.0.1", "ports": str(listener),
                                    "engine": "socket", "with_cves": False, "record": False})
    assert r.status_code == 200 and r.json()["open_ports"] == 1
    # authorization check endpoint
    assert client.get("/scan/authorize", params={"target": "8.8.8.8"}).json()["authorized"] is False
    # scanning an unauthorized target is refused
    assert client.post("/scan", json={"target": "8.8.8.8", "engine": "socket",
                                       "with_cves": False, "record": False}).status_code == 403
    # engines endpoint reports the always-available socket engine
    assert "socket" in client.get("/scan/engines").json()["engines"]
