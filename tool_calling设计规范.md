这份规范旨在为 QuantLogicLab 的图表系统提供一套工业级的 AI 插件接入标准，确保大模型（如 Qwen 系列）能够精准、稳定地操控 lightweight-charts。QuantLogicLab 图表 AI 插件 Tool Calling 
设计规范1. 核心设计原则语义化原子操作：工具名称必须反映交易员的操作意图，而非底层的代码命令。强类型约束：所有参数使用 JSON Schema 严格定义，尽可能使用 enum 减少 AI 的随机发挥。
状态闭环：AI 发起指令前必须感知图表当前状态（符号、周期、现有指标），指令执行后必须获得执行结果反馈。
2. 语义化工具集定义我们将工具集分为四个维度：视图控制、指标管理、绘图分析、交易辅助。
2.1 视图控制 (View Control)用于调整图表的基础展示参数。工具名称参数说明switch_market_contextsymbol (string), timeframe (enum: M1, M5, H1...)切换品种和K线周期。focus_on_time_rangestart_time (string/ISO), end_time (string/ISO)自动缩放图表至特定时间段（用于复盘）。reset_chart_view无恢复默认缩放和价格居中。
2.2 指标管理 (Indicator Management)针对 QuantLogicLab 核心工具（如 SVP, Trend Panel）的深度集成。工具名称参数说明add_technical_indicatortype (enum: SVP, EMA, RSI, RajaSR, MSB_zigzag等等所有指标), params (object)动态添加指标。update_indicator_configindicator_id (string), new_params (object)修改现有指标设置（如将 20 均线改为 50 均线）。toggle_indicator_visibilityindicator_id (string), visible (boolean)快速隐藏或显示特定工具。
2.3 绘图分析 (Drawing & Analysis)将 AI 的逻辑分析转化为视觉化的图表元素。工具名称参数说明draw_price_levelprice (number), label (string), style (enum: support, resistance)在特定价格画水平射线，并标注语义（如“机构订单块”）。mark_chart_areastart_t, end_t, top_p, bottom_p, color使用矩形框标记区域（常用于标记 FVG 缺口或震荡区间）。add_text_annotationtime, price, content在特定坐标添加分析注释。
2.4 交易辅助 (Trading Execution)联动 Scalp Trading Panel 的执行能力。工具名称参数说明prepare_trade_planside (enum: buy, sell), entry, sl, tp在图表上绘制虚拟成交计划线，但不直接下单。modify_position_visualorder_id (string), new_sl (number)通过在图表上拖动或 AI 指令调整止损位。3. 提高稳定性与准确性的设计技巧3.1 状态注入 (Context Injection) —— 解决 AI 幻觉技巧：在用户发送 Prompt 前，自动在系统消息中附加“图表快照”。不合理做法：让 AI 盲猜当前图表。设计规范：JSON{
  "current_chart": {
    "symbol": "BTCUSDT",
    "timeframe": "M15",
    "indicators": [{"id": "ema_20", "type": "EMA", "value": 65000}],
    "visible_price_range": {"high": 66000, "low": 64000}
  }
}
这能确保 AI 提出的 price 参数在当前视图范围内。
3.2 坐标转换屏蔽 —— 解决时效性偏移技巧：禁止 AI 使用像素坐标，强制使用逻辑坐标（时间戳 + 价格）。设计规范：时间参数统一使用 Unix Timestamp (Seconds) 或 ISO 8601。在 lightweight-charts 中，时间轴是唯一的锚点。AI 识别“昨晚 8 点的起涨点”时，后端需先将其转换为确切时间戳再传给 Tool。
3.3 指令确认模式 (Two-Step Verification)技巧：对于涉及绘图或指标删除的操作，采用“预执行”反馈。AI 返回 tool_call。前端 UI 显示一个淡色的预览层。用户点击确认或 AI 自动确认，正式调用 chart.addSeries()。3.4 错误追溯反馈 (Error Propagation)技巧：当 AI 传入非法参数（如在 M15 图表请求显示 M1 的数据）时，将前端抛出的异常原样返回给 AI。返回示例：{"status": "error", "message": "Indicator SVP cannot be rendered: Timeframe M1 data is missing for the requested range."}。效果：AI 会根据此反馈自动向用户解释原因，或修正参数重试。4. 针对 QuantLogicLab 的特殊优化建议SVP 专有参数优化：在 add_technical_indicator 的参数中，针对你的 SVP v5 工具，增加 purity_filter（纯度过滤）和 efficiency_factor（效率因子）的枚举，让 AI 能够根据波动率自动调整指标灵敏度。多图表联动：如果用户打开了多个窗口，Tool 参数需增加 chart_id，防止 AI 操控了错误的窗口。时效性校验：在 System Prompt 中加入当前服务器时间（Server Time），防止 AI 使用过时的历史数据来分析当前的实时 Tick 走势。5. 示例 JSON 定义 (以添加水平线为例)JSON{
  "name": "draw_price_level",
  "description": "在图表上绘制关键价格水平线（支撑/阻力/机构关口）",
  "parameters": {
    "type": "object",
    "properties": {
      "price": {
        "type": "number",
        "description": "价格数值，必须在当前品种的价格精度范围内"
      },
      "label": {
        "type": "string",
        "description": "显示在价格轴上的标签文本，例如 'Daily POC'"
      },
      "line_style": {
        "type": "string",
        "enum": ["solid", "dashed", "dotted"]
      },
      "color": {
        "type": "string",
        "description": "十六进制颜色代码，建议根据指标性质选择红/绿"
      }
    },
    "required": ["price", "label"]
  }
}
通过这套规范，AI Agent 将不再只是一个“聊天机器人”，而是真正成为你 QuantLogicLab 交易台的“副驾驶（Copilot）”。