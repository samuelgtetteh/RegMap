"""
Interprets free-text interview answers the same way RegMap interprets a NIST
control description: embed it, compare by cosine similarity against a small
set of canonical option descriptions, and pick the best match — rather than
requiring the user to type one exact string from a fixed list.

A user can answer "we're a small medical clinic that keeps patient charts"
and this will correctly resolve to sector=healthcare, the same way RegMap
resolves a full control paragraph to the right HIPAA citation without the
input needing to be a keyword.

Exact/near-exact matches (a user who just types "healthcare") still short-
circuit immediately without needing the model at all — this only reaches for
semantic matching when the literal answer doesn't already match.

Bare short answers ("no", "yes") get their own fast path too, ahead of the
embedding model: sentence embeddings compare poorly when one side is a single
word and the other is a full descriptive sentence (a real failure seen in
testing — "no" was matched to the "unsure" description instead of "none",
since a one-word input just doesn't carry enough signal against long option
text). A plain affirmation/negation word is unambiguous on its own and
doesn't need — or benefit from — the heavier semantic comparison.
"""
import torch

import control_mapper

UNSURE_SYNONYMS = {
    "unsure", "not sure", "not_sure", "notsure", "dont know", "don't know",
    "dk", "n/a", "na", "skip", "?", "no idea", "unknown",
}

AFFIRMATIVE_WORDS = {"yes", "yeah", "yep", "yup", "correct", "true", "affirmative", "sure", "definitely"}
NEGATIVE_WORDS = {"no", "nope", "nah", "none", "negative", "nothing", "not any", "no data", "not applicable"}

LOW_CONFIDENCE_THRESHOLD = 0.30  # below this, treat the interpretation as unreliable -> "unsure"


def _exact_match(raw, option_descriptions):
    v = raw.strip().lower()
    if v in UNSURE_SYNONYMS:
        return "unsure" if "unsure" in option_descriptions else None
    for option in option_descriptions:
        if v == option.lower():
            return option
    return None


def _affirmation_negation_match(raw, option_descriptions):
    """Bare yes/no-shaped answers, resolved directly against whichever of
    yes/no/none actually exists in this question's options — e.g. a
    regulated-data question has 'none' but no literal 'no', so "no" should
    still resolve there rather than falling through to semantic matching."""
    v = raw.strip().lower()
    if v in AFFIRMATIVE_WORDS and "yes" in option_descriptions:
        return "yes"
    if v in NEGATIVE_WORDS:
        if "no" in option_descriptions:
            return "no"
        if "none" in option_descriptions:
            return "none"
    return None


def interpret(raw_text, option_descriptions, multi=False, top_k_multi=3):
    """option_descriptions: dict of {option_value: natural-language description}.
    Returns (selected, details) where selected is a single option value, or a
    list of option values if multi=True. `details` carries scores for
    transparency (shown to the user, mirroring RegMap's score display)."""
    if not raw_text.strip():
        return ("unsure" if not multi else ["unsure"]), {"method": "empty_input"}

    exact = _exact_match(raw_text, option_descriptions)
    if exact and not multi:
        return exact, {"method": "exact_match"}

    affirm_neg = _affirmation_negation_match(raw_text, option_descriptions)
    if affirm_neg:
        return (affirm_neg if not multi else [affirm_neg]), {"method": "exact_match"}

    model = control_mapper.get_model()
    options = list(option_descriptions.keys())
    descriptions = list(option_descriptions.values())

    query_embed = model.encode(raw_text, convert_to_tensor=True)
    corpus_embeds = model.encode(descriptions, convert_to_tensor=True)
    scores = torch.nn.functional.cosine_similarity(query_embed, corpus_embeds)

    ranked = sorted(zip(options, [float(s) for s in scores]), key=lambda x: x[1], reverse=True)

    if multi:
        selected = [opt for opt, score in ranked[:top_k_multi] if score >= LOW_CONFIDENCE_THRESHOLD]
        # "unsure" alongside a confident, specific answer is contradictory — a
        # user who names actual data types isn't simultaneously "not sure."
        # Only keep "unsure" when it's the sole (or best) signal.
        if "unsure" in selected and len(selected) > 1:
            selected = [opt for opt in selected if opt != "unsure"]
        if not selected:
            selected = ["unsure"] if "unsure" in option_descriptions else [ranked[0][0]]
        return selected, {"method": "semantic", "ranked": ranked[:top_k_multi]}

    best_option, best_score = ranked[0]
    if best_score < LOW_CONFIDENCE_THRESHOLD:
        return ("unsure" if "unsure" in option_descriptions else best_option), {
            "method": "semantic_low_confidence", "best_guess": best_option, "score": best_score,
        }
    return best_option, {"method": "semantic", "score": best_score, "ranked": ranked[:3]}
