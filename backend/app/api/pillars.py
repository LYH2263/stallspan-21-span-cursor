from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import Pillar
from app.services import allocation_service as svc

router = APIRouter(prefix="/pillars", tags=["pillars"])


class PillarCreate(BaseModel):
    segment_id: int
    position_m: float
    thickness_m: float = 0.4
    label: str = "挡柱"


@router.get("")
def list_pillars(db: Session = Depends(get_db)):
    return [
        {"id": r.id, "segment_id": r.segment_id, "position_m": r.position_m,
         "thickness_m": r.thickness_m, "label": r.label}
        for r in db.scalars(select(Pillar).order_by(Pillar.position_m, Pillar.id)).all()
    ]


@router.post("")
def add_pillar(body: PillarCreate, db: Session = Depends(get_db)):
    """Insert a pillar, then recompute the segment IN THE SAME TRANSACTION.
    The returned `allocation` is the single response that drives both the map
    blocks and the rejected list."""
    seg = svc.get_segment(db, body.segment_id)
    existing = svc.pillar_rows(db, body.segment_id)
    svc.validate_new_pillar(seg, body.position_m, body.thickness_m, existing)
    pillar = Pillar(
        segment_id=body.segment_id,
        position_m=body.position_m,
        thickness_m=body.thickness_m,
        label=body.label,
    )
    db.add(pillar)
    db.flush()
    allocation = svc.compute_allocation(db, body.segment_id)
    run_id = svc.persist_run(db, body.segment_id, allocation)
    return {
        "pillar": {"id": pillar.id, "segment_id": pillar.segment_id,
                   "position_m": pillar.position_m, "thickness_m": pillar.thickness_m,
                   "label": pillar.label},
        "allocation": {"id": run_id, **allocation},
    }


@router.delete("/{pillar_id}")
def delete_pillar(pillar_id: int, db: Session = Depends(get_db)):
    pillar = db.get(Pillar, pillar_id)
    if not pillar:
        raise HTTPException(404, "挡柱不存在")
    segment_id = pillar.segment_id
    db.delete(pillar)
    db.flush()
    allocation = svc.compute_allocation(db, segment_id)
    run_id = svc.persist_run(db, segment_id, allocation)
    return {"deleted_id": pillar_id, "allocation": {"id": run_id, **allocation}}
