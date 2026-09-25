"""
Pure-Python TCP connect-scan engine — the default, dependency-free engine.

Uses a full TCP connect (connect_ex) rather than raw SYN packets: it needs no root and no external
binary, so it runs anywhere the app runs, including a locked-down cloud container. It is also
comparatively low-noise (a normal completed handshake, optional inter-port delay). It does light
service identification from a well-known-port table and an optional banner grab; it does NOT do
nmap-grade version detection (use the nmap engine for CPE-quality version strings).
"""
import socket
from typing import List, Optional

from .base import HostScan, PortFinding

NAME = "socket"

# A pragmatic default set of common TCP ports (service discovery, not an exhaustive sweep).
COMMON_PORTS = {
    21: "ftp", 22: "ssh", 23: "telnet", 25: "smtp", 53: "domain", 80: "http", 110: "pop3",
    111: "rpcbind", 135: "msrpc", 139: "netbios-ssn", 143: "imap", 161: "snmp", 389: "ldap",
    443: "https", 445: "microsoft-ds", 465: "smtps", 587: "submission", 636: "ldaps",
    993: "imaps", 995: "pop3s", 1433: "ms-sql-s", 1521: "oracle", 2049: "nfs", 2375: "docker",
    3306: "mysql", 3389: "ms-wbt-server", 5432: "postgresql", 5900: "vnc", 5985: "wsman",
    6379: "redis", 8000: "http-alt", 8080: "http-proxy", 8443: "https-alt", 9200: "elasticsearch",
    11211: "memcached", 27017: "mongodb",
}
DEFAULT_PORTS = sorted(COMMON_PORTS)


def is_available() -> bool:
    return True


def _grab_banner(ip: str, port: int, timeout: float) -> str:
    """Best-effort banner grab: read a short greeting, or nudge HTTP with a HEAD. Never raises."""
    try:
        with socket.create_connection((ip, port), timeout=timeout) as s:
            s.settimeout(timeout)
            if port in (80, 8080, 8000, 443, 8443):
                try:
                    s.sendall(b"HEAD / HTTP/1.0\r\n\r\n")
                except OSError:
                    return ""
            data = s.recv(256)
            return data.decode("latin-1", "replace").strip()
    except OSError:
        return ""


def _service_from_banner(banner: str) -> str:
    b = banner.lower()
    if b.startswith("ssh-"):
        return "ssh"
    if b.startswith("http/") or "server:" in b:
        return "http"
    if b.startswith("220") and "ftp" in b:
        return "ftp"
    if b.startswith("220") and ("smtp" in b or "esmtp" in b):
        return "smtp"
    return ""


def scan(target: str, ip: Optional[str] = None, ports: Optional[List[int]] = None,
         timeout: float = 0.7, banner: bool = True, delay: float = 0.0) -> HostScan:
    """Connect-scan `ip` (resolved by the caller) across `ports`. `delay` seconds between ports
    keeps it polite/low-noise on sensitive networks."""
    import time
    ip = ip or target
    port_list = ports if ports else DEFAULT_PORTS
    result = HostScan(target=target, ip=ip, up=False, engine=NAME)
    for port in port_list:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            rc = sock.connect_ex((ip, port))
            sock.close()
        except OSError:
            continue
        if rc == 0:
            result.up = True
            b = _grab_banner(ip, port, timeout) if banner else ""
            svc = COMMON_PORTS.get(port, "") or _service_from_banner(b)
            result.ports.append(PortFinding(port=port, service=svc, banner=b))
        if delay:
            time.sleep(delay)
    return result
