from collections.abc import Awaitable, Callable
from typing import Annotated

import httpx
from fastapi import Depends, Request

from app.core.config import Settings, get_settings
from app.core.errors import AuthenticationError, AuthorizationError
from app.core.security import ANONYMOUS, Principal, hash_api_key
from app.services.auth.base import ApiKeyStore
from app.services.model_router import ModelRouter

BEARER_PREFIX = "bearer "


def get_http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client


def get_model_router(request: Request) -> ModelRouter:
    return request.app.state.model_router


def get_api_key_store(request: Request) -> ApiKeyStore:
    return request.app.state.api_key_store


SettingsDep = Annotated[Settings, Depends(get_settings)]
HttpClientDep = Annotated[httpx.AsyncClient, Depends(get_http_client)]
ModelRouterDep = Annotated[ModelRouter, Depends(get_model_router)]
ApiKeyStoreDep = Annotated[ApiKeyStore, Depends(get_api_key_store)]


def _presented_key(request: Request) -> str:
    header = request.headers.get("authorization")
    if not header:
        raise AuthenticationError("missing Authorization header")
    if not header.lower().startswith(BEARER_PREFIX):
        raise AuthenticationError("Authorization header must use the Bearer scheme")
    key = header[len(BEARER_PREFIX) :].strip()
    if not key:
        raise AuthenticationError("Bearer token is empty")
    return key


async def authenticate(request: Request, store: ApiKeyStore) -> Principal:
    if not store.is_enforcing:
        return ANONYMOUS

    principal = await store.find(hash_api_key(_presented_key(request)))
    if principal is None:
        raise AuthenticationError("unknown API key")
    return principal


def require_scope(
    scope: str,
) -> Callable[[Request, ApiKeyStore], Awaitable[Principal]]:
    async def dependency(request: Request, store: ApiKeyStoreDep) -> Principal:
        principal = await authenticate(request, store)
        if not principal.may(scope):
            raise AuthorizationError(principal.label, scope)
        return principal

    return dependency
