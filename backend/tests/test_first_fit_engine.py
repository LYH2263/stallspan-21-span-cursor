"""引擎侧：柱列表 -> 禁入并集 -> 可用开区间 -> 优先序从左填空。

所有场景取自共享夹具 scenarios.SCENARIOS；与 test_api_allocation 的现网
入口跑同一批数据，两边结论必须咬合。
"""
from __future__ import annotations

import random

import pytest

from app.services.first_fit_engine import (
    EPS,
    allocate_first_fit,
    forbidden_union,
    free_spans_from_pillars,
    free_spans_from_union,
    pillar_centers_from_union,
)

from tests.conftest import engine_result, scenario_pillar_dicts, scenario_vendor_dicts


def _names(rows, attr):
    return [getattr(r, attr) for r in rows]


# ---------- 禁入并集 -> 开区间 ----------

def test_seed_forbidden_union_endpoints():
    """种子东街段两灯柱：禁入并集端点必须就是 ±厚度/2。"""
    from tests.scenarios import SEED_PILLARS, WIDTH
    blocked = forbidden_union(WIDTH, [
        {"position_m": p.position_m, "thickness_m": p.thickness_m} for p in SEED_PILLARS
    ])
    assert blocked == [(9.75, 10.25), (19.75, 20.25)]
    assert free_spans_from_union(WIDTH, blocked) == [(0.0, 9.75), (10.25, 19.75), (20.25, 30.0)]


def test_union_order_independent():
    """打乱柱序仍得同一禁入并集。"""
    from tests.scenarios import SEED_PILLARS, WIDTH
    rows = [{"position_m": p.position_m, "thickness_m": p.thickness_m} for p in SEED_PILLARS]
    base = forbidden_union(WIDTH, rows)
    shuffled = rows[:]
    random.Random(1234).shuffle(shuffled)
    shuffled.append(shuffled.pop(0))
    assert forbidden_union(WIDTH, shuffled) == base
    # 旧入口语义保持不变
    assert free_spans_from_pillars(WIDTH, shuffled) == free_spans_from_pillars(WIDTH, rows)


def test_union_merges_touching_same_thickness():
    """同厚柱相切/相接要并段（并集语义）；但一旦真正并成一段，
    单靠并集端点已无法区分“一根厚柱”还是“两根柱”，逆函数必须算失败。"""
    blocked = forbidden_union(20.0, [
        {"position_m": 5.0, "thickness_m": 1.0},   # [4.5, 5.5]
        {"position_m": 6.0, "thickness_m": 1.0},   # [5.5, 6.5] 端点相接
    ])
    assert blocked == [(4.5, 6.5)]
    with pytest.raises(ValueError):
        pillar_centers_from_union(blocked, 1.0)
    # 开区间补集不受影响：柱仍挡住 [4.5, 6.5]
    assert free_spans_from_union(20.0, blocked) == [(0.0, 4.5), (6.5, 20.0)]


def test_union_rejects_mixed_thickness_touching():
    """不同厚度的禁入区间相接会导致端点不可逆——必须算失败（抛错），不许硬并。"""
    with pytest.raises(ValueError):
        forbidden_union(20.0, [
            {"position_m": 5.0, "thickness_m": 1.0},
            {"position_m": 5.6, "thickness_m": 0.4},
        ])


# ---------- 可逆还原柱心 ----------

@pytest.mark.parametrize("thickness", [0.4, 0.5, 1.0])
def test_pillar_centers_roundtrip(thickness):
    """禁入并集端点在厚度已知时可逆还原柱心，容差内一致。"""
    pillars = [{"position_m": x, "thickness_m": thickness} for x in (3.0, 11.0, 22.5)]
    blocked = forbidden_union(30.0, pillars)
    recovered = pillar_centers_from_union(blocked, thickness)
    for got, want in zip(recovered, (3.0, 11.0, 22.5)):
        assert abs(got - want) <= EPS


def test_pillar_centers_wrong_thickness_fails():
    """厚度对不上即不可逆——抛错，行数不增于失败路径。"""
    blocked = forbidden_union(30.0, [{"position_m": 10.0, "thickness_m": 0.5}])
    with pytest.raises(ValueError):
        pillar_centers_from_union(blocked, 0.4)
    with pytest.raises(ValueError):
        pillar_centers_from_union([(0.0, 0.0)], 0.4)
    with pytest.raises(ValueError):
        pillar_centers_from_union(blocked, 0.0)


# ---------- 逐场景落位/放不下，与绿仓逐条对齐 ----------

def test_scenario_placements_and_rejected(scenario):
    r = engine_result(scenario)
    got = [(p.vendor_name, p.start_m, p.end_m) for p in r.placements]
    assert got == scenario.expect_placements
    assert _names(r.rejected, "vendor_name") == scenario.expect_rejected
    # 没有摊主人间蒸发：落位 + 放不下 == 全部摊主
    assert len(r.placements) + len(r.rejected) == len(scenario.vendors)


def test_no_stall_touches_pillar(scenario):
    """每个落位都完整落在某个可用开区间内部，绝不压柱/跨柱。"""
    r = engine_result(scenario)
    for p in r.placements:
        assert any(
            a - EPS <= p.start_m and p.end_m <= b + EPS
            for a, b in free_spans_from_union(scenario.width_m, r.blocked_spans)
        ), f"{p.vendor_name} 压/跨挡柱"


def test_blocked_spans_drive_the_map(scenario):
    """主图禁入块与本次分配同源：blocked_spans 必须能由本结果柱心重建。"""
    r = engine_result(scenario)
    # 种子/夹具柱同厚（0.5），可逆还原柱心并与输入对齐
    centers = pillar_centers_from_union(r.blocked_spans, 0.5)
    want = sorted(p.position_m for p in scenario.pillars)
    assert centers == pytest.approx(want, abs=EPS)


def test_insert_pillar_splits_engine():
    """15m 再插柱拆段：放不下集合与色块（禁入并集）一起变。"""
    from tests.scenarios import INSERT15
    before = engine_result(INSERT15, inserted=False)
    after = engine_result(INSERT15, inserted=True)
    # 禁入并集多出一段，且按端点排序
    assert len(after.blocked_spans) == len(before.blocked_spans) + 1
    assert (14.8, 15.2) in after.blocked_spans
    got = [(p.vendor_name, p.start_m, p.end_m) for p in after.placements]
    assert got == INSERT15.inserted_expect_placements
    assert _names(after.rejected, "vendor_name") == INSERT15.inserted_expect_rejected
    # 真的多了一个放不下：老周水果由落位变拒绝
    assert "老周水果" not in _names(before.rejected, "vendor_name")
    assert "老周水果" in _names(after.rejected, "vendor_name")


def test_green_matches_seed_warehouse():
    """未插柱时与绿仓放置一致：直接对种子数据（与 seed.py 同形）重算。"""
    from tests.scenarios import GREEN
    r = engine_result(GREEN)
    assert [(p.vendor_name, p.start_m, p.end_m) for p in r.placements] == [
        ("阿强烧烤", 0.0, 4.0),
        ("林记糖水", 4.0, 7.0),
        ("大碗面", 10.25, 16.25),
        ("老周水果", 20.25, 25.25),
        ("小美饰品", 7.0, 9.5),
        ("手作皮具", 16.25, 19.75),
    ]
    assert _names(r.rejected, "vendor_name") == ["巨型舞台车"]


def test_legacy_oversized_reject_kept():
    """保留旧用例口径：25m 摊在两柱 30m 段必被拒。"""
    vendors = [{"id": 1, "name": "Huge", "stall_width_m": 25.0, "priority": 1}]
    pillars = [{"position_m": 10.0, "thickness_m": 0.5}, {"position_m": 20.0, "thickness_m": 0.5}]
    r = allocate_first_fit(30.0, vendors, pillars)
    assert len(r.rejected) == 1 and r.rejected[0].vendor_name == "Huge"
