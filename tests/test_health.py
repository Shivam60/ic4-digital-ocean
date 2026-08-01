import httpx


async def test_health_returns_ok(client: httpx.AsyncClient, settings) -> None:
    response = await client.get(f"{settings.api_v1_prefix}/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app_name"] == settings.app_name
