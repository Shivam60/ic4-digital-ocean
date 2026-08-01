from typing import Protocol, runtime_checkable

from app.core.security import Principal


@runtime_checkable
class ApiKeyStore(Protocol):
    @property
    def is_enforcing(self) -> bool: ...

    async def find(self, key_hash: str) -> Principal | None: ...
