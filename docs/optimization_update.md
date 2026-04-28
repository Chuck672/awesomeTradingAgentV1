# Compact Context 复核与下一步优化清单

本文件基于：

- 原始 event context dump：`tmp/dump_XAUUSDz_M15_1777118651.json`
- compact 版本：`tmp/dump_XAUUSDz_M15_1777118651__compact.json`
- 总体目标清单：[event\_context\_optimization.md](file:///d:/TraeProjects/awesomeTradingAgentV1/docs/event_context_optimization.md)

仅保留“compact 版本尚未覆盖 / 仍需继续优化”的项目（已满足项不再列入）。

***

## P0（最高优先级）：直接影响一致性/可控性

### 1) 语义时间语境（Unix → 人类可读 + 相对索引）

现状（compact）：

- `event.snapshot_time`、`recent_bars[].time`、`Nearest_*.*_time`、`Recent_Structure_Breaks[].time` 仍是 Unix 秒。

需要补齐：

- 为关键时间增加 ISO 8601 字符串（保留 Unix 用于路由/计算）。
- 为结构事件（ChoCh/BoS）与最近 K 线增加相对索引：
  - `bars_ago` / `event_bars_ago`
- 增加会话语境字段（可由系统侧预处理）：
  - `market_session`（如 London\_AM / London-NY Overlap）
  - `is_market_open`（以及可选 spread、news impact 等）

### 2) 价格行为邻近性与“距离字段”（避免模型做减法）

现状（compact）：

- 只提供 `Nearest_Resistance` / `Nearest_Support`，已经比全量 zones 更接近“邻近性过滤”方向。
- 但仍缺少“距离到当前价”的显式字段，且对象字段偏冗余。

需要补齐：

- 在 SR（Nearest\_\*）与结构事件（Recent\_Structure\_Breaks）中增加：
  - `distance_to_price_points`（或 pips）
  - `distance_pct`
- 对 SR 对象字段做裁剪（保留决策必要信息）：
  - 建议保留：`type`、`level`（或 bottom/top 二选一）、`score`、`touches`、`last_touch_time(_iso)`、`distance_*`
  - 可考虑移除：`avg_wick_excess`、`trade_score`、长区间 `from_time/to_time`（除非你的策略明确依赖“区间跨度”）

### 3) 多时间框架联动摘要（multi\_tf\_alignment）

现状（compact）：

- H1 与 M15 各自有 `Market_Structure`，但没有“主次关系/冲突处理”的顶层总结。

需要补齐：

- 增加顶层 `multi_tf_alignment`（系统侧预处理生成）：
  - `direction`（bullish/bearish/neutral）
  - `consistency`（high/moderate/low）
  - `note`（一句话解释主周期与执行周期的关系与建议动作）

### 4) 输出 Schema 与强约束（strict\_json + 必填字段）：**检查是否强约束已经添加到了 system prompt 内部**

现状（compact）：

- compact 只包含市场摘要，没有携带 `constraints`，无法在“每次触发”时稳定约束模型输出格式。

需要补齐：

- 在事件上下文（最终喂给 analyzer 的 payload）里加入强约束：
  - `output_format: strict_json`
  - `required_fields` 最小集合（建议）：`signal/confidence/reasoning/entry_price/stop_loss/take_profit/risk_reward_ratio/invalidation_condition/trade_horizon`
- 明确字段语义：
  - `strength` → `confidence`（避免“强度”歧义）
  - `entry` 数组 → `entry_price` 标量（如需分批再加 `entry_prices`）

***

## P1：减少噪声、提升可解释性

### 5) 指标量纲/定义显式化（indicator\_notes / units）

现状（compact）：

- ATR、MACD、VP 等指标无单位说明；模型可能误用量纲推止损/仓位。

需要补齐：

- 增加 `indicator_notes` 或为每个指标字段附 `unit/description`：
  - ATR：单位为 price points
  - MACD：参数(12,26,9)，histogram 单位为 price points
  - RSI：0-100

### 6) 数值精度控制（降低 token 噪声，增强一致性）

现状（compact）：

- 存在大量长小数（如 POC/VAL/VAH、EMA、MACD），不利于稳定关注点。

需要补齐：

- 统一精度：
  - 价格类 3 位小数
  - 指标类 2\~4 位小数
  - 分数字段 1\~2 位小数

### 7) recent\_bars 仍可进一步收敛

现状（compact）：

- `recent_bars` 带了 `delta_volume/source` 等字段。

需要补齐：

- 若 `delta_volume` 恒为 0：移除。
- `source` 高重复：移除或提升为顶层元信息（例如 `data_source`）。
- 若你希望更“摘要化”：`recent_bars` 仅保留 OHLC（和 volume 可选）。

***

## P2：面向“跨事件一致性”的上下文工程（结构补齐）

### 8) Decision State Card（状态卡）/ 增量更新（delta）

现状（compact）：

- 每次触发是“无状态快照”，缺少对上一事件的引用与一致性约束。

需要补齐（建议作为独立顶层块，不与 market 混杂）：

- `decision_state`：
  - `position_state`（flat/long/short）
  - `thesis`（一句话）
  - `invalidation_rules`（反转门槛）
  - `last_decision`（signal/confidence/timestamp）
- 要求模型输出 `decision_delta`：
  - 本次相较上次“哪些证据变化导致调整”，反转必须点名触发了哪条失效条件。

