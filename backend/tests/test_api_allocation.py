"""现网分配入口侧：同一批夹具经真实 FastAPI 路由跑 HTTP，
与纯引擎 test_first_fit_engine.py 的结论逐条咬合。

这里不允许出现第二套分配实现或放宽口径——只调 /allocate/run、
/pillars、/allocate/latest 三个现网入口。
"""
from __future__ import annotations

from tests.conftest import engine_result


def _placements(data):
    return [(p["vendor_name"], p["start_m"], p["end_m"]) for p in data["placements"]]


def _rejected(data):
    return [r["vendor_name"] for r in data["rejected"]]


def _assert_matches_engine(data, scenario, inserted=False):
    eng = engine_result(scenario, inserted=inserted)
    # 逐条咬合：名字、起终点、宽度
    assert [(p["vendor_name"], p["start_m"], p["end_m"], p["width_m"]) for p in data["placements"]] == \
        [(p.vendor_name, p.start_m, p.end_m, p.width_m) for p in eng.placements]
    assert [(r["vendor_name"], r["width_m"], r["reason"]) for r in data["rejected"]] == \
        [(r.vendor_name, r.width_m, r.reason) for r in eng.rejected]
    # 主图禁入块必须是本次禁入代数产出的那一份
    assert [(b["start_m"], b["end_m"]) for b in data["blocked_spans"]] == eng.blocked_spans
    assert _placements(data) == (
        scenario.inserted_expect_placements if inserted else scenario.expect_placements
    )
    assert _rejected(data) == (
        scenario.inserted_expect_rejected if inserted else scenario.expect_rejected
    )


def test_run_matches_engine_and_fixture(api_factory):
    """/allocate/run 与引擎直算、夹具期望三者一致（含乱序柱）。"""
    client, scenario = api_factory
    res = client.post("/api/allocate/run", params={"segment_id": 1})
    assert res.status_code == 200
    data = res.json()
    _assert_matches_engine(data, scenario)


def test_latest_reuses_run_before_pillar_change(api_factory):
    """未插柱时 /allocate/latest 与 run 同一结论（绿仓放置一致）。"""
    client, scenario = api_factory
    run = client.post("/api/allocate/run", params={"segment_id": 1}).json()
    latest = client.get("/api/allocate/latest", params={"segment_id": 1}).json()
    assert latest["id"] == run["id"]  # 柱未变，不吃重算，但结论相同
    _assert_matches_engine(latest, scenario)


def test_insert_pillar_then_latest_recomputes(api_factory):
    """插柱后再分：/allocate/latest 必须按新柱瞬时重算，禁止吃旧禁入缓存。

    放不下集合与主图色块（blocked_spans）必须一起变。
    """
    client, scenario = api_factory
    before = client.post("/api/allocate/run", params={"segment_id": 1}).json()

    if not scenario.inserted:
        # 无插柱步骤的夹具：验证 latest 仍返回旧 run
        latest = client.get("/api/allocate/latest", params={"segment_id": 1}).json()
        assert latest["id"] == before["id"]
        return

    for p in scenario.inserted:
        added = client.post("/api/pillars", json={
            "segment_id": 1, "position_m": p.position_m,
            "thickness_m": p.thickness_m, "label": p.label,
        })
        assert added.status_code == 201

    # 不手动点“重新分配”，latest 自己识别柱变了并按新柱重算
    after = client.get("/api/allocate/latest", params={"segment_id": 1}).json()
    assert after["id"] != before["id"], "插柱后必须产生新一次分配，不得返回旧缓存"
    _assert_matches_engine(after, scenario, inserted=True)

    # 色块与放不下“一起变”：禁入并集新增段，放不下名单同时变化
    assert len(after["blocked_spans"]) == len(before["blocked_spans"]) + len(scenario.inserted)
    assert _rejected(after) != _rejected(before)
    # 再取一次 latest：柱未再变，应稳定复用刚重算的 run
    again = client.get("/api/allocate/latest", params={"segment_id": 1}).json()
    assert again["id"] == after["id"]
    _assert_matches_engine(again, scenario, inserted=True)


def test_rerun_after_insert_matches_latest(api_factory):
    """插柱后显式 /allocate/run 与 latest 的结论也必须咬合。"""
    client, scenario = api_factory
    if not scenario.inserted:
        return
    for p in scenario.inserted:
        client.post("/api/pillars", json={
            "segment_id": 1, "position_m": p.position_m,
            "thickness_m": p.thickness_m, "label": p.label,
        })
    rerun = client.post("/api/allocate/run", params={"segment_id": 1}).json()
    _assert_matches_engine(rerun, scenario, inserted=True)


def test_insert_pillar_rejects_bad_position(api_factory):
    client, scenario = api_factory
    bad = client.post("/api/pillars", json={
        "segment_id": 1, "position_m": scenario.width_m + 5,
        "thickness_m": 0.4, "label": "界外柱",
    })
    assert bad.status_code == 422
    thin = client.post("/api/pillars", json={
        "segment_id": 1, "position_m": 1, "thickness_m": 0,
    })
    assert thin.status_code == 422
