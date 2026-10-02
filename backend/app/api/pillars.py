from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Pillar, Segment

router = APIRouter(prefix="/pillars", tags=["pillars"])


class PillarIn(BaseModel):
    segment_id: int = 1
    position_m: float
    thickness_m: float = 0.4
    label: str = "新挡柱"


@router.get("")
def list_pillars(db: Session = Depends(get_db)):
    return [{"id": r.id, "segment_id": r.segment_id, "position_m": r.position_m,
             "thickness_m": r.thickness_m, "label": r.label}
            for r in db.scalars(select(Pillar).order_by(Pillar.position_m)).all()]


@router.post("", status_code=201)
def add_pillar(body: PillarIn, db: Session = Depends(get_db)):
    seg = db.get(Segment, body.segment_id)
    if not seg:
        raise HTTPException(404, "街段不存在")
    if body.thickness_m <= 0:
        raise HTTPException(422, "柱厚必须为正")
    if not (0.0 <= body.position_m <= seg.width_m):
        raise HTTPException(422, f"柱位必须在 [0, {seg.width_m}] 内")
    p = Pillar(segment_id=body.segment_id, position_m=body.position_m,
               thickness_m=body.thickness_m, label=body.label)
    db.add(p)
    db.commit()
    db.refresh(p)
    return {"id": p.id, "segment_id": p.segment_id, "position_m": p.position_m,
            "thickness_m": p.thickness_m, "label": p.label}
