from db import database, pastes
from schemas import PasteCreate, PasteOut
from typing import List, Optional

async def create_paste(p: PasteCreate) -> PasteOut:
    query = pastes.insert().values(title=p.title, content=p.content)
    paste_id = await database.execute(query)
    return await get_paste(paste_id)

async def list_pastes(skip: int = 0, limit: int = 50) -> List[PasteOut]:
    query = pastes.select().offset(skip).limit(limit).order_by(pastes.c.id.desc())
    rows = await database.fetch_all(query)
    return [PasteOut(**r) for r in rows]

async def get_paste(paste_id: int) -> Optional[PasteOut]:
    query = pastes.select().where(pastes.c.id == paste_id)
    row = await database.fetch_one(query)
    return PasteOut(**row) if row else None

async def delete_paste(paste_id: int) -> bool:
    query = pastes.delete().where(pastes.c.id == paste_id)
    res = await database.execute(query)
    return res > 0
