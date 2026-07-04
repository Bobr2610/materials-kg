from kg_engine.domain.models import HypothesisGenerationResult
from kg_engine.domain.models import HypothesisScore
from kg_engine.domain.models import ResearchHypothesis
from kg_engine.domain.product import ExperimentStep
from kg_engine.domain.product import RequiredResource
from kg_engine.domain.product import VerificationRoadmap
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
                    feasibility=0.75,
                    uncertainty=0.30,
                    technical_risk=0.20,
                ),
                risk_items=["Coupon aging may not reproduce plant conditions"],
                falsification_criteria=["Hardness does not improve over baseline"],
                verification_roadmap=VerificationRoadmap(
                    steps=[
                        ExperimentStep(
                            order=1,
                            objective="Measure baseline hardness",
                            method="Coupon test",
                            estimated_duration_days=2,
                        )
                    ]
                ),
                resource_estimate=[
                    RequiredResource(kind="lab", name="Hardness tester", quantity=1)
                ],
            )
        ],
    )


def test_report_formats_have_expected_signatures() -> None:
    result = _result()

    assert render_hypothesis_report(result, "markdown").startswith(b"# ")
    assert render_hypothesis_report(result, "xlsx").startswith(b"PK")
    assert render_hypothesis_report(result, "docx").startswith(b"PK")
    assert render_hypothesis_report(result, "pdf").startswith(b"%PDF")


def test_markdown_report_includes_risk_roadmap_and_resources() -> None:
    markdown = render_hypothesis_report(_result(), "markdown").decode("utf-8")

    assert "Uncertainty:" in markdown
    assert "Feasibility:" in markdown
    assert "Coupon aging may not reproduce plant conditions" in markdown
    assert "Hardness does not improve over baseline" in markdown
    assert "Measure baseline hardness via Coupon test" in markdown
    assert "lab:Hardness tester x1" in markdown
