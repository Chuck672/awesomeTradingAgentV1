"use client";

import React, { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";

type StrategyTemplateId = "price_action" | "volume_profile";

type SidebarConfig = {
  selectedTemplate: StrategyTemplateId;
  systemPrompt: string;
  userPrompt: string;
};

const KEY = "awesome_chart_sidebar_config_v1";

const TEMPLATES: Record<StrategyTemplateId, { name: string; systemPrompt: string; userPrompt: string }> = {
  price_action: {
    name: "价格行为（PA）",
    systemPrompt: `你是一位经验丰富、专业严谨的价格行为（Price Action）分析师，同时精通宏观经济数据解读和金融市场反应机制。

你的核心任务是：
1. 用户会先提供一个「数据 JSON Schema」，你必须先完整理解这个 Schema 的结构、字段含义、数据类型和业务逻辑。
2. 之后用户会提供符合该 Schema 的具体 JSON 数据（可能是单条记录、数组或多条历史数据）。
3. 你需要基于「价格行为」原则，对提供的数据进行合理、客观、数据驱动的分析。

【分析原则】（必须严格遵守）
- 始终以价格行为为核心：趋势、K线形态、支撑/阻力位、突破/回踩、成交量配合、波动率扩张/收缩、假突破、订单流逻辑等。
- 结合宏观经济事件（如财经日历数据）对价格的可能影响，包括事件重要性、预期差（Actual vs Forecast vs Previous）、历史市场反应模式。
- 保持客观中性：给出「最可能的情景」「次要情景」「极端情景」，并说明概率依据。
- 禁止给出「必涨/必跌」或绝对性结论，必须使用「大概率」「倾向于」「历史数据显示」等概率化语言。
- 禁止任何形式的投资建议或保证，只做客观分析。

【输出格式】（必须严格按照以下结构回复，使用 Markdown 格式，清晰美观）：

### 1. Schema 理解摘要
（简要总结用户提供的 JSON Schema 关键字段和业务含义，确认你已完全理解）

### 2. 数据概览
（用表格或 bullet points 简洁呈现关键数据点）

### 3. 价格行为核心分析
（这是重点部分）
- 当前/历史价格行为特征
- 关键支撑与阻力位判断
- 趋势强度与结构（Higher High / Lower Low 等）
- 事件对价格的潜在驱动逻辑（预期差、历史反应）
- 波动率预期与可能的 K 线形态

### 4. 情景推演（必须包含）
- 最可能情景（概率最高）
- 次要情景
- 极端情景（黑天鹅式）
每个情景请说明对应的价格行为特征和关键观察信号。

### 5. 风险提示与观察要点
（列出需要重点关注的后续价格信号）

### 6. 总结一句话
（一句话浓缩最核心的价格行为结论）

语言要求：
- 使用简洁、专业、通俗易懂的中文。
- 必要时可使用英文金融术语（括号内给出中文解释）。
- 语气专业且谨慎，体现深度思考。

现在请等待用户提供 JSON Schema 和数据后再开始分析，不要提前假设任何数据。`,
    userPrompt: "【可选补充】你可以在这里加入自己的执行偏好（例如：只做趋势/只做区间、确认条件、止损方式、目标方式、交易时段等）。",
  },
  volume_profile: {
    name: "Volume Profile",
    systemPrompt: ["你是一个以 Volume Profile / VWAP 为核心的量化交易分析师。", "你只允许基于输入字段分析，不允许编造未提供数据。", "当 VP 字段缺失时，必须返回：action=PASS，并列出 needs 字段。"].join("\n"),
    userPrompt: ["【适用场景】基于 VP/VWAP/关键位 做短线。", "【输出】强调关键价位与执行条件，尽量短。"].join("\n"),
  },
};

function defaultCfg(): SidebarConfig {
  return {
    selectedTemplate: "price_action",
    systemPrompt: TEMPLATES.price_action.systemPrompt,
    userPrompt: TEMPLATES.price_action.userPrompt,
  };
}

function loadCfg(): SidebarConfig {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return defaultCfg();
    const parsed = JSON.parse(raw);
    const d = defaultCfg();
    return { ...d, ...parsed };
  } catch {
    return defaultCfg();
  }
}

function saveCfg(cfg: SidebarConfig) {
  localStorage.setItem(KEY, JSON.stringify(cfg));
}

export function ChatStrategyPanel() {
  const [cfg, setCfg] = useState<SidebarConfig>(() => loadCfg());

  const templateName = useMemo(() => TEMPLATES[cfg.selectedTemplate].name, [cfg]);

  return (
    <div className="h-full flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <div className="text-xs text-gray-400">Chat / Strategy</div>
        <Button
          className="h-7 px-2 text-xs"
          onClick={() => {
            saveCfg(cfg);
          }}
        >
          保存
        </Button>
      </div>

      <div className="text-sm font-semibold">模板：{templateName}</div>

      <div className="flex gap-2">
        {(["price_action", "volume_profile"] as StrategyTemplateId[]).map((id) => (
          <button
            key={id}
            className={`text-xs px-2 py-1 rounded border ${
              cfg.selectedTemplate === id ? "border-emerald-400 text-emerald-300" : "border-white/10 text-gray-300"
            }`}
            onClick={() => {
              const t = TEMPLATES[id];
              setCfg({ selectedTemplate: id, systemPrompt: t.systemPrompt, userPrompt: t.userPrompt });
            }}
          >
            {TEMPLATES[id].name}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-auto space-y-3 pr-1">
        <div className="space-y-1">
          <div className="text-xs text-gray-400">System Prompt</div>
          <textarea
            className="w-full min-h-[220px] text-xs rounded border border-white/10 bg-black/20 p-2 outline-none focus:border-emerald-400"
            value={cfg.systemPrompt}
            onChange={(e) => setCfg({ ...cfg, systemPrompt: e.target.value })}
          />
        </div>
        <div className="space-y-1">
          <div className="text-xs text-gray-400">User Prompt</div>
          <textarea
            className="w-full min-h-[120px] text-xs rounded border border-white/10 bg-black/20 p-2 outline-none focus:border-emerald-400"
            value={cfg.userPrompt}
            onChange={(e) => setCfg({ ...cfg, userPrompt: e.target.value })}
          />
        </div>
        <div className="text-[11px] text-gray-500">
          说明：这里先迁移“策略模板/Prompt 管理”能力。下一步会把 scene_summary（paths/next_actions/evidence）一键拼接到 prompt 输入中。
        </div>
      </div>
    </div>
  );
}
