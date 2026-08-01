from typing import Annotated

import httpx
from fastapi import Depends, Request

from app.core.config import Settings, get_settings
from app.services.model_repository import ModelRepository


def get_http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client


def get_model_repository(request: Request) -> ModelRepository:
    return request.app.state.model_repository


SettingsDep = Annotated[Settings, Depends(get_settings)]
HttpClientDep = Annotated[httpx.AsyncClient, Depends(get_http_client)]
ModelRepositoryDep = Annotated[ModelRepository, Depends(get_model_repository)]
