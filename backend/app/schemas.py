"""API 请求/响应模型."""
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


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
    photo_ids: List[str] = Field(default_factory=list)  # 上传的图片文件名列表
    visual_style: str = "realistic"  # 动漫/真人
    showcase_style: str = "story"  # story（剧情带货）/ visual（视觉展示）
    num_variants: int = Field(default=1, ge=1, le=3, description="生成变体数量（1-3），多版本时可对比选择")
    ad_id: Optional[int] = Field(default=None, description="复用已有草稿 ID，传此值则更新已有记录而非新建")

class ProductAdScriptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    script_content: str
    genre: Optional[str] = None
    status: str
    tags: str
    product_info: str
    photo_ids: str
    review_score: Optional[float] = None
    review_detail: Optional[str] = None
    script_variants: Optional[str] = None
    composite_confirmed: bool = False
    composite_photo_ids: Optional[str] = None
    composite_retry_count: int = 0
    script_confirmed: bool = False
    script_user_feedback: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


# ---- 步骤化带货流程 ----

class CompositePreviewRequest(BaseModel):
    """商标合成预览请求."""
    ad_id: int
    logo_photo_id: str  # 商标照片 ID（单独上传的商标图）
    garment_photo_ids: List[str] = Field(default_factory=list)  # 需要合成商标的服装照片，为空则检测所有无标照片
    positions: dict = Field(default_factory=dict)  # 可选：{"photo_id": "左胸前"}，不传则 AI 推断


class CompositePreviewItem(BaseModel):
    photo_id: str
    photo_url: str
    garment_type: str = ""
    position: Optional[str] = None
    logo_visible: bool = False
    confirmed: bool = False


class CompositePreviewResponse(BaseModel):
    ad_id: int
    items: List[CompositePreviewItem]


class CompositeConfirmRequest(BaseModel):
    ad_id: int
    photo_ids: List[str]  # 确认的合成照片 ID 列表


class ScriptRetryRequest(BaseModel):
    ad_id: int
    feedback: str = ""  # 用户补充要求（自由文本）
    improve_dimensions: List[str] = Field(default_factory=list, description="用户勾选的改进维度列表")


class ConfirmVariantRequest(BaseModel):
    """确认选择某个剧本变体."""
    ad_id: int
    variant_index: int = Field(default=0, ge=0, description="选中的变体索引（0-based）")
