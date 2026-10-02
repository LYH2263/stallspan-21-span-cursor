import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import AllocationRun, Pillar, Segment, Vendor
from app.services.first_fit_engine import allocate_first_fit, result_to_dict
router = APIRouter(prefix="/allocate", tags=["allocate"])


def _sig_key(sig: dict) -> str:
    # 经 JSON 往返后元组会变列表，统一规范化成排序后的 JSON 串再比对
    return json.dumps(sig, sort_keys=True, ensure_ascii=False)


def _current_inputs(segment_id: int, db: Session):
    seg = db.get(Segment, segment_id)
    if not seg:
        raise HTTPException(404, "街段不存在")
    pillars = db.scalars(
        select(Pillar).where(Pillar.segment_id == segment_id).order_by(Pillar.id)
    ).all()
    vendors = db.scalars(
        select(Vendor).where(Vendor.market_day_id == seg.market_day_id).order_by(Vendor.id)
    ).all()
    return seg, pillars, vendors


def _signature(width_m: float, pillars, vendors) -> dict:
    """当前柱/摊/段宽的瞬时指纹；与最近一次产出所记录的指纹不同即重算。"""
    return {
        "width_m": round(float(width_m), 6),
        "pillars": sorted(
            (round(float(p.position_m), 6), round(float(p.thickness_m), 6)) for p in pillars
        ),
        "vendors": sorted(
            (v.id, round(float(v.stall_width_m), 6), int(v.priority)) for v in vendors
        ),
    }


def _compute(segment_id: int, db: Session, persist: bool) -> dict:
    seg, pillars, vendors = _current_inputs(segment_id, db)
    pillar_dicts = [{"position_m": p.position_m, "thickness_m": p.thickness_m} for p in pillars]
    vendor_dicts = [
        {"id": v.id, "name": v.name, "stall_width_m": v.stall_width_m, "priority": v.priority}
        for v in vendors
    ]
    # placements 与 rejected 取自同一次禁入代数，不存在第二套放宽口径
    result = result_to_dict(allocate_first_fit(seg.width_m, vendor_dicts, pillar_dicts))
    result["segment"] = {"id": seg.id, "name": seg.name, "width_m": seg.width_m}
    # 主图禁入块以 result.blocked_spans 为准；此处柱表仅用于标注名称
    result["pillars"] = [
        {"id": p.id, "position_m": p.position_m, "thickness_m": p.thickness_m, "label": p.label}
        for p in pillars
    ]
    result["input_signature"] = _signature(seg.width_m, pillars, vendors)

    if persist:
        run = AllocationRun(segment_id=segment_id, created_at=datetime.utcnow(),
                            result_json=json.dumps(result, ensure_ascii=False))
        db.add(run)
        db.commit()
        db.refresh(run)
        return {"id": run.id, **result}
    return result


@router.post("/run")
def run_allocate(segment_id: int = 1, db: Session = Depends(get_db)):
    return _compute(segment_id, db, persist=True)


@router.get("/latest")
def latest(segment_id: int = 1, db: Session = Depends(get_db)):
    run = db.scalars(select(AllocationRun).where(AllocationRun.segment_id == segment_id)
                     .order_by(AllocationRun.id.desc())).first()
    if not run:
        return _compute(segment_id, db, persist=True)
    data = json.loads(run.result_json)
    seg, pillars, vendors = _current_inputs(segment_id, db)
    # 柱被插/被改后指纹必变：按当前柱瞬时重算并落一次新 run，绝不吃旧禁入缓存
    if _sig_key(data.get("input_signature", {})) != _sig_key(_signature(seg.width_m, pillars, vendors)):
        return _compute(segment_id, db, persist=True)
    return {"id": run.id, **data}
