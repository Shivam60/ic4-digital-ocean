from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.deps import HttpClientDep, SettingsDep
from app.schemas.chat import ChatCompletionRequest, ChatCompletionResponse
from app.services.completions import (
    PROVIDER_NAME,
    create_chat_completion,
    iter_stream,
    open_stream,
)

router = APIRouter(tags=["chat"])


@router.post(
    "/chat/completions",
    response_model=None,
    summary="Unified chat completions",
)
async def chat_completions(
    payload: ChatCompletionRequest,
    client: HttpClientDep,
    settings: SettingsDep,
) -> ChatCompletionResponse | StreamingResponse:
    if not payload.stream:
        return await create_chat_completion(client, settings, payload)

    upstream = await open_stream(client, settings, payload)
    return StreamingResponse(
        iter_stream(upstream),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Gateway-Provider": PROVIDER_NAME,
        },
    )
