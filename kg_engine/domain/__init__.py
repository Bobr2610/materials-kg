"""Domain contracts for the graph-first materials knowledge graph core."""

from kg_engine.domain.models import CanonicalEntityInput
from kg_engine.domain.models import CoverageRuleInput
from kg_engine.domain.models import DataGap
from kg_engine.domain.models import DecisionHistoryQueryResult
from kg_engine.domain.models import DecisionTrace
from kg_engine.domain.models import DocumentExtractionResult
from kg_engine.domain.models import DocumentInput
from kg_engine.domain.models import Entity
from kg_engine.domain.models import Evidence
from kg_engine.domain.models import EvidencePath
from kg_engine.domain.models import ExperimentInput
from kg_engine.domain.models import ExtractedEntity
from kg_engine.domain.models import ExtractedExperiment
from kg_engine.domain.models import ExtractedRelationship
from kg_engine.domain.models import FindingInput
from kg_engine.domain.models import MaterialModeQueryResult
from kg_engine.domain.models import Observation
from kg_engine.domain.models import ObservationInput
from kg_engine.domain.models import PropertyFilters
from kg_engine.domain.models import PropertyQueryResult
from kg_engine.domain.models import QueryFilters
from kg_engine.domain.models import ReferenceDataBatch
from kg_engine.domain.models import RelatedEntitiesQueryResult
from kg_engine.domain.models import Relation
from kg_engine.domain.models import SearchTextUnit
from kg_engine.domain.models import SourceKind
from kg_engine.domain.models import SourceSpan
from kg_engine.domain.models import TextUnitInput
from kg_engine.domain.resolution import ReferenceResolver
from kg_engine.domain.resolution import normalize_name

__all__ = [
    "CanonicalEntityInput",
    "CoverageRuleInput",
    "DataGap",
    "DecisionHistoryQueryResult",
    "DecisionTrace",
    "DocumentExtractionResult",
    "DocumentInput",
    "Entity",
    "Evidence",
    "EvidencePath",
    "ExperimentInput",
    "ExtractedEntity",
    "ExtractedExperiment",
    "ExtractedRelationship",
    "FindingInput",
    "MaterialModeQueryResult",
    "Observation",
    "ObservationInput",
    "PropertyFilters",
    "PropertyQueryResult",
    "QueryFilters",
    "ReferenceDataBatch",
    "ReferenceResolver",
    "RelatedEntitiesQueryResult",
    "Relation",
    "SearchTextUnit",
    "SourceKind",
    "SourceSpan",
    "TextUnitInput",
    "normalize_name",
]
