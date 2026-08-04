"""
Compute Units — the billable unit, defined deterministically.

WHY THIS REPLACES WALL-CLOCK
The original meter charged `elapsed_seconds x device_multiplier`, measured across the whole request.
That is indefensible on an invoice for three reasons:

  1. It includes queueing, JSON parsing and time spent awaiting under concurrency, so the SAME request
     costs more when *our* service is busy. The customer pays for our oversubscription.
  2. It is not reproducible: a customer cannot predict a bill, and we cannot publish a price per call.
  3. It cannot be estimated before the work runs, so an over-quota caller could only be told no
     *after* consuming the compute.

So a Compute Unit is now a function of the REQUEST, not of the clock:

    CU = work_units(request) x device_rate

`work_units` counts the retrieval work actually implied — how many query encodes, and how many corpus
vectors each is scored against. Same request, same number, every time, on any hardware.

True wall-clock seconds are still recorded on every usage event, but as **cost-of-goods telemetry** for
margin analysis — never as the billed quantity. That separation is the whole point.

CALIBRATION
The constants below are chosen so that one CU is roughly one `/map` against a 1,000-control corpus,
which keeps the plan allowances in `billing.DEFAULT_PLANS` intuitive (a Free tier at 300 CU/month is
~300 such lookups). They are policy, not physics: change them deliberately and version the change,
because customers will have budgeted against them.
"""
import os

# One query encode. Dominates cost for small corpora.
ENCODE_UNITS = float(os.environ.get("REGMAP_CU_ENCODE", "0.5"))
# Scoring one query against 1,000 corpus vectors.
SCORE_UNITS_PER_1K = float(os.environ.get("REGMAP_CU_SCORE_PER_1K", "0.5"))
# Returning results costs almost nothing, but top_k shouldn't be entirely free or it invites abuse.
RESULT_UNITS_PER_ITEM = float(os.environ.get("REGMAP_CU_PER_RESULT", "0.004"))
# GPU-seconds cost more than CPU-seconds, so GPU work bills at a higher rate per unit of work.
GPU_RATE = float(os.environ.get("REGMAP_GPU_CU_MULT", "8"))

MIN_CU = 0.01          # never bill zero for a real request


def device_rate(on_gpu: bool) -> float:
    return GPU_RATE if on_gpu else 1.0


def _units(encodes: int, corpus_size: int, results: int = 0) -> float:
    return (encodes * ENCODE_UNITS
            + encodes * (corpus_size / 1000.0) * SCORE_UNITS_PER_1K
            + results * RESULT_UNITS_PER_ITEM)


def map_units(corpus_size: int, top_k: int = 5) -> float:
    """One query encoded and scored against a target framework."""
    return _units(1, corpus_size, top_k)


def bulk_units(n_controls: int, corpus_size: int, top_k: int = 5, n_ranked: int = None) -> float:
    """Bulk maps many controls, but only RANKS the ones lacking an official mapping.

    Charging for every submitted control would overbill: looking a control up in the crosswalk is a
    dictionary hit, not model work. `n_ranked` is what actually reached the encoder.
    """
    ranked = n_controls if n_ranked is None else n_ranked
    return _units(ranked, corpus_size, ranked * top_k)


def eval_units(n_queries: int, corpus_size: int) -> float:
    """Evaluation encodes every query against the whole corpus — by far the heaviest call."""
    return _units(n_queries, corpus_size)


def exercise_units(corpus_size: int, distractors: int = 8) -> float:
    """Setting an exercise is one encode plus a ranking pass to find plausible distractors."""
    return _units(1, corpus_size, distractors)


def quantise(units: float, on_gpu: bool) -> float:
    """Apply the device rate and round to a billable figure."""
    return max(MIN_CU, round(units * device_rate(on_gpu), 4))


def explain(units: float, on_gpu: bool) -> dict:
    """Returned on every billable response so a customer can verify the charge themselves.

    Publishing the derivation is what makes the meter auditable rather than something to be trusted.
    """
    return {
        "work_units": round(units, 4),
        "device": "gpu" if on_gpu else "cpu",
        "device_rate": device_rate(on_gpu),
        "compute_units": quantise(units, on_gpu),
        "formula": "compute_units = work_units x device_rate",
        "deterministic": True,
        "note": ("Derived from the request, not from elapsed time, so the same request always costs "
                 "the same regardless of server load."),
    }
