from collections.abc import Sequence

from app.core.config import ApiKeyConfig
from app.core.security import Principal


class ConfigApiKeyStore:
    def __init__(self, keys: Sequence[ApiKeyConfig]) -> None:
        self._principals = {
            key.key_hash: Principal(label=key.label, scopes=frozenset(key.scopes))
            for key in keys
        }

    @property
    def is_enforcing(self) -> bool:
        return bool(self._principals)

    async def find(self, key_hash: str) -> Principal | None:
        return self._principals.get(key_hash)
