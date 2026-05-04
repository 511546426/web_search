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
    review_score: Optional[float] = None
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


class CreateScriptRequest(BaseModel):
    """手动创建剧本请求."""
    title: str
    script_content: str  # JSON 格式的剧本内容
    genre: Optional[str] = None
    tags: Optional[str] = None
    source_topic: Optional[str] = None


class ScriptFromTextRequest(BaseModel):
    """从纯文本转换剧本请求."""
    text: str  # 用户提供的纯文本剧本
    visual_style: str = "anime"  # "anime"（动漫）或 "realistic"（真人）
    source_topic: Optional[str] = None


class TriggerRequest(BaseModel):
    topic: Optional[str] = None
    auto_generate_video: bool = True
    resolution: str = "720p"


class PublishRequest(BaseModel):
    platform: str
    message: Optional[str] = None


class TriggerBatchRequest(BaseModel):
    limit: int = 3


# ---- 商品带货 ----

class ProductInfoRequest(BaseModel):
    """商品信息 + 上传图片 ID 列表."""
    name: str = ""
    category: str = ""
    description: str = ""
    selling_points: str = ""  # 卖点，逗号分隔
    target_audience: str = ""  # 目标人群
    style_preference: str = ""  # 风格偏好
    photo_ids: list[str] = []  # 上传的图片文件名列表
    visual_style: str = "realistic"  # 动漫/真人
    showcase_style: str = "story"  # story（剧情带货）/ visual（视觉展示）

class ProductAdScriptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    script_content: str
    genre: str
    status: str
    tags: str
    product_info: str
    photo_ids: str
    review_score: Optional[float] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
