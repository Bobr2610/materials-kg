"""Persistent synchronous ingestion jobs with per-file failure isolation."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime
import logging
from pathlib import Path
import sqlite3

from kg_engine.domain.ingestion import IngestionJob
from kg_engine.domain.ingestion import IngestionJobStatus
from kg_engine.domain.ingestion import ParsedSource
from kg_engine.domain.models import DocumentInput
from kg_engine.domain.models import TextUnitInput
from kg_engine.ingestion.readers import DocumentReaderRegistry
from kg_engine.services.materials_kg import MaterialsKGService

logger = logging.getLogger(__name__)


class IngestionJobNotFoundError(LookupError):
    """Raised for unknown ingestion job or source identifiers."""


class IngestionJobService:
    """Parse files, persist provenance, and ingest valid documents into the graph."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        graph_service: MaterialsKGService,
        registry: DocumentReaderRegistry | None = None,
    ) -> None:
        self._path = Path(database_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._graph = graph_service
        self._registry = registry or DocumentReaderRegistry()
        self._ensure_schema()

    def submit(self, files: list[tuple[str, bytes]], *, actor: str) -> IngestionJob:
        """Process a batch while allowing individual files to fail."""
        job = IngestionJob(
            status=IngestionJobStatus.RUNNING,
            total_files=len(files),
            actor=actor,
        )
        for name, content in files:
            try:
                parsed = self._registry.read_bytes(name, content)
                job.source_ids.append(parsed.checksum)
                if self._source_exists(parsed.checksum):
                    job.duplicate_files += 1
                    continue
                self._ingest(parsed)
                self._save_source(parsed)
                job.processed_files += 1
            except Exception as exc:
                logger.warning("Failed to ingest %s: %s", name, exc)
                job.failed_files += 1
                job.errors.append(f"{Path(name).name}: {exc}")
        if job.failed_files and (job.processed_files or job.duplicate_files):
            job.status = IngestionJobStatus.PARTIAL
        elif job.failed_files:
            job.status = IngestionJobStatus.FAILED
        else:
            job.status = IngestionJobStatus.SUCCEEDED
        job.completed_at = datetime.now(UTC)
        self._save_job(job)
        return job

    def get_job(self, job_id: str) -> IngestionJob:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM ingestion_jobs WHERE id = ?", (job_id,)
            ).fetchone()
        if row is None:
            raise IngestionJobNotFoundError(job_id)
        return IngestionJob.model_validate_json(row[0])

    def get_source(self, source_id: str) -> ParsedSource:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM parsed_sources WHERE checksum = ?", (source_id,)
            ).fetchone()
        if row is None:
            raise IngestionJobNotFoundError(source_id)
        return ParsedSource.model_validate_json(row[0])

    def _ingest(self, parsed: ParsedSource) -> None:
        text_units = [
            TextUnitInput(content=item.content, metadata={"locator": item.locator})
            for item in parsed.fragments
        ]
        document = DocumentInput(
            document_id=f"source:{parsed.checksum}",
            title=Path(parsed.name).stem,
            text="\n".join(item.content for item in parsed.fragments),
            source_ref=parsed.name,
            text_units=text_units,
            metadata={
                "checksum": parsed.checksum,
                "media_type": parsed.media_type,
                "parser_version": parsed.parser_version,
                "warnings": [item.model_dump(mode="json") for item in parsed.warnings],
            },
        )
        self._graph.ingest_documents([document])

    def _source_exists(self, checksum: str) -> bool:
        with self._connect() as connection:
            return (
                connection.execute(
                    "SELECT 1 FROM parsed_sources WHERE checksum = ?", (checksum,)
                ).fetchone()
                is not None
            )

    def _save_source(self, source: ParsedSource) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO parsed_sources (checksum, payload) VALUES (?, ?)",
                (source.checksum, source.model_dump_json()),
            )

    def _save_job(self, job: IngestionJob) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO ingestion_jobs (id, payload) VALUES (?, ?)",
                (job.id, job.model_dump_json()),
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS parsed_sources "
                "(checksum TEXT PRIMARY KEY, payload TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS ingestion_jobs "
                "(id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
            )
