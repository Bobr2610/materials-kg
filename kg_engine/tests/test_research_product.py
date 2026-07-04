from pathlib import Path

from fastapi.testclient import TestClient

from kg_engine.api.materials_core import create_materials_app
from kg_engine.domain.product import Constraint
from kg_engine.domain.product import ConstraintKind
from kg_engine.domain.product import ConstraintStrength
from kg_engine.domain.product import ResearchProjectCreate
from kg_engine.domain.product import DecisionGate
from kg_engine.domain.product import ExperimentStep
from kg_engine.domain.product import VerificationRoadmap
from kg_engine.domain.product import ExpertReview
from kg_engine.domain.product import ExperimentOutcome
from kg_engine.domain.product import HypothesisRun
from kg_engine.domain.product import ReviewDecision
from kg_engine.domain.models import HypothesisScore
from kg_engine.domain.models import ResearchHypothesis
from kg_engine.repositories.memory import InMemoryMaterialsKGRepository
from kg_engine.services.materials_kg import MaterialsKGService
from kg_engine.services.research_projects import ResearchProjectService


def _product_service(tmp_path: Path) -> ResearchProjectService:
    return ResearchProjectService(tmp_path / "product.sqlite3")


def test_project_round_trip_is_persistent(tmp_path: Path) -> None:
    service = _product_service(tmp_path)
    created = service.create_project(
        ResearchProjectCreate(
            name="IN718 heat resistance",
            target_kpi="Increase creep strength by 15%",
            target_change=15.0,
            unit="%",
            direction="increase",
            language="en",
        )
    )

    reopened = _product_service(tmp_path)

    assert reopened.get_project(created.id) == created


def test_hard_constraints_are_reported_by_project_validation(tmp_path: Path) -> None:
    service = _product_service(tmp_path)
    project = service.create_project(
        ResearchProjectCreate(name="CuCrZr", target_kpi="Improve conductivity")
    )
    service.add_constraint(
        project.id,
        Constraint(
            kind=ConstraintKind.EQUIPMENT,
            strength=ConstraintStrength.HARD,
            operator="available",
            value="HIP furnace",
            explanation="Required equipment is unavailable",
        ),
    )

    validation = service.validate_project(project.id)

    assert validation.valid is False
    assert validation.blocking_constraints[0].value == "HIP furnace"


def test_project_api_crud_and_audit(tmp_path: Path) -> None:
    product = _product_service(tmp_path)
    app = create_materials_app(
        service=MaterialsKGService(InMemoryMaterialsKGRepository()),
        product_service=product,
    )
    client = TestClient(app)

    response = client.post(
        "/projects",
        json={"name": "316L", "target_kpi": "Reduce porosity"},
        headers={"X-User": "researcher-1", "X-Role": "researcher"},
    )
    assert response.status_code == 201
    project_id = response.json()["id"]

    assert client.get(f"/projects/{project_id}").status_code == 200
    assert product.list_audit_events(project_id=project_id)[0].actor == "researcher-1"


def test_viewer_cannot_create_project(tmp_path: Path) -> None:
    app = create_materials_app(
        service=MaterialsKGService(InMemoryMaterialsKGRepository()),
        product_service=_product_service(tmp_path),
    )

    response = TestClient(app).post(
        "/projects",
        json={"name": "Denied", "target_kpi": "No write"},
        headers={"X-User": "viewer-1", "X-Role": "viewer"},
    )

    assert response.status_code == 403


def test_project_hypothesis_run_is_persisted(tmp_path: Path) -> None:
    product = _product_service(tmp_path)
    project = product.create_project(
        ResearchProjectCreate(name="IN718", target_kpi="Increase hardness")
    )
    app = create_materials_app(
        service=MaterialsKGService(InMemoryMaterialsKGRepository()),
        product_service=product,
    )
    client = TestClient(app)

    created = client.post(
        f"/projects/{project.id}/hypothesis-runs",
        headers={"X-User": "researcher-1", "X-Role": "researcher"},
    )

    assert created.status_code == 201
    run = created.json()
    assert run["project_id"] == project.id
    assert client.get(f"/hypothesis-runs/{run['id']}").json() == run


def test_hypothesis_contract_supports_structured_verification_roadmap() -> None:
    roadmap = VerificationRoadmap(
        steps=[
            ExperimentStep(
                order=1,
                objective="Measure baseline hardness",
                method="HRC indentation",
                decision_gate=DecisionGate(
                    metric="hardness",
                    operator=">=",
                    threshold=44,
                    success_action="continue",
                    failure_action="review heat treatment",
                ),
            )
        ]
    )
    hypothesis = ResearchHypothesis(
        id="h-1",
        target_kpi="hardness",
        statement="Aging IN718 at 720 C increases hardness",
        rationale="Supported by an observed heat-treatment effect",
        test_plan="Run a controlled coupon test",
        score=HypothesisScore(
            novelty=0.5,
            risk=0.2,
            value=0.8,
            evidence_strength=0.7,
            final_score=0.68,
        ),
        mechanism="gamma-prime precipitation",
        confidence=0.75,
        verification_roadmap=roadmap,
    )

    assert hypothesis.verification_roadmap.steps[0].decision_gate.threshold == 44
    assert hypothesis.score.feasibility == 0.0


def test_expert_review_is_persisted_as_immutable_run_feedback(tmp_path: Path) -> None:
    service = _product_service(tmp_path)
    project = service.create_project(
        ResearchProjectCreate(name="CuCrZr", target_kpi="Conductivity")
    )
    run = service.save_hypothesis_run(
        HypothesisRun(project_id=project.id, result={"hypotheses": []})
    )

    review = service.save_expert_review(
        ExpertReview(
            run_id=run.id,
            hypothesis_id="h-1",
            expert_id="expert-1",
            decision=ReviewDecision.ACCEPT,
            rating=5,
            comment="Ready for coupon testing",
        )
    )

    assert service.list_expert_reviews(run_id=run.id) == [review]


def test_experiment_outcome_calibrates_future_project_weights(tmp_path: Path) -> None:
    service = _product_service(tmp_path)
    project = service.create_project(
        ResearchProjectCreate(name="Tailings", target_kpi="Reduce metal losses")
    )
    run = service.save_hypothesis_run(
        HypothesisRun(
            project_id=project.id,
            result={
                "hypotheses": [
                    {
                        "id": "h-value",
                        "score": {
                            "novelty": 0.1,
                            "risk": 0.8,
                            "value": 0.95,
                            "evidence_strength": 0.2,
                            "final_score": 0.43,
                        },
                    },
                    {
                        "id": "h-evidence",
                        "score": {
                            "novelty": 0.1,
                            "risk": 0.8,
                            "value": 0.2,
                            "evidence_strength": 0.95,
                            "final_score": 0.37,
                        },
                    },
                ]
            },
        )
    )
    accepted = service.save_expert_review(
        ExpertReview(
            run_id=run.id,
            hypothesis_id="h-value",
            expert_id="expert-1",
            decision=ReviewDecision.ACCEPT,
            rating=4,
        )
    )
    rejected = service.save_expert_review(
        ExpertReview(
            run_id=run.id,
            hypothesis_id="h-evidence",
            expert_id="expert-1",
            decision=ReviewDecision.REJECT,
            rating=2,
        )
    )

    confirmed = service.save_experiment_outcome(
        ExperimentOutcome(review_id=accepted.id, confirmed=True, actual_kpi=1.5)
    )
    service.save_experiment_outcome(
        ExperimentOutcome(review_id=rejected.id, confirmed=False, actual_kpi=0.1)
    )

    weights = service.derive_feedback_ranking_weights(project.id)

    assert service.list_experiment_outcomes(run_id=run.id)[0] == confirmed
    assert weights["value"] > weights["evidence_strength"]
