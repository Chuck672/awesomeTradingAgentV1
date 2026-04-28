"use client";
import { getBaseUrl } from "@/lib/api";

import React, { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Settings, Inbox, X, ChevronDown, ChevronRight, Trash2 } from "lucide-react";

type AlertRow = {
  id: number;
  name: string;
  enabled: boolean;
  rule: any;
  created_at: number;
};

type AlertEvent = { id: number; alert_id: number; ts: number; message: string };

type AIReport = { id: number; alert_id: number; session_id: string; ts: number; report_content: string; alert_name: string };


const ALERT_AGENT_SETTINGS_KEY = "awesome_alerts_agent_settings_v1";

function loadAlertAgentSettings() {
  try {
    const raw = localStorage.getItem(ALERT_AGENT_SETTINGS_KEY);
    return raw ? JSON.parse(raw) : { base_url: "https://api.siliconflow.cn/v1", model: "deepseek-ai/DeepSeek-V3", api_key: "" };
  } catch {
    return { base_url: "https://api.siliconflow.cn/v1", model: "deepseek-ai/DeepSeek-V3", api_key: "" };
  }
}

function saveAlertAgentSettings(v: any) {
  localStorage.setItem(ALERT_AGENT_SETTINGS_KEY, JSON.stringify(v || {}));
}

const TG_KEY = "awesome_chart_telegram_settings_v1";
const ALERT_CREATE_COLLAPSED_KEY = "awesome_chart_alert_create_collapsed_v1";
const AI_REPORTS_LAST_SEEN_TS_KEY = "awesome_chart_ai_reports_last_seen_ts_v1";

function loadTelegram() {
  try {
    const raw = localStorage.getItem(TG_KEY);
    return raw ? JSON.parse(raw) : { token: "", chat_id: "" };
  } catch {
    return { token: "", chat_id: "" };
  }
}

function saveTelegram(v: any) {
  localStorage.setItem(TG_KEY, JSON.stringify(v || {}));
}

function loadNumber(key: string, fallback: number) {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return fallback;
    const n = Number(raw);
    return Number.isFinite(n) ? n : fallback;
  } catch {
    return fallback;
  }
}

function saveNumber(key: string, v: number) {
  try {
    localStorage.setItem(key, String(v));
  } catch {}
}

async function readJsonOrThrow(r: Response) {
  const text = await r.text();
  if (!r.ok) {
    throw new Error(text || `HTTP ${r.status}`);
  }
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    throw new Error(text);
  }
}

export function AlertsPanel(props: { symbol?: string; timeframe?: string }) {
  const [alerts, setAlerts] = useState<AlertRow[]>([]);
  const [events, setEvents] = useState<AlertEvent[]>([]);
  const [reports, setReports] = useState<AIReport[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [showReportsModal, setShowReportsModal] = useState(false);
  const [selectedReportId, setSelectedReportId] = useState<number | null>(null);
  const [showAnalyzerPromptModal, setShowAnalyzerPromptModal] = useState(false);
  const [analyzerPrompt, setAnalyzerPrompt] = useState("");
  const [analyzerPromptDirty, setAnalyzerPromptDirty] = useState(false);
  
  const [symbol, setSymbol] = useState(props.symbol || "XAUUSD");
  const [timeframe, setTimeframe] = useState(props.timeframe || "M15");
  const [alertType, setAlertType] = useState<"raja_sr_touch" | "msb_zigzag_break" | "trend_exhaustion" | "rectangle_breakout">("raja_sr_touch");
  
  // Specific settings
  const [cooldown, setCooldown] = useState(30);
  const [detectBos, setDetectBos] = useState(true);
  const [detectChoch, setDetectChoch] = useState(true);
  const [rectLookbackBars, setRectLookbackBars] = useState(220);
  const [rectMinTouchesPerSide, setRectMinTouchesPerSide] = useState(2);
  const [rectToleranceAtrMult, setRectToleranceAtrMult] = useState(0.25);
  const [initialPrompt, setInitialPrompt] = useState("");
  const [featureCatalog, setFeatureCatalog] = useState<any>(null);
  const [contextEnabled, setContextEnabled] = useState<Record<string, boolean>>({});
  const [contextParams, setContextParams] = useState<Record<string, any>>({});
  const [contextBundles, setContextBundles] = useState<Record<string, boolean>>({});

  const [enableTg, setEnableTg] = useState(false);
  const [showTgSettings, setShowTgSettings] = useState(false);
  const [tg, setTg] = useState<{ token: string; chat_id: string }>(() => ({ token: "", chat_id: "" }));
  const [agentSettings, setAgentSettings] = useState(loadAlertAgentSettings());
  const [showAgentSettingsModal, setShowAgentSettingsModal] = useState(false);
  const [createCollapsed, setCreateCollapsed] = useState(true);
  const [lastSeenReportTs, setLastSeenReportTs] = useState(0);

  useEffect(() => {
    const loadedTg = loadTelegram();
    setTg(loadedTg);
    if (loadedTg.token && loadedTg.chat_id) {
      setEnableTg(true);
    }
  }, []);
  useEffect(() => {
    setCreateCollapsed(!!loadNumber(ALERT_CREATE_COLLAPSED_KEY, 1));
    setLastSeenReportTs(loadNumber(AI_REPORTS_LAST_SEEN_TS_KEY, 0));
  }, []);
  useEffect(() => setSymbol(props.symbol || "XAUUSD"), [props.symbol]);
  useEffect(() => setTimeframe(props.timeframe || "M15"), [props.timeframe]);
  useEffect(() => {
    (async () => {
      try {
        const cat = await fetch(`${getBaseUrl()}/api/market/features/catalog`).then(readJsonOrThrow);
        setFeatureCatalog(cat);
      } catch (e: any) {
        setErr(e?.message || "Failed to load feature catalog");
      }
    })();
  }, []);

  const patternCatalogItems = useMemo(() => {
    const groups = featureCatalog?.groups;
    if (!Array.isArray(groups)) return [];
    const g = groups.find((x: any) => x?.id === "patterns");
    const items = g?.items;
    return Array.isArray(items) ? items : [];
  }, [featureCatalog]);

  const contextBundleDefs = useMemo(() => {
    return [
      { id: "ta_sessionvp_rajasr_msb", label: "TA + SessionVP + RajaSR + MSB", features: ["bos_choch", "close_outside_level_zone"] },
      { id: "ta_vp_candle", label: "TA + VP + Candlestick Patterns", features: ["candlestick"] },
      { id: "ta_vp_rectangle", label: "TA + VP + Rectangle Range", features: ["rectangle_range"] },
      { id: "smc_pack", label: "SMC Pack (BOS/CHOCH + Sweep + False Breakout + Retest)", features: ["bos_choch", "liquidity_sweep", "false_breakout", "close_outside_level_zone", "breakout_retest_hold"] },
    ];
  }, []);

  const enableContextFeature = (fid: string) => {
    setContextEnabled(prev => ({ ...(prev || {}), [fid]: true }));
    const it = patternCatalogItems.find((x: any) => String(x?.id || "") === fid);
    const params = Array.isArray(it?.params) ? it.params : [];
    if (!params.length) return;
    setContextParams(prev => {
      const next = { ...(prev || {}) };
      const cur = { ...(next[fid] || {}) };
      for (const p of params) {
        const n = String(p?.name || "");
        if (!n) continue;
        if (cur[n] === undefined) cur[n] = p?.default;
      }
      next[fid] = cur;
      return next;
    });
  };

  const updateContextParam = (featureId: string, name: string, value: any) => {
    setContextParams(prev => {
      const next = { ...(prev || {}) };
      const cur = { ...(next[featureId] || {}) };
      cur[name] = value;
      next[featureId] = cur;
      return next;
    });
  };

  const unreadReportCount = useMemo(() => {
    if (!reports?.length) return 0;
    const t = Number(lastSeenReportTs || 0);
    return reports.filter(r => Number(r.ts || 0) > t).length;
  }, [reports, lastSeenReportTs]);

  const markReportsReadThrough = (ts: number) => {
    const t = Number(ts || 0);
    if (!Number.isFinite(t) || t <= 0) return;
    setLastSeenReportTs(prev => {
      const next = Math.max(Number(prev || 0), t);
      saveNumber(AI_REPORTS_LAST_SEEN_TS_KEY, next);
      return next;
    });
  };

  const refresh = async () => {
    setErr(null);
    try {
      const a = await fetch(`${getBaseUrl()}/api/alerts`).then(readJsonOrThrow);
      setAlerts(Array.isArray(a?.alerts) ? a.alerts : []);
      const e = await fetch(`${getBaseUrl()}/api/alerts/events?limit=100`).then(readJsonOrThrow);
      setEvents(Array.isArray(e?.events) ? e.events : []);
      const rp = await fetch(`${getBaseUrl()}/api/alerts/reports?limit=50`).then(readJsonOrThrow);
      setReports(Array.isArray(rp?.reports) ? rp.reports : []);
    } catch (e: any) {
      setErr(e?.message || "Failed to load");
    }
  };

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, []);

  const loadAnalyzerPrompt = async () => {
    setErr(null);
    try {
      const r = await fetch(`${getBaseUrl()}/api/alerts/analyzer-prompt`).then(readJsonOrThrow);
      setAnalyzerPrompt(String(r?.prompt || ""));
      setAnalyzerPromptDirty(false);
    } catch (e: any) {
      setErr(e?.message || "Failed to load analyzer prompt");
    }
  };

  const saveAnalyzerPrompt = async () => {
    setErr(null);
    try {
      const r = await fetch(`${getBaseUrl()}/api/alerts/analyzer-prompt`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: analyzerPrompt }),
      }).then(readJsonOrThrow);
      if (!r?.ok) throw new Error(r?.detail || "Failed to save");
      setAnalyzerPromptDirty(false);
      setShowAnalyzerPromptModal(false);
    } catch (e: any) {
      setErr(e?.message || "Failed to save analyzer prompt");
    }
  };

  const clearEventLogs = async () => {
    setErr(null);
    try {
      const r = await fetch(`${getBaseUrl()}/api/alerts/events/clear`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}) }).then(readJsonOrThrow);
      if (!r?.ok) throw new Error(r?.detail || "Failed to clear");
      setEvents([]);
      refresh();
    } catch (e: any) {
      setErr(e?.message || "Failed to clear");
    }
  };

  const clearAIReports = async () => {
    setErr(null);
    try {
      const r = await fetch(`${getBaseUrl()}/api/alerts/reports/clear`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}) }).then(readJsonOrThrow);
      if (!r?.ok) throw new Error(r?.detail || "Failed to clear");
      setReports([]);
      setSelectedReportId(null);
      setShowReportsModal(false);
      setLastSeenReportTs(0);
      saveNumber(AI_REPORTS_LAST_SEEN_TS_KEY, 0);
      refresh();
    } catch (e: any) {
      setErr(e?.message || "Failed to clear");
    }
  };

  const create = async () => {
    setErr(null);
    try {
      saveTelegram(tg);
      let rule: any = {
        type: alertType,
        symbol,
        timeframe,
        telegram: enableTg && tg?.token && tg?.chat_id ? { token: tg.token, chat_id: tg.chat_id } : undefined,
        agent_configs: {
          initial_prompt: initialPrompt || undefined,
        },
      };

      // Inject Agent Configs from dedicated Alert settings
      try {
        const s = agentSettings;
        if (s && s.api_key) {
          rule.agent_configs.analyzer = { base_url: s.base_url, model: s.model, api_key: s.api_key };
          rule.agent_configs.supervisor = { base_url: s.base_url, model: s.model, api_key: s.api_key };
        }
      } catch (e) {}

      try {
        const enabledIds = Object.entries(contextEnabled || {}).filter(([, v]) => !!v).map(([k]) => k);
        if (enabledIds.length) {
          const params: any = {};
          for (const k of enabledIds) {
            params[k] = contextParams?.[k] || {};
          }
          rule.agent_configs.context_features = { timeframe, enabled: enabledIds, params };
        }
      } catch (e) {}

      let name = "";
      if (alertType === "raja_sr_touch") {
        rule.cooldown_minutes = cooldown;
        name = `RajaSR ${symbol} ${timeframe}`;
      } else if (alertType === "msb_zigzag_break") {
        rule.detect_bos = detectBos;
        rule.detect_choch = detectChoch;
        name = `MSB Break ${symbol} ${timeframe}`;
      } else if (alertType === "trend_exhaustion") {
        name = `Trend Exhaustion ${symbol} ${timeframe}`;
      } else if (alertType === "rectangle_breakout") {
        rule.lookback_bars = rectLookbackBars;
        rule.min_touches_per_side = rectMinTouchesPerSide;
        rule.tolerance_atr_mult = rectToleranceAtrMult;
        rule.cooldown_minutes = cooldown;
        name = `Rectangle Breakout ${symbol} ${timeframe}`;
      }

      const r = await fetch(`${getBaseUrl()}/api/alerts/create`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, rule, enabled: true }),
      }).then(readJsonOrThrow);
      
      if (!r?.ok) throw new Error(r?.detail || "Failed to create");
      await refresh();
      setInitialPrompt(""); // clear prompt after success
    } catch (e: any) {
      setErr(e?.message || "Failed to create");
    }
  };

  const toggle = async (id: number, enabled: boolean) => {
    try {
      const r = await fetch(`${getBaseUrl()}/api/alerts/toggle`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id, enabled: !enabled }),
      }).then(readJsonOrThrow);
      if (!r?.ok) throw new Error(r?.detail || "Failed to toggle");
      refresh();
    } catch (e: any) {
      setErr(e?.message || "Failed to toggle");
    }
  };

  const remove = async (id: number) => {
    try {
      const r = await fetch(`${getBaseUrl()}/api/alerts/delete`, { 
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id })
      }).then(readJsonOrThrow);
      if (!r?.ok) throw new Error(r?.detail || "Failed to delete");
      refresh();
    } catch (e: any) {
      setErr(e?.message || "Failed to delete");
    }
  };

  return (
    <div className="h-full flex flex-col gap-3 p-3 overflow-y-auto relative">
      <div className="flex items-center justify-between">
        <div className="text-sm font-semibold text-gray-200">AI Agent Triggers</div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowAgentSettingsModal(true)}
            className="flex items-center gap-1.5 px-2 py-1 bg-white/10 hover:bg-white/20 rounded text-xs text-white transition-colors"
            title="Agent Settings"
            type="button"
          >
            <Settings size={14} />
          </button>
          <button
            onClick={async () => {
              await loadAnalyzerPrompt();
              setShowAnalyzerPromptModal(true);
            }}
            className="flex items-center gap-1.5 px-2 py-1 bg-white/10 hover:bg-white/20 rounded text-xs text-white transition-colors"
            type="button"
          >
            Analyzer System Prompt
          </button>
          <button 
            onClick={() => setShowReportsModal(true)}
            className="flex items-center gap-1.5 px-2 py-1 bg-white/10 hover:bg-white/20 rounded text-xs text-white transition-colors relative"
            type="button"
          >
            <Inbox size={14} />
            <span>AI Reports</span>
            {unreadReportCount > 0 && (
              <span className="absolute -top-1 -right-1 flex h-3 w-3 items-center justify-center rounded-full bg-red-500 text-[8px] font-bold text-white">
                {unreadReportCount}
              </span>
            )}
          </button>
        </div>
      </div>
      
      {err && <div className="text-xs text-red-400 whitespace-pre-wrap bg-red-500/10 p-2 rounded">{err}</div>}

      {/* CREATE NEW RULE */}
      <div className="border border-white/10 bg-white/5 rounded p-3">
        <button
          className="w-full flex items-center justify-between text-xs font-medium text-[#00bfa5]"
          onClick={() => {
            const next = !createCollapsed;
            setCreateCollapsed(next);
            saveNumber(ALERT_CREATE_COLLAPSED_KEY, next ? 1 : 0);
          }}
          type="button"
        >
          <span>Create New Event Trigger</span>
          {createCollapsed ? <ChevronRight size={14} className="text-[#00bfa5]" /> : <ChevronDown size={14} className="text-[#00bfa5]" />}
        </button>
        <div className="text-[10px] text-gray-500 mt-1">
          {alertType.replace(/_/g, " ")} · {symbol} · {timeframe}
        </div>

        {!createCollapsed && (
          <div className="space-y-3 mt-3">
            <select 
              className="w-full h-8 bg-[#0b0f14] border border-white/10 rounded px-2 text-xs text-white" 
              value={alertType} 
              onChange={(e) => setAlertType(e.target.value as any)}
            >
              <option value="raja_sr_touch">RajaSR Zone Touch</option>
              <option value="msb_zigzag_break">MSB / ChoCh Structure Break</option>
              <option value="trend_exhaustion">Trend Exhaustion (Triangle)</option>
              <option value="rectangle_breakout">Rectangle Pattern Breakout</option>
            </select>

            <div className="grid grid-cols-2 gap-2">
              <input className="h-8 bg-black/30 border border-white/10 rounded px-2 text-xs" value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="Symbol (e.g. XAUUSD)" />
              <select className="h-8 bg-[#0b0f14] border border-white/10 rounded px-2 text-xs text-white" value={timeframe} onChange={(e) => setTimeframe(e.target.value)}>
                <option value="M1">M1</option>
                <option value="M5">M5</option>
                <option value="M15">M15</option>
                <option value="M30">M30</option>
                <option value="H1">H1</option>
                <option value="H4">H4</option>
                <option value="D1">D1</option>
              </select>
            </div>

            {/* Dynamic Params based on type */}
            {alertType === "raja_sr_touch" && (
              <div className="flex items-center justify-between text-xs text-gray-300 bg-black/20 p-2 rounded">
                <span>Cooldown (mins):</span>
                <input className="w-16 h-6 bg-black/50 border border-white/10 rounded px-2 text-center" type="number" value={cooldown} onChange={(e) => setCooldown(Number(e.target.value))} />
              </div>
            )}

            {alertType === "msb_zigzag_break" && (
              <div className="flex items-center gap-4 text-xs text-gray-300 bg-black/20 p-2 rounded">
                <label className="flex items-center gap-1.5 cursor-pointer">
                  <input type="checkbox" checked={detectChoch} onChange={(e) => setDetectChoch(e.target.checked)} /> CHOCH
                </label>
                <label className="flex items-center gap-1.5 cursor-pointer">
                  <input type="checkbox" checked={detectBos} onChange={(e) => setDetectBos(e.target.checked)} /> BoS
                </label>
              </div>
            )}
            {alertType === "rectangle_breakout" && (
              <div className="grid grid-cols-3 gap-2 text-xs text-gray-300 bg-black/20 p-2 rounded">
                <div className="flex flex-col gap-1">
                  <span className="text-[10px] text-gray-500">lookback_bars</span>
                  <input className="h-7 bg-black/30 border border-white/10 rounded px-2 text-[11px] text-white" type="number" value={rectLookbackBars} onChange={(e) => setRectLookbackBars(Number(e.target.value))} />
                </div>
                <div className="flex flex-col gap-1">
                  <span className="text-[10px] text-gray-500">min_touches</span>
                  <input className="h-7 bg-black/30 border border-white/10 rounded px-2 text-[11px] text-white" type="number" value={rectMinTouchesPerSide} onChange={(e) => setRectMinTouchesPerSide(Number(e.target.value))} />
                </div>
                <div className="flex flex-col gap-1">
                  <span className="text-[10px] text-gray-500">tolerance_atr_mult</span>
                  <input className="h-7 bg-black/30 border border-white/10 rounded px-2 text-[11px] text-white" type="number" step="any" value={rectToleranceAtrMult} onChange={(e) => setRectToleranceAtrMult(Number(e.target.value))} />
                </div>
              </div>
            )}

            <div className="flex flex-col gap-1">
              <span className="text-[11px] text-gray-500">Agent Prompt (Optional)</span>
              <textarea 
                className="w-full h-16 bg-black/30 border border-white/10 rounded p-2 text-xs resize-none" 
                placeholder="e.g. Please analyze if this is a valid setup and draw a box..."
                value={initialPrompt}
                onChange={(e) => setInitialPrompt(e.target.value)}
              />
            </div>

            <div className="bg-black/20 p-2 rounded border border-white/5">
              <div className="flex items-center justify-between mb-2">
                <div className="text-[11px] text-gray-400 font-medium">Context Presets (互补组合)</div>
                <button
                  className="text-[10px] px-2 py-1 bg-white/10 hover:bg-white/20 rounded text-gray-300"
                  type="button"
                  onClick={() => {
                    setContextBundles({});
                    setContextEnabled({});
                    setContextParams({});
                  }}
                >
                  Reset
                </button>
              </div>
              <div className="grid grid-cols-1 gap-2">
                {contextBundleDefs.map((b) => {
                  const checked = !!contextBundles[b.id];
                  return (
                    <label key={b.id} className="flex items-start gap-2 text-[11px] text-gray-200 cursor-pointer bg-black/10 border border-white/10 rounded p-2">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={(e) => {
                          const v = e.target.checked;
                          setContextBundles(prev => ({ ...(prev || {}), [b.id]: v }));
                          if (v) {
                            for (const fid of b.features) enableContextFeature(fid);
                          }
                        }}
                      />
                      <div className="flex flex-col gap-1">
                        <div className="text-gray-100">{b.label}</div>
                        <div className="text-[10px] text-gray-500">
                          {b.features.join(", ")}
                        </div>
                      </div>
                    </label>
                  );
                })}
              </div>
              <div className="text-[10px] text-gray-500 mt-2">
                TA / SessionVP / active_zones / recent_structure_breaks 等基础上下文会自动随事件构建；这里主要控制额外的 pattern_events 与 patterns 模块。
              </div>
            </div>

            <div className="bg-black/20 p-2 rounded border border-white/5">
              <div className="text-[11px] text-gray-400 font-medium mb-2">Context Features (AI 投喂选型)</div>
              {!patternCatalogItems.length ? (
                <div className="text-[10px] text-gray-500">Feature catalog not loaded.</div>
              ) : (
                <div className="space-y-2">
                  {patternCatalogItems.map((it: any) => {
                    const fid = String(it?.id || "");
                    if (!fid) return null;
                    const enabled = !!contextEnabled[fid];
                    const params = Array.isArray(it?.params) ? it.params : [];
                    return (
                      <div key={fid} className="border border-white/10 rounded p-2 bg-black/10">
                        <label className="flex items-center gap-2 text-[11px] text-gray-200 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={enabled}
                            onChange={(e) => {
                              const v = e.target.checked;
                              setContextEnabled(prev => ({ ...(prev || {}), [fid]: v }));
                              if (v && params.length) {
                                setContextParams(prev => {
                                  const next = { ...(prev || {}) };
                                  const cur = { ...(next[fid] || {}) };
                                  for (const p of params) {
                                    const n = String(p?.name || "");
                                    if (!n) continue;
                                    if (cur[n] === undefined) cur[n] = p?.default;
                                  }
                                  next[fid] = cur;
                                  return next;
                                });
                              }
                            }}
                          />
                          <span>{String(it?.label || fid)}</span>
                        </label>
                        {enabled && params.length > 0 && (
                          <div className="mt-2 grid grid-cols-2 gap-2">
                            {params.map((p: any) => {
                              const pn = String(p?.name || "");
                              if (!pn) return null;
                              const pt = String(p?.type || "string");
                              const val = contextParams?.[fid]?.[pn];
                              const enumVals = Array.isArray(p?.enum) ? p.enum : null;
                              if (pt === "boolean") {
                                return (
                                  <label key={pn} className="flex items-center gap-2 text-[10px] text-gray-300">
                                    <input type="checkbox" checked={!!val} onChange={(e) => updateContextParam(fid, pn, e.target.checked)} />
                                    <span>{pn}</span>
                                  </label>
                                );
                              }
                              if (pt === "string" && enumVals) {
                                return (
                                  <div key={pn} className="flex flex-col gap-1">
                                    <span className="text-[10px] text-gray-500">{pn}</span>
                                    <select
                                      className="h-7 bg-[#0b0f14] border border-white/10 rounded px-2 text-[11px] text-white"
                                      value={String(val ?? p?.default ?? "")}
                                      onChange={(e) => updateContextParam(fid, pn, e.target.value)}
                                    >
                                      {enumVals.map((x: any) => (
                                        <option key={String(x)} value={String(x)}>
                                          {String(x)}
                                        </option>
                                      ))}
                                    </select>
                                  </div>
                                );
                              }
                              if (pt === "array") {
                                return (
                                  <div key={pn} className="flex flex-col gap-1">
                                    <span className="text-[10px] text-gray-500">{pn}</span>
                                    <input
                                      className="h-7 bg-black/30 border border-white/10 rounded px-2 text-[11px] text-white"
                                      value={Array.isArray(val) ? val.join(",") : String(val ?? "")}
                                      onChange={(e) => {
                                        const raw = e.target.value;
                                        const parts = raw
                                          .split(",")
                                          .map(s => s.trim())
                                          .filter(Boolean)
                                          .map(s => {
                                            const n = Number(s);
                                            return Number.isFinite(n) ? n : s;
                                          });
                                        updateContextParam(fid, pn, parts);
                                      }}
                                    />
                                  </div>
                                );
                              }
                              const isInt = pt === "integer";
                              const num = Number(val ?? p?.default ?? 0);
                              return (
                                <div key={pn} className="flex flex-col gap-1">
                                  <span className="text-[10px] text-gray-500">{pn}</span>
                                  <input
                                    className="h-7 bg-black/30 border border-white/10 rounded px-2 text-[11px] text-white"
                                    type="number"
                                    step={isInt ? 1 : "any"}
                                    value={Number.isFinite(num) ? num : 0}
                                    onChange={(e) => updateContextParam(fid, pn, isInt ? parseInt(e.target.value || "0", 10) : Number(e.target.value))}
                                  />
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
              <div className="text-[10px] text-gray-500 mt-2">
                创建规则时会写入 rule.agent_configs.context_features，由后端决定构建 event_context 时计算哪些特征。
              </div>
            </div>

            <div className="flex items-center justify-between pt-1 border-t border-white/10">
              <label className="flex items-center gap-1.5 text-[11px] text-gray-300 cursor-pointer">
                <input type="checkbox" checked={enableTg} onChange={(e) => setEnableTg(e.target.checked)} />
                Enable Telegram Notification
              </label>
              <button 
                className="text-gray-500 hover:text-white transition-colors p-1 rounded hover:bg-white/10"
                onClick={() => setShowTgSettings(!showTgSettings)}
                title="Telegram Settings"
                type="button"
              >
                <Settings size={14} />
              </button>
            </div>

            {showTgSettings && (
              <div className="grid grid-cols-2 gap-2 bg-black/20 p-2 rounded border border-white/5">
                <input className="h-8 bg-[#0b0f14] border border-white/10 rounded px-2 text-xs" value={tg.token} onChange={(e) => setTg({ ...tg, token: e.target.value })} placeholder="Bot Token" />
                <input className="h-8 bg-[#0b0f14] border border-white/10 rounded px-2 text-xs" value={tg.chat_id} onChange={(e) => setTg({ ...tg, chat_id: e.target.value })} placeholder="Chat ID" />
              </div>
            )}

            <Button className="w-full h-8 text-xs bg-[#00bfa5] hover:bg-[#00bfa5]/80 text-black font-medium" onClick={create}>
              Create Rule
            </Button>
          </div>
        )}
      </div>

      {/* ACTIVE RULES LIST */}
      <div className="flex-1 min-h-[150px] overflow-y-auto space-y-2 custom-scrollbar pr-1">
        <div className="text-xs font-medium text-gray-400">Active Rules</div>
        {alerts.length === 0 && <div className="text-xs text-gray-500 text-center py-4">No rules created yet</div>}
        {alerts.map((a) => {
          const r = a.rule || {};
          return (
            <div key={a.id} className={`border ${a.enabled ? 'border-[#00bfa5]/30 bg-[#00bfa5]/5' : 'border-white/10 bg-white/5'} rounded p-2 flex flex-col gap-2 transition-colors`}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className={`w-2 h-2 rounded-full ${a.enabled ? 'bg-[#00bfa5] shadow-[0_0_5px_#00bfa5]' : 'bg-gray-600'}`} />
                  <span className="text-xs font-medium text-gray-200">{a.name}</span>
                </div>
                <div className="flex items-center gap-2">
                  <button onClick={() => toggle(a.id, a.enabled)} className="text-[10px] px-2 py-1 bg-white/10 hover:bg-white/20 rounded text-gray-300">
                    {a.enabled ? 'Disable' : 'Enable'}
                  </button>
                  <button onClick={() => remove(a.id)} className="text-[10px] px-2 py-1 bg-red-500/20 hover:bg-red-500/40 rounded text-red-300">
                    Del
                  </button>
                </div>
              </div>
              <div className="text-[10px] text-gray-400 font-mono break-all line-clamp-1">
                {r.agent_configs?.initial_prompt || "Default Agent Prompt"}
              </div>
            </div>
          );
        })}
      </div>

      {/* TRIGGER LOGS */}
      <div className="border border-white/10 rounded p-3 h-[180px] shrink-0 flex flex-col">
        <div className="flex items-center justify-between mb-2">
          <div className="text-xs font-medium text-gray-400">Event Logs</div>
          <button
            onClick={clearEventLogs}
            className="text-[10px] px-2 py-1 bg-white/10 hover:bg-white/20 rounded text-gray-300 flex items-center gap-1"
            type="button"
          >
            <Trash2 size={12} />
            Clear
          </button>
        </div>
        <div className="flex-1 overflow-y-auto space-y-2 pr-1 custom-scrollbar">
          {events.map((e) => (
            <div key={e.id} className="text-[10px] border-l-2 border-[#00bfa5] bg-white/5 rounded-r p-1.5 flex flex-col gap-1">
              <div className="text-gray-500">{new Date(e.ts * 1000).toLocaleString()}</div>
              <div className="text-gray-300 leading-tight">{e.message}</div>
            </div>
          ))}
          {events.length === 0 && <div className="text-xs text-gray-500 text-center py-2">No triggers yet</div>}
        </div>
      </div>

      {/* AI REPORTS MODAL */}
      {showReportsModal && (
        <div className="absolute inset-0 bg-[#0b0f14] z-50 flex flex-col">
          <div className="flex items-center justify-between p-3 border-b border-white/10 shrink-0">
            <div className="text-sm font-semibold text-white flex items-center gap-2">
              <Inbox size={16} />
              AI Reports Inbox
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={clearAIReports}
                className="text-[10px] px-2 py-1 bg-white/10 hover:bg-white/20 rounded text-gray-300 flex items-center gap-1"
                type="button"
              >
                <Trash2 size={12} />
                Clear
              </button>
              <button onClick={() => { setShowReportsModal(false); setSelectedReportId(null); }} className="text-gray-400 hover:text-white transition-colors" type="button">
                <X size={16} />
              </button>
            </div>
          </div>
          
          {selectedReportId === null ? (
            <div className="flex-1 overflow-y-auto p-3 space-y-2 custom-scrollbar">
              {reports.length === 0 && (
                <div className="text-xs text-gray-500 text-center py-10">No AI reports generated yet.</div>
              )}
              {reports.map((r) => {
                const isUnread = Number(r.ts || 0) > Number(lastSeenReportTs || 0);
                return (
                  <div 
                    key={r.id} 
                    onClick={() => {
                      markReportsReadThrough(Number(r.ts || 0));
                      setSelectedReportId(r.id);
                    }}
                    className={`bg-white/5 hover:bg-white/10 border border-white/10 rounded p-3 cursor-pointer transition-colors flex flex-col gap-2 ${isUnread ? "ring-1 ring-red-500/30" : ""}`}
                  >
                    <div className="flex items-center justify-between text-[10px] text-gray-400">
                      <div className="flex items-center gap-2">
                        {isUnread && <span className="w-1.5 h-1.5 rounded-full bg-red-500" />}
                        <span>{new Date(r.ts * 1000).toLocaleString()}</span>
                      </div>
                      <span className="bg-[#00bfa5]/20 text-[#00bfa5] px-1.5 py-0.5 rounded">{r.alert_name}</span>
                    </div>
                    <div className="text-xs text-gray-200 font-medium line-clamp-2 break-words">
                      {r.report_content.replace(/[#*`]/g, '').slice(0, 100)}...
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="flex-1 flex flex-col overflow-hidden">
              <div className="p-2 border-b border-white/10 shrink-0 flex items-center">
                <button onClick={() => setSelectedReportId(null)} className="text-xs text-[#00bfa5] hover:underline">
                  &larr; Back to Inbox
                </button>
              </div>
              <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
                {reports.filter(r => r.id === selectedReportId).map(r => (
                  <div key={r.id} className="text-xs text-gray-200 whitespace-pre-wrap font-mono leading-relaxed">
                    {r.report_content}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {showAnalyzerPromptModal && (
        <div className="absolute inset-0 bg-[#0b0f14] z-50 flex flex-col">
          <div className="flex items-center justify-between p-3 border-b border-white/10 shrink-0">
            <div className="text-sm font-semibold text-white">Analyzer System Prompt</div>
            <button
              onClick={() => setShowAnalyzerPromptModal(false)}
              className="text-gray-400 hover:text-white transition-colors"
              type="button"
              title="Close"
            >
              <X size={16} />
            </button>
          </div>
          <div className="flex-1 overflow-hidden p-3 flex flex-col gap-2">
            <div className="text-[11px] text-gray-500">
              保存后会写入 alerts.sqlite，并在下一次 event_dual analyzer 执行时生效。
            </div>
            <textarea
              className="flex-1 w-full text-xs rounded border border-white/10 bg-black/20 p-2 outline-none focus:border-emerald-400 custom-scrollbar resize-none font-mono"
              value={analyzerPrompt}
              onChange={(e) => {
                setAnalyzerPrompt(e.target.value);
                setAnalyzerPromptDirty(true);
              }}
            />
            <div className="flex items-center justify-end gap-2">
              <Button
                className="h-8 px-3 text-xs"
                variant="secondary"
                onClick={() => setShowAnalyzerPromptModal(false)}
                type="button"
              >
                Cancel
              </Button>
              <Button
                className="h-8 px-3 text-xs bg-[#00bfa5] hover:bg-[#00bfa5]/80 text-black font-medium disabled:opacity-50"
                onClick={saveAnalyzerPrompt}
                disabled={!analyzerPromptDirty}
                type="button"
              >
                Save
              </Button>
            </div>
          </div>
        </div>
      )}
      {showAgentSettingsModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="bg-[#1e1e1e] border border-white/10 rounded-lg shadow-2xl w-full max-w-md overflow-hidden flex flex-col">
            <div className="flex items-center justify-between p-3 border-b border-white/10 bg-white/5">
              <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                <Settings size={16} className="text-blue-400" />
                Alert Agent Settings
              </h3>
              <button onClick={() => setShowAgentSettingsModal(false)} className="text-gray-400 hover:text-white p-1 rounded-md hover:bg-white/10 transition-colors">
                <X size={16} />
              </button>
            </div>
            <div className="p-4 flex flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <label className="text-xs text-gray-400">Base URL</label>
                <input
                  type="text"
                  value={agentSettings.base_url}
                  onChange={(e) => setAgentSettings({ ...agentSettings, base_url: e.target.value })}
                  className="w-full bg-black/40 border border-white/10 rounded px-2.5 py-1.5 text-xs text-white placeholder-gray-600 focus:outline-none focus:border-blue-500 transition-colors"
                  placeholder="https://api.siliconflow.cn/v1"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-xs text-gray-400">Model</label>
                <input
                  type="text"
                  value={agentSettings.model}
                  onChange={(e) => setAgentSettings({ ...agentSettings, model: e.target.value })}
                  className="w-full bg-black/40 border border-white/10 rounded px-2.5 py-1.5 text-xs text-white placeholder-gray-600 focus:outline-none focus:border-blue-500 transition-colors"
                  placeholder="deepseek-ai/DeepSeek-V3"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-xs text-gray-400">API Key</label>
                <input
                  type="password"
                  value={agentSettings.api_key}
                  onChange={(e) => setAgentSettings({ ...agentSettings, api_key: e.target.value })}
                  className="w-full bg-black/40 border border-white/10 rounded px-2.5 py-1.5 text-xs text-white placeholder-gray-600 focus:outline-none focus:border-blue-500 transition-colors"
                  placeholder="sk-..."
                />
              </div>
            </div>
            <div className="p-3 border-t border-white/10 bg-black/20 flex justify-end gap-2">
              <button
                onClick={() => setShowAgentSettingsModal(false)}
                className="px-3 py-1.5 text-xs text-gray-400 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  saveAlertAgentSettings(agentSettings);
                  setShowAgentSettingsModal(false);
                }}
                className="px-4 py-1.5 bg-blue-500/20 text-blue-400 hover:bg-blue-500/30 hover:text-blue-300 border border-blue-500/30 rounded text-xs transition-colors"
              >
                Save
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}