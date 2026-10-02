from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import allocation_service as svc

router = APIRouter(prefix="/allocate", tags=["allocate"])


@router.post("/run")
def run_allocate(segment_id: int = 1, db: Session = Depends(get_db)):
    """Explicit recompute: read current pillars/vendors, persist one historical
    snapshot, return it. Used by the '重新分配' button."""
    result = svc.compute_allocation(db, segment_id)
    run_id = svc.persist_run(db, segment_id, result)
    return {"id": run_id, **result}


@router.get("/latest")
def latest(segment_id: int = 1, db: Session = Depends(get_db)):
    """Always recomputed live from the current pillars — never a stale snapshot.
    `id` is just the most recent historical run (or null); browsing here does
    not create one."""
    result = svc.compute_allocation(db, segment_id)
    return {"id": svc.latest_run_id(db, segment_id), "live": True, **result}
