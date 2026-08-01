import json
import time

import httpx
import pytest

pytestmark = pytest.mark.e2e

MODEL_OK = "mock/ok"
DONE = "[DONE]"
EXPECTED_REPLY = "Hello, world from the mock provider."
REQUEST_TIMEOUT_SECONDS = 30.0
MIN_STREAM_SPREAD_SECONDS = 0.5


def _payload(*, stream: bool) -> dict[str, object]:
    return {
        "model": MODEL_OK,
        "messages": [{"role": "user", "content": "hi"}],
        "stream": stream,
    }


async def _collect_timed_frames(url: str) -> list[tuple[float, str]]:
    frames: list[tuple[float, str]] = []
    async with (
        httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client,
        client.stream(
            "POST", f"{url}/v1/chat/completions", json=_payload(stream=True)
        ) as response,
    ):
        response.raise_for_status()
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["x-gateway-provider"] == "mock"
        async for line in response.aiter_lines():
            if line.startswith("data:"):
                frames.append((time.monotonic(), line[len("data:") :].strip()))
    return frames


async def test_completion_over_a_real_socket(gateway_url: str) -> None:
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        response = await client.post(
            f"{gateway_url}/v1/chat/completions", json=_payload(stream=False)
        )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "mock"
    assert body["choices"][0]["message"]["content"] == EXPECTED_REPLY


async def test_tokens_arrive_progressively_rather_than_in_one_flush(
    gateway_url: str,
) -> None:
    started = time.monotonic()
    frames = await _collect_timed_frames(gateway_url)

    assert frames, "no SSE frames were received"
    assert frames[-1][1] == DONE

    content_frames = [(at, data) for at, data in frames if data != DONE]
    assert len(content_frames) >= 4

    first_at = content_frames[0][0]
    last_at = content_frames[-1][0]
    assert last_at - first_at >= MIN_STREAM_SPREAD_SECONDS
    assert first_at - started < (last_at - started) / 2

    text = "".join(
        json.loads(data)["choices"][0]["delta"].get("content") or ""
        for _, data in content_frames
    )
    assert text == EXPECTED_REPLY


async def test_dead_primary_falls_back_over_real_sockets(
    failover_gateway_url: str,
) -> None:
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        response = await client.post(
            f"{failover_gateway_url}/v1/chat/completions", json=_payload(stream=False)
        )

    assert response.status_code == 200
    assert response.json()["provider"] == "mock"
