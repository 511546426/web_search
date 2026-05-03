"""情侣记录站 · 数据模型."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, Date, ForeignKey

from app.database import Base


class User(Base):
    """用户账号."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(120), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Memory(Base):
    """时光轴：一条记忆."""
    __tablename__ = "memories"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=True)
    content = Column(Text, nullable=False)
    happened_at = Column(DateTime, default=datetime.utcnow)  # 发生时间
    created_at = Column(DateTime, default=datetime.utcnow)
    image_url = Column(String(500), nullable=True)  # 可选头图
    mood = Column(String(50), nullable=True)  # 心情标签：开心/感动/搞笑...
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)


class Anniversary(Base):
    """纪念日."""
    __tablename__ = "anniversaries"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)  # 如：在一起的日子
    date = Column(Date, nullable=False)  # 纪念日期
    repeat_yearly = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)


class Photo(Base):
    """相册."""
    __tablename__ = "photos"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)  # 存 uploads 下的路径
    description = Column(Text, nullable=True)
    taken_at = Column(DateTime, default=datetime.utcnow)  # 拍摄/记录时间
    created_at = Column(DateTime, default=datetime.utcnow)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)


class Note(Base):
    """悄悄话."""
    __tablename__ = "notes"

    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_public = Column(Boolean, default=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)


# ---- 漫剧视频系统 ----

class ComicScript(Base):
    """漫剧剧本."""
    __tablename__ = "comic_scripts"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    source_topic = Column(Text, nullable=True)  # 原始热点话题 JSON/文本
    script_content = Column(Text, nullable=False)  # 剧本 JSON
    storyboard_json = Column(Text, nullable=True)  # 分镜 JSON
    genre = Column(String(50), nullable=True)  # 类型
    status = Column(
        String(30), default="draft", index=True
    )  # draft / generating_video / video_done / video_failed / published
    tags = Column(Text, nullable=True)  # JSON 标签数组
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ComicVideo(Base):
    """漫剧视频."""
    __tablename__ = "comic_videos"

    id = Column(Integer, primary_key=True, index=True)
    script_id = Column(Integer, ForeignKey("comic_scripts.id"), nullable=False, index=True)
    file_path = Column(String(500), nullable=True)  # 本地文件路径
    seedance_task_id = Column(String(200), nullable=True)  # Seedance 任务 ID
    status = Column(
        String(30), default="pending", index=True
    )  # pending / generating / completed / failed
    duration_seconds = Column(Integer, default=10)
    resolution = Column(String(20), default="720p")
    seedance_result = Column(Text, nullable=True)  # API 响应 JSON
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PublishLog(Base):
    """发布记录."""
    __tablename__ = "publish_logs"

    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(Integer, ForeignKey("comic_videos.id"), nullable=False, index=True)
    platform = Column(String(50), nullable=False)  # weibo / douyin / bilibili / wechat
    status = Column(String(30), default="pending")  # pending / published / failed
    publish_url = Column(String(500), nullable=True)  # 发布后的链接
    publish_message = Column(Text, nullable=True)
    published_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
