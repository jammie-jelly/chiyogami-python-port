from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class PasteCreate(BaseModel):
    content: str
    visibility: Optional[str] = None
    expiration: Optional[str] = None
    isEncrypted: Optional[bool] = False

class PasteOut(BaseModel):
    id: int
    title: str
    content: str
    visibility: Optional[str]
    expiration: Optional[datetime]
    isEncrypted: bool
    created_at: datetime

class UserCreate(BaseModel):
    username: str
    password: str

class UserOut(BaseModel):
    id: int
    username: str
    created_at: datetime
