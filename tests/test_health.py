import httpx

from app import __version__
from app.core.config import Settings


async def test_health_returns_ok(client: httpx.AsyncClient, settings: Settings) -> None:
    response = await client.get(f"{settings.api_prefix}/health")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {
        "status": "ok",
        "app_name": settings.app_name,
        "version": __version__,
        "environment": settings.environment,
    }
