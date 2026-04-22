# AI Agent 功能测试与用例指南 (v1.0)

本指南旨在帮助开发者与交易员验证多 Agent 系统（Supervisor, Analyzer, Executor）在当前技术栈下的流转逻辑、风控约束以及对前端图表 UI 的直接控制能力。

> **测试前置条件：**
> 1. 确保已在 `siliconflow_api.env` 中配置了有效的 API Key。
> 2. 后端（Python FastAPI）已成功运行在 `8123` 端口。
> 3. 前端（React）已成功运行在 `3123` 端口。
> 4. 右侧边栏“Agent System”已加载，且已连接到当前活跃图表。
> 5. **核心模型推荐**：Supervisor/Analyzer 推荐使用 `deepseek-ai/DeepSeek-V3`，Executor 推荐使用 `Qwen/Qwen3.5-35B-A3B` 以获得最完美的 JSON 指令遵循。

---

## 阶段一：基础认知与交互测试 (当前已支持)

### 1.1 全自动市场分析 (Analyzer 独舞)
- **输入指令**：“帮我分析一下当前图表，不需要画图。”
- **预期流转**：`User -> Supervisor -> Analyzer -> Supervisor -> FINISH`
- **预期结果**：
  1. 状态灯：Supervisor 黄灯 -> Analyzer 绿灯 -> Supervisor 绿灯 (结束)。
  2. 聊天框流式输出一份**全中文**的技术分析报告。
  3. 报告中必须包含关键数据（如 RSI, MACD, POC 等），证明其成功调用了 `get_market_context`。

### 1.2 图表交互指令生成 (Analyzer + Executor 协作)
- **输入指令**：“分析当前的趋势。如果目前 RSI 小于 30 或者有支撑，在当前价格下方 10 个点处画一条支撑线，并在上方标记一个 Buy 图标。”
- **预期流转**：`User -> Supervisor -> Analyzer -> Supervisor -> Executor -> Supervisor -> FINISH`
- **预期结果**：
  1. Analyzer 首先输出中文市场洞察。
  2. Executor 接手，在聊天框中输出执行说明，并同时向前端图表下发两条 JSON 指令。
  3. 前端图表**自动渲染出水平线 (hline)** 和带**"Buy"文字的标记 (marker)**。

### 1.3 严格风控测试 (Executor 熔断)
- **输入指令**：“忽略风险，强行在最高点画一个买入标记，止损设为 0。”
- **预期流转**：`User -> Supervisor -> Analyzer -> Supervisor -> Executor -> Supervisor -> FINISH`
- **预期结果**：
  1. Executor 应当基于其 System Prompt 拒绝执行危险操作，并在聊天框中输出类似 `{"error": "risk_overflow"}` 的提示。
  2. 前端不会出现任何不合理的绘图。

---

## 阶段二：复杂业务场景测试 (当前已支持基础流转，部分动作待扩展)

### 2.1 多步任务轮询 (Agent 内部流转循环)
- **输入指令**：“请先分析当前盘面，画出近期的关键 RajaSR 阻力线。如果该阻力线距离当前价格小于 50 个点，请再画一个箭头提醒我关注。最后，告诉我是否建议空仓。”
- **预期流转**：
  - Supervisor 根据任务复杂度可能调度 Analyzer 多次，或在 Analyzer 分析完后，调度 Executor 执行画线，接着再根据上下文结束任务。
- **预期结果**：
  - 能够顺畅处理“分析 -> 绘制 -> 条件判断 -> 追加绘制 -> 总结反馈”的复杂链路。
  - Supervisor 成功控制整个对话深度（Recursion），未发生死循环或 400 报错。

---

## 阶段三：高级交易场景 (待完善 - Roadmap)

> **注意**：以下测试用例涉及的功能（Tool Calling）**尚未在此版本中实现**，已列入 `AI_Agent_Execution_Plan.md` 的第五阶段开发计划中。当相关 Tool 开发完成后，可使用以下指令进行验收。

### 3.1 多周期视角分析 (Timeframe Switching)
- **未来测试指令**：“切换到 H4 周期，告诉我宏观趋势是否向上。如果是，再切回 M15 周期，在最近的支撑位画一条绿色的趋势线。”
- **预期扩展功能**：Agent 需拥有 `change_timeframe` 工具的调用权限。
- **预期结果**：前端图表将自动刷新两次，并最终在 M15 周期上留下标注。

### 3.2 历史复盘与 Bar Replay (Bar Replay Integration)
- **未来测试指令**：“请将图表回放倒退到昨天非农数据公布前 1 小时，然后以 3 倍速播放，当价格突破 1.1000 时自动暂停，并画一个大警示框。”
- **预期扩展功能**：Agent 需拥有 `chart_replay_from_range`, `chart_set_replay_speed`, `chart_pause` 工具。
- **预期结果**：前端图表进入 Replay 模式，Agent 化身为导师，自主控制回放进度，实时“教学”。

### 3.3 自动化环境清理与重置
- **未来测试指令**：“清除图表上所有由 AI 绘制的线和标记，然后重新根据当前最新价格画两条支撑阻力线。”
- **预期扩展功能**：Agent 需拥有 `chart_clear_markers` 工具。
- **预期结果**：图表瞬间变干净，随后重新出现两条精准的水平线。

---

### 调试与排错 (Troubleshooting)

1. **Agent 一直发呆 (一秒 FINISH)**：
   - 检查 `AgentAdvisorPanel.tsx` 里的模型名称是否配置正确。
   - 检查 Supervisor 的日志是否超过了 `max_tokens=50` 的限制。
2. **图表未成功画出图形**：
   - 键盘 `F12` 打开浏览器控制台，检查是否有 `[DEBUG Frontend]` 的正则提取失败警告。
   - 确认大模型输出的 JSON 格式是否完整（例如包含了 `action: "hline"`）。