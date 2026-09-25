"""End-to-end tests for the decision layer (Track C: Record -> Decide -> Act), driven
through FastAPI's TestClient so they exercise the real store, policy rules, and responders.

Isolation: conftest.py points VERDICT_DB at a throwaway DB, and every test uses a UNIQUE
subject name, so assertions are about that test's own activity and are unaffected by other
tests writing to the shared throwaway trail.
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    import app
    return TestClient(app.app)


def _login(client, user, pc, suspicious=True):
    """Post one login. 'suspicious' uses an unknown auth type + failed remote-interactive,
    the pattern the detector treats as anomalous once access breadth builds up."""
    return client.post("/identity/score", json={
        "src_user": user, "src_pc": pc,
        "auth_type": "TotallyUnrecognizedAuth" if suspicious else "Kerberos",
        "logon_type": "RemoteInteractive" if suspicious else "Network",
        "orientation": "LogOn", "success": "Fail" if suspicious else "Success",
    })


# --- C1: Record + X-Verdict-Id + feedback + metrics ----------------------

def test_score_records_verdict_and_returns_id(client):
    r = _login(client, "test-solo@DOM1", "C1", suspicious=False)
    assert r.status_code == 200
    vid = r.headers.get("X-Verdict-Id")
    assert vid is not None                       # every scored response carries the id
    got = client.get("/decision/verdicts?subject=test-solo@DOM1&limit=1").json()
    assert got and got[0]["subject"] == "test-solo@DOM1"
    # request metadata was enriched by the middleware
    assert got[0]["path"] == "/identity/score" and got[0]["status"] == 200


def test_feedback_attaches_ground_truth_and_metrics(client):
    r = _login(client, "test-fb@DOM1", "C1", suspicious=True)
    vid = r.headers["X-Verdict-Id"]
    ok = client.post(f"/decision/verdicts/{vid}/feedback", json={"ground_truth": "malicious"})
    assert ok.status_code == 200
    # unknown label is rejected; unknown id is 404
    assert client.post(f"/decision/verdicts/{vid}/feedback",
                       json={"ground_truth": "purple"}).status_code == 422
    assert client.post("/decision/verdicts/999999/feedback",
                       json={"ground_truth": "benign"}).status_code == 404
    m = client.get("/decision/metrics").json()
    assert m["labeled"] >= 1
    for k in ("tp", "fp", "fn", "tn"):
        assert k in m


def test_non_scored_request_is_audited(client):
    client.get("/health")
    reqs = client.get("/decision/requests?limit=50").json()
    assert any(x["path"] == "/health" for x in reqs)


# --- C2: Decide (rules -> alerts) ----------------------------------------

BURST_USER = "test-burst@DOM1"


def test_identity_burst_raises_alert(client):
    for i in range(12):
        _login(client, BURST_USER, f"C90{i:02d}", suspicious=True)
    client.post("/decision/evaluate")
    alerts = client.get("/decision/alerts?limit=500&auto_evaluate=false").json()
    mine = [a for a in alerts if a["rule"] == "identity_burst" and a["subject"] == BURST_USER]
    assert mine, "expected an identity_burst alert for the burst subject"
    assert mine[0]["severity"] in ("low", "medium", "high")
    assert mine[0]["verdict_count"] >= 3


def test_evaluate_is_idempotent(client):
    # a second evaluate over the same window must not duplicate the burst alert
    client.post("/decision/evaluate")
    alerts = client.get("/decision/alerts?limit=500&auto_evaluate=false").json()
    mine = [a for a in alerts if a["rule"] == "identity_burst" and a["subject"] == BURST_USER]
    assert len(mine) == 1


def test_benign_history_suppresses_burst(client):
    # a subject whose flagged logins are consistently labelled benign is a chronic false
    # positive: its burst should be suppressed by the outcome-weighting rule.
    user = "test-suppress@DOM1"
    for i in range(12):
        r = _login(client, user, f"C95{i:02d}", suspicious=True)
        vid = r.headers.get("X-Verdict-Id")
        if vid:
            client.post(f"/decision/verdicts/{vid}/feedback", json={"ground_truth": "benign"})
    client.post("/decision/evaluate")
    alerts = client.get("/decision/alerts?limit=500&auto_evaluate=false").json()
    mine = [a for a in alerts if a["rule"] == "identity_burst" and a["subject"] == user]
    assert not mine, "burst from a chronic-benign subject should be suppressed"


# --- C3: Act (responders + lifecycle) ------------------------------------

def test_actions_fired_for_alert_and_close(client):
    # reuse the burst alert from the C2 test's subject
    alerts = client.get("/decision/alerts?limit=500&auto_evaluate=false").json()
    mine = [a for a in alerts if a["rule"] == "identity_burst" and a["subject"] == BURST_USER]
    assert mine
    aid = mine[0]["id"]
    acts = client.get(f"/decision/actions?alert_id={aid}").json()
    types = {a["action_type"] for a in acts}
    assert {"log", "ticket"}.issubset(types)          # high severity routes log + ticket
    assert all(a["status"] in ("ok", "skipped", "failed") for a in acts)
    # webhook is present but skipped when ACTION_WEBHOOK_URL is unset
    wh = [a for a in acts if a["action_type"] == "webhook"]
    assert wh and wh[0]["status"] == "skipped"
    # close the alert (analyst resolution) + 404 on unknown id
    assert client.post(f"/decision/alerts/{aid}/close").json()["status"] == "closed"
    assert client.post("/decision/alerts/999999/close").status_code == 404
    # closed alert no longer appears in the open queue
    open_ids = [a["id"] for a in client.get("/decision/alerts?status=open&auto_evaluate=false").json()]
    assert aid not in open_ids


# --- E2: LLM triage prioritization (deterministic path; LLM disabled in tests) -----

def test_new_alert_has_default_priority_from_severity(client):
    # a fresh burst subject -> a high-severity alert should get the deterministic default
    user = "test-prio@DOM1"
    for i in range(12):
        _login(client, user, f"C96{i:02d}", suspicious=True)
    client.post("/decision/evaluate")
    alerts = client.get("/decision/alerts?limit=500&auto_evaluate=false").json()
    mine = [a for a in alerts if a["rule"] == "identity_burst" and a["subject"] == user]
    assert mine and mine[0]["priority"] == 4        # high -> default priority 4
    # the queue is ordered by priority (non-increasing)
    prios = [a.get("priority") or 0 for a in alerts]
    assert prios == sorted(prios, reverse=True)


def test_reassess_is_advisory_and_clamped(client):
    # with the LLM disabled, reassess returns the deterministic default and never drops a
    # high-severity alert below its floor.
    user = "test-prio@DOM1"
    alerts = client.get("/decision/alerts?limit=500&auto_evaluate=false").json()
    aid = next(a["id"] for a in alerts if a["subject"] == user and a["rule"] == "identity_burst")
    r = client.post(f"/decision/alerts/{aid}/reassess").json()
    assert r["llm_used"] is False                   # LLM off in tests
    assert r["priority"] >= 3                        # high-severity floor respected
    assert client.post("/decision/alerts/999999/reassess").status_code == 404


# --- Analyst case-management workflow (Tier 1+2) -------------------------------------

def _make_burst_alert(client, user):
    """Raise a fresh identity_burst alert for `user` and return its id."""
    for i in range(12):
        _login(client, user, f"CQ{i:02d}", suspicious=True)
    client.post("/decision/evaluate")
    alerts = client.get("/decision/alerts?limit=500&auto_evaluate=false").json()
    mine = [a for a in alerts if a["rule"] == "identity_burst" and a["subject"] == user]
    assert mine, f"expected a burst alert for {user}"
    return mine[0]["id"]


def test_alert_detail_returns_evidence_and_history(client):
    aid = _make_burst_alert(client, "test-case@DOM1")
    d = client.get(f"/decision/alerts/{aid}").json()
    for k in ("alert", "evidence", "subject_history", "actions", "events"):
        assert k in d
    assert d["alert"]["id"] == aid
    assert len(d["evidence"]) >= 3                      # the contributing verdicts
    assert client.get("/decision/alerts/999999").status_code == 404


def test_acknowledge_assign_note_are_journalled(client):
    aid = _make_burst_alert(client, "test-ack@DOM1")
    assert client.post(f"/decision/alerts/{aid}/acknowledge", json={"actor": "sam"}).json()["status"] == "acknowledged"
    client.post(f"/decision/alerts/{aid}/assign", json={"assignee": "dana"})
    client.post(f"/decision/alerts/{aid}/note", json={"note": "looking into it"})
    d = client.get(f"/decision/alerts/{aid}").json()
    assert d["alert"]["status"] == "acknowledged" and d["alert"]["assignee"] == "dana"
    kinds = {e["action"] for e in d["events"]}
    assert {"acknowledge", "assign", "note"}.issubset(kinds)
    # acknowledged alerts stay visible in the active overview queue
    assert any(a["id"] == aid for a in client.get("/decision/overview").json()["alerts"])


def test_resolve_true_positive_labels_evidence(client):
    aid = _make_burst_alert(client, "test-tp@DOM1")
    ev_ids = [v["id"] for v in client.get(f"/decision/alerts/{aid}").json()["evidence"]]
    r = client.post(f"/decision/alerts/{aid}/resolve",
                    json={"resolution": "true_positive"}).json()
    assert r["status"] == "closed" and r["verdicts_labeled"] == len(ev_ids)
    # every contributing verdict now carries the malicious label (feedback loop closed)
    for vid in ev_ids:
        v = client.get(f"/decision/verdicts?limit=1000").json()
        got = [x for x in v if x["id"] == vid]
        assert got and got[0]["ground_truth"] == "malicious"
    assert client.post("/decision/alerts/999999/resolve", json={"resolution": "benign"}).status_code == 404
    assert client.post(f"/decision/alerts/{aid}/resolve", json={"resolution": "banana"}).status_code == 422


def test_suppress_allowlists_subject_and_blocks_realert(client):
    user = "test-sup@DOM1"
    aid = _make_burst_alert(client, user)
    client.post(f"/decision/alerts/{aid}/suppress", json={"window_hours": 24, "reason": "known good"})
    # the subject is now on the allowlist
    sup = client.get("/decision/suppressions").json()
    mine = [s for s in sup if s["subject"] == user]
    assert mine and mine[0]["active"]
    # new activity for the suppressed subject does NOT raise a fresh alert
    for i in range(12):
        _login(client, user, f"CR{i:02d}", suspicious=True)
    client.post("/decision/evaluate")
    openq = client.get("/decision/alerts?status=open&auto_evaluate=false").json()
    assert not [a for a in openq if a["subject"] == user], "suppressed subject should not re-alert"
    # lifting the suppression works
    assert client.delete(f"/decision/suppressions/{mine[0]['id']}").json()["removed"] is True


def test_manual_action_stub_is_recorded(client):
    aid = _make_burst_alert(client, "test-act@DOM1")
    r = client.post(f"/decision/alerts/{aid}/act", json={"action": "disable_account"}).json()
    assert r["status"] == "stub"                        # posture change is a recorded stub, no live effect
    acts = client.get(f"/decision/actions?alert_id={aid}").json()
    assert any(a["action_type"] == "disable_account" for a in acts)
    assert client.post(f"/decision/alerts/{aid}/act", json={"action": "nope"}).status_code == 422
    assert "disable_account" in client.get("/decision/actions/available").json()["actions"]


# --- Runtime settings (BC.1: personalize limits/thresholds from the browser) ---------

def test_settings_describe_and_effective(client):
    d = client.get("/decision/settings").json()
    assert "groups" in d and "values" in d
    groups = {g["group"] for g in d["groups"]}
    assert "Log retention (FIFO caps)" in groups and "Detection policy" in groups
    assert d["values"]["MAX_VERDICTS"] >= 0 and "IDENTITY_BURST_MIN" in d["values"]


def test_settings_update_is_live_and_validated(client):
    # a valid override takes effect immediately (visible in stats retention)
    r = client.patch("/decision/settings", json={"values": {"MAX_VERDICTS": 4321}})
    assert r.status_code == 200 and r.json()["values"]["MAX_VERDICTS"] == 4321
    assert client.get("/decision/stats").json()["retention"]["max_verdicts"] == 4321
    # out-of-range and unknown keys are rejected (422), nothing partially written
    assert client.patch("/decision/settings", json={"values": {"IDENTITY_BURST_MIN": 0}}).status_code == 422
    assert client.patch("/decision/settings", json={"values": {"NOPE": 1}}).status_code == 422
    # reset restores the default
    client.post("/decision/settings/reset", json={"keys": ["MAX_VERDICTS"]})
    assert client.get("/decision/stats").json()["retention"]["max_verdicts"] != 4321


def test_settings_change_retunes_policy_live(client):
    # raising the burst threshold above the activity means no burst alert is raised — proving the
    # policy reads the threshold live from settings rather than a frozen import-time constant.
    user = "test-cfg@DOM1"
    try:
        client.patch("/decision/settings", json={"values": {"IDENTITY_BURST_MIN": 50}})
        for i in range(12):
            _login(client, user, f"CS{i:02d}", suspicious=True)
        client.post("/decision/evaluate")
        alerts = client.get("/decision/alerts?limit=500&auto_evaluate=false").json()
        assert not [a for a in alerts if a["subject"] == user], "12 < 50 threshold: no burst expected"
    finally:
        client.post("/decision/settings/reset", json={"keys": ["IDENTITY_BURST_MIN"]})
    assert client.get("/decision/settings").json()["values"]["IDENTITY_BURST_MIN"] == 3


# --- Dashboard (live console) -----------------------------------------------------

def test_dashboard_served_at_root(client):
    r = client.get("/")
    assert r.status_code == 200 and "text/html" in r.headers.get("content-type", "")
    assert "EventSource" in r.text and "Live Security Decisioning" in r.text  # console, not Swagger


def test_overview_shape(client):
    o = client.get("/decision/overview").json()
    for k in ("stats", "metrics", "alerts", "recent_verdicts", "actions"):
        assert k in o
    assert set(o["metrics"]) == {"all", "identity", "ics"}
    assert "retention" in o["stats"]


# --- FIFO retention (kept last: it trims the shared verdict trail) -----------------

def test_fifo_retention_evicts_oldest(client):
    import verdict_store as vs
    # ensure a batch of verdicts exists, and note the newest id
    for i in range(15):
        _login(client, f"ret{i}@DOM1", "C1", suspicious=False)
    newest = vs.query_verdicts(limit=1)[0]["id"]
    keep = 5
    res = vs.enforce_retention(max_verdicts=keep, max_requests=10**9, max_actions=10**9)
    assert res["verdicts"]["after"] == keep and res["verdicts"]["evicted"] > 0
    survivors = vs.query_verdicts(limit=100)
    assert len(survivors) == keep                          # bounded to the cap
    ids = [s["id"] for s in survivors]
    assert newest in ids                                   # newest kept
    assert min(ids) == newest - keep + 1                   # exactly the last `keep` by id (FIFO)
