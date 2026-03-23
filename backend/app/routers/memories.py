"""时光轴 API."""
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Memory, User
from app.schemas import MemoryCreate, MemoryUpdate, MemoryResponse
from app.security import get_current_user

router = APIRouter(prefix="/api/memories", tags=["memories"])


@router.get("", response_model=List[MemoryResponse])
def list_memories(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """按时间倒序返回记忆列表."""
    return (
        db.query(Memory)
        .filter(Memory.owner_id == current_user.id)
        .order_by(Memory.happened_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.post("", response_model=MemoryResponse)
def create_memory(
    body: MemoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    m = Memory(
        title=body.title,
        content=body.content,
        happened_at=body.happened_at or datetime.utcnow(),
        image_url=body.image_url,
        mood=body.mood,
        owner_id=current_user.id,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


@router.get("/{memory_id}", response_model=MemoryResponse)
def get_memory(memory_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    m = db.query(Memory).filter(Memory.id == memory_id, Memory.owner_id == current_user.id).first()
    if not m:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return m


@router.patch("/{memory_id}", response_model=MemoryResponse)
def update_memory(
    memory_id: int,
    body: MemoryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    m = db.query(Memory).filter(Memory.id == memory_id, Memory.owner_id == current_user.id).first()
    if not m:
        raise HTTPException(status_code=404, detail="记忆不存在")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(m, k, v)
    db.commit()
    db.refresh(m)
    return m


@router.delete("/{memory_id}", status_code=204)
def delete_memory(memory_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    m = db.query(Memory).filter(Memory.id == memory_id, Memory.owner_id == current_user.id).first()
    if not m:
        raise HTTPException(status_code=404, detail="记忆不存在")
    db.delete(m)
    db.commit()
