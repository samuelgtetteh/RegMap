"""
Detects what kind of network/cloud environment this tool is currently running in,
so the scanner can suggest a sensible default target range instead of guessing blindly.

Two things this deliberately does NOT do:
  1. Auto-scan anything. Detection only ever produces a *suggestion* — the caller
     (CLI or API) must still get explicit user confirmation of the target range
     before any scan runs.
  2. Assume host networking. Running inside a Docker container's default bridge
     network means this will detect the container's isolated virtual subnet
     (e.g. 172.17.0.0/16), NOT the user's real LAN — that's only visible with
     `--network host` (Linux) or when run natively outside a container.
"""
import os
import socket
from pathlib import Path

import psutil


def get_local_interfaces(include_link_local=False):
    """Returns a list of dicts: {interface, ip, netmask, cidr} for every non-loopback
    IPv4 interface this process can see. Under default Docker bridge networking,
    this will only show the container's virtual interface, not the host's real NICs.

    By default, excludes 169.254.0.0/16 (APIPA) addresses — these show up on every
    inactive/unconfigured Windows adapter and aren't real scannable networks; they'd
    otherwise drown out the interface that actually matters."""
    results = []
    for iface, addrs in psutil.net_if_addrs().items():
        for addr in addrs:
            if addr.family != socket.AF_INET or addr.address.startswith("127."):
                continue
            if not include_link_local and addr.address.startswith("169.254."):
                continue
            cidr = _netmask_to_cidr(addr.netmask) if addr.netmask else None
            network = _network_address(addr.address, addr.netmask) if addr.netmask else None
            results.append({
                "interface": iface,
                "ip": addr.address,
                "netmask": addr.netmask,
                "suggested_range": f"{network}/{cidr}" if network and cidr else None,
            })
    return results


def get_outbound_ip():
    """The IP this host would use to reach the internet — a reliable way to find
    'my own address' even when there are multiple interfaces, without sending
    any actual traffic (UDP connect() doesn't transmit packets for a connected
    but unused socket)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def detect_docker():
    """True if this process is very likely running inside a Docker container."""
    if Path("/.dockerenv").exists():
        return True
    try:
        cgroup = Path("/proc/1/cgroup").read_text()
        return "docker" in cgroup or "containerd" in cgroup
    except (FileNotFoundError, PermissionError):
        return False


CLOUD_METADATA_ENDPOINTS = {
    "aws": ("http://169.254.169.254/latest/meta-data/", {}),
    "azure": ("http://169.254.169.254/metadata/instance", {"Metadata": "true"}),
    "gcp": ("http://169.254.169.254/computeMetadata/v1/", {"Metadata-Flavor": "Google"}),
}


def detect_cloud_metadata_service(timeout=0.3):
    """Checks whether this host is itself a cloud VM, by probing the standard
    instance-metadata IP each provider uses. Only meaningful if this container
    is actually running ON a cloud instance (e.g. an EC2 host) — running in
    Docker Desktop on a laptop will correctly report none of these as reachable."""
    import urllib.request

    found = []
    for provider, (url, headers) in CLOUD_METADATA_ENDPOINTS.items():
        try:
            req = urllib.request.Request(url, headers=headers)
            urllib.request.urlopen(req, timeout=timeout)
            found.append(provider)
        except Exception:
            continue
    return found


def detect_cloud_credentials():
    """Checks for locally configured cloud credentials (env vars or CLI config
    files) — this tells us API access to a cloud account *could* be available
    for the live cloud-scanning phase, independent of whether this machine is
    itself hosted in that cloud."""
    found = {}

    aws_env = any(os.environ.get(k) for k in ("AWS_ACCESS_KEY_ID", "AWS_PROFILE"))
    aws_file = (Path.home() / ".aws" / "credentials").exists()
    if aws_env or aws_file:
        found["aws"] = {"via_env": aws_env, "via_config_file": aws_file}

    azure_env = any(os.environ.get(k) for k in ("AZURE_CLIENT_ID", "AZURE_SUBSCRIPTION_ID"))
    azure_file = (Path.home() / ".azure").exists()
    if azure_env or azure_file:
        found["azure"] = {"via_env": azure_env, "via_config_file": azure_file}

    gcp_env = bool(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"))
    gcp_file = (Path.home() / ".config" / "gcloud").exists()
    if gcp_env or gcp_file:
        found["gcp"] = {"via_env": gcp_env, "via_config_file": gcp_file}

    return found


def _netmask_to_cidr(netmask):
    return sum(bin(int(octet)).count("1") for octet in netmask.split("."))


def _network_address(ip, netmask):
    ip_parts = [int(p) for p in ip.split(".")]
    mask_parts = [int(p) for p in netmask.split(".")]
    net_parts = [ip_parts[i] & mask_parts[i] for i in range(4)]
    return ".".join(str(p) for p in net_parts)


def detect_environment():
    """Top-level summary used by the CLI/API to present a suggested (never
    auto-applied) scan target and cloud context to the user."""
    return {
        "running_in_docker": detect_docker(),
        "outbound_ip": get_outbound_ip(),
        "local_interfaces": get_local_interfaces(),
        "is_cloud_instance": detect_cloud_metadata_service(),
        "cloud_credentials_available": detect_cloud_credentials(),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(detect_environment(), indent=2))
