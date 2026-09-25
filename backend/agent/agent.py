#!/usr/bin/env python3
"""
RegMap SecureScan Agent — run this on a machine INSIDE the network you want to scan.

Why an agent: a cloud-hosted console cannot reach devices inside a private LAN (they are behind
NAT). Running this agent from a host on that network lets it discover the internal assets locally
and submit the results back to the console, which then maps them to NIST 800-53 controls.

Safety / authorization:
  * You are running this yourself — that is the approval step. It is not installed silently.
  * It performs a TCP connect scan of ONLY the target in its job (or your local /24 if 'auto').
  * It talks only to the console URL you pass, authenticated by the one-time job token.
  * It reads no files and collects no credentials; it reports open ports/services only.
  * Only scan networks you own or are explicitly authorized to test.

Pure Python standard library — no pip installs. Usage:
    python agent.py --url https://console.example.com --job <JOB_ID> --token <TOKEN>
    python agent.py ... --target 192.168.1.0/24     # override the scan target
"""
import argparse
import ipaddress
import json
import socket
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

# port -> (service, category) — categories are what the console maps to NIST controls
PORTS = {
    21: ("ftp", "remote_access"), 22: ("ssh", "remote_access"), 23: ("telnet", "remote_access"),
    25: ("smtp", "email"), 53: ("dns", "network_service"), 80: ("http", "web"),
    110: ("pop3", "email"), 135: ("msrpc", "windows"), 139: ("netbios", "windows"),
    143: ("imap", "email"), 389: ("ldap", "directory"), 443: ("https", "web"),
    445: ("smb", "file_share"), 636: ("ldaps", "directory"), 1433: ("mssql", "database"),
    1521: ("oracle", "database"), 3306: ("mysql", "database"), 3389: ("rdp", "remote_access"),
    5432: ("postgres", "database"), 5900: ("vnc", "remote_access"), 6379: ("redis", "database"),
    8000: ("http", "web"), 8080: ("http", "web"), 8443: ("https", "web"),
    9200: ("elasticsearch", "database"), 27017: ("mongodb", "database"),
}


def local_cidr():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80)); ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip, str(ipaddress.ip_network(ip + "/24", strict=False))


def _open(ip, port, timeout=0.6):
    s = socket.socket(); s.settimeout(timeout)
    try:
        return s.connect_ex((ip, port)) == 0
    except OSError:
        return False
    finally:
        s.close()


def scan_host(ip):
    openp = [p for p in PORTS if _open(ip, p)]
    if not openp:
        return None
    return {"ip": ip, "open_ports": openp,
            "services": [{"port": p, "service": PORTS[p][0], "category": PORTS[p][1]} for p in openp],
            "categories": sorted({PORTS[p][1] for p in openp}), "device_type_guess": "host"}


def scan(cidr, max_hosts=512):
    net = ipaddress.ip_network(cidr, strict=False)
    hosts = [str(net.network_address)] if net.num_addresses == 1 else [str(h) for h in net.hosts()][:max_hosts]
    results = []
    with ThreadPoolExecutor(max_workers=64) as ex:
        for r in ex.map(scan_host, hosts):
            if r:
                results.append(r)
    return {"cidr": cidr, "hosts_scanned": len(hosts), "hosts_found": len(results), "results": results}


def main():
    ap = argparse.ArgumentParser(description="RegMap SecureScan agent")
    ap.add_argument("--url", required=True, help="console base URL")
    ap.add_argument("--job", required=True)
    ap.add_argument("--token", required=True)
    ap.add_argument("--target", default="", help="CIDR/host to scan (default: from job, or local /24)")
    a = ap.parse_args()
    base = a.url.rstrip("/")

    print("RegMap SecureScan agent — authorized use only.")
    try:
        with urllib.request.urlopen(f"{base}/agent/jobs/{a.job}/config?token={a.token}", timeout=15) as r:
            cfg = json.loads(r.read().decode())
    except Exception as e:
        print("could not fetch job config:", e); sys.exit(1)

    target = a.target or cfg.get("target") or "auto"
    if target == "auto" or not target:
        ip, cidr = local_cidr()
        target = cidr
        print(f"auto-detected local network: {target}  (this host: {ip})")
    print(f"scanning {target} ...")
    report = scan(target, int(cfg.get("max_hosts", 512)))
    print(f"found {report['hosts_found']} host(s) across {report['hosts_scanned']} scanned; submitting ...")

    data = json.dumps({"token": a.token, "scan_report": report}).encode()
    req = urllib.request.Request(f"{base}/agent/jobs/{a.job}/results", data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            print("submitted:", r.read().decode())
    except Exception as e:
        print("submit failed:", e); sys.exit(1)
    print("done — return to the console to continue.")


if __name__ == "__main__":
    main()
