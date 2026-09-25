"""
MAC address resolution (via the local ARP cache) and vendor lookup (via a
curated OUI prefix table) — the extra identifying details a tool like
Advanced IP Scanner shows that a pure TCP port scan doesn't produce on its own.

ARP is a Layer 2 protocol: it only resolves MAC addresses for hosts on the
same physical subnet as the scanning host. Scanning a routed/remote range
will only ever show a gateway's MAC, not each remote host's real one — that's
a protocol limitation, not a bug here.

The OUI table below is a curated subset of common vendors (network gear,
consumer electronics, major device manufacturers) — not the full ~35,000-entry
IEEE registry. Deliberately not an API call to a third-party MAC-vendor
lookup service either: sending MAC addresses (i.e. real network topology
data) off this host to a third party isn't something a compliance-scanning
tool should do by default, and this also needs to work in air-gapped/OT
environments with no internet access at all.
"""
import platform
import re
import subprocess

OUI_VENDORS = {
    "B8:27:EB": "Raspberry Pi Foundation",
    "DC:A6:32": "Raspberry Pi Foundation",
    "E4:5F:01": "Raspberry Pi Foundation",
    "00:1C:B3": "Apple", "3C:07:54": "Apple", "A8:66:7F": "Apple", "F0:18:98": "Apple",
    "00:17:88": "Philips (Hue)",
    "44:65:0D": "Amazon", "68:37:E9": "Amazon", "74:C2:46": "Amazon", "FC:65:DE": "Amazon",
    "00:1B:63": "Netgear", "20:E5:2A": "Netgear", "A0:04:60": "Netgear",
    "94:10:3E": "TP-Link", "50:C7:BF": "TP-Link", "F4:F2:6D": "TP-Link",
    "00:1E:8C": "ASUSTek", "1C:87:2C": "ASUSTek",
    "AC:22:0B": "Ubiquiti Networks", "24:A4:3C": "Ubiquiti Networks", "F0:9F:C2": "Ubiquiti Networks",
    "00:0C:29": "VMware", "00:50:56": "VMware",
    "08:00:27": "Oracle VirtualBox",
    "00:15:5D": "Microsoft (Hyper-V)", "00:03:FF": "Microsoft", "7C:1E:52": "Microsoft", "00:1D:D8": "Microsoft",
    "3C:52:82": "Dell", "B0:83:FE": "Dell", "D4:BE:D9": "Dell",
    "00:21:5A": "Hewlett Packard (HP)", "3C:D9:2B": "Hewlett Packard (HP)", "94:57:A5": "Hewlett Packard (HP)",
    "00:1B:21": "Intel", "3C:A9:F4": "Intel",
    "AC:7B:A1": "Actiontec (ISP router)", "70:F1:1C": "Actiontec (ISP router)",
    "94:B4:0F": "D-Link", "1C:BD:B9": "D-Link", "00:1C:F0": "D-Link",
    "94:C6:91": "Sonos", "5C:AA:FD": "Sonos",
    "00:17:C9": "Ring (Amazon)",
    "A8:70:5D": "Arris / CommScope (ISP router/modem)", "84:D6:D0": "Arris / CommScope (ISP router/modem)",
    "38:43:7D": "Hon Hai / Foxconn",
    "F8:04:2E": "Samsung", "8C:79:F5": "Samsung", "00:16:6C": "Samsung",
}


def get_arp_table():
    """Returns {ip: MAC} from the OS's ARP cache. Only entries for hosts this
    machine has recently communicated with will be present — network_scan.py
    calls this only after attempting connections to every host, so entries
    for responsive hosts on the local subnet should already be populated."""
    table = {}
    try:
        if platform.system() == "Windows":
            output = subprocess.run(["arp", "-a"], capture_output=True, text=True, timeout=5).stdout
            for line in output.splitlines():
                m = re.match(r"\s*(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F-]{17})\s+(\w+)", line)
                if m:
                    ip, mac, _ = m.groups()
                    table[ip] = mac.replace("-", ":").upper()
        else:
            try:
                with open("/proc/net/arp") as f:
                    next(f)
                    for line in f:
                        parts = line.split()
                        if len(parts) >= 4 and parts[3] != "00:00:00:00:00:00":
                            table[parts[0]] = parts[3].upper()
            except FileNotFoundError:
                output = subprocess.run(["ip", "neigh"], capture_output=True, text=True, timeout=5).stdout
                for line in output.splitlines():
                    m = re.match(r"(\d+\.\d+\.\d+\.\d+).*lladdr\s+([0-9a-fA-F:]{17})", line)
                    if m:
                        table[m.group(1)] = m.group(2).upper()
    except (subprocess.SubprocessError, OSError):
        pass
    return table


def lookup_vendor(mac):
    if not mac:
        return None
    prefix = mac.upper().replace("-", ":")[:8]
    return OUI_VENDORS.get(prefix, f"Unknown vendor (OUI {prefix})")
