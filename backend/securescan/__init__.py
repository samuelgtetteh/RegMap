"""
SecureScan — asset discovery + CVE mapping (Phase 1 of docs/securescan_roadmap.md).

Given an authorized target host, discover open ports and services, map each service to known
CVEs (NVD), and produce a structured report. Designed to plug into the existing platform: findings
are recorded to the verdict store (model="scan") so they reuse the Record -> Decide -> Act -> live
dashboard stack rather than living in a silo.

Key design choices:
  * Pluggable scan ENGINES (scanner.engines). The default `socket` engine is pure-Python (TCP
    connect scan) so it runs anywhere — including a cloud container — with no external binary. The
    optional `nmap` engine adds service/version + CPE detection when the nmap binary is present.
  * An AUTHORIZATION guard (scanner.authz): scans are restricted to an allowlist (loopback +
    private ranges by default). Scanning arbitrary hosts requires an explicit opt-in
    (SCAN_ALLOW_ANY) — the deliberate switch for a cloud deployment meant to scan whatever
    environment it is called into.
  * NVD lookups (scanner.nvd) are cached and best-effort (never raise), so the tool degrades
    gracefully offline / under rate limits.
"""
