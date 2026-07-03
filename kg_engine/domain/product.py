"""Product contracts for research projects, constraints, runs, and audit."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel
from pydantic import Field


def utc_now() -> datetime:
    """Return an aware UTC timestamp."""
    return datetime.now(UTC)


class ConstraintKind(StrEnum):
    """Supported project constraint families."""

    MATERIAL = "material"
    EQUIPMENT = "equipment"
    BUDGET = "budget"
    REGULATORY = "regulatory"
    PROCESS = "process"
    SAFETY = "safety"
    EXCLUSION = "exclusion"


class ConstraintStrength(StrEnum):
    """Whether a failed constraint blocks or penalizes a candidate."""

    HARD = "hard"
    SOFT = "soft"


class Constraint(BaseModel):
    """One explicit research-project constraint."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    kind: ConstraintKind
    strength: ConstraintStrength = ConstraintStrength.HARD
    operator: str
    value: Any
    source: str | None = None
    explanation: str = ""
    satisfied: bool | None = None


class ResearchProjectCreate(BaseModel):
    """Input used to create a research project."""

    name: str = Field(min_length=1, max_length=200)
    target_kpi: str = Field(min_length=1)
    description: str = ""
    baseline: float | None = None
    target_change: float | None = None
    unit: str | None = None
    direction: str = "increase"
    domain: str = "materials_science"
    materials: list[str] = Field(default_factory=list)
    available_raw_materials: list[str] = Field(default_factory=list)
    available_equipment: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    language: str = "ru"
    ranking_weights: dict[str, float] = Field(default_factory=dict)
    confidential: bool = False


class ResearchProject(ResearchProjectCreate):
    """Persisted research project and its current constraints."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    constraints: list[Constraint] = Field(default_factory=list)
    version: int = 1
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ProjectValidation(BaseModel):
    """Result of checking whether a project can start generation."""

    valid: bool
    blocking_constraints: list[Constraint] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AuditEvent(BaseModel):
    """Immutable record of a product-level mutation."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    actor: str
    action: str
    project_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class RequiredResource(BaseModel):
    """Resource required by an experiment step."""

    kind: str
    name: str
    quantity: float | None = None
    unit: str | None = None
    estimated_cost: float | None = None
    assumption: str | None = None


class ExpectedEffect(BaseModel):
    """Expected measurable change produced by a hypothesis."""

    property_name: str
    direction: str
    value: float | None = None
    minimum: float | None = None
    maximum: float | None = None
    unit: str | None = None


class ConstraintCheck(BaseModel):
    """Trace explaining how one constraint affected a hypothesis."""

    constraint_id: str
    satisfied: bool
    penalty: float = Field(default=0.0, ge=0.0, le=1.0)
    explanation: str = ""


class DecisionGate(BaseModel):
    """Measurable decision after an experiment step."""

    metric: str
    operator: str
    threshold: float | str
    success_action: str
    failure_action: str


class ExperimentStep(BaseModel):
    """One testable step in a verification roadmap."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    order: int = Field(ge=1)
    objective: str
    method: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    dependency_ids: list[str] = Field(default_factory=list)
    resources: list[RequiredResource] = Field(default_factory=list)
    decision_gate: DecisionGate | None = None
    estimated_duration_days: float | None = Field(default=None, ge=0)


class VerificationRoadmap(BaseModel):
    """Versioned laboratory verification plan."""

    version: int = 1
    steps: list[ExperimentStep] = Field(default_factory=list)
    estimated_budget: float | None = Field(default=None, ge=0)
    currency: str | None = None
    assumptions: list[str] = Field(default_factory=list)


class UncertaintyAssessment(BaseModel):
    """Explicit uncertainty attached to a generated hypothesis."""

    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    factors: list[str] = Field(default_factory=list)
    recommended_information_test: str | None = None


class HypothesisRun(BaseModel):
    """Immutable persisted result of one project generation run."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    project_id: str
    status: str = "succeeded"
    generation_engine: str = "deterministic"
    ranking_weights: dict[str, float] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    actor: str = "system"
    created_at: datetime = Field(default_factory=utc_now)


class ReviewDecision(StrEnum):
    """Expert disposition for a generated hypothesis."""

    ACCEPT = "accept"
    REJECT = "reject"
    DEFER = "defer"


class ExpertReview(BaseModel):
    """Immutable expert review tied to a hypothesis run version."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    hypothesis_id: str
    expert_id: str
    decision: ReviewDecision
    rating: int = Field(ge=1, le=5)
    rejection_reason: str | None = None
    comment: str = ""
    score_corrections: dict[str, float] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class ExperimentOutcome(BaseModel):
    """Measured outcome used to calibrate future ranking policies."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    review_id: str
    confirmed: bool
    actual_kpi: float | None = None
    unit: str | None = None
    measured_at: datetime = Field(default_factory=utc_now)
    notes: str = ""
