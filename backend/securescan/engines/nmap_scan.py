"""
Optional nmap engine — richer service/version detection + CPE strings (feeds precise NVD lookups).

Requires the `nmap` binary and the `python-nmap` package; both are installed in the Docker image
but absent from a bare dev machine. `is_available()` reports whether it can run, so callers
(engines.get_engine / "auto") transparently fall back to the socket engine when it can't.
"""
from typing import List, Optional

from .base import EngineUnavailable, HostScan, PortFinding

NAME = "nmap"

# Default scope: a fast top-ports service/version scan. -sV = version detection; -T3 = polite-ish.
_DEFAULT_ARGS = "-sV --version-intensity 5 -T3"


def is_available() -> bool:
    try:
        import nmap  # python-nmap
        scanner = nmap.PortScanner()  # raises if the nmap binary is missing
        _ = scanner
        return True
    except Exception:
        return False


def scan(target: str, ip: Optional[str] = None, ports: Optional[List[int]] = None,
         timeout: float = 0.0, banner: bool = True, delay: float = 0.0,
         arguments: str = _DEFAULT_ARGS) -> HostScan:
    import nmap
    ip = ip or target
    result = HostScan(target=target, ip=ip, up=False, engine=NAME)
    try:
        scanner = nmap.PortScanner()
    except Exception as e:
        raise EngineUnavailable(str(e))
    port_arg = ",".join(str(p) for p in ports) if ports else "1-1024"
    args = arguments + (f" --scan-delay {delay}s" if delay else "")
    try:
        scanner.scan(ip, port_arg, arguments=args)
    except Exception as e:
        result.error = f"nmap scan failed: {e}"
        return result
    if ip not in scanner.all_hosts():
        return result
    host = scanner[ip]
    result.up = host.state() == "up"
    for proto in host.all_protocols():
        for port in sorted(host[proto].keys()):
            svc = host[proto][port]
            if svc.get("state") != "open":
                continue
            cpe = svc.get("cpe", "")
            if isinstance(cpe, list):
                cpe = cpe[0] if cpe else ""
            result.ports.append(PortFinding(
                port=port, proto=proto, state=svc.get("state", "open"),
                service=svc.get("name", ""), product=svc.get("product", ""),
                version=svc.get("version", ""), cpe=cpe,
                banner=svc.get("extrainfo", "")))
    return result
