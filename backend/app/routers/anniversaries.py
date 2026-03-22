"""纪念日 API."""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Anniversary
from app.schemas import AnniversaryCreate, AnniversaryUpdate, AnniversaryResponse

router = APIRouter(prefix="/api/anniversaries", tags=["anniversaries"])


@router.get("", response_model=List[AnniversaryResponse])
def list_anniversaries(db: Session = Depends(get_db)):
    return db.query(Anniversary).order_by(Anniversary.date.asc()).all()


@router.post("", response_model=AnniversaryResponse)
def create_anniversary(body: AnniversaryCreate, db: Session = Depends(get_db)):
    a = Anniversary(name=body.name, date=body.date, repeat_yearly=body.repeat_yearly)
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


@router.get("/{anniversary_id}", response_model=AnniversaryResponse)
def get_anniversary(anniversary_id: int, db: Session = Depends(get_db)):
    a = db.query(Anniversary).filter(Anniversary.id == anniversary_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="纪念日不存在")
    return a


@router.patch("/{anniversary_id}", response_model=AnniversaryResponse)
def update_anniversary(anniversary_id: int, body: AnniversaryUpdate, db: Session = Depends(get_db)):
    a = db.query(Anniversary).filter(Anniversary.id == anniversary_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="纪念日不存在")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(a, k, v)
    db.commit()
    db.refresh(a)
    return a


@router.delete("/{anniversary_id}", status_code=204)
def delete_anniversary(anniversary_id: int, db: Session = Depends(get_db)):
    a = db.query(Anniversary).filter(Anniversary.id == anniversary_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="纪念日不存在")
    db.delete(a)
    db.commit()
