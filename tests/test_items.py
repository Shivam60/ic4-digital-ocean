import asyncio

import httpx
import pytest


@pytest.fixture
def items_url(settings) -> str:
    return f"{settings.api_v1_prefix}/items"


async def test_create_and_get_item(client: httpx.AsyncClient, items_url: str) -> None:
    created = await client.post(
        items_url, json={"name": "Keyboard", "price": 79.99, "description": "Split 60%"}
    )
    assert created.status_code == 201
    item = created.json()
    assert item["id"] == 1
    assert item["in_stock"] is True

    fetched = await client.get(f"{items_url}/{item['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == item


async def test_list_items_is_paginated(
    client: httpx.AsyncClient, items_url: str
) -> None:
    for index in range(3):
        response = await client.post(
            items_url, json={"name": f"Item {index}", "price": index + 1}
        )
        assert response.status_code == 201

    page = await client.get(items_url, params={"limit": 2, "offset": 1})
    assert page.status_code == 200
    names = [item["name"] for item in page.json()]
    assert names == ["Item 1", "Item 2"]


async def test_patch_applies_partial_update(
    client: httpx.AsyncClient, items_url: str
) -> None:
    created = await client.post(items_url, json={"name": "Mouse", "price": 25.0})
    item_id = created.json()["id"]

    patched = await client.patch(f"{items_url}/{item_id}", json={"in_stock": False})

    assert patched.status_code == 200
    assert patched.json()["in_stock"] is False
    assert patched.json()["name"] == "Mouse"


async def test_delete_then_get_returns_404(
    client: httpx.AsyncClient, items_url: str
) -> None:
    created = await client.post(items_url, json={"name": "Cable", "price": 5.0})
    item_id = created.json()["id"]

    assert (await client.delete(f"{items_url}/{item_id}")).status_code == 204

    missing = await client.get(f"{items_url}/{item_id}")
    assert missing.status_code == 404
    assert missing.json()["detail"] == f"Item {item_id} not found"


async def test_rejects_invalid_price(client: httpx.AsyncClient, items_url: str) -> None:
    response = await client.post(items_url, json={"name": "Free", "price": 0})

    assert response.status_code == 422


async def test_concurrent_creates_get_unique_ids(
    client: httpx.AsyncClient, items_url: str
) -> None:
    responses = await asyncio.gather(
        *(
            client.post(items_url, json={"name": f"Bulk {index}", "price": 1.0})
            for index in range(20)
        )
    )

    ids = {response.json()["id"] for response in responses}
    assert len(ids) == 20
