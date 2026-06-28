# MiMo unblock-core summary

## Scope

Accepted from `mimo/20260627-unblock-core`:

- Made `kg_engine.config.settings` safe to import without legacy CMW/agent environment variables.
- Kept legacy model-registry schemas lazy in `kg_engine.config.__init__` so the new core does not require YAML at settings import time.
- Added package metadata and dev dependencies to `pyproject.toml`.
- Added sample Materials KG fixtures in `data/`.
- Updated README quick-start commands for editable install, core API startup, fixture ingestion, and focused tests.

## Verification

Passed in the MiMo worktree before copying to main:

```powershell
python -c "from kg_engine.config import settings; print(settings.materials_api_title)"
python -c "from kg_engine.config.settings import settings; print(settings.materials_api_title)"
python -c "import tomllib; tomllib.load(open('pyproject.toml','rb')); print('pyproject ok')"
python kg_engine\scripts\ingest_materials_kg.py --reference data\reference.json --experiments data\experiments.json --documents data\documents.json
```

Known environment limitation during this run:

- Current Python environment does not have `pytest`, `ruff`, `fastapi`, or `pydantic-settings` installed, so full smoke/API/test commands require `pip install -e ".[dev]"`.
