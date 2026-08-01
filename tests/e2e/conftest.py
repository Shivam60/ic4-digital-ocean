import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
STARTUP_TIMEOUT_SECONDS = 30.0
SHUTDOWN_TIMEOUT_SECONDS = 10.0
POLL_INTERVAL_SECONDS = 0.1


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _serve(
    target: str, port: int, env_overrides: dict[str, str] | None = None
) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            target,
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=REPO_ROOT,
        env={**os.environ, **(env_overrides or {})},
    )


def _wait_until_serving(process: subprocess.Popen[bytes], probe_url: str) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"server exited during startup with code {process.returncode}"
            )
        try:
            if httpx.get(probe_url, timeout=1.0).status_code == 200:
                return
        except httpx.TransportError:
            time.sleep(POLL_INTERVAL_SECONDS)
    raise RuntimeError(f"server did not answer {probe_url} within the startup budget")


def _stop(process: subprocess.Popen[bytes]) -> None:
    process.terminate()
    try:
        process.wait(timeout=SHUTDOWN_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _run_server(
    target: str, probe_path: str, env_overrides: dict[str, str] | None = None
) -> Iterator[str]:
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    process = _serve(target, port, env_overrides)
    try:
        _wait_until_serving(process, f"{base_url}{probe_path}")
        yield base_url
    finally:
        _stop(process)


def _gateway_env(providers: dict[str, str], chain: list[str]) -> dict[str, str]:
    return {
        "PROVIDERS": json.dumps(
            {
                name: {"kind": "openai", "base_url": base_url}
                for name, base_url in providers.items()
            }
        ),
        "DEFAULT_CHAIN": json.dumps(chain),
        "MODEL_ROUTES": "{}",
        "UPSTREAM_CONNECT_TIMEOUT_SECONDS": "2.0",
    }


@pytest.fixture(scope="session")
def mock_provider_url() -> Iterator[str]:
    yield from _run_server("mock_provider.openai:app", "/openapi.json")


@pytest.fixture(scope="session")
def dead_provider_url() -> str:
    return f"http://127.0.0.1:{_free_port()}/v1"


@pytest.fixture(scope="session")
def gateway_url(mock_provider_url: str) -> Iterator[str]:
    yield from _run_server(
        "app.main:app",
        "/v1/health",
        _gateway_env({"mock": f"{mock_provider_url}/v1"}, ["mock"]),
    )


@pytest.fixture(scope="session")
def failover_gateway_url(
    mock_provider_url: str, dead_provider_url: str
) -> Iterator[str]:
    yield from _run_server(
        "app.main:app",
        "/v1/health",
        _gateway_env(
            {"dead": dead_provider_url, "mock": f"{mock_provider_url}/v1"},
            ["dead", "mock"],
        ),
    )
