"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Settings, X } from "lucide-react";
import { getBaseUrl } from "@/lib/api";

type AiSettings = {
  base_url: string;
  model: string;
  api_key: string;
};

type ChartState = {
  symbol?: string;
  timeframe?: string;
  enabled?: { 
    svp?: boolean; 
    vrvp?: boolean; 
    bubble?: boolean;
    RajaSR?: boolean;
    RSI?: boolean;
    MACD?: boolean;
    EMA?: boolean;
    BB?: boolean;
    VWAP?: boolean;
    ATR?: boolean;
    Zigzag?: boolean;
  };
};

type AiAction = { type: string; [k: string]: any };

const KEY = "awesome_chart_ai_settings_v1";

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

function tryParseJson(s: any): any {
  if (!s || typeof s !== "string") return null;
  try {
    return JSON.parse(s);
  } catch {
    return null;
  }
}

function toMarkdownTable(headers: string[], rows: string[][]): string {
  const esc = (x: any) => String(x ?? "").replace(/\|/g, "\\|");
  const head = `| ${headers.map(esc).join(" | ")} |`;
  const sep = `| ${headers.map(() => "---").join(" | ")} |`;
  const body = rows.map((r) => `| ${r.map(esc).join(" | ")} |`).join("\n");
  return [head, sep, body].filter(Boolean).join("\n");
}

function formatChartDrawArgs(args: any): string {
  const objs: any[] = Array.isArray(args?.objects) ? args.objects : [];
  if (!objs.length) return "（无绘图对象）";
  const rows = objs.slice(0, 20).map((o) => {
    const type = o?.type ?? "";
    const price = o?.price ?? "";
    const timeRange =
      type === "box"
        ? `${o?.from_time ?? ""} ~ ${o?.to_time ?? ""}`
        : o?.time
          ? String(o.time)
          : o?.t1 && o?.t2
            ? `${o.t1} ~ ${o.t2}`
            : "";
    const text = o?.text ?? "";
    const color = o?.color ?? "";
    return [String(type), String(price), String(timeRange), String(text), String(color)];
  });
  return (
    "绘图参数：\n" +
    toMarkdownTable(["类型", "价格", "时间/区间", "文本", "颜色"], rows)
  );
}

function summarizeToolCallsForUser(toolCalls: any[]): string {
  if (!Array.isArray(toolCalls) || !toolCalls.length) return "";
  // 只对用户有感知的动作做摘要（目前主要是 chart_draw）
  const parts: string[] = [];
  for (const tc of toolCalls) {
    const fn = tc?.function || {};
    const name = fn?.name;
    const args = tryParseJson(fn?.arguments);
    if (name === "chart_draw" && args) {
      const objs: any[] = Array.isArray(args?.objects) ? args.objects : [];
      const labels = objs
        .map((o) => o?.text)
        .filter(Boolean)
        .slice(0, 5);
      const labelText = labels.length ? `（${labels.join("，")}）` : "";
      parts.push(`已在图上绘制 ${objs.length} 个对象${labelText}。`);
      parts.push(formatChartDrawArgs(args));
    }
  }
  return parts.join("\n");
}

function defaultSettings(): AiSettings {
  return {
    base_url: "https://api.openai.com",
    model: "gpt-4o-mini",
    api_key: "",
  };
}

function loadSettings(): AiSettings {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return defaultSettings();
    const parsed = JSON.parse(raw);
    return { ...defaultSettings(), ...(parsed || {}) };
  } catch {
    return defaultSettings();
  }
}

function saveSettings(s: AiSettings) {
  localStorage.setItem(KEY, JSON.stringify(s));
}

async function fetchJsonWithTimeout(url: string, init: RequestInit, timeoutMs: number, retry: number = 1): Promise<any> {
  const attempt = async (): Promise<any> => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const r = await fetch(url, { ...init, signal: controller.signal });
      const data = await r.json().catch(() => ({}));
      // 后端一般用 {ok:false, detail:"..."}，也可能直接抛 HTTPException -> {detail:"..."}
      if (!r.ok) {
        const msg = data?.detail || `HTTP ${r.status}`;
        const err: any = new Error(msg);
        err._status = r.status;
        throw err;
      }
      return data;
    } finally {
      clearTimeout(timer);
    }
  };

  try {
    return await attempt();
  } catch (e: any) {
    const status = e?._status;
    const retriable = status === 502 || status === 503 || status === 504 || e?.name === "AbortError";
    if (retry > 0 && retriable) {
      await new Promise((r) => setTimeout(r, 600));
      return fetchJsonWithTimeout(url, init, timeoutMs, retry - 1);
    }
    if (e?.name === "AbortError") throw new Error("请求超时，请稍后重试");
    throw e;
  }
}

function redactKey(k: string) {
  if (!k) return "";
  if (k.length <= 8) return "********";
  return k.slice(0, 4) + "********" + k.slice(-4);
}

export function AiAssistantPanel(props: {
  chartState: ChartState;
  onExecuteActions: (actions: AiAction[]) => Promise<string[]> | string[];
  selectionRange?: { from: number; to: number } | null;
  selectionMode?: boolean;
  onStartSelection?: () => void;
  onClearSelection?: () => void;
  onPickVisibleRange?: () => void;
  onPickSelectedRectangle?: () => void;
  onRequestScreenshot?: () => Promise<string | null> | (string | null);
}) {
  const {
    chartState,
    onExecuteActions,
    selectionRange = null,
    selectionMode = false,
    onStartSelection,
    onClearSelection,
    onPickVisibleRange,
    onPickSelectedRectangle,
    onRequestScreenshot,
  } = props;
  const [settings, setSettings] = useState<AiSettings | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [showDebug, setShowDebug] = useState(false);
  const [running, setRunning] = useState(false);
  const [phaseHint, setPhaseHint] = useState<string>("");
  const [err, setErr] = useState<string | null>(null);
  const [input, setInput] = useState("");
  type ChatMsg = { id: string; role: "user" | "assistant" | "system"; content: string };
  const [messages, setMessages] = useState<ChatMsg[]>([
    {
      id: "sys_0",
      role: "system",
      content: "你可以直接描述你想要的策略规则，例如：'当价格突破20周期均线时做多'，我会自动为你生成相应的代码和工具调用。",
    },
  ]);
  // 预留：后续如果要把标注的“解释文本”也存起来，可以复用这里
  const [lastSelectionExplain] = useState<string>("");
  const scrollRef = useRef<HTMLDivElement>(null);

  const apiUrl = useMemo(() => {
    // 默认用相对路径（Next rewrite），但 explain/annotate 可能很慢，Next 会先 504。
    // 如果前端运行在 :3000（无论 hostname 是 localhost / 0.0.0.0 / 局域网 IP），则直连 :8000 后端，绕过 Next proxy timeout。
    const base = getBaseUrl();
    if (base) return (p: string) => `${base}${p}`;
    if (typeof window !== "undefined") {
      const host = window.location.hostname;
      const port = window.location.port;
      // 本地/局域网自托管（有端口号）时直连后端 :8000，避免 Next 的 /api proxy 504
      if (port && window.location.protocol !== "file:") {
        // 0.0.0.0 在浏览器里不是可访问目标，改成 127.0.0.1；否则用当前 host（支持局域网访问）
        const backendHost = host === "0.0.0.0" ? "127.0.0.1" : host;
        return (p: string) => `http://${backendHost}:8000${p}`;
      }
    }
    return (p: string) => p;
  }, []);

  useEffect(() => {
    setSettings(loadSettings());
  }, []);

  useEffect(() => {
    // 自动滚动到底部
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [messages, running]);

  const pushMsg = (role: ChatMsg["role"], content: string) => {
    const id = `${role}_${Date.now()}_${Math.random().toString(16).slice(2)}`;
    setMessages((m) => [...m, { id, role, content }]);
  };

  const summarizeActionsForUser = (actions: AiAction[]): string => {
    if (!Array.isArray(actions) || actions.length === 0) return "";
    const lines: string[] = [];
    for (const a of actions) {
      if (!a || typeof a !== "object") continue;
      if (a.type === "chart_set_timeframe" && a.timeframe) lines.push(`已切换周期到 ${a.timeframe}。`);
      else if (a.type === "chart_set_symbol" && a.symbol) lines.push(`已切换品种到 ${a.symbol}。`);
      else if (a.type === "chart_toggle_indicator" && a.id != null) lines.push(`已${a.enabled ? "打开" : "关闭"}指标：${a.id}。`);
      else if (a.type === "chart_set_range") lines.push(`已调整回看范围。`);
      else if (a.type === "chart_replay_from_range") lines.push(`已进入回放模式。`);
      else if (a.type === "chart_clear_drawings") lines.push("已清除绘图。");
    }
    // 去重并控制长度
    return Array.from(new Set(lines)).slice(0, 4).join("\n");
  };

  const canSend = useMemo(() => {
    if (!settings) return false;
    if (!input.trim()) return false;
    return true;
  }, [settings, input]);

  const send = async () => {
    if (!settings) return;
    const text = input.trim();
    if (!text) return;

    setErr(null);
    setRunning(true);
    setPhaseHint("请求中…");
    setInput("");
    pushMsg("user", text);

    try {
      const assistantId = `a_${Date.now()}_${Math.random().toString(16).slice(2)}`;
      setMessages((m) => [...m, { id: assistantId, role: "assistant", content: "" }]);

      const updateAssistant = (append: string) => {
        if (!append) return;
        setMessages((m) => m.map((x) => (x.id === assistantId ? { ...x, content: (x.content || "") + append } : x)));
      };
      const setAssistant = (content: string) => {
        setMessages((m) => m.map((x) => (x.id === assistantId ? { ...x, content } : x)));
      };

      // 取消流式：统一走非流式接口，减少不确定性与等待时间
      const data = await fetchJsonWithTimeout(
        apiUrl("/api/ai/chat"),
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ input: text, settings, chart_state: chartState || {} }),
        },
        120_000,
        1
      );
      if (!data?.ok) throw new Error(data?.detail || "AI 请求失败");

      const assistantText: string = data?.assistant?.content || "";
      const toolCalls: any[] = Array.isArray(data?.assistant?.tool_calls) ? data.assistant.tool_calls : [];
      const actions: AiAction[] = Array.isArray(data?.actions) ? data.actions : [];
      const warnings: string[] = Array.isArray(data?.warnings) ? data.warnings : [];

      const chunks: string[] = [];
      if (assistantText) chunks.push(assistantText);
      const actionSummary = summarizeActionsForUser(actions);
      // 避免 fast-path 已在 content 里写了“已切换周期/已切换品种”等，造成重复展示
      if (actionSummary) {
        const a = actionSummary.trim();
        const b = (assistantText || "").trim();
        if (a && a !== b && !b.includes(a)) chunks.push(actionSummary);
      }
      const toolSummary = summarizeToolCallsForUser(toolCalls);
      if (toolSummary) chunks.push(toolSummary);
      if (showDebug && toolCalls.length) chunks.push(`tool_calls:\n${JSON.stringify(toolCalls, null, 2)}`);
      if (showDebug && warnings.length) chunks.push(`warnings:\n- ${warnings.join("\n- ")}`);
      setAssistant(chunks.filter(Boolean).join("\n\n") || "（已完成）");

      if (actions.length) {
        setPhaseHint("绘图中…");
        await onExecuteActions(actions);
        setPhaseHint("");
        if (!showDebug) updateAssistant(`\n\n（已更新图表：${actions.length} 项）`);
      }
    } catch (e: any) {
      setErr(e?.message || "AI 请求失败");
    } finally {
      setPhaseHint("");
      setRunning(false);
    }
  };

  const annotateSelection = async () => {
    if (!settings) return;
    if (!selectionRange || !chartState?.symbol || !chartState?.timeframe) {
      setErr("请先用 Rectangle 画框并选中，然后点击“取矩形”");
      return;
    }
    setErr(null);
    setRunning(true);
    try {
      const data = await fetchJsonWithTimeout(
        apiUrl("/api/ai/annotate-selection"),
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            settings,
            symbol: chartState.symbol,
            timeframe: chartState.timeframe,
            from_time: selectionRange.from,
            to_time: selectionRange.to,
          }),
        },
        120_000,
        1
      );
      if (!data?.ok) throw new Error(data?.detail || "自动标注失败");
      const assistantText: string = data?.assistant?.content || "";
      const toolCalls: any[] = Array.isArray(data?.assistant?.tool_calls) ? data.assistant.tool_calls : [];
      const actions: AiAction[] = Array.isArray(data?.actions) ? data.actions : [];
      const chunks: string[] = [];
      if (assistantText) chunks.push(assistantText);
      const toolSummary = summarizeToolCallsForUser(toolCalls);
      if (toolSummary) chunks.push(toolSummary);
      if (showDebug && toolCalls.length) chunks.push(`tool_calls:\n${JSON.stringify(toolCalls, null, 2)}`);
      for (const c of chunks) {
        pushMsg("assistant", c);
        await sleep(120);
      }
      if (actions.length) {
        const results = await onExecuteActions(actions);
        if (showDebug) {
          pushMsg("assistant", `已执行标注动作：\n- ${(results || []).join("\n- ")}`);
        } else {
          pushMsg("assistant", `标注完成：已更新图表（${actions.length} 项）。`);
        }
      }
    } catch (e: any) {
      setErr(e?.message || "自动标注失败");
    } finally {
      setRunning(false);
    }
  };

  // 看图分析并标注（保留）：截图 → 多模态模型解读 → 自动落图（chart_draw）
  const visionAnalyze = async () => {
    if (!settings) return;
    if (!onRequestScreenshot) {
      setErr("当前版本未注入截图能力");
      return;
    }
    setErr(null);
    setRunning(true);
    try {
        const shot = await onRequestScreenshot();
        if (!shot) throw new Error("截图失败");

        // Trim massive data arrays from chartState before sending to AI to save token processing time
        const trimmedChartState = chartState ? JSON.parse(JSON.stringify(chartState)) : {};
        if (trimmedChartState.data) trimmedChartState.data = [];
        if (trimmedChartState.volumeProfile) trimmedChartState.volumeProfile = [];

        const data = await fetchJsonWithTimeout(
          apiUrl("/api/ai/vision-analyze"),
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              settings,
              chart_state: trimmedChartState,
              selection_range: selectionRange,
              screenshot_data_url: shot,
            }),
          },
          180_000,
          1
        );
      if (!data?.ok) throw new Error(data?.detail || "看图分析失败");

      const assistantText: string = data?.assistant?.content || "";
      const toolCalls: any[] = Array.isArray(data?.assistant?.tool_calls) ? data.assistant.tool_calls : [];
      const actions: AiAction[] = Array.isArray(data?.actions) ? data.actions : [];
      const warnings: string[] = Array.isArray(data?.warnings) ? data.warnings : [];

      const chunks: string[] = [];
      if (assistantText) chunks.push(`看图分析：\n${assistantText}`);
      const toolSummary = summarizeToolCallsForUser(toolCalls);
      if (toolSummary) chunks.push(toolSummary);
      if (showDebug && toolCalls.length) chunks.push(`tool_calls:\n${JSON.stringify(toolCalls, null, 2)}`);
      if (showDebug && warnings.length) chunks.push(`warnings:\n- ${warnings.join("\n- ")}`);
      for (const c of chunks) {
        pushMsg("assistant", c);
        await sleep(120);
      }
      if (actions.length) {
        const results = await onExecuteActions(actions);
        if (showDebug) {
          pushMsg("assistant", `已执行标注动作：\n- ${(results || []).join("\n- ")}`);
        } else {
          pushMsg("assistant", `已完成：${actions.length} 个图表更新。`);
        }
      }
    } catch (e: any) {
      setErr(e?.message || "看图分析失败");
    } finally {
      setRunning(false);
    }
  };

  if (!settings) return <div className="text-xs dark:text-gray-400 text-gray-500">加载中…</div>;

  return (
    <div className="h-full flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <div className="text-xs dark:text-gray-400 text-gray-500">AI · Chart Assistant</div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            className="h-8 px-2 text-xs hover:border-[#00bfa5] hover:bg-transparent"
            onClick={() => setShowDebug((v) => !v)}
            disabled={running}
            title="显示/隐藏内部 tool_calls（仅调试用）"
          >
            {showDebug ? "隐藏详细" : "显示详细"}
          </Button>
          <Button
            variant="outline"
            className="h-8 px-2 text-xs hover:border-[#00bfa5] hover:bg-transparent"
            onClick={() => {
              // 适配“无法强制刷新”的场景：通过 query 参数强制拉取最新 HTML/JS
              const v = Date.now();
              const url = `${window.location.pathname}?v=${v}`;
              window.location.href = url;
            }}
            disabled={running}
            title="如果你不能强制刷新，用这个按钮强制加载最新版本"
          >
            重新加载
          </Button>
          <Button
            variant="outline"
            className="h-8 px-2 text-xs hover:border-[#00bfa5] hover:bg-transparent"
            onClick={async () => {
              if (!settings) return;
              setErr(null);
              setRunning(true);
              try {
                const data = await fetchJsonWithTimeout(
                  apiUrl("/api/ai/test"),
                  { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ settings }) },
                  25_000,
                  1
                );
                if (!data?.ok) throw new Error(data?.detail || "测试失败");
                pushMsg("assistant", `连接测试：${data?.content || "OK"}`);
              } catch (e: any) {
                setErr(e?.message || "测试失败");
              } finally {
                setRunning(false);
              }
            }}
          >
            测试连接
          </Button>
          <button
            className="w-8 h-8 rounded-lg border dark:border-white/10 border-black/10 hover:border-[#00bfa5] hover:bg-transparent flex items-center justify-center"
            onClick={() => setShowSettings(true)}
            title="Settings"
          >
            <Settings size={18} />
          </button>
        </div>
      </div>

      <div className="text-[11px] text-gray-500 leading-4">
        当前：{chartState?.symbol || "-"} {chartState?.timeframe || "-"} · svp={chartState?.enabled?.svp ? "on" : "off"} · vrvp=
        {chartState?.enabled?.vrvp ? "on" : "off"} · bubble={chartState?.enabled?.bubble ? "on" : "off"} · RajaSR={chartState?.enabled?.RajaSR ? "on" : "off"}
        · RSI={chartState?.enabled?.RSI ? "on" : "off"} · MACD={chartState?.enabled?.MACD ? "on" : "off"} · EMA={chartState?.enabled?.EMA ? "on" : "off"}
        · BB={chartState?.enabled?.BB ? "on" : "off"} · VWAP={chartState?.enabled?.VWAP ? "on" : "off"} · ATR={chartState?.enabled?.ATR ? "on" : "off"}
        · Zigzag={chartState?.enabled?.Zigzag ? "on" : "off"}
      </div> 

      <div className="border dark:border-white/10 border-black/10 rounded p-2">
        <div className="text-xs dark:text-gray-400 text-gray-500 mb-2">看图分析并标注（Vision）</div>
        <div className="text-[11px] text-gray-500 mb-2">截图当前图表 → 多模态模型解读 → 自动落图</div>
        <Button className="h-8 px-3 text-xs" onClick={visionAnalyze} disabled={running}>
          看图分析并标注
        </Button>
      </div>

      {err && <div className="text-xs text-red-400 whitespace-pre-wrap">{err}</div>}

      <div ref={scrollRef} className="flex-1 overflow-auto border dark:border-white/10 border-black/10 rounded p-2 space-y-2 bg-black/10">
        {messages.map((m, idx) => (
          <div key={m.id || idx} className="text-xs whitespace-pre-wrap">
            <span className={m.role === "user" ? "text-emerald-300" : m.role === "system" ? "text-gray-500" : "dark:text-gray-200 text-gray-800"}>
              {m.role}：
            </span>{" "}
            {m.content}
          </div>
        ))}
        {running && <div className="text-xs dark:text-gray-400 text-gray-500">{phaseHint ? `阶段：${phaseHint}` : "AI 思考中…"}</div>}
      </div>

      <div className="flex gap-2">
        <input
          className="flex-1 h-9 bg-transparent border dark:border-white/10 border-black/10 rounded px-2 text-xs outline-none focus:border-emerald-400"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="输入指令或问题（例如：切到 EURUSD M15，打开 svp，回看 5 天）"
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              if (canSend && !running) send();
            }
          }}
        />
        <Button className="h-9 px-3 text-xs" onClick={send} disabled={!canSend || running}>
          发送
        </Button>
      </div>

      {showSettings && (
        <div className="absolute inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-[420px] max-w-[92vw] rounded-lg border dark:border-white/10 border-black/10 dark:bg-[#0b0f14] bg-white p-4 shadow-2xl">
            <div className="flex items-center justify-between mb-3">
              <div className="text-sm font-semibold">AI Settings</div>
              <button
                className="w-8 h-8 rounded-lg border dark:border-white/10 border-black/10 hover:dark:bg-white/5 bg-black/5 flex items-center justify-center"
                onClick={() => setShowSettings(false)}
                title="关闭"
              >
                <X size={18} />
              </button>
            </div>

            <div className="space-y-3">
              <label className="block text-xs dark:text-gray-400 text-gray-500">
                Base URL（OpenAI-compatible）
                <input
                  className="mt-1 w-full h-9 bg-transparent border dark:border-white/10 border-black/10 rounded px-2 text-xs outline-none focus:border-emerald-400"
                  value={settings.base_url}
                  onChange={(e) => setSettings({ ...settings, base_url: e.target.value })}
                  placeholder="https://api.openai.com 或你的网关地址"
                />
              </label>

              <label className="block text-xs dark:text-gray-400 text-gray-500">
                Model
                <input
                  className="mt-1 w-full h-9 bg-transparent border dark:border-white/10 border-black/10 rounded px-2 text-xs outline-none focus:border-emerald-400"
                  value={settings.model}
                  onChange={(e) => setSettings({ ...settings, model: e.target.value })}
                  placeholder="例如：gpt-4o-mini"
                />
              </label>

              <label className="block text-xs dark:text-gray-400 text-gray-500">
                API Key
                <input
                  type="password"
                  className="mt-1 w-full h-9 bg-transparent border dark:border-white/10 border-black/10 rounded px-2 text-xs outline-none focus:border-emerald-400 font-mono"
                  value={settings.api_key}
                  onChange={(e) => setSettings({ ...settings, api_key: e.target.value })}
                  placeholder="sk-..."
                  autoComplete="off"
                />
                <div className="mt-1 text-[11px] text-gray-600">当前：{redactKey(settings.api_key)}</div>
                <div className="mt-1 text-[11px] text-gray-600">提示：该设置仅保存在本机浏览器（localStorage）。</div>
              </label>

              <div className="flex justify-end gap-2 pt-2">
                <Button
                  variant="outline"
                  className="h-8 px-3 text-xs"
                  onClick={() => {
                    try {
                      localStorage.removeItem(KEY);
                    } catch {}
                    const d = defaultSettings();
                    setSettings(d);
                    saveSettings(d);
                  }}
                >
                  清除设置
                </Button>
                <Button
                  variant="outline"
                  className="h-8 px-3 text-xs"
                  onClick={() => {
                    const d = defaultSettings();
                    setSettings(d);
                    saveSettings(d);
                  }}
                >
                  重置默认
                </Button>
                <Button
                  className="h-8 px-3 text-xs"
                  onClick={() => {
                    saveSettings(settings);
                    setShowSettings(false);
                  }}
                >
                  保存
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
