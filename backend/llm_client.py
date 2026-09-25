"""
Single access point for the local LLM (Qwen). Prefers a decoupled SIDECAR service and falls
back to in-process generation, so the same code works in production (lean API image + a
separate model container) and in dev (model loaded locally).

Resolution order for generate():
  1. if LLM_SERVICE_URL is set -> POST {messages, max_new_tokens} to the sidecar's /generate
     (stdlib urllib, no new dependency);
  2. else if the local Qwen dir is present and AI_TRIAGE_LLM is enabled -> load and generate
     in-process (lazy);
  3. else -> return None (callers degrade to a deterministic path).

Everything is best-effort: any failure returns None rather than raising, so the LLM can never
break the decision pipeline.
"""
import json
import os
import urllib.request
from pathlib import Path
from typing import Optional

import settings

BASE_DIR = Path(__file__).resolve().parent.parent
QWEN_PATH = BASE_DIR / "models" / "qwen2.5-1.5b-instruct"

LLM_SERVICE_URL = os.environ.get("LLM_SERVICE_URL", "").strip().rstrip("/")

_llm = None
_tok = None


def _local_enabled() -> bool:
    """Whether in-process local generation is enabled — read LIVE from settings (BC.1), so the
    AI-triage toggle can be flipped from the dashboard, gated by the model actually being present."""
    return bool(settings.get("AI_TRIAGE_LLM")) and QWEN_PATH.exists()


def available() -> bool:
    return bool(LLM_SERVICE_URL) or _local_enabled()


def _generate_sidecar(messages, max_new_tokens, timeout) -> Optional[str]:
    payload = json.dumps({"messages": messages, "max_new_tokens": max_new_tokens}).encode("utf-8")
    req = urllib.request.Request(f"{LLM_SERVICE_URL}/generate", data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8")).get("text")


def _load_local():
    global _llm, _tok
    if _llm is not None:
        return
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    _tok = AutoTokenizer.from_pretrained(str(QWEN_PATH))
    _llm = AutoModelForCausalLM.from_pretrained(str(QWEN_PATH), dtype=torch.float32)
    _llm.eval()


def _generate_local(messages, max_new_tokens) -> Optional[str]:
    import torch
    _load_local()
    text = _tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = _tok(text, return_tensors="pt")
    with torch.no_grad():
        out = _llm.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
    return _tok.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True).strip()


def generate(messages, max_new_tokens: int = 160, timeout: float = 30.0) -> Optional[str]:
    """Return the model's completion for a chat-message list, or None if no LLM is available
    or the call fails. Never raises."""
    try:
        if LLM_SERVICE_URL:
            return _generate_sidecar(messages, max_new_tokens, timeout)
        if _local_enabled():
            return _generate_local(messages, max_new_tokens)
    except Exception:
        return None
    return None
