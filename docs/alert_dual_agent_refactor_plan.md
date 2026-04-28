# Alert System 双 Agent 重构实施方案（事件触发专用）

## 0. 目标与边界
- 目标：将 **事件触发链路** 从当前 3-Agent（Supervisor/Analyzer/Executor）拆分为 **双 Agent**：
  - Agent A：`analyzer`（只消费“预计算+历史汇总 JSON”，尽量不做指标工具调用）
  - Agent B：`executor`（仅负责绘图动作，缩减 tool list）
- 边界：保留当前 3-Agent 体系，仅用于“用户主动提问”场景；事件触发不再走 Supervisor 路由。
- 非目标：当前阶段不引入自动下单，仅保留分析与画图。

## 1. 实施步骤（分阶段，低风险上线）

### 阶段 A：架构分流（不改业务语义）
1. 新增事件专用 pipeline 开关（建议字段：`pipeline_mode`）
   - `interactive_tri_agent`：沿用当前 3-Agent（默认给手动问答）
   - `event_dual_agent`：事件触发走双 Agent
2. 在告警触发入口携带 `pipeline_mode=event_dual_agent`。
3. 在 workflow 编排层按 `pipeline_mode` 选择图构建器：
   - 互动问答：`build_multi_agent_graph`（现有）
   - 事件触发：新增 `build_event_dual_agent_graph`
4. 事件双 Agent 的状态机固定为：
   - `START -> analyzer -> executor -> END`
   - 不经过 supervisor，避免额外路由轮次与耗时
5. 全量启用并增加可观测性日志：
   - 每个事件记录 `event_id/symbol/timeframe/trigger_time/pipeline_mode`
   - 记录关键耗时切片：`context_build_ms/analyzer_ms/executor_ms/telegram_ms`
   - 记录输入/输出摘要：JSON 体积、缺失指标列表、最终 signal

### 阶段 B：Analyzer 输入改造（上下文 JSON 化）
1. 增加“事件上下文打包器”（Context Builder）：
   - 输入：symbol/timeframe/trigger_type/current_price/rule snapshot
   - 输入：OHLCV 历史窗口（多周期）
   - 输入：预计算指标结果（见第 2 节）
   - 输出：统一 JSON（schema 固定）
2. Analyzer Prompt 调整为“仅基于 JSON 推理”：
   - 完全禁用工具调用（最稳态），不允许兜底补查工具。
3. Telegram 报告发送点：
   - Analyzer 完成后立即发送一条报告（事件双 Agent 单次流转下，此报告即最终版）。

### 阶段 C：Executor 收敛（只负责画图）
1. Executor 工具白名单收敛为绘图相关：
   - `draw_objects`、`draw_clear_all`（按需）
2. 不包含交易执行工具组（TRADE_EXECUTION/RISK_MANAGEMENT）。
3. Executor 输入采用结构化字段：
   - `entry/sl/tp/labels/colors/style`
4. 输出保持最短回执（便于系统解析）。
5. 绘图幂等与清理策略：
   - 画图前先执行“仅清 AI 绘图”，再执行 `draw_objects`
   - 同时引入“同价位重复画线”治理（建议在绘图侧使用稳定 object id 或 hline 去重 key）
   - 不允许清除用户手动绘制对象（需要明确区分 AI vs User 绘图）

### 阶段 D：上线策略（无回退）
1. 事件触发后仅走 `event_dual_agent`（不回退到 3-Agent 事件链）。
2. 异常处理以“可观测 + 降级输出”为主：
   - 指标缺失：在报告中显式列出缺失项并降低 strength
   - 广播/Telegram 失败：不阻断告警主循环，记录失败原因与重试次数

## 2. 预计算指标 Data 方案

### 2.1 建议最小指标集（先稳后扩）
- 价格与成交量基础：
  - `ohlcv`（H1/M15，必要时 M5）
  - `atr`（波动）
  - `volume_profile`（POC/VAH/VAL）
- 结构类：
  - `msb_zigzag`（BoS/ChoCh、结构高低点）
  - `swing_points`（最近 N 个 pivot）
- 动量趋势类：
  - `rsi`（默认 14）
  - `macd`（12,26,9）
  - `ema_fast/ema_slow`（如 20/50）
- 区域类：
  - `raja_sr_zones`（当前生效支撑阻力区，含上下沿与置信度）

### 2.1.1 后续要补充的指标 TODO（按优先级）
- P0（强相关/高收益）
  - `session_high_low`（亚洲/伦敦/纽约分时段高低点）
  - `liquidity_sweeps`（扫流动性/等高等低/假突破识别）
  - `fvg_imbalance`（FVG/IMB 区域，含回补状态）
- P1（增强质量）
  - `news_risk`（简化新闻/高波动时间窗标记，仅作为过滤）
  - `spread_slippage_proxy`（点差/滑点 proxy，用于强度折扣）
- P2（可选/实验）
  - `multi_timeframe_confluence_score`（多周期共振分数）
  - `market_regime`（震荡/趋势状态判别）

### 2.2 JSON 建议结构（Analyzer 输入）
```json
{
  "event": {
    "event_id": "uuid",
    "trigger_type": "raja_sr_touch",
    "symbol": "XAUUSDz",
    "timeframe": "H1",
    "trigger_price": 4675.404,
    "trigger_time": "2026-04-24T11:55:00Z"
  },
  "market": {
    "ohlcv": {
      "H1": [],
      "M15": []
    },
    "indicators": {
      "rsi": {},
      "macd": {},
      "ema": {},
      "atr": {},
      "volume_profile": {},
      "msb_zigzag": {},
      "raja_sr_zones": {}
    }
  },
  "constraints": {
    "output_schema": {
      "signal": "buy|sell|hold",
      "strength": "1-10",
      "entry": [],
      "sl": 0,
      "tp": []
    }
  }
}
```

### 2.3 指标并行计算可行性
- 结论：**可以并行**，且建议并行。
- 推荐方式：
  - I/O 型（读数据库/缓存）：`asyncio.gather`
  - CPU 型（重计算指标）：线程池或进程池（按指标成本分层）
- 并行注意点：
  - 使用同一时间截面（snapshot timestamp）保证一致性
  - 设超时与兜底（某个指标超时不阻断整体，标记 `missing`）
  - 结果加版本号（indicator_version）便于回放与排错

## 3. 如何不影响当前 3-Agent（兼容策略）
- 路由隔离：基于 `pipeline_mode` 做硬分流，不改现有 3-Agent 主路径。
- Prompt 隔离：事件双 Agent 使用独立 prompt 常量，不覆盖原 prompt。
- Tool 隔离：事件 Executor 使用独立 tool 白名单，避免误引入复杂控制工具。
- 配置隔离：alert rule 中独立 `agent_configs`（model、timeout、token、pipeline_mode）。
- 存储兼容：沿用现有 `alert_events` / `ai_reports`，可新增 metadata 字段记录 `pipeline_mode`。
- 回滚机制：双 Agent 异常时自动 fallback 到原事件链（可配置开关）。

## 4. 双 Agent 的上下文工程（Context Engineering）

### 4.1 上下文分层
- L0（事件元数据）：symbol/timeframe/trigger/rule snapshot
- L1（结构化市场数据）：OHLCV + indicators JSON（主输入）
- L2（短记忆）：最近一次同 symbol/timeframe 的 analyzer 结论（用于“修订版”判定）
- L3（输出约束）：固定 schema，减少自由文本

### 4.2 Token 控制策略
- 输入按窗口裁剪：
  - H1 最近 200-500 根
  - M15 最近 300-800 根
- 大对象摘要化：
  - `volume_profile` 仅传核心区间与关键节点
  - `zigzag` 仅传最近 N 个结构点
- 历史结论仅传“最近一次+差异摘要”，避免全量对话回灌

### 4.3 事件消息策略（你提出的方向）
- Analyzer 完成后立即发 Telegram：单条消息即最终版（事件双 Agent 单次流转）。
- `【修订】` 为可选能力：仅当未来引入“同一 event_id 二次分析”（例如某些预计算指标延迟到达、或你主动触发重算）时才需要。
- 不发送“执行细节回执”（按当前需求）。

## 5. 预计问题与攻克方案

### 问题 1：预计算和实时价格存在时间错位
- 风险：Analyzer 看到的指标与触发时刻不一致。
- 方案：引入 snapshot timestamp，所有指标按同一时刻封装；超时指标标记缺失而不是混用旧值。

### 问题 2：指标缺失导致分析不稳定
- 风险：某些指标失败导致输出漂移。
- 方案：在 JSON 中显式 `missing_indicators`，Prompt 要求缺失时降级推理并降低 `strength`。

### 问题 3：双 Agent 与三 Agent 结果风格不一致
- 风险：用户感知“同系统不同口径”。
- 方案：统一输出 schema（signal/strength/entry/sl/tp/reasoning），并在报告模板层做统一。

### 问题 4：重复触发导致 Telegram 噪音
- 风险：同一区间反复触发刷屏。
- 方案：事件去重窗口（symbol+timeframe+zone_key+TTL）与“修订优先”策略。

### 问题 5：绘图重复（同价位多线）
- 风险：Executor 每次重复调用造成叠线。
- 方案：绘图侧引入 hline 幂等 key（symbol+timeframe+price+label）或稳定 object id。

### 问题 7：仅清 AI 绘图的实现边界
- 风险：如果只有 `draw_clear_all`，会清空用户手工标注，影响体验；若不清理，则 AI 线条会重复叠加。
- 方案（低风险优先级从高到低）：
  - A. 新增 `draw_clear_ai`（推荐）：前端维护“AI 绘图 registry”，只清理 id 前缀为 `ai_` 的对象；后端 executor 在画图前调用该工具。
  - B. 扩展 `draw_clear_all` 增加过滤参数：例如 `draw_clear_all({ scope: "ai" })`；由前端按 scope 选择性清理。
  - C. 不提供清理工具，改为稳定 object id 幂等覆盖：同一 price+label 的线条始终覆盖更新，不新增；实现难点在于“覆盖”需要绘图层支持 replace/update。

### 问题 6：切换后难以定位慢点
- 风险：不知道慢在预计算还是 LLM。
- 方案：全链路埋点（trigger->context_build->analyzer->telegram_prelim->executor）并记录 P50/P95。

## 6. 需要你确认的问题（开始开发前）
### 6.1 已确认决策（基于最新讨论）
1. 事件双 Agent：全量启用，并增加后台 log 观测以便 debug。
2. Analyzer：完全禁用工具调用（最稳态）。
3. 预计算指标：首版按第 2.1 节“最小指标集”执行；扩展指标见第 2.1.1 节 TODO。
4. 绘图：采用 `draw_clear_ai`（仅清 AI 绘图）+ `draw_objects`；画图前先清理再绘制，并治理重复画线问题。
5. 事件链：异常不回退到 3-Agent 事件链，后续只用双 Agent 处理 alert。
6. 清理策略：不允许清除用户手动绘制对象，需要“仅清 AI 绘图”的能力。
7. “仅清 AI 绘图”落地形态：选择 A（新增 `draw_clear_ai` 工具；前端维护 AI registry 或以 `ai_` 前缀标记，只清 AI）。

### 6.2 仍需确认的问题（进入编码前）
1. Telegram 消息标题是否需要固定前缀（例如 `【Alert】` / `【RajaSR】`）以便过滤与检索？
2. 预计算窗口大小是否固定（H1 200-500、M15 300-800），还是按品种/波动自适应？

## 7. 对应现有代码锚点（实施时参考）
- 事件触发入口：`backend/services/alerts_engine.py`
- Workflow 编排入口：`backend/api/agent_routes.py`
- 3-Agent 图定义：`backend/services/agents/graph.py`
- 告警与报告存储：`backend/services/alerts_store.py`
- Telegram 发送：`backend/services/telegram.py`
