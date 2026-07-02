from __future__ import annotations

from typing import TYPE_CHECKING

from kg_engine.domain.models import EntityKind
from kg_engine.domain.models import HypothesisGenerationResult
from kg_engine.domain.models import HypothesisScore
from kg_engine.domain.models import Observation
from kg_engine.domain.models import ResearchHypothesis
from kg_engine.domain.models import RelationType
from kg_engine.repositories.memory import InMemoryMaterialsKGRepository
from kg_engine.services.metrics import ContextBenchmark
from kg_engine.services.metrics import CoverageAxis
from kg_engine.services.metrics import EntityMatch
from kg_engine.services.metrics import ExpertFeedbackEntry
from kg_engine.services.metrics import ExpertFeedbackStore
from kg_engine.services.metrics import ExtractionBenchmark
from kg_engine.services.metrics import ExtractionBenchmarkSample
from kg_engine.services.metrics import MetricContext
from kg_engine.services.metrics import RankingWeights
from kg_engine.services.metrics import RelationMatch
from kg_engine.services.metrics import RunMetricsInput
from kg_engine.services.metrics import apply_calibrated_ranking
from kg_engine.services.metrics import automatic_expert_correlation
from kg_engine.services.metrics import build_repository_coverage_heatmap
from kg_engine.services.metrics import build_coverage_heatmap
from kg_engine.services.metrics import compare_hypothesis_runs
from kg_engine.services.metrics import evaluate_context_metrics
from kg_engine.services.metrics import evaluate_extraction_benchmark
from kg_engine.services.metrics import evaluate_hypothesis_metrics
from kg_engine.services.metrics import recalibrate_ranking_weights
from kg_engine.services.metrics import score_with_weights

if TYPE_CHECKING:
    from pathlib import Path


def test_extraction_benchmark_scores_entity_and_relation_f1() -> None:
    benchmark = ExtractionBenchmark(
        samples=[
            ExtractionBenchmarkSample(
                sample_id="doc-1",
                expected_entities=[
                    EntityMatch(kind=EntityKind.MATERIAL, name="CuCrZr"),
                    EntityMatch(kind=EntityKind.MODE, name="Aging"),
                ],
                extracted_entities=[
                    EntityMatch(kind=EntityKind.MATERIAL, name="cucrzr"),
                    EntityMatch(kind=EntityKind.PROPERTY, name="Hardness"),
                ],
                expected_relations=[
                    RelationMatch(
                        relation_type=RelationType.USES_MODE,
                        source=EntityMatch(kind=EntityKind.MATERIAL, name="CuCrZr"),
                        target=EntityMatch(kind=EntityKind.MODE, name="Aging"),
                    )
                ],
                extracted_relations=[
                    RelationMatch(
                        relation_type=RelationType.USES_MODE,
                        source=EntityMatch(kind=EntityKind.MATERIAL, name="CuCrZr"),
                        target=EntityMatch(kind=EntityKind.MODE, name="Aging"),
                    )
                ],
            )
        ]
    )

    result = evaluate_extraction_benchmark(benchmark)

    assert result.entity.precision == 0.5
    assert result.entity.recall == 0.5
    assert result.entity.f1 == 0.5
    assert result.relation.precision == 1.0
    assert result.relation.recall == 1.0
    assert result.relation.f1 == 1.0


def test_context_metrics_measure_kpi_recall_and_entity_recall() -> None:
    context = ContextBenchmark(
        expected_context_ids=["ev-1", "ev-2", "text-1"],
        retrieved_context_ids=["ev-1", "text-1", "extra"],
        expected_entity_ids=["material-cucrzr", "property-conductivity"],
        retrieved_entity_ids=["material-cucrzr", "mode-aging"],
    )

    result = evaluate_context_metrics(context)

    assert result.context_recall == 2 / 3
    assert result.context_entities_recall == 0.5


def test_hypothesis_metrics_are_grounded_and_novel_offline() -> None:
    hypothesis = ResearchHypothesis(
        id="hyp-1",
        target_kpi="Conductivity",
        statement="Test CuCrZr under aging for conductivity",
        rationale="Supported by ev-1 and obs-1",
        test_plan="Measure conductivity after aging",
        score=HypothesisScore(
            novelty=0.4,
            risk=0.3,
            value=0.8,
            evidence_strength=0.9,
            final_score=0.725,
        ),
        supporting_entity_ids=["mat-cucrzr", "mode-aging", "prop-cond"],
        supporting_evidence_ids=["ev-1"],
        supporting_observation_ids=["obs-1"],
    )
    context = MetricContext(
        evidence_ids=["ev-1"],
        observation_ids=["obs-1"],
        entity_ids=["mat-cucrzr", "mode-aging", "prop-cond"],
    )
    coverage = build_coverage_heatmap(
        axes=CoverageAxis(
            material_ids=["mat-cucrzr"],
            mode_ids=["mode-aging", "mode-hip"],
            property_ids=["prop-cond"],
        ),
        observations=[
            Observation(
                id="obs-1",
                material_id="mat-cucrzr",
                mode_id="mode-aging",
                property_id="prop-cond",
                evidence_id="ev-1",
            )
        ],
    )

    result = evaluate_hypothesis_metrics(
        hypotheses=[hypothesis],
        context=context,
        coverage=coverage,
    )

    assert result.average_faithfulness == 1.0
    assert result.average_groundedness == 1.0
    assert result.average_novelty == 0.0
    assert result.items[0].coverage_status == "measured"


def test_novelty_mixed_coverage_returns_weighted_ratio() -> None:
    hypothesis = ResearchHypothesis(
        id="hyp-mixed",
        target_kpi="Hardness",
        statement="Test CuCrZr under multiple modes for hardness",
        rationale="Grounded in obs-1",
        test_plan="Measure hardness under aging and HIP",
        score=HypothesisScore(
            novelty=0.5,
            risk=0.2,
            value=0.7,
            evidence_strength=0.6,
            final_score=0.65,
        ),
        supporting_entity_ids=["mat-cucrzr", "mode-aging", "mode-hip", "prop-hardness"],
        supporting_observation_ids=["obs-1"],
    )
    coverage = build_coverage_heatmap(
        axes=CoverageAxis(
            material_ids=["mat-cucrzr"],
            mode_ids=["mode-aging", "mode-hip"],
            property_ids=["prop-hardness"],
        ),
        observations=[
            Observation(
                id="obs-1",
                material_id="mat-cucrzr",
                mode_id="mode-aging",
                property_id="prop-hardness",
                evidence_id="ev-1",
            )
        ],
    )

    result = evaluate_hypothesis_metrics(
        hypotheses=[hypothesis],
        coverage=coverage,
    )

    assert result.average_novelty == 0.5
    assert result.items[0].coverage_status == "mixed"


def test_coverage_heatmap_marks_measured_and_missing_triplets() -> None:
    heatmap = build_coverage_heatmap(
        axes=CoverageAxis(
            material_ids=["mat-a"],
            mode_ids=["mode-aged", "mode-hip"],
            property_ids=["prop-hardness"],
        ),
        observations=[
            Observation(
                id="obs-a",
                material_id="mat-a",
                mode_id="mode-aged",
                property_id="prop-hardness",
                evidence_id="ev-a",
            )
        ],
    )

    measured = heatmap.get_cell("mat-a", "mode-aged", "prop-hardness")
    missing = heatmap.get_cell("mat-a", "mode-hip", "prop-hardness")

    assert measured is not None
    assert measured.measured is True
    assert measured.observation_count == 1
    assert missing is not None
    assert missing.measured is False
    assert heatmap.coverage_ratio == 0.5


def test_compare_hypothesis_runs_reports_metric_deltas() -> None:
    deterministic = HypothesisGenerationResult(
        target_kpi="Conductivity",
        generation_engine="deterministic",
        hypotheses=[
            _hypothesis("det-1", final_score=0.6, evidence_ids=["ev-1"]),
        ],
    )
    agent = HypothesisGenerationResult(
        target_kpi="Conductivity",
        generation_engine="agent",
        hypotheses=[
            _hypothesis("agent-1", final_score=0.8, evidence_ids=["missing"]),
        ],
    )
    context = MetricContext(evidence_ids=["ev-1"])

    extraction = ExtractionBenchmark(
        samples=[
            ExtractionBenchmarkSample(
                sample_id="doc-1",
                expected_entities=[EntityMatch(kind=EntityKind.MATERIAL, name="CuCrZr")],
                extracted_entities=[EntityMatch(kind=EntityKind.MATERIAL, name="CuCrZr")],
                expected_relations=[],
                extracted_relations=[],
            )
        ]
    )
    context_benchmark = ContextBenchmark(
        expected_context_ids=["ev-1", "ev-2"],
        retrieved_context_ids=["ev-1"],
        expected_entity_ids=["mat-1"],
        retrieved_entity_ids=["mat-1"],
    )

    comparison = compare_hypothesis_runs(
        RunMetricsInput(
            name="deterministic",
            result=deterministic,
            context=context,
            extraction_benchmark=extraction,
            context_benchmark=context_benchmark,
        ),
        RunMetricsInput(
            name="agent",
            result=agent,
            context=context,
            extraction_benchmark=extraction,
            context_benchmark=context_benchmark,
        ),
    )

    assert comparison.left.name == "deterministic"
    assert comparison.right.name == "agent"
    assert comparison.deltas["average_final_score"] == 0.2
    assert comparison.deltas["average_faithfulness"] == -1.0
    assert comparison.left.metrics.entity_f1 == 1.0
    assert comparison.left.metrics.context_recall == 0.5
    assert comparison.left.metrics.context_entities_recall == 1.0
    assert "entity_f1" in comparison.deltas
    assert "context_recall" in comparison.deltas


def test_expert_feedback_store_and_weight_recalibration(tmp_path: Path) -> None:
    store = ExpertFeedbackStore(tmp_path / "feedback.jsonl")
    store.save(
        ExpertFeedbackEntry(
            hypothesis_id="h-low-1",
            rating=1,
            score=HypothesisScore(
                novelty=0.1,
                risk=0.9,
                value=0.2,
                evidence_strength=0.1,
                final_score=0.2,
            ),
        )
    )
    store.save(
        ExpertFeedbackEntry(
            hypothesis_id="h-low-2",
            rating=1,
            score=HypothesisScore(
                novelty=0.15,
                risk=0.85,
                value=0.25,
                evidence_strength=0.15,
                final_score=0.22,
            ),
        )
    )
    store.save(
        ExpertFeedbackEntry(
            hypothesis_id="h-mid",
            rating=3,
            score=HypothesisScore(
                novelty=0.5,
                risk=0.5,
                value=0.55,
                evidence_strength=0.5,
                final_score=0.55,
            ),
        )
    )
    store.save(
        ExpertFeedbackEntry(
            hypothesis_id="h-high-1",
            rating=5,
            score=HypothesisScore(
                novelty=0.8,
                risk=0.1,
                value=0.9,
                evidence_strength=0.8,
                final_score=0.85,
            ),
        )
    )
    store.save(
        ExpertFeedbackEntry(
            hypothesis_id="h-high-2",
            rating=5,
            score=HypothesisScore(
                novelty=0.85,
                risk=0.1,
                value=0.92,
                evidence_strength=0.85,
                final_score=0.88,
            ),
        )
    )

    entries = store.load()
    weights = recalibrate_ranking_weights(entries)
    correlation = automatic_expert_correlation(entries)

    assert [entry.hypothesis_id for entry in entries] == [
        "h-low-1",
        "h-low-2",
        "h-mid",
        "h-high-1",
        "h-high-2",
    ]
    assert weights.value > 0
    assert weights.evidence_strength > 0
    assert weights.inverse_risk > 0
    assert weights.total == 1.0
    assert correlation is not None
    assert correlation > 0.99


def test_expert_feedback_store_skips_corrupt_jsonl_lines(tmp_path: Path) -> None:
    feedback_file = tmp_path / "feedback.jsonl"
    store = ExpertFeedbackStore(feedback_file)
    valid_entry = ExpertFeedbackEntry(
        hypothesis_id="h-valid",
        rating=4,
        score=HypothesisScore(
            novelty=0.4,
            risk=0.2,
            value=0.8,
            evidence_strength=0.7,
            final_score=0.72,
        ),
    )
    store.save(valid_entry)
    feedback_file.write_text(
        f"{valid_entry.model_dump_json()}\n"
        "{not-valid-json}\n"
        '{"hypothesis_id": "bad-rating", "rating": 9, "score": {}}\n',
        encoding="utf-8",
    )

    entries = store.load()

    assert [entry.hypothesis_id for entry in entries] == ["h-valid"]


def test_expert_correlation_and_weights_handle_sparse_or_constant_data() -> None:
    entry = ExpertFeedbackEntry(
        hypothesis_id="h-one",
        rating=3,
        score=HypothesisScore(
            novelty=0.5,
            risk=0.5,
            value=0.5,
            evidence_strength=0.5,
            final_score=0.5,
        ),
    )
    constant_entries = [
        entry,
        entry.model_copy(update={"hypothesis_id": "h-two", "rating": 5}),
    ]

    assert automatic_expert_correlation([]) is None
    assert automatic_expert_correlation([entry]) is None
    assert automatic_expert_correlation(constant_entries) is None
    assert recalibrate_ranking_weights([]) == RankingWeights(
        value=0.35,
        evidence_strength=0.25,
        novelty=0.20,
        inverse_risk=0.20,
    )
    assert recalibrate_ranking_weights(constant_entries) == RankingWeights(
        value=0.35,
        evidence_strength=0.25,
        novelty=0.20,
        inverse_risk=0.20,
    )
    assert score_with_weights(
        entry.score,
        RankingWeights(
            value=0.0,
            evidence_strength=0.0,
            novelty=0.0,
            inverse_risk=0.0,
        ),
    ) == 0.0


def test_faithfulness_with_text_unit_ids() -> None:
    hyp_no_match = ResearchHypothesis(
        id="hyp-tu-no-match",
        target_kpi="Conductivity",
        statement="Hypothesis referencing a text unit not in context",
        rationale="Text unit support missing",
        test_plan="Check faithfulness drops",
        score=HypothesisScore(
            novelty=0.5, risk=0.2, value=0.6, evidence_strength=0.6, final_score=0.6,
        ),
        supporting_text_unit_ids=["tu-missing"],
    )
    hyp_with_match = ResearchHypothesis(
        id="hyp-tu-match",
        target_kpi="Conductivity",
        statement="Hypothesis referencing a text unit present in context",
        rationale="Text unit support present",
        test_plan="Check faithfulness rises",
        score=HypothesisScore(
            novelty=0.5, risk=0.2, value=0.6, evidence_strength=0.6, final_score=0.6,
        ),
        supporting_text_unit_ids=["tu-1"],
    )
    context = MetricContext(text_unit_ids=["tu-1"])

    result = evaluate_hypothesis_metrics(
        hypotheses=[hyp_no_match, hyp_with_match],
        context=context,
    )

    assert result.items[0].faithfulness == 0.0
    assert result.items[1].faithfulness > 0.0


def test_groundedness_with_supporting_entity_ids() -> None:
    hyp_with_entity = ResearchHypothesis(
        id="hyp-ent-match",
        target_kpi="Conductivity",
        statement="Hypothesis supported by an entity in context",
        rationale="Entity present",
        test_plan="Check groundedness",
        score=HypothesisScore(
            novelty=0.5, risk=0.2, value=0.6, evidence_strength=0.6, final_score=0.6,
        ),
        supporting_entity_ids=["entity-1"],
    )
    hyp_without_entity = ResearchHypothesis(
        id="hyp-ent-missing",
        target_kpi="Conductivity",
        statement="Hypothesis supported by an entity not in context",
        rationale="Entity absent",
        test_plan="Check groundedness drops",
        score=HypothesisScore(
            novelty=0.5, risk=0.2, value=0.6, evidence_strength=0.6, final_score=0.6,
        ),
        supporting_entity_ids=["entity-missing"],
    )
    context = MetricContext(entity_ids=["entity-1"])

    result = evaluate_hypothesis_metrics(
        hypotheses=[hyp_with_entity, hyp_without_entity],
        context=context,
        coverage=None,
    )

    assert result.items[0].groundedness == 1.0
    assert result.items[1].groundedness == 0.0


def test_empty_support_sets_yield_zero_faithfulness_and_groundedness() -> None:
    hypothesis = ResearchHypothesis(
        id="hyp-empty-support",
        target_kpi="Conductivity",
        statement="Hypothesis with no supporting evidence at all",
        rationale="No support",
        test_plan="Verify zero metrics",
        score=HypothesisScore(
            novelty=0.5, risk=0.2, value=0.6, evidence_strength=0.6, final_score=0.6,
        ),
    )

    result = evaluate_hypothesis_metrics(hypotheses=[hypothesis])

    assert result.items[0].faithfulness == 0.0
    assert result.items[0].groundedness == 0.0


def test_mixed_novelty_one_measured_one_missing_returns_weighted_ratio() -> None:
    """Mixed measured/missing cells return weighted novelty ratio."""
    hypothesis = ResearchHypothesis(
        id="hyp-mixed",
        target_kpi="Conductivity",
        statement="Hypothesis covering both measured and missing cells",
        rationale="Mixed coverage",
        test_plan="Check novelty",
        score=HypothesisScore(
            novelty=0.5, risk=0.2, value=0.6, evidence_strength=0.6, final_score=0.6,
        ),
        supporting_entity_ids=["mat-a", "mode-aging", "prop-hardness", "mode-hip"],
    )
    coverage = build_coverage_heatmap(
        axes=CoverageAxis(
            material_ids=["mat-a"],
            mode_ids=["mode-aging", "mode-hip"],
            property_ids=["prop-hardness"],
        ),
        observations=[
            Observation(
                id="obs-1",
                material_id="mat-a",
                mode_id="mode-aging",
                property_id="prop-hardness",
                evidence_id="ev-1",
            )
        ],
    )

    result = evaluate_hypothesis_metrics(
        hypotheses=[hypothesis],
        coverage=coverage,
    )

    assert result.items[0].novelty == 0.5
    assert result.items[0].coverage_status == "mixed"


def test_score_with_weights_edge_cases() -> None:
    score = HypothesisScore(
        novelty=0.8, risk=1.0, value=0.9, evidence_strength=0.7, final_score=0.5,
    )

    zero_result = score_with_weights(
        score,
        RankingWeights(value=0.0, evidence_strength=0.0, novelty=0.0, inverse_risk=0.0),
    )
    assert zero_result == 0.0

    perfect_score = HypothesisScore(
        novelty=1.0, risk=0.0, value=1.0, evidence_strength=1.0, final_score=1.0,
    )
    default_result = score_with_weights(perfect_score, RankingWeights(
        value=0.35, evidence_strength=0.25, novelty=0.20, inverse_risk=0.20,
    ))
    assert default_result == 1.0

    max_risk_score = HypothesisScore(
        novelty=0.5, risk=1.0, value=0.5, evidence_strength=0.5, final_score=0.5,
    )
    weights = RankingWeights(
        value=0.0, evidence_strength=0.0, novelty=0.0, inverse_risk=1.0,
    )
    result = score_with_weights(max_risk_score, weights)
    assert result == 0.0


def test_compare_hypothesis_runs_identical_produces_zero_deltas() -> None:
    run_input = RunMetricsInput(
        name="run-a",
        result=HypothesisGenerationResult(
            target_kpi="Conductivity",
            hypotheses=[
                _hypothesis("hyp-1", final_score=0.5, evidence_ids=["ev-1"]),
            ],
        ),
        context=MetricContext(evidence_ids=["ev-1"]),
        extraction_benchmark=ExtractionBenchmark(
            samples=[
                ExtractionBenchmarkSample(
                    sample_id="doc-1",
                    expected_entities=[EntityMatch(kind=EntityKind.MATERIAL, name="CuCrZr")],
                    extracted_entities=[EntityMatch(kind=EntityKind.MATERIAL, name="CuCrZr")],
                    expected_relations=[],
                    extracted_relations=[],
                )
            ]
        ),
        context_benchmark=ContextBenchmark(
            expected_context_ids=["ev-1"],
            retrieved_context_ids=["ev-1"],
            expected_entity_ids=["mat-1"],
            retrieved_entity_ids=["mat-1"],
        ),
    )
    run_clone = run_input.model_copy(deep=True)
    run_clone.name = "run-b"

    comparison = compare_hypothesis_runs(run_input, run_clone)

    assert all(delta == 0.0 for delta in comparison.deltas.values())


def test_evaluate_extraction_benchmark_empty_returns_zero_f1() -> None:
    benchmark = ExtractionBenchmark(samples=[])

    result = evaluate_extraction_benchmark(benchmark)

    assert result.entity.f1 == 0.0
    assert result.relation.f1 == 0.0


def test_evaluate_context_metrics_empty_returns_zero_recall() -> None:
    benchmark = ContextBenchmark()

    result = evaluate_context_metrics(benchmark)

    assert result.context_recall == 0.0
    assert result.context_entities_recall == 0.0


def test_hypothesis_metrics_empty_input_returns_zero_summary() -> None:
    result = evaluate_hypothesis_metrics(hypotheses=[])

    assert result.items == []
    assert result.average_faithfulness == 0.0
    assert result.average_groundedness == 0.0
    assert result.average_novelty == 0.0
    assert result.average_final_score == 0.0


def test_calibrated_ranking_reorders_hypotheses_with_expert_weights() -> None:
    result = HypothesisGenerationResult(
        target_kpi="Conductivity",
        hypotheses=[
            _scored_hypothesis(
                "high-value",
                value=0.9,
                evidence_strength=0.1,
                novelty=0.1,
                risk=0.1,
            ),
            _scored_hypothesis(
                "high-evidence",
                value=0.1,
                evidence_strength=0.95,
                novelty=0.1,
                risk=0.1,
            ),
        ],
    )

    reranked = apply_calibrated_ranking(
        result,
        RankingWeights(
            value=0.05,
            evidence_strength=0.8,
            novelty=0.05,
            inverse_risk=0.1,
        ),
    )

    assert [hypothesis.id for hypothesis in reranked.hypotheses] == [
        "high-evidence",
        "high-value",
    ]
    assert [hypothesis.rank for hypothesis in reranked.hypotheses] == [1, 2]
    assert reranked.ranking_rubric["calibrated_weights"] == {
        "value": 0.05,
        "evidence_strength": 0.8,
        "novelty": 0.05,
        "inverse_risk": 0.1,
        "total": 1.0,
    }
    assert "final_score_formula" in reranked.ranking_rubric


def test_coverage_heatmap_can_be_built_from_repository() -> None:
    repo = InMemoryMaterialsKGRepository()
    repo.upsert_observation(
        Observation(
            id="obs-a",
            material_id="mat-a",
            mode_id="mode-a",
            property_id="prop-a",
            evidence_id="ev-a",
        )
    )

    heatmap = build_coverage_heatmap(
        axes=CoverageAxis(
            material_ids=["mat-a"],
            mode_ids=["mode-a"],
            property_ids=["prop-a"],
        ),
        repository=repo,
    )

    assert heatmap.coverage_ratio == 1.0


def test_repository_coverage_heatmap_derives_material_mode_property_axes() -> None:
    repo = InMemoryMaterialsKGRepository()
    repo.upsert_observation(
        Observation(
            id="obs-a",
            material_id="mat-a",
            mode_id="mode-a",
            property_id="prop-a",
            evidence_id="ev-a",
        )
    )

    heatmap = build_repository_coverage_heatmap(repo)

    assert heatmap.axes.material_ids == ["mat-a"]
    assert heatmap.axes.mode_ids == ["mode-a"]
    assert heatmap.axes.property_ids == ["prop-a"]
    assert heatmap.coverage_ratio == 1.0


def _hypothesis(
    hypothesis_id: str,
    *,
    final_score: float,
    evidence_ids: list[str],
) -> ResearchHypothesis:
    return ResearchHypothesis(
        id=hypothesis_id,
        target_kpi="Conductivity",
        statement="Test a measured materials hypothesis",
        rationale="Grounded in available evidence",
        test_plan="Run a controlled experiment",
        score=HypothesisScore(
            novelty=0.5,
            risk=0.2,
            value=final_score,
            evidence_strength=final_score,
            final_score=final_score,
        ),
        supporting_evidence_ids=evidence_ids,
    )


def _scored_hypothesis(
    hypothesis_id: str,
    *,
    value: float,
    evidence_strength: float,
    novelty: float,
    risk: float,
) -> ResearchHypothesis:
    return ResearchHypothesis(
        id=hypothesis_id,
        target_kpi="Conductivity",
        statement="Test calibrated ranking",
        rationale="Ranking uses expert-calibrated weights",
        test_plan="Compare ranked hypotheses",
        score=HypothesisScore(
            novelty=novelty,
            risk=risk,
            value=value,
            evidence_strength=evidence_strength,
            final_score=0.0,
        ),
    )
