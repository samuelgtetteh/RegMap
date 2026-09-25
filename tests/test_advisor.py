"""
Tests for the Compliance Advisor API (control-advisor wrapped over HTTP). Runs on a minimal app
carrying only the advisor router (no heavy model load). Scanning + the embedder are stubbed; the
real prioritization + DOCX/XLSX/JSON report builders are exercised end to end (no LLM).
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import advisor_api as A


@pytest.fixture(scope="module")
def client():
    app = FastAPI()
    app.include_router(A.router)
    return TestClient(app)


def test_health_available(client):
    h = client.get("/advisor/health").json()
    assert h["available"] is True


def test_base_questions(client):
    d = client.get("/advisor/questions").json()
    ids = [q["id"] for q in d["questions"]]
    assert ids == ["sector", "regulated_data", "internet_facing", "maturity"]
    assert d["business_name"]["type"] == "text"
    # regulated_data is multi-select and carries option descriptions
    rd = next(q for q in d["questions"] if q["id"] == "regulated_data")
    assert rd["multi"] is True and len(rd["options"]) >= 2


def test_followups_are_adaptive_subset(client):
    allids = {q["id"] for q in A.ca_interview.FOLLOWUP_QUESTIONS}
    r = client.post("/advisor/followups", json={
        "answers": {"sector": "healthcare", "regulated_data": ["phi"], "internet_facing": "yes"},
        "categories": ["database", "web", "remote_access"]})
    ids = [q["id"] for q in r.json()["questions"]]
    assert set(ids) <= allids                       # only real follow-ups, evaluated server-side
    if ids:                                          # answering one removes it from the next batch
        one = ids[0]
        r2 = client.post("/advisor/followups", json={
            "answers": {"regulated_data": ["phi"], one: "yes"},
            "categories": ["database", "web", "remote_access"]})
        assert one not in [q["id"] for q in r2.json()["questions"]]


def test_providers_physical_first(client):
    provs = client.get("/advisor/providers").json()["providers"]
    assert provs[0]["id"] == "physical" and provs[0]["implemented"] is True
    ids = {p["id"] for p in provs}
    assert {"aws", "azure", "gcp"} <= ids
    assert next(p for p in provs if p["id"] == "azure")["implemented"] is False


def test_expanded_questions(client):
    ids = [q["id"] for q in client.get("/advisor/questions?expanded=true").json()["questions"]]
    assert "deployment_model" in ids and "has_ot_ics" in ids and "cloud_providers" in ids
    # base set (non-expanded) does not include them
    base = [q["id"] for q in client.get("/advisor/questions").json()["questions"]]
    assert "deployment_model" not in base


def test_interpret_freetext_answers(client):
    # plain-English answers resolve to structured option values via the embedder (no LLM)
    r = client.post("/advisor/interpret", json={"responses": {
        "business_name": "Acme Medical Clinic",
        "sector": "we are a small medical clinic that keeps patient charts",
        "regulated_data": "we store patient health records and take credit card payments"}})
    res = r.json()["results"]
    assert res["business_name"]["value"] == "Acme Medical Clinic" and res["business_name"]["method"] == "text"
    assert res["sector"]["value"] == "healthcare"
    assert isinstance(res["regulated_data"]["value"], list) and "phi_hipaa" in res["regulated_data"]["value"]


def test_conversational_interview_flow(client, monkeypatch):
    monkeypatch.setattr(A, "_warm_llm", lambda: None)     # don't load the real model in tests
    monkeypatch.setattr(A, "_llm", lambda *a, **k: None)  # no model -> canonical question text
    monkeypatch.setattr(A.ca_semantic, "interpret",
                        lambda text, descs, multi=False: (([text] if multi else text), {"method": "exact_match"}))
    st = client.post("/advisor/interview/start", json={"categories": []}).json()
    sid = st["session_id"]
    assert st["current_field"] == "business_name" and st["done"] is False and st["message"]
    r = client.post("/advisor/interview/reply", json={"session_id": sid, "text": "Acme Clinic"}).json()
    assert r["current_field"] == "sector" and r["captured"]["business_name"] == "Acme Clinic"
    done = None
    for _ in range(30):
        rr = client.post("/advisor/interview/reply", json={"session_id": sid, "text": "no"}).json()
        if rr.get("done"):
            done = rr
            break
    assert done is not None, "interview should terminate"
    ctx = done["context"]
    assert ctx["business_name"] == "Acme Clinic"
    for f in ["sector", "regulated_data", "internet_facing", "maturity", "deployment_model",
              "cloud_providers", "has_ot_ics"]:
        assert f in ctx, f"{f} should have been gathered"


def test_interview_clarifies_once_then_advances(client, monkeypatch):
    monkeypatch.setattr(A, "_warm_llm", lambda: None)
    monkeypatch.setattr(A, "_llm", lambda *a, **k: None)
    monkeypatch.setattr(A.ca_semantic, "interpret",
                        lambda text, descs, multi=False: ("unsure", {"method": "semantic_low_confidence", "score": 0.1}))
    sid = client.post("/advisor/interview/start", json={}).json()["session_id"]
    client.post("/advisor/interview/reply", json={"session_id": sid, "text": "Acme"})  # -> sector
    r = client.post("/advisor/interview/reply", json={"session_id": sid, "text": "dunno"}).json()
    assert r.get("clarifying") is True and r["current_field"] == "sector"   # unclear -> clarify
    r2 = client.post("/advisor/interview/reply", json={"session_id": sid, "text": "still dunno"}).json()
    assert r2.get("clarifying") is not True   # second time accepted, no infinite clarify loop


def test_unimplemented_provider_501(client):
    assert client.post("/advisor/scan", json={"provider": "azure"}).status_code == 501


def test_template_only_report_no_scan(client, tmp_path, monkeypatch):
    monkeypatch.setattr(A, "REPORTS_DIR", tmp_path)
    answers = {"business_name": "Acme", "sector": "healthcare", "regulated_data": ["phi"],
               "internet_facing": "yes", "maturity": "developing", "deployment_model": "hybrid",
               "cloud_providers": ["aws", "azure"], "has_ot_ics": "yes"}
    r = client.post("/advisor/report", json={"answers": answers, "with_language": False})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["files"].get("docx") and b["files"].get("json")           # docs generated without a scan
    assert "hybrid" in b["environment_profile"]["summary"] and b["environment_profile"]["has_ot_ics"] is True


_FAKE_ANALYSIS = {"hosts": [{"ip": "127.0.0.1", "categories": ["web"], "ports": []}],
                  "categories": ["web"], "cve_total": 0, "kev_count": 0, "host_max_risk": 0.0,
                  "recommendations": {"cidr": None, "hosts": [
                      {"ip": "127.0.0.1", "categories": ["web"],
                       "recommended_controls": {"web": [{"control_id": "SC-7", "control_text": "x", "score": 0.8}]}}]}}


def test_scan_uses_securescan_and_maps_controls(client, monkeypatch):
    # /advisor/scan now runs SecureScan's engine then the shared analyzer (retired the duplicate scanner)
    monkeypatch.setattr(A.sdiscovery, "scan_network",
                        lambda *a, **k: {"cidr": None, "results": [{"ip": "127.0.0.1"}]})
    monkeypatch.setattr(A.sanalyze, "analyze", lambda sr, **k: dict(_FAKE_ANALYSIS))
    r = client.post("/advisor/scan", json={"target": "127.0.0.1"})
    assert r.status_code == 200
    body = r.json()
    assert body["recommendations"]["hosts"][0]["ip"] == "127.0.0.1"     # controls
    assert "cve_total" in body and "hosts" in body                       # vulns view too
    monkeypatch.delenv("SCAN_ALLOW_ANY", raising=False)
    assert client.post("/advisor/scan", json={"target": "8.8.8.8"}).status_code == 403


def test_advisor_ingest_securescan_output(client, monkeypatch):
    # the Advisor can ingest a scan report produced elsewhere (SecureScan / agent) and analyze it
    monkeypatch.setattr(A.sanalyze, "analyze", lambda sr, **k: dict(_FAKE_ANALYSIS))
    r = client.post("/advisor/ingest", json={"scan_report": {"results": [{"ip": "127.0.0.1"}]}})
    assert r.status_code == 200
    b = r.json()
    assert b["recommendations"]["hosts"][0]["ip"] == "127.0.0.1" and "categories" in b


def test_report_generation_and_download(client, tmp_path, monkeypatch):
    monkeypatch.setattr(A, "REPORTS_DIR", tmp_path)
    scan_report = {"cidr": "192.168.0.0/30", "hosts_found": 1, "results": [
        {"ip": "192.168.0.2", "hostname": "web01", "mac_address": None, "vendor": None,
         "response_time_ms": 5, "open_ports": [80], "device_type_guess": "server",
         "services": [{"port": 80, "service": "http", "category": "web"}], "categories": ["web"]}]}
    rec = {"cidr": "192.168.0.0/30", "hosts": [
        {"ip": "192.168.0.2", "categories": ["web"],
         "recommended_controls": {"web": [{"control_id": "SC-7",
                                           "control_text": "Boundary protection", "score": 0.82}]}}]}
    answers = {"business_name": "Acme Clinic", "sector": "healthcare", "regulated_data": ["phi"],
               "internet_facing": "yes", "maturity": "developing"}
    r = client.post("/advisor/report", json={"scan_report": scan_report, "recommendations": rec,
                                             "answers": answers, "with_language": False})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["llm_used"] is False and isinstance(body["rows"], list)
    assert body["files"].get("docx") and body["files"].get("xlsx") and body["files"].get("json")
    rid = body["report_id"]
    for fmt in ("docx", "xlsx", "json"):
        d = client.get(f"/advisor/report/{rid}/{fmt}")
        assert d.status_code == 200 and len(d.content) > 100
    assert client.get(f"/advisor/report/{rid}/pdf").status_code == 404
