import httpx

from app.core.errors import UpstreamError
from app.schemas.chat import ChatCompletionRequest, ChatCompletionResponse
from app.services.llm.openai_compat import to_unified_response, to_upstream_payload


class OllamaService:
    name = "ollama"

    def __init__(self, client: httpx.AsyncClient, base_url: str) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")

    @property
    def _url(self) -> str:
        return f"{self._base_url}/chat/completions"

    def _upstream_model(self, request: ChatCompletionRequest) -> str:
        return request.model

    async def complete(
        self, request: ChatCompletionRequest
    ) -> ChatCompletionResponse:
        response = await self._client.post(
            self._url,
            json=to_upstream_payload(
                request,
                model=self._upstream_model(request),
                stream=False,
            ),
            headers={"Content-Type": "application/json"},
        )
        if response.status_code >= 400:
            raise UpstreamError(self.name, response.status_code, response.text)
        return to_unified_response(response.json(), provider=self.name)
