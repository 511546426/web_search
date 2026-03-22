"""相册 API + 图片上传."""
import logging
import os
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Photo
from app.schemas import PhotoUpdate, PhotoResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/photos", tags=["photos"])

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 允许单张图片最大 20MB（避免 Starlette 默认 1MB 限制导致上传失败）
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


async def _get_upload_form(request: Request):
    """解析表单；若当前 Starlette 支持则放宽单 part 大小限制."""
    try:
        return await request.form(max_part_size=MAX_UPLOAD_BYTES)
    except TypeError:
        return await request.form()


def _get_file_from_form(form):
    """从表单中取出单个上传文件（兼容 list 或单个值）."""
    raw = form.get("file")
    if raw is None:
        return None
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    if raw is not None and hasattr(raw, "read") and hasattr(raw, "filename"):
        return raw
    return None


async def _save_upload(file: UploadFile) -> str:
    ext = os.path.splitext(file.filename or "")[-1] or ".jpg"
    name = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(UPLOAD_DIR, name)
    content = await file.read()
    with open(path, "wb") as f:
        f.write(content)
    return name


@router.get("", response_model=List[PhotoResponse])
def list_photos(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    return db.query(Photo).order_by(Photo.taken_at.desc()).offset(skip).limit(limit).all()


@router.post("", response_model=PhotoResponse)
async def upload_photo(
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        form = await _get_upload_form(request)
        file = _get_file_from_form(form)
        if not file:
            raise HTTPException(status_code=400, detail="请选择一张图片")
        description = form.get("description")
        if isinstance(description, str):
            description = description.strip() or None
        else:
            description = None
        filename = await _save_upload(file)
        p = Photo(filename=filename, description=description)
        db.add(p)
        db.commit()
        db.refresh(p)
        return p
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("photo upload failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"上传失败，请重试或换一张小一点的图片。错误: {e!s}",
        ) from e


@router.get("/{photo_id}", response_model=PhotoResponse)
def get_photo(photo_id: int, db: Session = Depends(get_db)):
    p = db.query(Photo).filter(Photo.id == photo_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="照片不存在")
    return p


@router.patch("/{photo_id}", response_model=PhotoResponse)
def update_photo(photo_id: int, body: PhotoUpdate, db: Session = Depends(get_db)):
    p = db.query(Photo).filter(Photo.id == photo_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="照片不存在")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    db.commit()
    db.refresh(p)
    return p


@router.delete("/{photo_id}", status_code=204)
def delete_photo(photo_id: int, db: Session = Depends(get_db)):
    p = db.query(Photo).filter(Photo.id == photo_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="照片不存在")
    db.delete(p)
    db.commit()
