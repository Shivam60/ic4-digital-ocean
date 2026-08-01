from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.deps import ModelRepositoryDep
from app.schemas.chat import ChatCompletionRequest, ChatCompletionResponse

router = APIRouter(tags=["chat"])


@router.post(
    "/chat/completions",
    response_model=None,
    summary="Unified chat completions",
)
async def chat_completions(
    payload: ChatCompletionRequest,
    repository: ModelRepositoryDep,
) -> ChatCompletionResponse | StreamingResponse:
    if not payload.stream:
        return await repository.complete(payload)

    handle = await repository.stream(payload)
    return StreamingResponse(
        handle.events,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Gateway-Provider": handle.provider,
        },
    )
