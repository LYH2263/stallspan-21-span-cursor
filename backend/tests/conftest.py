"""pytest 共享底座：

* engine_result(scenario[, inserted]) —— 纯引擎直接吃夹具数据；
* api_factory —— 用同一夹具数据播种 FastAPI + SQLite，
  经现网入口 /allocate/run、/pillars、/allocate/latest 跑真实 HTTP。

两侧只准共用 scenarios.SCENARIOS 这一份数据，结论逐条咬合。
"""
from __future__ import annotations

import pytest
from datetime import date
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.models import MarketDay, Pillar, Segment, Vendor
from app.services.first_fit_engine import allocate_first_fit

from tests.scenarios import SCENARIOS, Scenario


def scenario_vendor_dicts(scenario: Scenario) -> list[dict]:
    return [
        {"id": i + 1, "name": v.name, "stall_width_m": v.stall_width_m, "priority": v.priority}
        for i, v in enumerate(scenario.vendors)
    ]


def scenario_pillar_dicts(scenario: Scenario, inserted: bool = False) -> list[dict]:
    rows = list(scenario.pillars) + (list(scenario.inserted) if inserted else [])
    return [
        {"position_m": p.position_m, "thickness_m": p.thickness_m}
        for p in rows
    ]


def engine_result(scenario: Scenario, inserted: bool = False):
    return allocate_first_fit(
        scenario.width_m,
        scenario_vendor_dicts(scenario),
        scenario_pillar_dicts(scenario, inserted),
    )


@pytest.fixture(params=SCENARIOS, ids=[s.name for s in SCENARIOS])
def scenario(request) -> Scenario:
    return request.param


@pytest.fixture
def api_factory(scenario: Scenario, monkeypatch: pytest.MonkeyPatch):
    """按当前夹具播种一个一次性 SQLite 应用，返回可调用的现网客户端工厂。"""
    import app.main as main_mod
    from app.config import settings

    sqlite_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(sqlite_engine)
    Session = sessionmaker(bind=sqlite_engine, autoflush=False, autocommit=False)

    # lifespan 经 app.main 模块里 from-import 绑定的名字建表/播种：
    # 指到本次 SQLite，并关掉绿仓种子，避免污染夹具场景
    monkeypatch.setattr(main_mod, "engine", sqlite_engine)
    monkeypatch.setattr(main_mod, "SessionLocal", Session)
    monkeypatch.setattr(settings, "seed_on_empty", False)

    db = Session()
    day = MarketDay(name="测试集日", day=date(2026, 9, 20))
    db.add(day)
    db.flush()
    seg = Segment(market_day_id=day.id, name=scenario.name, width_m=scenario.width_m)
    db.add(seg)
    db.flush()
    # 柱故意按乱序写入，验证现网读取与柱序无关
    for i, p in enumerate(reversed(list(scenario.pillars))):
        db.add(Pillar(segment_id=seg.id, position_m=p.position_m,
                      thickness_m=p.thickness_m, label=p.label))
    # 摊主按夹具顺序写入，id 即 1..N，与 scenario_vendor_dicts 对齐
    for v in scenario.vendors:
        db.add(Vendor(market_day_id=day.id, name=v.name,
                      stall_width_m=v.stall_width_m, priority=v.priority))
    db.commit()

    def override_get_db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client, scenario
    app.dependency_overrides.clear()
    db.close()
    sqlite_engine.dispose()
