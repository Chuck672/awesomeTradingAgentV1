# Alert Dual-Agent 指标盘点与后续实施计划（基于现有代码的再规划）

## 1. 范围说明
- 本文只覆盖“event_trigger 命中规则后 → event_dual workflow 运行 → build_event_context 同步构建 JSON”这一段链路里会同步计算/打包的指标与特征。
- 目标：给出
  - 已完成（已接入 event_dual 的同步预计算）清单，含参数默认值与可配置入口
  - 已实现但未接入 event_dual 的候选指标/事件清单
  - 结合 `alert_dual_agent_refactor_plan.md` 的 TODO，输出下一阶段实施计划（以指标工程为主）

## 2. 现状：已接入 event_dual 的同步预计算（已完成清单）

### 2.1 触发侧（alerts_engine）为“是否触发事件”同步计算/使用的指标
- RajaSR 触发（`raja_sr_touch`）
  - zones：`calc_raja_sr(bars, max_zones=5)`（覆盖函数默认 `max_zones=6`）
  - 历史窗口：`limit=400`（硬编码）
  - 去重/冷却：`cooldown_minutes`（rule 可配，默认 30）
- MSB 结构突破触发（`msb_zigzag_break`）
  - zigzag：`calc_msb_zigzag(bars, pivot_period=5)`（函数默认 pivot_period=5）
  - 历史窗口：`limit=400`（硬编码）
  - 触发类型：`detect_bos` / `detect_choch`（rule 可配，默认 True/True）
- Trend Exhaustion 触发（`trend_exhaustion`）
  - 指标：`calc_trend_exhaustion(bars)`（默认参数见 2.2.2）
  - 历史窗口：`limit=400`（硬编码）
- London Breakout（legacy 规则，非 event_dual 核心输入）
  - `volume_mult`（rule 可配，默认 1.5）

### 2.2 上下文侧（build_event_context）为“Analyzer 输入 JSON”同步计算/打包的指标与特征

#### 2.2.1 多周期 OHLCV 拉取与 payload 裁剪
- 固定计算 TF：
  - H4：只打包 OHLCV（`include_indicators=False`）
  - H1/M15：打包 OHLCV + indicators
  - 若 `event_timeframe` 不在上述三者中，会额外对该 TF 也打包 indicators
- 历史拉取条数（可配置入口：`history_limits` 入参）
  - 默认：`{"H1": 400, "M15": 600, "H4": 200}`
- 写入 JSON 的 OHLCV 根数（当前硬编码，不可配）
  - `{"H1": 25, "M15": 50, "H4": 15}`

#### 2.2.2 每个 TF 的基础指标（build_agent_context）
- SMA：`SMA_20` / `SMA_50`（period=20/50）
- EMA：`EMA_20`（period=20）
- ATR：`ATR_14`（period=14）
- RSI：`RSI_14`（period=14）
- MACD：`MACD`（fast=12, slow=26, signal=9）

#### 2.2.3 每个 TF 的高级指标与结构摘要（build_agent_context + build_event_context 二次加工）
- Volume Profile（基于 bars 的全量窗口）
  - `calc_volume_profile(bars, bins_count=50, value_area_pct=70.0)`
  - 输出被压缩为 `VolumeProfile_POC/VAH/VAL`
- RajaSR zones（基于 bars 的全量窗口）
  - `calc_raja_sr(bars, lookback=1000, pivot=2, max_zones=6)`
- MSB ZigZag（结构事件）
  - `calc_msb_zigzag(bars, pivot_period=5)`，内部返回 `lines[-10:]`
  - `build_agent_context` 进一步裁剪为 `Recent_Structure_Breaks = lines[-3:]`
  - `build_event_context` 进一步二次加工为 `recent_structure_breaks = lines[-5:]`，并补充 `age_candles/distance_to_price`
- Trend Exhaustion
  - `calc_trend_exhaustion(bars, short_len=21, short_smooth=7, long_len=112, long_smooth=3, threshold=20)`
- Swing 与结构状态
  - `detect_swings(bars, left=2, right=2, max_points=10)`
  - `structure_state_from_swings(swings)` → `Market_Structure`
  - `confirmed_structure_levels(swings)` → `Structure_High/Structure_Low`
- active_zones（基于 RajaSR 的“近邻支撑/阻力区”）
  - 选取规则：距离当前价最近的上方 3 个 + 下方 3 个（硬编码上限）
  - 额外字段：`distance_to_price_points/distance_pct/last_touch_age_candles/evidence_id`

#### 2.2.4 跨周期一致性（multi_tf_alignment）
- 固定 TF：`trend_tf=H1`，`exec_tf=M15`
- direction（硬编码规则）：
  - H1 `Market_Structure=HH_HL` → bullish
  - H1 `Market_Structure=LH_LL` → bearish
  - 其他 → neutral
- consistency（硬编码规则）：
  - M15 与 H1 一致 → high
  - M15=Consolidation → moderate
  - 其他 → low/unknown

#### 2.2.5 市场状态（market_state）
- 当前报价/点差（若 MT5 不可用则退化为历史 close）
- data_fresh：`abs(now - snapshot_time) <= 3h`（硬编码）
- vol_regime：`_infer_vol_regime(window=20)`，阈值：`>=1.2 expanding`，`<=0.8 contracting`
- volume_activity：
  - 需要 `len(M15) >= 30`
  - `recent=avg(last10)` vs `base=median(last30:-10)`，阈值：`>=1.5 spike`，`<=0.7 dull`
- upcoming_news_impact：从 `calendar.json` 读取未来 2 小时内事件的最高 impact（硬编码时间窗）
- session_vp（Session Volume Profile 摘要）
  - `SessionVPOptions(days_to_calculate=5, bins=70, value_area_pct=70.0)`
  - 当前只打包 `current/previous` 的 POC/VAH/VAL 摘要，不包含 bins

## 3. 已实现但尚未接入 event_dual 的候选指标/事件（后端已有代码）

### 3.1 蜡烛形态（candlestick patterns）
- 位置：`backend/domain/market/patterns/candles.py`
- 入口：`detect_candlestick_patterns(bars, atr14=0.0, min_body_atr=0.1)`
- 状态：已接入 `build_event_context`，默认在 `market.patterns["M15"].candlestick` 输出（见 2.2 新增字段）

### 3.2 VP 派生事件（Value Area/POC 破位、接受/拒绝、HVN/LVN 等）
- 位置：`backend/services/chart_scene/vp_events.py`
- 入口：`build_vp_events(...) -> {derived, events}`
- 价值：把“VP 结构语言”直接交给 analyzer，减少其在 JSON 上做二次推导
- 依赖：需要 SessionVP 的 active_block（含 bins），而当前 event_context 只传摘要

### 3.3 ChartSceneEngine：有记忆的 sweep / retest 状态机事件
- 位置：`backend/services/chart_scene/scene_engine.py`
- 价值：更贴近“事件语言”（sweep_detected → recover/timeout；break → retest → reclaim/failed）
- 注意：需要保存跨 bar 的短期状态（适合做短 TTL 缓存或按 event_id 存 alerts.sqlite）

### 3.4 tools_patterns_v1：结构/突破/假突破/扫流动性/箱体等检测器（当前作为 tool 暴露）
- 位置：`backend/services/strategy/tools_patterns_v1.py`
- 代表性 detector：
  - `detect_rectangle_ranges(...)`
  - `detect_liquidity_sweep(lookback_bars=160, recover_within_bars=3, buffer=0.0)`
  - `detect_false_breakout(lookback_bars=120, buffer=0.0)`
  - `detect_bos_choch(lookback_bars=220, pivot_left=3, pivot_right=3, buffer=0.0)`
  - `detect_close_outside_level_zone(...)`
  - `detect_breakout_retest_hold(...)`
- 状态：已迁移为 domain 算法并接入 `build_event_context`，默认输出：
  - `market.patterns["M15"].rectangle_ranges`
  - `market.pattern_events["M15"]`（包含 bos/choch、liquidity_sweep、false_breakout、close_outside、breakout_retest_hold 等事件）
  - `market.structures["M15"]`（用于上述结构类 detector 的 levels/zones 摘要）

## 4. 后续实施计划（结合 refactor_plan 的 TODO，按优先级落地）

### 4.1 设计原则（保持 event_dual 稳态）
- Analyzer 只消费 JSON，不兜底调用指标工具。
- 新增指标必须：
  - 明确“输入依赖”（来自哪一 TF 的哪一段 bars / 哪个已有字段）
  - 明确“可配置参数”与默认值（写入 rule.agent_configs 或 event_context builder 入参）
  - 明确“失败降级”（写入 `missing_indicators`，并不阻断事件链）
- Token 约束：新增字段优先“事件化/摘要化”，避免传大数组（尤其是 VP bins）。

### 4.2 P0（强相关/高收益）：优先接入到 build_event_context

#### P0-1 Session High/Low（亚洲/伦敦/纽约）
- 目标：补齐 `session_high_low` 指标，支撑 breakout 与扫流动性判断（对应 refactor_plan 的 P0）
- 计算方式（建议）：
  - 以 UTC 时间窗定义 session，使用 M15 或 H1 近 N 天数据聚合高低点
- 建议参数：
  - `days=5`，`tf=M15`，`session_defs`（可固定内置）
- JSON 位置：
  - `market_state.session_levels` 或 `market.indicators[M15].session_high_low`

#### P0-2 Liquidity Sweeps（扫流动性/等高等低/假突破）
- 目标：接入 `liquidity_sweeps`（对应 refactor_plan 的 P0）
- 推荐落地路径（最小接入 → 强化）：
  1) 先接 `tools_patterns_v1.detect_liquidity_sweep`（无状态版，低依赖）
  2) 再考虑接入 `ChartSceneEngine` 的有记忆 sweep/recover（需要状态保存）
- 建议参数（无状态版）：
  - `lookback_bars=160`，`recover_within_bars=3`，`buffer=0.0`
- JSON 位置：
  - `market.events[M15].liquidity_sweeps`（事件列表，最多 N 条）

#### P0-3 FVG / Imbalance（缺口/失衡区）
- 目标：接入 `fvg_imbalance`（对应 refactor_plan 的 P0）
- 现状：代码库内尚未看到稳定的 FVG detector（需要新增实现）
- 建议参数：
  - `lookback_bars`，`min_gap_atr_mult`，`mitigation_mode`（wick/body），`max_zones`
- JSON 位置：
  - `market.indicators[M15].fvg_imbalance`（区域列表 + 回补状态）

### 4.3 P1（增强质量）：过滤与强度折扣

#### P1-1 news_risk（简化新闻风险）
- 现状：已有 `upcoming_news_impact`（2 小时窗）
- 增强方向：
  - 明确“禁止交易/降低 strength”的影响规则
  - 允许配置 `horizon_minutes` 与 impact 映射

#### P1-2 spread_slippage_proxy（点差/滑点 proxy）
- 现状：`market_state.current_quote.spread` 已存在（MT5 不可用时为 None）
- 增强方向：
  - 计算 `spread_pts`、`spread_to_atr`（spread/ATR14）作为强度折扣项
- 建议参数：
  - `max_spread_to_atr=0.15`（超过则 strength 折扣）

### 4.4 P2（可选/实验）：评分化与 regime

#### P2-1 multi_timeframe_confluence_score
- 目标：把“多周期一致性”从离散等级升级为数值分数
- 输入：H4/H1/M15 的结构、趋势、VP、关键区距离等
- 输出：`0-100` 或 `0-1`，并给出可解释的子项分解

#### P2-2 market_regime（趋势/震荡/扩张/收缩）
- 现状：已有 `vol_regime` 与 `Market_Structure`
- 增强：组合生成更稳定的 regime（并给 analyzer 一句摘要）

## 5. 工程落地步骤（建议按 PR/迭代拆分）

### 5.0 可视化选型集成（已开始接入）
- 后端提供 feature catalog：`GET /market/features/catalog`
- 前端在 Alerts 面板创建规则时可保存：
  - `rule.agent_configs.context_features = { timeframe, enabled: [feature_id...], params: {feature_id: {...}} }`
- `build_event_context` 会读取 `agent_configs.context_features` 决定是否计算并写入：
  - `market.patterns[tf]`
  - `market.structures[tf]`
  - `market.pattern_events[tf]`

### 5.0.1 通用触发器 detector_trigger（下一步）
- 新增 alert rule 类型：`rule.type = "detector_trigger"`
- 配置字段：
  - `rule.trigger_detectors = [{ feature_id, timeframe?, params? }, ...]`
  - 可选：`rule.cooldown_minutes`（通用冷却）
- 触发逻辑：
  - 后端按 detectors 扫描最近 bars，命中后写入 events，并启动 event_dual workflow
  - 去重：`state.last_trigger_sig = sha1(symbol|event_id|tf|bar_time|key)`，避免重复触发同一事件

### 5.0.2 迁移旧触发到 detector_trigger（进行中）
- 旧触发类型仍保留（兼容历史 rules），但内部 eval 已统一走 detector_trigger：
  - raja_sr_touch → trigger_detectors=[{feature_id:"raja_sr_touch", params:{limit:400,max_zones:5}}]
  - msb_zigzag_break → trigger_detectors=[{feature_id:"msb_zigzag_break", params:{limit:400,detect_bos,detect_choch}}]
  - trend_exhaustion → trigger_detectors=[{feature_id:"trend_exhaustion", params:{limit:400}}]
- 下一步：前端创建规则默认推荐 detector_trigger（旧三种作为快捷模板入口）。
  - 已实现：Detector Trigger 作为默认选项，并提供 Template 按钮与 Trigger/Context 选型联动。

### 5.1 先做“低依赖、高确定性”的预计算
- candlestick_patterns（patterns.py）
- rectangle_ranges（tools_patterns_v1.py，不依赖 levels/zones）
- session_high_low（新实现，依赖 OHLCV 聚合）

### 5.2 再做“依赖结构/区域”的预计算
- liquidity_sweep / false_breakout / bos_choch（tools_patterns_v1.py）
- close_outside_level_zone / breakout_retest_hold（需要 levels/zones；可先用 RajaSR zones + Structure_High/Low 做简化映射）

### 5.3 最后做“VP bins/状态机”类（注意 token 与状态）
- session_vp 增强：在 JSON 中增加 `active_block` 的精简 bins（例如 top-N HVN/LVN、developing POC 序列），而不是全量 bins
- vp_events：把 derived 与 events 接入 JSON
- ChartSceneEngine：引入短 TTL 状态保存（cache 或 alerts.sqlite keyed by symbol/tf）

## 6. 验收标准（每项新增指标）
- build_event_context 输出新增字段，且在指标缺失时：
  - 不抛异常、不阻断触发链
  - `missing_indicators` 增加明确 key
- 增加最小单元测试：
  - 输入固定 bars，输出事件/区域稳定可复现
- 增加最小集成验证：
  - 触发一次 event_dual，ai_report 中能引用新增 evidence/事件

### 6.1 调试/验收工具
- 输出“包含所有可选 patterns/features 的 event_context JSON”：
  - 脚本：`backend/scripts/dump_event_context_all_features.py <SYMBOL> <TF> [OUT_PATH]`
  - 默认输出目录：`docs/debug_dumps/`
