from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import Memory
from ..schemas import MemoryCreateRequest, MemoryOut

router = APIRouter(tags=["memory"])


@router.get("/memory", response_model=list[MemoryOut])
def get_memory(user=Depends(get_current_user), db: Session = Depends(get_db)) -> list[MemoryOut]:
    records = db.query(Memory).filter(Memory.user_id == user.id).order_by(Memory.created_at.desc()).all()
    return records


@router.post("/memory", response_model=MemoryOut)
def store_memory(payload: MemoryCreateRequest, user=Depends(get_current_user), db: Session = Depends(get_db)) -> MemoryOut:
    record = Memory(user_id=user.id, key=payload.key, value=payload.value)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record
