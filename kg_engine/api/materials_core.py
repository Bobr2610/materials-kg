"""Thin REST API for the graph-first materials KG core."""

from __future__ import annotations

import csv
import io
import json
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Query
from fastapi import UploadFile
from fastapi.responses import HTMLResponse
from fastapi.responses import Response
from pydantic import BaseModel
from pydantic import Field

from kg_engine.domain.models import DocumentInput
from kg_engine.domain.models import ExperimentInput
from kg_engine.domain.models import HypothesisInput
from kg_engine.domain.models import PropertyFilters
from kg_engine.domain.models import QueryFilters
from kg_engine.domain.models import ReferenceDataBatch
from kg_engine.domain.models import RelationType
from kg_engine.ingestion.adapters import DocumentCorpusAdapter
from kg_engine.ingestion.adapters import ExperimentCatalogAdapter
from kg_engine.ingestion.adapters import ReferenceDataAdapter
from kg_engine.repositories.factory import create_materials_repository
from kg_engine.services.materials_kg import MaterialsKGService
from kg_engine.services.metrics import ContextBenchmark
from kg_engine.services.metrics import CoverageAxis
from kg_engine.services.metrics import ExpertFeedbackEntry
from kg_engine.services.metrics import ExpertFeedbackStore
from kg_engine.services.metrics import ExtractionBenchmark
from kg_engine.services.metrics import RunMetricsInput
from kg_engine.services.metrics import automatic_expert_correlation
from kg_engine.services.metrics import build_repository_coverage_heatmap
from kg_engine.services.metrics import compare_hypothesis_runs
from kg_engine.services.metrics import evaluate_context_metrics
from kg_engine.services.metrics import evaluate_extraction_benchmark
from kg_engine.services.metrics import evaluate_hypothesis_metrics
from kg_engine.services.metrics import recalibrate_ranking_weights

if TYPE_CHECKING:
    from kg_engine.config.settings import Settings

_TEXT_SUFFIXES = {".txt", ".md"}
_STRUCTURED_SUFFIXES = {".json", ".jsonl", ".csv", ".tsv"}
_SAMPLE_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_SOURCES_QUERY = Query(default=None)
_REFERENCE_KEYS = {
    "entities",
    "materials",
    "equipment",
    "properties",
    "modes",
    "teams",
    "documents",
    "tags",
    "coverage_rules",
}
_EXPERIMENT_KEYS = {
    "experiment_id",
    "material_name",
    "mode_name",
    "observations",
}
_DOCUMENT_KEYS = {"document_id", "text", "content", "body"}


def _parse_uploaded_file(name: str, content: bytes) -> object | None:
    suffix = Path(name).suffix.lower()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")
    if suffix == ".json":
        return json.loads(text)
    if suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    if suffix in {".csv", ".tsv"}:
        delimiter = "\t" if suffix == ".tsv" else ","
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        return [dict(row) for row in reader]
    if suffix in _TEXT_SUFFIXES:
        title = Path(name).stem
        if suffix == ".md":
            for line in text.splitlines():
                if line.startswith("# "):
                    title = line[2:].strip() or title
                    break
        return [
            {
                "document_id": name,
                "title": title,
                "text": text,
                "metadata": {"source_file": name},
            }
        ]
    return None


def _mark_uploaded_from(payload: object, name: str) -> None:
    if isinstance(payload, dict):
        payload["_uploaded_from"] = name
        metadata = payload.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata.setdefault("source_file", name)
    elif isinstance(payload, list):
        for item in payload:
            _mark_uploaded_from(item, name)


def _looks_like_reference_record(item: dict) -> bool:
    return bool(item.get("kind") or item.get("entity_kind"))


def _looks_like_experiment_record(item: dict) -> bool:
    return bool(
        (item.get("experiment_id") or item.get("id"))
        and item.get("material_name")
        and item.get("observations")
    )


def _looks_like_document_record(item: dict) -> bool:
    return bool(any(item.get(key) for key in _DOCUMENT_KEYS))


def _looks_canonical(parsed: object) -> bool:
    if isinstance(parsed, dict):
        if any(key in parsed for key in _REFERENCE_KEYS | {"experiments"}):
            return True
        return (
            _looks_like_reference_record(parsed)
            or _looks_like_experiment_record(parsed)
            or _looks_like_document_record(parsed)
        )
    if isinstance(parsed, list):
        dict_items = [item for item in parsed if isinstance(item, dict)]
        if not dict_items:
            return False
        return all(
            _looks_like_reference_record(item)
            or _looks_like_experiment_record(item)
            or _looks_like_document_record(item)
            for item in dict_items
        )
    return False


def _append_llm_structured_payload(
    *,
    structured: dict,
    name: str,
    ref_payload: dict,
    exp_payload: list,
    doc_payload: list,
) -> bool:
    added = False
    reference = structured.get("reference")
    if isinstance(reference, dict):
        for key in _REFERENCE_KEYS:
            values = reference.get(key)
            if isinstance(values, list) and values:
                for item in values:
                    _mark_uploaded_from(item, name)
                ref_payload.setdefault(key, []).extend(values)
                added = True
    experiments = structured.get("experiments")
    if isinstance(experiments, list) and experiments:
        for item in experiments:
            _mark_uploaded_from(item, name)
        exp_payload.extend(experiments)
        added = True
    documents = structured.get("documents")
    if isinstance(documents, list) and documents:
        for item in documents:
            _mark_uploaded_from(item, name)
        doc_payload.extend(documents)
        added = True
    return added


def _append_as_searchable_documents(
    *,
    parsed: object,
    name: str,
    doc_payload: list,
) -> None:
    items = parsed if isinstance(parsed, list) else [parsed]
    for item_index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        doc_payload.append(
            {
                "document_id": f"{name}#row-{item_index}",
                "title": f"{Path(name).stem} #row-{item_index}",
                "text": json.dumps(item, ensure_ascii=False, default=str),
                "source_ref": name,
                "metadata": {"source_file": name},
            }
        )


class MaterialModeRequest(BaseModel):
    material: str = Field(min_length=1)
    mode: str | None = Field(default=None)
    property_name: str | None = Field(default=None)


class PropertyQueryRequest(BaseModel):
    property_name: str = Field(min_length=1)
    filters: PropertyFilters = Field(default_factory=PropertyFilters)


class RelatedQueryRequest(BaseModel):
    entity: str = Field(min_length=1)
    depth: int = Field(default=2, ge=1, le=5)
    relation_filters: list[str] = Field(default_factory=list)


class DecisionHistoryRequest(BaseModel):
    entity_or_experiment: str = Field(min_length=1)


class DataGapQueryRequest(BaseModel):
    scope: str | None = Field(default=None)
    filters: QueryFilters = Field(default_factory=QueryFilters)


class AnswerQueryRequest(BaseModel):
    question: str = Field(default="", max_length=4000)
    material: str | None = Field(default=None)
    mode: str | None = Field(default=None)
    property_name: str | None = Field(default=None)
    source_ids: list[str] | None = Field(default=None)
    session_id: str | None = Field(default=None)


class MetricsCoverageRequest(BaseModel):
    axes: CoverageAxis | None = Field(default=None)


class MetricsHypothesesRequest(BaseModel):
    run: RunMetricsInput


class MetricsRunComparisonRequest(BaseModel):
    left: RunMetricsInput
    right: RunMetricsInput


_UI_PAGE = Path(__file__).resolve().parents[2] / "ui-page.html"
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _notebook_dashboard_html() -> str:
    return _UI_PAGE.read_text(encoding="utf-8")


def _create_llm_provider(settings: Settings | None = None):
    """Create LLM provider if API key is configured, else None."""
    try:
        from kg_engine.llm_core.provider import create_provider_from_env
        from kg_engine.llm_core.provider import create_provider_from_settings

        if settings is not None:
            return create_provider_from_settings(settings)
        return create_provider_from_env()
    except Exception:
        return None


def _create_session_store():
    """Create session store with TTL from settings."""
    try:
        from kg_engine.services.session import SessionStore
        from kg_engine.config.settings import settings

        return SessionStore(
            ttl_seconds=settings.session_ttl_seconds,
            max_messages=settings.session_max_messages,
        )
    except Exception:
        return None


def create_materials_app(
    *,
    settings: Settings | None = None,
    service: MaterialsKGService | None = None,
    ensure_schema: bool = False,
    title: str | None = None,
) -> FastAPI:
    """Create a standalone FastAPI app for the materials KG core."""
    api_title = title
    if settings is None:
        if service is None:
            from kg_engine.config.settings import settings as app_settings

            runtime_settings = app_settings
            if api_title is None:
                api_title = runtime_settings.materials_api_title
        else:
            runtime_settings = None
            if api_title is None:
                api_title = "Materials KG Core API"
    else:
        runtime_settings = settings
        if api_title is None:
            api_title = runtime_settings.materials_api_title
    runtime_service = service or MaterialsKGService(
        create_materials_repository(runtime_settings, ensure_schema=ensure_schema),
        llm_provider=_create_llm_provider(runtime_settings),
        session_store=_create_session_store(),
    )
    app = FastAPI(title=api_title)
    _source_files: list[dict] = []
    feedback_store = ExpertFeedbackStore(
        _PROJECT_ROOT / ".scratch" / "metrics" / "expert_feedback.jsonl"
    )

    @app.get("/", response_class=HTMLResponse)
    def dashboard() -> Response:
        html = _notebook_dashboard_html()
        return Response(
            content=html,
            media_type="text/html",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "materials-kg-core"}

    @app.get("/state")
    def get_state() -> dict:
        overview = runtime_service.get_source_overview()
        return {
            "source_files": list(_source_files),
            "overview": overview,
            "suggested_questions": runtime_service.get_suggested_questions(),
        }

    @app.get("/graph/data")
    def graph_data(sources: list[str] | None = _SOURCES_QUERY) -> dict:
        if sources is not None:
            active_sources = sources
        elif _source_files:
            active_sources = [
                item["name"] for item in _source_files if item.get("name")
            ]
        else:
            active_sources = []
        return runtime_service.get_graph_data(active_sources)

    @app.post("/ingest/upload")
    async def ingest_upload(files: list[UploadFile]) -> dict:
        ref_payload: dict = {}
        exp_payload: list = []
        doc_payload: list = []
        uploaded: list[dict] = []
        ingestion_status = {
            "llm_provider_enabled": runtime_service.llm_provider is not None,
            "llm_structured_files": [],
            "searchable_fallback_files": [],
            "fallback_reasons": {},
            "text_document_files": [],
        }
        for upload in files:
            name = upload.filename or "unnamed"
            content = await upload.read()
            parsed = _parse_uploaded_file(name, content)
            suffix = Path(name).suffix.lower()
            uploaded.append(
                {
                    "name": name,
                    "size": len(content),
                    "type": suffix.lstrip(".") or "unknown",
                }
            )
            if parsed is None:
                ingestion_status["searchable_fallback_files"].append(name)
                ingestion_status["fallback_reasons"][name] = "unsupported_or_binary_file"
                doc_payload.append(
                    {
                        "document_id": name,
                        "title": Path(name).stem,
                        "text": content.decode("utf-8", errors="replace"),
                        "metadata": {"source_file": name},
                    }
                )
                continue
            if suffix in _TEXT_SUFFIXES:
                ingestion_status["text_document_files"].append(name)
                items = parsed if isinstance(parsed, list) else [parsed]
                for item in items:
                    if isinstance(item, dict):
                        _mark_uploaded_from(item, name)
                if isinstance(parsed, list):
                    doc_payload.extend(items)
                else:
                    doc_payload.append(parsed)
                continue
            if suffix in _STRUCTURED_SUFFIXES:
                structured_added = False
                if runtime_service.llm_provider:
                    try:
                        from kg_engine.llm_core.extraction import (
                            structure_upload_with_llm,
                        )

                        structured = structure_upload_with_llm(
                            runtime_service.llm_provider,
                            name,
                            suffix.lstrip(".") or "structured",
                            parsed,
                        )
                        structured_added = _append_llm_structured_payload(
                            structured=structured,
                            name=name,
                            ref_payload=ref_payload,
                            exp_payload=exp_payload,
                            doc_payload=doc_payload,
                        )
                    except Exception:
                        structured_added = False
                if structured_added:
                    ingestion_status["llm_structured_files"].append(name)
                else:
                    ingestion_status["searchable_fallback_files"].append(name)
                    ingestion_status["fallback_reasons"][name] = (
                        "llm_unavailable_or_empty_payload"
                        if runtime_service.llm_provider
                        else "llm_provider_disabled"
                    )
                    _append_as_searchable_documents(
                        parsed=parsed,
                        name=name,
                        doc_payload=doc_payload,
                    )
                continue
            if isinstance(parsed, dict):
                for key in (
                    "entities",
                    "materials",
                    "equipment",
                    "properties",
                    "modes",
                    "teams",
                    "documents",
                    "tags",
                    "coverage_rules",
                ):
                    if key in parsed and isinstance(parsed[key], list):
                        for item in parsed[key]:
                            _mark_uploaded_from(item, name)
                        ref_payload.setdefault(key, []).extend(parsed[key])
                if "experiments" in parsed and isinstance(parsed["experiments"], list):
                    for item in parsed["experiments"]:
                        _mark_uploaded_from(item, name)
                    exp_payload.extend(parsed["experiments"])
                if "documents" in parsed and isinstance(parsed["documents"], list):
                    for item in parsed["documents"]:
                        _mark_uploaded_from(item, name)
                    doc_payload.extend(parsed["documents"])
                if not any(
                    k in parsed
                    for k in ("entities", "materials", "experiments", "documents")
                ):
                    if (
                        parsed.get("kind")
                        or parsed.get("entity_kind")
                        or parsed.get("type")
                    ):
                        _mark_uploaded_from(parsed, name)
                        ref_payload.setdefault("entities", []).append(parsed)
                    else:
                        doc_payload.append(
                            {
                                "document_id": name,
                                "title": Path(name).stem,
                                "text": json.dumps(parsed, ensure_ascii=False),
                                "metadata": {"source_file": name},
                            }
                        )
            elif isinstance(parsed, list):
                for item_index, item in enumerate(parsed):
                    if not isinstance(item, dict):
                        continue
                    if item.get("kind") or item.get("entity_kind") or item.get("type"):
                        _mark_uploaded_from(item, name)
                        ref_payload.setdefault("entities", []).append(item)
                    elif (item.get("experiment_id") or item.get("id")) and (
                        item.get("material_name") or item.get("material")
                    ):
                        _mark_uploaded_from(item, name)
                        exp_payload.append(item)
                    elif (
                        item.get("document_id")
                        or item.get("text")
                        or item.get("content")
                    ):
                        doc_payload.append(item)
                    else:
                        doc_payload.append(
                            {
                                "document_id": f"{name}#row-{item_index}",
                                "title": f"{Path(name).stem} #row-{item_index}",
                                "text": json.dumps(item, ensure_ascii=False),
                                "metadata": {"source_file": name},
                            }
                        )
        results = {}
        if ref_payload:
            results["reference"] = runtime_service.ingest_reference_data(
                ReferenceDataAdapter().from_payload(ref_payload)
            )
        if exp_payload:
            results["experiments"] = runtime_service.ingest_experiments(
                ExperimentCatalogAdapter().from_payload(exp_payload)
            )
        if doc_payload:
            results["documents"] = runtime_service.ingest_documents(
                DocumentCorpusAdapter().from_payload(doc_payload)
            )
        results["ingestion"] = ingestion_status
        results["uploaded"] = uploaded
        results["overview"] = runtime_service.get_source_overview()
        results["suggested_questions"] = runtime_service.get_suggested_questions()
        _source_files.extend(uploaded)
        return results

    @app.post("/demo/load-sample")
    def load_sample_data() -> dict:
        reference_path = _SAMPLE_DATA_DIR / "reference.json"
        experiments_path = _SAMPLE_DATA_DIR / "experiments.json"
        documents_path = _SAMPLE_DATA_DIR / "documents.json"
        with reference_path.open("r", encoding="utf-8") as file:
            reference_payload = json.load(file)
        with experiments_path.open("r", encoding="utf-8") as file:
            experiments_payload = json.load(file)
        with documents_path.open("r", encoding="utf-8") as file:
            documents_payload = json.load(file)

        for section_key in (
            "entities",
            "materials",
            "equipment",
            "properties",
            "modes",
            "teams",
            "documents",
            "tags",
            "coverage_rules",
        ):
            for item in reference_payload.get(section_key, []):
                item.setdefault("source_ref", reference_path.name)
        exp_items = (
            experiments_payload.get("experiments", [])
            if isinstance(experiments_payload, dict)
            else experiments_payload
        )
        for item in exp_items:
            if isinstance(item, dict):
                item.setdefault("source_ref", experiments_path.name)
        doc_items = (
            documents_payload.get("documents", [])
            if isinstance(documents_payload, dict)
            else documents_payload
        )
        for item in doc_items:
            if isinstance(item, dict):
                item.setdefault("source_ref", documents_path.name)

        results = {
            "reference": runtime_service.ingest_reference_data(
                ReferenceDataAdapter().from_payload(reference_payload)
            ),
            "experiments": runtime_service.ingest_experiments(
                ExperimentCatalogAdapter().from_payload(experiments_payload)
            ),
            "documents": runtime_service.ingest_documents(
                DocumentCorpusAdapter().from_payload(documents_payload)
            ),
            "uploaded": [
                {
                    "name": reference_path.name,
                    "size": reference_path.stat().st_size,
                    "type": "json",
                },
                {
                    "name": experiments_path.name,
                    "size": experiments_path.stat().st_size,
                    "type": "json",
                },
                {
                    "name": documents_path.name,
                    "size": documents_path.stat().st_size,
                    "type": "json",
                },
            ],
        }
        results["overview"] = runtime_service.get_source_overview()
        results["suggested_questions"] = runtime_service.get_suggested_questions()
        _source_files.extend(results["uploaded"])
        return results

    @app.post("/ingest/reference")
    def ingest_reference(batch: ReferenceDataBatch) -> dict[str, int]:
        return runtime_service.ingest_reference_data(batch)

    @app.post("/ingest/experiments")
    def ingest_experiments(batch: list[ExperimentInput]) -> dict[str, int]:
        return runtime_service.ingest_experiments(batch)

    @app.post("/ingest/documents")
    def ingest_documents(batch: list[DocumentInput]) -> dict[str, int]:
        return runtime_service.ingest_documents(batch)

    @app.post("/query/answer")
    def query_answer(request: AnswerQueryRequest) -> dict:
        return runtime_service.answer_question(
            question=request.question,
            material=request.material,
            mode=request.mode,
            property_name=request.property_name,
            source_ids=request.source_ids,
            session_id=request.session_id,
        )

    @app.post("/query/answer/stream")
    async def query_answer_stream(request: AnswerQueryRequest):
        from fastapi.responses import StreamingResponse

        async def generate():
            async for chunk in runtime_service.answer_question_stream(
                question=request.question,
                material=request.material,
                mode=request.mode,
                property_name=request.property_name,
                source_ids=request.source_ids,
                session_id=request.session_id,
            ):
                yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")

    @app.post("/hypotheses/generate")
    def generate_hypotheses(request: HypothesisInput) -> dict:
        from kg_engine.config.settings import settings as app_settings

        effective_settings = runtime_settings or app_settings
        engine = effective_settings.materials_hypothesis_engine.strip().lower()
        if engine == "deterministic":
            return runtime_service.generate_hypotheses(request).model_dump(mode="json")
        if engine != "deepagents":
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported hypothesis engine: {engine}",
            )
        try:
            from kg_engine.agents import DeepAgentsConfigurationError
            from kg_engine.agents import DeepAgentsResultError
            from kg_engine.agents import generate_hypotheses_with_deep_agent

            result = generate_hypotheses_with_deep_agent(
                runtime_service,
                request,
                runtime_settings=effective_settings,
            )
        except DeepAgentsConfigurationError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except DeepAgentsResultError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return result.model_dump(mode="json")

    @app.post("/metrics/extraction")
    def metrics_extraction(request: ExtractionBenchmark) -> dict:
        return evaluate_extraction_benchmark(request).model_dump(mode="json")

    @app.post("/metrics/context")
    def metrics_context(request: ContextBenchmark) -> dict:
        return evaluate_context_metrics(request).model_dump(mode="json")

    @app.post("/metrics/coverage")
    def metrics_coverage(request: MetricsCoverageRequest | None = None) -> dict:
        axes = request.axes if request is not None else None
        return build_repository_coverage_heatmap(
            runtime_service.repository,
            axes=axes,
        ).model_dump(mode="json")

    @app.post("/metrics/hypotheses")
    def metrics_hypotheses(request: MetricsHypothesesRequest) -> dict:
        return evaluate_hypothesis_metrics(
            hypotheses=request.run.result.hypotheses,
            context=request.run.context,
            coverage=request.run.coverage,
        ).model_dump(mode="json")

    @app.post("/metrics/runs/compare")
    def metrics_runs_compare(request: MetricsRunComparisonRequest) -> dict:
        return compare_hypothesis_runs(request.left, request.right).model_dump(
            mode="json"
        )

    @app.post("/metrics/feedback")
    def metrics_feedback(entry: ExpertFeedbackEntry) -> dict:
        feedback_store.save(entry)
        entries = feedback_store.load()
        return {
            "saved": 1,
            "sample_size": len(entries),
            "invalid_feedback_lines": feedback_store.invalid_line_count,
            "weights": recalibrate_ranking_weights(entries).model_dump(mode="json"),
            "correlation": automatic_expert_correlation(entries),
        }

    @app.get("/metrics/feedback/weights")
    def metrics_feedback_weights() -> dict:
        entries = feedback_store.load()
        return {
            "sample_size": len(entries),
            "invalid_feedback_lines": feedback_store.invalid_line_count,
            "weights": recalibrate_ranking_weights(entries).model_dump(mode="json"),
        }

    @app.get("/metrics/feedback/correlation")
    def metrics_feedback_correlation() -> dict:
        entries = feedback_store.load()
        return {
            "sample_size": len(entries),
            "invalid_feedback_lines": feedback_store.invalid_line_count,
            "correlation": automatic_expert_correlation(entries),
        }

    @app.get("/source/overview")
    def source_overview() -> dict:
        overview = runtime_service.get_source_overview()
        overview["uploaded_files"] = list(_source_files)
        return overview

    @app.get("/source/suggestions")
    def source_suggestions() -> list[str]:
        return runtime_service.get_suggested_questions()

    @app.post("/query/material-mode")
    def query_material_mode(request: MaterialModeRequest) -> dict:
        return runtime_service.query_material_mode(
            request.material,
            request.mode,
            request.property_name,
        ).model_dump(mode="json")

    @app.post("/query/property")
    def query_property(request: PropertyQueryRequest) -> dict:
        return runtime_service.query_property(
            request.property_name,
            request.filters,
        ).model_dump(mode="json")

    @app.post("/query/related")
    def query_related(request: RelatedQueryRequest) -> dict:
        relation_filters = (
            [RelationType(item) for item in request.relation_filters]
            if request.relation_filters
            else None
        )
        return runtime_service.query_related(
            request.entity,
            request.depth,
            relation_filters=relation_filters,
        ).model_dump(mode="json")

    @app.post("/query/decision-history")
    def query_decision_history(request: DecisionHistoryRequest) -> dict:
        return runtime_service.query_decision_history(
            request.entity_or_experiment
        ).model_dump(mode="json")

    @app.post("/query/data-gaps")
    def query_data_gaps(request: DataGapQueryRequest) -> list[dict]:
        return [
            gap.model_dump(mode="json")
            for gap in runtime_service.query_data_gaps(request.scope, request.filters)
        ]

    @app.get("/sources")
    def list_sources() -> list[dict]:
        return list(_source_files)

    @app.delete("/sources/{source_name}")
    def delete_source(source_name: str) -> dict:
        if not getattr(runtime_settings, "materials_enable_destructive_api", False):
            return Response(
                content='{"error": "Destructive API disabled. Set MATERIALS_ENABLE_DESTRUCTIVE_API=true."}',
                status_code=403,
                media_type="application/json",
            )
        removed = runtime_service._repository.delete_source(source_name)  # noqa: SLF001
        _source_files[:] = [s for s in _source_files if s.get("name") != source_name]
        return {
            "deleted": source_name,
            "removed_records": removed,
            "overview": runtime_service.get_source_overview(),
        }

    @app.delete("/sources")
    def clear_all_sources() -> dict:
        if not getattr(runtime_settings, "materials_enable_destructive_api", False):
            return Response(
                content='{"error": "Destructive API disabled. Set MATERIALS_ENABLE_DESTRUCTIVE_API=true."}',
                status_code=403,
                media_type="application/json",
            )
        runtime_service._repository.clear_all()  # noqa: SLF001
        _source_files.clear()
        return {
            "cleared": True,
            "overview": runtime_service.get_source_overview(),
            "suggested_questions": runtime_service.get_suggested_questions(),
        }

    return app
