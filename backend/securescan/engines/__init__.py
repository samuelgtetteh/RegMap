"""
Pluggable scan engines. Each engine exposes `scan(target, ports=..., **opts) -> HostScan` and a
`name`. `get_engine(name)` resolves one; "auto" prefers nmap (richer: service/version + CPE) and
falls back to the dependency-free socket engine. New engines (naabu, SBOM/Grype, cloud-API
inventory) can be added here without touching callers.
"""
from typing import Optional

from .base import EngineUnavailable, HostScan, PortFinding  # noqa: F401
from . import socket_scan


def available() -> list:
    """Names of engines usable in this environment (socket is always available)."""
    names = [socket_scan.NAME]
    try:
        from . import nmap_scan
        if nmap_scan.is_available():
            names.append(nmap_scan.NAME)
    except Exception:
        pass
    return names


def get_engine(name: str = "auto"):
    """Return the engine module for `name`. 'auto' = nmap if available, else socket."""
    if name in ("auto", None, ""):
        try:
            from . import nmap_scan
            if nmap_scan.is_available():
                return nmap_scan
        except Exception:
            pass
        return socket_scan
    if name == socket_scan.NAME:
        return socket_scan
    if name == "nmap":
        from . import nmap_scan
        if not nmap_scan.is_available():
            raise EngineUnavailable("nmap engine requested but the nmap binary / python-nmap "
                                    "is not available in this environment")
        return nmap_scan
    raise EngineUnavailable(f"unknown scan engine '{name}' (available: {available()})")
