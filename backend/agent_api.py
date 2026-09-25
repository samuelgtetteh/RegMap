"""
Agent API — the "scan a private network with an on-prem agent" path.

A cloud-hosted console cannot reach inside a private LAN (NAT). Instead, the user runs a small,
self-contained agent (backend/agent/agent.py) on a machine INSIDE the network they want to scan;
it discovers assets locally and submits the results back here, where they are mapped to NIST
800-53 controls (the same pipeline as a server-side scan) and fed into the Compliance Advisor.

Flow:
  POST /agent/jobs           -> create a token-scoped job; returns run commands for the user
  GET  /agent/agent.py       -> download the agent script
  GET  /agent/jobs/{id}/config?token=  -> agent fetches its scope
  POST /agent/jobs/{id}/results        -> agent submits scan results (token-auth) -> control mapping
  GET  /agent/jobs/{id}      -> console polls for status/results

Safety: the agent is user-run (explicit approval), token-scoped, scans only the job's target, and
only reports open ports/services. Jobs are in-memory (process-local) — fine for this single-node
console; a production deployment would persist them.
"""
import json
import secrets
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

# control-advisor toolkit is made importable by advisor_api; ensure the path here too (order-safe).
_REPO = Path(__file__).resolve().parent.parent
_CA = _REPO / "control-advisor" / "scanner"
if _CA.is_dir() and str(_CA) not in sys.path:
    sys.path.insert(0, str(_CA))

_AGENT_SCRIPT = Path(__file__).resolve().parent / "agent" / "agent.py"
router = APIRouter(prefix="/agent", tags=["agent"])

_JOBS: dict = {}   # job_id -> {token, target, max_hosts, status, scan_report, recommendations, ...}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _map_controls(scan_report: dict):
    """Map an agent's scan results to NIST 800-53 controls (best-effort)."""
    try:
        import control_mapper
        return control_mapper.recommend_for_scan(scan_report)
    except Exception:
        return {"cidr": scan_report.get("cidr"), "hosts": []}


class NewJob(BaseModel):
    label: str = Field("", description="a friendly name for this scan")
    target: str = Field("auto", description="CIDR/host the agent should scan; 'auto' = its local /24")
    max_hosts: int = Field(512, ge=1, le=4096)


@router.post("/jobs")
def create_job(body: NewJob, request: Request):
    """Create a token-scoped agent job and return ready-to-run commands (the user runs the agent
    themselves — that is the approval step)."""
    job_id = uuid.uuid4().hex[:12]
    token = secrets.token_urlsafe(18)
    _JOBS[job_id] = {"token": token, "target": body.target, "max_hosts": body.max_hosts,
                     "label": body.label, "status": "pending", "created_at": _now(),
                     "scan_report": None, "recommendations": None, "submitted_at": None}
    base = str(request.base_url).rstrip("/")
    common = f"--url {base} --job {job_id} --token {token}"
    return {
        "job_id": job_id, "token": token, "target": body.target, "status": "pending",
        "agent_url": f"{base}/agent/agent.py",
        "commands": {
            "powershell": f"iwr {base}/agent/agent.py -OutFile agent.py; python agent.py {common}",
            "bash": f"curl -s {base}/agent/agent.py -o agent.py && python3 agent.py {common}",
            "python": f"python agent.py {common}",
        },
        "note": "Run this on a host INSIDE the network you want to scan. Only scan networks you "
                "are authorized to test.",
    }


@router.get("/agent.py", response_class=PlainTextResponse)
def download_agent():
    """The self-contained agent script (pure standard library)."""
    try:
        return PlainTextResponse(_AGENT_SCRIPT.read_text(encoding="utf-8"),
                                 media_type="text/x-python")
    except OSError:
        raise HTTPException(status_code=500, detail="agent script unavailable")


@router.get("/jobs/{job_id}/config")
def job_config(job_id: str, token: str = Query(...)):
    """The agent fetches its scan scope here (token-authenticated)."""
    job = _JOBS.get(job_id)
    if not job or not secrets.compare_digest(token, job["token"]):
        raise HTTPException(status_code=403, detail="invalid job or token")
    return {"target": job["target"], "max_hosts": job["max_hosts"]}


class AgentResults(BaseModel):
    token: str
    scan_report: dict


@router.post("/jobs/{job_id}/results")
def submit_results(job_id: str, body: AgentResults):
    """The agent submits its scan results here; we map them to controls and mark the job complete."""
    job = _JOBS.get(job_id)
    if not job or not secrets.compare_digest(body.token, job["token"]):
        raise HTTPException(status_code=403, detail="invalid job or token")
    job["scan_report"] = body.scan_report
    job["recommendations"] = _map_controls(body.scan_report)
    job["status"] = "complete"
    job["submitted_at"] = _now()
    return {"ok": True, "job_id": job_id,
            "hosts_found": body.scan_report.get("hosts_found", len(body.scan_report.get("results", [])))}


@router.get("/jobs/{job_id}")
def job_status(job_id: str):
    """Console polls this. Returns status, and (when complete) the scan report + control mappings
    so the Advisor can continue with the interview. Never returns the token."""
    job = _JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="no such job")
    out = {"job_id": job_id, "status": job["status"], "target": job["target"],
           "label": job["label"], "created_at": job["created_at"], "submitted_at": job["submitted_at"]}
    if job["status"] == "complete":
        out["scan_report"] = job["scan_report"]
        out["recommendations"] = job["recommendations"]
        out["hosts_found"] = (job["scan_report"] or {}).get("hosts_found", 0)
    return out


@router.get("/jobs")
def list_jobs():
    """Recent agent jobs (no tokens)."""
    return [{"job_id": jid, "status": j["status"], "label": j["label"], "target": j["target"],
             "created_at": j["created_at"]} for jid, j in list(_JOBS.items())[-50:]]
