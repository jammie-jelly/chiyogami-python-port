from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class PasteBase(BaseModel):
    title: Optional[str]
    content: str

class PasteCreate(PasteBase):
    pass

class PasteOut(PasteBase):
    id: int
    created_at: datetime

    class Config:
        orm_mode = True
