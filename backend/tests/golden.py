"""Single source of truth for fixtures and golden expectations.

Imported by BOTH the engine unit tests and the HTTP API tests: the exact same
scenario dicts are fed to allocate_first_fit() directly and through the live
/ allocate endpoints, then compared with the same assert_alloc_matches helper,
so the two paths cannot quietly use different, loosened criteria.

All coordinates are post-round(3) values; quarters/tenths used here are exactly
representable, so tuple equality (not approx) is an intentional strict bite.
"""
from app.services.first_fit_engine import REJECT_REASON

SEGMENT_WIDTH = 30.0

SEED_PILLARS = [
    {"position_m": 10.0, "thickness_m": 0.5},
    {"position_m": 20.0, "thickness_m": 0.5},
]

# Insertion order == seed vendor ids 1..7; the engine re-sorts by (priority,id).
SEED_VENDORS = [
    {"id": 1, "name": "阿强烧烤", "stall_width_m": 4.0, "priority": 1},
    {"id": 2, "name": "林记糖水", "stall_width_m": 3.0, "priority": 1},
    {"id": 3, "name": "老周水果", "stall_width_m": 5.0, "priority": 2},
    {"id": 4, "name": "小美饰品", "stall_width_m": 2.5, "priority": 2},
    {"id": 5, "name": "大碗面", "stall_width_m": 6.0, "priority": 1},
    {"id": 6, "name": "手作皮具", "stall_width_m": 3.5, "priority": 3},
    {"id": 7, "name": "巨型舞台车", "stall_width_m": 12.0, "priority": 9},
]

# --- Baseline ("绿仓放置"): no extra pillar, must match live row-for-row. ---
BASELINE = {
    "forbidden": [(9.75, 10.25), (19.75, 20.25)],
    "open_intervals": [(0.0, 9.75), (10.25, 19.75), (20.25, 30.0)],
    "placements": [
        (1, 0.0, 4.0, 4.0),      # 阿强烧烤
        (2, 4.0, 7.0, 3.0),      # 林记糖水
        (5, 10.25, 16.25, 6.0),  # 大碗面 (span1 only 2.75 left)
        (3, 20.25, 25.25, 5.0),  # 老周水果 (2.75 / 3.5 both too short)
        (4, 7.0, 9.5, 2.5),      # 小美饰品 back to span1
        (6, 16.25, 19.75, 3.5),  # 手作皮具, span2 exactly 3.5 (FIT_EPS)
    ],
    "rejected": [
        (7, 12.0, REJECT_REASON),  # 巨型舞台车
    ],
    "free_spans": [(9.5, 9.75), (25.25, 30.0)],
}

# --- Insert one more pillar at 15m (thickness 0.5): it splits the middle. ---
INSERT15_PILLAR = {"position_m": 15.0, "thickness_m": 0.5}

INSERT15 = {
    "forbidden": [(9.75, 10.25), (14.75, 15.25), (19.75, 20.25)],
    "open_intervals": [(0.0, 9.75), (10.25, 14.75), (15.25, 19.75), (20.25, 30.0)],
    "placements": [
        (1, 0.0, 4.0, 4.0),
        (2, 4.0, 7.0, 3.0),
        (5, 20.25, 26.25, 6.0),  # 6m: 2.75 / 4.5 / 4.5 all too short
        (4, 7.0, 9.5, 2.5),
        (6, 10.25, 13.75, 3.5),  # first 3.5 fit in the new 4.5 span
    ],
    "rejected": [
        (3, 5.0, REJECT_REASON),   # 老周水果 now joins the rejected set
        (7, 12.0, REJECT_REASON),
    ],
    "free_spans": [(9.5, 9.75), (13.75, 14.75), (15.25, 19.75), (26.25, 30.0)],
}

# --- Fixture (a): flush-to-pillar fit (stall end exactly on the pillar edge). ---
FLUSH_SCENARIO = {
    "name": "flush_to_pillar",
    "width": 10.0,
    "pillars": [{"position_m": 5.0, "thickness_m": 1.0}],
    "vendors": [
        {"id": 1, "name": "贴左", "stall_width_m": 4.5, "priority": 1},
        {"id": 2, "name": "贴右", "stall_width_m": 4.5, "priority": 1},
    ],
    "expect": {
        "forbidden": [(4.5, 5.5)],
        "open_intervals": [(0.0, 4.5), (5.5, 10.0)],
        "placements": [(1, 0.0, 4.5, 4.5), (2, 5.5, 10.0, 4.5)],
        "rejected": [],
        "free_spans": [],
    },
}

# --- Fixture (b): two stalls contend for the same inter-pillar opening. ------
# Different priorities: higher priority (lower number) takes the 9m middle.
CONTEST_PRIORITY_SCENARIO = {
    "name": "contest_priority",
    "width": 20.0,
    "pillars": [{"position_m": 5.0, "thickness_m": 1.0},
                {"position_m": 15.0, "thickness_m": 1.0}],
    "vendors": [
        {"id": 1, "name": "甲摊", "stall_width_m": 6.0, "priority": 2},
        {"id": 2, "name": "乙摊", "stall_width_m": 6.0, "priority": 1},
    ],
    "expect": {
        "forbidden": [(4.5, 5.5), (14.5, 15.5)],
        "open_intervals": [(0.0, 4.5), (5.5, 14.5), (15.5, 20.0)],
        "placements": [(2, 5.5, 11.5, 6.0)],
        "rejected": [(1, 6.0, REJECT_REASON)],
        "free_spans": [(0.0, 4.5), (11.5, 14.5), (15.5, 20.0)],
    },
}

# Same priority: id order breaks the tie, id 1 wins the middle.
CONTEST_TIE_SCENARIO = {
    "name": "contest_tie",
    "width": 20.0,
    "pillars": [{"position_m": 5.0, "thickness_m": 1.0},
                {"position_m": 15.0, "thickness_m": 1.0}],
    "vendors": [
        {"id": 1, "name": "甲摊", "stall_width_m": 6.0, "priority": 1},
        {"id": 2, "name": "乙摊", "stall_width_m": 6.0, "priority": 1},
    ],
    "expect": {
        "forbidden": [(4.5, 5.5), (14.5, 15.5)],
        "open_intervals": [(0.0, 4.5), (5.5, 14.5), (15.5, 20.0)],
        "placements": [(1, 5.5, 11.5, 6.0)],
        "rejected": [(2, 6.0, REJECT_REASON)],
        "free_spans": [(0.0, 4.5), (11.5, 14.5), (15.5, 20.0)],
    },
}

# Wider segment: the loser does not reject — first-fit carries it into the
# next opening (15.5–21.5).
CONTEST_OVERFLOW_SCENARIO = {
    "name": "contest_overflow",
    "width": 25.0,
    "pillars": [{"position_m": 5.0, "thickness_m": 1.0},
                {"position_m": 15.0, "thickness_m": 1.0}],
    "vendors": [
        {"id": 1, "name": "甲摊", "stall_width_m": 6.0, "priority": 2},
        {"id": 2, "name": "乙摊", "stall_width_m": 6.0, "priority": 1},
    ],
    "expect": {
        "forbidden": [(4.5, 5.5), (14.5, 15.5)],
        "open_intervals": [(0.0, 4.5), (5.5, 14.5), (15.5, 25.0)],
        "placements": [(2, 5.5, 11.5, 6.0), (1, 15.5, 21.5, 6.0)],
        "rejected": [],
        "free_spans": [(0.0, 4.5), (11.5, 14.5), (21.5, 25.0)],
    },
}

EXTRA_SCENARIOS = [
    FLUSH_SCENARIO,
    CONTEST_PRIORITY_SCENARIO,
    CONTEST_TIE_SCENARIO,
    CONTEST_OVERFLOW_SCENARIO,
]

# --- Fixture: unions from shuffled pillar input must be identical. ----------
SEED_PILLARS_SHUFFLED = [
    {"position_m": 20.0, "thickness_m": 0.5},
    {"position_m": 10.0, "thickness_m": 0.5},
]
INSERT15_PILLARS_SHUFFLED = [
    {"position_m": 20.0, "thickness_m": 0.5},
    {"position_m": 10.0, "thickness_m": 0.5},
    {"position_m": 15.0, "thickness_m": 0.5},
]

# --- Fixture: irrecoverable geometries -> pillar_centers_from_forbidden must raise.
IRRECOVERABLE = [
    # touching: [9.75,10.25] + [10.25,10.75] merge into a 1.0 component
    [{"position_m": 10.0, "thickness_m": 0.5},
     {"position_m": 10.5, "thickness_m": 0.5}],
    # overlapping: merged component is 0.75 wide
    [{"position_m": 10.0, "thickness_m": 0.5},
     {"position_m": 10.25, "thickness_m": 0.5}],
    # edge-clipped: forbidden starts at 0, outer endpoint lost
    [{"position_m": 0.1, "thickness_m": 0.5}],
]


def assert_alloc_matches(expect: dict, data: dict) -> None:
    """Compare a serialized allocation (engine result_to_dict or HTTP JSON)
    against the golden expectation, row for row."""
    got_p = [
        (p["vendor_id"], p["start_m"], p["end_m"], p["width_m"])
        for p in data["placements"]
    ]
    assert got_p == expect["placements"]
    got_r = [
        (r["vendor_id"], r["width_m"], r["reason"])
        for r in data["rejected"]
    ]
    assert got_r == expect["rejected"]
    for key in ("free_spans", "forbidden", "open_intervals"):
        if key in expect:
            got_s = [(s["start_m"], s["end_m"]) for s in data[key]]
            assert got_s == expect[key], key
