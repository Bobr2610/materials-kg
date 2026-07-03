"""Read-only tools exposed to the Deep Agents Hypothesis Factory."""

from __future__ import annotations

from typing import Any

from kg_engine.domain.models import HypothesisInput
from kg_engine.domain.models import PropertyFilters
from kg_engine.domain.models import QueryFilters
from kg_engine.domain.models import RelationType
from kg_engine.services.materials_kg import MaterialsKGService


def create_hypothesis_tools(
    service: MaterialsKGService,
    agent_trace: list[dict[str, Any]] | None = None,
    max_tool_steps: int | None = None,
) -> list[Any]:
    """Create read-only graph tools scoped to a MaterialsKGService instance."""

    trace = agent_trace if agent_trace is not None else []
    tool_call_count = 0

    def record_tool(name: str, **metadata: Any) -> None:
        nonlocal tool_call_count
        tool_call_count += 1
        if max_tool_steps is not None and tool_call_count > max_tool_steps:
            msg = f"Deep Agents exceeded max read-only tool steps: {max_tool_steps}"
            raise RuntimeError(msg)
        trace.append({"event": "tool_call", "tool": name, **metadata})

    def tool_error(name: str, error: ValueError) -> dict[str, Any]:
        message = str(error)
        trace.append({"event": "tool_warning", "tool": name, "warning": message})
        return {"tool": name, "error": message}

    def kg_build_context(
        target_kpi: str,
        question: str = "",
        material: str | None = None,
        mode: str | None = None,
        property_name: str | None = None,
        source_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Build a compact graph context packet for a KPI hypothesis task."""
        record_tool("kg_build_context", target_kpi=target_kpi)
        baseline = service.generate_hypotheses(
            HypothesisInput(
                target_kpi=target_kpi,
                question=question,
                material=material,
                mode=mode,
                property_name=property_name,
                source_ids=source_ids,
                max_hypotheses=10,
            )
        )
        return {
            "target_kpi": baseline.target_kpi,
            "resolved_query": baseline.resolved_query,
            "knowledge_base_summary": baseline.knowledge_base_summary,
            "ranking_rubric": baseline.ranking_rubric,
            "matched_entities": [
                item.model_dump(mode="json") for item in baseline.matched_entities
            ],
            "observations": [
                item.model_dump(mode="json") for item in baseline.observations[:20]
            ],
            "evidence": [item.model_dump(mode="json") for item in baseline.evidence[:20]],
            "data_gaps": [
                item.model_dump(mode="json") for item in baseline.data_gaps[:20]
            ],
            "search_hits": [
                item.model_dump(mode="json") for item in baseline.search_hits[:20]
            ],
            "warnings": baseline.warnings,
        }

    def kg_generate_baseline_hypotheses(
        target_kpi: str,
        question: str = "",
        material: str | None = None,
        mode: str | None = None,
        property_name: str | None = None,
        source_ids: list[str] | None = None,
        max_hypotheses: int = 5,
    ) -> dict[str, Any]:
        """Generate deterministic baseline hypotheses from graph evidence."""
        record_tool("kg_generate_baseline_hypotheses", target_kpi=target_kpi)
        result = service.generate_hypotheses(
            HypothesisInput(
                target_kpi=target_kpi,
                question=question,
                material=material,
                mode=mode,
                property_name=property_name,
                source_ids=source_ids,
                max_hypotheses=max_hypotheses,
            )
        )
        return result.model_dump(mode="json")

    def kg_query_data_gaps(
        material_name: str | None = None,
        mode_name: str | None = None,
        property_name: str | None = None,
        source_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return rule-driven data gaps for a material/mode/property filter."""
        record_tool("kg_query_data_gaps", property_name=property_name)
        gaps = service.query_data_gaps(
            filters=QueryFilters(
                material_name=material_name,
                mode_name=mode_name,
                property_name=property_name,
            ),
            source_ids=source_ids,
        )
        return [gap.model_dump(mode="json") for gap in gaps]

    def kg_search_evidence(
        query: str,
        limit: int = 8,
        source_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search indexed text units for literature and report evidence."""
        record_tool("kg_search_evidence", query=query, limit=limit)
        hits = service.search_evidence_units(query, limit=limit, source_ids=source_ids)
        return [hit.model_dump(mode="json") for hit in hits]

    def kg_get_source_overview() -> dict[str, Any]:
        """Return source, entity, observation, relation, and evidence counts."""
        record_tool("kg_get_source_overview")
        return service.get_source_overview()

    def kg_query_material_mode(
        material: str,
        mode: str | None = None,
        property_name: str | None = None,
    ) -> dict[str, Any]:
        """Return experiments, observations, findings, evidence, and text hits for a material/mode/property slice."""
        record_tool(
            "kg_query_material_mode",
            material=material,
            mode=mode,
            property_name=property_name,
        )
        try:
            return service.query_material_mode(
                material,
                mode=mode,
                property_name=property_name,
            ).model_dump(mode="json")
        except ValueError as exc:
            return tool_error("kg_query_material_mode", exc)

    def kg_query_property(
        property_name: str,
        material_name: str | None = None,
        mode_name: str | None = None,
        min_value: float | None = None,
        max_value: float | None = None,
    ) -> dict[str, Any]:
        """Return observations, materials, experiments, and evidence for a property with optional range filters."""
        record_tool(
            "kg_query_property",
            property_name=property_name,
            material_name=material_name,
            mode_name=mode_name,
        )
        try:
            return service.query_property(
                property_name,
                PropertyFilters(
                    material_name=material_name,
                    mode_name=mode_name,
                    min_value=min_value,
                    max_value=max_value,
                ),
            ).model_dump(mode="json")
        except ValueError as exc:
            return tool_error("kg_query_property", exc)

    def kg_query_related(
        entity: str,
        depth: int = 2,
        relation_types: list[str] | None = None,
    ) -> dict[str, Any]:
        """Traverse related entities and evidence paths around a material, experiment, property, mode, team, or document."""
        record_tool("kg_query_related", entity=entity, depth=depth)
        filters: list[RelationType] | None = None
        if relation_types:
            filters = []
            for rel_type in relation_types:
                try:
                    filters.append(RelationType(rel_type))
                except ValueError:
                    trace.append(
                        {
                            "event": "tool_warning",
                            "tool": "kg_query_related",
                            "warning": f"unknown relation type skipped: {rel_type}",
                        }
                    )
        try:
            return service.query_related(
                entity,
                depth=max(1, min(depth, 4)),
                relation_filters=filters,
            ).model_dump(mode="json")
        except ValueError as exc:
            return tool_error("kg_query_related", exc)

    def kg_query_decision_history(entity_or_experiment: str) -> dict[str, Any]:
        """Return decision traces and evidence for a canonical entity or experiment."""
        record_tool(
            "kg_query_decision_history",
            entity_or_experiment=entity_or_experiment,
        )
        try:
            return service.query_decision_history(entity_or_experiment).model_dump(
                mode="json"
            )
        except ValueError as exc:
            return tool_error("kg_query_decision_history", exc)

    return [
        kg_build_context,
        kg_generate_baseline_hypotheses,
        kg_query_data_gaps,
        kg_search_evidence,
        kg_get_source_overview,
        kg_query_material_mode,
        kg_query_property,
        kg_query_related,
        kg_query_decision_history,
    ]
