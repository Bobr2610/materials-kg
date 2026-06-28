[0m
> build · mimo-auto
[0m
[0m⚙ [0mmemory Memory search: 0 results
[0m⚙ [0mmemory Memory search: 0 results
[0m⚙ [0mhistory History search: 2 matches
I don't have any prior context about Postgres repository hardening in this project. Let me explore the codebase to understand the current Postgres
[0m→ [0mRead .
[0m✱ [0mGlob "**/*postgres*"[90m 2 matches[0m
[0m✱ [0mGlob "**/*pg*"[90m 1 match[0m
[0m✱ [0mGlob "**/*sql*"[90m 0 matches[0m
Let me explore the codebase to understand the current state and what "Postgres Repository Hardening" entails.
[0m✱ [0mGlob "**/*database*"[90m 0 matches[0m
[0m→ [0mRead docs\mimo-prompts\graph-first-core\02_postgres_repository_hardening.md
Found the prompt file and current implementation. Let me read both.
[0m→ [0mRead kg_engine\repositories\postgres.py
[0m→ [0mRead kg_engine\repositories\protocols.py
[0m→ [0mRead kg_engine\repositories\memory.py
[0m→ [0mRead kg_engine\domain\models.py
[0m→ [0mRead kg_engine\domain\resolution.py
Let me read the remaining files referenced in the prompt to understand the full context.
[0m→ [0mRead kg_engine\services\materials_kg.py
[0m→ [0mRead kg_engine\tests\test_materials_kg_core.py
[0m→ [0mRead kg_engine\tests\conftest.py
[0m✗ [0mtask failed
[91m[1mError: [0mInvalid arguments for the task tool:
✖ Unrecognized key: "summary"
✖ Invalid input: expected object, received string
  → at operation
Now I have a clear picture. Let me create a task to track this work and then implement the hardening.
[0m✗ [0mtask failed
[91m[1mError: [0mInvalid arguments for the task tool:
✖ Unrecognized key: "summary"
✖ Invalid input: expected object, received string
  → at operation
[0m⚙ [0mtask Task created: T1
[0m⚙ [0mtask Task T1: in_progress
I've analyzed the codebase. Now implementing the hardening directly.

**6 failure modes identified:**
1. No rollback on cursor exceptions (half-applied writes)
2. `aliases` replaced instead of merged on re-ingestion
3. `source_refs` replaced instead of merged
4. `evidence_ids` replaced instead of merged on re-upsert
5. Fragile enum decoding (`hasattr(row, "value")` instead of explicit cast)
6. Non-deterministic ordering on 4 list methods
[0m
[0m← [0mEdit kg_engine\repositories\postgres.py
Index: C:\MAI\Nornicel\Code\materials-kg\kg_engine\repositories\postgres.py
===================================================================
--- C:\MAI\Nornicel\Code\materials-kg\kg_engine\repositories\postgres.py
+++ C:\MAI\Nornicel\Code\materials-kg\kg_engine\repositories\postgres.py
@@ -3,8 +3,10 @@
 from __future__ import annotations
 
 import json
 import logging
+from datetime import UTC
+from datetime import datetime
 from typing import Any
 
 from kg_engine.domain.models import CoverageRuleInput
 from kg_engine.domain.models import DecisionTrace
@@ -14,13 +16,30 @@
 from kg_engine.domain.models import Observation
 from kg_engine.domain.models import Relation
 from kg_engine.domain.models import RelationType
 from kg_engine.domain.models import SearchTextUnit
+from kg_engine.domain.models import SourceKind
 from kg_engine.domain.models import SourceSpan
 from kg_engine.domain.resolution import normalize_name
 
 logger = logging.getLogger(__name__)
 
+
+def _ensure_datetime(value: Any) -> datetime | None:
+    """Coerce a database value to an aware UTC datetime, or None."""
+    if value is None:
+        return None
+    if isinstance(value, datetime):
+        if value.tzinfo is None:
+            return value.replace(tzinfo=UTC)
+        return value
+    if isinstance(value, str):
+        parsed = datetime.fromisoformat(value)
+        if parsed.tzinfo is None:
+            return parsed.replace(tzinfo=UTC)
+        return parsed
+    return value
+
 POSTGRES_SCHEMA_SQL = """
 CREATE EXTENSION IF NOT EXISTS vector;
 
 CREATE TABLE IF NOT EXISTS kg_entities (
System.Management.Automation.RemoteException
[0m
[0m← [0mEdit kg_engine\repositories\postgres.py
Index: C:\MAI\Nornicel\Code\materials-kg\kg_engine\repositories\postgres.py
===================================================================
--- C:\MAI\Nornicel\Code\materials-kg\kg_engine\repositories\postgres.py
+++ C:\MAI\Nornicel\Code\materials-kg\kg_engine\repositories\postgres.py
@@ -158,11 +158,23 @@
     VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s, %s)
     ON CONFLICT (id) DO UPDATE SET
         canonical_name = EXCLUDED.canonical_name,
         normalized_name = EXCLUDED.normalized_name,
-        aliases = EXCLUDED.aliases,
+        aliases = (
+            SELECT jsonb_agg(DISTINCT elem)
+            FROM jsonb_array_elements(
+                COALESCE(kg_entities.aliases, '[]'::jsonb)
+                || COALESCE(EXCLUDED.aliases, '[]'::jsonb)
+            ) AS elem
+        ),
         properties = kg_entities.properties || EXCLUDED.properties,
-        source_refs = EXCLUDED.source_refs,
+        source_refs = (
+            SELECT jsonb_agg(DISTINCT elem)
+            FROM jsonb_array_elements(
+                COALESCE(kg_entities.source_refs, '[]'::jsonb)
+                || COALESCE(EXCLUDED.source_refs, '[]'::jsonb)
+            ) AS elem
+        ),
         confidence = GREATEST(kg_entities.confidence, EXCLUDED.confidence),
         updated_at = EXCLUDED.updated_at
     """
     payload = (
@@ -176,31 +188,35 @@
         entity.confidence,
         entity.created_at,
         entity.updated_at,
     )
-    with self._connection.cursor() as cursor:
-        cursor.execute(query, payload)
-        cursor.execute(
-            "DELETE FROM kg_entity_aliases WHERE entity_id = %s",
-            (entity.id,),
-        )
-        aliases = [entity.canonical_name, *entity.aliases]
-        for alias in aliases:
+    try:
+        with self._connection.cursor() as cursor:
+            cursor.execute(query, payload)
             cursor.execute(
-                """
-                INSERT INTO kg_entity_aliases(entity_id, kind, alias, normalized_alias)
-                VALUES (%s, %s, %s, %s)
-                ON CONFLICT (kind, normalized_alias) DO UPDATE
-                SET entity_id = EXCLUDED.entity_id, alias = EXCLUDED.alias
-                """,
-                (
-                    entity.id,
-                    entity.kind.value,
-                    alias,
-                    normalize_name(alias),
-                ),
+                "DELETE FROM kg_entity_aliases WHERE entity_id = %s",
+                (entity.id,),
             )
-    self._connection.commit()
+            aliases = [entity.canonical_name, *entity.aliases]
+            for alias in aliases:
+                cursor.execute(
+                    """
+                    INSERT INTO kg_entity_aliases(entity_id, kind, alias, normalized_alias)
+                    VALUES (%s, %s, %s, %s)
+                    ON CONFLICT (kind, normalized_alias) DO UPDATE
+                    SET entity_id = EXCLUDED.entity_id, alias = EXCLUDED.alias
+                    """,
+                    (
+                        entity.id,
+                        entity.kind.value,
+                        alias,
+                        normalize_name(alias),
+                    ),
+                )
+        self._connection.commit()
+    except Exception:
+        self._connection.rollback()
+        raise
     return entity
 
 def get_entity(self, entity_id: str) -> Entity | None:
     with self._connection.cursor() as cursor:
System.Management.Automation.RemoteException
[0m
Now fix `upsert_entity` — merge aliases/source_refs and add rollback:
Fix `_row_to_entity` to use `_ensure_datetime`:
[0m← [0mEdit kg_engine\repositories\postgres.py
Index: C:\MAI\Nornicel\Code\materials-kg\kg_engine\repositories\postgres.py
===================================================================
--- C:\MAI\Nornicel\Code\materials-kg\kg_engine\repositories\postgres.py
+++ C:\MAI\Nornicel\Code\materials-kg\kg_engine\repositories\postgres.py
@@ -596,10 +596,10 @@
         aliases=row[4] or [],
         properties=row[5] or {},
         source_refs=row[6] or [],
         confidence=row[7],
-        created_at=row[8],
-        updated_at=row[9],
+        created_at=_ensure_datetime(row[8]) or datetime.now(UTC),
+        updated_at=_ensure_datetime(row[9]) or datetime.now(UTC),
     )
 
 def _row_to_evidence(self, row: Any) -> Evidence:
     return Evidence(
System.Management.Automation.RemoteException
[0m
Fix `_row_to_evidence` — explicit `SourceKind` cast and datetime coercion:
[0m← [0mEdit kg_engine\repositories\postgres.py
Index: C:\MAI\Nornicel\Code\materials-kg\kg_engine\repositories\postgres.py
===================================================================
--- C:\MAI\Nornicel\Code\materials-kg\kg_engine\repositories\postgres.py
+++ C:\MAI\Nornicel\Code\materials-kg\kg_engine\repositories\postgres.py
@@ -601,17 +601,24 @@
         updated_at=_ensure_datetime(row[9]) or datetime.now(UTC),
     )
 
 def _row_to_evidence(self, row: Any) -> Evidence:
+    raw_kind = row[1]
+    if isinstance(raw_kind, SourceKind):
+        source_kind = raw_kind
+    elif isinstance(raw_kind, str):
+        source_kind = SourceKind(raw_kind)
+    else:
+        source_kind = SourceKind(str(raw_kind))
     return Evidence(
         id=row[0],
-        source_kind=row[1] if hasattr(row[1], "value") else row[1],
+        source_kind=source_kind,
         source_id=row[2],
         span=SourceSpan(**(row[3] or {})),
         extraction_method=row[4],
         confidence=row[5],
         version=row[6],
-        recorded_at=row[7],
+        recorded_at=_ensure_datetime(row[7]) or datetime.now(UTC),
         metadata=row[8] or {},
     )
 
 def _row_to_relation(self, row: Any) -> Relation:
System.Management.Automation.RemoteException
[0m
Add rollback to `upsert_evidence`:
[0m← [0mEdit kg_engine\repositories\postgres.py
Index: C:\MAI\Nornicel\Code\materials-kg\kg_engine\repositories\postgres.py
===================================================================
--- C:\MAI\Nornicel\Code\materials-kg\kg_engine\repositories\postgres.py
+++ C:\MAI\Nornicel\Code\materials-kg\kg_engine\repositories\postgres.py
@@ -257,36 +257,40 @@
     entities = self.find_entities(kind=kind, name=raw_name)
     return entities[0] if entities else None
 
 def upsert_evidence(self, evidence: Evidence) -> Evidence:
-    with self._connection.cursor() as cursor:
-        cursor.execute(
-            """
-            INSERT INTO kg_evidence (
-                id, source_kind, source_id, span, extraction_method,
-                confidence, version, recorded_at, metadata
+    try:
+        with self._connection.cursor() as cursor:
+            cursor.execute(
+                """
+                INSERT INTO kg_evidence (
+                    id, source_kind, source_id, span, extraction_method,
+                    confidence, version, recorded_at, metadata
+                )
+                VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s::jsonb)
+                ON CONFLICT (id) DO UPDATE SET
+                    span = EXCLUDED.span,
+                    extraction_method = EXCLUDED.extraction_method,
+                    confidence = GREATEST(kg_evidence.confidence, EXCLUDED.confidence),
+                    version = EXCLUDED.version,
+                    metadata = kg_evidence.metadata || EXCLUDED.metadata
+                """,
+                (
+                    evidence.id,
+                    evidence.source_kind.value,
+                    evidence.source_id,
+                    json.dumps(evidence.span.model_dump()),
+                    evidence.extraction_method,
+                    evidence.confidence,
+                    evidence.version,
+                    evidence.recorded_at,
+                    json.dumps(evidence.metadata),
+                ),
             )
-            VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s::jsonb)
-            ON CONFLICT (id) DO UPDATE SET
-                span = EXCLUDED.span,
-                extraction_method = EXCLUDED.extraction_method,
-                confidence = GREATEST(kg_evidence.confidence, EXCLUDED.confidence),
-                version = EXCLUDED.version,
-                metadata = kg_evidence.metadata || EXCLUDED.metadata
-            """,
-            (
-                evidence.id,
-                evidence.source_kind.value,
-                evidence.source_id,
-                json.dumps(evidence.span.model_dump()),
-                evidence.extraction_method,
-                evidence.confidence,
-                evidence.version,
-                evidence.recorded_at,
-                json.dumps(evidence.metadata),
-            ),
-        )
-    self._connection.commit()
+        self._connection.commit()
+    except Exception:
+        self._connection.rollback()
+        raise
     return evidence
 
 def get_evidence(self, evidence_id: str) -> Evidence | None:
     with self._connection.cursor() as cursor:
System.Management.Automation.RemoteException
[0m
Add rollback + merge `evidence_ids` in `upsert_relation`:
[0m← [0mEdit kg_engine\repositories\postgres.py
Index: C:\MAI\Nornicel\Code\materials-kg\kg_engine\repositories\postgres.py
===================================================================
--- C:\MAI\Nornicel\Code\materials-kg\kg_engine\repositories\postgres.py
+++ C:\MAI\Nornicel\Code\materials-kg\kg_engine\repositories\postgres.py
@@ -309,35 +309,45 @@
         rows = cursor.fetchall()
     return [self._row_to_evidence(row) for row in rows]
 
 def upsert_relation(self, relation: Relation) -> Relation:
-    with self._connection.cursor() as cursor:
-        cursor.execute(
-            """
-            INSERT INTO kg_relations (
-                id, relation_type, source_entity_id, target_entity_id,
-                evidence_ids, properties, confidence, created_at, updated_at
+    try:
+        with self._connection.cursor() as cursor:
+            cursor.execute(
+                """
+                INSERT INTO kg_relations (
+                    id, relation_type, source_entity_id, target_entity_id,
+                    evidence_ids, properties, confidence, created_at, updated_at
+                )
+                VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s)
+                ON CONFLICT (id) DO UPDATE SET
+                    evidence_ids = (
+                        SELECT jsonb_agg(DISTINCT elem)
+                        FROM jsonb_array_elements(
+                            COALESCE(kg_relations.evidence_ids, '[]'::jsonb)
+                            || COALESCE(EXCLUDED.evidence_ids, '[]'::jsonb)
+                        ) AS elem
+                    ),
+                    properties = kg_relations.properties || EXCLUDED.properties,
+                    confidence = GREATEST(kg_relations.confidence, EXCLUDED.confidence),
+                    updated_at = EXCLUDED.updated_at
+                """,
+                (
+                    relation.id,
+                    relation.relation_type.value,
+                    relation.source_entity_id,
+                    relation.target_entity_id,
+                    json.dumps(relation.evidence_ids),
+                    json.dumps(relation.properties),
+                    relation.confidence,
+                    relation.created_at,
+                    relation.updated_at,
+                ),
             )
-            VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s)
-            ON CONFLICT (id) DO UPDATE SET
-                evidence_ids = EXCLUDED.evidence_ids,
-                properties = kg_relations.properties || EXCLUDED.properties,
-                confidence = GREATEST(kg_relations.confidence, EXCLUDED.confidence),
-                updated_at = EXCLUDED.updated_at
-            """,
-            (
-                relation.id,
-                relation.relation_type.value,
-                relation.source_entity_id,
-                relation.target_entity_id,
-                json.dumps(relation.evidence_ids),
-                json.dumps(relation.properties),
-                relation.confidence,
-                relation.created_at,
-                relation.updated_at,
-            ),
-        )
-    self._connection.commit()
+        self._connection.commit()
+    except Exception:
+        self._connection.rollback()
+        raise
     return relation
 
 def list_relations(
     self,
System.Management.Automation.RemoteException
[0m
Add rollback to `upsert_observation`:
[0m← [0mEdit kg_engine\repositories\postgres.py
Index: C:\MAI\Nornicel\Code\materials-kg\kg_engine\repositories\postgres.py
===================================================================
--- C:\MAI\Nornicel\Code\materials-kg\kg_engine\repositories\postgres.py
+++ C:\MAI\Nornicel\Code\materials-kg\kg_engine\repositories\postgres.py
@@ -369,43 +369,47 @@
         rows = cursor.fetchall()
     return [self._row_to_relation(row) for row in rows]
 
 def upsert_observation(self, observation: Observation) -> Observation:
-    with self._connection.cursor() as cursor:
-        cursor.execute(
-            """
-            INSERT INTO kg_observations (
-                id, material_id, property_id, experiment_id, mode_id,
-                value, unit, comparator, evidence_id, confidence,
-                observed_at, metadata
-            )
-            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
-            ON CONFLICT (id) DO UPDATE SET
-                value = EXCLUDED.value,
-                unit = EXCLUDED.unit,
-                comparator = EXCLUDED.comparator,
-                confidence = GREATEST(
-                    kg_observations.confidence, EXCLUDED.confidence
+    try:
+        with self._connection.cursor() as cursor:
+            cursor.execute(
+                """
+                INSERT INTO kg_observations (
+                    id, material_id, property_id, experiment_id, mode_id,
+                    value, unit, comparator, evidence_id, confidence,
+                    observed_at, metadata
+                )
+                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
+                ON CONFLICT (id) DO UPDATE SET
+                    value = EXCLUDED.value,
+                    unit = EXCLUDED.unit,
+                    comparator = EXCLUDED.comparator,
+                    confidence = GREATEST(
+                        kg_observations.confidence, EXCLUDED.confidence
+                    ),
+                    observed_at = EXCLUDED.observed_at,
+                    metadata = kg_observations.metadata || EXCLUDED.metadata
+                """,
+                (
+                    observation.id,
+                    observation.material_id,
+                    observation.property_id,
+                    observation.experiment_id,
+                    observation.mode_id,
+                    observation.value,
+                    observation.unit,
+                    observation.comparator,
+                    observation.evidence_id,
+                    observation.confidence,
+                    observation.observed_at,
+                    json.dumps(observation.metadata),
                 ),
-                observed_at = EXCLUDED.observed_at,
-                metadata = kg_observations.metadata || EXCLUDED.metadata
-            """,
-            (
-                observation.id,
-                observation.material_id,
-                observation.property_id,
-                observation.experiment_id,
-                observation.mode_id,
-                observation.value,
-                observation.unit,
-                observation.comparator,
-                observation.evidence_id,
-                observation.confidence,
-                observation.observed_at,
-                json.dumps(observation.metadata),
-            ),
-        )
-    self._connection.commit()
+            )
+        self._connection.commit()
+    except Exception:
+        self._connection.rollback()
+        raise
     return observation
 
 def list_observations(
     self,
System.Management.Automation.RemoteException
[0m
Add rollback to `upsert_decision_trace`:
[0m← [0mEdit kg_engine\repositories\postgres.py
Index: C:\MAI\Nornicel\Code\materials-kg\kg_engine\repositories\postgres.py
===================================================================
--- C:\MAI\Nornicel\Code\materials-kg\kg_engine\repositories\postgres.py
+++ C:\MAI\Nornicel\Code\materials-kg\kg_engine\repositories\postgres.py
@@ -439,48 +439,52 @@
         rows = cursor.fetchall()
     return [self._row_to_observation(row) for row in rows]
 
 def upsert_decision_trace(self, trace: DecisionTrace) -> DecisionTrace:
-    with self._connection.cursor() as cursor:
-        cursor.execute(
-            """
-            INSERT INTO kg_decision_traces (
-                id, summary, decision, entity_ids, experiment_id,
-                observation_ids, evidence_ids, changed_from_trace_id,
-                timestamp, confidence, metadata
-            )
-            VALUES (
-                %s, %s, %s, %s::jsonb, %s, %s::jsonb, %s::jsonb,
-                %s, %s, %s, %s::jsonb
-            )
-            ON CONFLICT (id) DO UPDATE SET
-                summary = EXCLUDED.summary,
-                decision = EXCLUDED.decision,
-                entity_ids = EXCLUDED.entity_ids,
-                observation_ids = EXCLUDED.observation_ids,
-                evidence_ids = EXCLUDED.evidence_ids,
-                changed_from_trace_id = EXCLUDED.changed_from_trace_id,
-                timestamp = EXCLUDED.timestamp,
-                confidence = GREATEST(
-                    kg_decision_traces.confidence, EXCLUDED.confidence
+    try:
+        with self._connection.cursor() as cursor:
+            cursor.execute(
+                """
+                INSERT INTO kg_decision_traces (
+                    id, summary, decision, entity_ids, experiment_id,
+                    observation_ids, evidence_ids, changed_from_trace_id,
+                    timestamp, confidence, metadata
+                )
+                VALUES (
+                    %s, %s, %s, %s::jsonb, %s, %s::jsonb, %s::jsonb,
+                    %s, %s, %s, %s::jsonb
+                )
+                ON CONFLICT (id) DO UPDATE SET
+                    summary = EXCLUDED.summary,
+                    decision = EXCLUDED.decision,
+                    entity_ids = EXCLUDED.entity_ids,
+                    observation_ids = EXCLUDED.observation_ids,
+                    evidence_ids = EXCLUDED.evidence_ids,
+                    changed_from_trace_id = EXCLUDED.changed_from_trace_id,
+                    timestamp = EXCLUDED.timestamp,
+                    confidence = GREATEST(
+                        kg_decision_traces.confidence, EXCLUDED.confidence
+                    ),
+                    metadata = kg_decision_traces.metadata || EXCLUDED.metadata
+                """,
+                (
+                    trace.id,
+                    trace.summary,
+                    trace.decision,
+                    json.dumps(trace.entity_ids),
+                    trace.experiment_id,
+                    json.dumps(trace.observation_ids),
+                    json.dumps(trace.evidence_ids),
+                    trace.changed_from_trace_id,
+                    trace.timestamp,
+                    trace.confidence,
+                    json.dumps(trace.metadata),
                 ),
-                metadata = kg_decision_traces.metadata || EXCLUDED.metadata
-            """,
-            (
-                trace.id,
-                trace.summary,
-                trace.decision,
-                json.dumps(trace.entity_ids),
-                trace.experiment_id,
-                json.dumps(trace.observation_ids),
-                json.dumps(trace.evidence_ids),
-                trace.changed_from_trace_id,
-                trace.timestamp,
-                trace.confidence,
-                json.dumps(trace.metadata),
-            ),
-        )
-    self._connection.commit()
+            )
+        self._connection.commit()
+    except Exception:
+        self._connection.rollback()
+        raise
     return trace
 
 def list_decision_traces(
     self,
System.Management.Automation.RemoteException
[0m
