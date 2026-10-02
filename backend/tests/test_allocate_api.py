"""HTTP entry-point tests.

The SAME golden fixtures drive both allocate_first_fit() directly and the live
/ allocate endpoints; assert_alloc_matches is used on both, so the API path
cannot hide behind looser criteria than the engine.
"""
from datetime import date

from app.models.models import AllocationRun, MarketDay, Pillar, Segment, Vendor
from app.services.first_fit_engine import allocate_first_fit, result_to_dict
from tests.golden import (
    BASELINE,
    EXTRA_SCENARIOS,
    INSERT15,
    SEGMENT_WIDTH,
    SEED_PILLARS,
    SEED_VENDORS,
    assert_alloc_matches,
)

ALLOC_KEYS = ("placements", "rejected", "free_spans", "forbidden", "open_intervals")


def _payload(resp_json: dict) -> dict:
    return {k: resp_json[k] for k in ALLOC_KEYS}


def _run_count(session_factory, segment_id: int = 1) -> int:
    db = session_factory()
    try:
        return (
            db.query(AllocationRun)
            .filter(AllocationRun.segment_id == segment_id)
            .count()
        )
    finally:
        db.close()


def _remap_expect(expect: dict, actual_ids: list[int]) -> dict:
    """Golden scenarios use synthetic ids 1..n; map them to the DB-assigned
    vendor ids while keeping every coordinate/width/reason unchanged."""
    remap = {i + 1: actual_ids[i] for i in range(len(actual_ids))}
    out = dict(expect)
    out["placements"] = [
        (remap[vid], s, e, w) for vid, s, e, w in expect["placements"]
    ]
    out["rejected"] = [
        (remap[vid], w, reason) for vid, w, reason in expect["rejected"]
    ]
    return out


def _seed_scenario(session_factory, scenario: dict) -> tuple[int, list[int]]:
    db = session_factory()
    try:
        day = MarketDay(name=scenario["name"], day=date(2026, 9, 20))
        db.add(day)
        db.flush()
        seg = Segment(
            market_day_id=day.id, name=scenario["name"], width_m=scenario["width"]
        )
        db.add(seg)
        db.flush()
        ids = []
        for v in scenario["vendors"]:
            row = Vendor(
                market_day_id=day.id,
                name=v["name"],
                stall_width_m=v["stall_width_m"],
                priority=v["priority"],
            )
            db.add(row)
            db.flush()
            ids.append(row.id)
        for p in scenario["pillars"]:
            db.add(Pillar(segment_id=seg.id, position_m=p["position_m"],
                          thickness_m=p["thickness_m"], label="挡柱"))
        db.commit()
        return seg.id, ids
    finally:
        db.close()


# --- Baseline: live entry point matches the engine row for row. -------------
def test_run_endpoint_matches_engine_golden(client):
    direct = result_to_dict(
        allocate_first_fit(SEGMENT_WIDTH, SEED_VENDORS, SEED_PILLARS)
    )
    resp = client.post("/api/allocate/run?segment_id=1")
    assert resp.status_code == 200
    data = _payload(resp.json())
    assert data == direct            # identical, not merely "close"
    assert_alloc_matches(BASELINE, data)
    assert resp.json()["id"] is not None


def test_run_response_pillars_carry_id_and_label(client):
    resp = client.post("/api/allocate/run?segment_id=1").json()
    labels = {p["label"] for p in resp["pillars"]}
    assert labels == {"灯柱A", "灯柱B"}
    assert all({"id", "segment_id", "position_m", "thickness_m", "label"} <= set(p)
               for p in resp["pillars"])
    assert resp["segment"] == {"id": 1, "name": "东街段", "width_m": 30.0}


def test_latest_is_live_and_creates_no_run_rows(client, session_factory):
    assert _run_count(session_factory) == 0
    resp = client.get("/api/allocate/latest?segment_id=1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["live"] is True and body["id"] is None
    assert_alloc_matches(BASELINE, _payload(body))
    assert _run_count(session_factory) == 0     # browsing does not snapshot


def test_run_unknown_segment_404(client):
    assert client.post("/api/allocate/run?segment_id=999").status_code == 404
    assert client.get("/api/allocate/latest?segment_id=999").status_code == 404


# --- Same fixtures fed to the HTTP entry for the non-seed geometries. -------
def test_extra_scenarios_through_http_match_engine(client, session_factory):
    for scenario in EXTRA_SCENARIOS:
        seg_id, actual_ids = _seed_scenario(session_factory, scenario)
        # Rebuild the engine input with the exact rows the DB now holds.
        db = session_factory()
        try:
            seg = db.get(Segment, seg_id)
            vendors = [
                {"id": v.id, "name": v.name, "stall_width_m": v.stall_width_m,
                 "priority": v.priority}
                for v in db.query(Vendor).filter(Vendor.market_day_id == seg.market_day_id)
            ]
            pillars = [
                {"position_m": p.position_m, "thickness_m": p.thickness_m}
                for p in db.query(Pillar).filter(Pillar.segment_id == seg_id)
            ]
        finally:
            db.close()
        direct = result_to_dict(
            allocate_first_fit(scenario["width"], vendors, pillars)
        )
        resp = client.post(f"/api/allocate/run?segment_id={seg_id}")
        assert resp.status_code == 200, scenario["name"]
        http_data = _payload(resp.json())
        assert http_data == direct, scenario["name"]
        assert_alloc_matches(
            _remap_expect(scenario["expect"], actual_ids), http_data
        )


# --- Insert @15: rejected set AND placements move in one response; latest is
#     never the stale pre-insert snapshot; delete returns to baseline. -------
def test_insert_pillar_response_drives_both_and_latest_is_fresh(client, session_factory):
    client.post("/api/allocate/run?segment_id=1")           # baseline snapshot stored
    assert_alloc_matches(BASELINE, _payload(client.get("/api/allocate/latest").json()))

    resp = client.post("/api/pillars", json={
        "segment_id": 1, "position_m": 15.0, "thickness_m": 0.5, "label": "新柱",
    })
    assert resp.status_code == 200
    body = resp.json()
    inserted = body["allocation"]
    assert_alloc_matches(INSERT15, _payload(inserted))      # same object: blocks + rejects
    assert body["pillar"]["position_m"] == 15.0
    assert {p["label"] for p in inserted["pillars"]} == {"灯柱A", "灯柱B", "新柱"}

    latest = client.get("/api/allocate/latest").json()
    assert_alloc_matches(INSERT15, _payload(latest))        # live, not the stale run
    assert _payload(latest) == _payload(inserted)
    assert latest["id"] == inserted["id"]


def test_delete_inserted_pillar_returns_to_baseline(client, session_factory):
    before = _run_count(session_factory)
    added = client.post("/api/pillars", json={
        "segment_id": 1, "position_m": 15.0, "thickness_m": 0.5,
    }).json()
    new_id = added["pillar"]["id"]
    assert _run_count(session_factory) == before + 1
    assert_alloc_matches(INSERT15, _payload(added["allocation"]))

    deleted = client.delete(f"/api/pillars/{new_id}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted_id"] == new_id
    assert_alloc_matches(BASELINE, _payload(deleted.json()["allocation"]))
    assert _run_count(session_factory) == before + 2
    assert_alloc_matches(BASELINE, _payload(client.get("/api/allocate/latest").json()))


# --- Validation: geometry that destroys invertibility is refused. ----------
def test_pillar_validation(client):
    assert client.post("/api/pillars", json={
        "segment_id": 999, "position_m": 15.0,
    }).status_code == 404

    assert client.post("/api/pillars", json={
        "segment_id": 1, "position_m": 15.0, "thickness_m": 0.0,
    }).status_code == 400

    # edge-clipped (would cut the forbidden interval)
    assert client.post("/api/pillars", json={
        "segment_id": 1, "position_m": 0.1, "thickness_m": 0.5,
    }).status_code == 400

    # touching 灯柱A ([9.75,10.25] meets [10.25,10.75])
    assert client.post("/api/pillars", json={
        "segment_id": 1, "position_m": 10.5, "thickness_m": 0.5,
    }).status_code == 409

    assert client.delete("/api/pillars/999").status_code == 404


def test_duplicate_pillar_position_conflicts(client):
    first = client.post("/api/pillars", json={
        "segment_id": 1, "position_m": 15.0, "thickness_m": 0.5,
    })
    assert first.status_code == 200
    second = client.post("/api/pillars", json={
        "segment_id": 1, "position_m": 15.0, "thickness_m": 0.5,
    })
    assert second.status_code == 409
