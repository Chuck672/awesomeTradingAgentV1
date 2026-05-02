# AwesomeTradingAgent（AwesomeChartV3）

一个面向日内/剥头皮交易的桌面端图表与事件驱动 AI 分析系统：后端负责行情接入、指标/结构/形态计算与告警触发；前端基于 Lightweight Charts 做高性能绘图与指标插件；当触发事件出现时，系统会生成结构化上下文，调用 LLM 输出“可落图、可执行的未来入场预判”（等待区、确认线、失效线、目标位），并同步到图表与 Telegram。

当前开发主线围绕 [trigger_event_playbooks.md](docs/trigger_event_playbooks.md) 的“触发器路由”实现：不同 trigger 只允许使用各自白名单 playbook，避免模型因为 `regime=range/trend` 等叙事导致跑偏。

## 版本与仓库

- 分支策略：日常开发默认基于 `main`
- Release：推送形如 `v*` 的 tag 会触发 GitHub Actions 构建 Windows `zip/exe`（见 [.github/workflows/build-electron.yml](.github/workflows/build-electron.yml)）

## 核心能力

- 行情与数据
  - MT5 数据源（Windows 环境可用，见 [mt5_source.py](backend/data_sources/mt5_source.py)）
  - 历史数据缓存与回放（见 [historical.py](backend/services/historical.py)、[replay.py](backend/services/replay.py)）
- 事件驱动 AI（Alert → Workflow）
  - 告警评估循环：[alerts_engine.py](backend/services/alerts_engine.py)
  - 双代理事件工作流（Analyzer → 落图/通知）：[alert_dual_agent_workflow.py](backend/services/workflows/alert_dual_agent_workflow.py)
  - 结构化上下文构建：[event_context_builder.py](backend/services/ai/event_context_builder.py)
- 图表与可视化
  - Next.js + Electron UI（见 [frontend](frontend/)）
  - Lightweight Charts 绘图协议：后端发 `draw_objects`，前端接收 `chart_draw/draw_objects`（见 [drawing_tools.py](backend/services/tools/drawing_tools.py)、[chart.tsx](frontend/src/components/chart.tsx)）
  - 指标插件：RajaSR / MSB_ZigZag / TrendExhaustion / VolumeProfile 等（见 [frontend/src/plugins](frontend/src/plugins)）

## 目录结构（重点）

- backend/
  - main.py：FastAPI 入口，启动 message bus、MT5、ingestion、alerts_engine 循环（见 [backend/main.py](backend/main.py)）
  - services/
    - alerts_engine.py：告警触发与 workflow 调度（见 [alerts_engine.py](backend/services/alerts_engine.py)）
    - workflows/alert_dual_agent_workflow.py：事件分析与落图执行（见 [alert_dual_agent_workflow.py](backend/services/workflows/alert_dual_agent_workflow.py)）
    - ai/event_context_builder.py：将结构/指标/形态裁剪为 LLM 可用上下文（见 [event_context_builder.py](backend/services/ai/event_context_builder.py)）
    - ai/llm_factory.py：LLM 初始化与密钥加载（见 [llm_factory.py](backend/services/ai/llm_factory.py)）
    - tools/drawing_tools.py：绘图命令接口（见 [drawing_tools.py](backend/services/tools/drawing_tools.py)）
  - domain/market/
    - structure/：RajaSR、MSB、swing/structure 工具
    - patterns/：false_breakout、liquidity_sweep、rectangle_range 等
    - indicators/：Trend Exhaustion、TA（ATR/RSI 等）
- frontend/
  - src/components/chart.tsx：图表实例管理、接收后端绘图动作并落到图上（见 [chart.tsx](frontend/src/components/chart.tsx)）
  - src/components/single-chart.tsx：单图表渲染与指标挂载（见 [single-chart.tsx](frontend/src/components/single-chart.tsx)）
  - src/plugins/：指标插件（RajaSR、MSB_ZigZag、TrendExhaustion…）
- docs/
  - trigger_event_playbooks.md：触发器主线与 playbook 字典（见 [trigger_event_playbooks.md](docs/trigger_event_playbooks.md)）
  - analyzer_system_prompt.md / agent_prompts.md：提示词与输出约束

## 运行与开发（本地）

### 1) 后端（FastAPI）

依赖：Python 3.10+（建议），安装：

```bash
pip install -r requirements.txt
```

启动（开发模式支持 reload）：

```bash
python run_backend.py
```

- 默认端口：`8123`（见 [run_backend.py](run_backend.py)）
- FastAPI 入口：`backend.main:app`

### 2) 前端（Next.js）

```bash
cd frontend
npm ci
npm run dev
```

- Next dev 默认端口：`3123`（见 [frontend/package.json](frontend/package.json)）

### 3) Electron（桌面端）

生产构建由 GitHub Actions 完成（tag 触发）。本地也可构建：

```bash
cd frontend
npm run dist
```

## 配置与密钥

### LLM（SiliconFlow/OpenAI 兼容）

- 配置文件：`siliconflow_api.env`（根目录）
- 读取位置：`backend/services/ai/llm_factory.py` 会 `load_dotenv(siliconflow_api.env)`（见 [llm_factory.py](backend/services/ai/llm_factory.py)）
- 关键字段：
  - `Base_URL`
  - `Model`
  - `API_Key`

注意：不要把真实密钥提交到仓库。

### 数据目录（应用数据与 SQLite）

- 默认位置由 OS 决定（Windows：`%APPDATA%/AwesomeTradingAgent/data`）
- 可用环境变量覆盖：`AWESOMECHART_DATA_DIR`
- 实现：见 [app_config.py](backend/database/app_config.py)

### Telegram

Telegram 配置来自“告警规则”里的 `telegram` 字段（不是全局配置）：

- 读取位置：`backend/services/alerts_engine.py`（见 [alerts_engine.py](backend/services/alerts_engine.py)）
- 字段：`telegram.token`、`telegram.chat_id`
- 发送实现：见 [telegram.py](backend/services/telegram.py)

## 关键数据流（从触发到落图）

1. `alerts_engine.loop()` 周期性调用 `eval_once()`（见 [alerts_engine.py](backend/services/alerts_engine.py)）
2. 匹配到规则后，进入对应 trigger 评估（如 `raja_sr_touch` / `msb_zigzag_break` / `trend_exhaustion` / `consolidation_rectangle_breakout`）
3. 生成 `trigger_text` + `trigger_payload(best_event)` 并调度：
   - `AlertDualAgentWorkflow.run(...)`（见 [alert_dual_agent_workflow.py](backend/services/workflows/alert_dual_agent_workflow.py)）
4. workflow 构建 event context：
   - `build_event_context(..., trigger_payload=...)`（见 [event_context_builder.py](backend/services/ai/event_context_builder.py)）
5. Analyzer LLM 通过 Structured Output 产出 `AnalyzerPlan`（包含 playbook/status/entry_zone/confirm/invalidate/targets 等）
6. workflow 校验输出是否符合 trigger 的白名单策略，不合规则降级 `no_trade`（仍保留 targets 虚线）
7. 发送绘图对象：
   - 后端：`draw_clear_ai` + `draw_objects(objects)`（见 [drawing_tools.py](backend/services/tools/drawing_tools.py)）
   - 前端：`chart_draw/draw_objects` → `chartRefs.drawObjects`（见 [chart.tsx](frontend/src/components/chart.tsx)）

## Trigger 类型（当前实现）

触发器路由与语义以 docs 为准（见 [trigger_event_playbooks.md](docs/trigger_event_playbooks.md)），代码侧目前包含：

- `raja_sr_touch`：RajaSR level-zone 触发（会产出 trigger_zone 锚点）
- `msb_zigzag_break`：BoS/ChoCh（结构提示器）
- `trend_exhaustion`：TE 反转提示（携带 te_id/box_high/box_low）
- `consolidation_rectangle_breakout`：震荡矩形充分触碰后的 breakout（携带 rect_id）
- `detector_trigger`：通用 detector trigger（用于实验/扩展）

## Playbook（统一字典）

Playbook 语义详见 [trigger_event_playbooks.md](docs/trigger_event_playbooks.md#playbook-字典统一语言)。核心目标是把输出限制为“可落图的原子规则”：

- `trend_pullback_limit`
- `trend_break_retest`
- `range_breakout_confirmed`
- `exhaustion_confirmed_reversal`
- `no_trade`

## 测试

后端单元测试：

```bash
python -m unittest discover -s backend/tests -p 'test_*.py'
```

## 常见问题

### 1) 为什么会出现 no_trade？

系统会对 LLM 输出做强校验：如果 playbook 不在 trigger 白名单、锚点不匹配、或者规则不可落图（例如 `retest_ok` 这类抽象规则），会直接降级为 `no_trade`，并保留 targets 虚线作为参考（见 [alert_dual_agent_workflow.py](backend/services/workflows/alert_dual_agent_workflow.py)）。

### 2) 为什么图上看起来“没画”？

前端绘图依赖历史 K 线加载与时间对齐。若对象时间在未来或历史数据不足，可能需要先补齐历史或调整视图范围（见 [chart.tsx](frontend/src/components/chart.tsx)、[single-chart.tsx](frontend/src/components/single-chart.tsx)）。
