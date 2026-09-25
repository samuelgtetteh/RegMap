import importlib.util
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
AUTH_APP_PATH = ROOT / "auth_service" / "app.py"

spec = importlib.util.spec_from_file_location("auth_service_app", AUTH_APP_PATH)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

client = TestClient(module.app)


def test_redmap_status_requires_authentication(monkeypatch):
    class FakeResponse:
        status = 200
        def __init__(self):
            self._body = b'{"status":"ok"}'
        def read(self):
            return self._body
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(request, timeout=10):
        return FakeResponse()

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    response = client.get("/redmap/status")
    assert response.status_code == 401

    register = client.post("/register", json={"username": "redmapuser", "password": "StrongPass123!"})
    assert register.status_code == 201

    login = client.post("/login", json={"username": "redmapuser", "password": "StrongPass123!"})
    assert login.status_code == 200
    token = login.json()["access_token"]

    authed = client.get("/redmap/status", headers={"Authorization": f"Bearer {token}"})
    assert authed.status_code == 200
    payload = authed.json()
    assert payload["reachable"] is True
    assert payload["service"] == "redmap"
