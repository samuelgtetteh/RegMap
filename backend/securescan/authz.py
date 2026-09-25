"""
Authorization guard for SecureScan.

Active scanning is only appropriate against hosts you own or are explicitly authorized to test.
This module enforces that: a target must fall inside an allowlist, or scanning-anything must be
explicitly enabled. It is the safety switch that keeps the scanner from being pointed at third
parties by accident (or by a malicious API caller).

Policy (env-configurable; can be surfaced in the settings UI later):
  * Default allowlist: loopback (127.0.0.0/8, ::1) + RFC1918/private + link-local ranges.
  * ALLOWED_SCAN_TARGETS: comma-separated extra CIDRs/IPs to allow (e.g. a lab subnet).
  * SCAN_ALLOW_ANY (truthy): allow ANY target. This is the deliberate opt-in for a cloud
    deployment intended to scan whatever environment it is called into — set it consciously.
"""
import ipaddress
import os
import socket
from typing import Tuple

# Private / loopback / link-local ranges allowed by default (no opt-in needed).
_DEFAULT_ALLOWED = [
    "127.0.0.0/8", "::1/128",
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
    "169.254.0.0/16", "fe80::/10", "fc00::/7",
]


def _truthy(val: str) -> bool:
    return str(val).strip().lower() not in ("0", "false", "no", "off", "")


def allow_any() -> bool:
    return _truthy(os.environ.get("SCAN_ALLOW_ANY", "0"))


def _allowed_networks():
    nets = [ipaddress.ip_network(c) for c in _DEFAULT_ALLOWED]
    extra = os.environ.get("ALLOWED_SCAN_TARGETS", "").strip()
    for token in (t.strip() for t in extra.split(",") if t.strip()):
        try:
            nets.append(ipaddress.ip_network(token, strict=False))
        except ValueError:
            continue  # ignore malformed entries rather than failing closed on config typos
    return nets


def resolve(target: str) -> str:
    """Resolve a hostname to an IP (or return the IP unchanged). Raises ValueError if unresolvable."""
    target = (target or "").strip()
    if not target:
        raise ValueError("empty target")
    try:
        ipaddress.ip_address(target)
        return target
    except ValueError:
        pass
    try:
        return socket.gethostbyname(target)
    except OSError as e:
        raise ValueError(f"could not resolve '{target}': {e}")


def is_authorized(target: str) -> Tuple[bool, str]:
    """Return (allowed, reason). A target is allowed if SCAN_ALLOW_ANY is set, or its resolved IP
    falls inside the (default + configured) allowlist."""
    try:
        ip = resolve(target)
    except ValueError as e:
        return False, str(e)
    if allow_any():
        return True, "SCAN_ALLOW_ANY enabled"
    addr = ipaddress.ip_address(ip)
    for net in _allowed_networks():
        if addr in net:
            return True, f"{ip} in allowlisted {net}"
    return False, (f"{ip} is not in the scan allowlist (loopback/private by default). "
                   "Add it to ALLOWED_SCAN_TARGETS, or set SCAN_ALLOW_ANY=1 to authorize "
                   "scanning any target (only do this where you are authorized to scan).")


def assert_authorized(target: str) -> str:
    """Return the resolved IP if authorized; raise PermissionError otherwise."""
    ok, reason = is_authorized(target)
    if not ok:
        raise PermissionError(reason)
    return resolve(target)


def describe() -> dict:
    """Current authorization posture, for the API/UI."""
    return {"allow_any": allow_any(),
            "default_allowlist": _DEFAULT_ALLOWED,
            "extra_allowlist": os.environ.get("ALLOWED_SCAN_TARGETS", "").strip()}
