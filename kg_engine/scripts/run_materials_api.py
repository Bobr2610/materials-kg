"""Run the standalone FastAPI app for the graph-first materials KG core."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from kg_engine.api.materials_core import create_materials_app
from kg_engine.config.settings import settings


def main() -> None:
    import uvicorn

    app = create_materials_app(ensure_schema=settings.materials_api_ensure_schema)
    uvicorn.run(
        app,
        host=settings.materials_api_host,
        port=settings.materials_api_port,
        timeout_graceful_shutdown=3,
    )


if __name__ == "__main__":
    main()
