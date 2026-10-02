"""1D First-Fit stall placement along a street segment.

Pipeline (pure functions, no caching, no I/O):
    pillars -> forbidden union -> open intervals -> priority-ordered left fill

Placements and the rejected list are produced in ONE pass over the very same
mutable open-interval state: there is no separate "gap list" pass followed by a
second filler that could drift out of alignment.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

# Internal geometric tolerance. Kept identical to the live system so the seed
# baseline is reproduced bit-for-bit (e.g. a 3.5m stall ending exactly on a
# pillar edge fits only thanks to this slack).
FIT_EPS = 1e-9
# Spans narrower than this are treated as empty in the serialized remainder.
DEBRIS_EPS = 1e-6
# Inverse-reconstruction tolerance (see pillar_centers_from_forbidden).
RECOVER_EPS = 1e-6
REJECT_REASON = "无连续空档可放下且不跨越挡柱"

Interval = tuple[float, float]


@dataclass
class Placement:
    vendor_id: int
    vendor_name: str
    start_m: float
    end_m: float
    width_m: float


@dataclass
class Rejected:
    vendor_id: int
    vendor_name: str
    width_m: float
    reason: str


@dataclass
class AllocResult:
    placements: list[Placement]
    rejected: list[Rejected]
    free_spans: list[Interval]
    forbidden: tuple[Interval, ...] = ()
    open_intervals: tuple[Interval, ...] = ()


def forbidden_union_from_pillars(width_m: float, pillars: list[dict]) -> tuple[Interval, ...]:
    """Pillar centers + known thicknesses -> normalized union of forbidden
    (blocked) closed intervals, clipped to [0, width_m], touching/overlapping
    intervals merged. Output is order-independent (sorted + merged)."""
    blocked: list[Interval] = []
    for p in pillars:
        half = p.get("thickness_m", 0.4) / 2.0
        lo = max(0.0, p["position_m"] - half)
        hi = min(width_m, p["position_m"] + half)
        if hi > lo:
            blocked.append((lo, hi))
    blocked.sort()
    merged: list[list[float]] = []
    for lo, hi in blocked:
        # Strictly greater: intervals that merely touch are merged too, so the
        # shared endpoint disappears (matching the live gap-cutting behaviour).
        if not merged or lo > merged[-1][1]:
            merged.append([lo, hi])
        else:
            merged[-1][1] = max(merged[-1][1], hi)
    return tuple((lo, hi) for lo, hi in merged)


def open_intervals(width_m: float, forbidden: tuple[Interval, ...]) -> tuple[Interval, ...]:
    """Complement of the forbidden union within [0, width_m].

    A stall may end exactly on a pillar edge (fit is a length comparison with
    FIT_EPS slack), so an open interval wide enough admits a flush-to-pillar
    placement without touching the pillar body.
    """
    spans: list[Interval] = []
    cursor = 0.0
    for lo, hi in forbidden:
        if lo > cursor:
            spans.append((cursor, lo))
        cursor = hi
    if cursor < width_m:
        spans.append((cursor, width_m))
    return tuple(spans)


def pillar_centers_from_forbidden(
    forbidden: tuple[Interval, ...],
    thickness_m: float,
    width_m: float | None = None,
) -> tuple[float, ...]:
    """Inverse of forbidden_union_from_pillars for the recoverable domain:
    each forbidden component must be exactly one pillar of the given thickness,
    strictly inside the segment (no boundary clipping). Then its center is
    trivially the component midpoint.

    Raises ValueError on an irrecoverable union (merged touching/overlapping
    pillars, or a pillar clipped by a segment edge) instead of silently
    returning wrong centers. Not used on the production allocation path.
    """
    centers: list[float] = []
    for lo, hi in forbidden:
        if abs((hi - lo) - thickness_m) > RECOVER_EPS:
            raise ValueError(
                f"禁入并集不可逆：区间[{lo},{hi}]长度不等于单根挡柱厚度{thickness_m}，"
                "端点已因相接或重叠而消失"
            )
        if width_m is not None and (lo <= RECOVER_EPS or hi >= width_m - RECOVER_EPS):
            raise ValueError(
                f"禁入并集不可逆：区间[{lo},{hi}]贴合或越过街段边界，外侧端点已被截断"
            )
        centers.append(round((lo + hi) / 2.0, 6))
    return tuple(centers)


def allocate_first_fit(width_m: float, vendors: list[dict], pillars: list[dict]) -> AllocResult:
    """Vendors sorted by priority ascending then id; each needs stall_width_m
    contiguous inside one open interval (no pillar crossing). First fit from
    the left. Placements and rejects are the if/else of the same single pass."""
    forbidden = forbidden_union_from_pillars(width_m, pillars)
    intervals = open_intervals(width_m, forbidden)
    # The one and only mutable state: remaining capacity inside each opening.
    remain = [[a, b] for a, b in intervals]
    ordered = sorted(vendors, key=lambda v: (v.get("priority", 1), v["id"]))
    placements: list[Placement] = []
    rejected: list[Rejected] = []
    for v in ordered:
        need = float(v["stall_width_m"])
        for span in remain:
            if span[1] - span[0] + FIT_EPS >= need:
                start = span[0]
                end = start + need
                placements.append(
                    Placement(v["id"], v["name"], round(start, 3), round(end, 3), need)
                )
                span[0] = end
                break
        else:
            rejected.append(Rejected(v["id"], v["name"], need, REJECT_REASON))
    free = [(a, b) for a, b in remain if b - a > DEBRIS_EPS]
    return AllocResult(placements, rejected, free, forbidden, intervals)


def free_spans_from_pillars(width_m: float, pillars: list[dict]) -> list[Interval]:
    """Backward-compatible thin wrapper over the two-stage pure pipeline."""
    return list(open_intervals(width_m, forbidden_union_from_pillars(width_m, pillars)))


def _span_dicts(spans) -> list[dict]:
    return [{"start_m": round(a, 3), "end_m": round(b, 3)} for a, b in spans]


def result_to_dict(r: AllocResult) -> dict:
    return {
        "placements": [asdict(p) for p in r.placements],
        "rejected": [asdict(x) for x in r.rejected],
        "free_spans": _span_dicts(r.free_spans),
        "forbidden": _span_dicts(r.forbidden),
        "open_intervals": _span_dicts(r.open_intervals),
    }
