"""
Tests for the on-prem agent path: create a token-scoped job, agent fetches its config, submits
results (token-authenticated), console polls for completion. Control mapping is stubbed so no
embedder load is needed.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import agent_api as AG


@pytest.fixture(scope="module")
def client():
    app = FastAPI()
    app.include_router(AG.router)
    return TestClient(app)


def test_agent_job_lifecycle(client, monkeypatch):
    monkeypatch.setattr(AG, "_map_controls", lambda sr: {
        "cidr": sr.get("cidr"),
        "hosts": [{"ip": h["ip"], "categories": h.get("categories", []),
                   "recommended_controls": {}} for h in sr.get("results", [])]})
    created = client.post("/agent/jobs", json={"label": "office", "target": "auto"}).json()
    jid, tok = created["job_id"], created["token"]
    assert created["status"] == "pending" and "powershell" in created["commands"]

    # config is token-gated
    assert client.get(f"/agent/jobs/{jid}/config", params={"token": "wrong"}).status_code == 403
    assert client.get(f"/agent/jobs/{jid}/config", params={"token": tok}).json()["target"] == "auto"

    report = {"cidr": "192.168.1.0/24", "hosts_found": 1, "results": [
        {"ip": "192.168.1.5", "open_ports": [445],
         "services": [{"port": 445, "service": "smb", "category": "file_share"}],
         "categories": ["file_share"]}]}
    # submitting requires the right token
    assert client.post(f"/agent/jobs/{jid}/results",
                       json={"token": "wrong", "scan_report": report}).status_code == 403
    r = client.post(f"/agent/jobs/{jid}/results", json={"token": tok, "scan_report": report}).json()
    assert r["ok"] and r["hosts_found"] == 1

    # console poll -> complete, includes mapped controls, never the token
    s = client.get(f"/agent/jobs/{jid}").json()
    assert s["status"] == "complete" and s["hosts_found"] == 1
    assert s["recommendations"]["hosts"][0]["ip"] == "192.168.1.5" and "token" not in s
    assert client.get("/agent/jobs/999").status_code == 404


def test_agent_script_downloadable(client):
    a = client.get("/agent/agent.py")
    assert a.status_code == 200 and "def scan(" in a.text and "SecureScan agent" in a.text
