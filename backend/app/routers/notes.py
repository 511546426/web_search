"""悄悄话 API."""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Note
from app.schemas import NoteCreate, NoteResponse

router = APIRouter(prefix="/api/notes", tags=["notes"])


@router.get("", response_model=List[NoteResponse])
def list_notes(db: Session = Depends(get_db)):
    return db.query(Note).order_by(Note.created_at.desc()).all()


@router.post("", response_model=NoteResponse)
def create_note(body: NoteCreate, db: Session = Depends(get_db)):
    n = Note(content=body.content, is_public=body.is_public)
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


@router.get("/{note_id}", response_model=NoteResponse)
def get_note(note_id: int, db: Session = Depends(get_db)):
    n = db.query(Note).filter(Note.id == note_id).first()
    if not n:
        raise HTTPException(status_code=404, detail="悄悄话不存在")
    return n


@router.delete("/{note_id}", status_code=204)
def delete_note(note_id: int, db: Session = Depends(get_db)):
    n = db.query(Note).filter(Note.id == note_id).first()
    if not n:
        raise HTTPException(status_code=404, detail="悄悄话不存在")
    db.delete(n)
    db.commit()
