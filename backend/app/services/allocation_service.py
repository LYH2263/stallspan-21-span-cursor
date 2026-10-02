"""Shared allocation service: every entry point (/run, /latest, pillar
insert/delete) computes from the SAME current DB state through the SAME engine
pipeline, so placements and the rejected list can never disagree.

compute_allocation is a pure instantaneous read (never touches AllocationRun);
persist_run is the only place a historical snapshot is written.
"""
import json
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import AllocationRun, Pillar, Segment, Vendor
from app.services.first_fit_engine import allocate_first_fit, result_to_dict

# A new pillar's forbidden interval must keep a strictly positive gap from the
# segment edges and from every existing pillar (touching already merges).
EDGE_EPS = 1e-9


def get_segment(db: Session, segment_id: int) -> Segment:
    seg = db.get(Segment, segment_id)
    if not seg:
        raise HTTPException(404, "街段不存在")
    return seg


def pillar_rows(db: Session, segment_id: int) -> list[Pillar]:
    return list(
        db.scalars(
            select(Pillar)
            .where(Pillar.segment_id == segment_id)
            .order_by(Pillar.position_m, Pillar.id)
        ).all()
    )


def pillar_dicts(rows: list[Pillar]) -> list[dict]:
    return [
        {
            "id": p.id,
            "segment_id": p.segment_id,
            "position_m": p.position_m,
            "thickness_m": p.thickness_m,
            "label": p.label,
        }
        for p in rows
    ]


def vendor_dicts(db: Session, market_day_id: int) -> list[dict]:
    return [
        {
            "id": v.id,
            "name": v.name,
            "stall_width_m": v.stall_width_m,
            "priority": v.priority,
        }
        for v in db.scalars(
            select(Vendor).where(Vendor.market_day_id == market_day_id)
        ).all()
    ]


def compute_allocation(db: Session, segment_id: int) -> dict:
    """Current pillars + current vendors -> one AllocResult dict (live).

    Does not read or write AllocationRun; no forbidden geometry is cached
    anywhere, so a changed pillar is reflected on the very next call.
    """
    seg = get_segment(db, segment_id)
    rows = pillar_rows(db, segment_id)
    pillars = [{"position_m": p.position_m, "thickness_m": p.thickness_m} for p in rows]
    vendors = vendor_dicts(db, seg.market_day_id)
    result = result_to_dict(allocate_first_fit(seg.width_m, vendors, pillars))
    result["segment"] = {"id": seg.id, "name": seg.name, "width_m": seg.width_m}
    result["pillars"] = pillar_dicts(rows)
    return result


def latest_run_id(db: Session, segment_id: int) -> int | None:
    return db.scalars(
        select(AllocationRun.id)
        .where(AllocationRun.segment_id == segment_id)
        .order_by(AllocationRun.id.desc())
    ).first()


def persist_run(db: Session, segment_id: int, result: dict) -> int:
    """Explicit historical snapshot. Caller is responsible for flushing its own
    writes first so the snapshot sees the same transaction's changes."""
    run = AllocationRun(
        segment_id=segment_id,
        created_at=datetime.utcnow(),
        result_json=json.dumps(result, ensure_ascii=False),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run.id


def validate_new_pillar(
    seg: Segment, position_m: float, thickness_m: float, existing: list[Pillar]
) -> None:
    """Reject writes that would make the forbidden union irrecoverable:
    non-positive thickness, boundary clipping, or touching/overlapping pillars.
    """
    if thickness_m <= 0:
        raise HTTPException(400, "挡柱厚度必须为正数")
    half = thickness_m / 2.0
    lo, hi = position_m - half, position_m + half
    if lo <= EDGE_EPS or hi >= seg.width_m - EDGE_EPS:
        raise HTTPException(
            400, "挡柱不得超出或贴合街段边界（禁入区间会被截断而不可逆）"
        )
    for p in existing:
        p_lo = p.position_m - p.thickness_m / 2.0
        p_hi = p.position_m + p.thickness_m / 2.0
        # A strictly positive gap is required: equality means the intervals
        # touch, and the union merge would erase the shared endpoint.
        if not (hi < p_lo or lo > p_hi):
            raise HTTPException(
                409, "与既有挡柱禁入区间相接或重叠，禁入并集不可逆"
            )
