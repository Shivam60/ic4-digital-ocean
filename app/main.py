from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api.router import api_router
from app.core.config import get_settings
from app.core.errors import (
    GatewayConfigError,
    UpstreamError,
    UpstreamProtocolError,
)
from app.services.llm.ollama import OllamaService
from app.services.model_repository import ModelNotRoutableError, ModelRepository


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    timeout = httpx.Timeout(
        connect=settings.upstream_connect_timeout_seconds,
        read=None,
        write=settings.upstream_write_timeout_seconds,
        pool=settings.upstream_connect_timeout_seconds,
    )
    async with httpx.AsyncClient(timeout=timeout) as client:
        app.state.http_client = client
        app.state.model_repository = ModelRepository(
            services=[OllamaService(client, settings.ollama_base_url)],
            routes=settings.model_routes,
            default_provider=settings.default_provider,
        )
        yield


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        debug=settings.debug,
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix=settings.api_prefix)

    @app.exception_handler(GatewayConfigError)
    async def config_error_handler(_: Request, exc: GatewayConfigError) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "type": "gateway_configuration_error",
                    "message": str(exc),
                }
            },
        )

    @app.exception_handler(ModelNotRoutableError)
    async def model_not_routable_handler(
        _: Request, exc: ModelNotRoutableError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "type": "model_not_routable",
                    "model": exc.model,
                    "message": str(exc),
                }
            },
        )

    @app.exception_handler(UpstreamError)
    async def upstream_error_handler(_: Request, exc: UpstreamError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "type": "upstream_error",
                    "provider": exc.provider,
                    "message": exc.detail,
                }
            },
        )

    @app.exception_handler(UpstreamProtocolError)
    async def upstream_protocol_error_handler(
        _: Request, exc: UpstreamProtocolError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=502,
            content={
                "error": {
                    "type": "upstream_protocol_error",
                    "provider": exc.provider,
                    "message": exc.detail,
                }
            },
        )

    return app


app = create_app()
