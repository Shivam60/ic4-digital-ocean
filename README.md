# model-router-gateway

An API gateway that acts as a unified model router. It accepts one standardized inference
schema, translates it for real LLM providers, streams responses back over SSE without
buffering, and falls back to a backup provider when a primary fails.

See `ARCHITECTURE.md` for the design diagram and the delivery plan.

## Requirements

- Python 3.11+ (developed against 3.14)

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt   # use requirements.txt for production
cp .env.example .env                  # then set OPENAI_API_KEY
```

## Run

```bash
uvicorn app.main:app --reload
```

| Resource | URL |
| --- | --- |
| Health | http://127.0.0.1:8000/v1/health |
| Chat completions | http://127.0.0.1:8000/v1/chat/completions |
| Swagger UI | http://127.0.0.1:8000/docs |
| OpenAPI schema | http://127.0.0.1:8000/openapi.json |

## Usage

Non-streaming:

```bash
curl -s http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hello"}]}'
```

Streaming over SSE — `-N` disables curl's own buffering so you can watch tokens arrive:

```bash
curl -N http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hello"}],"stream":true}'
```

Point `OPENAI_BASE_URL` at any OpenAI-compatible upstream to use a different provider.

## Layout

```
app/
  main.py            app factory, lifespan, shared HTTP client
  core/config.py     pydantic-settings configuration (env-driven)
  core/errors.py     gateway and upstream error types
  api/
    router.py        aggregates routers
    deps.py          typed dependency aliases
    routes/          health.py, chat.py
  schemas/chat.py    unified request/response/chunk models
  services/          upstream call and SSE translation
```

## Why the streaming path is shaped the way it is

The upstream connection is opened and its status checked *before* the streaming response
object is constructed. Starlette sends response headers before it begins iterating the
response body generator, so opening the upstream lazily inside the generator would flush
a `200` downstream before we knew the upstream was healthy — which would make the silent
fallback in a later slice impossible. Nothing is buffered: chunks are translated and
forwarded one at a time.

## Timeout policy

Streaming upstreams get no read timeout, because long gaps between tokens are normal.
A stalled-but-connected upstream is instead caught by a separate first-chunk budget
(`UPSTREAM_FIRST_CHUNK_TIMEOUT_SECONDS`), which is what triggers fallback to a backup
provider.

## Notes

- Configuration is read from environment variables or `.env`; field names map to uppercase
  env keys (`api_prefix` -> `API_PREFIX`).
- The shared `httpx.AsyncClient` is created once per process in `lifespan` and reached
  through `HttpClientDep`, so handlers never construct per-request clients.
