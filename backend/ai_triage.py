"""
AI triage layer (Track E): per-alert analyst support, grounded by retrieval (RAG) over the
compliance corpus and written/scored by the local LLM (via backend/llm_client.py, which prefers
a sidecar service and falls back to in-process Qwen).

Two capabilities:
  * triage(alert)  -> a concise analyst summary + the most relevant HIPAA provisions (RAG).
  * assess(alert)  -> an ADVISORY prioritization: {priority (1-5), disposition
    (escalate|monitor|likely_false_positive), rationale}. The LLM re-ranks/labels, but priority is
    CLAMPED to a severity floor so it can never bury a high-severity alert, and everything degrades
    to a deterministic default if no LLM is available. The LLM is never authoritative (it reads
    attacker-controlled fields, so it advises; deterministic rules + humans enforce).

Lazy, gated, best-effort: heavy models load on first use; retrieval/generation failures fall back
to deterministic behaviour rather than raising.
"""
import json
import os
import re
from pathlib import Path

import llm_client
from verdict_store import subject_outcome_history

BASE_DIR = Path(__file__).resolve().parent.parent
EMBED_PATH = BASE_DIR / "models" / "regmap-embedder"
CORPUS_CSV = BASE_DIR / "data" / "processed" / "training_pairs.csv"

TRIAGE_ENABLED = os.environ.get("AI_TRIAGE_ENABLED", "1").lower() not in ("0", "false", "")
TOP_K = int(os.environ.get("AI_TRIAGE_TOPK", "3"))

# priority scale 1-5 (5 = most urgent). Deterministic default + floor per severity.
SEVERITY_DEFAULT = {"high": 4, "medium": 2, "low": 1}
SEVERITY_FLOOR = {"high": 3, "medium": 2, "low": 1}
DISPOSITIONS = {"escalate", "monitor", "likely_false_positive"}

_embedder = None
_corpus = None
_corpus_emb = None


def _load_retriever():
    global _embedder, _corpus, _corpus_emb
    if _embedder is not None:
        return
    import pandas as pd
    from sentence_transformers import SentenceTransformer
    _embedder = SentenceTransformer(str(EMBED_PATH))
    df = pd.read_csv(CORPUS_CSV)
    _corpus = df["hipaa_text"].dropna().unique().tolist()
    _corpus_emb = _embedder.encode(_corpus, convert_to_tensor=True)


def _retrieve(query: str, k: int = TOP_K) -> list[dict]:
    try:
        _load_retriever()
        import torch
        qe = _embedder.encode(query, convert_to_tensor=True)
        scores = torch.nn.functional.cosine_similarity(qe, _corpus_emb)
        idx = torch.topk(scores, k=min(k, len(_corpus))).indices.tolist()
        return [{"provision": _corpus[i][:240], "score": round(float(scores[i]), 4)} for i in idx]
    except Exception:
        return []


def _reason(alert: dict) -> str:
    d = alert.get("detail") or {}
    if isinstance(d, dict) and d.get("reason"):
        return d["reason"]
    return f"{alert.get('verdict_count')} contributing verdict(s)"


def _query_for(alert: dict) -> str:
    return (f"{alert.get('rule')} {alert.get('model')} "
            f"{alert.get('subject') or ''} {_reason(alert)}").strip()


def _templated_summary(alert: dict, context: list[dict]) -> str:
    prov = context[0]["provision"] if context else "n/a"
    return (f"{str(alert.get('severity', '?')).upper()} {alert.get('rule')} on "
            f"{alert.get('model')}/{alert.get('subject')}: {_reason(alert)}. "
            f"Most relevant control context: {prov}")


def triage(alert: dict) -> dict:
    if not (TRIAGE_ENABLED and alert):
        return {"enabled": False, "summary": None, "related_controls": [], "llm_used": False}
    context = _retrieve(_query_for(alert))
    summary, llm_used = None, False
    if llm_client.available():
        ctx_block = "\n".join(f"- {c['provision']}" for c in context) or "- (none)"
        messages = [
            {"role": "system",
             "content": ("You are a SOC analyst assistant. Given a security alert and the related "
                         "compliance controls, write a concise 2-3 sentence triage: what happened, "
                         "why it matters, and a recommended next action. Be specific and factual; "
                         "do not invent details.")},
            {"role": "user",
             "content": f"ALERT: {_templated_summary(alert, context)}\n\nRELATED COMPLIANCE CONTROLS:\n{ctx_block}"},
        ]
        summary = llm_client.generate(messages, max_new_tokens=180)
        llm_used = bool(summary)
    if not summary:
        summary = _templated_summary(alert, context)
    return {"enabled": True, "summary": summary, "related_controls": context, "llm_used": llm_used}


def default_priority(severity: str) -> int:
    return SEVERITY_DEFAULT.get(severity, 2)


def assess(alert: dict) -> dict:
    """ADVISORY prioritization for an alert. Returns {priority, disposition, rationale, llm_used}.
    Falls back to the deterministic severity default (and no disposition) when no LLM is available;
    priority is always clamped to the severity floor."""
    severity = alert.get("severity", "medium")
    floor = SEVERITY_FLOOR.get(severity, 2)
    base = default_priority(severity)

    if not llm_client.available():
        return {"priority": base, "disposition": None,
                "rationale": "LLM unavailable; deterministic severity default.", "llm_used": False}

    context = _retrieve(_query_for(alert))
    history = subject_outcome_history(alert.get("subject"), alert.get("model"))
    ctx_block = "\n".join(f"- {c['provision']}" for c in context) or "- (none)"
    messages = [
        {"role": "system",
         "content": ("You are a SOC triage assistant. Assess the alert for analyst prioritization. "
                     "Respond with ONLY a JSON object and nothing else: "
                     '{"priority": <integer 1-5, 5=most urgent>, '
                     '"disposition": "escalate" | "monitor" | "likely_false_positive", '
                     '"rationale": "<one short sentence>"}. Consider the subject\'s historical '
                     "outcomes: many prior confirmed-benign verdicts suggest a likely false "
                     "positive; confirmed-malicious history suggests escalate.")},
        {"role": "user",
         "content": (f"ALERT: {_templated_summary(alert, context)}\n"
                     f"SUBJECT HISTORY (labelled outcomes): malicious={history['malicious']}, "
                     f"benign={history['benign']}\n"
                     f"RELATED COMPLIANCE CONTROLS:\n{ctx_block}")},
    ]
    raw = llm_client.generate(messages, max_new_tokens=120)
    if not raw:
        return {"priority": base, "disposition": None,
                "rationale": "LLM call failed; deterministic default.", "llm_used": False}

    # parse the JSON object out of the completion; validate + clamp
    priority, disposition, rationale = base, None, None
    try:
        obj = json.loads(re.search(r"\{.*\}", raw, re.DOTALL).group(0))
        p = int(obj.get("priority", base))
        priority = max(floor, min(5, p))                      # clamp to [floor, 5]
        d = str(obj.get("disposition", "")).strip().lower()
        disposition = d if d in DISPOSITIONS else "monitor"
        rationale = str(obj.get("rationale", "")).strip()[:300] or None
    except Exception:
        return {"priority": base, "disposition": None,
                "rationale": "Could not parse LLM output; deterministic default.", "llm_used": False}

    return {"priority": priority, "disposition": disposition,
            "rationale": rationale, "llm_used": True}
