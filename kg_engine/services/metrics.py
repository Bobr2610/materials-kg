"""Offline quality metrics for extraction, context, coverage, and hypotheses."""

from __future__ import annotations

import logging
import math
from pathlib import Path
from statistics import fmean

from pydantic import BaseModel
from pydantic import Field
from pydantic import ValidationError
from pydantic import computed_field

from kg_engine.domain.models import EntityKind
from kg_engine.domain.models import HypothesisGenerationResult
from kg_engine.domain.models import HypothesisScore
from kg_engine.domain.models import Observation
from kg_engine.domain.models import ResearchHypothesis
from kg_engine.domain.models import RelationType
from kg_engine.domain.models import utc_now
from kg_engine.domain.resolution import normalize_name
from kg_engine.repositories.protocols import MaterialsKGRepository

logger = logging.getLogger(__name__)


class EntityMatch(BaseModel):
    """Canonical comparison key for extracted or expected entities."""

    kind: EntityKind
    name: str = Field(min_length=1)

    def key(self) -> tuple[str, str]:
        return (self.kind.value, normalize_name(self.name))


class RelationMatch(BaseModel):
    """Canonical comparison key for extracted or expected relations."""

    relation_type: RelationType
    source: EntityMatch
    target: EntityMatch

    def key(self) -> tuple[str, tuple[str, str], tuple[str, str]]:
        return (self.relation_type.value, self.source.key(), self.target.key())


class ExtractionBenchmarkSample(BaseModel):
    """One gold-vs-predicted extraction benchmark sample."""

    sample_id: str
    expected_entities: list[EntityMatch] = Field(default_factory=list)
    extracted_entities: list[EntityMatch] = Field(default_factory=list)
    expected_relations: list[RelationMatch] = Field(default_factory=list)
    extracted_relations: list[RelationMatch] = Field(default_factory=list)


class ExtractionBenchmark(BaseModel):
    """Gold extraction benchmark evaluated fully offline."""

    samples: list[ExtractionBenchmarkSample] = Field(default_factory=list)


class PrecisionRecallF1(BaseModel):
    """Precision, recall, and F1 with raw counts."""

    precision: float
    recall: float
    f1: float
    true_positive: int
    predicted: int
    expected: int


class ExtractionMetrics(BaseModel):
    """Entity and relation extraction quality."""

    entity: PrecisionRecallF1
    relation: PrecisionRecallF1


class ContextBenchmark(BaseModel):
    """Expected-vs-retrieved context and key entity IDs for KPI evaluation."""

    expected_context_ids: list[str] = Field(default_factory=list)
    retrieved_context_ids: list[str] = Field(default_factory=list)
    expected_entity_ids: list[str] = Field(default_factory=list)
    retrieved_entity_ids: list[str] = Field(default_factory=list)


class ContextMetrics(BaseModel):
    """Context recall metrics for retrieval quality."""

    context_recall: float
    context_entities_recall: float


class MetricContext(BaseModel):
    """Available offline support IDs for hypothesis grounding checks."""

    evidence_ids: list[str] = Field(default_factory=list)
    observation_ids: list[str] = Field(default_factory=list)
    text_unit_ids: list[str] = Field(default_factory=list)
    entity_ids: list[str] = Field(default_factory=list)

    def support_ids(self) -> set[str]:
        return {
            *self.evidence_ids,
            *self.observation_ids,
            *self.text_unit_ids,
            *self.entity_ids,
        }

    def source_ids(self) -> set[str]:
        return {*self.evidence_ids, *self.observation_ids, *self.text_unit_ids}


class CoverageAxis(BaseModel):
    """Material, mode, and property IDs defining a coverage cube."""

    material_ids: list[str] = Field(default_factory=list)
    mode_ids: list[str] = Field(default_factory=list)
    property_ids: list[str] = Field(default_factory=list)


class CoverageCell(BaseModel):
    """One material x mode x property coverage cell."""

    material_id: str
    mode_id: str
    property_id: str
    measured: bool
    observation_count: int = 0
    observation_ids: list[str] = Field(default_factory=list)


class CoverageHeatmap(BaseModel):
    """Coverage matrix for measured and missing material/mode/property triplets."""

    axes: CoverageAxis
    cells: list[CoverageCell] = Field(default_factory=list)

    @computed_field
    @property
    def coverage_ratio(self) -> float:
        if not self.cells:
            return 0.0
        measured = sum(1 for cell in self.cells if cell.measured)
        return measured / len(self.cells)

    def get_cell(
        self,
        material_id: str,
        mode_id: str,
        property_id: str,
    ) -> CoverageCell | None:
        for cell in self.cells:
            if (
                cell.material_id == material_id
                and cell.mode_id == mode_id
                and cell.property_id == property_id
            ):
                return cell
        return None


class HypothesisMetricItem(BaseModel):
    """Metrics for one generated hypothesis."""

    hypothesis_id: str
    faithfulness: float
    groundedness: float
    novelty: float
    coverage_status: str
    final_score: float


class HypothesisMetricsSummary(BaseModel):
    """Aggregate quality metrics for a hypothesis run."""

    items: list[HypothesisMetricItem] = Field(default_factory=list)
    entity_f1: float = 0.0
    relation_f1: float = 0.0
    context_recall: float = 0.0
    context_entities_recall: float = 0.0
    coverage_ratio: float = 0.0
    average_faithfulness: float
    average_groundedness: float
    average_novelty: float
    average_final_score: float


class RunMetricsInput(BaseModel):
    """Inputs needed to score one hypothesis-generation run."""

    name: str
    result: HypothesisGenerationResult
    context: MetricContext = Field(default_factory=MetricContext)
    coverage: CoverageHeatmap | None = None
    extraction_benchmark: ExtractionBenchmark | None = None
    context_benchmark: ContextBenchmark | None = None


class RunMetricsSummary(BaseModel):
    """Named metrics for one run."""

    name: str
    generation_engine: str
    metrics: HypothesisMetricsSummary


class RunComparison(BaseModel):
    """Side-by-side comparison of two hypothesis-generation runs."""

    left: RunMetricsSummary
    right: RunMetricsSummary
    deltas: dict[str, float]


class RankingWeights(BaseModel):
    """Weights for transparent hypothesis ranking."""

    value: float = Field(ge=0.0)
    evidence_strength: float = Field(ge=0.0)
    novelty: float = Field(ge=0.0)
    inverse_risk: float = Field(ge=0.0)

    @computed_field
    @property
    def total(self) -> float:
        return round(
            self.value + self.evidence_strength + self.novelty + self.inverse_risk,
            10,
        )


class ExpertFeedbackEntry(BaseModel):
    """Persistent expert rating for one hypothesis."""

    hypothesis_id: str
    rating: int = Field(ge=1, le=5)
    score: HypothesisScore
    expert_id: str | None = None
    comment: str = ""
    created_at: str = Field(default_factory=lambda: utc_now().isoformat())


class ExpertFeedbackStore:
    """JSONL-backed expert feedback store for offline calibration datasets."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self.invalid_line_count = 0

    def save(self, entry: ExpertFeedbackEntry) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as file:
            file.write(entry.model_dump_json())
            file.write("\n")

    def load(self) -> list[ExpertFeedbackEntry]:
        if not self._path.exists():
            return []
        entries: list[ExpertFeedbackEntry] = []
        self.invalid_line_count = 0
        with self._path.open("r", encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                raw = line.strip()
                if not raw:
                    continue
                try:
                    entries.append(ExpertFeedbackEntry.model_validate_json(raw))
                except ValidationError:
                    self.invalid_line_count += 1
                    logger.warning(
                        "Skipping invalid expert feedback line %s in %s",
                        line_number,
                        self._path,
                    )
        return entries


def evaluate_extraction_benchmark(
    benchmark: ExtractionBenchmark,
) -> ExtractionMetrics:
    """Evaluate entity and relation F1 against a gold benchmark."""
    expected_entities: set[tuple[str, str]] = set()
    predicted_entities: set[tuple[str, str]] = set()
    expected_relations: set[tuple[str, tuple[str, str], tuple[str, str]]] = set()
    predicted_relations: set[tuple[str, tuple[str, str], tuple[str, str]]] = set()

    for sample in benchmark.samples:
        sample_prefix = sample.sample_id
        expected_entities.update(
            (sample_prefix, *entity.key()) for entity in sample.expected_entities
        )
        predicted_entities.update(
            (sample_prefix, *entity.key()) for entity in sample.extracted_entities
        )
        expected_relations.update(
            (sample_prefix, *relation.key()) for relation in sample.expected_relations
        )
        predicted_relations.update(
            (sample_prefix, *relation.key()) for relation in sample.extracted_relations
        )

    return ExtractionMetrics(
        entity=_precision_recall_f1(predicted_entities, expected_entities),
        relation=_precision_recall_f1(predicted_relations, expected_relations),
    )


def evaluate_context_metrics(benchmark: ContextBenchmark) -> ContextMetrics:
    """Measure context recall and key-entity recall for retrieved context."""
    return ContextMetrics(
        context_recall=_recall(
            predicted=set(benchmark.retrieved_context_ids),
            expected=set(benchmark.expected_context_ids),
        ),
        context_entities_recall=_recall(
            predicted=set(benchmark.retrieved_entity_ids),
            expected=set(benchmark.expected_entity_ids),
        ),
    )


def build_coverage_heatmap(
    *,
    axes: CoverageAxis,
    observations: list[Observation] | None = None,
    repository: MaterialsKGRepository | None = None,
) -> CoverageHeatmap:
    """Build a material x mode x property coverage heatmap."""
    if observations is None:
        observations = repository.list_observations() if repository else []

    by_triplet: dict[tuple[str, str, str], list[Observation]] = {}
    for observation in observations:
        if observation.mode_id is None:
            continue
        key = (
            observation.material_id,
            observation.mode_id,
            observation.property_id,
        )
        by_triplet.setdefault(key, []).append(observation)

    cells: list[CoverageCell] = []
    for material_id in axes.material_ids:
        for mode_id in axes.mode_ids:
            for property_id in axes.property_ids:
                key = (material_id, mode_id, property_id)
                cell_observations = by_triplet.get(key, [])
                cells.append(
                    CoverageCell(
                        material_id=material_id,
                        mode_id=mode_id,
                        property_id=property_id,
                        measured=bool(cell_observations),
                        observation_count=len(cell_observations),
                        observation_ids=[item.id for item in cell_observations],
                    )
                )
    return CoverageHeatmap(axes=axes, cells=cells)


def build_repository_coverage_heatmap(
    repository: MaterialsKGRepository,
    *,
    axes: CoverageAxis | None = None,
) -> CoverageHeatmap:
    """Build a coverage heatmap from repository entities and observations."""
    observations = repository.list_observations()
    if axes is None:
        axes = CoverageAxis(
            material_ids=_axis_ids(
                repository=repository,
                kind=EntityKind.MATERIAL,
                observed_ids=[item.material_id for item in observations],
            ),
            mode_ids=_axis_ids(
                repository=repository,
                kind=EntityKind.MODE,
                observed_ids=[
                    item.mode_id for item in observations if item.mode_id is not None
                ],
            ),
            property_ids=_axis_ids(
                repository=repository,
                kind=EntityKind.PROPERTY,
                observed_ids=[item.property_id for item in observations],
            ),
        )
    return build_coverage_heatmap(axes=axes, observations=observations)


def evaluate_hypothesis_metrics(
    *,
    hypotheses: list[ResearchHypothesis],
    context: MetricContext | None = None,
    coverage: CoverageHeatmap | None = None,
) -> HypothesisMetricsSummary:
    """Evaluate groundedness, faithfulness, novelty, and final scores."""
    context = context or MetricContext()
    items = [
        _evaluate_hypothesis_item(
            hypothesis=hypothesis,
            context=context,
            coverage=coverage,
        )
        for hypothesis in hypotheses
    ]
    return HypothesisMetricsSummary(
        items=items,
        coverage_ratio=coverage.coverage_ratio if coverage is not None else 0.0,
        average_faithfulness=_average([item.faithfulness for item in items]),
        average_groundedness=_average([item.groundedness for item in items]),
        average_novelty=_average([item.novelty for item in items]),
        average_final_score=_average([item.final_score for item in items]),
    )


def compare_hypothesis_runs(
    left: RunMetricsInput,
    right: RunMetricsInput,
) -> RunComparison:
    """Compare two hypothesis-generation runs across all hypothesis metrics."""
    left_summary = _run_summary(left)
    right_summary = _run_summary(right)
    left_values = _metric_values(left_summary.metrics)
    right_values = _metric_values(right_summary.metrics)
    deltas = {
        metric: round(right_values[metric] - left_values[metric], 10)
        for metric in left_values
    }
    return RunComparison(left=left_summary, right=right_summary, deltas=deltas)


def score_with_weights(score: HypothesisScore, weights: RankingWeights) -> float:
    """Calculate a final score using calibrated ranking weights."""
    total = weights.total
    if total == 0:
        return 0.0
    normalized = RankingWeights(
        value=weights.value / total,
        evidence_strength=weights.evidence_strength / total,
        novelty=weights.novelty / total,
        inverse_risk=weights.inverse_risk / total,
    )
    return min(
        1.0,
        max(
            0.0,
            normalized.value * score.value
            + normalized.evidence_strength * score.evidence_strength
            + normalized.novelty * score.novelty
            + normalized.inverse_risk * (1.0 - score.risk),
        ),
    )


def apply_calibrated_ranking(
    result: HypothesisGenerationResult,
    weights: RankingWeights,
) -> HypothesisGenerationResult:
    """Apply calibrated ranking weights and return a reranked result copy."""
    reranked = result.model_copy(deep=True)
    for hypothesis in reranked.hypotheses:
        hypothesis.score = hypothesis.score.model_copy(
            update={
                "final_score": score_with_weights(hypothesis.score, weights),
            }
        )
    reranked.hypotheses.sort(key=lambda item: item.score.final_score, reverse=True)
    for rank, hypothesis in enumerate(reranked.hypotheses, start=1):
        hypothesis.rank = rank
    ranking_rubric = dict(reranked.ranking_rubric)
    ranking_rubric["calibrated_weights"] = weights.model_dump(mode="json")
    ranking_rubric["final_score_formula"] = (
        "value*w_value + evidence_strength*w_evidence_strength + "
        "novelty*w_novelty + (1-risk)*w_inverse_risk"
    )
    reranked.ranking_rubric = ranking_rubric
    return reranked


def recalibrate_ranking_weights(
    feedback: list[ExpertFeedbackEntry],
    *,
    min_entries: int = 5,
) -> RankingWeights:
    """Derive ranking weights from expert ratings using positive correlations."""
    if len(feedback) < min_entries:
        logger.warning(
            "Not enough feedback entries (%d < %d) for calibration, using default weights",
            len(feedback),
            min_entries,
        )
        return _default_weights()

    ratings = [float(entry.rating) for entry in feedback]
    candidates = {
        "value": [entry.score.value for entry in feedback],
        "evidence_strength": [entry.score.evidence_strength for entry in feedback],
        "novelty": [entry.score.novelty for entry in feedback],
        "inverse_risk": [1.0 - entry.score.risk for entry in feedback],
    }
    raw_weights = {
        name: max(0.0, _pearson(values, ratings) or 0.0)
        for name, values in candidates.items()
    }
    total = sum(raw_weights.values())
    if total <= 0:
        return _default_weights()
    return RankingWeights(
        value=raw_weights["value"] / total,
        evidence_strength=raw_weights["evidence_strength"] / total,
        novelty=raw_weights["novelty"] / total,
        inverse_risk=raw_weights["inverse_risk"] / total,
    )


def automatic_expert_correlation(
    feedback: list[ExpertFeedbackEntry],
) -> float | None:
    """Measure Pearson correlation between automatic final scores and ratings."""
    if len(feedback) < 2:
        return None
    return _pearson(
        [entry.score.final_score for entry in feedback],
        [float(entry.rating) for entry in feedback],
    )


def _run_summary(run: RunMetricsInput) -> RunMetricsSummary:
    extraction = (
        evaluate_extraction_benchmark(run.extraction_benchmark)
        if run.extraction_benchmark is not None
        else None
    )
    context = (
        evaluate_context_metrics(run.context_benchmark)
        if run.context_benchmark is not None
        else None
    )
    metrics = evaluate_hypothesis_metrics(
        hypotheses=run.result.hypotheses,
        context=run.context,
        coverage=run.coverage,
    )
    if extraction is not None:
        metrics.entity_f1 = extraction.entity.f1
        metrics.relation_f1 = extraction.relation.f1
    if context is not None:
        metrics.context_recall = context.context_recall
        metrics.context_entities_recall = context.context_entities_recall
    return RunMetricsSummary(
        name=run.name,
        generation_engine=run.result.generation_engine,
        metrics=metrics,
    )


def _metric_values(metrics: HypothesisMetricsSummary) -> dict[str, float]:
    return {
        "entity_f1": metrics.entity_f1,
        "relation_f1": metrics.relation_f1,
        "context_recall": metrics.context_recall,
        "context_entities_recall": metrics.context_entities_recall,
        "coverage_ratio": metrics.coverage_ratio,
        "average_faithfulness": metrics.average_faithfulness,
        "average_groundedness": metrics.average_groundedness,
        "average_novelty": metrics.average_novelty,
        "average_final_score": metrics.average_final_score,
    }


def _evaluate_hypothesis_item(
    *,
    hypothesis: ResearchHypothesis,
    context: MetricContext,
    coverage: CoverageHeatmap | None,
) -> HypothesisMetricItem:
    source_support_ids = {
        *hypothesis.supporting_evidence_ids,
        *hypothesis.supporting_observation_ids,
        *hypothesis.supporting_text_unit_ids,
    }
    all_support_ids = {*source_support_ids, *hypothesis.supporting_entity_ids}
    faithfulness = _recall(context.source_ids(), source_support_ids)
    groundedness = _recall(context.support_ids(), all_support_ids)
    novelty, coverage_status = _novelty_from_coverage(hypothesis, coverage)
    return HypothesisMetricItem(
        hypothesis_id=hypothesis.id,
        faithfulness=faithfulness,
        groundedness=groundedness,
        novelty=novelty,
        coverage_status=coverage_status,
        final_score=hypothesis.score.final_score,
    )


def _novelty_from_coverage(
    hypothesis: ResearchHypothesis,
    coverage: CoverageHeatmap | None,
) -> tuple[float, str]:
    if coverage is None:
        return hypothesis.score.novelty, "unknown"

    supported = set(hypothesis.supporting_entity_ids)
    matching_cells = [
        cell
        for cell in coverage.cells
        if {cell.material_id, cell.mode_id, cell.property_id}.issubset(supported)
    ]
    if not matching_cells:
        return hypothesis.score.novelty, "unknown"
    measured_count = sum(1 for cell in matching_cells if cell.measured)
    missing_count = len(matching_cells) - measured_count
    if missing_count == 0:
        return 0.0, "measured"
    if measured_count == 0:
        return 1.0, "missing"
    return missing_count / len(matching_cells), "mixed"


def _precision_recall_f1(
    predicted: set[tuple],
    expected: set[tuple],
) -> PrecisionRecallF1:
    true_positive = len(predicted & expected)
    precision = true_positive / len(predicted) if predicted else 0.0
    recall = true_positive / len(expected) if expected else 0.0
    f1 = 0.0
    if precision + recall > 0:
        f1 = 2 * precision * recall / (precision + recall)
    return PrecisionRecallF1(
        precision=precision,
        recall=recall,
        f1=f1,
        true_positive=true_positive,
        predicted=len(predicted),
        expected=len(expected),
    )


def _recall(predicted: set[str], expected: set[str]) -> float:
    if not expected:
        return 0.0
    return len(predicted & expected) / len(expected)


def _average(values: list[float]) -> float:
    return fmean(values) if values else 0.0


def _pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_mean = fmean(left)
    right_mean = fmean(right)
    numerator = sum(
        (left_value - left_mean) * (right_value - right_mean)
        for left_value, right_value in zip(left, right, strict=True)
    )
    left_variance = sum((value - left_mean) ** 2 for value in left)
    right_variance = sum((value - right_mean) ** 2 for value in right)
    denominator = math.sqrt(left_variance * right_variance)
    if denominator == 0:
        return None
    return numerator / denominator


def _default_weights() -> RankingWeights:
    return RankingWeights(
        value=0.35,
        evidence_strength=0.25,
        novelty=0.20,
        inverse_risk=0.20,
    )


def _axis_ids(
    *,
    repository: MaterialsKGRepository,
    kind: EntityKind,
    observed_ids: list[str],
) -> list[str]:
    ids = {entity.id for entity in repository.find_entities(kind=kind)}
    ids.update(observed_ids)
    return sorted(ids)
