"""1D First-Fit stall placement along a street segment; stalls cannot cross pillars.

单条流水线，放置结果与放不下结果同一次产出，严禁分开计算：

    柱列表 -> 禁入并集(blocked_spans) -> 可用开区间(free_spans)
           -> 摊主按 (priority, id) 排序，从左到右逐摊填第一个放得下的空档

禁入并集是唯一事实源：主图色块与放不下清单都取自同一次 AllocResult。
禁入并集端点在柱厚已知时可逆还原柱心（pillar_centers_from_union），
做不到可逆（厚度对不上等）即抛错，调用方按失败处理。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

EPS = 1e-9
ROUND = 3
DEFAULT_THICKNESS = 0.4


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
    free_spans: list[tuple[float, float]]
    # 本次分配所依据的禁入并集（已按端点排序、合并）；主图禁入块与本结果同源
    blocked_spans: list[tuple[float, float]]
    pillars: list[dict]


def _r(x: float) -> float:
    return round(float(x), ROUND)


def pillar_interval(width_m: float, position_m: float, thickness_m: float) -> tuple[float, float]:
    """单根柱在 [0, width_m] 上的禁入闭区间。"""
    half = thickness_m / 2.0
    lo = max(0.0, position_m - half)
    hi = min(width_m, position_m + half)
    return lo, hi


def forbidden_union(width_m: float, pillars: list[dict]) -> list[tuple[float, float]]:
    """柱列表 -> 禁入并集：把每根柱的 [心-厚/2, 心+厚/2] 夹到段内后排序合并。

    端点相接（含 EPS 容差）即并为一段；并入的区间厚度必须一致，
    否则并集端点无法可逆还原柱心，直接视为失败（ValueError）。
    """
    pieces: list[tuple[float, float, float]] = []
    for p in pillars:
        thickness = float(p.get("thickness_m", DEFAULT_THICKNESS))
        lo, hi = pillar_interval(width_m, float(p["position_m"]), thickness)
        if hi - lo > EPS:
            pieces.append((lo, hi, thickness))
    pieces.sort(key=lambda t: (t[0], t[1]))

    merged: list[list[float]] = []
    merged_thick: list[float] = []
    for lo, hi, thickness in pieces:
        if not merged or lo > merged[-1][1] + EPS:
            merged.append([lo, hi])
            merged_thick.append(thickness)
            continue
        if abs(thickness - merged_thick[-1]) > EPS:
            raise ValueError(
                f"禁入区间在 [{lo}, {hi}] 处与不同厚度 {merged_thick[-1]} 的柱相接/重叠，"
                "并集端点不可逆还原柱心"
            )
        merged[-1][1] = max(merged[-1][1], hi)
    return [(lo, hi) for lo, hi in merged]


def free_spans_from_union(
    width_m: float, blocked: list[tuple[float, float]]
) -> list[tuple[float, float]]:
    """禁入并集 -> 补集，即段内互不相交的可用开区间，按从左到右排序。"""
    spans: list[tuple[float, float]] = []
    cursor = 0.0
    for lo, hi in sorted(blocked):
        if lo - cursor > EPS:
            spans.append((cursor, lo))
        cursor = max(cursor, hi)
    if width_m - cursor > EPS:
        spans.append((cursor, width_m))
    return spans


def free_spans_from_pillars(width_m: float, pillars: list[dict]) -> list[tuple[float, float]]:
    """兼容旧调用：柱列表经禁入并集得到可用开区间。"""
    return free_spans_from_union(width_m, forbidden_union(width_m, pillars))


def pillar_centers_from_union(
    blocked: list[tuple[float, float]], thickness_m: float
) -> list[float]:
    """禁入并集端点 -> 柱心的可逆纯函数（柱厚已知）。

    每段并集必须恰为 [心-厚/2, 心+厚/2]（端点在 EPS 容差内一致）；
    任一段宽度与给定厚度对不上即抛 ValueError——做不到可逆就算失败。
    """
    if thickness_m <= 0:
        raise ValueError("柱厚必须为正")
    centers: list[float] = []
    for lo, hi in sorted(blocked):
        if abs((hi - lo) - thickness_m) > EPS:
            raise ValueError(
                f"禁入段 [{lo}, {hi}] 宽 {hi - lo} 与柱厚 {thickness_m} 不符，无法还原柱心"
            )
        centers.append((lo + hi) / 2.0)
    return centers


def allocate_first_fit(
    width_m: float, vendors: list[dict], pillars: list[dict]
) -> AllocResult:
    """单次禁入代数：同一轮内先得禁入并集，再按优先序从左填空。

    摊主按 (priority 升序, id 升序) 排队；每摊只放进第一个容得下的空档
    （不跨柱、不压柱），放入后该空档左沿右移；任何空档都放不下即进 rejected。
    placements 与 rejected 来自同一次遍历，不存在另写的放宽口径。
    """
    blocked = forbidden_union(width_m, pillars)
    spans = free_spans_from_union(width_m, blocked)

    ordered = sorted(vendors, key=lambda v: (v.get("priority", 1), v["id"]))
    remain = [[a, b] for a, b in spans]
    placements: list[Placement] = []
    rejected: list[Rejected] = []

    for v in ordered:
        need = float(v["stall_width_m"])
        for span in remain:
            if span[1] - span[0] + EPS >= need:
                start, end = span[0], span[0] + need
                placements.append(
                    Placement(v["id"], v["name"], _r(start), _r(end), _r(need))
                )
                span[0] = end
                break
        else:
            rejected.append(
                Rejected(v["id"], v["name"], _r(need), "无连续空档可放下且不跨越挡柱")
            )

    free = [(a, b) for a, b in remain if b - a > EPS]
    return AllocResult(
        placements=placements,
        rejected=rejected,
        free_spans=[(_r(a), _r(b)) for a, b in free],
        blocked_spans=[(_r(a), _r(b)) for a, b in blocked],
        pillars=[{"position_m": _r(p["position_m"]),
                  "thickness_m": _r(p.get("thickness_m", DEFAULT_THICKNESS))}
                 for p in pillars],
    )


def result_to_dict(r: AllocResult) -> dict:
    return {
        "placements": [asdict(p) for p in r.placements],
        "rejected": [asdict(x) for x in r.rejected],
        "free_spans": [{"start_m": a, "end_m": b} for a, b in r.free_spans],
        "blocked_spans": [{"start_m": a, "end_m": b} for a, b in r.blocked_spans],
        "pillars": r.pillars,
    }
