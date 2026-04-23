"use client";

import React, { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Settings, Inbox, X } from "lucide-react";

type AlertRow = {
  id: number;
  name: string;
  enabled: boolean;
  rule: any;
  created_at: number;
};

type AlertEvent = { id: number; alert_id: number; ts: number; message: string };

type AIReport = { id: number; alert_id: number; session_id: string; ts: number; report_content: string; alert_name: string };

const TG_KEY = "awesome_chart_telegram_settings_v1";

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

export function AlertsPanel(props: { symbol?: string; timeframe?: string }) {
  const [alerts, setAlerts] = useState<AlertRow[]>([]);
  const [events, setEvents] = useState<AlertEvent[]>([]);
  const [reports, setReports] = useState<AIReport[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [showReportsModal, setShowReportsModal] = useState(false);
  const [selectedReportId, setSelectedReportId] = useState<number | null>(null);
  
  const [symbol, setSymbol] = useState(props.symbol || "XAUUSD");
  const [timeframe, setTimeframe] = useState(props.timeframe || "M15");
  const [alertType, setAlertType] = useState<"raja_sr_touch" | "msb_zigzag_break" | "trend_exhaustion">("raja_sr_touch");
  
  // Specific settings
  const [cooldown, setCooldown] = useState(30);
  const [detectBos, setDetectBos] = useState(true);
  const [detectChoch, setDetectChoch] = useState(true);
  const [initialPrompt, setInitialPrompt] = useState("");

  const [enableTg, setEnableTg] = useState(false);
  const [showTgSettings, setShowTgSettings] = useState(false);
  const [tg, setTg] = useState<{ token: string; chat_id: string }>(() => ({ token: "", chat_id: "" }));

  useEffect(() => {
    const loadedTg = loadTelegram();
    setTg(loadedTg);
    if (loadedTg.token && loadedTg.chat_id) {
      setEnableTg(true);
    }
  }, []);
  useEffect(() => setSymbol(props.symbol || "XAUUSD"), [props.symbol]);
  useEffect(() => setTimeframe(props.timeframe || "M15"), [props.timeframe]);

  const refresh = async () => {
    setErr(null);
    try {
      const a = await fetch("/api/alerts").then((r) => r.json());
      setAlerts(Array.isArray(a?.alerts) ? a.alerts : []);
      const e = await fetch("/api/alerts/events?limit=100").then((r) => r.json());
      setEvents(Array.isArray(e?.events) ? e.events : []);
      const rp = await fetch("/api/alerts/reports?limit=50").then((r) => r.json());
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
          initial_prompt: initialPrompt || undefined
        }
      };

      // Inject Agent Configs from local storage so the backend has API keys to run the agent
      try {
        const rawSettings = localStorage.getItem("awesome_trading_agent_settings_v3");
        if (rawSettings) {
          const s = JSON.parse(rawSettings);
          if (s.configs) {
            Object.assign(rule.agent_configs, s.configs);
          }
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
      }

      const r = await fetch("/api/alerts/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, rule, enabled: true }),
      }).then((r) => r.json());
      
      if (!r?.ok) throw new Error(r?.detail || "Failed to create");
      await refresh();
      setInitialPrompt(""); // clear prompt after success
    } catch (e: any) {
      setErr(e?.message || "Failed to create");
    }
  };

  const toggle = async (id: number, enabled: boolean) => {
    await fetch(`/api/alerts/toggle`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id, enabled: !enabled }),
    });
    refresh();
  };

  const remove = async (id: number) => {
    await fetch(`/api/alerts/delete`, { 
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id })
    });
    refresh();
  };

  return (
    <div className="h-full flex flex-col gap-3 p-3 overflow-y-auto relative">
      <div className="flex items-center justify-between">
        <div className="text-sm font-semibold text-gray-200">AI Agent Triggers</div>
        <button 
          onClick={() => setShowReportsModal(true)}
          className="flex items-center gap-1.5 px-2 py-1 bg-white/10 hover:bg-white/20 rounded text-xs text-white transition-colors relative"
        >
          <Inbox size={14} />
          <span>AI Reports</span>
          {reports.length > 0 && (
            <span className="absolute -top-1 -right-1 flex h-3 w-3 items-center justify-center rounded-full bg-red-500 text-[8px] font-bold text-white">
              {reports.length}
            </span>
          )}
        </button>
      </div>
      
      {err && <div className="text-xs text-red-400 whitespace-pre-wrap bg-red-500/10 p-2 rounded">{err}</div>}

      {/* CREATE NEW RULE */}
      <div className="border border-white/10 bg-white/5 rounded p-3 space-y-3">
        <div className="text-xs font-medium text-[#00bfa5]">Create New Event Trigger</div>
        
        <select 
          className="w-full h-8 bg-[#0b0f14] border border-white/10 rounded px-2 text-xs text-white" 
          value={alertType} 
          onChange={(e) => setAlertType(e.target.value as any)}
        >
          <option value="raja_sr_touch">RajaSR Zone Touch</option>
          <option value="msb_zigzag_break">MSB / ChoCh Structure Break</option>
          <option value="trend_exhaustion">Trend Exhaustion (Triangle)</option>
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

        <div className="flex flex-col gap-1">
          <span className="text-[11px] text-gray-500">Agent Prompt (Optional)</span>
          <textarea 
            className="w-full h-16 bg-black/30 border border-white/10 rounded p-2 text-xs resize-none" 
            placeholder="e.g. Please analyze if this is a valid setup and draw a box..."
            value={initialPrompt}
            onChange={(e) => setInitialPrompt(e.target.value)}
          />
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

      {/* ACTIVE RULES LIST */}
      <div className="flex-1 min-h-[150px] overflow-y-auto space-y-2">
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
        <div className="text-xs font-medium text-gray-400 mb-2">Event Logs</div>
        <div className="flex-1 overflow-y-auto space-y-2 pr-1">
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
            <button onClick={() => { setShowReportsModal(false); setSelectedReportId(null); }} className="text-gray-400 hover:text-white transition-colors">
              <X size={16} />
            </button>
          </div>
          
          {selectedReportId === null ? (
            <div className="flex-1 overflow-y-auto p-3 space-y-2">
              {reports.length === 0 && (
                <div className="text-xs text-gray-500 text-center py-10">No AI reports generated yet.</div>
              )}
              {reports.map((r) => (
                <div 
                  key={r.id} 
                  onClick={() => setSelectedReportId(r.id)}
                  className="bg-white/5 hover:bg-white/10 border border-white/10 rounded p-3 cursor-pointer transition-colors flex flex-col gap-2"
                >
                  <div className="flex items-center justify-between text-[10px] text-gray-400">
                    <span>{new Date(r.ts * 1000).toLocaleString()}</span>
                    <span className="bg-[#00bfa5]/20 text-[#00bfa5] px-1.5 py-0.5 rounded">{r.alert_name}</span>
                  </div>
                  <div className="text-xs text-gray-200 font-medium line-clamp-2 break-words">
                    {r.report_content.replace(/[#*`]/g, '').slice(0, 100)}...
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="flex-1 flex flex-col overflow-hidden">
              <div className="p-2 border-b border-white/10 shrink-0 flex items-center">
                <button onClick={() => setSelectedReportId(null)} className="text-xs text-[#00bfa5] hover:underline">
                  &larr; Back to Inbox
                </button>
              </div>
              <div className="flex-1 overflow-y-auto p-4">
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
    </div>
  );
}