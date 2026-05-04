"""漫剧视频系统 · 数据模型."""
from datetime import datetime
from sqlalchemy import Column, Integer, Float, String, Text, Boolean, DateTime, Date, ForeignKey

from app.database import Base


class User(Base):
    """用户账号."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(120), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class ComicScript(Base):
    """漫剧剧本."""
    __tablename__ = "comic_scripts"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    source_topic = Column(Text, nullable=True)
    script_content = Column(Text, nullable=False)
    storyboard_json = Column(Text, nullable=True)
    genre = Column(String(50), nullable=True)
    status = Column(
        String(30), default="draft", index=True
    )
    tags = Column(Text, nullable=True)
    review_score = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ComicVideo(Base):
    """漫剧视频."""
    __tablename__ = "comic_videos"

    id = Column(Integer, primary_key=True, index=True)
    script_id = Column(Integer, ForeignKey("comic_scripts.id"), nullable=False, index=True)
    file_path = Column(String(500), nullable=True)
    seedance_task_id = Column(String(200), nullable=True)
    status = Column(
        String(30), default="pending", index=True
    )
    duration_seconds = Column(Integer, default=10)
    resolution = Column(String(20), default="720p")
    seedance_result = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ProductAd(Base):
    """商品带货剧本."""
    __tablename__ = "product_ads"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    product_info = Column(Text, nullable=True)  # JSON: 商品基础信息
    photo_ids = Column(Text, nullable=True)  # JSON: 关联图片文件名列表
    script_content = Column(Text, nullable=False)  # JSON: 带货剧本
    genre = Column(String(50), nullable=True)
    status = Column(String(30), default="draft", index=True)
    tags = Column(Text, nullable=True)
    video_path = Column(String(500), nullable=True)
    review_score = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PublishLog(Base):
    """发布记录."""
    __tablename__ = "publish_logs"

    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(Integer, ForeignKey("comic_videos.id"), nullable=False, index=True)
    platform = Column(String(50), nullable=False)
    status = Column(String(30), default="pending")
    publish_url = Column(String(500), nullable=True)
    publish_message = Column(Text, nullable=True)
    published_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
