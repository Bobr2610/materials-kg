from kg_engine.domain.models import HypothesisGenerationResult
from kg_engine.domain.models import HypothesisScore
from kg_engine.domain.models import ResearchHypothesis
from kg_engine.services.reports import render_hypothesis_report


def _result() -> HypothesisGenerationResult:
    return HypothesisGenerationResult(
        target_kpi="Increase hardness",
        hypotheses=[
            ResearchHypothesis(
                id="h-1",
                target_kpi="Increase hardness",
                statement="Age IN718 at 720 C",
                rationale="Observed precipitation response",
                mechanism="gamma-prime precipitation",
                test_plan="Test three coupons",
                supporting_evidence_ids=["e-1"],
                score=HypothesisScore(
                    novelty=0.5,
                    risk=0.2,
                    value=0.8,
                    evidence_strength=0.7,
                    final_score=0.68,
                ),
            )
        ],
    )


def test_report_formats_have_expected_signatures() -> None:
    result = _result()

    assert render_hypothesis_report(result, "markdown").startswith(b"# ")
    assert render_hypothesis_report(result, "xlsx").startswith(b"PK")
    assert render_hypothesis_report(result, "docx").startswith(b"PK")
    assert render_hypothesis_report(result, "pdf").startswith(b"%PDF")
