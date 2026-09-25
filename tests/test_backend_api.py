"""End-to-end tests for the live scoring API, driven through FastAPI's
TestClient so they exercise the real routers, models, and validation.

The identity tests pin an explicit timestamp so the score doesn't depend on
what hour of what day the suite happens to run.
"""
import pytest
from fastapi.testclient import TestClient

# A fixed normal-business-hours moment (a Monday afternoon), so time-derived
# features are deterministic across runs.
FIXED_TS = "2024-01-15T14:30:00Z"


@pytest.fixture(scope="module")
def client():
    import app
    return TestClient(app.app)


# --- RegMap /map ---------------------------------------------------------

def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_map_returns_five_scored_results(client):
    r = client.post("/map", json={"nist_control": "access control policy"})
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 5
    assert all("hipaa_citation" in item and "score" in item for item in body)
    # scores should be sorted high-to-low (topk order)
    scores = [item["score"] for item in body]
    assert scores == sorted(scores, reverse=True)


def test_map_rejects_empty_text(client):
    r = client.post("/map", json={"nist_control": "   "})
    assert r.status_code == 400


def test_map_rejects_oversized_text(client):
    r = client.post("/map", json={"nist_control": "x" * 6000})
    assert r.status_code == 422


# --- Identity /identity/score -------------------------------------------

def test_identity_normal_login_not_anomalous(client):
    r = client.post("/identity/score", json={
        "src_user": "U1@DOM1", "src_pc": "C1", "auth_type": "Kerberos",
        "logon_type": "Network", "orientation": "LogOn", "success": "Success",
        "timestamp": FIXED_TS,
    })
    assert r.status_code == 200
    assert r.json()["is_anomaly"] is False


def test_identity_unknown_auth_type_is_anomalous(client):
    # An auth_type absent from the trained vocabulary maps to the unknown code
    # the model never saw during training, which is what should trip the alert.
    r = client.post("/identity/score", json={
        "src_user": "ANONYMOUS LOGON@C9999", "src_pc": "C1",
        "auth_type": "TotallyMadeUpAuthType", "logon_type": "RemoteInteractive",
        "orientation": "LogOn", "success": "Fail", "timestamp": FIXED_TS,
    })
    assert r.status_code == 200
    assert r.json()["is_anomaly"] is True


# --- Identity rolling-window counters ------------------------------------

def test_identity_hourly_count_accumulates_within_window(client):
    base = {"src_user": "WIN_A@DOM1", "src_pc": "C1", "auth_type": "Kerberos",
            "logon_type": "Network", "orientation": "LogOn", "success": "Success"}
    r1 = client.post("/identity/score", json={**base, "timestamp": "2024-03-01T10:00:00Z"})
    r2 = client.post("/identity/score", json={**base, "timestamp": "2024-03-01T10:15:00Z"})
    assert r1.json()["hourly_count"] == 1
    assert r2.json()["hourly_count"] == 2


def test_identity_unique_pcs_counts_distinct_within_window(client):
    base = {"src_user": "WIN_B@DOM1", "auth_type": "Kerberos", "logon_type": "Network",
            "orientation": "LogOn", "success": "Success"}
    client.post("/identity/score", json={**base, "src_pc": "C1", "timestamp": "2024-03-01T10:00:00Z"})
    r = client.post("/identity/score", json={**base, "src_pc": "C2", "timestamp": "2024-03-01T10:10:00Z"})
    assert r.json()["unique_pcs"] == 2


def test_identity_same_hour_different_day_does_not_collide(client):
    # Regression test for the old (user, hour-of-day) key: two events at 10:00
    # a full day apart must NOT be counted together. Sliding window ages the
    # first out, so the second is a fresh count of 1.
    base = {"src_user": "WIN_C@DOM1", "src_pc": "C1", "auth_type": "Kerberos",
            "logon_type": "Network", "orientation": "LogOn", "success": "Success"}
    client.post("/identity/score", json={**base, "timestamp": "2024-03-01T10:00:00Z"})
    r2 = client.post("/identity/score", json={**base, "timestamp": "2024-03-02T10:00:00Z"})
    assert r2.json()["hourly_count"] == 1


# --- OT/ICS /ics/score ---------------------------------------------------

def test_ics_example_returns_full_reading(client):
    r = client.get("/ics/example")
    assert r.status_code == 200
    assert len(r.json()) == 59


def test_ics_baseline_reading_not_anomalous(client):
    example = client.get("/ics/example").json()
    r = client.post("/ics/score", json={"readings": example})
    assert r.status_code == 200
    body = r.json()
    assert body["is_anomaly"] is False
    assert body["missing_fields"] == []
    assert body["reconstruction_error"] < body["threshold"]


def test_ics_spiked_sensor_is_anomalous(client):
    example = client.get("/ics/example").json()
    example["P4_ST_TT01"] = 900000  # far outside any real operating value
    r = client.post("/ics/score", json={"readings": example})
    assert r.status_code == 200
    assert r.json()["is_anomaly"] is True


def test_ics_missing_field_is_reported(client):
    example = client.get("/ics/example").json()
    example.pop("P1_B2004")
    r = client.post("/ics/score", json={"readings": example})
    assert r.status_code == 200
    assert "P1_B2004" in r.json()["missing_fields"]
