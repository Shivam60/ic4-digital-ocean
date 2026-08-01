from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.deps import ModelRouterDep, require_scope
from app.core.security import CHAT_COMPLETIONS_SCOPE, Principal
from app.schemas.chat import ChatCompletionRequest, ChatCompletionResponse

router = APIRouter(tags=["chat"])

CallerDep = Annotated[Principal, Depends(require_scope(CHAT_COMPLETIONS_SCOPE))]


@router.post(
    "/chat/completions",
    response_model=None,
    summary="Unified chat completions",
)
async def chat_completions(
    payload: ChatCompletionRequest,
    model_router: ModelRouterDep,
    caller: CallerDep,
) -> ChatCompletionResponse | StreamingResponse:
    if not payload.stream:
        return await model_router.complete(payload)

    handle = await model_router.stream(payload)
    return StreamingResponse(
        handle.events,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Gateway-Provider": handle.provider,
        },
    )
