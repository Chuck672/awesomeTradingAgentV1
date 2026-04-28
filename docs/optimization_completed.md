# Event\_Dual（双 Agent）优化总纲：Context 压缩 + 一致性增强（v1）

本文是 event\_dual（Alert 系统双 agent：Analyzer + Executor）的统一优化总纲，整合以下来源并按优先级归并为一份可执行清单：

- `docs/optimization_update.md`（基于当前 compact 的差距清单）
- `docs/optimization_from_deepseek.md`
- `docs/optimization_from_gemini.md`
- `docs/optimization_from_qwen.md`

目标是：在不破坏现有运行链路的前提下，逐步把 event\_dual 的 Analyzer 输入升级为 **更小、更稳、更可解释、更易保持跨事件一致性** 的上下文 payload。

***

## 0) 适用范围与不变约束

### 0.1 范围

- 仅针对 Alert 系统的 event\_dual：`backend/api/agent_routes.py::_run_event_dual_agent_workflow`
- 不包含对话窗口 3-agent 线路（后续单独做）

### 0.2 不变约束（保证不影响现有运行）

- event\_dual 的 Analyzer 仍保持“禁止调用工具”的模式（当前 prompt 约束）
- event\_dual 的 Executor 仍使用现有绘图工具链（draw\_clear\_ai + draw\_objects）
- 优化优先以“输入剪裁/预处理”为主，避免大规模改动指标算法

***

## 1) 当前事实（event\_dual 的真实输入是什么）

在 event\_dual 中，Analyzer 接收到的是 `build_event_context(...)` 的完整输出 JSON：

- 包含 **全量 OHLCV**：`market.ohlcv.{H1,M15}`（默认 H1 400 / M15 600）
- 同时包含 `build_agent_context(bars)` 的摘要拆字段：`market.indicators[tf].{current_price,recent_bars,basic_indicators,advanced_indicators}`
- 并额外加入 `raja_sr_zones` 与 `msb_zigzag`

这意味着目前并不是“只给摘要”，而是“全量 bars + 摘要 + 额外结构”并存，导致上下文体积和噪声偏大。

***

## 2) 设计原则（所有优化都要遵守）

### 2.1 让 LLM 少算术、多推理

- 预先计算距离（到关键位/结构点），避免模型做减法
- 提供 ISO 时间 / 会话标签 / 相对索引，避免模型做时间戳换算

### 2.2 让证据可引用

- 关键证据要结构化、可排序（例如 active\_zones、recent\_swing\_points）
- 强制输出引用“证据集合”，便于回测/复盘

### 2.3 输入形状稳定（提升相似条件下的一致性）

- 固定 TF 组合与窗口策略（trend\_tf / exec\_tf）
- 数值精度统一（避免无意义长小数扰动注意力）

### 2.4 分阶段演进（先剪裁，再增益）

- P0：先把 payload 变小、变稳、变可控
- P1：再补关键元数据与可解释性字段
- P2：最后做跨事件一致性（状态卡 / delta 更新）

***

## 3) P0 优先级（最先做，收益最大，风险最低）

### P0-1：裁剪/重排 Analyzer 输入（从 “full bars + 多套重复” → “compact evidence”）

目标：

- event\_dual analyzer payload 默认不再携带全量 `market.ohlcv`
- 将 raw bars 改为“固定短窗口”（用于 Price Action/复核），其余以 compact evidence 为主

建议的 OHLCV 窗口（用于 event\_dual，不等同于历史全量）：

| 时间周期   | 建议保留根数 | 覆盖范围（约）      | 用途                                 |
| ------ | ------ | ------------ | ---------------------------------- |
| H1     | 25 根   | 约 1.5～2 个交易日 | 验证趋势延续/衰竭、识别关键突破、过滤隔夜跳空干扰          |
| M15    | 50 根   | 约 10～15 小时   | 捕捉微观结构、识别 PA 形态（吞没/Pin/假突破）、观察量价异动 |
| H4（必选） | 15 根   | 约 2～4 天      | 大级别波段方向、主要流动性池定位（仅用于 OHLCV 观察）       |

建议策略：

- 仅引入 event\_dual 所需的时间周期：
  - `trend_tf`: H1
  - `exec_tf`: M15
  - `liquiditylevel_tf`：H4（流动性池定位；仅保留在 `market.ohlcv.H4`，不计算/不输出 `market.indicators.H4`）
- `recent_swing_points`：保留最近 5 个关键结构拐点（从 msb\_zigzag 或 swings 提取）
  - 说明：仅 3 条 breaks 容易丢信息（deepseek）
- `active_zones`：仅使用 `raja_sr_zones` 做统一的支撑阻力来源，并过滤/排序后保留“上下临近”的 Top 3：
  - 上方阻力 Top 3 + 下方支撑 Top 3（都按邻近度与评分综合排序）
  - 为了避免重复与歧义，后续不再单独使用 `Nearest_Resistance` / `Nearest_Support`（其信息应被 `active_zones` 覆盖）
  - 命名建议：`level_zone_bottom_edge_price` / `level_zone_top_edge_price`（不再使用 `level`）

\
落点（模块）：

### P0-2：预计算距离字段（避免 LLM 数学负担）

目标：

- 在关键位对象中加入距离字段：
  - `dist_points` / `dist_pct`
  - 或更直观的 `distance_to_price_points`

适用对象：

- active\_zones（支撑/阻力）
- structure breaks / swing points（关键结构价位）

落点（模块）：

- `build_event_context` 或 event\_dual 的 payload 裁剪层

### P0-3：语义时间语境（ISO + 会话标签 + 相对索引）

目标：

- 保留 Unix 秒用于路由/存储，同时提供：
  - `*_iso`（ISO 8601 UTC）
  - `market_session`（Asia/London/NY/Overlap）
  - `bars_ago` / `age_candles`（相对索引）
  - 说明：为减少噪声与避免时间戳算术，payload 中不再保留 Unix 秒时间戳字段

落点（模块）：

- `build_event_context`（event 级别最适合）

### P0-4：强制结构化输出（constraints + prompt 双保险）

目标：

- Analyzer 输出必须可解析、可校验、可回测：
  - strict\_json
  - 必填字段：`signal/confidence/reasoning/evidence_refs/entry_type/entry_price/stop_loss/take_profit/risk_reward_ratio/invalidation_condition/trade_horizon`

落点（模块）：

- Analyzer prompt：`backend/api/agent_routes.py::_run_event_dual_agent_workflow`（强约束）
- 约束注入：`build_event_context` 的 `constraints`（可选但建议保留）

补充：

- `constraints` 建议保留在 payload 内，作为“结构化输出的自描述契约”，避免仅靠 prompt 约束导致漂移。
  - `evidence_refs` 必须引用证据对象的 `evidence_id`（而非 JSON path），避免因排序变化造成引用漂移。

***

## 4) P1 优先级（增强可解释性与交易常识）

### P1-1：注入市场元数据（session/spread/data\_quality/vol\_regime/news）

目标：

- 模型要知道“什么时候、市场是否开盘、点差大小、波动环境、是否临近新闻”，否则 SL/TP 与入场类型可能失真（deepseek/qwen）。

建议字段：

- `market_state`：
  - `session`
  - `spread_pts`（bid/ask 推导）
  - `data_fresh`（数据是否延迟/缺失）
  - `vol_regime`（expanding/contracting/normal）
  - `upcoming_news_impact`（low/medium/high）

落点（模块）：

- `build_event_context`（event 级最合适）
- 若需要经济日历：复用 `calendar_service` 的能力（后续接入）

### P1-2：指标量纲/定义显式化（indicator\_notes）

目标：

- 防止 ATR/MACD 等量纲被误解导致风险评估错误（deepseek）。

建议字段：

- `indicator_notes`（根层级）：
  - ATR：price points
  - MACD：参数(12,26,9)，hist 为 price points
  - RSI：0-100

落点（模块）：

- `build_event_context`（或作为 prompt 附加说明）

补充：

- `indicator_notes` 应覆盖所有被纳入 payload 的指标，尤其是 `advanced_indicators`（命名更抽象），至少说明：
  - 指标含义与用途（用于趋势/波动/结构/量价/关键位）
  - 单位与量纲（points/%/0-100 等）
  - 关键参数（例如 MACD(12,26,9)、VP 的 bins\_count/value\_area\_pct 等）

### P1-3：成交量活动标记 / 背离预计算（可选）

目标：

- 把“成交量是否异常”“是否存在 RSI/MACD 背离”等高价值模式预计算出来，减少模型自己发明规则。

建议字段：

- `volume_activity`: `dull | normal | spike`
- `RSI_divergence`: `bullish | bearish | none`
- `MACD_divergence`: `bullish | bearish | none`

落点（模块）：

- 指标计算层（`build_agent_context` 或 `build_event_context` 的附加计算）
- 注意：如改 `build_agent_context` 会影响两条线路；如只想影响 event\_dual，优先加在 `build_event_context`

补充：

- 第一阶段（event\_dual）优先只改 `build_event_context`，避免影响对话窗口 3-agent 线路。
- 如存在 Session Volume Profile（SessionVP）能力，后续应补充：
  - `current_session_vp` 的关键值（POC/VAH/VAL 等）
  - `prev_session_vp` 的关键值
  - 并给出 session 切分规则与时区（避免模型误读“前一 session”）

***

## 5) P2 优先级（跨事件一致性：Decision State Card + delta 更新）

问题根因：

- 每次触发都是“无状态推理”，模型不知道上一事件给了什么建议，也不知道该建议是否仍有效。

目标：

- 让模型在“相似条件”下输出更一致；当反转时必须说明“触发了什么失效条件”。

建议机制：

- `decision_state`（由系统维护/注入）：
  - `position_state`: `flat|long|short`
  - `thesis`: 一句话交易逻辑
  - `last_decision`: 上次 signal/confidence/entry/SL/TP（含 evidence_refs=evidence_id）
  - `invalidation_rules`: 明确反转门槛
- 强制输出：
  - `decision_delta`: 本次相对上次变化点（证据引用）

落点（模块）：

- 注入位置：`backend/api/agent_routes.py::_run_event_dual_agent_workflow`（构造 prompt 时加入）
- 若要持久化：`alerts_store` 增加 state 存储（后续再定）

***

## 6) event\_dual v2 目标 Schema（建议草案）

下面是为 event\_dual 定制的 compact payload 目标形态（示意，不要求一次到位）：

```json
{
  "schema": "event_dual_context_v2",
  "schema_version": "2.0.0",
  "event": {
    "event_id": "evt_xxx",
    "trigger_type": "msb_zigzag_break",
    "trigger_text": "...",
    "symbol": "XAUUSDz",
    "exec_tf": "M15",
    "trend_tf": "H1",
    "snapshot_time_iso": "2026-04-25T10:00:00Z",
    "exec_tf": "M15",
    "trend_tf": "H1",
    "liquiditylevel_tf": "H4"
  },
  "market_state": {
    "session": "London_NY_Overlap",
    "is_market_open": true,
    "spread_pts": 1.2,
    "vol_regime": "normal",
    "data_fresh": true,
    "upcoming_news_impact": "low"
  },
  "multi_tf_alignment": {
    "direction": "bullish",
    "consistency": "moderate",
    "note": "H1 uptrend, M15 consolidation near resistance – wait for breakout or pullback."
  },
  "indicator_notes": {
    "ATR_14": "单位为价格点",
    "MACD": "标准参数(12,26,9)，hist 单位为价格点",
    "RSI_14": "0-100"
  },
  "market": {
    "ohlcv": {
      "H4": [
        { "time_iso": "2026-04-24T00:00:00Z", "bars_ago": 14, "open": 0, "high": 0, "low": 0, "close": 0, "tick_volume": 0 }
      ],
      "H1": [],
      "M15": []
    },
    "indicators": {
      "H1": {
        "current_price": 4724.62,
        "basic_indicators": {},
        "advanced_indicators": {},
        "active_zones": [
          {
            "evidence_id": "zone_H1_xxxxxxxxxx",
            "type": "support",
            "level_zone_bottom_edge_price": 4708.26,
            "level_zone_top_edge_price": 4709.23,
            "score": 94.96,
            "touches": 7,
            "last_touch_time_iso": "2026-04-24T12:00:00Z",
            "last_touch_age_candles": 2,
            "distance_to_price_points": 15.4,
            "distance_pct": 0.003
          }
        ],
        "recent_structure_breaks": [
          {
            "evidence_id": "break_H1_xxxxxxxxxx",
            "type": "ChoCh_Bull",
            "level_price": 4711.22,
            "time_iso": "2026-04-24T12:00:00Z",
            "age_candles": 3,
            "distance_to_price_points": 13.4
          }
        ]
      },
      "M15": {}
    }
  },
  "constraints": {
    "output_format": "strict_json",
    "required_fields": [
      "signal",
      "confidence",
      "reasoning",
      "evidence_refs",
      "entry_type",
      "entry_price",
      "stop_loss",
      "take_profit",
      "risk_reward_ratio",
      "invalidation_condition",
      "trade_horizon"
    ]
  }
}
```

***

## 7) 模块落点总览（后续实现时对照）

> 这里只列“event\_dual 优先”的落点；对话 3-agent 后续再拆。

- **Payload 构建/裁剪**：`backend/services/ai/agent_tools.py::build_event_context`
- **Analyzer 强约束 prompt / 注入 decision\_state**：`backend/api/agent_routes.py::_run_event_dual_agent_workflow`
- **指标摘要（如需共用增强）**：`backend/services/ai/agent_tools.py::build_agent_context`
- **session/spread/news/data\_quality 的真实数据源**：后续确定接入位置（MT5 quote / calendar\_service）

***

## 8) 验收标准（每一阶段都要可验证）

### P0 验收

- event\_dual 的 Analyzer 输入 payload 明显缩小（至少移除全量 `market.ohlcv`，或裁剪到固定短窗口）
- payload 内包含：
  - ISO 时间 / session（或至少 ISO）
  - dist 字段（zones / breaks）
  - 多周期对齐摘要（multi\_tf\_alignment）
- Analyzer 输出严格 JSON，必填字段齐全，可被程序解析

### P1 验收

- 加入 spread/session/vol\_regime/data\_quality 后，模型 SL/TP 明显更贴近市场常识
- 指标量纲明确，避免把 ATR 当百分比/把 MACD 当价格

### P2 验收

- 连续触发事件时，模型输出包含 decision\_delta；反转必须引用 invalidation\_condition
