from datetime import date

import pytest

from app.services.first_fit_engine import (
    REJECT_REASON,
    allocate_first_fit,
    forbidden_union_from_pillars,
    free_spans_from_pillars,
    open_intervals,
    pillar_centers_from_forbidden,
    result_to_dict,
)
from tests.golden import (
    BASELINE,
    EXTRA_SCENARIOS,
    INSERT15,
    INSERT15_PILLAR,
    INSERT15_PILLARS_SHUFFLED,
    IRRECOVERABLE,
    SEGMENT_WIDTH,
    SEED_PILLARS,
    SEED_PILLARS_SHUFFLED,
    SEED_VENDORS,
    assert_alloc_matches,
)


def _alloc(width, vendors, pillars):
    return result_to_dict(allocate_first_fit(width, vendors, pillars))


# --- Baseline: seed streets must match the live ("绿仓") result row for row. ---
def test_seed_baseline_matches_live_golden():
    data = _alloc(SEGMENT_WIDTH, SEED_VENDORS, SEED_PILLARS)
    assert_alloc_matches(BASELINE, data)
    # placements and rejected partition the vendor set: one product per vendor,
    # from the same single pass.
    p_ids = {p["vendor_id"] for p in data["placements"]}
    r_ids = {r["vendor_id"] for r in data["rejected"]}
    assert p_ids | r_ids == {v["id"] for v in SEED_VENDORS}
    assert p_ids & r_ids == set()
    assert data["rejected"][0]["reason"] == REJECT_REASON


# --- Fixture (a): flush-to-pillar; (b): contention variants. ---
@pytest.mark.parametrize("scenario", EXTRA_SCENARIOS, ids=[s["name"] for s in EXTRA_SCENARIOS])
def test_engine_scenarios(scenario):
    data = _alloc(scenario["width"], scenario["vendors"], scenario["pillars"])
    assert_alloc_matches(scenario["expect"], data)


def test_flush_to_pillar_endpoints_are_exact_pillar_edges():
    r = allocate_first_fit(10.0, EXTRA_SCENARIOS[0]["vendors"], EXTRA_SCENARIOS[0]["pillars"])
    assert r.placements[0].end_m == 4.5
    assert r.placements[1].start_m == 5.5
    assert r.free_spans == []


# --- Fixture (c): inserting a pillar at 15m splits the segment and moves both
#     the rejected set and every changed placement together. ---
def test_insert_pillar_at_15_golden():
    data = _alloc(SEGMENT_WIDTH, SEED_VENDORS, SEED_PILLARS + [INSERT15_PILLAR])
    assert_alloc_matches(INSERT15, data)


def test_insert_pillar_changes_rejected_and_placements_together():
    before = _alloc(SEGMENT_WIDTH, SEED_VENDORS, SEED_PILLARS)
    after = _alloc(SEGMENT_WIDTH, SEED_VENDORS, SEED_PILLARS + [INSERT15_PILLAR])
    before_r = {r["vendor_id"] for r in before["rejected"]}
    after_r = {r["vendor_id"] for r in after["rejected"]}
    assert before_r == {7}
    assert after_r == {3, 7}          # 老周水果 joins; nothing else changes
    assert after_r - before_r == {3}

    def by_vendor(data):
        return {p["vendor_id"]: (p["start_m"], p["end_m"]) for p in data["placements"]}

    b, a = by_vendor(before), by_vendor(after)
    assert a[1] == b[1] == (0.0, 4.0)    # 阿强烧烤 unmoved
    assert a[2] == b[2] == (4.0, 7.0)    # 林记糖水 unmoved
    assert a[4] == b[4] == (7.0, 9.5)    # 小美饰品 unmoved
    assert b[5] == (10.25, 16.25) and a[5] == (20.25, 26.25)  # 大碗面 jumps right
    assert b[3] == (20.25, 25.25) and 3 not in a             # 老周水果 now rejected
    assert b[6] == (16.25, 19.75) and a[6] == (10.25, 13.75)  # 手作皮具 moves left
    assert len(before["free_spans"]) == 2
    assert len(after["free_spans"]) == 4


# --- Fixture (d): shuffled pillar order yields the identical forbidden union. ---
def test_shuffled_pillars_give_same_union():
    canonical = forbidden_union_from_pillars(SEGMENT_WIDTH, SEED_PILLARS)
    shuffled = forbidden_union_from_pillars(SEGMENT_WIDTH, SEED_PILLARS_SHUFFLED)
    assert shuffled == canonical
    with15 = forbidden_union_from_pillars(
        SEGMENT_WIDTH, SEED_PILLARS + [INSERT15_PILLAR]
    )
    with15_shuffled = forbidden_union_from_pillars(
        SEGMENT_WIDTH, INSERT15_PILLARS_SHUFFLED
    )
    assert with15_shuffled == with15


def test_pillar_centers_round_trip_within_tolerance():
    for pillars, expected in (
        (SEED_PILLARS, (10.0, 20.0)),
        (SEED_PILLARS + [INSERT15_PILLAR], (10.0, 15.0, 20.0)),
    ):
        union = forbidden_union_from_pillars(SEGMENT_WIDTH, pillars)
        recovered = pillar_centers_from_forbidden(union, 0.5, SEGMENT_WIDTH)
        assert len(recovered) == len(expected)
        for got, want in zip(recovered, expected):
            assert abs(got - want) <= 1e-6


def test_shuffled_input_recovers_same_centers():
    union = forbidden_union_from_pillars(SEGMENT_WIDTH, INSERT15_PILLARS_SHUFFLED)
    assert pillar_centers_from_forbidden(union, 0.5, SEGMENT_WIDTH) == (10.0, 15.0, 20.0)


@pytest.mark.parametrize("pillars", IRRECOVERABLE)
def test_irrecoverable_unions_raise(pillars):
    union = forbidden_union_from_pillars(SEGMENT_WIDTH, pillars)
    with pytest.raises(ValueError):
        pillar_centers_from_forbidden(union, 0.5, SEGMENT_WIDTH)


def test_result_dict_carries_pipeline_stages():
    data = _alloc(SEGMENT_WIDTH, SEED_VENDORS, SEED_PILLARS)
    assert set(data) == {
        "placements", "rejected", "free_spans", "forbidden", "open_intervals"
    }
    assert [(s["start_m"], s["end_m"]) for s in data["forbidden"]] == BASELINE["forbidden"]
    assert [(s["start_m"], s["end_m"]) for s in data["open_intervals"]] == BASELINE["open_intervals"]


# --- Legacy tests (kept verbatim in spirit; exercise the wrapper too). ------
def test_free_spans_with_pillars():
    spans = free_spans_from_pillars(
        30.0,
        [{"position_m": 10.0, "thickness_m": 0.5},
         {"position_m": 20.0, "thickness_m": 0.5}],
    )
    assert len(spans) == 3
    assert spans[0][0] == 0.0


def test_open_intervals_is_complement_of_forbidden():
    forbidden = forbidden_union_from_pillars(30.0, SEED_PILLARS)
    assert open_intervals(30.0, forbidden) == (
        (0.0, 9.75), (10.25, 19.75), (20.25, 30.0)
    )


def test_first_fit_no_cross_pillar():
    vendors = [
        {"id": 1, "name": "A", "stall_width_m": 4.0, "priority": 1},
        {"id": 2, "name": "B", "stall_width_m": 12.0, "priority": 1},
    ]
    r = allocate_first_fit(30.0, vendors, [{"position_m": 10.0, "thickness_m": 0.5}])
    assert any(p.vendor_name == "A" for p in r.placements)
    assert len(r.placements) + len(r.rejected) == 2


def test_reject_oversized():
    vendors = [{"id": 1, "name": "Huge", "stall_width_m": 25.0, "priority": 1}]
    r = allocate_first_fit(
        30.0, vendors,
        [{"position_m": 10.0, "thickness_m": 0.5},
         {"position_m": 20.0, "thickness_m": 0.5}],
    )
    assert len(r.rejected) == 1
    assert r.rejected[0].vendor_name == "Huge"
