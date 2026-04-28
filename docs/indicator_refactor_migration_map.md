# 指标/形态/结构重构迁移映射表（兼容迁移）

## 1. 新目录结构（目标）

```
backend/domain/market/
  types.py
  catalog.py
  indicators/...
  structure/...
  patterns/...
```

原则：
- domain 层只做算法与数据结构，不依赖 FastAPI/workflow/tool schema。
- services/strategy/tools_* 只做“适配层”：payload/schema → domain 调用 → 返回结果。
- services/ai/*context_builder 只负责 orchestration（拉数据、裁剪、组装 JSON），不写指标细节。

## 2. 迁移映射（现有 → 目标模块）

### 2.1 Patterns（形态/事件检测）

| 现有位置 | 现有符号 | 目标位置 | 目标符号 | 迁移策略 |
|---|---|---|---|---|
| backend/services/chart_scene/patterns.py | detect_candlestick_patterns | backend/domain/market/patterns/candles.py | detect_candlestick_patterns | 已落地：旧函数变为 wrapper，逻辑在 domain |
| backend/services/strategy/tools_patterns_v1.py | detect_false_breakout | backend/domain/market/patterns/breakouts.py | detect_false_breakout | 已落地：旧函数变为 wrapper，逻辑在 domain |
| backend/services/strategy/tools_patterns_v1.py | detect_liquidity_sweep | backend/domain/market/patterns/breakouts.py | detect_liquidity_sweep | 已落地：旧函数变为 wrapper，逻辑在 domain |
| backend/services/strategy/tools_patterns_v1.py | detect_rectangle_ranges / detect_rectangle_range | backend/domain/market/patterns/pattern_detectors_v1.py | detect_rectangle_ranges / detect_rectangle_range | 已落地：旧函数变为 wrapper，逻辑在 domain |
| backend/services/strategy/tools_patterns_v1.py | detect_close_outside_level_zone | backend/domain/market/patterns/pattern_detectors_v1.py | detect_close_outside_level_zone | 已落地：旧函数变为 wrapper，逻辑在 domain |
| backend/services/strategy/tools_patterns_v1.py | detect_breakout_retest_hold | backend/domain/market/patterns/pattern_detectors_v1.py | detect_breakout_retest_hold | 已落地：旧函数变为 wrapper，逻辑在 domain |
| backend/services/strategy/tools_patterns_v1.py | detect_bos_choch | backend/domain/market/patterns/pattern_detectors_v1.py | detect_bos_choch | 已落地：旧函数变为 wrapper，逻辑在 domain |

### 2.2 Structures（结构/水平/区域）

| 现有位置 | 现有符号 | 目标位置 | 目标符号 | 迁移策略 |
|---|---|---|---|---|
| backend/services/chart_scene/indicators.py | calc_raja_sr | backend/domain/market/structure/raja_sr_calc.py | calc_raja_sr | 已落地：实现迁入 domain；旧入口仍可保留兼容 |
| backend/domain/market/structure/raja_sr.py | compute_raja_sr_level_zones | backend/domain/market/structure/raja_sr_calc.py | calc_raja_sr | 已落地：compute_* 作为 domain 对外入口，内部调用 calc_raja_sr |
| backend/services/chart_scene/indicators.py | detect_swings / structure_state_from_swings / confirmed_structure_levels | backend/domain/market/structure/swings.py | 同名 | 已落地：业务侧 import 已切到 domain |
| backend/services/chart_scene/indicators.py | calc_msb_zigzag | backend/domain/market/structure/msb.py | calc_msb_zigzag | 已落地：业务侧 import 已切到 domain |
| backend/services/strategy/tools_structures_v1.py | tool_structure_level_generator | backend/domain/market/structure/structures_tool_v1.py | tool_structure_level_generator | 已落地：旧函数变为 wrapper，逻辑在 domain |

### 2.3 Indicators（技术指标）

| 现有位置 | 现有符号 | 目标位置 | 目标符号 | 迁移策略 |
|---|---|---|---|---|
| backend/services/chart_scene/indicators.py | sma/ema/rsi/macd/atr | backend/domain/market/indicators/ta.py | 同名 | 已落地：业务侧 import 已切到 domain |
| backend/services/chart_scene/indicators.py | calc_volume_profile | backend/domain/market/indicators/volume_profile.py | calc_volume_profile | 已落地：业务侧 import 已切到 domain |
| backend/services/chart_scene/indicators.py | calc_trend_exhaustion | backend/domain/market/indicators/trend_exhaustion.py | calc_trend_exhaustion | 已落地：业务侧 import 已切到 domain |
| backend/services/chart_scene/session_vp.py | calculate_all/SessionVPOptions | backend/domain/market/vp/session_vp.py（建议新增） | 同名 | 待迁移 |
| backend/services/chart_scene/vp_events.py | build_vp_events | backend/domain/market/vp/vp_events.py（建议新增） | 同名 | 待迁移 |

## 3. “可视化选型”支持点

### 3.1 Feature Catalog（后端可导出）
- 位置：`backend/domain/market/catalog.py`
- 入口：`get_market_feature_catalog()`
- 用途：前端/配置页可读取该 catalog，渲染“指标/结构/形态”的可选项 + 参数表单；后端再用同一套 id/params 驱动计算（避免 UI 与计算逻辑脱节）。

### 3.2 执行侧适配（建议落地顺序）
1. tools 层（已具备 detectors 列表机制）：继续沿用 `tool_pattern_detect_batch(payload.detectors=...)`
2. event_context_builder：新增可选的 feature selection（先用于“是否附加 patterns/structure 事件”，不破坏默认 baseline 指标集）
