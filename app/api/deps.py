from typing import Annotated

import httpx
from fastapi import Depends, Request

from app.core.config import Settings, get_settings
from app.services.items import ItemRepository


def get_item_repository(request: Request) -> ItemRepository:
    return request.app.state.item_repository


def get_http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client


SettingsDep = Annotated[Settings, Depends(get_settings)]
ItemRepositoryDep = Annotated[ItemRepository, Depends(get_item_repository)]
HttpClientDep = Annotated[httpx.AsyncClient, Depends(get_http_client)]
