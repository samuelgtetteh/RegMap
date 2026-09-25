"""
End-to-end CLI for the Control Advisor: detect environment -> confirm scan
target -> scan -> map controls -> interview -> prioritize -> report.

Run from the control-advisor/ directory:
    python cli.py
"""
import datetime
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "scanner"))

import baseline_controls
import control_mapper
import docx_report
import draft_language
import environment_detect
import interview
import network_scan
import xlsx_report

REPORTS_DIR = Path(__file__).parent / "reports"


def _sanitize_folder_name(name):
    """Strips characters Windows/most filesystems don't allow in a folder
    name, and trims trailing dots/spaces (Windows silently mangles those)."""
    cleaned = re.sub(r'[<>:"/\\|?*]', "", name).strip().strip(".")
    return cleaned or "Unnamed Organization"


def _unique_report_folder(base_dir, name):
    """Never overwrites or merges into a previous run's folder for the same
    business — if the name is already taken, the NEW run gets renamed
    (name_2, name_3, ...), leaving prior reports untouched."""
    candidate = base_dir / name
    if not candidate.exists():
        return candidate
    i = 2
    while (base_dir / f"{name}_{i}").exists():
        i += 1
    return base_dir / f"{name}_{i}"


def _parse_draft_count(raw, max_n):
    """Accepts a bare number, but also natural phrasing like "all of them" or
    "none" — a strict int() parse silently defaulted to 0 (skip everything)
    on any input it didn't understand, which is exactly the kind of silent
    misinterpretation this tool is supposed to avoid. Returns None if the
    input is genuinely ambiguous, so the caller can ask once more instead of
    guessing wrong."""
    v = raw.strip().lower()
    if not v:
        return 0
    if any(w in v for w in ("all", "everything", "every one", "every control")):
        return max_n
    if any(w in v for w in ("none", "skip", "nothing", "n/a", "na")):
        return 0
    match = re.search(r"\d+", v)
    if match:
        return max(0, min(int(match.group()), max_n))
    return None


def _write_with_fallback(path, write_fn, max_attempts=10):
    """Tries `path`, then path_1, path_2, ... on PermissionError (almost
    always because a previous report of the same name is still open in
    Excel/Notepad/etc. on Windows, which locks the file for writing) — a
    report you were reviewing shouldn't cause the whole tool to crash on its
    next run. Returns the path actually written, or None if every attempt
    was blocked, printing a warning either way."""
    candidate = path
    for attempt in range(max_attempts):
        try:
            write_fn(candidate)
            return candidate
        except PermissionError:
            print(f"  Warning: '{candidate}' is locked (probably open in another program) - trying a different filename.")
            candidate = path.with_stem(f"{path.stem}_{attempt + 1}")
    print(f"  Warning: could not write {path} after {max_attempts} attempts - close whatever has it open and re-run.")
    return None


def main():
    print("=" * 60)
    print("  Control Advisor - NIST 800-53 Control Recommendation Tool")
    print("=" * 60)

    print("\nDetecting local environment...")
    env = environment_detect.detect_environment()

    if env["running_in_docker"]:
        print("Running inside a Docker container - network visibility depends on how it was launched")
        print("(default bridge networking only sees the container's own virtual subnet).")
    else:
        print("Running natively (not in a container).")

    if env["is_cloud_instance"]:
        print(f"This host appears to be a cloud instance: {', '.join(env['is_cloud_instance'])}")
    if env["cloud_credentials_available"]:
        print(f"Cloud credentials detected for: {', '.join(env['cloud_credentials_available'].keys())} "
              "(live cloud resource scanning is a future phase, not yet implemented)")

    print("\nDetected local network interfaces:")
    for iface in env["local_interfaces"]:
        if iface["suggested_range"]:
            print(f"  {iface['interface']}: {iface['ip']} (suggests range {iface['suggested_range']})")

    print("\nThis tool will ONLY scan the exact range(s) you confirm below.")
    print("Only enter ranges you own or are explicitly authorized to scan.")
    default_range = next((i["suggested_range"] for i in env["local_interfaces"] if i["suggested_range"]), None)

    print("\nScan scope:")
    print("  [1] Local network only" + (f" (detected: {default_range})" if default_range else ""))
    print("  [2] WAN / multiple sites - enter additional ranges you own or administer")
    scope = input("Choose 1 or 2 [1]: ").strip() or "1"

    cidrs = []
    if default_range and scope != "2":
        cidrs.append(default_range)

    if scope == "2":
        print("\nEnter each range you own or are explicitly authorized to scan, comma-separated")
        print("(e.g. 10.0.0.0/24,203.0.113.0/24,198.51.100.128/28) - this is NOT for scanning")
        print("the open internet or ranges belonging to someone else.")
        prompt = f"WAN/site range(s) [{default_range}]: " if default_range else "WAN/site range(s): "
        raw_ranges = input(prompt).strip() or default_range
        if not raw_ranges:
            print("No range provided. Exiting.")
            return
        cidrs = [c.strip() for c in raw_ranges.split(",") if c.strip()]

    if not cidrs:
        print("No range provided. Exiting.")
        return

    confirmed_cidrs = []
    for cidr in cidrs:
        if not network_scan.is_private_range(cidr):
            print(f"\n'{cidr}' is a PUBLIC/routable range, not a private LAN range.")
            print("Scanning ranges you don't own or aren't explicitly authorized to test can be illegal")
            print("(e.g. under the US Computer Fraud and Abuse Act) and violates most cloud/hosting")
            print("providers' terms of service. Also note: MAC/vendor identification cannot work across")
            print("a routed WAN regardless of authorization - ARP does not cross subnet boundaries.")
            ack = input(f"Type CONFIRM if you own or are explicitly authorized to scan {cidr}: ").strip()
            if ack.lower() != "confirm":
                print(f"  Skipping {cidr} - not confirmed.")
                continue
        confirmed_cidrs.append(cidr)

    if not confirmed_cidrs:
        print("No confirmed ranges to scan. Exiting.")
        return

    def progress(done, total, ip):
        print(f"\r  {done}/{total} ({ip})", end="", flush=True)

    all_results = []
    total_scanned = 0
    total_duration = 0.0
    for cidr in confirmed_cidrs:
        print(f"\nScanning {cidr}...")
        scan_report = network_scan.scan(cidr, progress_callback=progress, max_hosts=network_scan.HARD_MAX_HOSTS)
        print(f"\nFound {scan_report['hosts_found']} live host(s) in {scan_report['duration_seconds']}s.")
        all_results.extend(scan_report["results"])
        total_scanned += scan_report["hosts_scanned"]
        total_duration += scan_report["duration_seconds"]

    scan_report = {
        "cidr": ", ".join(confirmed_cidrs),
        "hosts_scanned": total_scanned,
        "hosts_found": len(all_results),
        "duration_seconds": round(total_duration, 2),
        "results": all_results,
    }

    if scan_report["hosts_found"] == 0:
        print("No responsive hosts found on the scanned ports - nothing to recommend controls for.")
        return

    print("\n" + "=" * 60)
    print("  DEVICES FOUND")
    print("=" * 60)
    for host in scan_report["results"]:
        services = ", ".join(f"{s['service']}:{s['port']}" for s in host["services"])
        label = f"{host['ip']}" + (f" ({host['hostname']})" if host.get("hostname") else "")
        print(f"\n  {label}")
        print(f"    {host['device_type_guess']}")
        if host.get("mac_address"):
            print(f"    MAC: {host['mac_address']}  |  Vendor: {host['vendor']}")
        elif not network_scan.is_private_range(f"{host['ip']}/32"):
            print("    MAC: not available (WAN/routed target - ARP cannot resolve beyond the local subnet)")
        else:
            print("    MAC: not available (no ARP entry - may be this scanner's own IP, or ARP hasn't populated)")
        if host.get("response_time_ms") is not None:
            print(f"    Response time: {host['response_time_ms']} ms")
        print(f"    Open services: {services}")

    print("\nMapping discovered resources to candidate NIST 800-53 controls...")
    recommendations = control_mapper.recommend_for_scan(scan_report)

    all_categories = {c for host in scan_report["results"] for c in host["categories"]}
    context = interview.run_interview(categories=all_categories)

    print("Prioritizing controls based on environment context...\n")
    final = interview.prioritize_scan_recommendations(recommendations, context)
    baseline_raw = baseline_controls.load_baseline_controls()
    baseline_prioritized = interview.prioritize_baseline_controls(baseline_raw, context)

    print("Writing an executive summary (about 30-60 seconds)...\n")
    executive_summary = draft_language.generate_executive_summary(final, baseline_prioritized, context)
    print("=" * 60)
    print("  EXECUTIVE SUMMARY")
    print("=" * 60)
    print(executive_summary)

    print("\n" + "=" * 60)
    print("  CONTROLS REQUIRED BASED ON DISCOVERED SYSTEMS")
    print("=" * 60)
    for host in final["hosts"]:
        print(f"\n{host['ip']}  (categories: {', '.join(host['categories'])})")
        all_controls = [c for controls in host["recommended_controls"].values() for c in controls]
        all_controls.sort(key=lambda c: c["adjusted_score"], reverse=True)
        for c in all_controls:
            print(f"  [{c['priority']:>8}] {c['control_id']}  (score={c['adjusted_score']:.2f})")
            for reason in c["reasons"]:
                print(f"             - {reason}")

    print("\n" + "=" * 60)
    print("  BASELINE CONTROLS RECOMMENDED FOR EVERY ENVIRONMENT")
    print("  (not tied to a specific scan finding - optional, but recommended")
    print("   for best security; priority reflects your interview answers)")
    print("=" * 60)
    for c in baseline_prioritized:
        print(f"  [{c['priority']:>8}] {c['control_id']}  (score={c['adjusted_score']:.2f})")
        for reason in c["reasons"]:
            print(f"             - {reason}")

    drafts = {}
    unique_top_ids = list({
        c["control_id"]
        for host in final["hosts"] for controls in host["recommended_controls"].values() for c in controls
        if c["priority"] in draft_language.DRAFT_TIERS
    } | {c["control_id"] for c in baseline_prioritized if c["priority"] in draft_language.DRAFT_TIERS})

    if unique_top_ids:
        print(f"\n{len(unique_top_ids)} unique Critical/High controls found. Drafting tailored policy language for")
        print("each takes roughly 1-1.5 minutes PER control on this machine, so drafting all of them could take")
        print(f"~{len(unique_top_ids)} to {len(unique_top_ids) * 2} minutes.")
        n = 0
        for attempt in range(2):
            try:
                n_raw = input(f"How many should I draft language for (0-{len(unique_top_ids)}, highest priority first, or 'all'/'none') [0]: ")
            except EOFError:
                break
            n = _parse_draft_count(n_raw, len(unique_top_ids))
            if n is not None:
                break
            print(f"  Didn't catch a number there — try a number 0-{len(unique_top_ids)}, or 'all' / 'none'.")
            n = 0

        if n > 0:
            # Highest-scoring occurrence of each control ID, across both sections.
            all_scored = [c for host in final["hosts"] for controls in host["recommended_controls"].values() for c in controls]
            all_scored += baseline_prioritized
            best_by_id = {}
            for c in all_scored:
                if c["control_id"] not in best_by_id or c["adjusted_score"] > best_by_id[c["control_id"]]["adjusted_score"]:
                    best_by_id[c["control_id"]] = c
            to_draft = sorted(
                (best_by_id[cid] for cid in unique_top_ids), key=lambda c: c["adjusted_score"], reverse=True
            )[:n]

            print()
            for i, c in enumerate(to_draft, start=1):
                print(f"Drafting {i}/{len(to_draft)}: {c['control_id']}...")
                drafts[c["control_id"]] = draft_language.draft_control_paragraph(c["control_id"], c["control_text"], context)

            print("\n" + "=" * 60)
            print("  DRAFT POLICY LANGUAGE")
            print("=" * 60)
            for control_id, text in drafts.items():
                print(f"\n--- {control_id} ---")
                print(text)
        skipped = len(unique_top_ids) - n
        if skipped > 0:
            print(f"\n({skipped} Critical/High control(s) not drafted - re-run and choose a higher number to include them.)")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    business_name = _sanitize_folder_name(context.get("business_name", "Unnamed Organization"))
    report_dir = _unique_report_folder(REPORTS_DIR, business_name)
    report_dir.mkdir(parents=True, exist_ok=True)
    if report_dir.name != business_name:
        print(f"\nA report folder named '{business_name}' already exists - saving this run to '{report_dir.name}' instead.")
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")

    json_path = _write_with_fallback(
        report_dir / f"report_{stamp}.json",
        lambda p: p.write_text(json.dumps({
            **final,
            "baseline_controls": baseline_prioritized,
            "executive_summary": executive_summary,
            "draft_language": drafts,
        }, indent=2)),
    )
    if json_path:
        print(f"\nMachine-readable report saved to {json_path.resolve()}")
    else:
        print("\nCould not save the JSON report - see warning above.")

    docx_path = _write_with_fallback(
        report_dir / f"report_{stamp}.docx",
        lambda p: docx_report.build_report(
            p, final, baseline_prioritized, context, executive_summary, drafts=drafts, scan_report=scan_report
        ),
    )
    if docx_path:
        print(f"Full report saved to {docx_path.resolve()}")
    else:
        print("Could not save the DOCX report - see warning above.")

    xlsx_path = _write_with_fallback(
        report_dir / f"report_{stamp}.xlsx",
        lambda p: xlsx_report.build_report(p, final, baseline_prioritized, executive_summary, drafts=drafts, business_name=business_name),
    )
    if xlsx_path:
        print(f"Spreadsheet saved to {xlsx_path.resolve()} - formatted as a filterable table, color-coded by priority.")
    else:
        print("Could not save the XLSX report - see warning above.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        try:
            input("\nAn error occurred (see above). Press Enter to close...")
        except EOFError:
            pass
