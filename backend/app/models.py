"""情侣记录站 · 数据模型."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, Date

from app.database import Base


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


class Anniversary(Base):
    """纪念日."""
    __tablename__ = "anniversaries"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)  # 如：在一起的日子
    date = Column(Date, nullable=False)  # 纪念日期
    repeat_yearly = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Photo(Base):
    """相册."""
    __tablename__ = "photos"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)  # 存 uploads 下的路径
    description = Column(Text, nullable=True)
    taken_at = Column(DateTime, default=datetime.utcnow)  # 拍摄/记录时间
    created_at = Column(DateTime, default=datetime.utcnow)


class Note(Base):
    """悄悄话."""
    __tablename__ = "notes"

    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_public = Column(Boolean, default=True)  # True=都可见
