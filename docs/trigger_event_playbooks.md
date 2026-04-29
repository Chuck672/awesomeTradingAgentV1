# Trigger Event Playbooks（按触发器的主线分析与执行剧本）

本文件将触发器（Trigger Event）映射为“主线分析方向 + 证据白名单 + 执行剧本（Playbook）+ 落图规范”，用于降低多工具冲突导致的保守 hold，并让 AI 能输出“未来入场预判”（等待区间、确认线、失效线、目标区间），而不是只给一段不可读的文字。

## 目标与约束

### 目标
- 将“触发器 → 分析主线”固定化：每类触发只做该类最关键的问题判断，避免工具堆叠导致互相打架。
- 输出可执行的未来入场预判：明确“等哪里（entry zone）/等什么发生（confirm）/错了哪里算失效（invalidate）/目标在哪（targets）”。
- 把不确定性显式化：无法判定时，使用虚线标注上下两个方向的关键区间与目标，不强行给 SL。

### 非目标
- 不做仓位与风控自动化（由人工执行）。

### 落图语义约定
- **实线**：方向明确（ready），可执行的 entry / SL / TP（单向）。
- **虚线**：方向未确认（wait/uncertain），用于“预判/等待”的 entry_zone、confirm_line、双向 targets。
- **双色方案**：PRIMARY（主方案）用方向色；ALTERNATE（备选方案）用灰色弱化显示。

## 通用“裁决层”（Conflict Policy）

当指标/结构/形态给出矛盾信号时，禁止直接停摆为 hold，必须先尝试进入以下分流：

1) 若存在可定位的边界（level-zone / rectangle top/bottom / Structure_H/L），优先转入 Playbook，并输出 PRIMARY + ALTERNATE 两套互斥路径。
2) 若缺少可定位边界，或 confirm 条件不可验证，才允许 no_trade/hold。

证据优先级建议（从高到低）：
- 结构边界（Structure_High/Low、rectangle_range top/bottom、关键 level-zone 边界）
- 行为确认（close_outside / false_breakout / breakout_retest_hold / liquidity_sweep_recover）
- 指标过滤（RSI/MACD/Trend Exhaustion 作为“过滤与择时”，不用于推翻结构边界）

## Playbook 字典（统一语言）

- trend_pullback_limit：趋势延续，回踩到关键 zone/结构位后等待拒绝信号，再考虑进。
- trend_break_retest：趋势延续，突破→回踩→确认后进。
- range_mean_reversion：震荡区间，上沿做空/下沿做多（必须要“回收/拒绝”确认）。
- range_breakout_confirmed：区间突破跟随（必须突破+回踩确认）。
- exhaustion_confirmed_reversal：衰竭后反转（必须结构确认，禁止猜顶猜底 market）。
- no_trade：证据矛盾或条件不可验证，放弃交易。

## Trigger 1：RajaSR Level-Zone（rajasr_level_zone / raja_sr_touch）

### 主线问题
该 level-zone 触及/突破，当前更可能是：
- A) 真突破（breakout → retest → continuation）
- B) 假突破（sweep/false_breakout → reversal 或回撤）
- C) 不确定（uncertain → 标注双向路径）

### A) 真突破（Breakout Plan）
#### 关键约束
- **第一次接触该位置，禁止立刻入场**（尤其是 market）。
- 等待实体收线在 level-zone 之外（close_outside），并且出现 retest（回踩确认）后再入场。
- 若经历回踩后再突破，突破概率更高（break→retest→hold）。

#### 白名单证据（建议只引用这些）
- structure：
  - Structure_High/Low（trend_tf 与 exec_tf）
  - recent_structure_breaks（BoS/ChoCh）
- zones：
  - active_zones（仅使用触发 zone 与最近 1 个相邻 zone）
- behavior：
  - close_outside_level_zone / breakout_retest_hold
- indicators（过滤器）：
  - Trend Exhaustion：避免在 exhaustion 反向信号出现时追突破
  - RSI/MACD：避免“突破方向已极端超买/超卖 + 动能衰竭”

#### 预判输出（必须给）
- entry_zone：retest 区间（通常为 level-zone 边界附近的缓冲带）
- confirm：close_outside + retest_hold（或二次 BoS）
- invalidate：回到 zone 内部（突破失败）或结构失效位
- targets：
  - 目标 1：最近的高分相邻 level-zone（下一阻力/支撑）
  - 目标 2：更高周期 Structure_H/L 或下一结构位
- RR：需判断到目标 1 是否具有正向 RR；否则降级为 wait/uncertain

### B) 假突破（False Breakout Plan）
#### 典型条件（满足越多越偏向假突破）
- 突破方向与大周期方向逆势，或大周期近期出现反向 ChoCh。
- 价格触及 level-zone 但未突破关键 swing（例如未破 swing_low / swing_high）。
- 小周期出现 Trend Exhaustion（动能耗竭）或 sweep + recover。
- 出现 false_breakout（刺破后收盘回到区间/zone 内）。

#### 白名单证据
- behavior：
  - false_breakout（优先）
  - liquidity_sweep + recover
  - close_outside（若无则更偏假突破）
- structure：
  - ChoCh（反向换向）优先级高于 RSI/MACD
- indicators（佐证）：
  - Trend Exhaustion reversal（exec_tf）
  - RSI/MACD：背离/动能衰竭只做加分

#### 预判输出
- entry_zone：zone 边界附近的“失败突破回收区”
- confirm：回收后再跌回/站回 zone 内 + 反向结构确认（ChoCh）
- invalidate：真正突破并站稳（close_outside + retest 成立）
- targets：
  - 目标 1：对侧最近 zone
  - 目标 2：rectangle_range 另一端/结构位（若存在）

### C) 不确定（Uncertain）
当真突破与假突破证据接近、或缺少关键确认事件时：
- 不给 SL（避免伪确定性）。
- 在图上用虚线标记：
  - level-zone 上下边界
  - 上方目标（最近阻力 zone）与下方目标（最近支撑 zone）
  - 并明确“确认线”：close_outside 的阈值

## Trigger 2：MSB Break（msb_zigzag_break / bos_choch）

### 策略原则
- 将 MSB Break 从“直接入场触发器”降级为“结构提示器”。
- MSB Break 本身一般不立刻入场，后续必须回到关键 level-zone / rectangle 边界去验证“站稳/没站稳”。

### 白名单证据
- structure：BoS/ChoCh、Structure_H/L
- zones：active_zones（最近 1 个）或 rectangle_range top/bottom
- behavior：breakout_retest_hold / close_outside（用来判断站稳）

### 输出要求
- 若 break 发生但未站稳：输出 wait，并画出 retest zone（未来入场预判）。
- 若 break + retest_hold：才允许 ready 并给 entry/sl/tp。

## Trigger 3：Rectangle Range Breakout（rectangle_range breakout）

### 主线问题
该 breakout 是否值得参与？
- A) 趋势中继突破（可做，成功率高）
- B) 大震荡里的“假突破/噪声突破”（应 hold 或仅给双向虚线预判）

### A) 突破入场（Breakout Plan）
#### 条件
- breakout 与大周期方向一致（或至少不逆势）
- breakout 后出现 retest_hold（站稳）
- 距离下一个高分 level-zone 有足够空间（目标不太近）

#### 白名单证据
- rectangle_range（top/bottom、touches、containment/efficiency）
- close_outside / breakout_retest_hold
- structure：大周期结构方向（Market_Structure）
- indicators（锦上添花）：vol_regime=expanding、volume_activity=spike、ATR 合理

#### 输出与落图
- entry_zone：retest 区间（贴着 top/bottom）
- confirm：close_outside + retest_hold
- invalidate：回到 rectangle 内
- targets：下一高分 level-zone / Structure_H/L
- 同时标记 SL/TP（实线）

### B) Hold/低确定性（Inside Bigger Range）
当 rectangle_breakout 被“更大级别震荡”包裹时（例如 H1/M15 都是 Consolidation，且更大级别 rectangle/多 zone 重叠）：
- 输出 hold 或 uncertain
- 画虚线：当前价格上下最近的 level-zone 与 rectangle 边界
- 明确说明“突破失败/站稳失败”的条件线

## Trigger 4：Trend Exhaustion（TE 三角出现的那根）

### 主线问题
该 TE 反转是否“真反转”？

### A) 真反转（Confirmed Reversal）
#### 条件建议
- TE box 的极值“抬高/降低”体现结构改善（例如 bullish reversal 时：本次 box low 高于前低）。
- exec_tf（M15）在 TE 前后出现结构确认：MSB Break(ChoCh) 或反向 BoS。
- 反转发生在关键 level-zone 附近（更可靠）。

#### 白名单证据
- Trend Exhaustion（reversal 标记）
- structure：ChoCh/BoS、Structure_H/L
- behavior：liquidity_sweep + recover（加分）
- indicators：RSI/MACD 仅作辅助（不作主证据）

#### 输出与落图
- entry_zone：确认后的 retest 区（或反向突破触发区）
- confirm：反向结构确认线（ChoCh/BoS level）
- invalidate：跌破/突破 TE box 极值
- targets：最近对侧 level-zone / rectangle 对侧

### B) 假反转 / 趋势中继（Hold 或小尝试）
当 TE 出现在大周期趋势中继（例如 H1 仍强趋势，TE 只是新低/新高延伸过程）：
- 输出 hold 或 uncertain
- 虚线标记：当前上下最近 level-zone（可能触及的区域）
- 明确：需要看到结构确认（ChoCh/BoS）才能升级为 reversal playbook

## 指标/结构/形态筛选（按事件白名单）

| 触发器 | 主证据（必须） | 次证据（可选） | 禁用/降权（避免误导） |
|---|---|---|---|
| raja_sr_touch/level_zone | zone 边界、close_outside、false_breakout、retest_hold | TE、RSI/MACD 过滤 | 仅凭 RSI 超买/超卖推翻结构 |
| msb_zigzag_break | BoS/ChoCh level、Structure_H/L | 关联 zone/rectangle 的站稳验证 | 把 break 当成“立刻 market 入场” |
| rectangle_range breakout | rectangle top/bottom、站稳/回到区间内 | vol_regime、volume_activity、ATR | 无 retest 就直接判 ready |
| Trend Exhaustion | TE reversal + 结构确认（ChoCh/BoS） | sweep+recover、RSI/MACD 背离 | 单独 TE 不配结构确认就强行反转 |

## 实施建议（为 AI 提供“触发器主线分析方向”）

最小可用方案（Prompt-only）：
1) 触发器路由：不同 trigger_type 使用不同“主线模板”（本文件的对应章节）。
2) 证据白名单：每类触发只允许引用白名单证据作为主证据，其它证据只能写为备注，不得推翻结论。
3) 输出规范：必须输出 PRIMARY + ALTERNATE，并给出 entry_zone/confirm/invalidate/targets（可落图）。

稳定方案（Prompt + 轻量校验）：
1) 后端对输出做校验：entry_zone 必须来自 zone/rectangle/structure；confirm/invalidate 必须可解析到价位。
2) 若不可解析：自动降级为 uncertain 并只画边界虚线与双向 targets。

## 交易者补充建议（可选增强）
- 统一“站稳”的定义：例如需要连续 N 根 close_outside（N=2）才算站稳，避免单根噪音。
- 引入“距离过滤”：距离下一高分 level-zone < X * ATR 时，禁止 breakout playbook（空间不够）。
- 统一“retest 成功”定义：回踩触及 zone 边界后，收盘回到突破方向外侧，且未出现反向 false_breakout。

## 待确认问题（便于后续固化到系统）
- “第一次接触”定义：以 zone.last_touch_age_candles <= ? 作为首次触及还是最近一次触及？
- close_outside 判定：需要 1 根还是 2 根收盘确认？
- retest 区域宽度：用 zone 自带宽度、还是用 ATR * k 生成缓冲带？
- 趋势中继 vs 大震荡包裹：你希望用什么量化判定（multi_tf_alignment.consistency + rectangle containment/efficiency + vol_regime 是否足够）？

