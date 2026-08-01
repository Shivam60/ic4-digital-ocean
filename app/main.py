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
    AllProvidersFailedError,
    AuthenticationError,
    AuthorizationError,
    GatewayConfigError,
    UpstreamError,
    UpstreamProtocolError,
)
from app.services.llm.registry import build_services
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
            services=build_services(settings, client),
            routes=settings.model_routes,
            default_chain=settings.default_chain,
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

    @app.exception_handler(AuthenticationError)
    async def authentication_error_handler(
        _: Request, exc: AuthenticationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
            content={
                "error": {
                    "type": "authentication_error",
                    "message": str(exc),
                }
            },
        )

    @app.exception_handler(AuthorizationError)
    async def authorization_error_handler(
        _: Request, exc: AuthorizationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={
                "error": {
                    "type": "authorization_error",
                    "message": str(exc),
                    "required_scope": exc.scope,
                }
            },
        )

    @app.exception_handler(AllProvidersFailedError)
    async def all_providers_failed_handler(
        _: Request, exc: AllProvidersFailedError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "type": "all_providers_failed",
                    "model": exc.model,
                    "message": str(exc),
                    "attempts": [
                        {
                            "provider": attempt.provider,
                            "status_code": attempt.status_code,
                            "detail": attempt.detail,
                        }
                        for attempt in exc.attempts
                    ],
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
