 一、当前 build_agent_context 提取逻辑分析
✅ 亮点（做得好的地方）
大幅砍掉冗余 OHLCV：将数百根 K 线压缩为 recent_bars（3根），直接降低 80%+ Token 消耗，符合 LLM “只看最近上下文” 的特性。
保留多周期对齐：H1 定方向，M15 找入场，结构清晰，符合主流 MTF 交易逻辑。
关键指标完整：basic_indicators + advanced_indicators 覆盖了趋势、动量、波动率、量价分布（VolumeProfile）和结构突破，信息密度高。
⚠️ 致命问题与潜在风险
问题点
LLM 影响
交易逻辑影响
1. recent_bars 仅保留 3 根
无法识别基础 Price Action（如吞没、Pin Bar、放量突破/衰竭），AI 只能看指标数值，失去“盘面感觉”。
3根 H1 = 3小时，3根 M15 = 45分钟。错过近期波动扩张/收缩、假突破、流动性扫荡等关键微观结构。
2. 丢弃了 raja_sr_zones 和 msb_zigzag
原 JSON 中最具 Alpha 的自定义区域/结构线被完全过滤，AI 只能依赖单一 Nearest_R/S，决策依据变薄。
市场交易的是“区域带”而非单一点。仅保留最近 1 个阻力/支撑，AI 无法评估上方抛压/下方承接的叠加效应。
3. Nearest_Resistance/Support 字段过度膨胀
包含 from_time, to_time, avg_wick_excess 等对 AI 决策无直接帮助的字段，占用 Token 且分散注意力。
LLM 只需要：价格区间、强度评分、距离当前价多远、最近触碰时间。
4. 缺乏市场状态与风控上下文
AI 不知道当前是亚盘/欧盘/美盘，点差多少，数据是否延迟，容易在流动性枯竭或新闻发布前给出错误信号。
黄金在伦敦开盘和美盘重叠期波动率差异极大，缺少 vol_regime 和 session 会导致 SL/TP 设置脱离实际。
5. constraints.output_schema 未升级
仍为松散结构，AI 容易输出格式不一致、缺少失效条件、不计算盈亏比。
无法直接对接执行模块，需二次解析，增加系统延迟和出错率。
🛠 二、基于 Compact 的 v2 优化方案
📐 v2 核心设计原则
动态上下文窗口：固定保留 10~15 根 K 线（覆盖最近 2.5~4 小时），平衡 Token 与形态识别。
智能过滤 + 字段扁平化：S/R 区域仅保留 距离 < 2.0 * ATR 且 score > 60 的前 3 个；剔除时间戳细节，改为 age_candles。
注入交易元数据：补充 session, spread, vol_regime, data_quality。
强制结构化输出：输出 Schema 增加 invalidation, rr_ratio, confidence, reasoning_chain。
📦 优化后 JSON Schema 示例（可直接替换）
{
  "meta": {
    "snapshot_unix": 1777124721,
    "symbol": "XAUUSDz",
    "exec_tf": "M15",
    "trend_tf": "H1",
    "market_state": {
      "session": "London_AM",
      "spread_pts": 1.2,
      "vol_regime": "expanding",
      "data_fresh": true
    },
    "risk_context": {
      "balance_usd": 10000,
      "risk_pct": 1.0,
      "max_slippage_pts": 3.0
    }
  },
  "context": {
    "H1": {
      "price_now": 4724.62,
      "recent_bars": [
        {"t": 1777039200, "o": 4711.68, "h": 4740.39, "l": 4706.93, "c": 4726.51, "vol": 24372},
        {"t": 1777042800, "o": 4726.57, "h": 4733.47, "l": 4714.58, "c": 4727.11, "vol": 20439},
        {"t": 1777046400, "o": 4727.03, "h": 4729.81, "l": 4719.05, "c": 4724.62, "vol": 11169}
      ],
      "indicators": {
        "SMA_20": 4695.54, "EMA_20": 4704.27, "ATR_14": 20.42,
        "RSI_14": 67.7, "MACD": {"macd": 2.26, "signal": -3.98, "hist": 6.24}
      },
      "structure": {
        "bias": "HH_HL",
        "swing_range": {"high": 4740.39, "low": 4706.93},
        "breaks": [{"type": "ChoCh_Bull", "level": 4711.22, "age_candles": 3}]
      },
      "active_zones": [
        {"level": [4708.26, 4709.23], "type": "support", "strength": 95, "dist_pts": 15.4, "last_touch_age": 2},
        {"level": [4728.71, 4729.68], "type": "resistance", "strength": 94, "dist_pts": 4.1, "last_touch_age": 1}
      ]
    },
    "M15": {
      "price_now": 4724.73,
      "recent_bars": [
        {"t": 1777047300, "o": 4720.67, "h": 4725.92, "l": 4719.05, "c": 4723.38, "vol": 2779},
        {"t": 1777048200, "o": 4723.44, "h": 4727.28, "l": 4719.16, "c": 4722.48, "vol": 3033},
        {"t": 1777049100, "o": 4722.54, "h": 4724.73, "l": 4720.41, "c": 4724.73, "vol": 1511}
      ],
      "indicators": {
        "SMA_20": 4717.18, "EMA_20": 4716.90, "ATR_14": 11.84,
        "RSI_14": 68.7, "MACD": {"macd": 7.78, "signal": 8.43, "hist": -0.65}
      },
      "structure": {
        "bias": "Consolidation",
        "swing_range": {"high": 4733.47, "low": 4714.58},
        "breaks": [{"type": "BoS_Bull", "level": 4717.52, "age_candles": 2}]
      },
      "active_zones": [
        {"level": [4711.18, 4711.68], "type": "support", "strength": 47, "dist_pts": 13.1, "last_touch_age": 4},
        {"level": [4726.46, 4726.96], "type": "support", "strength": 84, "dist_pts": -1.8, "last_touch_age": 1},
        {"level": [4731.25, 4731.75], "type": "resistance", "strength": 63, "dist_pts": 6.5, "last_touch_age": 3}
      ]
    }
  },
  "constraints": {
    "output_schema": {
      "signal": {"type": "string", "enum": ["buy", "sell", "hold"]},
      "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
      "entry": {"price": "number", "type": "enum:market|limit"},
      "sl": "number",
      "tp": ["number"],
      "risk_reward_ratio": "number",
      "invalidation_condition": "string (e.g., 'H1 close below 4708.26 invalidates bias')",
      "trade_horizon": "enum:scalp|intraday|swing",
      "reasoning_chain": "string (3-5 sentences: MTF alignment -> structure -> indicator confluence -> risk)"
    }
  }
}

 v2 核心改进点说明
模块
优化动作
收益
recent_bars
从 3 根 → 10 根（代码中可写死或按 max(10, ATR_period)）
恢复 Price Action 识别能力，AI 可判断 K 线形态、成交量异动、假突破。
active_zones
合并原 Nearest_R/S + raja_sr_zones，过滤 score<60 或 dist>2*ATR，仅留 Top 3
去除历史无效位，聚焦当前价格正在交互的流动性区域，决策更精准。
字段精简
time → t, delta_volume 移除, source 移除, 价格保留 2 位小数
Token 减少 25%~35%，JSON 解析速度提升，LLM 注意力更集中。
元数据注入
新增 market_state (session, spread, vol_regime) 和 risk_context
让 AI 具备“交易员常识”，避免在点差扩大或低波动期给出过度交易的信号。
输出约束
强制 invalidation_condition, risk_reward_ratio, reasoning_chain
形成 分析 → 决策 → 风控 → 失效预案 闭环，直接可对接 Order Manager。

Prompt 配合指令：
“你是一名量化交易主管。请严格基于 context 中的多周期结构、活跃区域带、量价与指标进行推演。若 H1 与 M15 信号冲突，或价格处于无结构震荡区，请输出 hold。必须提供明确的失效条件，禁止使用模糊词汇（如‘可能’、‘大概’）