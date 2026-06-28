# Prompt 03: Tests and Dependency Coverage for the New Core

You are working in the `materials-kg` repo. Tighten tests and dependency declarations around the new graph-first core so the core can be developed and validated without relying on the legacy RAG/agent stack.

## Goal

Close obvious test and dependency gaps for the new graph-first core: API smoke coverage, repository/service coverage, and minimal package requirements needed to run those paths cleanly.

## Files to inspect first

- `pyproject.toml`
- `requirements.txt`
- `requirements_agent.txt`
- `kg_engine/tests/test_materials_kg_core.py`
- `kg_engine/tests/test_materials_api_smoke.py`
- `kg_engine/tests/conftest.py`
- `kg_engine/repositories/factory.py`
- `kg_engine/api/materials_core.py`
- `kg_engine/services/materials_kg.py`

## Desired work

- Identify missing or mis-scoped dependencies needed specifically for the graph-first core and its tests.
- Add narrowly targeted tests for new-core behavior that is currently unprotected.
- Keep test setup lightweight: prefer in-memory repository tests and small fakes over heavyweight integration harnesses unless the value is obvious.
- If dependency declarations are overly legacy-centric, improve them in the smallest way that makes the graph-first core testable and installable.

## Specific gaps worth checking

- standalone FastAPI smoke path
- factory selection between memory and Postgres repository
- optional `psycopg` availability assumptions
- any missing test coverage for `query_related`, `query_decision_history`, `query_data_gaps`, or document ingestion
- whether new-core tests can run without Chroma, Gradio startup, model downloads, or agent dependencies

## Constraints

- Do not do a full dependency cleanup for the whole repo.
- Do not downgrade or broadly reshuffle ML/LLM packages unless a new-core test path is directly blocked by them.
- Do not delete legacy tests.
- Keep the patch focused on the graph-first core and the minimal support surface around it.

## Acceptance criteria

- There is an explicit, targeted verification path for the new core using pytest.
- The dependency files accurately cover the packages needed for that path.
- The new-core test suite does not require legacy runtime services to start.
- At least one added or updated test covers repository factory behavior.
- At least one added or updated test covers document ingestion or one of the less-covered query methods.

## Verification commands

```bash
ruff check pyproject.toml kg_engine/tests kg_engine/repositories/factory.py kg_engine/api/materials_core.py
python -m pytest kg_engine/tests/test_materials_kg_core.py kg_engine/tests/test_materials_api_smoke.py -v
python -m pytest -k "materials and not graph" kg_engine/tests -v
```

If you change dependency files, also note the exact install command that should work after your patch.

## What not to touch

- Do not refactor legacy graph tests in `kg_engine/tests/test_graph.py`.
- Do not modify `kg_engine/api/app.py` unless a tiny import-isolation fix is required for new-core tests.
- Do not introduce broad CI/CD changes.
- Do not rewrite docs instead of code.

## Output expected from you

- Implement the patch.
- State which dependency gaps were real vs false alarms.
- List the tests you added or strengthened.
- Report the verification commands you ran.
