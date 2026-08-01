from fastapi import APIRouter, Query, status

from app.api.deps import ItemRepositoryDep
from app.schemas.item import ItemCreate, ItemRead, ItemUpdate

router = APIRouter(prefix="/items", tags=["items"])


@router.get("", response_model=list[ItemRead])
async def list_items(
    repository: ItemRepositoryDep,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[ItemRead]:
    return await repository.list(limit=limit, offset=offset)


@router.post("", response_model=ItemRead, status_code=status.HTTP_201_CREATED)
async def create_item(payload: ItemCreate, repository: ItemRepositoryDep) -> ItemRead:
    return await repository.create(payload)


@router.get("/{item_id}", response_model=ItemRead)
async def get_item(item_id: int, repository: ItemRepositoryDep) -> ItemRead:
    return await repository.get(item_id)


@router.patch("/{item_id}", response_model=ItemRead)
async def update_item(
    item_id: int, payload: ItemUpdate, repository: ItemRepositoryDep
) -> ItemRead:
    return await repository.update(item_id, payload)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(item_id: int, repository: ItemRepositoryDep) -> None:
    await repository.delete(item_id)
