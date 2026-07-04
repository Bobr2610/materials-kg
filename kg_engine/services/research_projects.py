"""Persistent research-project service backed by local SQLite."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from kg_engine.domain.product import AuditEvent
from kg_engine.domain.product import Constraint
from kg_engine.domain.product import ConstraintStrength
from kg_engine.domain.product import HypothesisRun
from kg_engine.domain.product import ExpertReview
from kg_engine.domain.product import ExperimentOutcome
from kg_engine.domain.product import ProjectValidation
from kg_engine.domain.product import ResearchProject
from kg_engine.domain.product import ResearchProjectCreate
from kg_engine.domain.models import HypothesisScore
from kg_engine.domain.product import utc_now
from kg_engine.services.metrics import ExpertFeedbackEntry
from kg_engine.services.metrics import recalibrate_ranking_weights


class ProjectNotFoundError(LookupError):
    """Raised when a project identifier does not exist."""


class ResearchProjectService:
    """Store project state and immutable audit events transactionally."""

    def __init__(self, database_path: str | Path) -> None:
        self._path = Path(database_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def create_project(
        self,
        request: ResearchProjectCreate,
        *,
        actor: str = "system",
    ) -> ResearchProject:
        project = ResearchProject(**request.model_dump())
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO research_projects (id, payload) VALUES (?, ?)",
                (project.id, project.model_dump_json()),
            )
            self._insert_audit(
                connection,
                AuditEvent(actor=actor, action="project.created", project_id=project.id),
            )
        return project

    def list_projects(self) -> list[ResearchProject]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM research_projects ORDER BY rowid"
            ).fetchall()
        return [ResearchProject.model_validate_json(row[0]) for row in rows]

    def get_project(self, project_id: str) -> ResearchProject:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM research_projects WHERE id = ?", (project_id,)
            ).fetchone()
        if row is None:
            raise ProjectNotFoundError(project_id)
        return ResearchProject.model_validate_json(row[0])

    def update_project(
        self,
        project_id: str,
        changes: dict[str, Any],
        *,
        actor: str = "system",
    ) -> ResearchProject:
        current = self.get_project(project_id)
        immutable = {"id", "created_at", "constraints", "version"}
        safe_changes = {key: value for key, value in changes.items() if key not in immutable}
        updated = current.model_copy(
            update={**safe_changes, "version": current.version + 1, "updated_at": utc_now()}
        )
        updated = ResearchProject.model_validate(updated.model_dump())
        self._save(updated, actor=actor, action="project.updated")
        return updated

    def delete_project(self, project_id: str, *, actor: str = "system") -> None:
        self.get_project(project_id)
        with self._connect() as connection:
            connection.execute("DELETE FROM research_projects WHERE id = ?", (project_id,))
            self._insert_audit(
                connection,
                AuditEvent(actor=actor, action="project.deleted", project_id=project_id),
            )

    def add_constraint(
        self,
        project_id: str,
        constraint: Constraint,
        *,
        actor: str = "system",
    ) -> ResearchProject:
        project = self.get_project(project_id)
        updated = project.model_copy(
            update={
                "constraints": [*project.constraints, constraint],
                "version": project.version + 1,
                "updated_at": utc_now(),
            }
        )
        self._save(updated, actor=actor, action="constraint.added")
        return updated

    def validate_project(self, project_id: str) -> ProjectValidation:
        project = self.get_project(project_id)
        blockers = [
            item
            for item in project.constraints
            if item.strength == ConstraintStrength.HARD and item.satisfied is not True
        ]
        warnings = []
        if not project.source_ids:
            warnings.append("No source scope selected; generation will use all sources")
        return ProjectValidation(
            valid=not blockers,
            blocking_constraints=blockers,
            warnings=warnings,
        )

    def list_audit_events(self, *, project_id: str | None = None) -> list[AuditEvent]:
        query = "SELECT payload FROM audit_events"
        parameters: tuple[str, ...] = ()
        if project_id is not None:
            query += " WHERE project_id = ?"
            parameters = (project_id,)
        query += " ORDER BY rowid"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [AuditEvent.model_validate_json(row[0]) for row in rows]

    def save_hypothesis_run(
        self,
        run: HypothesisRun,
        *,
        actor: str = "system",
    ) -> HypothesisRun:
        self.get_project(run.project_id)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO hypothesis_runs (id, project_id, payload) VALUES (?, ?, ?)",
                (run.id, run.project_id, run.model_dump_json()),
            )
            self._insert_audit(
                connection,
                AuditEvent(
                    actor=actor,
                    action="hypothesis_run.created",
                    project_id=run.project_id,
                    payload={"run_id": run.id},
                ),
            )
        return run

    def get_hypothesis_run(self, run_id: str) -> HypothesisRun:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM hypothesis_runs WHERE id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise ProjectNotFoundError(run_id)
        return HypothesisRun.model_validate_json(row[0])

    def save_expert_review(self, review: ExpertReview) -> ExpertReview:
        run = self.get_hypothesis_run(review.run_id)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO expert_reviews (id, run_id, payload) VALUES (?, ?, ?)",
                (review.id, review.run_id, review.model_dump_json()),
            )
            self._insert_audit(
                connection,
                AuditEvent(
                    actor=review.expert_id,
                    action="expert_review.created",
                    project_id=run.project_id,
                    payload={"run_id": run.id, "review_id": review.id},
                ),
            )
        return review

    def list_expert_reviews(self, *, run_id: str) -> list[ExpertReview]:
        self.get_hypothesis_run(run_id)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM expert_reviews WHERE run_id = ? ORDER BY rowid",
                (run_id,),
            ).fetchall()
        return [ExpertReview.model_validate_json(row[0]) for row in rows]

    def save_experiment_outcome(self, outcome: ExperimentOutcome) -> ExperimentOutcome:
        review = self.get_expert_review(outcome.review_id)
        run = self.get_hypothesis_run(review.run_id)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO experiment_outcomes (id, review_id, payload) VALUES (?, ?, ?)",
                (outcome.id, outcome.review_id, outcome.model_dump_json()),
            )
            self._insert_audit(
                connection,
                AuditEvent(
                    actor="system",
                    action="experiment_outcome.created",
                    project_id=run.project_id,
                    payload={
                        "run_id": run.id,
                        "review_id": review.id,
                        "outcome_id": outcome.id,
                        "confirmed": outcome.confirmed,
                    },
                ),
            )
        return outcome

    def get_expert_review(self, review_id: str) -> ExpertReview:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM expert_reviews WHERE id = ?", (review_id,)
            ).fetchone()
        if row is None:
            raise ProjectNotFoundError(review_id)
        return ExpertReview.model_validate_json(row[0])

    def list_experiment_outcomes(
        self,
        *,
        review_id: str | None = None,
        run_id: str | None = None,
    ) -> list[ExperimentOutcome]:
        if review_id is not None:
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT payload FROM experiment_outcomes WHERE review_id = ? ORDER BY rowid",
                    (review_id,),
                ).fetchall()
            return [ExperimentOutcome.model_validate_json(row[0]) for row in rows]
        if run_id is not None:
            self.get_hypothesis_run(run_id)
            review_ids = [review.id for review in self.list_expert_reviews(run_id=run_id)]
            if not review_ids:
                return []
            placeholders = ",".join("?" for _ in review_ids)
            with self._connect() as connection:
                rows = connection.execute(
                    f"SELECT payload FROM experiment_outcomes WHERE review_id IN ({placeholders}) ORDER BY rowid",
                    tuple(review_ids),
                ).fetchall()
            return [ExperimentOutcome.model_validate_json(row[0]) for row in rows]
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM experiment_outcomes ORDER BY rowid"
            ).fetchall()
        return [ExperimentOutcome.model_validate_json(row[0]) for row in rows]

    def derive_feedback_ranking_weights(self, project_id: str) -> dict[str, float]:
        """Calibrate default ranking weights from prior reviews and outcomes."""
        self.get_project(project_id)
        with self._connect() as connection:
            run_rows = connection.execute(
                "SELECT payload FROM hypothesis_runs WHERE project_id = ? ORDER BY rowid",
                (project_id,),
            ).fetchall()
        entries: list[ExpertFeedbackEntry] = []
        for run_row in run_rows:
            run = HypothesisRun.model_validate_json(run_row[0])
            hypotheses = {
                item.get("id"): item
                for item in run.result.get("hypotheses", [])
                if isinstance(item, dict) and item.get("id")
            }
            reviews = self.list_expert_reviews(run_id=run.id)
            outcomes_by_review = {
                outcome.review_id: outcome
                for outcome in self.list_experiment_outcomes(run_id=run.id)
            }
            for review in reviews:
                payload = hypotheses.get(review.hypothesis_id)
                if not payload or "score" not in payload:
                    continue
                try:
                    score = HypothesisScore.model_validate(payload["score"])
                except Exception:
                    continue
                outcome = outcomes_by_review.get(review.id)
                rating = review.rating
                if outcome is not None:
                    rating = 5 if outcome.confirmed else 1
                entries.append(
                    ExpertFeedbackEntry(
                        hypothesis_id=review.hypothesis_id,
                        rating=rating,
                        score=score,
                        expert_id=review.expert_id,
                        comment=review.comment,
                    )
                )
        return recalibrate_ranking_weights(entries).model_dump(mode="json")

    def _save(self, project: ResearchProject, *, actor: str, action: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE research_projects SET payload = ? WHERE id = ?",
                (project.model_dump_json(), project.id),
            )
            self._insert_audit(
                connection,
                AuditEvent(actor=actor, action=action, project_id=project.id),
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS research_projects "
                "(id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS audit_events "
                "(id TEXT PRIMARY KEY, project_id TEXT, payload TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS hypothesis_runs "
                "(id TEXT PRIMARY KEY, project_id TEXT NOT NULL, payload TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS expert_reviews "
                "(id TEXT PRIMARY KEY, run_id TEXT NOT NULL, payload TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS experiment_outcomes "
                "(id TEXT PRIMARY KEY, review_id TEXT NOT NULL, payload TEXT NOT NULL)"
            )

    @staticmethod
    def _insert_audit(connection: sqlite3.Connection, event: AuditEvent) -> None:
        connection.execute(
            "INSERT INTO audit_events (id, project_id, payload) VALUES (?, ?, ?)",
            (event.id, event.project_id, event.model_dump_json()),
        )
