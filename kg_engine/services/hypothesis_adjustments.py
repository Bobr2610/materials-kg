"""Expert adjustment helpers for ranked research hypotheses."""

from __future__ import annotations

from typing import Any

from kg_engine.domain.models import HypothesisScore
from kg_engine.domain.models import ResearchHypothesis

DEFAULT_RANKING_WEIGHTS: dict[str, float] = {
    "value": 0.35,
    "evidence_strength": 0.25,
    "novelty": 0.20,
    "inverse_risk": 0.20,
}

EXPERT_ADJUSTMENT_SCHEMA: dict[str, Any] = {
    "description": "Per-hypothesis expert controls keyed by hypothesis id.",
    "fields": {
        "ranking_weights": "global weights for value/evidence_strength/novelty/inverse_risk",
        "reject": "boolean; when true sets the hypothesis final score to 0",
        "note": "string; appended to expert_notes",
        "risk_adjustment": "number in -1..1 added to risk",
        "value_adjustment": "number in -1..1 added to value",
        "novelty_adjustment": "number in -1..1 added to novelty",
        "evidence_strength_adjustment": "number in -1..1 added to evidence_strength",
        "score_override": "number in 0..1 replacing final score",
    },
}


def clamp_score(value: float) -> float:
    """Clamp a score component to the public 0..1 scale."""
    return max(0.0, min(1.0, float(value)))


def normalize_ranking_weights(weights: dict[str, Any] | None) -> dict[str, float]:
    """Return non-negative score weights normalized to sum to one."""
    if not weights:
        return dict(DEFAULT_RANKING_WEIGHTS)
    raw: dict[str, float] = {}
    for key in DEFAULT_RANKING_WEIGHTS:
        value = weights.get(key, DEFAULT_RANKING_WEIGHTS[key])
        try:
            raw[key] = max(0.0, float(value))
        except (TypeError, ValueError):
            raw[key] = DEFAULT_RANKING_WEIGHTS[key]
    total = sum(raw.values())
    if total <= 0:
        return dict(DEFAULT_RANKING_WEIGHTS)
    return {key: value / total for key, value in raw.items()}


def calculate_final_score(
    *,
    novelty: float,
    risk: float,
    value: float,
    evidence_strength: float,
    weights: dict[str, Any] | None = None,
) -> float:
    """Calculate the transparent Hypothesis Factory ranking score."""
    normalized = normalize_ranking_weights(weights)
    return clamp_score(
        normalized["value"] * value
        + normalized["evidence_strength"] * evidence_strength
        + normalized["novelty"] * novelty
        + normalized["inverse_risk"] * (1.0 - risk)
    )


def apply_expert_adjustments(
    hypotheses: list[ResearchHypothesis],
    expert_adjustments: dict[str, Any] | None,
) -> None:
    """Apply expert overrides in-place using the public adjustment schema."""
    if not expert_adjustments:
        return
    ranking_weights = expert_adjustments.get("ranking_weights")

    for hypothesis in hypotheses:
        adjustment = expert_adjustments.get(hypothesis.id)
        if adjustment is None:
            if ranking_weights:
                hypothesis.score = hypothesis.score.model_copy(
                    update={
                        "final_score": calculate_final_score(
                            novelty=hypothesis.score.novelty,
                            risk=hypothesis.score.risk,
                            value=hypothesis.score.value,
                            evidence_strength=hypothesis.score.evidence_strength,
                            weights=ranking_weights,
                        )
                    }
                )
            continue
        if not isinstance(adjustment, dict):
            continue
        if adjustment.get("reject"):
            hypothesis.score = HypothesisScore(
                novelty=0,
                risk=1.0,
                value=0,
                evidence_strength=0,
                final_score=0,
            )
        else:
            new_novelty = hypothesis.score.novelty
            new_risk = hypothesis.score.risk
            new_value = hypothesis.score.value
            new_evidence = hypothesis.score.evidence_strength
            if "risk_adjustment" in adjustment:
                new_risk = clamp_score(new_risk + adjustment["risk_adjustment"])
            if "value_adjustment" in adjustment:
                new_value = clamp_score(new_value + adjustment["value_adjustment"])
            if "novelty_adjustment" in adjustment:
                new_novelty = clamp_score(
                    new_novelty + adjustment["novelty_adjustment"]
                )
            if "evidence_strength_adjustment" in adjustment:
                new_evidence = clamp_score(
                    new_evidence + adjustment["evidence_strength_adjustment"]
                )
            if "score_override" in adjustment:
                final_score = clamp_score(adjustment["score_override"])
            else:
                final_score = calculate_final_score(
                    novelty=new_novelty,
                    risk=new_risk,
                    value=new_value,
                    evidence_strength=new_evidence,
                    weights=ranking_weights,
                )
            hypothesis.score = HypothesisScore(
                novelty=new_novelty,
                risk=new_risk,
                value=new_value,
                evidence_strength=new_evidence,
                final_score=final_score,
            )
        if "note" in adjustment:
            hypothesis.expert_notes.append(str(adjustment["note"]))
