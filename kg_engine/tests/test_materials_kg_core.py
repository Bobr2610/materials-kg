from __future__ import annotations

import asyncio
from typing import Any

import pytest

from kg_engine.config.settings import settings
from kg_engine.domain.models import CanonicalEntityInput
from kg_engine.domain.models import CoverageRuleInput
from kg_engine.domain.models import DocumentInput
from kg_engine.domain.models import ExperimentInput
from kg_engine.domain.models import FindingInput
from kg_engine.domain.models import HypothesisInput
from kg_engine.domain.models import ObservationInput
from kg_engine.domain.models import PropertyFilters
from kg_engine.domain.models import QueryFilters
from kg_engine.domain.models import ReferenceDataBatch
from kg_engine.domain.models import TextUnitInput
from kg_engine.repositories.memory import InMemoryMaterialsKGRepository
from kg_engine.services.materials_kg import MaterialsKGService
from kg_engine.services.materials_kg import _document_extraction_batches


def build_service() -> MaterialsKGService:
    repository = InMemoryMaterialsKGRepository()
    return MaterialsKGService(repository)


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


def test_graph_data_matches_relative_filter_to_absolute_source_path() -> None:
    service = build_service()
    service.ingest_reference_data(
        ReferenceDataBatch(
            entities=[
                CanonicalEntityInput(
                    kind="document",
                    name="Регламент 1.png",
                    canonical_id="doc_abs",
                    source_ref="/app/Задача 1/Регламенты/Регламент 1.png",
                    properties={
                        "source_file": "/app/Задача 1/Регламенты/Регламент 1.png",
                    },
                ),
            ],
        )
    )

    graph = service.get_graph_data(["Регламенты/Регламент 1.png"])

    assert [node["id"] for node in graph["nodes"]] == ["doc_abs"]


def test_graph_data_without_source_filter_returns_all_entities() -> None:
    service = build_service()
    service.ingest_reference_data(
        ReferenceDataBatch(
            entities=[
                CanonicalEntityInput(
                    kind="material",
                    name="CuCrZr",
                    canonical_id="mat_cucrzr",
                ),
                CanonicalEntityInput(
                    kind="property",
                    name="Conductivity",
                    canonical_id="prop_conductivity",
                ),
            ],
        )
    )

    graph = service.get_graph_data([])

    assert {node["id"] for node in graph["nodes"]} == {
        "mat_cucrzr",
        "prop_conductivity",
    }


def test_reference_resolution_handles_aliases_and_noisy_names() -> None:
    service = build_service()
    service.ingest_reference_data(
        ReferenceDataBatch(
            entities=[
                CanonicalEntityInput(
                    kind="material",
                    name="Ti-6Al-4V",
                    aliases=["Ti6Al4V", "ti 6al 4v"],
                ),
                CanonicalEntityInput(
                    kind="mode",
                    name="Annealing",
                    aliases=["anneal", "annealing"],
                ),
                CanonicalEntityInput(
                    kind="property",
                    name="Hardness",
                    aliases=["hardness", "твердость"],
                ),
            ]
        )
    )
    service.ingest_experiments(
        [
            ExperimentInput(
                experiment_id="exp-001",
                title="Anneal trial",
                material_name="ti 6al 4v",
                mode_name="anneal",
                observations=[
                    ObservationInput(
                        property_name="твердость",
                        value=36.0,
                        unit="HRC",
                    )
                ],
            )
        ]
    )

    result = service.query_material_mode("Ti6Al4V", "Annealing")

    assert result.material.canonical_name == "Ti-6Al-4V"
    assert result.mode is not None
    assert result.mode.canonical_name == "Annealing"
    assert len(result.observations) == 1


def test_relation_and_observation_preserve_provenance_and_units() -> None:
    service = build_service()
    service.ingest_reference_data(
        ReferenceDataBatch(
            entities=[
                CanonicalEntityInput(kind="material", name="IN718"),
                CanonicalEntityInput(kind="mode", name="Aging"),
                CanonicalEntityInput(
                    kind="property",
                    name="Yield strength",
                    aliases=["yield_strength"],
                ),
            ]
        )
    )
    service.ingest_experiments(
        [
            ExperimentInput(
                experiment_id="exp-718",
                title="IN718 aging trial",
                material_name="IN718",
                mode_name="Aging",
                observations=[
                    ObservationInput(
                        property_name="yield_strength",
                        value=1080.0,
                        unit="MPa",
                        fragment="Yield strength reached 1080 MPa",
                        row_reference="sheet1!B12",
                    )
                ],
            )
        ]
    )

    result = service.query_property(
        "Yield strength",
        PropertyFilters(min_value=1000.0),
    )

    assert len(result.observations) == 1
    observation = result.observations[0]
    assert observation.unit == "MPa"
    evidence = result.evidence[0]
    assert evidence.span.row_reference == "sheet1!B12"
    assert evidence.span.fragment == "Yield strength reached 1080 MPa"


def test_gap_analysis_uses_coverage_rules_instead_of_cartesian_noise() -> None:
    service = build_service()
    service.ingest_reference_data(
        ReferenceDataBatch(
            entities=[
                CanonicalEntityInput(kind="material", name="Ti-6Al-4V"),
                CanonicalEntityInput(kind="mode", name="Annealing"),
                CanonicalEntityInput(kind="property", name="Hardness"),
                CanonicalEntityInput(
                    kind="property",
                    name="Tensile strength",
                ),
            ],
            coverage_rules=[
                CoverageRuleInput(
                    rule_id="rule-1",
                    name="Ti-6Al-4V annealing matrix",
                    material_names=["Ti-6Al-4V"],
                    mode_names=["Annealing"],
                    property_names=["Hardness", "Tensile strength"],
                )
            ],
        )
    )
    service.ingest_experiments(
        [
            ExperimentInput(
                experiment_id="exp-gap",
                title="Anneal matrix partial",
                material_name="Ti-6Al-4V",
                mode_name="Annealing",
                observations=[
                    ObservationInput(
                        property_name="Hardness",
                        value=35.0,
                        unit="HRC",
                    )
                ],
            )
        ]
    )

    gaps = service.query_data_gaps(filters=QueryFilters(material_name="Ti-6Al-4V"))

    assert len(gaps) == 1
    assert "Tensile strength" in gaps[0].reason


def test_material_mode_query_returns_experiments_findings_and_evidence_paths() -> None:
    service = build_service()
    service.ingest_reference_data(
        ReferenceDataBatch(
            entities=[
                CanonicalEntityInput(kind="material", name="Al6061"),
                CanonicalEntityInput(kind="mode", name="Solution treatment"),
                CanonicalEntityInput(
                    kind="property",
                    name="Tensile strength",
                ),
            ]
        )
    )
    service.ingest_experiments(
        [
            ExperimentInput(
                experiment_id="exp-mm",
                title="Al6061 solution treatment run",
                material_name="Al6061",
                mode_name="Solution treatment",
                observations=[
                    ObservationInput(
                        property_name="Tensile strength",
                        value=310.0,
                        unit="MPa",
                        fragment="Measured tensile strength 310 MPa",
                    )
                ],
                findings=[
                    FindingInput(
                        summary="Strength improved after solution treatment",
                        decision="Continue with follow-up aging study",
                        observation_indices=[0],
                    )
                ],
                text_units=[
                    {"content": "Al6061 solution treatment increased tensile strength."}
                ],
            )
        ]
    )

    result = service.query_material_mode(
        "Al6061",
        "Solution treatment",
        "Tensile strength",
    )
    related = service.query_related("Al6061", depth=2)
    history = service.query_decision_history("exp-mm")

    assert len(result.experiments) == 1
    assert len(result.findings) == 1
    assert len(result.evidence) == 2
    assert result.search_hits
    assert any(
        path.entity_ids[-1] != path.entity_ids[0] for path in related.evidence_paths
    )
    assert len(history.traces) == 1


def test_incremental_reingestion_does_not_duplicate_canonical_entities() -> None:
    service = build_service()
    service.ingest_reference_data(
        ReferenceDataBatch(
            entities=[CanonicalEntityInput(kind="material", name="WC-Co")]
        )
    )
    batch = [
        ExperimentInput(
            experiment_id="exp-dup",
            title="WC-Co baseline",
            material_name="WC-Co",
            observations=[
                ObservationInput(property_name="Hardness", value=1450.0, unit="HV")
            ],
        )
    ]
    service.ingest_experiments(batch)
    service.ingest_experiments(batch)

    property_result = service.query_property("Hardness")
    related = service.query_related("WC-Co", depth=1)

    assert len(property_result.materials) == 1
    assert len(related.related_entities) >= 1


def test_query_related_accepts_canonical_entity_id() -> None:
    service = build_service()
    service.ingest_reference_data(
        ReferenceDataBatch(
            entities=[
                CanonicalEntityInput(
                    kind="material",
                    name="CuCrZr",
                    canonical_id="mat-cucrzr",
                )
            ]
        )
    )
    service.ingest_experiments(
        [
            ExperimentInput(
                experiment_id="exp-cucrzr-aged",
                title="CuCrZr aged baseline",
                material_name="CuCrZr",
                mode_name="Aged",
                observations=[
                    ObservationInput(
                        property_name="Electrical Conductivity",
                        value=58.0,
                        unit="%IACS",
                    )
                ],
            )
        ]
    )

    related = service.query_related("mat-cucrzr", depth=1)

    assert related.root_entity.id == "mat-cucrzr"
    assert related.related_entities
    assert related.relations


def test_hypothesis_factory_generates_ranked_graph_grounded_candidates() -> None:
    service = build_service()
    service.ingest_reference_data(
        ReferenceDataBatch(
            entities=[
                CanonicalEntityInput(kind="material", name="CuCrZr"),
                CanonicalEntityInput(kind="mode", name="Solution Treated"),
                CanonicalEntityInput(kind="mode", name="Aged"),
                CanonicalEntityInput(
                    kind="property",
                    name="Electrical Conductivity",
                ),
            ],
            coverage_rules=[
                CoverageRuleInput(
                    rule_id="cu-gap",
                    name="CuCrZr conductivity coverage",
                    material_names=["CuCrZr"],
                    mode_names=["Solution Treated", "Aged"],
                    property_names=["Electrical Conductivity"],
                )
            ],
        )
    )
    service.ingest_experiments(
        [
            ExperimentInput(
                experiment_id="exp-cu",
                title="CuCrZr solution treatment",
                material_name="CuCrZr",
                mode_name="Solution Treated",
                observations=[
                    ObservationInput(
                        property_name="Electrical Conductivity",
                        value=58.0,
                        unit="%IACS",
                        row_reference="row-1",
                    )
                ],
            )
        ]
    )

    result = service.generate_hypotheses(
        HypothesisInput(
            target_kpi="Electrical Conductivity",
            material="CuCrZr",
            max_hypotheses=5,
        )
    )

    assert result.hypotheses
    assert (
        result.hypotheses[0].score.final_score
        >= result.hypotheses[-1].score.final_score
    )
    assert any(item.data_gap_ids for item in result.hypotheses)
    assert any(item.supporting_observation_ids for item in result.hypotheses)
    assert result.evidence
    assert result.data_gaps
    assert result.knowledge_base_summary["observations"] == 1
    assert result.ranking_rubric["weights"]["value"] == 0.35
    assert [item.rank for item in result.hypotheses] == list(
        range(1, len(result.hypotheses) + 1)
    )


def test_hypothesis_factory_uses_literature_when_observations_are_missing() -> None:
    service = build_service()
    service.ingest_documents(
        [
            DocumentInput(
                document_id="lit-001",
                title="Additive manufacturing porosity report",
                text=(
                    "Laser power modulation and hatch spacing were discussed as "
                    "possible levers for reducing porosity in nickel alloy builds."
                ),
                property_names=["Porosity"],
                material_names=["Nickel alloy"],
                text_units=[
                    TextUnitInput(
                        content=(
                            "Lower porosity may be achieved by testing laser power "
                            "modulation together with hatch spacing changes."
                        )
                    )
                ],
            )
        ]
    )

    result = service.generate_hypotheses(
        HypothesisInput(target_kpi="Porosity", max_hypotheses=3)
    )

    assert result.hypotheses
    assert result.search_hits
    assert result.knowledge_base_summary["text_hits"] > 0
    assert result.hypotheses[0].hypothesis_type == "literature_signal"
    assert result.hypotheses[0].supporting_text_unit_ids
    assert result.hypotheses[0].test_plan
    assert result.hypotheses[0].score.final_score > 0


def test_each_document_ingest_creates_document_entity_text_unit_and_relation() -> None:
    service = build_service()

    result = service.ingest_documents(
        [
            DocumentInput(
                document_id="task1-doc",
                title="Task 1 source",
                text="Файл сохранен как источник: Регламенты/source.png.",
                source_ref="Регламенты/source.png",
            )
        ]
    )

    document = service.repository.get_entity("task1-doc")
    relations = service.repository.list_relations(entity_id="task1-doc")
    text_units = service.repository.list_text_units()

    assert result["documents"] == 1
    assert document is not None
    assert document.kind == "document"
    assert text_units
    assert text_units[0].source_entity_id == "task1-doc"
    assert any(
        relation.source_entity_id == "task1-doc"
        and relation.relation_type == "tagged_with"
        for relation in relations
    )


def test_document_extraction_batches_cover_all_text_units_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "materials_llm_extraction_batch_chars", 420)
    monkeypatch.setattr(settings, "materials_llm_extraction_max_batches_per_document", 0)

    document = DocumentInput(
        document_id="large-doc",
        title="Large textbook",
        text="full document text",
        text_units=[
            TextUnitInput(
                content=f"semantic unit {idx} " + ("tail context " * 12),
                metadata={"page": idx, "block_id": f"b{idx}"},
            )
            for idx in range(1, 8)
        ],
    )

    batches = _document_extraction_batches(document, max_chars=25_000)
    metadata = batches[-1][2]

    assert len(batches) > 1
    assert metadata["processed_text_units"] == 7
    assert metadata["omitted_text_units"] == 0
    assert metadata["llm_extraction_truncated"] is False
    assert all(batch[2]["coverage_scope"] == "full_document" for batch in batches)


def test_document_extraction_batches_report_explicit_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "materials_llm_extraction_batch_chars", 420)
    monkeypatch.setattr(settings, "materials_llm_extraction_max_batches_per_document", 2)

    document = DocumentInput(
        document_id="capped-doc",
        title="Capped textbook",
        text="full document text",
        text_units=[
            TextUnitInput(
                content=f"semantic unit {idx} " + ("context " * 90),
                metadata={"page": idx},
            )
            for idx in range(1, 8)
        ],
    )

    batches = _document_extraction_batches(document, max_chars=25_000)
    metadata = batches[-1][2]

    assert len(batches) == 2
    assert metadata["processed_text_units"] < metadata["total_text_units"]
    assert metadata["omitted_text_units"] > 0
    assert metadata["llm_extraction_truncated"] is True


def test_document_extraction_batches_cover_raw_text_without_storing_full_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "materials_llm_extraction_batch_chars", 1_000)
    monkeypatch.setattr(settings, "materials_llm_extraction_max_batches_per_document", 0)
    monkeypatch.setattr(settings, "materials_llm_extraction_chunk_overlap", 100)

    document = DocumentInput(
        document_id="raw-doc",
        title="Raw textbook",
        text="A" * 2_700,
    )

    batches = _document_extraction_batches(document, max_chars=25_000)

    assert len(batches) == 3
    assert batches[0][2]["source_char_start"] == 0
    assert batches[-1][2]["source_char_end"] == 2_700
    assert batches[-1][2]["omitted_chars"] == 0
    assert batches[-1][2]["llm_extraction_truncated"] is False


def test_ingest_documents_extracts_graph_facts_from_tail_text_unit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "materials_llm_extraction_batch_chars", 1_000)
    monkeypatch.setattr(settings, "materials_llm_extraction_max_batches_per_document", 0)

    provider = _QueuedJSONProvider(
        [
            {"entities": [{"kind": "material", "name": "HeadMaterial"}]},
            {"relationships": []},
            {"experiments": []},
            {
                "entities": [
                    {"kind": "material", "name": "TailMaterial"},
                    {"kind": "process", "name": "TailProcess"},
                ]
            },
            {
                "relationships": [
                    {
                        "source": "TailMaterial",
                        "target": "TailProcess",
                        "type": "uses_process",
                    }
                ]
            },
            {"experiments": []},
            {"experiments": []},
        ]
    )
    service = MaterialsKGService(
        InMemoryMaterialsKGRepository(),
        llm_provider=provider,  # type: ignore[arg-type]
    )

    result = service.ingest_documents(
        [
            DocumentInput(
                document_id="tail-doc",
                title="Tail coverage report",
                text="head context\n\ntail context",
                source_ref="tail-doc.pdf",
                text_units=[
                    TextUnitInput(
                        content=(
                            "HeadMaterial appears in the first page. "
                            + ("introductory context " * 42)
                        ),
                        metadata={"page": 1, "block_id": "head"},
                    ),
                    TextUnitInput(
                        content=(
                            "TailMaterial uses TailProcess in the final page. "
                            "This is the relation that used to be missed. "
                            + ("tail source context " * 42)
                        ),
                        metadata={"page": 200, "block_id": "tail"},
                    ),
                ],
            )
        ]
    )

    related = service.query_related("TailMaterial", relation_filters=["uses_process"])

    assert result["llm_extraction_errors"] == []
    assert len(provider.messages) == 6
    assert "final page" in provider.messages[3][1]["content"]
    assert related.relations
    evidence = service.repository.list_evidence(related.relations[0].evidence_ids)
    assert evidence[0].metadata["extraction_batch"]["page_end"] == 200
    assert evidence[0].metadata["source_pages"] == [200]
    assert evidence[0].metadata["page_end"] == 200
    assert evidence[0].metadata["source_file"] == "tail-doc.pdf"


class TestSourceGrounding:
    """Verify that answer_question returns source-backed data, not fabricated content."""

    def _build_service_with_data(self) -> MaterialsKGService:
        service = build_service()
        service.ingest_reference_data(
            ReferenceDataBatch(
                entities=[
                    CanonicalEntityInput(kind="material", name="Ti-6Al-4V"),
                    CanonicalEntityInput(kind="mode", name="Annealing"),
                    CanonicalEntityInput(
                        kind="property",
                        name="Hardness",
                        aliases=["hardness", "твердость"],
                    ),
                ]
            )
        )
        service.ingest_experiments(
            [
                ExperimentInput(
                    experiment_id="exp-ground-001",
                    title="Ti6Al4V hardness after anneal",
                    material_name="Ti-6Al-4V",
                    mode_name="Annealing",
                    observations=[
                        ObservationInput(
                            property_name="Hardness",
                            value=36.0,
                            unit="HRC",
                            fragment="Ti-6Al-4V hardness 36 HRC after annealing",
                            row_reference="sheet1!A1",
                        )
                    ],
                    findings=[
                        FindingInput(
                            summary="Annealing reduces hardness to 36 HRC",
                            confidence=0.9,
                        )
                    ],
                    text_units=[
                        TextUnitInput(
                            content="Ti-6Al-4V alloy annealed at 700C shows hardness 36 HRC",
                            metadata={"section": "results"},
                        )
                    ],
                )
            ]
        )
        return service

    def test_answer_contains_citations_from_loaded_sources(self) -> None:
        service = self._build_service_with_data()
        result = service.answer_question(
            question="What is the hardness of Ti-6Al-4V after Annealing?"
        )

        assert result["answer"], "Answer should not be empty"
        assert result["citations"], "Answer must include citations from loaded sources"
        assert result["experiments"], "Answer must reference matched experiments"
        assert result["observations"], "Answer must include observation data"

        citation = result["citations"][0]
        assert "source_id" in citation, "Citation must have source_id"
        assert "source_kind" in citation, "Citation must have source_kind"

    def test_answer_does_not_fabricate_unloaded_entities(self) -> None:
        service = self._build_service_with_data()
        result = service.answer_question(
            question="What is the tensile strength of Inconel 718?"
        )

        assert result["warnings"], "Should warn when no entities match"
        assert any(
            "не найден" in w
            or "не удалось" in w.lower()
            or "не сопоставить" in w.lower()
            for w in result["warnings"]
        ), f"Warning should indicate entity not found, got: {result['warnings']}"

    def test_answer_includes_source_fragments(self) -> None:
        service = self._build_service_with_data()
        result = service.answer_question(question="Hardness Ti-6Al-4V Annealing")

        evidence = result.get("evidence", [])
        assert evidence, "Evidence list should not be empty for matched query"

        ev = evidence[0]
        assert "source_id" in ev, "Evidence must track source_id"
        assert "span" in ev, "Evidence must have span with fragment"
        span = ev["span"]
        assert span.get("fragment"), "Evidence span must contain a text fragment"

    def test_search_hits_are_included_for_text_match(self) -> None:
        service = self._build_service_with_data()
        result = service.answer_question(question="hardness annealing Ti-6Al-4V")

        search_hits = result.get("search_hits", [])
        assert search_hits, "Text search should find relevant units"

        hit = search_hits[0]
        assert "source_entity_id" in hit, "Search hit must reference source entity"
        assert "content" in hit, "Search hit must include content fragment"

    def test_russian_text_search_matches_preserved_source_names(self) -> None:
        service = build_service()
        service.ingest_documents(
            [
                DocumentInput(
                    document_id="doc-russian",
                    title="Хвосты и флотация",
                    text="Файл сохранен как источник: Пример 1\\Хвосты КГМК.xlsx.",
                    source_ref="Пример 1\\Хвосты КГМК.xlsx",
                )
            ]
        )

        hits = service.search_evidence_units("хвосты флотация", limit=5)

        assert hits
        assert "Хвосты" in hits[0].content

    def test_raw_document_fallback_is_compacted_before_storage(self) -> None:
        service = build_service()
        noise = "\n".join(
            f"background paragraph {idx} without useful values"
            for idx in range(120)
        )
        important = "CuCrZr aging at 480 C reached conductivity 82 %IACS."
        raw_text = f"{noise}\n{important}\n{noise}"
        service.ingest_documents(
            [
                DocumentInput(
                    document_id="doc-raw",
                    title="Raw fallback document",
                    text=raw_text,
                )
            ]
        )

        units = service.repository.list_text_units()

        assert len(units) == 1
        assert len(units[0].content) < len(raw_text)
        assert len(units[0].content) <= 1400
        assert important in units[0].content
        assert units[0].metadata["semantic_unit"] is True
        assert units[0].metadata["source_text_chars"] == len(raw_text)
        assert units[0].metadata["stored_text_chars"] == len(units[0].content)


class TestSourceIdsIsolation:
    """Verify that source_ids filters all returned structures by source file."""

    def _build_two_source_service(self) -> MaterialsKGService:
        service = build_service()
        service.ingest_reference_data(
            ReferenceDataBatch(
                entities=[
                    CanonicalEntityInput(kind="material", name="Material-A"),
                    CanonicalEntityInput(kind="property", name="KPI-A"),
                    CanonicalEntityInput(kind="mode", name="Mode-A"),
                    CanonicalEntityInput(kind="material", name="Material-B"),
                    CanonicalEntityInput(kind="property", name="KPI-B"),
                    CanonicalEntityInput(kind="mode", name="Mode-B"),
                ],
                coverage_rules=[
                    CoverageRuleInput(
                        rule_id="rule-a",
                        name="Material-A coverage",
                        material_names=["Material-A"],
                        mode_names=["Mode-A"],
                        property_names=["KPI-A", "KPI-B"],
                    ),
                    CoverageRuleInput(
                        rule_id="rule-b",
                        name="Material-B coverage",
                        material_names=["Material-B"],
                        mode_names=["Mode-B"],
                        property_names=["KPI-A", "KPI-B"],
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
                    observations=[
                        ObservationInput(
                            property_name="KPI-A",
                            value=100.0,
                            unit="MPa",
                            fragment="Material-A KPI-A = 100 MPa",
                        )
                    ],
                    findings=[
                        FindingInput(summary="Material-A result", confidence=0.9)
                    ],
                    text_units=[
                        TextUnitInput(content="Material-A experiment result for KPI-A")
                    ],
                ),
                ExperimentInput(
                    experiment_id="exp-b",
                    title="Experiment B",
                    material_name="Material-B",
                    mode_name="Mode-B",
                    source_ref="file-b.json",
                    observations=[
                        ObservationInput(
                            property_name="KPI-B",
                            value=200.0,
                            unit="MPa",
                            fragment="Material-B KPI-B = 200 MPa",
                        )
                    ],
                    findings=[
                        FindingInput(summary="Material-B result", confidence=0.9)
                    ],
                    text_units=[
                        TextUnitInput(content="Material-B experiment result for KPI-B")
                    ],
                ),
            ]
        )
        return service

    def test_answer_source_ids_filters_all_structures(self) -> None:
        service = self._build_two_source_service()
        result_a = service.answer_question(
            question="Material KPI values",
            source_ids=["file-a.json"],
        )

        assert all(
            "file-a.json" in e.get("metadata", {}).get("source_file", "")
            or e["source_id"] == "file-a.json"
            for e in result_a["evidence"]
        )
        assert all(
            "file-b.json" not in e.get("metadata", {}).get("source_file", "")
            for e in result_a["evidence"]
        )
        assert not any(
            "Material-B" in e.get("canonical_name", "")
            for e in result_a["matched_entities"]
        )
        assert all(
            "file-b.json" not in h.get("metadata", {}).get("source_file", "")
            for h in result_a["search_hits"]
        )

    def test_answer_empty_source_ids_returns_nothing(self) -> None:
        service = self._build_two_source_service()
        result = service.answer_question(
            question="Material KPI values",
            source_ids=[],
        )
        assert result["evidence"] == []
        assert result["observations"] == []
        assert result["experiments"] == []
        assert result["relations"] == []
        assert result["matched_entities"] == []
        assert result["resolved_query"] == {
            "material": None,
            "mode": None,
            "property_name": None,
        }

    def test_answer_source_ids_excludes_explicit_foreign_entity(self) -> None:
        service = self._build_two_source_service()
        result = service.answer_question(
            question="Material-B KPI-B",
            material="Material-B",
            source_ids=["file-a.json"],
        )

        assert result["matched_entities"] == []
        assert result["resolved_query"]["material"] is None
        assert result["evidence"] == []
        assert result["observations"] == []
        assert result["experiments"] == []
        assert not any("Material-B" in hit["content"] for hit in result["search_hits"])

    def test_stream_source_ids_excludes_foreign_graph_context(self) -> None:
        class CaptureLLM:
            def __init__(self) -> None:
                self.messages: list[dict[str, str]] = []

            async def chat_stream(
                self,
                messages: list[dict[str, str]],
                *,
                temperature: float,
                max_tokens: int,
            ):
                _ = (temperature, max_tokens)
                self.messages = messages
                yield "ok"

        llm = CaptureLLM()
        service = self._build_two_source_service()
        service._llm = llm  # noqa: SLF001

        async def collect() -> list[str]:
            chunks: list[str] = []
            async for chunk in service.answer_question_stream(
                question="Material-B KPI-B",
                material="Material-B",
                source_ids=["file-a.json"],
            ):
                chunks.append(chunk)
            return chunks

        assert asyncio.run(collect()) == ["ok"]
        graph_prompt = "\n".join(msg["content"] for msg in llm.messages)
        assert "Experiment B" not in graph_prompt
        assert "Material-B KPI-B = 200 MPa" not in graph_prompt

    def test_stream_uses_full_answer_context_for_property_questions(self) -> None:
        class CaptureLLM:
            def __init__(self) -> None:
                self.messages: list[dict[str, str]] = []

            async def chat_stream(
                self,
                messages: list[dict[str, str]],
                *,
                temperature: float,
                max_tokens: int,
            ):
                _ = (temperature, max_tokens)
                self.messages = messages
                yield "ok"

        llm = CaptureLLM()
        service = self._build_two_source_service()
        service._llm = llm  # noqa: SLF001

        async def collect() -> list[str]:
            chunks: list[str] = []
            async for chunk in service.answer_question_stream(
                question="Какие результаты есть по KPI-A?",
                property_name="KPI-A",
                source_ids=["file-a.json"],
            ):
                chunks.append(chunk)
            return chunks

        assert asyncio.run(collect()) == ["ok"]
        assert llm.messages[0]["role"] == "system"
        graph_prompt = "\n".join(msg["content"] for msg in llm.messages)
        assert "Graph retrieval packet" in graph_prompt
        assert '"observations"' in graph_prompt
        assert "Material-A KPI-A = 100 MPa" in graph_prompt
        assert '"entity_lookup"' in graph_prompt
        assert "Недостаточно данных" in graph_prompt

    def test_hypotheses_source_ids_filters(self) -> None:
        service = self._build_two_source_service()
        result_a = service.generate_hypotheses(
            HypothesisInput(
                target_kpi="KPI-A",
                material="Material-A",
                source_ids=["file-a.json"],
            )
        )
        all_supporting = set()
        for hyp in result_a.hypotheses:
            all_supporting.update(hyp.supporting_entity_ids)
            all_supporting.update(hyp.supporting_evidence_ids)
            all_supporting.update(hyp.supporting_observation_ids)
        material_b_entity = service._repository.resolve_entity(  # noqa: SLF001
            "material", "Material-B"
        )
        if material_b_entity:
            assert material_b_entity.id not in all_supporting
        for obs in result_a.observations:
            if obs.experiment_id:
                exp_entity = service._repository.get_entity(obs.experiment_id)  # noqa: SLF001
                if exp_entity:
                    assert exp_entity.canonical_name != "Material-B"

    def test_source_overview_shows_files_not_ids(self) -> None:
        service = self._build_two_source_service()
        overview = service.get_source_overview()
        source_files = overview["source_files"]
        assert "file-a.json" in source_files
        assert "file-b.json" in source_files
        assert "exp-a" not in source_files
        assert "exp-b" not in source_files

    def test_hypothesis_no_literal_placeholders(self) -> None:
        service = self._build_two_source_service()
        result = service.generate_hypotheses(
            HypothesisInput(
                target_kpi="KPI-A",
                material="Material-A",
            )
        )
        for hyp in result.hypotheses:
            for field_value in [
                hyp.statement,
                hyp.rationale,
                hyp.test_plan,
                hyp.novelty_rationale,
                hyp.value_rationale,
                *hyp.falsification_criteria,
                *hyp.required_evidence,
            ]:
                assert "{prop_name}" not in field_value, (
                    f"Literal placeholder {{prop_name}} found in {field_value!r}"
                )
                assert "{mat_name}" not in field_value, (
                    f"Literal placeholder {{mat_name}} found in {field_value!r}"
                )
                assert "{mode_name}" not in field_value, (
                    f"Literal placeholder {{mode_name}} found in {field_value!r}"
                )


class TestExpertAdjustments:
    """Verify expert adjustments properly recalculate final_score."""

    def test_value_adjustment_changes_final_score(self) -> None:
        service = build_service()
        service.ingest_reference_data(
            ReferenceDataBatch(
                entities=[
                    CanonicalEntityInput(kind="material", name="TestMat"),
                    CanonicalEntityInput(kind="mode", name="TestMode"),
                    CanonicalEntityInput(kind="property", name="TestKPI"),
                ],
                coverage_rules=[
                    CoverageRuleInput(
                        rule_id="test-rule",
                        name="Test coverage",
                        material_names=["TestMat"],
                        mode_names=["TestMode"],
                        property_names=["TestKPI"],
                    )
                ],
            )
        )
        service.ingest_experiments(
            [
                ExperimentInput(
                    experiment_id="exp-test",
                    title="Test experiment",
                    material_name="TestMat",
                    mode_name="TestMode",
                    observations=[
                        ObservationInput(
                            property_name="TestKPI",
                            value=50.0,
                            unit="MPa",
                        )
                    ],
                )
            ]
        )
        result_before = service.generate_hypotheses(
            HypothesisInput(target_kpi="TestKPI", material="TestMat", max_hypotheses=1)
        )
        hyp_id = result_before.hypotheses[0].id
        old_score = result_before.hypotheses[0].score.final_score

        result_after = service.generate_hypotheses(
            HypothesisInput(
                target_kpi="TestKPI",
                material="TestMat",
                max_hypotheses=1,
                expert_adjustments={hyp_id: {"value_adjustment": 0.5}},
            )
        )
        new_score = result_after.hypotheses[0].score.final_score
        assert new_score > old_score, (
            f"value_adjustment should increase final_score: {old_score} -> {new_score}"
        )

    def test_risk_adjustment_changes_final_score(self) -> None:
        service = build_service()
        service.ingest_reference_data(
            ReferenceDataBatch(
                entities=[
                    CanonicalEntityInput(kind="material", name="TestMat"),
                    CanonicalEntityInput(kind="mode", name="TestMode"),
                    CanonicalEntityInput(kind="property", name="TestKPI"),
                ],
                coverage_rules=[
                    CoverageRuleInput(
                        rule_id="test-rule",
                        name="Test coverage",
                        material_names=["TestMat"],
                        mode_names=["TestMode"],
                        property_names=["TestKPI"],
                    )
                ],
            )
        )
        service.ingest_experiments(
            [
                ExperimentInput(
                    experiment_id="exp-test",
                    title="Test experiment",
                    material_name="TestMat",
                    mode_name="TestMode",
                    observations=[
                        ObservationInput(
                            property_name="TestKPI",
                            value=50.0,
                            unit="MPa",
                        )
                    ],
                )
            ]
        )
        result_before = service.generate_hypotheses(
            HypothesisInput(target_kpi="TestKPI", material="TestMat", max_hypotheses=1)
        )
        hyp_id = result_before.hypotheses[0].id
        old_score = result_before.hypotheses[0].score.final_score

        result_after = service.generate_hypotheses(
            HypothesisInput(
                target_kpi="TestKPI",
                material="TestMat",
                max_hypotheses=1,
                expert_adjustments={hyp_id: {"risk_adjustment": -0.3}},
            )
        )
        new_score = result_after.hypotheses[0].score.final_score
        assert new_score > old_score, (
            f"risk_adjustment should change final_score: {old_score} -> {new_score}"
        )

    def test_reject_sets_final_score_zero(self) -> None:
        service = build_service()
        service.ingest_reference_data(
            ReferenceDataBatch(
                entities=[
                    CanonicalEntityInput(kind="material", name="TestMat"),
                    CanonicalEntityInput(kind="mode", name="TestMode"),
                    CanonicalEntityInput(kind="property", name="TestKPI"),
                ],
            )
        )
        service.ingest_experiments(
            [
                ExperimentInput(
                    experiment_id="exp-test",
                    title="Test experiment",
                    material_name="TestMat",
                    mode_name="TestMode",
                    observations=[
                        ObservationInput(
                            property_name="TestKPI",
                            value=50.0,
                            unit="MPa",
                        )
                    ],
                )
            ]
        )
        result = service.generate_hypotheses(
            HypothesisInput(
                target_kpi="TestKPI",
                material="TestMat",
                max_hypotheses=10,
                expert_adjustments={
                    h.id: {"reject": True}
                    for h in service.generate_hypotheses(
                        HypothesisInput(target_kpi="TestKPI", material="TestMat")
                    ).hypotheses
                },
            )
        )
        for hyp in result.hypotheses:
            assert hyp.score.final_score == 0, (
                f"Rejected hypothesis should have final_score=0, got {hyp.score.final_score}"
            )
