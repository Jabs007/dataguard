"""FastAPI application factory, settings, and exception handlers.

The web layer is isolated from the CLI engine: it imports from
``dataguard.*`` but never from ``dataguard.cli``. The CLI continues to work
unchanged.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from web.upload import (
    UploadError,
    FileTooLargeError,
    InvalidExtensionError,
    EmptyFileError,
)

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"

# Resource limits for the local MVP. These are defaults, not universal
# guarantees, and are documented as such in Milestone 4.
MAX_ROWS = 100_000
MAX_COLUMNS = 1_000
AUDIT_TIMEOUT_SECONDS = 30


def create_app() -> FastAPI:
    """Build the FastAPI application with routes and error handlers."""
    app = FastAPI(title="DataGuard", version="0.1.0")

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    # Jinja2 auto-escapes by default for ``.html`` templates. CSV-derived values
    # are never marked with |safe.

    from web import routes  # noqa: WPS433 - local import avoids circularity
    routes.setup(app, templates)

    # Mount static files (CSS) so url_for('static', ...) resolves.
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # --- Exception handlers -------------------------------------------------
    # Every error path renders a plain error page with a user-friendly message.
    # Tracebacks and raw cell values never reach the client.

    @app.exception_handler(FileTooLargeError)
    async def _too_large(request: Request, exc: FileTooLargeError):
        return _error_page(request, str(exc), status_code=413, templates=templates)

    @app.exception_handler(InvalidExtensionError)
    async def _bad_extension(request: Request, exc: InvalidExtensionError):
        return _error_page(request, str(exc), status_code=400, templates=templates)

    @app.exception_handler(EmptyFileError)
    async def _empty_file(request: Request, exc: EmptyFileError):
        return _error_page(request, str(exc), status_code=400, templates=templates)

    @app.exception_handler(UploadError)
    async def _upload_error(request: Request, exc: UploadError):
        return _error_page(request, str(exc), status_code=400, templates=templates)

    @app.exception_handler(Exception)  # noqa: BLE001 - catch-all safety net
    async def _unhandled(request: Request, exc: Exception):
        return _error_page(
            request,
            "An unexpected error occurred. Please try again.",
            status_code=500,
            templates=templates,
        )

    return app


def _error_page(
    request: Request,
    message: str,
    status_code: int,
    templates: Jinja2Templates,
):
    return templates.TemplateResponse(
        request,
        "error.html",
        {"message": message},
        status_code=status_code,
    )
