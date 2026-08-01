from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.deps import HttpClientDep, ModelRepositoryDep, SettingsDep
from app.schemas.chat import ChatCompletionRequest, ChatCompletionResponse
from app.services.completions import PROVIDER_NAME, iter_stream, open_stream

router = APIRouter(tags=["chat"])


@router.post(
    "/chat/completions",
    response_model=None,
    summary="Unified chat completions",
)
async def chat_completions(
    payload: ChatCompletionRequest,
    repository: ModelRepositoryDep,
    client: HttpClientDep,
    settings: SettingsDep,
) -> ChatCompletionResponse | StreamingResponse:
    if not payload.stream:
        return await repository.complete(payload)

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
