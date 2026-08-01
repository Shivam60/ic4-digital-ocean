from typing import Annotated

import httpx
from fastapi import Depends, Request

from app.core.config import Settings, get_settings


def get_http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client


SettingsDep = Annotated[Settings, Depends(get_settings)]
HttpClientDep = Annotated[httpx.AsyncClient, Depends(get_http_client)]
