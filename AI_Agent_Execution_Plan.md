# AI驱动的Lightweight Charts智能交易系统 - 执行计划

## 1. 核心架构设计

在现有代码库（`awesomeTradingAgent`）的基础上，我们将采用以下最终技术方案来实现多 Agent 智能交易系统：

1. **后端技术栈与 Agent 框架**：
   - 保持 **Python (FastAPI)** 后端架构，深度集成现有的 MT5 数据源与 SQLite 管理。
   - 引入 **LangGraph (Python原生)** 构建 Supervisor、Analyzer 和 Executor 的多 Agent 协作状态机。
   - 大模型调用复用 `openai_compat.py`，支持灵活配置 Base URL 和 API Key，以便无缝切换 OpenAI、Anthropic、DeepSeek 等模型。
   - **异步非阻塞**：Agent 任务将作为后台异步任务运行。HTTP 接口仅负责触发并立即返回，避免长耗时推理导致的接口超时。
2. **状态同步机制 (WebSocket)**：
   - 废弃轮询方案，全面采用 **WebSocket 实时推送**。
   - 依托现有的 `message_bus.py`，当 Agent 思考或状态切换时，后端主动向前端广播 `agent_status`，实现毫秒级的 UI 指示灯亮起和流式消息渲染。
3. **Tool Calling 权限与职责拆分**：
   - **主 Agent (Supervisor)**：系统大脑，负责全局统筹和判断（路由到 analyze、execute 或 finish）。无直接调用工具权限。
   - **分析 Agent (Analyzer)**：负责技术分析与策略决策，仅分配**查询类工具**（获取K线、计算指标、查询支撑阻力等）。
   - **执行 Agent (Executor)**：负责风控、画图与下单，仅分配**动作类工具**（风控计算、生成图表绘制指令、下单）。
   - *注：现有* *`chart_tools.py`* *将被拆分为* *`analyzer_tools`* *和* *`executor_tools`。保留* *`get_all_tools()`* *方法以兼容旧的 AI Chat 功能。*
4. **数据投喂周期与频率**：
   - **多周期结构 (Timeframe)**：投喂数据时采用多周期组合（如 `H1` 用于判断宏观趋势，`M15` 用于寻找入场点），提升决策视野。
   - **触发频率**：禁止 Tick 级别的高频触发，采用以下两种模式唤醒 Agent：
     1. **定时唤醒**：在主周期 K 线收盘时（如每 15 分钟或每 1 小时）触发一次全局检视。
     2. **事件唤醒**：当系统监控到价格突破或触碰关键技术位（如 RajaSR 阻力区）时，主动唤醒 Agent 进行实时干预。

***

## 2. 实现步骤 (Execution Plan)

### 阶段零：环境隔离 (Environment Isolation)

为了防止当前系统与生产环境中正在运行的 `awesomeChartV3` 产生冲突，我们首先需要：

1. **隔离数据库沙盒路径**：修改 `backend/database/app_config.py`，将 SQLite 的数据文件夹由 `.awesome-chart-v3` 更改为 `.awesome-trading-agent`。
2. **更改后端端口**：修改 `backend/main.py` 和 `run_backend.py`，将 FastAPI 默认启动端口由 `8000` 变更为 `8123`。
3. **更改前端端口**：修改 `frontend/package.json` 中的启动脚本，将前端由 `3000` 变更为 `3123`，并同步更新前端所有直连后端的硬编码端口。

### 阶段一：基础设施与独立记忆库 (Backend Data & DB)

1. **独立沙盒数据库**：在 `backend/database/` 下新建 `agent_sandbox.sqlite`，结合 LangGraph 官方的 `AsyncSqliteSaver` 存储 Agent 的 Checkpoint（记忆与状态），防止测试期产生的垃圾数据污染核心交易库。
2. **依赖安装**：在 `requirements.txt` 中添加 `langgraph`, `langchain-openai`, `langgraph-checkpoint-sqlite` 等核心依赖。

### 阶段二：指标算法 Python 化与数据组装 (Indicators & Context)

1. **核心指标重写**：将前端 TypeScript 编写的核心指标（如 RajaSR、MSB\_ZigZag、TrendExhaustion、VolumeProfile 等，**排除 Bubble**）算法逻辑使用 Python 重写，放置于 `backend/services/chart_scene/indicators.py` 或专属工具模块中。
2. **封装 Tool Calling**：将上述重写后的 Python 算法封装为标准的大模型工具（Tools），供 Analyzer 节点调用。
3. **数据预处理模块**：编写上下文组装函数，将原始的 K 线数组转化为高密度、结构化的 JSON（例如提取“趋势特征描述”、“当前价格距关键阻力位的距离”等），避免 Token 浪费。

### 阶段三：LangGraph 多 Agent 核心开发 (Backend Agent Logic)

1. **定义 Agent State**：创建继承自 `TypedDict` 的全局状态，包含 `messages`, `current_agent`, `next_action`, `json_context` 等。
2. **构建 Agent 节点**：
   - **Supervisor Node**：注入系统提示词，根据当前状态决定下一步路由。
   - **Analyzer Node**：绑定分析工具，将见解和分析结果写入 State。
   - **Executor Node**：绑定执行工具，生成具体的 UI 动作指令或交易订单。
3. **编译 Graph 与持久化**：使用 `StateGraph` 连接节点，接入 `AsyncSqliteSaver` 形成带持久化记忆的闭环。

### 阶段四：通信层与前端 UI 交互 (Backend <-> Frontend)

1. **状态拦截器 (agent\_status)**：在 LangGraph 节点转换时触发回调，提取当前 Agent 名称、工作状态（thinking/acting/idle）及流式输出文本。
2. **WebSocket 广播**：通过 `message_bus` 将上述状态实时推送至前端。
3. **AI Advisor 右侧边栏集成**：在前端右侧边栏（RightPanel）集成全新的 AI Advisor 面板，保持与现有项目设计风格一致。
   - **状态指示与对话**：顶部包含 Supervisor、Analyzer、Executor 的状态指示灯（根据 WS 推送点亮），下方通过聊天框组件流式渲染思考与决策日志。
   - **Agent 可视化配置**：面板内提供设置按钮，支持为每个 Agent **独立配置**大模型参数（Base URL、Model、API Key），实现多模型（如 Qwen/Claude/GPT）混合驱动。
   - **触发控制区**：提供手动“让 AI 决策”按钮，以及定时/事件触发的控制开关。
4. **图表指令解析渲染**：前端捕获 Executor Agent 下发的标准 JSON UI Action（如 `{"action": "draw_marker", "price": 1.1200, "type": "buy"}`），调用 Lightweight Charts 的 Custom Series 或 Drawing Tools 插件在图表上呈现。

### 阶段五：Tool Calling 体系全量重构与扩展设计 (Future Work)

为了支撑数十种复杂的图表控制、自动化分析与交互需求，现有的临时 Tool Calling 将被全面重构。我们将采用 **命名空间 (Namespace)** 的方式，将工具分为五大核心模块，并重新定义大模型输出参数标准。

#### 5.1 视图与环境控制 (View & Environment Control)

负责图表的基础环境设置、周期切换以及截屏能力。

- **`chart_set_symbol(symbol: str)`**: 切换当前图表交易品种（如 XAUUSDz）。
- **`chart_set_timeframe(timeframe: str)`**: 切换图表时间周期（M1, M15, H1, H4, D1）。
- **`chart_take_screenshot(action: str)`**: `action` 可选 `save_local` (保存本地) 或 `feed_ai` (将截图作为多模态输入投喂给 Analyzer 进行视觉复核)。
- **`chart_replay_start(start_time: int)`**: 启动 Bar Replay 历史回放，定位到指定时间戳。
- **`chart_replay_control(action: str, speed: int)`**: 控制回放进度，`action` 可选 `play`, `pause`, `stop`，`speed` 控制播放倍速。

#### 5.2 数据与分析抓取 (Data & Analytics)

**专属 Agent**: Analyzer
将原有的黑盒 `get_market_context` 拆分为职责单一的数据引擎，减少冗余计算。

- **`data_query_ohlcv(symbol, timeframe, limit)`**: 纯粹拉取指定数量的 K 线基础数据。
- **`data_compute_indicators(type: list)`**: 按需计算传统指标，传入 `["RSI", "MACD", "EMA"]`。
- **`data_compute_structure()`**: 专门用于计算量价分布 (Volume Profile) 与市场结构 (RajaSR / MSB / ChoCh)。
- **`data_query_economic_calendar()`**: 获取未来 24/48 小时的重大财经日历数据（如非农、CPI 等），供分析师在给出交易建议前进行风险规避。

#### 5.3 绘图分析管理 (Drawing & Overlays)

**专属 Agent**: Executor
负责所有可视化标记的绘制与清理。摒弃摊平参数，强制使用嵌套数组结构。

- **`draw_objects(objects: list)`**: 通用绘图入口。
  - 支持画线：`{"type": "hline", "price": 1.10}` 或 `{"type": "trendline", "t1": xxx, "p1": xxx, "t2": xxx, "p2": xxx}`。
  - 支持标记：`{"type": "marker", "time": xxx, "position": "belowBar", "text": "Buy", "shape": "arrowUp"}`。
  - 支持图形：矩形框 `box`、趋势箭头 `arrow` 等所有图表组件原生支持的工具。
- **`draw_clear_all()`**: 移除图表上的所有手动或 AI 绘制的线条和标记。
- **`draw_remove_object(id: str)`**: 移除特定的绘图对象。

#### 5.4 指标视图管理 (Indicator Management)

负责控制主副图指标的显示状态，让图表保持清爽。

- **`indicator_toggle(id: str, visible: bool)`**: 开启或隐藏特定指标（如打开 RSI 附图，关闭 Bollinger Bands）。
- **`indicator_clear_all()`**: 移除或隐藏图表上的所有指标，恢复纯净 K 线图。

#### 5.5 任务控制与容错机制 (Task Control & Error Handling)

摒弃重型 Checkpointer 的复杂状态持久化，转而实现更轻量级、更可控的任务干预与自动容错。

- **`system_abort_task()`**: （后端机制）在前端提供一个“中断/停止”按钮。当用户发现 AI 走偏或者生成时间过长时，直接发送中止指令，后端通过 `asyncio.Task.cancel()` 强制掐断当前的图流转，并恢复空闲状态。
- **动态上下文注入 (Brief State Manifest)**: 每次调用 Supervisor 前，向其注入当前图表状态（如：是否有线、选中的指标、最后一次操作等），避免上下文丢失。
- **`INSUFFICIENT_PERMISSION_FOR_TASK`** **(容错重试)**: 若 Analyzer 发现缺少必要权限（如需要画图却没拿到 draw\_tools），触发特殊错误码，Supervisor 捕获后主动重算权限并补发。

***

## 6. 核心难点解析与重构实施路径 (Implementation Roadmap)

基于当前现状，全量重构的稳妥实施路径如下（按优先级排序）：

### 战役一：通信协议标准化 (Protocol Standardization) - \[最高优]

- **目标**：彻底废弃前端的正则提取机制，消除 JSON 解析脆弱性。
- **实施**：后端拦截 LangGraph 的 Tool Calls，将其包装为 `{ "type": "TOOL_EXECUTION", "tool": "xxx", "payload": {...} }` 的结构化 WebSocket 事件。前端基于此类型直接触发控制器，实现前后端解耦。

### 战役二：意图路由与提示词调教 (Intent Routing & Prompt Tuning)

- **目标**：解决 Token 爆炸与模型幻觉，使 Supervisor 成为聪明的调度中枢。
- **实施**（参考 `提示词调教.md`）：
  - **多标签分类 (Multi-label)**：废弃单选，让 Supervisor 输出所需能力组合 `required_capabilities: ["MARKET_DATA", "VISUAL_ANNOTATION"]`。
  - **逻辑依赖链**：在 Prompt 中硬编码“画图必带分析”、“交易必带风控”等前置规则。
  - **思维链 (CoT)**：强制 Supervisor 输出 `user_intent_analysis`, `logical_steps`, 和 `active_tool_groups` 三段式 JSON。
  - **边缘案例 (Few-shot)**：在提示词中预埋 3-5 个复合意图、纯展示意图的边界示例。
  - **动态绑定 (Dynamic Binding)**：根据 Supervisor 输出的组别，动态向 Analyzer 和 Executor 注入特定子集的工具（如只给 `draw_` 工具），大幅降低 Token 消耗。

### 战役三：任务中断与状态清零 (Task Cancellation)

- **目标**：实现对失控任务的紧急制动（代替 Checkpointer 方案）。
- **实施**：前端新增“Stop”按钮。后端在 `run_agent_workflow` 的外层套用可取消的异步任务管理字典。当接收到中断信号时，直接 `cancel()` 该协程，并清空当前会话在内存中的临时图状态，广播 `finished` 或 `aborted` 信号。

### 战役四：多模态与全量工具库扩充 (Multimodal & Tool Expansion)

- **目标**：为系统装上“眼睛”并接入 20+ 个细分能力。
- **实施**：
  - 改造 HTTP 触发接口，支持接收 Base64 截图，并在构建 `HumanMessage` 时采用 `image_url` 数据块。
  - 批量实现第 5.1 到 5.4 节规划的 `chart_`、`data_`、`draw_`、`indicator_` 命名空间工具。

***

## 4. 事件触发设计 (Event-based Triggers)

经过讨论，我们已确定事件触发机制的最终方案：

1. **双重触发支持与配置化**：
   - 系统将在代码层同时预设 **RajaSR 阻力/支撑触碰** 和 **MSB\_ZigZag 结构突破 (BoS/ChoCh)** 两种触发器。
   - 提供参数配置接口，允许用户可视化选择开启哪些事件、以及事件监控的 K 线时间周期（Timeframe）。
2. **触发频率与防抖控制**：
   - **MSB\_ZigZag**：由于 15min\~30min 周期的结构破坏本身频率就不高，因此**不设触发频率限制**，一旦发生立刻唤醒 Agent。
   - **RajaSR**：由于价格可能在关键位附近反复摩擦，设定 **30 分钟冷却期 (Cooldown)**，即同一个 Zone 在 30 分钟内最多只触发一次唤醒。
   - **指标瘦身 (Top-N)**：RajaSR 聚类出的 Zone 会按有效触点数 (Score/Touches) 降序排列，暴露一个 `max_zones` 参数（默认如 5），过滤掉弱级别的区域，确保提供给 Agent 的都是高实用性的关键阻力位。

***

## 5. 待办探讨 (To-Do List)

- [ ] **【前端集成】探讨如何在前端的 Alerts 面板中添加对** **`ai_agent_trigger`** **新规则类型可视化的增删改查。**

