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
    platform: str
    message: Optional[str] = None


class TriggerBatchRequest(BaseModel):
    limit: int = 3
