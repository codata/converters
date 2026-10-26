"""FastAPI application factory for CDIF Multi-Format Converters API.

Run with: ``uvicorn cdif_converter.api.main:app --reload``
"""

from __future__ import annotations

from pathlib import Path
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from .. import __version__
from ..config import settings
from .routes import router
from .store import UploadStore


def create_app() -> FastAPI:
    app = FastAPI(
        title="CDIF Multi-Format Converters API",
        version=__version__,
        description=(
            "Converts between CDIF JSON-LD and various metadata formats: "
            "Croissant 1.1, SOSO (Science-on-Schema.org), W3C DCAT, DDI Codebook/CDI, "
            "RO-Crate 1.2, NASA UMM-C, and FAIR²."
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition"],
    )
    app.state.store = UploadStore(settings.work_dir, settings.upload_ttl_seconds)
    app.include_router(router)

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> Response:
        return Response(status_code=204)

    @app.get("/", include_in_schema=False)
    def root_docs() -> RedirectResponse:
        return RedirectResponse(url="/docs")

    return app


app = create_app()
