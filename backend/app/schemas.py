"""API 请求/响应模型."""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    created_at: datetime


class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse


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


# ---- 漫剧视频系统 ----

class ComicScriptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    source_topic: Optional[str] = None
    script_content: str
    storyboard_json: Optional[str] = None
    genre: Optional[str] = None
    status: str
    tags: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ComicVideoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    script_id: int
    file_path: Optional[str] = None
    seedance_task_id: Optional[str] = None
    status: str
    duration_seconds: int
    resolution: str
    error_message: Optional[str] = None
    created_at: datetime


class PublishLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    video_id: int
    platform: str
    status: str
    publish_url: Optional[str] = None
    publish_message: Optional[str] = None
    published_at: Optional[datetime] = None
    created_at: datetime


class TriggerRequest(BaseModel):
    topic: Optional[str] = None
    auto_generate_video: bool = True
    resolution: str = "720p"


class PublishRequest(BaseModel):
    platform: str  # weibo / douyin / bilibili / wechat
    message: Optional[str] = None


class TriggerBatchRequest(BaseModel):
    limit: int = 3
