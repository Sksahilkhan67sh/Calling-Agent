# Weighted rubric (Lead Scoring Specification §3); defaults only — per-campaign weights/bands are not configurable yet.
VERSION = "1"
INTEREST = {"interested": 1.0, "undecided": 0.5, "not_interested": 0.0}
DECISION = {"sole": 1.0, "influencer": 0.5, "not_involved": 0.0}  # [verify] spec only says sole scores higher than the others
CONFIRMED = {"confirm_and_close", "end_call_goal_met"}
ADDRESSED_PENALTY, UNADDRESSED_PENALTY = 3, 8  # [verify] spec's worked example gives one addressed objection = 12/15
SUBSTANTIVE_MIN_WORDS = 4  # [verify] engagement heuristic; the spec gives no numeric rule


def score(memory, required_fields, *, partial, suppressed):
    entities = memory.get("captured_entities") or {}
    interest = entities.get("interest_level")
    turns = memory.get("turns") or []
    captured = sum(entities.get(f) not in (None, "", "not_captured") for f in required_fields)
    substantive = sum(len(str(t.get("utterance", "")).split()) >= SUBSTANTIVE_MIN_WORDS for t in turns)
    objections = memory.get("objections_raised") or []
    points = {
        "interest": 40 * INTEREST.get(interest, 0),
        "decision_maker": 20 * DECISION.get(entities.get("decision_maker_status"), 0),
        # no interest signal → no free points, so an early drop cannot land mid-range for lack of negatives
        "objections": max(0, 15 - sum(ADDRESSED_PENALTY if o.get("addressed") else UNADDRESSED_PENALTY for o in objections))
        if interest in INTEREST else 0,
        "completion": 10 * captured / len(required_fields) if required_fields else 10,
        "engagement": 10 * substantive / len(turns) if turns else 0,
        "next_step": 5 if memory.get("next_action") in CONFIRMED else 0,
    }
    total = round(sum(points.values()))
    return {
        "lead_score": total, "components": points, "conversion_probability": total,  # direct mapping until outcomes are calibrated (§4.3)
        "temperature_tag": "Hot" if total >= 70 else "Warm" if total >= 40 else "Cold",
        "qualification_level": "Unqualified" if suppressed else (
            "Highly Qualified" if total >= 85 else "Qualified" if total >= 60 else "Marginal" if total >= 30 else "Unqualified"),
        "score_confidence": "partial" if partial or interest not in INTEREST else "full",
        "interest_classification": interest if interest in INTEREST else "undecided",
    }
