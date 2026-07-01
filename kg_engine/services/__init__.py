"""Service APIs for the graph-first materials KG core."""

from kg_engine.services.materials_kg import MaterialsKGService
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

__all__ = [
    "ContextBenchmark",
    "CoverageAxis",
    "EntityMatch",
    "ExpertFeedbackEntry",
    "ExpertFeedbackStore",
    "ExtractionBenchmark",
    "ExtractionBenchmarkSample",
    "MaterialsKGService",
    "MetricContext",
    "RankingWeights",
    "RelationMatch",
    "RunMetricsInput",
    "apply_calibrated_ranking",
    "automatic_expert_correlation",
    "build_repository_coverage_heatmap",
    "build_coverage_heatmap",
    "compare_hypothesis_runs",
    "evaluate_context_metrics",
    "evaluate_extraction_benchmark",
    "evaluate_hypothesis_metrics",
    "recalibrate_ranking_weights",
    "score_with_weights",
]
