"""
Generates tailored draft control language and an executive summary, reusing
the same local LLM already loaded for the interview (llm_interview.py) — no
new model, no new download. This is a different task than the interview's
classification: pure generation, turning a heavily templated NIST control
("[Assignment: org-defined]" placeholders and all) into an actionable
paragraph for this specific environment, and turning a list of findings into
a short narrative a non-technical stakeholder could actually read.

Scope note: draft language is only generated for Critical/High priority
controls, deduplicated by control ID — generating it for every recommended
control (sometimes 30+, often repeated across hosts) would take many minutes
on CPU for no real benefit, since Medium/Low items are lower stakes by
definition. This is a stated cap, not a silent one — the report and CLI
output both say exactly how many controls got drafted language and why the
rest didn't.
"""
import llm_interview

DRAFT_TIERS = {"Critical", "High"}


def draft_control_paragraph(control_id, control_text, context):
    system_prompt = f"""You write clear, actionable security policy language for a specific organization, based on a NIST SP 800-53 control template.

The template often contains bracketed placeholders like [Assignment: org-defined] describing things the organization must decide for itself (a time period, a list of roles, a specific mechanism, etc). Replace these placeholders with sensible, concrete choices appropriate for the described environment — do not leave any brackets in your answer.

Environment context:
- Sector: {context.get('sector', 'unspecified')}
- Regulated data: {', '.join(context.get('regulated_data', []) or []) or 'unspecified'}
- Internet-facing: {context.get('internet_facing', 'unspecified')}
- Security program maturity: {context.get('maturity', 'unspecified')}

NIST Control {control_id}: {control_text}

Write a short (3-5 sentence) draft policy paragraph implementing this control for this specific organization. Write it as finished policy text, not advice about how to write policy. Do not use placeholder brackets."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Write the policy paragraph."},
    ]
    return llm_interview._generate(messages, max_new_tokens=200)


def draft_language_for_report(final_report, baseline_prioritized, context, progress_callback=None):
    """Collects unique Critical/High controls across both scan-findings and
    baseline sections, drafts language once per unique control ID (reused if
    the same control appears for multiple hosts), and returns {control_id: draft_text}."""
    unique_controls = {}
    for host in final_report["hosts"]:
        for controls in host["recommended_controls"].values():
            for c in controls:
                if c["priority"] in DRAFT_TIERS and c["control_id"] not in unique_controls:
                    unique_controls[c["control_id"]] = c["control_text"]
    for c in baseline_prioritized:
        if c["priority"] in DRAFT_TIERS and c["control_id"] not in unique_controls:
            unique_controls[c["control_id"]] = c["control_text"]

    drafts = {}
    total = len(unique_controls)
    for i, (control_id, control_text) in enumerate(unique_controls.items(), start=1):
        if progress_callback:
            progress_callback(i, total, control_id)
        drafts[control_id] = draft_control_paragraph(control_id, control_text, context)
    return drafts


def generate_executive_summary(final_report, baseline_prioritized, context):
    all_controls = []
    for host in final_report["hosts"]:
        for category, controls in host["recommended_controls"].items():
            for c in controls:
                all_controls.append({**c, "host": host["ip"], "category": category})
    all_controls.extend({**c, "host": None, "category": "baseline"} for c in baseline_prioritized)

    critical = [c for c in all_controls if c["priority"] == "Critical"]
    high = [c for c in all_controls if c["priority"] == "High"]
    other_count = len(all_controls) - len(critical) - len(high)

    top_findings = "\n".join(
        f"- {c['control_id']} ({c['priority']}) on {c['host'] or 'organization-wide'}: {c['reasons'][0]}"
        for c in (critical + high)[:8]
    ) or "- No Critical or High priority findings."

    system_prompt = f"""You write a short executive summary of a security control assessment for a non-technical stakeholder (e.g. a business owner or compliance officer, not a security engineer).

Environment: {context.get('sector', 'unspecified')} sector, security program maturity reported as {context.get('maturity', 'unspecified')}.
Total findings: {len(critical)} Critical, {len(high)} High priority, {other_count} Medium/Low priority.

Top findings:
{top_findings}

Write a 4-6 sentence executive summary: what was found, why it matters in plain language, and the overall risk picture. Do not use jargon like "NIST 800-53" or cite control IDs — describe the underlying risks in plain English. Do not recommend specific next steps, just summarize the situation."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Write the summary."},
    ]
    return llm_interview._generate(messages, max_new_tokens=250)
