from __future__ import annotations

from kg_engine.domain.models import CanonicalEntityInput
from kg_engine.domain.models import CoverageRuleInput
from kg_engine.domain.models import DocumentInput
from kg_engine.domain.models import EntityKind
from kg_engine.domain.models import ExperimentInput
from kg_engine.domain.models import FindingInput
from kg_engine.domain.models import ObservationInput
from kg_engine.domain.models import QueryFilters
from kg_engine.domain.models import ReferenceDataBatch
from kg_engine.domain.models import TextUnitInput
from kg_engine.ingestion.adapters import DocumentCorpusAdapter
from kg_engine.ingestion.adapters import ExperimentCatalogAdapter
from kg_engine.ingestion.adapters import ReferenceDataAdapter
from kg_engine.repositories.memory import InMemoryMaterialsKGRepository
from kg_engine.services.materials_kg import MaterialsKGService

REFERENCE_DATA = {
    "materials": [
        {"name": "TEST-MATERIAL-001", "aliases": ["TM-001", "TestMat1"]},
        {"name": "TEST-MATERIAL-002", "aliases": ["TM-002"]},
        {"name": "TEST-MATERIAL-003"},
    ],
    "properties": [
        {"name": "Tensile strength"},
        {"name": "Yield strength"},
        {"name": "Elongation"},
    ],
    "modes": [
        {"name": "Annealed"},
        {"name": "As-cast"},
    ],
    "equipment": [
        {"name": "TEST-UTM-001"},
        {"name": "TEST-SEM-001"},
    ],
    "coverage_rules": [
        {
            "rule_id": "rule_001",
            "name": "All materials need tensile in annealed",
            "material_names": ["TEST-MATERIAL-001", "TEST-MATERIAL-002"],
            "mode_names": ["Annealed"],
            "property_names": ["Tensile strength"],
            "scope": "material-mode-property",
        },
        {
            "rule_id": "rule_002",
            "name": "Material 001 needs elongation in as-cast",
            "material_names": ["TEST-MATERIAL-001"],
            "mode_names": ["As-cast"],
            "property_names": ["Elongation"],
            "scope": "material-mode-property",
        },
        {
            "rule_id": "rule_003",
            "name": "Material 001 needs yield in as-cast",
            "material_names": ["TEST-MATERIAL-001"],
            "mode_names": ["As-cast"],
            "property_names": ["Yield strength"],
            "scope": "material-mode-property",
        },
    ],
}

EXPERIMENTS_DATA = [
    {
        "experiment_id": "EXP-001",
        "title": "Tensile test of TEST-MATERIAL-001 Annealed",
        "material_name": "TEST-MATERIAL-001",
        "mode_name": "Annealed",
        "equipment_names": ["TEST-UTM-001"],
        "observations": [
            {
                "property_name": "Tensile strength",
                "value": 950.0,
                "unit": "MPa",
                "fragment": "Tensile strength measured at 950 MPa",
            },
            {
                "property_name": "Yield strength",
                "value": 880.0,
                "unit": "MPa",
            },
        ],
        "findings": [
            {
                "summary": "TEST-MATERIAL-001 shows good tensile properties in annealed state",
                "decision": "Approve for structural use",
                "observation_indices": [0, 1],
            }
        ],
        "text_units": [
            {
                "content": "TEST-MATERIAL-001 Annealed tensile strength 950 MPa yield 880 MPa elongation 12%"
            }
        ],
    },
    {
        "experiment_id": "EXP-002",
        "title": "Tensile test of TEST-MATERIAL-001 As-cast",
        "material_name": "TEST-MATERIAL-001",
        "mode_name": "As-cast",
        "equipment_names": ["TEST-UTM-001"],
        "observations": [
            {
                "property_name": "Tensile strength",
                "value": 870.0,
                "unit": "MPa",
            },
            {
                "property_name": "Elongation",
                "value": 8.5,
                "unit": "%",
            },
        ],
        "findings": [
            {
                "summary": "As-cast TEST-MATERIAL-001 has lower ductility",
            }
        ],
        "text_units": [
            {"content": "As-cast TEST-MATERIAL-001 elongation 8.5% tensile 870 MPa"}
        ],
    },
    {
        "experiment_id": "EXP-003",
        "title": "Characterization of TEST-MATERIAL-002 Annealed",
        "material_name": "TEST-MATERIAL-002",
        "mode_name": "Annealed",
        "observations": [
            {
                "property_name": "Tensile strength",
                "value": 720.0,
                "unit": "MPa",
            },
        ],
        "findings": [
            {
                "summary": "TEST-MATERIAL-002 has moderate tensile strength",
            }
        ],
    },
    {
        "experiment_id": "EXP-004",
        "title": "SEM analysis of TEST-MATERIAL-001",
        "material_name": "TEST-MATERIAL-001",
        "observations": [
            {
                "property_name": "Yield strength",
                "value": 900.0,
                "unit": "MPa",
            },
        ],
        "text_units": [
            {
                "content": "Microstructural SEM analysis of TEST-MATERIAL-001 confirmed grain size"
            }
        ],
    },
    {
        "experiment_id": "EXP-005",
        "title": "High-temperature test of TEST-MATERIAL-003",
        "material_name": "TEST-MATERIAL-003",
        "mode_name": "As-cast",
        "observations": [
            {
                "property_name": "Tensile strength",
                "value": 600.0,
                "unit": "MPa",
            },
        ],
    },
]

DOCUMENTS_DATA = [
    {
        "document_id": "DOC-001",
        "title": "TEST-MATERIAL-001 Review",
        "text": (
            "Comprehensive review of TEST-MATERIAL-001 mechanical properties. "
            "The material exhibits tensile strength of 950 MPa in annealed condition "
            "and 870 MPa in as-cast condition."
        ),
        "material_names": ["TEST-MATERIAL-001", "TEST-MATERIAL-002"],
        "property_names": ["Tensile strength"],
        "experiment_ids": ["EXP-001"],
    },
    {
        "document_id": "DOC-002",
        "title": "TEST-MATERIAL-003 Overview",
        "text": (
            "Overview of TEST-MATERIAL-003 properties and applications. "
            "Tensile strength ranges from 580-620 MPa."
        ),
        "material_names": ["TEST-MATERIAL-003"],
    },
]


def _build_test_graph() -> tuple[InMemoryMaterialsKGRepository, MaterialsKGService]:
    repository = InMemoryMaterialsKGRepository()
    service = MaterialsKGService(repository)

    service.ingest_reference_data(ReferenceDataAdapter().from_payload(REFERENCE_DATA))
    service.ingest_experiments(
        ExperimentCatalogAdapter().from_payload(EXPERIMENTS_DATA)
    )
    service.ingest_documents(DocumentCorpusAdapter().from_payload(DOCUMENTS_DATA))
    return repository, service


def test_graph_repository_is_populated_and_queryable_from_sample_data() -> None:
    repository, service = _build_test_graph()

    materials = repository.find_entities(kind=EntityKind.MATERIAL)
    experiments = repository.find_entities(kind=EntityKind.EXPERIMENT)
    documents = repository.find_entities(kind=EntityKind.DOCUMENT)
    test_mat = repository.resolve_entity(EntityKind.MATERIAL, "TEST-MATERIAL-001")

    assert len(materials) >= 3
    assert len(experiments) >= 5
    assert len(documents) >= 2
    assert test_mat is not None

    relations = repository.list_relations(entity_id=test_mat.id)
    observations = repository.list_observations(material_id=test_mat.id)
    traces = repository.list_decision_traces(entity_id=test_mat.id)
    text_hits = repository.search_text_units("TEST-MATERIAL-001 tensile strength")

    assert relations
    assert observations
    assert traces
    assert text_hits
    assert repository.list_coverage_rules()

    material_mode = service.query_material_mode(
        "TEST-MATERIAL-001",
        "Annealed",
        "Tensile strength",
    )
    related = service.query_related("TEST-MATERIAL-001", depth=2)
    history = service.query_decision_history("TEST-MATERIAL-001")
    gaps = service.query_data_gaps(
        filters=QueryFilters(material_name="TEST-MATERIAL-001")
    )

    assert material_mode.experiments
    assert material_mode.observations
    assert material_mode.evidence
    assert material_mode.search_hits
    assert related.related_entities
    assert related.evidence_paths
    assert history.traces
    assert gaps
