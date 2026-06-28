# MiMo cleanup-runtime summary

## Scope

Accepted from `mimo/20260627-cleanup-runtime`, with Codex review hardening:

- Cleaned the active public Materials KG environment example.
- Removed legacy donor brand fields from the main `Settings` model.
- Added a guard test for the active Materials KG surface.
- Kept old donor/legacy code excluded from the product entrypoints.

## Files Changed

| File | Change |
|------|--------|
| `.env.example` | Replaced with Materials KG core settings only. No legacy donor platform variables remain in the public example. |
| `kg_engine/config/settings.py` | Removed legacy donor platform fields from the main public `Settings` model. Extra env vars remain ignored via `extra="ignore"`. |
| `kg_engine/tests/test_no_cmw_in_core.py` | New guard test. It scans README, pyproject, `.env.example`, public API, settings, domain, repositories, services, ingestion, scripts, and focused Materials KG tests for legacy donor brand leakage. |

## Verification

Passed in the cleanup worktree after Codex hardening:

```powershell
rg -n -i --hidden "cmw|comindware|kb\.comindware\.ru" .env.example README.md pyproject.toml kg_engine\api\materials_core.py kg_engine\config\settings.py kg_engine\domain kg_engine\repositories kg_engine\services kg_engine\ingestion kg_engine\scripts\ingest_materials_kg.py kg_engine\scripts\run_materials_api.py kg_engine\tests\test_materials_kg_core.py kg_engine\tests\test_materials_api_smoke.py kg_engine\tests\test_repository_factory.py kg_engine\tests\test_no_cmw_in_core.py
# no matches

python -c "import importlib.util; spec=importlib.util.spec_from_file_location('guard','kg_engine/tests/test_no_cmw_in_core.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); m.test_active_files_free_of_legacy_brand_references(); print('guard ok')"
# guard ok

python -c "from kg_engine.config import settings; print(settings.materials_api_title); print(hasattr(settings, 'cmw_api_key'))"
# Materials KG Core API
# False

python kg_engine\scripts\ingest_materials_kg.py --reference data\reference.json --experiments data\experiments.json --documents data\documents.json
# Reference ingestion: {'entities': 17, 'coverage_rules': 3}
# Experiment ingestion: {'experiments': 5, 'observations': 19, 'decision_traces': 5}
# Document ingestion: {'documents': 2, 'decision_traces': 4}
```

MiMo also ran these successfully before Codex hardening:

```powershell
python -m pytest kg_engine/tests/test_materials_kg_core.py -q       # 5 passed
python -m pytest kg_engine/tests/test_materials_api_smoke.py -q     # 1 passed
python -m pytest kg_engine/tests/test_repository_factory.py -q      # 5 passed
```

In the Codex shell, `python -m pytest ...` reports `No module named pytest`, so the post-hardening pytest rerun was limited by the local environment. `ruff` is not available as a command in the Codex shell; `python -m ruff` in MiMo found pre-existing style issues across active and legacy code.

## Remaining Legacy Occurrences

Legacy donor references remain in explicitly excluded old paths such as `kg_engine/agent`, old `kg_engine/api/app.py`, `kg_engine/llm`, `kg_engine/tools`, `kg_engine/utils`, archived MiMo logs, and root donor folders. They are not imported by the Materials KG core API, ingestion script, domain, repository, or service layer.
