from __future__ import annotations

from kg_engine.domain.models import CanonicalEntityInput
from kg_engine.domain.models import CoverageRuleInput
from kg_engine.domain.models import DocumentInput
from kg_engine.domain.models import EntityKind
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


def build_service() -> MaterialsKGService:
    repository = InMemoryMaterialsKGRepository()
    return MaterialsKGService(repository)


def test_reference_resolution_handles_aliases_and_noisy_names() -> None:
    service = build_service()
    service.ingest_reference_data(
        ReferenceDataBatch(
            entities=[
                CanonicalEntityInput(
                    kind=EntityKind.MATERIAL,
                    name="Ti-6Al-4V",
                    aliases=["Ti6Al4V", "ti 6al 4v"],
                ),
                CanonicalEntityInput(
                    kind=EntityKind.MODE,
                    name="Annealing",
                    aliases=["anneal", "annealing"],
                ),
                CanonicalEntityInput(
                    kind=EntityKind.PROPERTY,
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
                CanonicalEntityInput(kind=EntityKind.MATERIAL, name="IN718"),
                CanonicalEntityInput(kind=EntityKind.MODE, name="Aging"),
                CanonicalEntityInput(
                    kind=EntityKind.PROPERTY,
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
                CanonicalEntityInput(kind=EntityKind.MATERIAL, name="Ti-6Al-4V"),
                CanonicalEntityInput(kind=EntityKind.MODE, name="Annealing"),
                CanonicalEntityInput(kind=EntityKind.PROPERTY, name="Hardness"),
                CanonicalEntityInput(
                    kind=EntityKind.PROPERTY,
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
                CanonicalEntityInput(kind=EntityKind.MATERIAL, name="Al6061"),
                CanonicalEntityInput(kind=EntityKind.MODE, name="Solution treatment"),
                CanonicalEntityInput(
                    kind=EntityKind.PROPERTY,
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
    assert any(path.entity_ids[-1] != path.entity_ids[0] for path in related.evidence_paths)
    assert len(history.traces) == 1


def test_incremental_reingestion_does_not_duplicate_canonical_entities() -> None:
    service = build_service()
    service.ingest_reference_data(
        ReferenceDataBatch(
            entities=[CanonicalEntityInput(kind=EntityKind.MATERIAL, name="WC-Co")]
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


def test_hypothesis_factory_generates_ranked_graph_grounded_candidates() -> None:
    service = build_service()
    service.ingest_reference_data(
        ReferenceDataBatch(
            entities=[
                CanonicalEntityInput(kind=EntityKind.MATERIAL, name="CuCrZr"),
                CanonicalEntityInput(kind=EntityKind.MODE, name="Solution Treated"),
                CanonicalEntityInput(kind=EntityKind.MODE, name="Aged"),
                CanonicalEntityInput(
                    kind=EntityKind.PROPERTY,
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
    assert result.hypotheses[0].score.final_score >= result.hypotheses[-1].score.final_score
    assert any(item.data_gap_ids for item in result.hypotheses)
    assert any(item.supporting_observation_ids for item in result.hypotheses)
    assert result.evidence
    assert result.data_gaps


class TestSourceGrounding:
    """Verify that answer_question returns source-backed data, not fabricated content."""

    def _build_service_with_data(self) -> MaterialsKGService:
        service = build_service()
        service.ingest_reference_data(
            ReferenceDataBatch(
                entities=[
                    CanonicalEntityInput(kind=EntityKind.MATERIAL, name="Ti-6Al-4V"),
                    CanonicalEntityInput(kind=EntityKind.MODE, name="Annealing"),
                    CanonicalEntityInput(
                        kind=EntityKind.PROPERTY,
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
            "не найден" in w or "не удалось" in w.lower() or "не сопоставить" in w.lower()
            for w in result["warnings"]
        ), f"Warning should indicate entity not found, got: {result['warnings']}"

    def test_answer_includes_source_fragments(self) -> None:
        service = self._build_service_with_data()
        result = service.answer_question(
            question="Hardness Ti-6Al-4V Annealing"
        )

        evidence = result.get("evidence", [])
        assert evidence, "Evidence list should not be empty for matched query"

        ev = evidence[0]
        assert "source_id" in ev, "Evidence must track source_id"
        assert "span" in ev, "Evidence must have span with fragment"
        span = ev["span"]
        assert span.get("fragment"), "Evidence span must contain a text fragment"

    def test_search_hits_are_included_for_text_match(self) -> None:
        service = self._build_service_with_data()
        result = service.answer_question(
            question="hardness annealing Ti-6Al-4V"
        )

        search_hits = result.get("search_hits", [])
        assert search_hits, "Text search should find relevant units"

        hit = search_hits[0]
        assert "source_entity_id" in hit, "Search hit must reference source entity"
        assert "content" in hit, "Search hit must include content fragment"
