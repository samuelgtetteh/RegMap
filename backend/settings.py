"""
Runtime settings registry — the single source of truth for the operational limits and thresholds
a user can personalize from the dashboard (BC.1 of docs/browser_control_plan.md).

Previously these values were frozen from environment variables at import, so changing one meant
editing env + restarting the container. Now the REGISTRY below defines each tunable (type, range,
label, help, and its env/coded default), values are read LIVE at the point of use, and overrides
are persisted in the verdict_store `settings` table. A change takes effect on the next verdict /
evaluate — no restart. Deleting an override reverts the tunable to its default.

Design:
  * verdict_store owns storage + a lock-free cache (get_setting*/set_setting_values/reset_settings)
    and has NO knowledge of this registry, so there is no import cycle (settings -> verdict_store).
  * Consumers (policy.py, app.py, llm_client.py) call settings.get("KEY") for the effective value.
  * Defaults come from env at import (preserving current deployment behaviour); the registry just
    makes them editable, validated, and grouped for the UI.
"""
import os

import verdict_store as store


def _env_int(key, default):
    try:
        return int(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


def _env_float(key, default):
    try:
        return float(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


def _env_bool(key, default):
    raw = os.environ.get(key)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off", "")


# Each entry: key, type, default (env-resolved), optional min/max/step, group, label, help.
REGISTRY = [
    # --- Log retention (FIFO caps) : bound how much live-monitoring history is kept ---
    {"key": "MAX_VERDICTS", "type": "int", "default": store.MAX_VERDICTS,
     "min": 0, "max": 100_000_000, "step": 1000,
     "group": "Log retention (FIFO caps)", "label": "Max verdicts kept",
     "help": "Oldest verdicts are evicted beyond this. 0 = unbounded."},
    {"key": "MAX_REQUESTS", "type": "int", "default": store.MAX_REQUESTS,
     "min": 0, "max": 100_000_000, "step": 1000,
     "group": "Log retention (FIFO caps)", "label": "Max audited requests kept",
     "help": "Cap on the non-scored request audit table. 0 = unbounded."},
    {"key": "MAX_ACTIONS", "type": "int", "default": store.MAX_ACTIONS,
     "min": 0, "max": 100_000_000, "step": 1000,
     "group": "Log retention (FIFO caps)", "label": "Max response actions kept",
     "help": "Cap on the recorded responder-action table. 0 = unbounded."},
    {"key": "RETENTION_TRIM_EVERY", "type": "int", "default": store.RETENTION_TRIM_EVERY,
     "min": 1, "max": 100000, "step": 10,
     "group": "Log retention (FIFO caps)", "label": "Trim cadence (inserts)",
     "help": "Run the FIFO trim once every N inserts (batched to amortize cost)."},

    # --- Detection policy : how aggressively the Decide layer raises alerts ---
    {"key": "DECISION_WINDOW_SECONDS", "type": "int", "default": _env_int("DECISION_WINDOW_SECONDS", 300),
     "min": 10, "max": 86400, "step": 30,
     "group": "Detection policy", "label": "Decision window (seconds)",
     "help": "Trailing window the rules evaluate over."},
    {"key": "IDENTITY_BURST_MIN", "type": "int", "default": _env_int("IDENTITY_BURST_MIN", 3),
     "min": 1, "max": 1000, "step": 1,
     "group": "Detection policy", "label": "Identity burst threshold",
     "help": "Flagged logins from one subject in the window before a burst alert."},
    {"key": "ICS_SUSTAINED_MIN", "type": "int", "default": _env_int("ICS_SUSTAINED_MIN", 3),
     "min": 1, "max": 1000, "step": 1,
     "group": "Detection policy", "label": "ICS sustained threshold",
     "help": "Flagged ICS ticks in the window before a sustained-event alert."},
    {"key": "ICS_SEVERE_ERROR", "type": "float", "default": _env_float("ICS_SEVERE_ERROR", 1.0),
     "min": 0.0, "max": 1000.0, "step": 0.1,
     "group": "Detection policy", "label": "ICS severe-error threshold",
     "help": "Reconstruction error at/above this raises a single-event high-severity alert."},
    {"key": "IDENTITY_SEVERE", "type": "float", "default": _env_float("IDENTITY_SEVERE", -0.1),
     "min": -1.0, "max": 1.0, "step": 0.01,
     "group": "Detection policy", "label": "Identity severe-score threshold",
     "help": "IsolationForest score at/below this raises a single-event high-severity alert."},
    {"key": "DECISION_SUPPRESS_MIN", "type": "int", "default": _env_int("DECISION_SUPPRESS_MIN", 3),
     "min": 1, "max": 1000, "step": 1,
     "group": "Detection policy", "label": "Outcome-weighting min history",
     "help": "Min labelled history before a subject's outcomes suppress/escalate its alerts."},

    # --- Compliance mapping ---
    {"key": "REGMAP_FLAG_THRESHOLD", "type": "float", "default": _env_float("REGMAP_FLAG_THRESHOLD", 0.5),
     "min": 0.0, "max": 1.0, "step": 0.01,
     "group": "Compliance mapping", "label": "Low-confidence flag threshold",
     "help": "A NIST->HIPAA mapping with top-1 similarity below this is flagged low-confidence."},

    # --- AI triage ---
    {"key": "AI_TRIAGE_LLM", "type": "bool", "default": _env_bool("AI_TRIAGE_LLM", True),
     "group": "AI triage", "label": "Enable local LLM triage",
     "help": "Use the local language model to write triage summaries (advisory only). "
             "When off, triage/assess fall back to the deterministic templated path."},
]

_BY_KEY = {r["key"]: r for r in REGISTRY}


def keys() -> list:
    return [r["key"] for r in REGISTRY]


def get(key: str):
    """Effective (typed) value for a setting: the stored override if present and valid, else its
    coded/env default. This is what consumers call at the point of use."""
    spec = _BY_KEY.get(key)
    if spec is None:
        raise KeyError(f"unknown setting '{key}'")
    t, d = spec["type"], spec["default"]
    if t == "int":
        return store.get_setting_int(key, d)
    if t == "float":
        return store.get_setting_float(key, d)
    if t == "bool":
        return store.get_setting_bool(key, d)
    return store.get_setting(key, d)


def effective() -> dict:
    return {r["key"]: get(r["key"]) for r in REGISTRY}


def _validate(spec: dict, value):
    """Coerce `value` to the setting's type and range-check it; returns the native value."""
    t = spec["type"]
    if t == "bool":
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes", "on")
    try:
        v = int(value) if t == "int" else float(value) if t == "float" else str(value)
    except (TypeError, ValueError):
        raise ValueError(f"{spec['key']} must be a {t}")
    if t in ("int", "float"):
        if "min" in spec and v < spec["min"]:
            raise ValueError(f"{spec['key']} must be >= {spec['min']}")
        if "max" in spec and v > spec["max"]:
            raise ValueError(f"{spec['key']} must be <= {spec['max']}")
    return v


def update(patch: dict) -> dict:
    """Validate and persist a batch of overrides. Raises ValueError on an unknown key or an
    out-of-range value (nothing is written if any value is invalid). Returns the new effective set."""
    unknown = [k for k in patch if k not in _BY_KEY]
    if unknown:
        raise ValueError(f"unknown setting(s): {unknown}")
    coerced = {}
    for k, val in patch.items():
        v = _validate(_BY_KEY[k], val)
        coerced[k] = ("1" if v else "0") if _BY_KEY[k]["type"] == "bool" else v
    store.set_setting_values(coerced)
    return effective()


def reset(keys_to_reset=None) -> dict:
    """Drop overrides (all, or a named subset) so they revert to defaults. Returns effective set."""
    if keys_to_reset is not None:
        unknown = [k for k in keys_to_reset if k not in _BY_KEY]
        if unknown:
            raise ValueError(f"unknown setting(s): {unknown}")
    store.reset_settings(keys_to_reset)
    return effective()


def describe() -> list:
    """Grouped registry + current values, for the settings UI."""
    groups: dict = {}
    order: list = []
    for spec in REGISTRY:
        g = spec["group"]
        if g not in groups:
            groups[g] = []
            order.append(g)
        groups[g].append({
            "key": spec["key"], "label": spec["label"], "help": spec.get("help", ""),
            "type": spec["type"], "min": spec.get("min"), "max": spec.get("max"),
            "step": spec.get("step"), "default": spec["default"], "value": get(spec["key"]),
            "overridden": store.get_setting(spec["key"]) is not None,
        })
    return [{"group": g, "settings": groups[g]} for g in order]
