from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient
import pytest

from kg_engine.agents.hypothesis_factory import DeepAgentsConfigurationError
from kg_engine.agents.hypothesis_factory import DeepAgentsResultError
from kg_engine.agents.hypothesis_factory import generate_hypotheses_with_deep_agent
from kg_engine.agents.hypothesis_tools import create_hypothesis_tools
from kg_engine.api.materials_core import create_materials_app
from kg_engine.config.settings import Settings
from kg_engine.domain.models import CanonicalEntityInput
from kg_engine.domain.models import CoverageRuleInput
from kg_engine.domain.models import DocumentInput
from kg_engine.domain.models import EntityKind
from kg_engine.domain.models import ExperimentInput
from kg_engine.domain.models import FindingInput
from kg_engine.domain.models import HypothesisInput
from kg_engine.domain.models import ObservationInput
from kg_engine.domain.models import ReferenceDataBatch
from kg_engine.domain.models import RelationType
from kg_engine.domain.models import TextUnitInput
from kg_engine.llm_core.extraction import extract_entities_from_document
from kg_engine.llm_core.extraction import select_extraction_strategy
from kg_engine.repositories.memory import InMemoryMaterialsKGRepository
from kg_engine.services.materials_kg import MaterialsKGService


class _Message:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeDeepAgent:
    def __init__(self, payload: dict[str, Any], tools: list[Any]) -> None:
        self._payload = payload
        self._tools = tools
        self.invoke_inputs: list[dict[str, Any]] = []

    def invoke(self, payload: dict[str, Any], *, config: dict[str, Any]) -> dict[str, Any]:
        self.invoke_inputs.append({"payload": payload, "config": config})
        for tool in self._tools:
            if tool.__name__ == "kg_get_source_overview":
                tool()
        return {"messages": [_Message(json.dumps(self._payload, ensure_ascii=False))]}


def _build_service() -> MaterialsKGService:
    service = MaterialsKGService(InMemoryMaterialsKGRepository())
    service.ingest_reference_data(
        ReferenceDataBatch(
            entities=[
                CanonicalEntityInput(kind=EntityKind.MATERIAL, name="CuCrZr"),
                CanonicalEntityInput(kind=EntityKind.MODE, name="Aged"),
                CanonicalEntityInput(
                    kind=EntityKind.PROPERTY,
                    name="Electrical Conductivity",
                ),
            ],
        )
    )
    service.ingest_experiments(
        [
            ExperimentInput(
                experiment_id="exp-cu",
                title="CuCrZr aging conductivity",
                material_name="CuCrZr",
                mode_name="Aged",
                observations=[
                    ObservationInput(
                        property_name="Electrical Conductivity",
                        value=58.0,
                        unit="%IACS",
                        fragment="CuCrZr aged sample reached 58 %IACS",
                    )
                ],
            )
        ]
    )
    return service


def _settings() -> Settings:
    return Settings(
        materials_hypothesis_engine="deepagents",
        materials_deepagents_enabled=True,
        materials_deepagents_max_tool_steps=7,
        default_llm_provider="openai",
        default_model="gpt-test",
        openai_api_key="test-key",
    )


def test_deep_agent_factory_validates_result_and_records_trace() -> None:
    service = _build_service()
    baseline = service.generate_hypotheses(
        HypothesisInput(target_kpi="Electrical Conductivity", material="CuCrZr")
    )
    payload = baseline.model_dump(mode="json")
    payload["generation_engine"] = "deepagents"
    payload["agent_trace"] = [{"event": "agent_report"}]

    created: dict[str, Any] = {}

    def fake_agent_factory(**kwargs: Any) -> _FakeDeepAgent:
        created.update(kwargs)
        return _FakeDeepAgent(payload, kwargs["tools"])

    result = generate_hypotheses_with_deep_agent(
        service,
        HypothesisInput(target_kpi="Electrical Conductivity", material="CuCrZr"),
        runtime_settings=_settings(),
        agent_factory=fake_agent_factory,
        model_factory=lambda _: ("fake-model", "openai:gpt-test"),
    )

    assert result.generation_engine == "deepagents"
    assert result.llm_used == "openai:gpt-test"
    assert result.hypotheses
    assert result.agent_trace[0]["event"] == "agent_prepare"
    assert result.agent_trace[0]["max_tool_steps"] == 7
    assert result.agent_trace[0]["recursion_limit"] == 42
    assert any(item.get("event") == "tool_call" for item in result.agent_trace)
    assert created["tools"][0] is not None
    assert created["name"] == "materials-hypothesis-factory"
    assert {item["name"] for item in created["subagents"]} == {
        "evidence_analyst",
        "novelty_reviewer",
        "risk_reviewer",
        "ranker",
    }
    assert "Electrical Conductivity" in created["system_prompt"]
    assert "entity_counts_by_kind" in created["system_prompt"]


def test_deep_agent_rejects_non_json_without_deterministic_fallback() -> None:
    service = _build_service()

    class BadAgent:
        def invoke(
            self, payload: dict[str, Any], *, config: dict[str, Any]
        ) -> dict[str, Any]:
            _ = (payload, config)
            return {"messages": [_Message("not json")]}

    with pytest.raises(DeepAgentsResultError):
        generate_hypotheses_with_deep_agent(
            service,
            HypothesisInput(target_kpi="Electrical Conductivity"),
            runtime_settings=_settings(),
            agent_factory=lambda **_: BadAgent(),
            model_factory=lambda _: ("fake-model", "openai:gpt-test"),
        )


def test_deep_agent_invocation_error_is_explicit() -> None:
    service = _build_service()

    class FailingAgent:
        def invoke(
            self, payload: dict[str, Any], *, config: dict[str, Any]
        ) -> dict[str, Any]:
            _ = (payload, config)
            msg = "provider unavailable"
            raise RuntimeError(msg)

    with pytest.raises(DeepAgentsConfigurationError, match="RuntimeError"):
        generate_hypotheses_with_deep_agent(
            service,
            HypothesisInput(target_kpi="Electrical Conductivity"),
            runtime_settings=_settings(),
            agent_factory=lambda **_: FailingAgent(),
            model_factory=lambda _: ("fake-model", "openai:gpt-test"),
        )


def test_deep_agent_llm_preflight_runs_before_factories() -> None:
    service = _build_service()

    def fail_agent_factory(**_: Any) -> _FakeDeepAgent:
        msg = "agent factory should not run"
        raise AssertionError(msg)

    with pytest.raises(DeepAgentsConfigurationError, match="API key"):
        generate_hypotheses_with_deep_agent(
            service,
            HypothesisInput(target_kpi="Electrical Conductivity"),
            runtime_settings=Settings(
                materials_deepagents_enabled=True,
                default_llm_provider="openai",
                default_model="gpt-test",
                openai_api_key="",
            ),
            agent_factory=fail_agent_factory,
        )


def test_deep_agent_discards_ungrounded_hypotheses() -> None:
    service = _build_service()
    baseline = service.generate_hypotheses(
        HypothesisInput(target_kpi="Electrical Conductivity", material="CuCrZr")
    )
    payload = baseline.model_dump(mode="json")
    unsupported = payload["hypotheses"][0].copy()
    unsupported.update(
        {
            "id": "hallucinated-hypothesis",
            "supporting_entity_ids": [],
            "supporting_evidence_ids": [],
            "supporting_observation_ids": [],
            "supporting_text_unit_ids": [],
            "data_gap_ids": [],
        }
    )
    payload["hypotheses"].append(unsupported)
    payload["generation_engine"] = "deepagents"

    result = generate_hypotheses_with_deep_agent(
        service,
        HypothesisInput(target_kpi="Electrical Conductivity", material="CuCrZr"),
        runtime_settings=_settings(),
        agent_factory=lambda **kwargs: _FakeDeepAgent(payload, kwargs["tools"]),
        model_factory=lambda _: ("fake-model", "openai:gpt-test"),
    )

    assert "hallucinated-hypothesis" not in {item.id for item in result.hypotheses}
    assert any("Discarded ungrounded hypotheses" in item for item in result.warnings)
    assert any(
        item.get("event") == "ungrounded_hypotheses_discarded"
        for item in result.agent_trace
    )


def test_hypothesis_tools_are_read_only() -> None:
    service = _build_service()
    before = service.get_source_overview()
    trace: list[dict[str, Any]] = []
    tools = {tool.__name__: tool for tool in create_hypothesis_tools(service, trace)}

    context = tools["kg_build_context"](
        target_kpi="Electrical Conductivity",
        material="CuCrZr",
    )
    overview = tools["kg_get_source_overview"]()
    hits = tools["kg_search_evidence"]("CuCrZr conductivity")
    after = service.get_source_overview()

    assert context["knowledge_base_summary"]["observations"] == 1
    assert overview == after == before
    assert isinstance(hits, list)
    assert [item["event"] for item in trace] == [
        "tool_call",
        "tool_call",
        "tool_call",
    ]


def test_hypothesis_tools_expose_full_read_api() -> None:
    service = _build_service()
    trace: list[dict[str, Any]] = []
    tools = {tool.__name__: tool for tool in create_hypothesis_tools(service, trace)}

    assert set(tools) == {
        "kg_build_context",
        "kg_generate_baseline_hypotheses",
        "kg_query_data_gaps",
        "kg_search_evidence",
        "kg_get_source_overview",
        "kg_query_material_mode",
        "kg_query_property",
        "kg_query_related",
        "kg_query_decision_history",
    }

    material_mode = tools["kg_query_material_mode"](
        material="CuCrZr",
        mode="Aged",
        property_name="Electrical Conductivity",
    )
    prop = tools["kg_query_property"]("Electrical Conductivity", material_name="CuCrZr")
    related = tools["kg_query_related"]("CuCrZr", depth=1)
    history = tools["kg_query_decision_history"]("exp-cu")

    assert material_mode["observations"]
    assert prop["observations"]
    assert related["root_entity"]["canonical_name"] == "CuCrZr"
    assert history["requested_entity"]["id"] == "exp-cu"
    assert [item["tool"] for item in trace] == [
        "kg_query_material_mode",
        "kg_query_property",
        "kg_query_related",
        "kg_query_decision_history",
    ]


def test_hypothesis_tools_enforce_max_tool_steps() -> None:
    service = _build_service()
    tools = {tool.__name__: tool for tool in create_hypothesis_tools(service, max_tool_steps=1)}

    tools["kg_get_source_overview"]()
    with pytest.raises(RuntimeError, match="max read-only tool steps"):
        tools["kg_get_source_overview"]()


def test_hypothesis_tools_filter_by_source_ids() -> None:
    service = MaterialsKGService(InMemoryMaterialsKGRepository())
    service.ingest_reference_data(
        ReferenceDataBatch(
            entities=[
                CanonicalEntityInput(
                    kind=EntityKind.MATERIAL,
                    name="Material-A",
                    source_ref="file-a.json",
                ),
                CanonicalEntityInput(
                    kind=EntityKind.MODE,
                    name="Mode-A",
                    source_ref="file-a.json",
                ),
                CanonicalEntityInput(
                    kind=EntityKind.PROPERTY,
                    name="KPI-A",
                    source_ref="file-a.json",
                ),
                CanonicalEntityInput(
                    kind=EntityKind.PROPERTY,
                    name="KPI-A-Missing",
                    source_ref="file-a.json",
                ),
                CanonicalEntityInput(
                    kind=EntityKind.MATERIAL,
                    name="Material-B",
                    source_ref="file-b.json",
                ),
                CanonicalEntityInput(
                    kind=EntityKind.MODE,
                    name="Mode-B",
                    source_ref="file-b.json",
                ),
                CanonicalEntityInput(
                    kind=EntityKind.PROPERTY,
                    name="KPI-B-Missing",
                    source_ref="file-b.json",
                ),
            ],
            coverage_rules=[
                CoverageRuleInput(
                    rule_id="rule-a",
                    name="A missing KPI",
                    material_names=["Material-A"],
                    mode_names=["Mode-A"],
                    property_names=["KPI-A-Missing"],
                ),
                CoverageRuleInput(
                    rule_id="rule-b",
                    name="B missing KPI",
                    material_names=["Material-B"],
                    mode_names=["Mode-B"],
                    property_names=["KPI-B-Missing"],
                ),
            ],
        )
    )
    service.ingest_experiments(
        [
            ExperimentInput(
                experiment_id="exp-a",
                title="Experiment A",
                material_name="Material-A",
                mode_name="Mode-A",
                source_ref="file-a.json",
                observations=[ObservationInput(property_name="KPI-A", value=1.0)],
                findings=[FindingInput(summary="Material-A source hit")],
                text_units=[TextUnitInput(content="Material-A source hit")],
            ),
            ExperimentInput(
                experiment_id="exp-b",
                title="Experiment B",
                material_name="Material-B",
                mode_name="Mode-B",
                source_ref="file-b.json",
                findings=[FindingInput(summary="Material-B source hit")],
                text_units=[TextUnitInput(content="Material-B source hit")],
            ),
        ]
    )

    tools = {tool.__name__: tool for tool in create_hypothesis_tools(service)}
    gaps = tools["kg_query_data_gaps"](source_ids=["file-a.json"])
    hits = tools["kg_search_evidence"]("source hit", source_ids=["file-a.json"])

    assert gaps
    assert all("Material-A" in gap["reason"] for gap in gaps)
    assert hits
    assert all(
        hit["metadata"].get("source_file") == "file-a.json"
        or hit["metadata"].get("source_id") == "file-a.json"
        for hit in hits
    )


def test_api_uses_deepagents_engine_with_injected_runner(monkeypatch) -> None:
    service = _build_service()
    baseline = service.generate_hypotheses(
        HypothesisInput(target_kpi="Electrical Conductivity", material="CuCrZr")
    )
    payload = baseline.model_dump(mode="json")
    payload["generation_engine"] = "deepagents"
    payload["llm_used"] = "openai:gpt-test"

    def fake_generate(
        runtime_service: MaterialsKGService,
        request: HypothesisInput,
        *,
        runtime_settings: Settings,
    ):
        _ = (runtime_service, request, runtime_settings)
        return baseline.model_copy(
            update={
                "generation_engine": "deepagents",
                "llm_used": "openai:gpt-test",
                "agent_trace": [{"event": "fake"}],
            }
        )

    from kg_engine import agents

    monkeypatch.setattr(agents, "generate_hypotheses_with_deep_agent", fake_generate)
    app = create_materials_app(
        settings=_settings(),
        service=service,
    )
    client = TestClient(app)

    response = client.post(
        "/hypotheses/generate",
        json={"target_kpi": "Electrical Conductivity", "material": "CuCrZr"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["generation_engine"] == "deepagents"
    assert body["llm_used"] == "openai:gpt-test"
    assert body["agent_trace"] == [{"event": "fake"}]


def test_api_returns_explicit_error_when_llm_config_is_missing() -> None:
    app = create_materials_app(
        settings=Settings(
            materials_hypothesis_engine="deepagents",
            materials_deepagents_enabled=True,
            default_llm_provider="openai",
            default_model="gpt-test",
            openai_api_key="",
        ),
        service=_build_service(),
    )
    client = TestClient(app)

    response = client.post(
        "/hypotheses/generate",
        json={"target_kpi": "Electrical Conductivity", "material": "CuCrZr"},
    )

    assert response.status_code == 503
    assert response.json()["detail"]


def test_expert_adjustments_apply_to_deep_agent_result() -> None:
    service = _build_service()
    baseline = service.generate_hypotheses(
        HypothesisInput(target_kpi="Electrical Conductivity", material="CuCrZr")
    )
    hyp_id = baseline.hypotheses[0].id
    old_score = baseline.hypotheses[0].score.final_score
    payload = baseline.model_dump(mode="json")
    payload["generation_engine"] = "deepagents"

    result = generate_hypotheses_with_deep_agent(
        service,
        HypothesisInput(
            target_kpi="Electrical Conductivity",
            material="CuCrZr",
            expert_adjustments={hyp_id: {"value_adjustment": 0.5, "note": "важно"}},
        ),
        runtime_settings=_settings(),
        agent_factory=lambda **kwargs: _FakeDeepAgent(payload, kwargs["tools"]),
        model_factory=lambda _: ("fake-model", "openai:gpt-test"),
    )

    assert result.hypotheses[0].score.final_score > old_score
    assert "важно" in result.hypotheses[0].expert_notes


def test_expert_adjustments_do_not_touch_unmatched_hypotheses() -> None:
    service = _build_service()

    result = service.generate_hypotheses(
        HypothesisInput(
            target_kpi="Electrical Conductivity",
            material="CuCrZr",
            expert_adjustments={"missing-hypothesis-id": {"note": "не применять"}},
        )
    )

    assert result.hypotheses
    assert all(not hypothesis.expert_notes for hypothesis in result.hypotheses)


class _QueuedJSONProvider:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = list(responses)
        self.messages: list[list[dict[str, str]]] = []

    def chat_json(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        max_tokens: int,
    ) -> dict[str, Any]:
        _ = (temperature, max_tokens)
        self.messages.append(messages)
        return self.responses.pop(0) if self.responses else {}


def test_extraction_uses_sequential_provider_neutral_phases() -> None:
    provider = _QueuedJSONProvider(
        [
            {
                "entities": [
                    {"kind": "material", "name": "CuCrZr"},
                    {"kind": "mode", "name": "Aging"},
                    {"kind": "property", "name": "Electrical Conductivity"},
                ]
            },
            {
                "relationships": [
                    {
                        "source": "CuCrZr",
                        "target": "Aging",
                        "type": "uses_mode",
                    },
                    {
                        "source": "Unknown material",
                        "target": "Aging",
                        "type": "uses_mode",
                    },
                ]
            },
            {
                "experiments": [
                    {
                        "experiment_id": "doc-exp-1",
                        "title": "Aging trial",
                        "material_name": "CuCrZr",
                        "mode_name": "Aging",
                        "observations": [
                            {
                                "property_name": "Electrical Conductivity",
                                "value": 58.0,
                                "unit": "%IACS",
                                "comparator": ">=",
                                "fragment": "CuCrZr reached >=58 %IACS",
                                "row_reference": "row-7",
                                "confidence": 0.9,
                            }
                        ],
                    }
                ]
            },
        ]
    )

    result = extract_entities_from_document(
        provider,  # type: ignore[arg-type]
        "CuCrZr report",
        "CuCrZr after Aging measured Electrical Conductivity of >=58 %IACS.",
    )

    assert result.extraction_engine == "llm_phased"
    assert [item["event"] for item in result.agent_trace] == [
        "strategy_selected",
        "entities_extracted",
        "relationships_extracted",
        "measurements_extracted",
    ]
    assert len(provider.messages) == 3
    assert "entity extractor" in provider.messages[0][0]["content"]
    assert "relationship extractor" in provider.messages[1][0]["content"]
    assert "measurement extractor" in provider.messages[2][0]["content"]
    assert result.entities[0].name == "CuCrZr"
    assert len(result.relationships) == 1
    assert result.relationships[0].source == "CuCrZr"
    observation = result.experiments[0].observations[0]
    assert observation.value == 58.0
    assert observation.unit == "%IACS"
    assert observation.comparator == ">="
    assert observation.fragment == "CuCrZr reached >=58 %IACS"
    assert observation.row_reference == "row-7"


def test_extraction_strategy_handles_empty_simple_numeric_and_long_documents() -> None:
    assert select_extraction_strategy("empty", "   ") == "empty"
    assert (
        select_extraction_strategy("note", "CuCrZr and IN718 overview")
        == "entity_first"
    )
    assert (
        select_extraction_strategy("results", "Hardness reached 36 HRC after anneal")
        == "phased"
    )
    assert select_extraction_strategy("long", "CuCrZr " * 3000) == "chunked_phased"


def test_ingest_documents_writes_llm_extracted_graph_data_with_evidence() -> None:
    provider = _QueuedJSONProvider(
        [
            {
                "entities": [
                    {"kind": "material", "name": "CuCrZr"},
                    {"kind": "mode", "name": "Aging"},
                    {"kind": "property", "name": "Electrical Conductivity"},
                ]
            },
            {
                "relationships": [
                    {
                        "source": "CuCrZr",
                        "target": "Aging",
                        "type": "uses_mode",
                    }
                ]
            },
            {
                "experiments": [
                    {
                        "experiment_id": "doc-exp-1",
                        "title": "Document extracted aging trial",
                        "material_name": "CuCrZr",
                        "mode_name": "Aging",
                        "observations": [
                            {
                                "property_name": "Electrical Conductivity",
                                "value": 58.0,
                                "unit": "%IACS",
                                "fragment": "CuCrZr reached 58 %IACS",
                                "confidence": 0.9,
                            }
                        ],
                    }
                ]
            },
        ]
    )
    service = MaterialsKGService(
        InMemoryMaterialsKGRepository(),
        llm_provider=provider,
    )

    result = service.ingest_documents(
        [
            DocumentInput(
                document_id="doc-llm",
                title="LLM extracted CuCrZr report",
                text="CuCrZr after Aging measured Electrical Conductivity of 58 %IACS.",
                source_ref="doc-llm.txt",
            )
        ]
    )

    assert result["llm_extracted_experiments"] == 1
    material_mode = service.query_material_mode(
        "CuCrZr",
        "Aging",
        "Electrical Conductivity",
    )
    assert material_mode.observations
    assert material_mode.observations[0].value == 58.0
    related = service.query_related("CuCrZr", relation_filters=[RelationType.USES_MODE])
    assert related.relations
    assert related.relations[0].evidence_ids
    relation_evidence = service.repository.list_evidence(related.relations[0].evidence_ids)
    assert relation_evidence
    assert relation_evidence[0].metadata["source_file"] == "doc-llm.txt"
