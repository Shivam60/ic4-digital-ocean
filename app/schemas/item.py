from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ItemBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    price: float = Field(gt=0)
    in_stock: bool = True


class ItemCreate(ItemBase):
    pass


class ItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    price: float | None = Field(default=None, gt=0)
    in_stock: bool | None = None


class ItemRead(ItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
