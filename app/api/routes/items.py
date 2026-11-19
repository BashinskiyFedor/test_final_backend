from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import Item
from app.schemas.item import ItemCreate, ItemRead, ItemUpdate

router = APIRouter(prefix="/items", tags=["items"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_item_or_404(item_id: int, session: SessionDep) -> Item:
    item = await session.get(Item, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")
    return item


ItemDep = Annotated[Item, Depends(get_item_or_404)]


@router.get("", response_model=list[ItemRead])
async def list_items(session: SessionDep, skip: int = 0, limit: int = 100):
    result = await session.scalars(select(Item).offset(skip).limit(limit))
    return result.all()


@router.post("", response_model=ItemRead, status_code=status.HTTP_201_CREATED)
async def create_item(data: ItemCreate, session: SessionDep):
    item = Item(**data.model_dump())
    session.add(item)
    await session.commit()
    return item


@router.get("/{item_id}", response_model=ItemRead)
async def read_item(item: ItemDep):
    return item


@router.patch("/{item_id}", response_model=ItemRead)
async def update_item(data: ItemUpdate, item: ItemDep, session: SessionDep):
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    await session.commit()
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(item: ItemDep, session: SessionDep):
    await session.delete(item)
    await session.commit()
