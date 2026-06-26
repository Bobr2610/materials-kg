"""Server launch helpers for the Gradio/FastAPI app."""

from typing import Any

from kg_engine.config.settings import settings


def run_gradio_uvicorn(app: Any) -> None:
    """Run the mounted ASGI app with bounded graceful shutdown."""
    import uvicorn

    uvicorn.run(
        app,
        host=settings.gradio_server_name,
        port=settings.gradio_server_port,
        timeout_graceful_shutdown=3,
    )
