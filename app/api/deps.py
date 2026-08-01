from collections.abc import Callable
from typing import Annotated

import httpx
from fastapi import Depends, Request

from app.core.config import Settings, get_settings
from app.core.errors import AuthenticationError, AuthorizationError
from app.core.security import ANONYMOUS, Principal, hash_api_key
from app.services.model_repository import ModelRepository

BEARER_PREFIX = "bearer "


def get_http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client


def get_model_repository(request: Request) -> ModelRepository:
    return request.app.state.model_repository


SettingsDep = Annotated[Settings, Depends(get_settings)]
HttpClientDep = Annotated[httpx.AsyncClient, Depends(get_http_client)]
ModelRepositoryDep = Annotated[ModelRepository, Depends(get_model_repository)]


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


def authenticate(request: Request, settings: Settings) -> Principal:
    if not settings.api_keys:
        return ANONYMOUS

    presented = hash_api_key(_presented_key(request))
    for configured in settings.api_keys:
        if configured.key_hash == presented:
            return Principal(
                label=configured.label, scopes=frozenset(configured.scopes)
            )
    raise AuthenticationError("unknown API key")


def require_scope(scope: str) -> Callable[[Request, Settings], Principal]:
    def dependency(request: Request, settings: SettingsDep) -> Principal:
        principal = authenticate(request, settings)
        if not principal.may(scope):
            raise AuthorizationError(principal.label, scope)
        return principal

    return dependency
