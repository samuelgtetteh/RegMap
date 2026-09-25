"""
Interactive environment-context interview + prioritization engine.

network_scan.py finds resources; control_mapper.py finds semantically relevant
controls per resource category — but "relevant" isn't the same as "necessary."
A database on a home network and a database holding PHI at a hospital surface
the same category ("database") and the same raw candidate controls, but the
priority is completely different. This module closes that gap in two ways:

1. A base set of environment-defining questions, plus ADAPTIVE follow-up
   questions triggered by what was actually discovered (e.g. only ask about
   MFA if remote access was found) and by prior answers (e.g. only ask to
   confirm PHI handling if the sector is healthcare but PHI wasn't already
   named) — the interview gets more specific as it learns more, rather than
   asking a fixed list regardless of relevance.
2. Answers are interpreted by a small local LLM (llm_interview.py), invisibly
   — a user can type "we're a small medical clinic that keeps patient charts"
   and it resolves to sector=healthcare, with no fixed set of literal strings
   required and no visible mention that a model is involved at all. Cheap,
   instant, deterministic checks (an exact keyword, or a bare "yes"/"no")
   still short-circuit before the LLM is invoked at all — reserving the
   slower model for genuine free text is both faster for the common case and
   the reason the embedding-similarity approach tried first (semantic_answer.py)
   was replaced: sentence embeddings compare poorly when the user's answer is
   short and the option text is a full sentence, which is exactly the case
   where natural language flexibility matters most. The LLM asks its own
   natural follow-up questions when genuinely unsure, rather than a visible
   confidence score and a "press Enter to confirm" prompt.
"""
from pathlib import Path

import pandas as pd

import llm_interview
import semantic_answer

CORPUS_CSV = Path(__file__).parent.parent.parent / "data" / "processed" / "labeled_pairs.csv"

YES_NO_UNSURE_DESCRIPTIONS = {
    "yes": "Yes, this is true, in place, or enabled.",
    "no": "No, this is not true, not in place, or not enabled.",
    "unsure": "I don't know or am not sure about this.",
}

SECTOR_DESCRIPTIONS = {
    "healthcare": "A healthcare environment such as a hospital, clinic, or medical practice that treats patients and handles health records.",
    "financial_services": "A financial services environment such as a bank, credit union, insurer, or payment processor handling financial transactions.",
    "government_or_defense": "A government agency or defense contractor environment.",
    "critical_infrastructure_ot": "A critical infrastructure or operational technology environment such as power, water, oil and gas, or industrial control systems.",
    "general_business": "A general business or corporate office environment without specialized regulatory requirements.",
    "home_or_personal": "A home network or personal environment for individual, non-business use.",
    "lab_or_research_testing": "A lab, testing, research, or development/sandbox environment used for experimentation rather than production business operations.",
    "unsure": "I don't know what type of environment this is.",
}

REGULATED_DATA_DESCRIPTIONS = {
    "phi_hipaa": "Stores or processes protected health information (PHI) covered by HIPAA, such as patient medical records or health data.",
    "cardholder_data_pci": "Stores or processes payment card or credit card cardholder data covered by PCI DSS.",
    "cui_or_classified": "Stores or processes controlled unclassified information (CUI) or classified government information.",
    "general_pii": "Stores or processes general personally identifiable information such as names, addresses, or social security numbers.",
    "none": "Does not store or process any regulated or sensitive personal data.",
    "unsure": "I don't know what kind of data, if any, is stored or processed here.",
}

INTERNET_FACING_DESCRIPTIONS = {
    "yes": "Yes, one or more of these systems are reachable from the public internet.",
    "no": "No, these systems are only reachable from the internal network, not the internet.",
    "unsure": "I don't know whether these systems are reachable from the internet.",
}

MATURITY_DESCRIPTIONS = {
    "none_or_ad_hoc": "There is no formal security program; security is handled informally or ad hoc as issues come up.",
    "basic": "There is a basic security program with some policies but limited formal processes.",
    "established": "There is an established security program with documented policies and regular processes.",
    "mature": "There is a mature, well-resourced security program with continuous monitoring and improvement.",
    "unsure": "I don't know how mature our security program is.",
}

WEB_PUBLIC_DESCRIPTIONS = {
    "yes": "Yes, this web service is intentionally meant to be publicly accessible from the internet.",
    "no": "No, this web service should only be accessible internally and should not be exposed to the public internet.",
    "unsure": "I don't know whether this web service is meant to be public or internal-only.",
}

ENVIRONMENT_QUESTIONS = [
    {
        "id": "sector",
        "question": "What type of environment is this? (answer in your own words if you like)",
        "descriptions": SECTOR_DESCRIPTIONS,
    },
    {
        "id": "regulated_data",
        "question": "Does this environment store or process any regulated data? Describe it, or list types.",
        "descriptions": REGULATED_DATA_DESCRIPTIONS,
        "multi": True,
    },
    {
        "id": "internet_facing",
        "question": "Are any of the discovered hosts reachable from the public internet?",
        "descriptions": INTERNET_FACING_DESCRIPTIONS,
    },
    {
        "id": "maturity",
        "question": "How would you describe this environment's current security program maturity?",
        "descriptions": MATURITY_DESCRIPTIONS,
    },
]

# Adaptive follow-ups: only asked when `trigger` returns True given the union
# of discovered categories across all hosts and the answers collected so far.
# Evaluated in order, after the base questions, so later triggers can see
# earlier follow-up answers too.
FOLLOWUP_QUESTIONS = [
    {
        "id": "mfa_remote_access",
        "trigger": lambda categories, answers: bool({"remote_access", "remote_access_insecure"} & categories),
        "question": "Is multi-factor authentication (MFA) required for remote access to any discovered system?",
        "descriptions": YES_NO_UNSURE_DESCRIPTIONS,
    },
    {
        "id": "file_share_permissions",
        "trigger": lambda categories, answers: "file_sharing" in categories,
        "question": "Are the discovered file shares restricted by user/role-based permissions, not open to everyone?",
        "descriptions": YES_NO_UNSURE_DESCRIPTIONS,
    },
    {
        "id": "database_sensitive_data",
        "trigger": lambda categories, answers: "database" in categories,
        "question": "Does any discovered database store payment card, health, or other regulated data?",
        "descriptions": YES_NO_UNSURE_DESCRIPTIONS,
    },
    {
        "id": "web_intended_public",
        "trigger": lambda categories, answers: "web_insecure" in categories,
        "question": "Is the unencrypted web service found supposed to be publicly accessible from the internet?",
        "descriptions": WEB_PUBLIC_DESCRIPTIONS,
    },
    {
        "id": "written_policy_check",
        "trigger": lambda categories, answers: answers.get("maturity") in ("unsure", "none_or_ad_hoc"),
        "question": "Do you currently have a written security policy or acceptable use policy?",
        "descriptions": YES_NO_UNSURE_DESCRIPTIONS,
    },
    {
        "id": "phi_confirmation",
        "trigger": lambda categories, answers: (
            answers.get("sector") == "healthcare"
            and "phi_hipaa" not in answers.get("regulated_data", [])
        ),
        "question": "You indicated a healthcare environment - does it store or transmit patient health information (PHI)?",
        "descriptions": YES_NO_UNSURE_DESCRIPTIONS,
    },
]

# Plain-language explanations per question, used when the person answering
# signals confusion (llm_interview.py checks for this deterministically,
# rather than trusting the model to both recognize confusion AND generate an
# accurate explanation in one pass — tested and found unreliable: asked to
# explain PHI, the model just asked another clarifying question instead).
# Written for a non-specialist (e.g. "I'm just the IT director") — plain
# words, concrete examples, no jargon.
GLOSSARY = {
    "sector": "This is just asking what kind of organization or place this is - for example a medical clinic, a bank, a government office, a home network, or a research/testing lab.",
    "regulated_data": "This is asking whether you store information that has special legal protection - like patient health records, credit card numbers, government classified info, or basic personal details like names and social security numbers.",
    "internet_facing": "This is asking whether any of your computers or servers can be reached from outside your building over the internet, or if they're only reachable from inside your own network.",
    "maturity": "This is asking how organized your security practices are - for example, do you have written policies and regular reviews, or is security handled informally, case by case, without a formal plan?",
    "mfa_remote_access": "MFA (multi-factor authentication) means requiring more than just a password to log in remotely - for example also entering a code sent to your phone.",
    "file_share_permissions": "This is asking whether your shared files or folders are limited to specific people or teams, or whether anyone on the network can open them.",
    "database_sensitive_data": "This is asking whether the database contains information like patient records, payment card numbers, or other data with special legal protection.",
    "web_intended_public": "This is asking whether the website found was something you meant to be accessible to anyone on the internet, or whether it was only supposed to be used internally by your team.",
    "written_policy_check": "A written security policy is a documented set of rules about things like passwords, who can access what data, and acceptable computer use - as opposed to handling things informally with nothing written down.",
    "phi_confirmation": "PHI stands for Protected Health Information - things like a patient's name linked to their medical records, diagnoses, treatment history, appointment records, or insurance details. Even a simple patient list or appointment log usually counts.",
}

# Categories whose exposure risk is meaningfully worse when internet-facing.
INTERNET_RISK_CATEGORIES = {
    "web_insecure", "remote_access", "remote_access_insecure",
    "file_transfer_insecure", "database", "file_sharing",
}

# Control families prioritized first for low-maturity environments — the
# essentials (access control, authentication, transmission/system protection,
# configuration management) before program-management-heavy families.
BASELINE_FAMILIES_FOR_LOW_MATURITY = {"AC", "IA", "SC", "CM", "SI"}

# Every value of a boost condition gets a defined weight, including "unsure" —
# nothing silently does nothing just because the user wasn't certain.
MATURITY_BOOST = {"none_or_ad_hoc": 0.15, "basic": 0.08, "unsure": 0.08, "established": 0.0, "mature": 0.0}
INTERNET_FACING_BOOST = {"yes": 0.20, "unsure": 0.10, "no": 0.0}


def _ask_one(q, input_fn, max_confusion_loops=2):
    """Cheap, instant, deterministic checks first — a literal keyword or a
    bare yes/no/none needs no model at all and resolves immediately. Anything
    more descriptive is handed to the LLM, which asks its own natural
    follow-up questions when genuinely unsure rather than showing a visible
    confidence score. Nothing about a model is ever surfaced to the user;
    this should read as a normal, if slightly perceptive, interview.

    Confusion ("I don't know what you mean, can you explain?") is detected
    and answered deterministically from GLOSSARY, not left to the model —
    tested and found unreliable: asked to explain a term, the 1.5B model
    just asked another clarifying question instead of actually explaining."""
    print(f"{q['question']}")

    for _ in range(max_confusion_loops + 1):
        try:
            raw = input_fn("> ")
        except EOFError:
            return ["unsure"] if q.get("multi") else "unsure"

        if not raw.strip():
            return ["unsure"] if q.get("multi") else "unsure"

        if llm_interview.seems_confused(raw) and q["id"] in GLOSSARY:
            print(f"{GLOSSARY[q['id']]}")
            print(f"{q['question']}")
            continue

        exact = semantic_answer._exact_match(raw, q["descriptions"])
        if exact and not q.get("multi"):
            return exact

        affirm_neg = semantic_answer._affirmation_negation_match(raw, q["descriptions"])
        if affirm_neg:
            return affirm_neg if not q.get("multi") else [affirm_neg]

        return llm_interview.interpret_conversationally(q, raw, input_fn, glossary_text=GLOSSARY.get(q["id"]))

    return ["unsure"] if q.get("multi") else "unsure"


def run_interview(categories=None, input_fn=input):
    """CLI-interactive by default (input_fn=input); pass a different input_fn
    (e.g. a queue-backed function) to drive this from an API session instead.
    `categories` is the union of resource categories found across the scan —
    used to decide which adaptive follow-ups are relevant."""
    categories = set(categories or [])
    answers = {}

    print("\n--- Environment Context Interview ---")
    print("A few questions about this environment to help decide which controls actually")
    print("matter here. Answer in your own words - if you're not sure, just say so.")
    print("Everything stays local; nothing is sent anywhere.\n")

    print("What's the name of this business or organization? (used to label the report, stays local)")
    try:
        business_name = input_fn("> ").strip()
    except EOFError:
        business_name = ""
    answers["business_name"] = business_name or "Unnamed Organization"
    print()

    for q in ENVIRONMENT_QUESTIONS:
        answers[q["id"]] = _ask_one(q, input_fn)
        print()

    followups_asked = 0
    for q in FOLLOWUP_QUESTIONS:
        if q["trigger"](categories, answers):
            answers[q["id"]] = _ask_one(q, input_fn)
            followups_asked += 1
            print()

    if followups_asked == 0:
        print("(No follow-up questions were triggered by this scan's findings.)\n")

    return answers


def _hipaa_relevant_control_ids():
    df = pd.read_csv(CORPUS_CSV)
    return set(df["nist_control_id"].unique())


def _control_family(control_id):
    return control_id.split("-")[0]


def prioritize_control(control, category, context):
    """Returns (tier, adjusted_score, reasons) for one candidate control given
    the discovered category (or 'baseline' for non-scan-driven controls) and
    the interview context."""
    score = control["score"]
    reasons = ([f"Semantic match to '{category}' (similarity {control['score']:.2f})"]
               if category != "baseline"
               else ["Recommended as a foundational control for every environment"])

    regulated = set(context.get("regulated_data", []))
    if "phi_hipaa" in regulated and control["control_id"] in _hipaa_relevant_control_ids():
        score += 0.25
        reasons.append("Maps to a HIPAA-relevant control - environment reports handling PHI")
    elif "unsure" in regulated and control["control_id"] in _hipaa_relevant_control_ids():
        score += 0.08
        reasons.append("Regulated-data status is unconfirmed - treating cautiously as potentially in scope")

    if context.get("phi_confirmation") == "yes" and control["control_id"] in _hipaa_relevant_control_ids():
        score += 0.25
        reasons.append("Confirmed via follow-up: environment stores/transmits PHI")

    net_boost = INTERNET_FACING_BOOST.get(context.get("internet_facing"), 0.0)
    if net_boost and category in INTERNET_RISK_CATEGORIES:
        score += net_boost
        reasons.append(f"'{category}' internet exposure is {context.get('internet_facing')} (risk weighting applied)")

    maturity_boost = MATURITY_BOOST.get(context.get("maturity"), 0.0)
    if maturity_boost and (category == "baseline" or _control_family(control["control_id"]) in BASELINE_FAMILIES_FOR_LOW_MATURITY):
        score += maturity_boost
        reasons.append("Part of the essential baseline recommended given reported/uncertain program maturity")

    if context.get("sector") == "critical_infrastructure_ot" and category in ("remote_access", "remote_access_insecure"):
        score += 0.20
        reasons.append("Remote access to OT/critical infrastructure environments carries elevated risk")

    if context.get("mfa_remote_access") in ("no", "unsure") and category in ("remote_access", "remote_access_insecure") and control["control_id"] == "AC-17":
        score += 0.15
        reasons.append(f"MFA on remote access is '{context.get('mfa_remote_access')}' - access control gap likely")

    if context.get("file_share_permissions") in ("no", "unsure") and category == "file_sharing":
        score += 0.15
        reasons.append(f"File share permission enforcement is '{context.get('file_share_permissions')}'")

    if context.get("database_sensitive_data") == "yes" and category == "database":
        score += 0.20
        reasons.append("Confirmed via follow-up: discovered database holds regulated/sensitive data")

    if context.get("web_intended_public") == "no" and category == "web_insecure":
        score += 0.30
        reasons.append("This web service was NOT supposed to be internet-facing - likely a misconfiguration exposing it unintentionally")
    elif context.get("web_intended_public") == "unsure" and category == "web_insecure":
        score += 0.10
        reasons.append("Whether this web service is intentionally public is unconfirmed - treating cautiously")

    if score >= 0.75:
        tier = "Critical"
    elif score >= 0.55:
        tier = "High"
    elif score >= 0.40:
        tier = "Medium"
    else:
        tier = "Low"

    return tier, round(score, 4), reasons


def prioritize_scan_recommendations(scan_recommendations, context):
    """scan_recommendations: output of control_mapper.recommend_for_scan().
    Returns the same host structure with each control annotated with a
    priority tier, adjusted score, and explanation."""
    output_hosts = []
    for host in scan_recommendations["hosts"]:
        prioritized = {}
        for category, controls in host["recommended_controls"].items():
            annotated = []
            for control in controls:
                tier, score, reasons = prioritize_control(control, category, context)
                annotated.append({**control, "priority": tier, "adjusted_score": score, "reasons": reasons})
            annotated.sort(key=lambda c: c["adjusted_score"], reverse=True)
            prioritized[category] = annotated
        output_hosts.append({"ip": host["ip"], "categories": host["categories"], "recommended_controls": prioritized})

    return {"cidr": scan_recommendations["cidr"], "context": context, "hosts": output_hosts}


def prioritize_baseline_controls(baseline_controls, context):
    """baseline_controls: output of baseline_controls.load_baseline_controls().
    These aren't tied to a specific host/category, but still get the same
    explainable prioritization treatment against the interview context."""
    annotated = []
    for control in baseline_controls:
        tier, score, reasons = prioritize_control(control, "baseline", context)
        annotated.append({**control, "priority": tier, "adjusted_score": score, "reasons": reasons})
    annotated.sort(key=lambda c: c["adjusted_score"], reverse=True)
    return annotated


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("Usage: python interview.py <recommendations.json>")
        sys.exit(1)

    with open(sys.argv[1]) as f:
        recs = json.load(f)

    all_categories = {c for host in recs["hosts"] for c in host["categories"]}
    context = run_interview(categories=all_categories)
    result = prioritize_scan_recommendations(recs, context)
    print(json.dumps(result, indent=2))
