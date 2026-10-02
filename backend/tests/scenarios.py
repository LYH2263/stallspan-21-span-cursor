"""共享夹具数据：同一批场景既喂纯引擎 allocate_first_fit，也喂现网分配入口。

严禁为测试另写放宽口径的分配实现——两侧都只能用这一份数据，
引擎直算结果与经 FastAPI /allocate/run、/pillars、/allocate/latest
跑出来的结果必须逐条咬合。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PillarSpec:
    position_m: float
    thickness_m: float = 0.5
    label: str = "灯柱"


@dataclass(frozen=True)
class VendorSpec:
    name: str
    stall_width_m: float
    priority: int


@dataclass
class Scenario:
    name: str
    width_m: float
    pillars: list[PillarSpec]
    vendors: list[VendorSpec]
    # 期望落位，顺序即排队顺序 (priority 升序, id 升序)：(摊主名, 起点, 终点)
    expect_placements: list[tuple[str, float, float]]
    # 期望放不下，顺序即被拒顺序：摊主名
    expect_rejected: list[str]
    # 运行中再通过 POST /pillars 插入的柱（模拟 15m 处再插柱拆段）
    inserted: list[PillarSpec] = field(default_factory=list)
    inserted_expect_placements: list[tuple[str, float, float]] | None = None
    inserted_expect_rejected: list[str] | None = None


WIDTH = 30.0
SEED_PILLARS = [PillarSpec(10.0, 0.5, "灯柱A"), PillarSpec(20.0, 0.5, "灯柱B")]
SEED_VENDORS = [
    VendorSpec("阿强烧烤", 4.0, 1),
    VendorSpec("林记糖水", 3.0, 1),
    VendorSpec("老周水果", 5.0, 2),
    VendorSpec("小美饰品", 2.5, 2),
    VendorSpec("大碗面", 6.0, 1),
    VendorSpec("手作皮具", 3.5, 3),
    VendorSpec("巨型舞台车", 12.0, 9),
]

# 未插柱时的绿仓（种子东街段）逐条落位锚点，重构前后必须一致：
# 禁入 [9.75,10.25]、[19.75,20.25]；空档 9.75 / 9.5 / 9.75。
GREEN = Scenario(
    name="种子东街段·贴柱可落",
    width_m=WIDTH,
    pillars=[*SEED_PILLARS],
    vendors=[*SEED_VENDORS],
    expect_placements=[
        ("阿强烧烤", 0.0, 4.0),
        ("林记糖水", 4.0, 7.0),
        ("大碗面", 10.25, 16.25),   # 起点贴灯柱A 右缘
        ("老周水果", 20.25, 25.25),
        ("小美饰品", 7.0, 9.5),
        ("手作皮具", 16.25, 19.75), # 末端贴灯柱B 左缘，贴柱恰好可落
    ],
    expect_rejected=["巨型舞台车"],  # 12m 超过任何单个空档(最大9.75)
)

# 两摊争同一柱间：两侧空档各 6.25 放不下 6.5，仅柱间 6.5 容得下一摊，
# 优先序 (priority, id) 靠前者占满柱间，另一摊只能进放不下。
CONTEST = Scenario(
    name="两摊争同一柱间",
    width_m=20.0,
    pillars=[PillarSpec(6.5, 0.5, "柱L"), PillarSpec(13.5, 0.5, "柱R")],
    vendors=[VendorSpec("阿甲", 6.5, 1), VendorSpec("阿乙", 6.5, 1)],
    expect_placements=[("阿甲", 6.75, 13.25)],  # 恰好占满 [6.75,13.25] 柱间
    expect_rejected=["阿乙"],
)

# 绿仓跑到一半在 15m 再插一根 0.4m 的柱：柱间 9.5m 被拆成 4.55 + 4.55，
# 原本在右段落位的 5m「老周水果」无处可去，放不下集合与主图色块同时变化。
INSERT_PILLAR = PillarSpec(15.0, 0.4, "加灯柱")
INSERT15 = Scenario(
    name="十五米处再插柱拆段",
    width_m=WIDTH,
    pillars=[*SEED_PILLARS],
    vendors=[*SEED_VENDORS],
    expect_placements=GREEN.expect_placements,
    expect_rejected=GREEN.expect_rejected,
    inserted=[INSERT_PILLAR],
    inserted_expect_placements=[
        ("阿强烧烤", 0.0, 4.0),
        ("林记糖水", 4.0, 7.0),
        ("大碗面", 20.25, 26.25),  # 中段被拆后 6m 只能去最右空档
        ("小美饰品", 7.0, 9.5),
        ("手作皮具", 10.25, 13.75),
    ],
    inserted_expect_rejected=["老周水果", "巨型舞台车"],
)

SCENARIOS = [GREEN, CONTEST, INSERT15]
