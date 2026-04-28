# event_dual Analyzer System Prompt（优化前 vs 优化后）

本文用于对比 **Alert 系统 event_dual（双 Agent）** 中 Analyzer 的提示词变化，便于你复盘“连贯性提升”与“交易效果变化”的关系。

## 0) 说明与来源

- **优化后（当前生效）**：来自代码 [agent_routes.py](file:///d:/TraeProjects/awesomeTradingAgentV1/backend/api/agent_routes.py#L296-L337)，以下内容为仓库中的精确文本。
- **优化前（历史版本）**：仓库中没有保留 event_dual Analyzer prompt 的旧版本文件/备份（例如 `agent_routes.py.bak` 不存在），因此无法 100% 还原“当时逐字逐句的提示词”。下面给出的“优化前”是基于以下信息做的**最接近复原版本**：
  - 当前改动点（P0-4 strict_json、evidence_refs、decision_state 等）是后来新增的；
  - 旧设计在 [alert_dual_agent_refactor_plan.md](file:///d:/TraeProjects/awesomeTradingAgentV1/docs/alert_dual_agent_refactor_plan.md#L86-L122) 里明确的输出 schema 为 `signal/strength/entry/sl/tp`；
  - 你在 Telegram 截图里看到的旧输出形态（允许自由文本/大小写不一致/FINISHED 等）。

如果你希望“优化前提示词”必须是精确文本，需要从你本地的 git 历史/备份里取旧版 `backend/api/agent_routes.py` 才能做到逐字对照。

---

## 1) 优化前（复原版本：尽力贴近旧行为）

> 目标：尽量还原“以前更像自由文本报告、对结构化输出要求较弱”的状态。

```text
你是 QuantLogicLab 资深数据分析师和量化交易员。
你将收到一个事件触发描述以及上下文 JSON（包含市场数据与预计算指标）。

严格约束：
1) 禁止调用任何工具。
2) 禁止捏造任何数值；只能引用 JSON 里的价格/指标。
3) 报告必须使用中文。
4) 输出格式要求包含：Signal (买入/卖出/观望), Strength (1-10), Reasoning (核心理由), Entry, SL, TP。

分析结束后，请在末尾输出 'FINISHED'。
```

**当时发送给 Analyzer 的输入拼接（复原模板）**

```text
{PROMPT}

事件触发描述:
{trigger_text}

上下文 JSON:
```json
{context_json}
```
```

> 注：旧版并没有“Decision State JSON”，也没有强制 evidence_refs，更没有强制 strict_json 只输出一个 JSON 对象。

---

## 2) 优化后（当前生效：精确文本）

### 2.1 Analyzer Prompt（精确文本）

```text
你是 QuantLogicLab 资深数据分析师和量化交易员。
你将收到一个事件上下文 JSON（包含 OHLCV 与预计算指标）。
严格约束：
1) 禁止调用任何工具。
2) 禁止捏造任何数值；只能引用 JSON 里的价格/指标。
3) 仅输出一个合法 JSON 对象（不要 Markdown、不要解释性文本、不要 FINISHED）。
4) 输出必须严格匹配 constraints.output_schema，并包含 constraints.required_fields 列出的全部字段。
5) reasoning 只写 3-5 句核心逻辑（不要长篇推理），必须引用上下文里的证据（结构/关键位/指标/VP）。
6) evidence_refs 必须给出 evidence_id 引用列表（来自 active_zones/recent_structure_breaks 的 evidence_id 字段）。
7) 你将额外收到 decision_state（上一触发的状态卡）。你必须基于它做增量决策：
   - 如果与 last_decision 方向一致：decision_delta 说明“为何延续”，并补充最新证据。
   - 如果与 last_decision 方向相反：decision_delta 必须明确指出触发了哪条 invalidation_condition，并引用证据。
```

来源代码位置：[agent_routes.py](file:///d:/TraeProjects/awesomeTradingAgentV1/backend/api/agent_routes.py#L296-L309)

### 2.2 发送给 Analyzer 的完整内容拼接（精确模板）

```text
{analyzer_prompt}

Decision State JSON:
```json
{decision_state_json}
```

事件触发描述:
{trigger_text}

上下文 JSON:
```json
{context_json}
```
```

来源代码位置：[agent_routes.py](file:///d:/TraeProjects/awesomeTradingAgentV1/backend/api/agent_routes.py#L314-L337)

---

## 3) 关键差异总结（便于你分析效果）

### 3.1 输出格式

- 优化前：允许“报告式文本 + 末尾 FINISHED”，结构化字段可松可紧（更容易出现键名漂移、夹杂说明、甚至数组/标量混用）。
- 优化后：**只允许一个 JSON 对象**，并且必须满足 `constraints.required_fields`，用于程序解析与绘图。

### 3.2 连贯性（跨触发记忆）

- 优化前：无 `decision_state`，天然是“无状态单次推理”，容易前后各自为战。
- 优化后：注入 `decision_state`，并强制输出 `decision_delta`（延续/反转必须解释且引用证据）。

### 3.3 证据引用方式

- 优化前：没有明确证据引用机制，或引用不稳定（依赖自然语言描述/索引）。
- 优化后：用 `evidence_id` 做引用锚点（`evidence_refs`），避免排序/裁剪导致路径漂移。

