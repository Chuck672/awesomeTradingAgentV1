# awesomeTradingAgentV1 代码知识库 (Code Wiki)

## 1. 项目概述 (Project Overview)

**awesomeTradingAgentV1** 是一个前沿的 AI 驱动的量化交易图表系统。系统将大语言模型（LLM）与专业量化图表引擎（Lightweight Charts）深度结合，采用了高度抽象的 **Agentic Workflow（多智能体协同）** 模式。

本项目的核心目标是突破传统脚本化交易工具的限制，赋予交易面板“思考”与“行动”的能力，通过多 Agent 协同工作，实现从市场数据收集、深度指标分析，到最终图表交互与风险控制的全自动化闭环。

---

## 2. 系统架构 (System Architecture)

系统核心采用了 **1+2 的多智能体 (Multi-Agent) 架构**，基于 Python FastAPI 提供后端底座，LangGraph 作为 Agent 编排框架，前端使用 React (Next.js) 结合 Lightweight Charts 负责呈现交互。

### 2.1 Agent 编排模型

*   **👑 Supervisor (主 Agent / 路由节点)**：
    *   **职责**：系统的大脑。不直接绑定或执行具体工具，仅负责全局统筹、意图识别与任务路由。
    *   **机制**：根据当前的对话上下文、图表状态，决定下一步是进行市场深度分析（路由至 Analyzer），还是直接执行图表操作与风控（路由至 Executor），亦或是结束当前工作流 (FINISH)。
*   **🔍 Analyzer (分析 Agent)**：
    *   **职责**：负责“读”和“思考”。
    *   **机制**：被授权调用数据查询与指标计算工具。能够拉取 K 线数据、计算技术指标（如 RSI, MACD）、分析 Volume Profile（成交量分布）以及识别 RajaSR（动态支撑阻力）和 MSB（市场结构破坏）。它的任务是为交易决策提供严谨的数据支撑并给出量化评分。
*   **🛠️ Executor (执行 Agent)**：
    *   **职责**：负责“写”和“行动”。
    *   **机制**：仅被分配动作类工具，负责风险控制逻辑计算、在前端图表上执行物理绘制（如画趋势线、标记买卖点信号）以及操控 UI 状态（如切换时间周期、开启历史回放）。

---

## 3. 核心模块解析 (Core Modules)

### 3.1 前端模块 (`frontend/`)
*   **图表与插件系统 (`src/plugins/`)**：系统将复杂的量化分析逻辑深度定制为了 Lightweight Charts 的原生插件，保证了渲染的高性能与流畅度。核心插件包括：
    *   `MSB_ZigZag`：市场结构破坏识别。
    *   `RajaSR`：动态支撑与阻力位绘制。
    *   `VolumeProfile`：成交量分布图。
    *   `drawing-tools`：提供给 AI 调用的复杂画图工具集。
*   **控制面板 (`src/components/sidebar/`)**：包含如 `AgentAdvisorPanel`、`AlertsPanel` 等侧边栏组件，承载用户与多 Agent 系统的交互对话和状态监控。

### 3.2 后端模块 (`backend/`)
*   **Agent 编排引擎 (`services/agents/`)**：
    *   `graph.py`：基于 LangGraph 定义的状态流转图（State Graph），并封装了状态字典（AgentState）。
    *   `communication.py`：负责拦截 LangGraph 的中间执行状态，通过消息总线向前端实时广播。
*   **AI 与工具注册 (`services/ai/` & `services/strategy/`)**：
    *   包含 `chart_tools.py` 等文件，严格定义了供 LLM 调用的 Function Calling Schemas（如 `chart_set_symbol`, `draw_objects`）。
*   **量化指标域 (`domain/market/`)**：
    *   底层金融与数学逻辑的实现。包含传统的 TA 指标、K 线形态识别（Patterns）、以及高级结构识别算法（如 `raja_sr.py`, `msb.py`）。

---

## 4. 核心数据流向 (Data Flow)

系统的通信逻辑已从传统的“文本解析”演进为高效的“协议化推流”，主干数据流如下：

1.  **触发与上下文构建**：用户在前端发送指令或后台触发 Alert，后端 `trigger_decision` API 接收请求。`event_context_builder.py` 将当前价格、预计算的指标状态、关键阻力位等信息组装成结构化 JSON 喂给大模型。
2.  **Agent 循环与思考**：
    *   Supervisor 评估当前状态，决定流转给 Analyzer 还是 Executor。
    *   Analyzer 利用 ReAct 机制自主决定调用哪些数据 API，获取市场真实数据并得出结论。
    *   Executor 决定前端图表动作，生成具体的 Tool Calls（含坐标和画图参数）。
3.  **WebSocket 结构化推送**：后端在 `executor_node` 中拦截 Tool Call，由 `AgentCommunicationLayer` 直接包装成 `type: "tool_execution"` 的标准化 JSON 事件，通过 WebSocket 实时推送到前端，避免前端进行冗长且不稳定的文本正则解析。
4.  **前端无缝渲染**：前端监听到 WebSocket 指令后，直接调用 Lightweight Charts 实例的原生 API 执行画线、打标签或周期切换。

---

## 5. 技术债务与优化方案 (Optimization Plan)

基于当前的架构现状与内部剖析，系统存在以下需要重点攻克的技术债务及迭代优化方案：

### 5.1 Token 爆炸与幻觉缓解 (Dynamic Tool Binding)
*   **痛点**：目前系统中存在 20+ 个工具，如果在图编译时一次性全量绑定给 Agent，会导致 Context Window 消耗暴增，模型极易产生“选择困难症”和严重幻觉。
*   **优化方案**：实施 **动态工具注入 (Dynamic Tool Binding)**。在 Supervisor 节点先进行意图分类，动态地将相关工具的子集（如只下发 3-5 个特定的画图或查询工具）绑定给子 Agent，极大降低上下文噪音。

### 5.2 分析深度不可控 (Structured Output & SOP)
*   **痛点**：当前 Analyzer Agent 高度依赖 ReAct 机制，存在随机性。分析师有时看 RSI，有时看成交量，缺乏专业量化分析的标准化流程（SOP）。
*   **优化方案**：加强 State Management，利用 Structured Output（如 Pydantic）强制约束分析报告的输出格式。将发散式的 ReAct 改为确定性更高的多步执行链，确保每次分析覆盖核心量化指标。

### 5.3 人机协同 (Human-in-the-loop) 机制缺失
*   **痛点**：当前 Agent 工作流是“一脚油门跑到底”，在执行真实订单等高危操作时，无法暂停等待用户二次确认。
*   **优化方案**：利用 LangGraph 的持久化 Checkpointer（如 SqliteSaver）结合 `interrupt_before` 机制。在 Executor 下单或执行高危操作前将状态挂起，前端弹出审批确认框，用户同意后再通过 API 唤醒 (resume) 工作流继续执行。

### 5.4 多模态能力 (视觉化分析) 尚未打通
*   **痛点**：前端已经具备截取 Base64 图表的能力，但当前 LangGraph 链路仅支持纯文本消息传递，浪费了丰富的图表直观视觉信息。
*   **优化方案**：重构 HumanMessage 结构，引入 `image_url` Content Blocks。将轻量化的图表截图发送给具备视觉能力的大模型（如 GPT-4o 或 Claude 3.5 Sonnet），实现真正的“看图说话”，提升形态识别准确率。
