from collections.abc import AsyncIterator

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI

from app.core.config import get_settings
from app.main import create_app


@pytest.fixture
def settings():
    return get_settings()


@pytest.fixture
async def app() -> AsyncIterator[FastAPI]:
    # LifespanManager runs startup/shutdown, which ASGITransport skips on its own.
    application = create_app()
    async with LifespanManager(application):
        yield application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as async_client:
        yield async_client
