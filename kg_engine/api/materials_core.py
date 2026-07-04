"""Thin REST API for the graph-first materials KG core."""

from __future__ import annotations

import csv
import asyncio
import io
import json
import mimetypes
import tempfile
from datetime import datetime
from datetime import timezone
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING
from typing import Any
from urllib.parse import unquote
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import BackgroundTasks
from fastapi import FastAPI
from fastapi import Header
from fastapi import HTTPException
from fastapi import Query
from fastapi import UploadFile
from fastapi.responses import HTMLResponse
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pydantic import Field

from kg_engine.domain.models import DocumentInput
from kg_engine.domain.models import ExperimentInput
from kg_engine.domain.models import HypothesisGenerationResult
from kg_engine.domain.models import HypothesisInput
from kg_engine.domain.models import PropertyFilters
from kg_engine.domain.models import QueryFilters
from kg_engine.domain.models import ReferenceDataBatch
from kg_engine.domain.product import Constraint
from kg_engine.domain.product import ConstraintKind
from kg_engine.domain.product import ExperimentOutcome
from kg_engine.domain.product import HypothesisRun
from kg_engine.domain.product import ExpertReview
from kg_engine.domain.product import ResearchProjectCreate
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
from kg_engine.services.research_projects import ProjectNotFoundError
from kg_engine.services.research_projects import ResearchProjectService
from kg_engine.services.reports import render_hypothesis_report

if TYPE_CHECKING:
    from kg_engine.config.settings import Settings

_TEXT_SUFFIXES = {".txt", ".md"}
_STRUCTURED_SUFFIXES = {".json", ".jsonl", ".csv", ".tsv"}
_PARSER_SUFFIXES = {".docx", ".xlsx", ".xls", ".pdf", ".html", ".htm"}
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}
_MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB
_URL_DOWNLOAD_TIMEOUT_SECONDS = 30.0
_SAMPLE_DATA_DIR = Path(__file__).resolve().parents[2] / "kg_engine" / "tests" / "data"
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_TASK_MATERIALS_DIRS = (
    _PROJECT_ROOT / "Задача 1",
    _PROJECT_ROOT / "task-1",
    _PROJECT_ROOT / "task1",
    _PROJECT_ROOT / "task_1",
    _PROJECT_ROOT / "data" / "task1",
)
_TASK_MATERIALS_FALLBACK_DIRS = (_PROJECT_ROOT / "sample_sources",)
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


class UrlIngestRequest(BaseModel):
    """URL source requested for ingestion."""

    url: str = Field(min_length=1)
    filename: str | None = Field(default=None, max_length=240)
    max_bytes: int = Field(default=_MAX_UPLOAD_SIZE, gt=0, le=_MAX_UPLOAD_SIZE)


class _TemporaryProviderTimeout:
    """Temporarily tune the shared LLM provider for bounded bulk ingestion."""

    def __init__(self, provider: object | None, settings: Settings | None) -> None:
        self.provider = provider
        self.settings = settings
        self._old_timeout: object | None = None
        self._old_retries: object | None = None

    def __enter__(self):
        if self.provider is None or self.settings is None:
            return None
        timeout = getattr(self.settings, "materials_ingestion_llm_timeout_seconds", None)
        retries = getattr(self.settings, "materials_ingestion_llm_max_retries", None)
        if timeout is None and retries is None:
            return None
        self._old_timeout = getattr(self.provider, "timeout", None)
        self._old_retries = getattr(self.provider, "max_retries", None)
        if timeout is not None and hasattr(self.provider, "timeout"):
            self.provider.timeout = timeout
        if retries is not None and hasattr(self.provider, "max_retries"):
            self.provider.max_retries = retries
        return None

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.provider is None:
            return
        if self._old_timeout is not None and hasattr(self.provider, "timeout"):
            self.provider.timeout = self._old_timeout
        if self._old_retries is not None and hasattr(self.provider, "max_retries"):
            self.provider.max_retries = self._old_retries


def _parse_uploaded_file(name: str, content: bytes) -> object | None:
    suffix = Path(name).suffix.lower()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")
    if suffix == ".json":
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None
    if suffix == ".jsonl":
        lines = []
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                lines.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return lines
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


def _api_document_parser(
    settings: Settings | None = None,
    *,
    enable_vision: bool = False,
):
    """Create a DocumentBlockParser with auto-VLM for the API layer."""
    try:
        if settings is None:
            from kg_engine.config.settings import settings as app_settings

            settings = app_settings
        from kg_engine.ingestion.document_blocks import DocumentBlockParser
        from kg_engine.ingestion.document_blocks import DocumentParseSettings
        if not enable_vision:
            return DocumentBlockParser(
                settings=DocumentParseSettings(
                    enable_vision=False,
                    grobid_url=settings.materials_grobid_url,
                    grobid_timeout_seconds=settings.materials_grobid_timeout_seconds,
                    grobid_min_text_chars=settings.materials_grobid_min_text_chars,
                ),
            )
        from kg_engine.llm_core.provider import LLMProvider, resolve_chat_completions_config
        from kg_engine.llm_core.vision import VisionConductor

        conductor = None

        vision_provider_name = (settings.materials_vision_provider or "").strip().lower()
        vision_model = (settings.materials_vision_model or "").strip()
        vision_api_key = (settings.materials_vision_api_key or "").strip()
        vision_base_url = (settings.materials_vision_base_url or "").strip()

        vision_provider = None
        if vision_provider_name and vision_model:
            if not vision_api_key:
                vision_api_key = (settings.llm_api_key or "").strip()
            if not vision_base_url:
                vision_base_url = (settings.llm_base_url or "").strip()
            if vision_api_key or vision_base_url:
                vision_settings_proxy = type("VisionSettings", (), {
                    "default_llm_provider": vision_provider_name,
                    "default_model": vision_model,
                    "llm_api_key": vision_api_key,
                    "llm_base_url": vision_base_url,
                })()
                config = resolve_chat_completions_config(vision_settings_proxy)
                if config is not None:
                    vision_provider = LLMProvider(
                        base_url=config.base_url,
                        api_key=config.api_key,
                        chat_model=config.chat_model,
                        embedding_model=config.embedding_model,
                        timeout=getattr(
                            settings,
                            "materials_ingestion_llm_timeout_seconds",
                            getattr(settings, "llm_timeout_seconds", 60.0),
                        ),
                        max_retries=getattr(
                            settings,
                            "materials_ingestion_llm_max_retries",
                            getattr(settings, "llm_max_retries", 3),
                        ),
                    )

        if vision_provider is None:
            return None

        conductor = VisionConductor(vision_provider, model=vision_model)
        return DocumentBlockParser(
            vision_conductor=conductor,
            settings=DocumentParseSettings(
                enable_vision=True,
                grobid_url=settings.materials_grobid_url,
                grobid_timeout_seconds=settings.materials_grobid_timeout_seconds,
                grobid_min_text_chars=settings.materials_grobid_min_text_chars,
            ),
        )
    except Exception:
        return None


def _mark_uploaded_from(
    payload: object,
    name: str,
    *,
    source_ref: str | None = None,
) -> None:
    if isinstance(payload, dict):
        payload["_uploaded_from"] = name
        if source_ref:
            payload.setdefault("source_ref", source_ref)
        metadata = payload.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata.setdefault("source_file", name)
            if source_ref:
                metadata.setdefault("source_url", source_ref)
    elif isinstance(payload, list):
        for item in payload:
            _mark_uploaded_from(item, name, source_ref=source_ref)


def _looks_like_reference_record(item: dict) -> bool:
    return bool(item.get("kind") or item.get("entity_kind"))


def _looks_like_experiment_record(item: dict) -> bool:
    return bool(
        (item.get("experiment_id") or item.get("id"))
        and (item.get("material_name") or item.get("material") or item.get("alloy"))
        and (
            item.get("observations")
            or item.get("property_name")
            or item.get("property")
            or item.get("property_id")
        )
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
    source_ref: str | None = None,
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
                    _mark_uploaded_from(item, name, source_ref=source_ref)
                ref_payload.setdefault(key, []).extend(values)
                added = True
    experiments = structured.get("experiments")
    if isinstance(experiments, list) and experiments:
        for item in experiments:
            _mark_uploaded_from(item, name, source_ref=source_ref)
        exp_payload.extend(experiments)
        added = True
    documents = structured.get("documents")
    if isinstance(documents, list) and documents:
        for item in documents:
            _mark_uploaded_from(item, name, source_ref=source_ref)
        doc_payload.extend(documents)
        added = True
    return added


def _append_as_searchable_documents(
    *,
    parsed: object,
    name: str,
    doc_payload: list,
    source_ref: str | None = None,
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
                "source_ref": source_ref or name,
                "metadata": _metadata_for_source(name, source_ref),
            }
        )


def _append_parsed_payload_without_llm(
    *,
    parsed: object,
    name: str,
    suffix: str,
    ref_payload: dict,
    exp_payload: list,
    doc_payload: list,
    source_ref: str | None = None,
) -> None:
    if suffix in _TEXT_SUFFIXES:
        items = parsed if isinstance(parsed, list) else [parsed]
        for item in items:
            if isinstance(item, dict):
                _mark_uploaded_from(item, name, source_ref=source_ref)
                doc_payload.append(item)
        return
    if isinstance(parsed, dict):
        for key in _REFERENCE_KEYS:
            values = parsed.get(key)
            if isinstance(values, list):
                for item in values:
                    _mark_uploaded_from(item, name, source_ref=source_ref)
                ref_payload.setdefault(key, []).extend(values)
        experiments = parsed.get("experiments")
        if isinstance(experiments, list):
            for item in experiments:
                _mark_uploaded_from(item, name, source_ref=source_ref)
            exp_payload.extend(experiments)
        documents = parsed.get("documents")
        if isinstance(documents, list):
            for item in documents:
                _mark_uploaded_from(item, name, source_ref=source_ref)
            doc_payload.extend(documents)
        if not any(key in parsed for key in _REFERENCE_KEYS | {"experiments"}):
            if _looks_like_reference_record(parsed):
                _mark_uploaded_from(parsed, name, source_ref=source_ref)
                ref_payload.setdefault("entities", []).append(parsed)
            elif _looks_like_experiment_record(parsed):
                _mark_uploaded_from(parsed, name, source_ref=source_ref)
                exp_payload.append(parsed)
            elif _looks_like_document_record(parsed):
                _mark_uploaded_from(parsed, name, source_ref=source_ref)
                doc_payload.append(parsed)
            else:
                _append_as_searchable_documents(
                    parsed=parsed,
                    name=name,
                    doc_payload=doc_payload,
                    source_ref=source_ref,
                )
        return
    if isinstance(parsed, list):
        for item_index, item in enumerate(parsed):
            if not isinstance(item, dict):
                continue
            if _looks_like_reference_record(item):
                _mark_uploaded_from(item, name, source_ref=source_ref)
                ref_payload.setdefault("entities", []).append(item)
            elif _looks_like_experiment_record(item):
                _mark_uploaded_from(item, name, source_ref=source_ref)
                exp_payload.append(item)
            elif _looks_like_document_record(item):
                _mark_uploaded_from(item, name, source_ref=source_ref)
                doc_payload.append(item)
            else:
                doc_payload.append(
                    {
                        "document_id": f"{name}#row-{item_index}",
                        "title": f"{Path(name).stem} #row-{item_index}",
                        "text": json.dumps(item, ensure_ascii=False),
                        "source_ref": source_ref or name,
                        "metadata": _metadata_for_source(name, source_ref),
                    }
                )


def _metadata_for_source(name: str, source_ref: str | None = None) -> dict[str, str]:
    metadata = {"source_file": name}
    if source_ref:
        metadata["source_url"] = source_ref
    return metadata


def _fallback_document_payload(
    *,
    name: str,
    content: bytes,
    source_ref: str | None,
    message: str | None = None,
) -> dict[str, Any]:
    return {
        "document_id": name,
        "title": Path(name).stem,
        "text": message or content.decode("utf-8", errors="replace"),
        "source_ref": source_ref or name,
        "metadata": _metadata_for_source(name, source_ref),
    }


async def _download_url_bytes(url: str, max_bytes: int) -> tuple[bytes, str | None]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        message = "Only absolute http/https URLs are supported"
        raise ValueError(message)

    import httpx

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=_URL_DOWNLOAD_TIMEOUT_SECONDS,
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        content = response.content
    if len(content) > max_bytes:
        limit_mb = max_bytes // (1024 * 1024)
        message = f"Downloaded source exceeds {limit_mb} MB limit"
        raise ValueError(message)
    return content, response.headers.get("content-type")


def _filename_from_url(
    url: str,
    content_type: str | None,
    explicit_filename: str | None,
) -> str:
    if explicit_filename:
        candidate = explicit_filename.strip()
    else:
        path_name = Path(unquote(urlparse(url).path)).name
        candidate = path_name.strip() or "downloaded-source"
    candidate = candidate.replace("\\", "/").split("/")[-1]
    candidate = "".join(
        char if char.isalnum() or char in {" ", ".", "_", "-"} else "_"
        for char in candidate
    ).strip(" .")
    if not candidate:
        candidate = "downloaded-source"
    if Path(candidate).suffix:
        return candidate

    media_type = (content_type or "").split(";", 1)[0].strip().lower()
    extension = {
        "text/markdown": ".md",
        "text/x-markdown": ".md",
        "application/json": ".json",
        "application/pdf": ".pdf",
        "text/html": ".html",
        "text/plain": ".txt",
    }.get(media_type)
    if extension is None:
        extension = mimetypes.guess_extension(media_type) if media_type else None
    return f"{candidate}{extension or '.txt'}"


async def _ingest_named_contents(
    *,
    runtime_service: MaterialsKGService,
    sources: list[dict[str, Any]],
) -> dict:
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
    for source in sources:
        name = source["name"]
        content = source["content"]
        source_ref = source.get("source_ref")
        source_url = source.get("url")
        if len(content) > _MAX_UPLOAD_SIZE:
            limit_mb = _MAX_UPLOAD_SIZE // (1024 * 1024)
            raise HTTPException(
                status_code=413,
                detail=f"File '{name}' exceeds {limit_mb} MB limit",
            )
        parsed = _parse_uploaded_file(name, content)
        suffix = Path(name).suffix.lower()
        upload_record = {
            "name": name,
            "size": len(content),
            "type": suffix.lstrip(".") or "unknown",
        }
        if source_url:
            upload_record["url"] = source_url
        uploaded.append(upload_record)

        # DOCX/XLSX/PDF/HTML — document block parser (MarkItDown + optional VLM)
        if suffix in _PARSER_SUFFIXES:
            parser = _api_document_parser()
            if parser is not None:
                tmp_path = None
                try:
                    with tempfile.NamedTemporaryFile(
                        suffix=suffix,
                        delete=False,
                    ) as tmp:
                        tmp.write(content)
                        tmp_path = Path(tmp.name)
                    from kg_engine.ingestion.document_blocks import parse_document_file

                    document = parse_document_file(tmp_path, parser=parser)
                    document_payload = document.model_dump(mode="json")
                    document_payload["document_id"] = name
                    document_payload["title"] = Path(name).stem
                    document_payload["source_ref"] = source_ref or name
                    metadata = document_payload.setdefault("metadata", {})
                    if isinstance(metadata, dict):
                        metadata.update(_metadata_for_source(name, source_ref))
                    doc_payload.append(document_payload)
                    ingestion_status["llm_structured_files"].append(name)
                except Exception:
                    ingestion_status["searchable_fallback_files"].append(name)
                    ingestion_status["fallback_reasons"][name] = (
                        "document_parser_failed"
                    )
                    doc_payload.append(
                        _fallback_document_payload(
                            name=name,
                            content=content,
                            source_ref=source_ref,
                        )
                    )
                finally:
                    if tmp_path is not None:
                        tmp_path.unlink(missing_ok=True)
            else:
                ingestion_status["searchable_fallback_files"].append(name)
                ingestion_status["fallback_reasons"][name] = "no_parser_available"
                doc_payload.append(
                    _fallback_document_payload(
                        name=name,
                        content=content,
                        source_ref=source_ref,
                    )
                )
            continue

        # PNG/JPG/etc — image block parser (VL conductor)
        if suffix in _IMAGE_SUFFIXES:
            parser = _api_document_parser()
            if parser is not None:
                tmp_path = None
                try:
                    with tempfile.NamedTemporaryFile(
                        suffix=suffix,
                        delete=False,
                    ) as tmp:
                        tmp.write(content)
                        tmp_path = Path(tmp.name)
                    from kg_engine.ingestion.document_blocks import parse_document_file

                    document = parse_document_file(tmp_path, parser=parser)
                    document_payload = document.model_dump(mode="json")
                    document_payload["document_id"] = name
                    document_payload["title"] = Path(name).stem
                    document_payload["source_ref"] = source_ref or name
                    metadata = document_payload.setdefault("metadata", {})
                    if isinstance(metadata, dict):
                        metadata.update(_metadata_for_source(name, source_ref))
                    if document.text.strip() or document.text_units:
                        doc_payload.append(document_payload)
                        ingestion_status["llm_structured_files"].append(name)
                    else:
                        doc_payload.append(
                            _fallback_document_payload(
                                name=name,
                                content=content,
                                source_ref=source_ref,
                                message=(
                                    f"Image {name} processed but no text extracted."
                                ),
                            )
                        )
                        ingestion_status["searchable_fallback_files"].append(name)
                except Exception:
                    ingestion_status["searchable_fallback_files"].append(name)
                    ingestion_status["fallback_reasons"][name] = "image_parser_failed"
                    doc_payload.append(
                        _fallback_document_payload(
                            name=name,
                            content=content,
                            source_ref=source_ref,
                            message=f"Image {name} could not be processed.",
                        )
                    )
                finally:
                    if tmp_path is not None:
                        tmp_path.unlink(missing_ok=True)
            else:
                ingestion_status["searchable_fallback_files"].append(name)
                ingestion_status["fallback_reasons"][name] = "no_parser_available"
                doc_payload.append(
                    _fallback_document_payload(
                        name=name,
                        content=content,
                        source_ref=source_ref,
                        message=f"Image {name} — no VL parser available.",
                    )
                )
            continue

        # TXT/MD — raw text documents
        if suffix in _TEXT_SUFFIXES:
            ingestion_status["text_document_files"].append(name)
            if parsed is None:
                doc_payload.append(
                    _fallback_document_payload(
                        name=name,
                        content=content,
                        source_ref=source_ref,
                    )
                )
            else:
                items = parsed if isinstance(parsed, list) else [parsed]
                for item in items:
                    if isinstance(item, dict):
                        _mark_uploaded_from(item, name, source_ref=source_ref)
                if isinstance(parsed, list):
                    doc_payload.extend(items)
                else:
                    doc_payload.append(parsed)
            continue

        # JSON/CSV/TSV — structured data with LLM structuring
        if suffix in _STRUCTURED_SUFFIXES:
            structured_added = False
            if runtime_service.llm_provider and parsed is not None:
                try:
                    from kg_engine.llm_core.extraction import structure_upload_with_llm

                    structured = structure_upload_with_llm(
                        runtime_service.llm_provider,
                        name,
                        suffix.lstrip(".") or "structured",
                        parsed,
                    )
                    structured_added = _append_llm_structured_payload(
                        structured=structured,
                        name=name,
                        source_ref=source_ref,
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
                if parsed is not None:
                    _append_as_searchable_documents(
                        parsed=parsed,
                        name=name,
                        doc_payload=doc_payload,
                        source_ref=source_ref,
                    )
                else:
                    doc_payload.append(
                        _fallback_document_payload(
                            name=name,
                            content=content,
                            source_ref=source_ref,
                        )
                    )
            continue

        if parsed is not None:
            _append_parsed_payload_without_llm(
                parsed=parsed,
                name=name,
                suffix=suffix,
                ref_payload=ref_payload,
                exp_payload=exp_payload,
                doc_payload=doc_payload,
                source_ref=source_ref,
            )
        else:
            doc_payload.append(
                _fallback_document_payload(
                    name=name,
                    content=content,
                    source_ref=source_ref,
                )
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
        results["documents"] = await runtime_service.ingest_documents_async(
            DocumentCorpusAdapter().from_payload(doc_payload),
            parallel_workers=4,
        )
    results["ingestion"] = ingestion_status
    results["uploaded"] = uploaded
    results["overview"] = runtime_service.get_source_overview()
    results["suggested_questions"] = runtime_service.get_suggested_questions()
    return results


def _find_task_materials_dir() -> tuple[Path | None, bool, list[str]]:
    checked: list[str] = []
    for candidate in _TASK_MATERIALS_DIRS:
        checked.append(_display_path(candidate))
        if candidate.is_dir():
            return candidate, False, checked
    for candidate in _TASK_MATERIALS_FALLBACK_DIRS:
        checked.append(_display_path(candidate))
        if candidate.is_dir():
            return candidate, True, checked
    return None, False, checked


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(_PROJECT_ROOT))
    except ValueError:
        return str(path)


def _is_task_example_path(path: Path, task_dir: Path) -> bool:
    try:
        parts = path.relative_to(task_dir).parts
    except ValueError:
        return False
    return bool(parts) and parts[0].casefold().startswith("пример")


def _fallback_file_document(path: Path, task_dir: Path, reason: str) -> dict:
    relative_name = str(path.relative_to(task_dir))
    return {
        "document_id": relative_name,
        "title": path.stem,
        "text": f"Файл сохранен как источник без извлеченного текста: {relative_name}. Причина: {reason}.",
        "source_ref": relative_name,
        "metadata": {
            "source_file": relative_name,
            "source_path": str(path),
            "ingestion_role": "source_file_preserved",
            "parse_status": reason,
        },
    }


def _hypotheses_csv(result: HypothesisGenerationResult) -> str:
    output = io.StringIO()
    fieldnames = [
        "rank",
        "id",
        "target_kpi",
        "hypothesis_type",
        "statement",
        "rationale",
        "test_plan",
        "final_score",
        "novelty",
        "risk",
        "value",
        "evidence_strength",
        "novelty_rationale",
        "value_rationale",
        "risk_items",
        "supporting_entity_ids",
        "supporting_evidence_ids",
        "supporting_observation_ids",
        "supporting_text_unit_ids",
        "data_gap_ids",
        "assumptions",
        "required_evidence",
        "falsification_criteria",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for hypothesis in result.hypotheses:
        score = hypothesis.score
        writer.writerow(
            {
                "rank": hypothesis.rank,
                "id": hypothesis.id,
                "target_kpi": hypothesis.target_kpi,
                "hypothesis_type": hypothesis.hypothesis_type,
                "statement": hypothesis.statement,
                "rationale": hypothesis.rationale,
                "test_plan": hypothesis.test_plan,
                "final_score": score.final_score,
                "novelty": score.novelty,
                "risk": score.risk,
                "value": score.value,
                "evidence_strength": score.evidence_strength,
                "novelty_rationale": hypothesis.novelty_rationale,
                "value_rationale": hypothesis.value_rationale,
                "risk_items": ";".join(hypothesis.risk_items),
                "supporting_entity_ids": ";".join(hypothesis.supporting_entity_ids),
                "supporting_evidence_ids": ";".join(hypothesis.supporting_evidence_ids),
                "supporting_observation_ids": ";".join(
                    hypothesis.supporting_observation_ids
                ),
                "supporting_text_unit_ids": ";".join(
                    hypothesis.supporting_text_unit_ids
                ),
                "data_gap_ids": ";".join(hypothesis.data_gap_ids),
                "assumptions": ";".join(hypothesis.assumptions),
                "required_evidence": ";".join(hypothesis.required_evidence),
                "falsification_criteria": ";".join(
                    hypothesis.falsification_criteria
                ),
            }
        )
    return output.getvalue()


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


class HypothesisExportRequest(BaseModel):
    result: HypothesisGenerationResult


_UI_DIR = Path(__file__).resolve().parents[2] / "ui"
_UI_INDEX = _UI_DIR / "index.html"


def _notebook_dashboard_html() -> str:
    return _UI_INDEX.read_text(encoding="utf-8")


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
    product_service: ResearchProjectService | None = None,
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
    runtime_product_service = product_service or ResearchProjectService(
        _PROJECT_ROOT / ".scratch" / "product" / "research.sqlite3"
    )
    app = FastAPI(title=api_title)
    app.mount("/ui", StaticFiles(directory=_UI_DIR), name="ui")
    _source_files: list[dict] = []
    _task_load_jobs: dict[str, dict] = {}
    _task_load_jobs_lock = Lock()
    _hypothesis_jobs: dict[str, dict] = {}
    _hypothesis_jobs_lock = Lock()
    feedback_store = ExpertFeedbackStore(
        _PROJECT_ROOT / ".scratch" / "metrics" / "expert_feedback.jsonl"
    )

    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _get_task_load_job(job_id: str) -> dict:
        with _task_load_jobs_lock:
            job = _task_load_jobs.get(job_id)
            if job is None:
                raise HTTPException(status_code=404, detail="Task load job not found")
            return dict(job)

    def _update_task_load_job(job_id: str, **changes) -> None:
        with _task_load_jobs_lock:
            job = _task_load_jobs.get(job_id)
            if job is None:
                return
            job.update(changes)
            job["updated_at"] = _utc_now()

    def _finish_task_load_job(job_id: str, result: dict) -> None:
        with _task_load_jobs_lock:
            job = _task_load_jobs.get(job_id)
            if job is None:
                return
            job.update(
                {
                    "status": "completed",
                    "stage": "completed",
                    "finished_at": _utc_now(),
                    "updated_at": _utc_now(),
                    "result": result,
                    "error": None,
                    "total_files": max(
                        job.get("total_files", 0),
                        len(result.get("uploaded") or []),
                    ),
                    "processed_files": max(
                        job.get("total_files", 0),
                        len(result.get("uploaded") or []),
                    ),
                    "uploaded": result.get("uploaded") or [],
                    "skipped_example_files": result.get("skipped_example_files") or [],
                    "unsupported_files": result.get("unsupported_files") or [],
                }
            )

    def _fail_task_load_job(job_id: str, error: str) -> None:
        _update_task_load_job(
            job_id,
            status="failed",
            stage="failed",
            finished_at=_utc_now(),
            error=error,
        )

    def _get_hypothesis_job(job_id: str) -> dict:
        with _hypothesis_jobs_lock:
            job = _hypothesis_jobs.get(job_id)
            if job is None:
                raise HTTPException(status_code=404, detail="Hypothesis job not found")
            return dict(job)

    def _update_hypothesis_job(job_id: str, **changes) -> None:
        with _hypothesis_jobs_lock:
            job = _hypothesis_jobs.get(job_id)
            if job is None:
                return
            job.update(changes)
            job["updated_at"] = _utc_now()

    def _finish_hypothesis_job(job_id: str, result: dict) -> None:
        with _hypothesis_jobs_lock:
            job = _hypothesis_jobs.get(job_id)
            if job is None:
                return
            job.update(
                {
                    "status": "completed",
                    "stage": "completed",
                    "message": "Hypotheses generated",
                    "finished_at": _utc_now(),
                    "updated_at": _utc_now(),
                    "result": result,
                    "error": None,
                }
            )

    def _fail_hypothesis_job(job_id: str, error: str, *, status_code: int = 500) -> None:
        _update_hypothesis_job(
            job_id,
            status="failed",
            stage="failed",
            message="Hypothesis generation failed",
            finished_at=_utc_now(),
            error=error,
            status_code=status_code,
        )

    def require_writer(role: str | None) -> None:
        if role not in {"admin", "researcher", "expert"}:
            raise HTTPException(status_code=403, detail="Write access is required")

    def find_project(project_id: str):
        try:
            return runtime_product_service.get_project(project_id)
        except ProjectNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Project not found") from exc

    @app.post("/projects", status_code=201)
    def create_project(
        request: ResearchProjectCreate,
        user: str = Header(default="anonymous", alias="X-User"),
        role: str | None = Header(default=None, alias="X-Role"),
    ):
        require_writer(role)
        return runtime_product_service.create_project(request, actor=user)

    @app.get("/projects")
    def list_projects():
        return runtime_product_service.list_projects()

    @app.get("/projects/{project_id}")
    def get_project(project_id: str):
        return find_project(project_id)

    @app.patch("/projects/{project_id}")
    def update_project(
        project_id: str,
        changes: dict,
        user: str = Header(default="anonymous", alias="X-User"),
        role: str | None = Header(default=None, alias="X-Role"),
    ):
        require_writer(role)
        find_project(project_id)
        return runtime_product_service.update_project(project_id, changes, actor=user)

    @app.delete("/projects/{project_id}", status_code=204)
    def delete_project(
        project_id: str,
        user: str = Header(default="anonymous", alias="X-User"),
        role: str | None = Header(default=None, alias="X-Role"),
    ) -> Response:
        require_writer(role)
        find_project(project_id)
        runtime_product_service.delete_project(project_id, actor=user)
        return Response(status_code=204)

    @app.post("/projects/{project_id}/constraints", status_code=201)
    def add_project_constraint(
        project_id: str,
        constraint: Constraint,
        user: str = Header(default="anonymous", alias="X-User"),
        role: str | None = Header(default=None, alias="X-Role"),
    ):
        require_writer(role)
        find_project(project_id)
        return runtime_product_service.add_constraint(project_id, constraint, actor=user)

    @app.get("/projects/{project_id}/validation")
    def validate_project(project_id: str):
        find_project(project_id)
        return runtime_product_service.validate_project(project_id)

    @app.post("/projects/{project_id}/hypothesis-runs", status_code=201)
    def create_project_hypothesis_run(
        project_id: str,
        user: str = Header(default="anonymous", alias="X-User"),
        role: str | None = Header(default=None, alias="X-Role"),
    ):
        require_writer(role)
        project = find_project(project_id)
        validation = runtime_product_service.validate_project(project_id)
        if not validation.valid:
            raise HTTPException(
                status_code=409,
                detail="Project has unresolved hard constraints",
            )
        ranking_weights = project.ranking_weights
        if not ranking_weights:
            ranking_weights = runtime_product_service.derive_feedback_ranking_weights(
                project.id
            )
        request = HypothesisInput(
            target_kpi=project.target_kpi,
            material=project.materials[0] if project.materials else None,
            source_ids=project.source_ids or None,
            ranking_weights=ranking_weights,
            excluded_directions=[
                str(item.value)
                for item in project.constraints
                if item.kind == ConstraintKind.EXCLUSION
            ],
            domain_constraints=[
                item.explanation or f"{item.kind}: {item.operator} {item.value}"
                for item in project.constraints
            ],
        )
        result = runtime_service.generate_hypotheses(request)
        run = HypothesisRun(
            project_id=project.id,
            generation_engine=result.generation_engine,
            ranking_weights=ranking_weights,
            result=result.model_dump(mode="json"),
            actor=user,
        )
        return runtime_product_service.save_hypothesis_run(run, actor=user)

    @app.get("/hypothesis-runs/{run_id}")
    def get_hypothesis_run(run_id: str):
        try:
            return runtime_product_service.get_hypothesis_run(run_id)
        except ProjectNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Hypothesis run not found") from exc

    @app.post("/hypothesis-runs/{run_id}/reviews", status_code=201)
    def create_expert_review(
        run_id: str,
        review: ExpertReview,
        user: str = Header(default="anonymous", alias="X-User"),
        role: str | None = Header(default=None, alias="X-Role"),
    ):
        require_writer(role)
        if review.run_id != run_id or review.expert_id != user:
            raise HTTPException(status_code=422, detail="Review identity mismatch")
        try:
            return runtime_product_service.save_expert_review(review)
        except ProjectNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Hypothesis run not found") from exc

    @app.get("/hypothesis-runs/{run_id}/reviews")
    def list_expert_reviews(run_id: str):
        try:
            return runtime_product_service.list_expert_reviews(run_id=run_id)
        except ProjectNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Hypothesis run not found") from exc

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

    @app.post("/reviews/{review_id}/outcomes", status_code=201)
    def create_experiment_outcome(
        review_id: str,
        outcome: ExperimentOutcome,
        role: str | None = Header(default=None, alias="X-Role"),
    ):
        require_writer(role)
        if outcome.review_id != review_id:
            raise HTTPException(status_code=422, detail="Outcome identity mismatch")
        try:
            return runtime_product_service.save_experiment_outcome(outcome)
        except ProjectNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Expert review not found") from exc

    @app.get("/hypothesis-runs/{run_id}/outcomes")
    def list_experiment_outcomes(run_id: str):
        try:
            return runtime_product_service.list_experiment_outcomes(run_id=run_id)
        except ProjectNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Hypothesis run not found") from exc

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
        sources: list[dict[str, Any]] = []
        for upload in files:
            name = upload.filename or "unnamed"
            content = await upload.read()
            sources.append({"name": name, "content": content})
        results = await _ingest_named_contents(
            runtime_service=runtime_service,
            sources=sources,
        )
        _source_files.extend(results["uploaded"])
        return results

    @app.post("/ingest/url")
    async def ingest_url(request: UrlIngestRequest) -> dict:
        try:
            content, content_type = await _download_url_bytes(
                request.url,
                request.max_bytes,
            )
            name = _filename_from_url(request.url, content_type, request.filename)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to download URL: {exc}",
            ) from exc
        results = await _ingest_named_contents(
            runtime_service=runtime_service,
            sources=[
                {
                    "name": name,
                    "content": content,
                    "url": request.url,
                    "source_ref": request.url,
                }
            ],
        )
        _source_files.extend(results["uploaded"])
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
            "documents": runtime_service.ingest_documents_parallel(
                DocumentCorpusAdapter().from_payload(documents_payload),
                parallel_workers=4,
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

    async def _run_task_materials_pipeline(
        *,
        job_id: str,
        exclude_examples: bool,
        snapshot_path: str | None,
        enable_vision: bool | None,
        enable_llm_extraction: bool,
        enable_embeddings: bool,
        max_pdf_pages: int | None,
        parallel_workers: int,
    ) -> dict:
        started_at = _utc_now()
        _update_task_load_job(
            job_id,
            status="running",
            stage="discovering",
            started_at=started_at,
            message="Discovering Task 1 files",
        )

        task_dir, used_fallback, checked = _find_task_materials_dir()
        if task_dir is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    "No Task 1 corpus or packaged fallback corpus is present. "
                    f"Checked: {', '.join(checked)}"
                ),
            )

        if enable_vision is None:
            from kg_engine.config.settings import settings as _cfg

            enable_vision = getattr(_cfg, "materials_document_vision_enabled", False)

        ref_payload: dict = {}
        exp_payload: list = []
        doc_payload: list = []
        uploaded: list[dict] = []
        unsupported: list[str] = []
        skipped_examples: list[str] = []
        supported_suffixes = (
            _TEXT_SUFFIXES | _STRUCTURED_SUFFIXES | _PARSER_SUFFIXES | _IMAGE_SUFFIXES
        )
        worker_count = (
            max(parallel_workers, 0)
            or (
                getattr(runtime_settings, "materials_ingestion_parallel_workers", 4)
                if runtime_settings
                else 4
            )
        )

        candidates: list[Path] = []
        for path in sorted(item for item in task_dir.rglob("*") if item.is_file()):
            relative_name = str(path.relative_to(task_dir))
            if exclude_examples and _is_task_example_path(path, task_dir):
                skipped_examples.append(relative_name)
                continue
            suffix = path.suffix.lower()
            if suffix not in supported_suffixes:
                unsupported.append(relative_name)
                continue
            candidates.append(path)

        _update_task_load_job(
            job_id,
            stage="parsing",
            total_files=len(candidates),
            processed_files=0,
            skipped_example_files=list(skipped_examples),
            unsupported_files=list(unsupported),
            message=f"Parsing {len(candidates)} files",
        )

        shared_parser = _api_document_parser(
            runtime_settings,
            enable_vision=enable_vision,
        )
        if shared_parser is not None and max_pdf_pages is not None:
            from dataclasses import replace

            shared_parser.settings = replace(
                shared_parser.settings,
                max_pdf_pages=max_pdf_pages,
            )

        parsed_files = 0

        def _record_upload(path: Path) -> dict:
            item = {
                "name": str(path.relative_to(task_dir)),
                "size": path.stat().st_size,
                "type": path.suffix.lstrip(".") or "unknown",
            }
            uploaded.append(item)
            return item

        def _mark_parsed(path: Path) -> None:
            nonlocal parsed_files
            parsed_files += 1
            _update_task_load_job(
                job_id,
                processed_files=parsed_files,
                uploaded=list(uploaded),
                message=f"Parsed {parsed_files} of {len(candidates)} files",
            )

        def _parse_doc_file(path: Path) -> dict:
            try:
                from kg_engine.ingestion.document_blocks import parse_document_file

                doc = parse_document_file(path, parser=shared_parser)
                if doc.text.strip() or doc.text_units:
                    return doc.model_dump(mode="json")
                return _fallback_file_document(path, task_dir, "no_text_extracted")
            except Exception:
                return _fallback_file_document(path, task_dir, "parser_failed")

        async def _parse_task_file(path: Path, semaphore: asyncio.Semaphore) -> dict:
            async with semaphore:
                suffix = path.suffix.lower()
                relative_name = str(path.relative_to(task_dir))
                if suffix in (_PARSER_SUFFIXES | _IMAGE_SUFFIXES):
                    doc = await asyncio.to_thread(_parse_doc_file, path)
                    return {"path": path, "kind": "document", "payload": doc}
                content = await asyncio.to_thread(path.read_bytes)
                parsed = _parse_uploaded_file(relative_name, content)
                if parsed is None:
                    return {
                        "path": path,
                        "kind": "unsupported",
                        "relative_name": relative_name,
                    }
                return {
                    "path": path,
                    "kind": "parsed",
                    "relative_name": relative_name,
                    "suffix": suffix,
                    "payload": parsed,
                }

        semaphore = asyncio.Semaphore(max(worker_count, 1))
        tasks = [
            asyncio.create_task(_parse_task_file(path, semaphore))
            for path in candidates
        ]
        for task in asyncio.as_completed(tasks):
            parsed_result = await task
            path = parsed_result["path"]
            suffix = path.suffix.lower()
            relative_name = str(path.relative_to(task_dir))
            if parsed_result["kind"] == "unsupported":
                unsupported.append(parsed_result["relative_name"])
                _mark_parsed(path)
                continue
            if parsed_result["kind"] == "document":
                doc_payload.append(parsed_result["payload"])
            else:
                _append_parsed_payload_without_llm(
                    parsed=parsed_result["payload"],
                    name=relative_name,
                    suffix=suffix,
                    ref_payload=ref_payload,
                    exp_payload=exp_payload,
                    doc_payload=doc_payload,
                )
            _record_upload(path)
            _mark_parsed(path)

        doc_count = 0
        doc_results: dict | None = None
        if doc_payload:
            document_batch = DocumentCorpusAdapter().from_payload(doc_payload)
            _update_task_load_job(
                job_id,
                stage="ingesting",
                message=f"Ingesting {len(document_batch)} parsed documents",
            )
            with _TemporaryProviderTimeout(
                runtime_service.llm_provider,
                runtime_settings,
            ):
                doc_results = await runtime_service.ingest_documents_async(
                    document_batch,
                    enable_llm_extraction=enable_llm_extraction,
                    enable_embeddings=enable_embeddings,
                    parallel_workers=max(worker_count, 1),
                )
            doc_count = len(document_batch)

        results: dict = {
            "job_id": job_id,
            "task_materials_dir": _display_path(task_dir),
            "used_fallback": used_fallback,
            "excluded_examples": exclude_examples,
            "vision_enabled": enable_vision,
            "llm_extraction_enabled": enable_llm_extraction,
            "embeddings_enabled": enable_embeddings,
            "parallel_workers": max(worker_count, 1),
            "uploaded": uploaded,
            "documents_ingested": doc_count,
            "skipped_example_files": skipped_examples,
            "unsupported_files": unsupported,
        }
        if doc_results is not None:
            results["documents"] = doc_results
        if used_fallback:
            results["warnings"] = [
                (
                    "Task 1 corpus directory is not present; loaded packaged "
                    "sample_sources fallback instead."
                )
            ]

        if ref_payload:
            _update_task_load_job(
                job_id,
                stage="ingesting_reference",
                message="Ingesting structured reference records",
            )
            results["reference"] = await asyncio.to_thread(
                runtime_service.ingest_reference_data,
                ReferenceDataAdapter().from_payload(ref_payload),
            )
        if exp_payload:
            _update_task_load_job(
                job_id,
                stage="ingesting_experiments",
                message="Ingesting structured experiment records",
            )
            results["experiments"] = await asyncio.to_thread(
                runtime_service.ingest_experiments,
                ExperimentCatalogAdapter().from_payload(exp_payload),
                enable_embeddings=enable_embeddings,
            )
        if uploaded:
            _source_files.extend(uploaded)

        _update_task_load_job(
            job_id,
            stage="summarizing",
            message="Refreshing source overview",
        )
        results["overview"] = await asyncio.to_thread(runtime_service.get_source_overview)
        results["suggested_questions"] = await asyncio.to_thread(
            runtime_service.get_suggested_questions
        )
        if snapshot_path:
            results["snapshot"] = await asyncio.to_thread(
                runtime_service.save_graph_snapshot,
                snapshot_path,
            )
        return results

    @app.post("/demo/load-task-materials", status_code=202)
    async def load_task_materials(
        background_tasks: BackgroundTasks,
        exclude_examples: bool = Query(default=False),
        snapshot_path: str | None = Query(default=None),
        enable_vision: bool = Query(default=None),
        enable_llm_extraction: bool = Query(default=True, description="Run LLM extraction on document text units"),
        enable_embeddings: bool = Query(default=False, description="Generate embeddings during bulk load"),
        max_pdf_pages: int | None = Query(default=None, description="Limit PDF pages parsed per file"),
        parallel_workers: int = Query(default=0, description="Parallel file parse workers (0=auto)"),
    ) -> dict:
        task_dir, used_fallback, checked = _find_task_materials_dir()
        if task_dir is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    "No Task 1 corpus or packaged fallback corpus is present. "
                    f"Checked: {', '.join(checked)}"
                ),
            )
        job_id = uuid4().hex
        now = _utc_now()
        job = {
            "job_id": job_id,
            "status": "queued",
            "stage": "queued",
            "message": "Queued Task 1 materials load",
            "created_at": now,
            "updated_at": now,
            "started_at": None,
            "finished_at": None,
            "total_files": 0,
            "processed_files": 0,
            "task_materials_dir": _display_path(task_dir),
            "used_fallback": used_fallback,
            "excluded_examples": exclude_examples,
            "vision_enabled": enable_vision,
            "llm_extraction_enabled": enable_llm_extraction,
            "embeddings_enabled": enable_embeddings,
            "parallel_workers": parallel_workers,
            "uploaded": [],
            "skipped_example_files": [],
            "unsupported_files": [],
            "result": None,
            "error": None,
        }
        with _task_load_jobs_lock:
            _task_load_jobs[job_id] = job

        async def _worker() -> None:
            try:
                result = await _run_task_materials_pipeline(
                    job_id=job_id,
                    exclude_examples=exclude_examples,
                    snapshot_path=snapshot_path,
                    enable_vision=enable_vision,
                    enable_llm_extraction=enable_llm_extraction,
                    enable_embeddings=enable_embeddings,
                    max_pdf_pages=max_pdf_pages,
                    parallel_workers=parallel_workers,
                )
                _finish_task_load_job(job_id, result)
            except HTTPException as exc:
                _fail_task_load_job(job_id, str(exc.detail))
            except Exception as exc:
                _fail_task_load_job(job_id, str(exc))

        background_tasks.add_task(_worker)
        return _get_task_load_job(job_id)

    @app.get("/demo/load-task-materials/jobs/{job_id}")
    def get_task_materials_load_job(job_id: str) -> dict:
        return _get_task_load_job(job_id)

    @app.post("/ingest/reference")
    async def ingest_reference(batch: ReferenceDataBatch) -> dict[str, int]:
        return await asyncio.to_thread(runtime_service.ingest_reference_data, batch)

    @app.post("/ingest/experiments")
    async def ingest_experiments(batch: list[ExperimentInput]) -> dict[str, int]:
        return await asyncio.to_thread(runtime_service.ingest_experiments, batch)

    @app.post("/ingest/documents")
    async def ingest_documents(batch: list[DocumentInput]) -> dict[str, int]:
        return await runtime_service.ingest_documents_async(batch, parallel_workers=4)

    @app.post("/query/answer")
    async def query_answer(request: AnswerQueryRequest) -> dict:
        return await asyncio.to_thread(
            runtime_service.answer_question,
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

    def _run_hypothesis_generation(
        request: HypothesisInput,
        *,
        job_id: str | None = None,
    ) -> dict:
        from kg_engine.config.settings import settings as app_settings

        effective_settings = runtime_settings or app_settings
        engine = effective_settings.materials_hypothesis_engine.strip().lower()
        if job_id is not None:
            _update_hypothesis_job(
                job_id,
                status="running",
                stage="preparing",
                started_at=_utc_now(),
                message=f"Preparing {engine} hypothesis generation",
            )
        if engine == "deterministic":
            if job_id is not None:
                _update_hypothesis_job(
                    job_id,
                    stage="generating",
                    message="Generating deterministic hypotheses",
                )
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

            if job_id is not None:
                _update_hypothesis_job(
                    job_id,
                    stage="deepagents",
                    message="Running Deep Agents hypothesis factory",
                )
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

    @app.post("/hypotheses/generate", status_code=202)
    async def generate_hypotheses(
        request: HypothesisInput,
        background_tasks: BackgroundTasks,
    ) -> dict:
        from kg_engine.config.settings import settings as app_settings

        effective_settings = runtime_settings or app_settings
        job_id = uuid4().hex
        now = _utc_now()
        job = {
            "job_id": job_id,
            "status": "queued",
            "stage": "queued",
            "message": "Queued hypothesis generation",
            "created_at": now,
            "updated_at": now,
            "started_at": None,
            "finished_at": None,
            "request": request.model_dump(mode="json"),
            "result": None,
            "error": None,
            "status_code": None,
        }
        with _hypothesis_jobs_lock:
            _hypothesis_jobs[job_id] = job

        engine = effective_settings.materials_hypothesis_engine.strip().lower()
        if engine == "deepagents":
            from kg_engine.llm_core.provider import resolve_chat_completions_config

            if resolve_chat_completions_config(
                effective_settings,
                require_provider=True,
            ) is None:
                _fail_hypothesis_job(
                    job_id,
                    "API key and base URL for the selected Deep Agents provider are not configured.",
                    status_code=503,
                )
                return _get_hypothesis_job(job_id)

        async def _worker() -> None:
            try:
                result = await asyncio.to_thread(
                    _run_hypothesis_generation,
                    request,
                    job_id=job_id,
                )
                _finish_hypothesis_job(job_id, result)
            except HTTPException as exc:
                _fail_hypothesis_job(
                    job_id,
                    str(exc.detail),
                    status_code=exc.status_code,
                )
            except Exception as exc:
                _fail_hypothesis_job(job_id, str(exc))

        background_tasks.add_task(_worker)
        return _get_hypothesis_job(job_id)

    @app.get("/hypotheses/jobs/{job_id}")
    def get_hypothesis_job(job_id: str) -> dict:
        return _get_hypothesis_job(job_id)

    @app.post("/hypotheses/export")
    def export_hypotheses(
        request: HypothesisExportRequest,
        export_format: str = Query(
            default="json",
            pattern="^(json|csv|xlsx|docx|pdf|markdown)$",
            alias="format",
        ),
    ) -> Response:
        result = request.result
        if export_format == "csv":
            return Response(
                content=_hypotheses_csv(result),
                media_type="text/csv; charset=utf-8",
                headers={
                    "Content-Disposition": (
                        'attachment; filename="materials-hypotheses.csv"'
                    )
                },
            )
        if export_format in {"xlsx", "docx", "pdf", "markdown"}:
            media_types = {
                "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "pdf": "application/pdf",
                "markdown": "text/markdown; charset=utf-8",
            }
            extensions = {"markdown": "md"}
            extension = extensions.get(export_format, export_format)
            return Response(
                content=render_hypothesis_report(result, export_format),
                media_type=media_types[export_format],
                headers={
                    "Content-Disposition": (
                        f'attachment; filename="materials-hypotheses.{extension}"'
                    )
                },
            )
        return Response(
            content=json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2),
            media_type="application/json",
            headers={
                "Content-Disposition": 'attachment; filename="materials-hypotheses.json"'
            },
        )

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
            [str(item) for item in request.relation_filters]
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
            raise HTTPException(
                status_code=403,
                detail="Destructive API disabled. Set MATERIALS_ENABLE_DESTRUCTIVE_API=true.",
            )
        removed = runtime_service.delete_source(source_name)
        _source_files[:] = [s for s in _source_files if s.get("name") != source_name]
        return {
            "deleted": source_name,
            "removed_records": removed,
            "overview": runtime_service.get_source_overview(),
        }

    @app.delete("/sources")
    def clear_all_sources() -> dict:
        if not getattr(runtime_settings, "materials_enable_destructive_api", False):
            raise HTTPException(
                status_code=403,
                detail="Destructive API disabled. Set MATERIALS_ENABLE_DESTRUCTIVE_API=true.",
            )
        runtime_service.clear_all()
        _source_files.clear()
        return {
            "cleared": True,
            "overview": runtime_service.get_source_overview(),
            "suggested_questions": runtime_service.get_suggested_questions(),
        }

    return app
