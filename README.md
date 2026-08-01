# fastapi-async-service

Async FastAPI service scaffold: fully `async def` route handlers, an async lifespan that
owns shared resources, and an async test suite driven through the ASGI transport (no live
server needed).

## Requirements

- Python 3.11+ (developed against 3.14)

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt   # use requirements.txt for production
cp .env.example .env
```

## Run

```bash
uvicorn app.main:app --reload
```

| Resource | URL |
| --- | --- |
| Health | http://127.0.0.1:8000/api/v1/health |
| Items | http://127.0.0.1:8000/api/v1/items |
| Swagger UI | http://127.0.0.1:8000/docs |
| OpenAPI schema | http://127.0.0.1:8000/openapi.json |

## Test and lint

```bash
pytest
ruff check .
ruff format .
```

## Layout

```
app/
  main.py            app factory, lifespan, CORS, exception handlers
  core/config.py     pydantic-settings configuration (env-driven)
  api/
    router.py        aggregates versioned routers
    deps.py          typed dependency aliases
    routes/          health.py, items.py
  schemas/           request/response models
  services/items.py  async in-memory repository
tests/               async tests (conftest.py builds the ASGI client)
```

## How the async pieces fit together

`lifespan` in `app/main.py` creates the shared `httpx.AsyncClient` and the item repository
once per process and tears the client down on shutdown. Both are stored on `app.state` and
reached through the dependency aliases in `app/api/deps.py`, so handlers never construct
per-request clients:

```python
async def call_upstream(client: HttpClientDep) -> dict:
    response = await client.get("https://example.com/api")
    return response.json()
```

`ItemRepository` guards its dict with an `asyncio.Lock` so concurrent requests can't
interleave on the ID counter. Replace it with a database-backed repository (for example
SQLAlchemy's `AsyncSession` or `asyncpg`) by keeping the same async method signatures and
binding the new implementation in `get_item_repository`.

`pytest` runs in `asyncio_mode = "auto"` (set in `pyproject.toml`), so test functions can be
`async def` without a decorator. `tests/conftest.py` wraps the app in `LifespanManager` so
startup and shutdown run during tests, since `httpx.ASGITransport` skips lifespan events on
its own.

## Notes

- Configuration is read from environment variables or `.env`; field names map to uppercase
  env keys (`api_v1_prefix` -> `API_V1_PREFIX`).
- Item storage is in-memory and resets on restart. It is a placeholder for a real database.
- If you add blocking I/O or CPU-bound work, run it off the event loop with
  `starlette.concurrency.run_in_threadpool` (or a process pool) rather than awaiting it
  inline.
