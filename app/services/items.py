import asyncio
from datetime import UTC, datetime

from app.schemas.item import ItemCreate, ItemRead, ItemUpdate


class ItemNotFoundError(Exception):
    def __init__(self, item_id: int) -> None:
        self.item_id = item_id
        super().__init__(f"Item {item_id} not found")


class ItemRepository:
    """In-memory async store. Swap for a database-backed repository later."""

    def __init__(self) -> None:
        self._items: dict[int, ItemRead] = {}
        self._next_id = 1
        self._lock = asyncio.Lock()

    async def list(self, *, limit: int = 50, offset: int = 0) -> list[ItemRead]:
        async with self._lock:
            ordered = sorted(self._items.values(), key=lambda item: item.id)
        return ordered[offset : offset + limit]

    async def get(self, item_id: int) -> ItemRead:
        async with self._lock:
            item = self._items.get(item_id)
        if item is None:
            raise ItemNotFoundError(item_id)
        return item

    async def create(self, payload: ItemCreate) -> ItemRead:
        async with self._lock:
            item = ItemRead(
                id=self._next_id,
                created_at=datetime.now(UTC),
                **payload.model_dump(),
            )
            self._items[item.id] = item
            self._next_id += 1
        return item

    async def update(self, item_id: int, payload: ItemUpdate) -> ItemRead:
        async with self._lock:
            current = self._items.get(item_id)
            if current is None:
                raise ItemNotFoundError(item_id)
            updated = current.model_copy(update=payload.model_dump(exclude_unset=True))
            self._items[item_id] = updated
        return updated

    async def delete(self, item_id: int) -> None:
        async with self._lock:
            if self._items.pop(item_id, None) is None:
                raise ItemNotFoundError(item_id)
