# 多 Agent 系统当前痛点与优化方向 (QuantLogicLab)

本文档整理了当前基于 LangGraph 的多 Agent 交易分析系统中存在的核心痛点，以便在后续迭代中逐个攻破。

## 1. 工具调用与结构化输出的兼容性冲突

- **痛点描述**：当使用 LangChain 的 `create_react_agent` 赋予 Agent 调用外部工具的能力时，底层框架会强制将工具的 Schema 描述以 `prefix` (前缀) 的形式注入到发送给大模型的系统提示词中。然而，像 SiliconFlow 这样严格遵循 OpenAI 规范的 API 平台，**在启用** **`response_format={"type": "json_schema"}`** **(Structured Output) 时，明确禁止在 messages 中携带特定的 prefix**，导致 HTTP 400 (Value error, prefix is not allowed) 致命错误。
- **当前妥协方案**：在 `Analyzer` 节点中被迫放弃了原生的 Structured Output，退而求其次使用了“强提示词约束 + 正则表达式手动提取 JSON” 的 Fallback 模式。
- **负面影响**：丧失了 API 语法层面的绝对稳定性（Grammar Level Determinism），一旦模型出现幻觉不输出 JSON 代码块，整个分析报告提取流程就会崩溃。

## 2. Agent 分析深度的不确定性 (ReAct 机制的随机性)

- **痛点描述**：目前的 `Analyzer` 被赋予了一个包含 5 个数据工具的“工具箱”（涵盖基础 K 线、传统指标、RajaSR 市场结构、经济日历等）。由于使用的是 ReAct (Reasoning and Acting) 架构，**大模型每次会自主决定调用哪些工具**。
- **当前妥协方案**：完全依赖大模型（如 Qwen-72B 或 DeepSeek-V3）的即兴发挥。有时它只看 RSI 和 MACD 就草率下结论，有时又会去查 Volume Profile。
- **负面影响**：分析报告的结构、深度和侧重点在不同时间点极其不稳定，缺乏专业量化分析师应有的“标准化研判流程（SOP）”。

## 3. 状态流转与指令丢失风险 (State Management)

- **痛点描述**：在 LangGraph 中，各节点之间的信息传递依赖于全局的 `AgentState` 字典。在之前的版本中，Supervisor 虽然在 CoT 推理中生成了给 Executor 的画图坐标指令，但由于没有在 State 中专门开辟字段保存这些指令，导致流转到 Executor 时指令完全丢失，Executor 无所适从只能罢工。
- **当前妥协方案**：已在 `AgentState` 中新增 `executor_instruction` 字段，并在 Supervisor 和 Executor 之间打通了指令传递链路，使用动态注入 Prompt 的方式让 Executor 听命行事。
- **负面影响**：虽然暂时解决，但暴露了目前的状态管理（State Management）过于扁平和脆弱。随着未来加入更多的 Sub-Agents（如 Risk Manager, Backtester），仅仅依靠 `messages` 列表和几个字符串列表来维持复杂的交易上下文将变得难以维护。

## 4. 冗余的 API 交互与高延迟

- **痛点描述**：每次用户请求或后台事件触发，系统都需要经过 `Supervisor (路由)` -> `Analyzer (思考+调用工具)` -> `Supervisor (Review)` -> `Executor (画图)` -> `Supervisor (结束)` 这样漫长的链路。
- **当前妥协方案**：虽然加了 `temperature=0.1` 来减少模型幻觉，并实现了遇到 `executor` 消息直接 `Short-circuiting to FINISH` 来节省一次 LLM 调用的优化，但整体耗时依然不短。尤其是遇到 Fallback 降级重试时，耗时甚至会翻倍。
- **负面影响**：用户体验上的响应速度较慢（长达数十秒甚至分钟级），且消耗的 Token 成本随交互次数成倍增加。

## 5. 多模型兼容性与配置动态生效

- **痛点描述**：系统最初依赖硬编码读取 `.env` 文件获取模型 API Key 和 URL。虽然现在已经打通了从前端 UI（Agent Configurations 面板）动态下发配置给后端的链路，但针对不同模型的特性差异（如 Qwen 支持的上下文长度、DeepSeek 对特定 prompt 的敏感度）缺乏精细化适配。
- **当前妥协方案**：所有的 Agent 统一使用一套泛化的 Prompt 和 `ChatOpenAI` 接口封装。
- **负面影响**：当用户切换到一个在 Structured Output 或 Function Calling 方面较弱的开源模型时，系统极易大面积崩溃或陷入逻辑死循环。

