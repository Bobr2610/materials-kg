"""Ingest reference, experiment, and document batches into the graph-first core."""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)

_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from kg_engine.config.settings import settings
from kg_engine.ingestion.adapters import DocumentCorpusAdapter
from kg_engine.ingestion.adapters import ExperimentCatalogAdapter
from kg_engine.ingestion.adapters import ReferenceDataAdapter
from kg_engine.ingestion.adapters import StaffDirectoryAdapter
from kg_engine.ingestion.adapters import TagCatalogAdapter
from kg_engine.ingestion.document_blocks import DocumentBlockParser
from kg_engine.ingestion.document_blocks import DocumentParseSettings
from kg_engine.ingestion.document_blocks import parse_document_file
from kg_engine.llm_core.provider import create_provider_from_settings
from kg_engine.llm_core.vision import VisionConductor
from kg_engine.repositories.factory import create_materials_repository
from kg_engine.services.materials_kg import MaterialsKGService


_CANONICAL_REFERENCE_SECTIONS = {
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

_CANONICAL_EXPERIMENT_SECTIONS = {"experiments", "rows", "items"}
_CANONICAL_DOCUMENT_SECTIONS = {"documents", "rows", "items"}
_TEXT_FILE_SUFFIXES = {".txt", ".md"}
_STRUCTURED_FILE_SUFFIXES = {".json", ".jsonl", ".csv", ".tsv"}
_PARSER_FILE_SUFFIXES = {
    ".docx",
    ".xlsx",
    ".xls",
    ".pdf",
    ".html",
    ".htm",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".tif",
    ".tiff",
    ".bmp",
}


def _supported_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return [
        item
        for item in sorted(path.rglob("*"))
        if item.is_file()
        and item.suffix.lower()
        in {*_STRUCTURED_FILE_SUFFIXES, *_TEXT_FILE_SUFFIXES, *_PARSER_FILE_SUFFIXES}
    ]


def _load_tabular(path: Path) -> list[dict[str, Any]]:
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle, delimiter=delimiter)]


def _document_parser(*, disable_vision: bool = False) -> DocumentBlockParser:
    vision_enabled = (
        settings.materials_document_vision_enabled and not disable_vision
    )
    conductor = None
    if vision_enabled:
        vision_provider = _create_vision_provider()
        if vision_provider is None:
            logger.info(
                "No VLM provider configured — VLM interpretation disabled."
            )
            vision_enabled = False
        else:
            vision_model = settings.materials_vision_model or settings.default_model or None
            conductor = VisionConductor(vision_provider, model=vision_model)
            logger.info("VLM enabled, model: %s", vision_model or "(default)")
    return DocumentBlockParser(
        vision_conductor=conductor,
        settings=DocumentParseSettings(
            enable_vision=vision_enabled,
            enable_ocr=settings.materials_document_ocr_enabled,
            ocr_languages=settings.materials_ocr_languages,
            ocr_timeout_seconds=settings.materials_ocr_timeout_seconds,
            ocr_min_text_chars=settings.materials_ocr_min_text_chars,
            ocr_min_confidence=settings.materials_ocr_min_confidence,
            pdf_render_dpi=settings.materials_pdf_render_dpi,
            max_pdf_pages=settings.materials_pdf_max_pages,
            grobid_url=settings.materials_grobid_url,
            grobid_timeout_seconds=settings.materials_grobid_timeout_seconds,
            grobid_min_text_chars=settings.materials_grobid_min_text_chars,
        ),
    )


def _create_vision_provider():
    """Create LLM provider for VLM from dedicated settings or the main provider."""
    from kg_engine.llm_core.provider import LLMProvider, resolve_chat_completions_config

    vision_provider_name = (settings.materials_vision_provider or "").strip().lower()
    vision_model = (settings.materials_vision_model or "").strip()
    vision_api_key = (settings.materials_vision_api_key or "").strip()
    vision_base_url = (settings.materials_vision_base_url or "").strip()

    if vision_provider_name:
        if not vision_api_key:
            vision_api_key = (settings.llm_api_key or "").strip()

        if not vision_base_url:
            vision_base_url = (settings.llm_base_url or "").strip()

        if vision_api_key or vision_base_url:
            if not vision_model:
                vision_model = settings.default_model

            vision_settings_proxy = type("VisionSettings", (), {
                "default_llm_provider": vision_provider_name,
                "default_model": vision_model,
                "llm_api_key": vision_api_key,
                "llm_base_url": vision_base_url,
            })()
            config = resolve_chat_completions_config(vision_settings_proxy)
            if config is not None:
                return LLMProvider(
                    base_url=config.base_url,
                    api_key=config.api_key,
                    chat_model=config.chat_model,
                    embedding_model=config.embedding_model,
                )

    # Fallback to main LLM provider
    return create_provider_from_settings(settings)


def _load_one(
    path: Path,
    *,
    family: str,
    document_parser: DocumentBlockParser | None = None,
) -> Any:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    if suffix == ".jsonl":
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    if suffix in {".csv", ".tsv"}:
        return _load_tabular(path)
    if family == "documents" and suffix in {".txt", ".md"}:
        text = path.read_text(encoding="utf-8", errors="replace")
        title = path.stem
        if suffix == ".md":
            for line in text.splitlines():
                if line.startswith("# "):
                    title = line[2:].strip() or title
                    break
        return [
            {
                "document_id": str(path),
                "title": title,
                "text": text,
                "metadata": {"source_path": str(path)},
            }
        ]
    if family in {"documents", "bundle"} and suffix in _PARSER_FILE_SUFFIXES:
        parser = document_parser or _document_parser()
        document = parse_document_file(path, parser=parser)
        return [document.model_dump(mode="json")]
    logger.warning("Skipping unsupported %s input file: %s", family, path)
    return [] if family != "reference" else {}


def _source_metadata(path: Path, **extra: Any) -> dict[str, Any]:
    return {
        "source_path": str(path),
        "source_file": path.name,
        **{key: value for key, value in extra.items() if value not in (None, "")},
    }


def _document_from_text_file(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    title = path.stem
    if path.suffix.lower() == ".md":
        for line in text.splitlines():
            if line.startswith("# "):
                title = line[2:].strip() or title
                break
    return {
        "document_id": str(path),
        "title": title,
        "text": text,
        "metadata": _source_metadata(path, ingestion_role="raw_text_document"),
    }


def _fallback_document(
    path: Path, payload: Any, *, row_index: int | None = None
) -> dict[str, Any]:
    if isinstance(payload, str):
        text = payload
    else:
        text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    row_part = "" if row_index is None else f"#{row_index}"
    return {
        "document_id": f"{path}{row_part}",
        "title": path.stem if row_index is None else f"{path.stem} row {row_index}",
        "text": text,
        "metadata": _source_metadata(
            path,
            row_index=row_index,
            ingestion_role="unclassified_source_preserved",
        ),
    }


def _has_explicit_entity_kind(record: dict[str, Any]) -> bool:
    return bool(record.get("kind") or record.get("entity_kind") or record.get("type"))


def _looks_like_experiment(record: dict[str, Any]) -> bool:
    return bool(
        (record.get("experiment_id") or record.get("id") or record.get("code"))
        and (
            record.get("material_name") or record.get("material") or record.get("alloy")
        )
        and (
            isinstance(record.get("observations"), list)
            or record.get("property_name")
            or record.get("property")
            or record.get("property_id")
        )
    )


def _looks_like_document(record: dict[str, Any]) -> bool:
    return bool(
        (
            record.get("document_id")
            or record.get("path")
            or record.get("file")
            or record.get("id")
        )
        and (record.get("text") or record.get("content") or record.get("body"))
    )


def _iter_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in (*_CANONICAL_EXPERIMENT_SECTIONS, *_CANONICAL_DOCUMENT_SECTIONS):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [payload]
    return []


def _merge_reference_payload(
    target: dict[str, Any], payload: Any, _source: Path
) -> None:
    if isinstance(payload, dict):
        matched = False
        for key, value in payload.items():
            if key in _CANONICAL_REFERENCE_SECTIONS and isinstance(value, list):
                target.setdefault(key, []).extend(value)
                matched = True
        if matched:
            return
        if payload.get("kind") or payload.get("entity_kind") or payload.get("type"):
            target.setdefault("entities", []).append(payload)
        return
    if isinstance(payload, list):
        target.setdefault("entities", []).extend(
            item
            for item in payload
            if isinstance(item, dict)
            and (item.get("kind") or item.get("entity_kind") or item.get("type"))
        )


def _merge_bundle_payload(bundle: dict[str, Any], payload: Any, source: Path) -> None:
    if isinstance(payload, dict):
        matched = False
        for key, value in payload.items():
            if key in _CANONICAL_REFERENCE_SECTIONS and isinstance(value, list):
                bundle["reference"].setdefault(key, []).extend(value)
                matched = True
            elif key == "experiments" and isinstance(value, list):
                bundle["experiments"].extend(
                    {
                        **item,
                        "metadata": {
                            **item.get("metadata", {}),
                            **_source_metadata(source),
                        },
                    }
                    if isinstance(item, dict)
                    else item
                    for item in value
                )
                matched = True
            elif key == "documents" and isinstance(value, list):
                bundle["documents"].extend(
                    {
                        **item,
                        "metadata": {
                            **item.get("metadata", {}),
                            **_source_metadata(source),
                        },
                    }
                    if isinstance(item, dict)
                    else item
                    for item in value
                )
                matched = True
        if matched:
            return

    for index, record in enumerate(_iter_records(payload)):
        metadata = _source_metadata(source, row_index=index)
        if _has_explicit_entity_kind(record):
            bundle["reference"].setdefault("entities", []).append(
                {
                    **record,
                    "source_ref": record.get("source_ref") or str(source),
                }
            )
        elif _looks_like_experiment(record):
            bundle["experiments"].append(
                {**record, "metadata": {**record.get("metadata", {}), **metadata}}
            )
        elif _looks_like_document(record):
            bundle["documents"].append(
                {**record, "metadata": {**record.get("metadata", {}), **metadata}}
            )
        else:
            bundle["documents"].append(
                _fallback_document(source, record, row_index=index)
            )

    if not _iter_records(payload) and payload not in (None, {}, []):
        bundle["documents"].append(_fallback_document(source, payload))


def _load_bundle(
    path: str,
    *,
    document_parser: DocumentBlockParser | None = None,
) -> dict[str, Any]:
    source_path = Path(path)
    if not source_path.exists():
        raise FileNotFoundError(f"Input path not found: {source_path}")
    bundle: dict[str, Any] = {
        "reference": {},
        "experiments": [],
        "documents": [],
    }
    for file_path in _supported_files(source_path):
        suffix = file_path.suffix.lower()
        if suffix in _TEXT_FILE_SUFFIXES:
            bundle["documents"].append(_document_from_text_file(file_path))
            continue
        if suffix in _STRUCTURED_FILE_SUFFIXES:
            _merge_bundle_payload(
                bundle,
                _load_one(
                    file_path,
                    family="bundle",
                    document_parser=document_parser,
                ),
                file_path,
            )
            continue
        if suffix in _PARSER_FILE_SUFFIXES:
            _merge_bundle_payload(
                bundle,
                _load_one(
                    file_path,
                    family="bundle",
                    document_parser=document_parser,
                ),
                file_path,
            )
    return bundle


def _load_payload(
    path: str | None,
    *,
    family: str,
    document_parser: DocumentBlockParser | None = None,
) -> object | None:
    if path is None:
        return None
    source_path = Path(path)
    if not source_path.exists():
        raise FileNotFoundError(f"Input file not found: {source_path}")
    files = _supported_files(source_path)
    if family == "reference":
        merged: dict[str, Any] = {}
        for file_path in files:
            _merge_reference_payload(
                merged,
                _load_one(
                    file_path,
                    family=family,
                    document_parser=document_parser,
                ),
                file_path,
            )
        return merged
    merged_rows: list[Any] = []
    for file_path in files:
        payload = _load_one(
            file_path,
            family=family,
            document_parser=document_parser,
        )
        if isinstance(payload, list):
            merged_rows.extend(payload)
        elif isinstance(payload, dict):
            for key in (family, "rows", "items"):
                value = payload.get(key)
                if isinstance(value, list):
                    merged_rows.extend(value)
                    break
            else:
                merged_rows.append(payload)
    return merged_rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest data into the materials KG core"
    )
    parser.add_argument(
        "--input",
        type=str,
        default=None,
        help=(
            "Path to a mixed file or directory. The loader recursively ingests explicit "
            "reference/experiment/document structures and preserves unknown files as documents."
        ),
    )
    parser.add_argument(
        "--reference",
        type=str,
        default=None,
        help="Path to reference JSON/JSONL/CSV/TSV file or directory",
    )
    parser.add_argument(
        "--experiments",
        type=str,
        default=None,
        help="Path to experiment JSON/JSONL/CSV/TSV file or directory",
    )
    parser.add_argument(
        "--documents",
        type=str,
        default=None,
        help="Path to document JSON/JSONL/CSV/TSV/TXT/MD file or directory",
    )
    parser.add_argument(
        "--staff",
        type=str,
        default=None,
        help="Path to staff/lab JSON/JSONL/CSV/TSV file or directory",
    )
    parser.add_argument(
        "--tags",
        type=str,
        default=None,
        help="Path to topic tag JSON/JSONL/CSV/TSV file or directory",
    )
    parser.add_argument(
        "--ensure-schema",
        action="store_true",
        default=False,
        help="Ensure Neo4j schema constraints before ingestion",
    )
    parser.add_argument(
        "--disable-vision",
        action="store_true",
        default=False,
        help=(
            "Disable Vision-Language interpretation for rendered PDF/image pages. "
            "VLM is opt-in through MATERIALS_DOCUMENT_VISION_ENABLED; local OCR "
            "is used first."
        ),
    )
    args = parser.parse_args()

    document_parser = _document_parser(disable_vision=args.disable_vision)

    repository = create_materials_repository(
        settings,
        ensure_schema=args.ensure_schema or settings.materials_api_ensure_schema,
    )
    service = MaterialsKGService(repository)

    if args.input:
        bundle = _load_bundle(args.input, document_parser=document_parser)
        reference_result = service.ingest_reference_data(
            ReferenceDataAdapter().from_payload(bundle["reference"])
        )
        experiment_result = service.ingest_experiments(
            ExperimentCatalogAdapter().from_payload(bundle["experiments"])
        )
        document_result = service.ingest_documents(
            DocumentCorpusAdapter().from_payload(bundle["documents"])
        )
        logger.info("Mixed input reference ingestion: %s", reference_result)
        logger.info("Mixed input experiment ingestion: %s", experiment_result)
        logger.info("Mixed input document ingestion: %s", document_result)

    if args.reference:
        payload = _load_payload(args.reference, family="reference")
        batch = ReferenceDataAdapter().from_payload(payload or {})
        result = service.ingest_reference_data(batch)
        logger.info("Reference ingestion: %s", result)

    if args.experiments:
        payload = _load_payload(args.experiments, family="experiments")
        batch = ExperimentCatalogAdapter().from_payload(payload or [])
        result = service.ingest_experiments(batch)
        logger.info("Experiment ingestion: %s", result)

    if args.documents:
        payload = _load_payload(
            args.documents,
            family="documents",
            document_parser=document_parser,
        )
        batch = DocumentCorpusAdapter().from_payload(payload or [])
        result = service.ingest_documents(batch)
        logger.info("Document ingestion: %s", result)

    if args.staff:
        payload = _load_payload(args.staff, family="staff")
        batch = StaffDirectoryAdapter().from_payload(payload or [])
        result = service.ingest_reference_data(batch)
        logger.info("Staff ingestion: %s", result)

    if args.tags:
        payload = _load_payload(args.tags, family="tags")
        batch = TagCatalogAdapter().from_payload(payload or [])
        result = service.ingest_reference_data(batch)
        logger.info("Tag ingestion: %s", result)


if __name__ == "__main__":
    main()
