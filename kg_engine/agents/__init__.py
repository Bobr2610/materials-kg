"""Agent orchestration entrypoints for Materials KG."""

from kg_engine.agents.extraction_agent import extract_and_resolve
from kg_engine.agents.extraction_agent import resolve_relation_type
from kg_engine.agents.hypothesis_factory import DeepAgentsConfigurationError
from kg_engine.agents.hypothesis_factory import DeepAgentsResultError
from kg_engine.agents.hypothesis_factory import generate_hypotheses_with_deep_agent

__all__ = [
    "DeepAgentsConfigurationError",
    "DeepAgentsResultError",
    "extract_and_resolve",
    "generate_hypotheses_with_deep_agent",
    "resolve_relation_type",
]
