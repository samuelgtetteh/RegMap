"""
Host discovery and service fingerprinting for a user-specified IP range.

Deliberately uses plain TCP connect() attempts rather than raw ICMP/SYN scanning:
raw sockets need root/admin privileges on every OS and behave inconsistently
inside containers, while a TCP connect scan works identically and portably on
Windows, Linux, and Docker with zero special privileges. The tradeoff is it's
slower than a SYN scan and only detects hosts with at least one reachable port
in PORT_FINGERPRINTS — acceptable for this tool's purpose (inferring what kind
of resource is running, not exhaustive host discovery).

Safety: this module only ever scans the CIDR range explicitly passed in by the
caller. Nothing here auto-discovers or defaults to a target — see cli.py for
where the user is required to confirm the range before scan() is called.
"""
import ipaddress
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import mac_lookup

# port -> (label, category). Category is the interface to Phase 2's control mapper.
PORT_FINGERPRINTS = {
    21: ("FTP", "file_transfer_insecure"),
    22: ("SSH", "remote_access"),
    23: ("Telnet", "remote_access_insecure"),
    25: ("SMTP", "email"),
    53: ("DNS", "dns"),
    80: ("HTTP", "web_insecure"),
    110: ("POP3", "email"),
    135: ("MSRPC", "windows_rpc"),
    139: ("NetBIOS", "file_sharing"),
    143: ("IMAP", "email"),
    443: ("HTTPS", "web"),
    445: ("SMB", "file_sharing"),
    993: ("IMAPS", "email"),
    995: ("POP3S", "email"),
    1433: ("MSSQL", "database"),
    1521: ("Oracle DB", "database"),
    3306: ("MySQL", "database"),
    3389: ("RDP", "remote_access"),
    5432: ("PostgreSQL", "database"),
    5900: ("VNC", "remote_access"),
    6379: ("Redis", "database"),
    8080: ("HTTP-alt", "web_insecure"),
    8443: ("HTTPS-alt", "web"),
    9200: ("Elasticsearch", "database"),
    27017: ("MongoDB", "database"),
}

MAX_HOSTS_ALLOWED = 1024  # default cap for a single scan call
HARD_MAX_HOSTS = 65536    # absolute ceiling (a /16) — cannot be overridden, even for WAN scans


def is_private_range(cidr):
    """False for public/routable ranges — used by cli.py to require an extra
    explicit authorization confirmation before scanning a WAN-style target,
    on top of the normal 'confirm your range' step every scan already requires."""
    return ipaddress.ip_network(cidr, strict=False).is_private


def check_port(ip, port, timeout):
    """Returns (is_open, elapsed_ms). is_open is True if the port is open OR
    actively refused (both mean the host is alive) — only a timeout means
    'no signal', which is treated as closed."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    started = time.time()
    try:
        result = sock.connect_ex((str(ip), port))
        elapsed_ms = (time.time() - started) * 1000
        return result == 0, elapsed_ms
    except socket.error:
        return False, None
    finally:
        sock.close()


def scan_host(ip, ports, timeout):
    open_ports = []
    latencies = []
    with ThreadPoolExecutor(max_workers=len(ports)) as pool:
        futures = {pool.submit(check_port, ip, p, timeout): p for p in ports}
        for future in as_completed(futures):
            port = futures[future]
            is_open, elapsed_ms = future.result()
            if is_open:
                open_ports.append(port)
                if elapsed_ms is not None:
                    latencies.append(elapsed_ms)
    response_time_ms = round(min(latencies), 1) if latencies else None
    return sorted(open_ports), response_time_ms


DEVICE_TYPE_RULES = [
    (lambda cats: {"dns", "web"} <= cats or {"dns", "web_insecure"} <= cats,
     "Likely a router/gateway (DNS + web admin interface)"),
    (lambda cats: {"file_sharing", "windows_rpc"} <= cats,
     "Likely a Windows PC or file server (SMB/RPC)"),
    (lambda cats: "database" in cats,
     "Likely a database server"),
    (lambda cats: "email" in cats,
     "Likely a mail server"),
    (lambda cats: bool({"remote_access", "remote_access_insecure"} & cats) and len(cats) == 1,
     "Likely a server or workstation with remote access enabled"),
    (lambda cats: bool({"web", "web_insecure"} & cats) and len(cats) <= 2,
     "Likely a web server or web-enabled device (could be IoT, printer, or camera)"),
    (lambda cats: "file_sharing" in cats,
     "Likely a NAS or file-sharing device"),
]


def guess_device_type(categories):
    cats = set(categories)
    for rule, label in DEVICE_TYPE_RULES:
        if rule(cats):
            return label
    return "Unidentified device type"


def resolve_hostname(ip, timeout=0.5):
    """Best-effort reverse DNS lookup — many devices (esp. IoT/mobile) won't
    have one, so a miss is expected and not an error."""
    old_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout)
    try:
        hostname, _, _ = socket.gethostbyaddr(str(ip))
        return hostname
    except (socket.herror, socket.gaierror, socket.timeout, OSError):
        return None
    finally:
        socket.setdefaulttimeout(old_timeout)


def fingerprint_host(ip, open_ports, response_time_ms=None, mac=None):
    services = []
    categories = set()
    for port in open_ports:
        label, category = PORT_FINGERPRINTS.get(port, (f"unknown:{port}", "unknown"))
        services.append({"port": port, "service": label, "category": category})
        categories.add(category)
    categories = sorted(categories)
    return {
        "ip": str(ip),
        "hostname": resolve_hostname(ip),
        "mac_address": mac,
        "vendor": mac_lookup.lookup_vendor(mac),
        "response_time_ms": response_time_ms,
        "open_ports": open_ports,
        "services": services,
        "categories": categories,
        "device_type_guess": guess_device_type(categories),
    }


def scan(cidr, ports=None, timeout=0.5, max_workers=64, progress_callback=None, max_hosts=MAX_HOSTS_ALLOWED):
    """Scans every host in `cidr` for the given ports (defaults to all of
    PORT_FINGERPRINTS) and returns a list of fingerprint dicts for hosts with
    at least one responsive port.

    `max_hosts` defaults to MAX_HOSTS_ALLOWED (1024) but callers can raise it
    for legitimately large authorized targets — e.g. a company's own WAN
    spanning multiple sites — up to HARD_MAX_HOSTS, which cannot be overridden
    at all. That ceiling exists to stop a typo'd /8 from launching a scan of
    16 million addresses regardless of what the caller asked for."""
    effective_max = min(max_hosts, HARD_MAX_HOSTS)
    network = ipaddress.ip_network(cidr, strict=False)
    hosts = list(network.hosts()) or [network.network_address]
    if len(hosts) > effective_max:
        raise ValueError(
            f"{cidr} contains {len(hosts)} addresses, over the {effective_max} limit. "
            "Pass a smaller range, or raise max_hosts (capped at "
            f"{HARD_MAX_HOSTS} / a /16, regardless of what's requested)."
        )

    ports = ports or list(PORT_FINGERPRINTS.keys())
    results = []
    started = time.time()

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(scan_host, ip, ports, timeout): ip for ip in hosts}
        done = 0
        for future in as_completed(futures):
            ip = futures[future]
            done += 1
            if progress_callback:
                progress_callback(done, len(hosts), str(ip))
            open_ports, response_time_ms = future.result()
            if open_ports:
                results.append((ip, open_ports, response_time_ms))

    # Pull the ARP cache once, after every connection attempt has already run —
    # entries for hosts on the local subnet should now be populated. Only
    # meaningful for local-subnet targets; see mac_lookup.py's docstring.
    arp_table = mac_lookup.get_arp_table()
    fingerprints = [
        fingerprint_host(ip, open_ports, response_time_ms, mac=arp_table.get(str(ip)))
        for ip, open_ports, response_time_ms in results
    ]

    fingerprints.sort(key=lambda r: ipaddress.ip_address(r["ip"]))
    return {
        "cidr": str(network),
        "hosts_scanned": len(hosts),
        "hosts_found": len(fingerprints),
        "duration_seconds": round(time.time() - started, 2),
        "results": fingerprints,
    }


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Scan a CIDR range for live hosts and fingerprint open services.")
    parser.add_argument("cidr", help="Target range, e.g. 10.0.0.0/24 — must be a network you own or are authorized to scan.")
    parser.add_argument("--timeout", type=float, default=0.5, help="Per-port connect timeout in seconds")
    args = parser.parse_args()

    def progress(done, total, ip):
        print(f"\r  scanning... {done}/{total} ({ip})", end="", flush=True)

    print(f"Scanning {args.cidr} - only scan networks you own or are authorized to test.")
    report = scan(args.cidr, timeout=args.timeout, progress_callback=progress)
    print()
    print(json.dumps(report, indent=2))
