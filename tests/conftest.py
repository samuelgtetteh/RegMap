"""Shared pytest setup: put the backend and control-advisor packages on the
import path so tests can import them without installing anything."""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "control-advisor"))

# Point the decision-layer verdict store at a throwaway DB so the suite neither
# depends on nor pollutes the real trail (data/verdicts.db). This MUST be set before
# the backend is imported, because verdict_store opens its connection at import time.
_TEST_DB = Path(tempfile.gettempdir()) / "regmap_pytest_verdicts.db"
try:
    _TEST_DB.unlink()
except FileNotFoundError:
    pass
os.environ["VERDICT_DB"] = str(_TEST_DB)

# Keep the suite deterministic and fast: no LLM in tests (assess() then returns the
# deterministic severity-based default). LLM behaviour is exercised separately, not in CI.
os.environ["AI_TRIAGE_LLM"] = "0"
os.environ.pop("LLM_SERVICE_URL", None)
