"""
LLM-based natural-language interpretation for interview answers — invisible
to the user. No scores, no "interpreted as X (confidence Y)", no mention of
AI or models anywhere in the output. When the model needs more information,
it asks its own natural follow-up question and the conversation just
continues, the way a person conducting the interview would.

Uses Qwen2.5-1.5B-Instruct (models/qwen2.5-1.5b-instruct/), chosen after
head-to-head testing against Qwen2.5-0.5B-Instruct on this exact task:
0.5B was unreliable (it defaulted to "general_business" even when shown the
correct answer as a labeled few-shot example moments earlier — a real
mode-collapse failure, not a fluke), while 1.5B classified every test case
correctly, including the ones 0.5B got wrong. Costs ~3GB on disk and roughly
7-12s per turn on CPU — accepted deliberately, because a wrong classification
here silently drives the whole report's control recommendations, so
reliability matters more than latency for a once-per-question interview.
"""
import json
import re
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_PATH = Path(__file__).parent.parent.parent / "models" / "qwen2.5-1.5b-instruct"

CONFUSION_SIGNALS = (
    "don't know what", "dont know what", "don't understand", "dont understand",
    "not sure what", "what do you mean", "what does that mean", "can you explain",
    "help me understand", "i'm confused", "im confused", "what is that", "what's that",
    "no idea what", "unclear what",
)


def seems_confused(raw):
    """Detected deterministically rather than left to the model — tested and
    found unreliable: asked to explain a confusing term, the 1.5B model just
    asked another clarifying question instead of actually explaining it."""
    v = raw.strip().lower()
    return any(signal in v for signal in CONFUSION_SIGNALS)


import threading as _threading

_model = None
_tokenizer = None
_load_lock = _threading.Lock()


def _load():
    global _model, _tokenizer
    if _model is not None:
        return
    # Serialize loading so concurrent callers (e.g. a warmup thread + a request) don't each load a
    # copy and blow past memory. Load in bfloat16 with low_cpu_mem_usage to roughly halve resident
    # RAM (~3GB vs ~6GB for a 1.5B model) so it fits an 8GB Docker/WSL2 VM; fall back to float32.
    with _load_lock:
        if _model is not None:
            return
        _tokenizer = AutoTokenizer.from_pretrained(str(MODEL_PATH))
        try:
            _model = AutoModelForCausalLM.from_pretrained(
                str(MODEL_PATH), dtype=torch.bfloat16, low_cpu_mem_usage=True)
        except Exception:
            _model = AutoModelForCausalLM.from_pretrained(
                str(MODEL_PATH), dtype=torch.float32, low_cpu_mem_usage=True)
        _model.eval()


def _build_system_prompt(question, multi):
    options_block = "\n".join(
        f"- {key}: {desc}" for key, desc in question["descriptions"].items() if key != "unsure"
    )
    if multi:
        multi_note = "Multiple categories can apply at once — respond with a JSON list of all that apply."
        decision_format = '{"decision": ["<category>", ...]}'
    else:
        multi_note = "Exactly one category applies."
        decision_format = '{"decision": "<category>"}'

    return f"""You are having a normal, natural conversation with someone to understand their computer network environment, so you can privately decide which of the categories below applies. {multi_note} The person you're talking to must never find out that categories, classification, or an AI are involved — you're just a knowledgeable colleague asking questions.

Question being answered: {question['question']}

Categories (for your own internal use only — NEVER say these words, or "category"/"classify"/"label", to the person):
{options_block}
- unsure: genuinely unclear or not stated

Given the full conversation, decide:
1. Does the person's most recent answer actually address this question? Sometimes people describe something unrelated (e.g. what their organization does, instead of how mature their security program is) — that is NOT an answer to this question, even if it sounds detailed and confident.
2. Does the person seem confused, say they don't understand, ask what a term means, or ask for help? Treat this as a real request — answer it.

Based on that:
- If their answer genuinely and directly addresses this question, and you're confident which category fits, respond with ONLY: {decision_format}
- Otherwise (their answer didn't address the question, OR they're confused, OR they asked you to explain something), respond with ONLY: {{"clarify": "<your response>"}}
  - If they seem confused or asked what something means, FIRST briefly explain the relevant idea in one or two plain, jargon-free sentences (a real answer to their question, not a brush-off), THEN gently re-ask what you need to know in simpler words.
  - If their answer was just off-topic, acknowledge what they said naturally and steer back to what you actually asked, without being repetitive or robotic.
  - Never say "category", "classify", "label", "the appropriate option", or anything that reveals this is a structured decision. Write only as a person continuing a normal conversation.

Respond with ONLY the JSON object, nothing else, no explanation."""


def _generate(messages, max_new_tokens=80):
    _load()
    text = _tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = _tokenizer(text, return_tensors="pt")
    with torch.no_grad():
        output = _model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
    return _tokenizer.decode(output[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True).strip()


def _parse_response(text, valid_options, multi):
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        obj = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None

    if "decision" in obj:
        decision = obj["decision"]
        if multi:
            if isinstance(decision, str):
                decision = [decision]
            valid = [d for d in decision if d in valid_options]
            return {"type": "decision", "value": valid or ["unsure"]}
        if isinstance(decision, list):
            decision = decision[0] if decision else "unsure"
        return {"type": "decision", "value": decision if decision in valid_options else "unsure"}

    if "clarify" in obj and isinstance(obj["clarify"], str) and obj["clarify"].strip():
        return {"type": "clarify", "value": obj["clarify"].strip()}

    return None


def interpret_conversationally(question, first_answer, input_fn, max_turns=3, glossary_text=None):
    """Runs the whole multi-turn clarification loop itself, asking its own
    natural follow-up questions via input_fn when it needs more information.
    Returns the final decision: a string, or a list of strings if
    question.get('multi') is True. Falls back to 'unsure' if the model can't
    reach a decision within max_turns, or if input runs out.

    If the person seems confused at any point and a glossary_text is
    available for this question, that's answered directly and deterministically
    (see seems_confused) rather than handed to the model — the confused reply
    is never added to the model's conversation, and the model's own follow-up
    is re-asked once the explanation has been given."""
    multi = question.get("multi", False)
    valid_options = set(question["descriptions"].keys())
    unsure_result = ["unsure"] if multi else "unsure"

    messages = [
        {"role": "system", "content": _build_system_prompt(question, multi)},
        {"role": "user", "content": first_answer},
    ]

    for _ in range(max_turns):
        raw_response = _generate(messages)
        parsed = _parse_response(raw_response, valid_options, multi)

        if parsed is None:
            # Malformed output from the model — never surface this to the
            # user; just nudge it to retry rather than exposing the glitch.
            messages.append({"role": "assistant", "content": raw_response})
            messages.append({"role": "user", "content": "(Please respond with ONLY the JSON object as instructed.)"})
            continue

        if parsed["type"] == "decision":
            return parsed["value"]

        messages.append({"role": "assistant", "content": raw_response})
        follow_up = parsed["value"]

        while True:
            try:
                next_answer = input_fn(f"{follow_up} > ")
            except EOFError:
                return unsure_result
            if not next_answer.strip():
                return unsure_result
            if glossary_text and seems_confused(next_answer):
                print(glossary_text)
                follow_up = question["question"]
                continue
            break

        messages.append({"role": "user", "content": next_answer})

    return unsure_result
