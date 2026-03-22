"""API 请求/响应模型."""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


# ----- Memory -----
class MemoryCreate(BaseModel):
    title: Optional[str] = None
    content: str
    happened_at: Optional[datetime] = None
    image_url: Optional[str] = None
    mood: Optional[str] = None


class MemoryUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    happened_at: Optional[datetime] = None
    image_url: Optional[str] = None
    mood: Optional[str] = None


class MemoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: Optional[str] = None
    content: str
    happened_at: datetime
    created_at: datetime
    image_url: Optional[str] = None
    mood: Optional[str] = None


# ----- Anniversary -----
class AnniversaryCreate(BaseModel):
    name: str
    date: date
    repeat_yearly: bool = True


class AnniversaryUpdate(BaseModel):
    name: Optional[str] = None
    date: Optional[date] = None
    repeat_yearly: Optional[bool] = None


class AnniversaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    date: date
    repeat_yearly: bool
    created_at: datetime


# ----- Photo -----
class PhotoCreate(BaseModel):
    description: Optional[str] = None
    taken_at: Optional[datetime] = None


class PhotoUpdate(BaseModel):
    description: Optional[str] = None
    taken_at: Optional[datetime] = None


class PhotoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    filename: str
    description: Optional[str] = None
    taken_at: datetime
    created_at: datetime


# ----- Note -----
class NoteCreate(BaseModel):
    content: str
    is_public: bool = True


class NoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    content: str
    created_at: datetime
    is_public: bool
