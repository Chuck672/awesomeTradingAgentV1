产品需求说明书（更新版）
产品名称：AI驱动的Lightweight Charts智能交易系统
核心目标
让AI真正控制图表，实现基于自定义指标的策略自我回测，支持多Agent协同决策，并将交易信号实时呈现在图表上。
1. 系统架构（更新为 1+2 结构）

1个强势主Agent（Supervisor）：负责全局统筹、判断下一步动作，是整个系统的大脑。
2个子Agent：
分析Agent：合并技术分析 + 策略决策
执行Agent：合并风险控制 + 图表绘制 + 执行订单


主Agent价值：判断当前最需要做什么、在分析与执行之间做仲裁、保持整体决策连贯性。
2. 主Agent工作流程图
用户触发决策
      ↓
主Agent启动（输入：最新JSON数据 + 历史记忆 + 当前状态）
      ↓
主Agent判断下一步动作
      ├─→ next = "analyze" → 分析Agent执行 → 结果写回SQLite → 返回主Agent
      ├─→ next = "execute" → 执行Agent执行（风控+画图+下单）→ 结果写回SQLite → 返回主Agent
      └─→ next = "finish"  → 本次决策结束
      ↓
循环回到主Agent继续判断，直到输出 "finish"

3. 数据流与输入

数据源：SQLite本地数据库 + 实时数据接口。
给AI的数据格式：结构化JSON（包含当前价格、最近30根K线、预计算指标、关键支撑阻力位）。
所有指标计算在代码层完成，AI只负责解读和决策。

4. 策略设计原则
采用规则框架 + AI自由发挥模式：

必须固定的框架：最大单笔风险≤2%、每日最多3次交易、必须设止损止盈。
AI可自由发挥：如何解读自定义指标、具体进场时机和价位。

5. Tool Calling设计（权限最小化）

分析Agent：只允许调用数据查询和指标相关Tool
执行Agent：只允许调用风控计算、图表绘制、下单相关Tool
主Agent：不分配任何Tool，仅负责思考和调度

6. Agent记忆与状态管理

每次决策都存入agent_memory表。
新增agent_status表用于实时状态同步（主Agent、分析Agent、执行Agent的状态及消息）。

7. 前后端通信与实时显示

多Agent运行在后台任务中，避免API超时。
前端（React + TypeScript）每1.5秒轮询agent_status表：
主Agent工作时主灯变绿
分析Agent或执行Agent工作时对应灯变绿
流式消息实时显示在图表旁边的对话框中


8. 技术栈要点

图表：Lightweight Charts
多Agent框架：LangGraph
后端：Node.js
前端：React + TypeScript
数据库：SQLite
模型选择：主Agent使用较强模型，两个子Agent使用轻量快速模型