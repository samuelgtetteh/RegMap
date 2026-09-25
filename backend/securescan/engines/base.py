"""Shared types for scan engines."""
from dataclasses import asdict, dataclass, field
from typing import List, Optional


class EngineUnavailable(RuntimeError):
    """Raised when a requested engine cannot run in this environment."""


@dataclass
class PortFinding:
    port: int
    proto: str = "tcp"
    state: str = "open"
    service: str = ""       # e.g. 'http', 'ssh'
    product: str = ""       # e.g. 'OpenSSH', 'nginx'
    version: str = ""       # e.g. '8.9p1'
    cpe: str = ""           # e.g. 'cpe:2.3:a:openbsd:openssh:8.9p1:...' (nmap) or ''
    banner: str = ""        # raw banner text, if grabbed

    def dict(self) -> dict:
        return asdict(self)


@dataclass
class HostScan:
    target: str             # what the caller asked for (host or IP)
    ip: str                 # resolved IP
    up: bool
    engine: str
    ports: List[PortFinding] = field(default_factory=list)
    error: Optional[str] = None

    def dict(self) -> dict:
        d = asdict(self)
        return d
