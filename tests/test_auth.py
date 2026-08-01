from collections.abc import Iterator

import httpx
import pytest
from fastapi import FastAPI

from app.core.config import ApiKeyConfig, Settings, get_settings
from app.core.security import CHAT_COMPLETIONS_SCOPE, hash_api_key
from tests.helpers import MODEL_OK, ask, counting_provider, error_of, use_chain

VALID_KEY = "sk-gateway-valid"
SCOPED_KEY = "sk-gateway-scoped"
UNKNOWN_KEY = "sk-gateway-unknown"


def _settings_with_keys() -> Settings:
    return Settings(
        api_keys=[
            ApiKeyConfig(label="full", key_hash=hash_api_key(VALID_KEY), scopes=[]),
            ApiKeyConfig(
                label="reader",
                key_hash=hash_api_key(SCOPED_KEY),
                scopes=["models:read"],
            ),
        ]
    )


@pytest.fixture(autouse=True)
def _reset_overrides(app: FastAPI) -> Iterator[None]:
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def guarded(app: FastAPI) -> list[httpx.Request]:
    provider, calls = counting_provider("upstream")
    use_chain(app, provider)
    app.dependency_overrides[get_settings] = _settings_with_keys
    return calls


def _bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


async def test_valid_key_is_accepted(
    client: httpx.AsyncClient, guarded: list[httpx.Request]
) -> None:
    response = await ask(client, MODEL_OK, headers=_bearer(VALID_KEY))

    assert response.status_code == 200
    assert len(guarded) == 1


@pytest.mark.parametrize(
    ("headers", "reason"),
    [
        (None, "missing header"),
        ({"Authorization": ""}, "empty header"),
        ({"Authorization": "Bearer"}, "scheme with no token"),
        ({"Authorization": "Bearer "}, "empty token"),
        ({"Authorization": f"Basic {VALID_KEY}"}, "wrong scheme"),
        ({"Authorization": VALID_KEY}, "no scheme"),
        ({"Authorization": f"Bearer {UNKNOWN_KEY}"}, "unknown key"),
    ],
)
async def test_bad_credentials_are_rejected_before_any_upstream_call(
    client: httpx.AsyncClient,
    guarded: list[httpx.Request],
    headers: dict[str, str] | None,
    reason: str,
) -> None:
    response = await ask(client, MODEL_OK, headers=headers)

    assert response.status_code == 401, reason
    assert response.headers["www-authenticate"] == "Bearer"
    assert error_of(response)["type"] == "authentication_error"
    assert guarded == [], "an upstream connection was opened for a rejected caller"


async def test_valid_key_without_the_scope_is_forbidden_and_never_reaches_upstream(
    client: httpx.AsyncClient, guarded: list[httpx.Request]
) -> None:
    response = await ask(client, MODEL_OK, headers=_bearer(SCOPED_KEY))

    assert response.status_code == 403
    error = error_of(response)
    assert error["type"] == "authorization_error"
    assert error["required_scope"] == CHAT_COMPLETIONS_SCOPE
    assert guarded == []


async def test_gateway_is_open_when_no_keys_are_configured(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    provider, calls = counting_provider("upstream")
    use_chain(app, provider)

    response = await ask(client, MODEL_OK)

    assert response.status_code == 200
    assert len(calls) == 1


async def test_health_stays_public(
    client: httpx.AsyncClient, guarded: list[httpx.Request]
) -> None:
    response = await client.get("/v1/health")

    assert response.status_code == 200


def test_hashing_is_stable_and_not_reversible() -> None:
    assert hash_api_key(VALID_KEY) == hash_api_key(VALID_KEY)
    assert hash_api_key(VALID_KEY) != hash_api_key(UNKNOWN_KEY)
    assert VALID_KEY not in hash_api_key(VALID_KEY)
