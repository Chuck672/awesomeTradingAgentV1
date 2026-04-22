"use client";

import React, { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";

type AlertRow = {
  id: number;
  name: string;
  enabled: boolean;
  rule: any;
  created_at: number;
};

type AlertEvent = { id: number; alert_id: number; ts: number; message: string };

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
  const [err, setErr] = useState<string | null>(null);
  const [symbol, setSymbol] = useState(props.symbol || "XAUUSD");
  const [timeframe, setTimeframe] = useState(props.timeframe || "M15");
  const [alertType, setAlertType] = useState<"london_break" | "ai_agent_trigger">("ai_agent_trigger");
  const [volMult, setVolMult] = useState(1.5);
  
  // AI Agent Specific
  const [enableMSB, setEnableMSB] = useState(true);
  const [eventTimeframeMSB, setEventTimeframeMSB] = useState("M15");
  const [enableRajaSR, setEnableRajaSR] = useState(true);
  const [eventTimeframeRajaSR, setEventTimeframeRajaSR] = useState("H1");
  const [tg, setTg] = useState<{ token: string; chat_id: string }>(() => ({ token: "", chat_id: "" }));

  useEffect(() => setTg(loadTelegram()), []);
  useEffect(() => setSymbol(props.symbol || "XAUUSD"), [props.symbol]);
  useEffect(() => setTimeframe(props.timeframe || "M15"), [props.timeframe]);

  const refresh = async () => {
    setErr(null);
    try {
      const a = await fetch("/api/alerts").then((r) => r.json());
      setAlerts(Array.isArray(a?.alerts) ? a.alerts : []);
      const e = await fetch("/api/alerts/events?limit=100").then((r) => r.json());
      setEvents(Array.isArray(e?.events) ? e.events : []);
    } catch (e: any) {
      setErr(e?.message || "加载失败");
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
      let rule: any;
      let name: string;
      
      if (alertType === "london_break") {
        rule = {
          type: "london_break_asia_high_volume",
          symbol,
          timeframe,
          volume_mult: volMult,
          telegram: tg?.token && tg?.chat_id ? { token: tg.token, chat_id: tg.chat_id } : undefined,
        };
        name = `London Break ${symbol} ${timeframe}`;
      } else {
        rule = {
          type: "ai_agent_trigger",
          symbol,
          timeframe,
          enable_msb: enableMSB,
          timeframe_msb: eventTimeframeMSB,
          enable_raja_sr: enableRajaSR,
          timeframe_raja_sr: eventTimeframeRajaSR,
          telegram: tg?.token && tg?.chat_id ? { token: tg.token, chat_id: tg.chat_id } : undefined,
        };
        name = `AI Agent Trigger ${symbol}`;
      }

      const r = await fetch("/api/alerts/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, rule, enabled: true }),
      }).then((r) => r.json());
      if (!r?.ok) throw new Error(r?.detail || "创建失败");
      await refresh();
    } catch (e: any) {
      setErr(e?.message || "创建失败");
    }
  };

  return (
    <div className="h-full flex flex-col gap-3 p-3 overflow-y-auto">
      <div className="text-sm font-semibold text-gray-200">Alerts Engine</div>
      {err && <div className="text-xs text-red-400 whitespace-pre-wrap bg-red-500/10 p-2 rounded">{err}</div>}

      <div className="border border-white/10 bg-white/5 rounded p-3 space-y-3">
        <div className="text-xs font-medium text-[#00bfa5]">Create New Alert</div>
        
        <div className="flex flex-col gap-2">
          <select 
            className="h-8 bg-black/30 border border-white/10 rounded px-2 text-xs text-white" 
            value={alertType} 
            onChange={(e) => setAlertType(e.target.value as any)}
          >
            <option value="ai_agent_trigger">AI Agent System Trigger</option>
            <option value="london_break">London Break AsiaHigh (Legacy)</option>
          </select>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <input className="h-8 bg-black/30 border border-white/10 rounded px-2 text-xs" value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="Symbol (e.g. XAUUSD)" />
          {alertType === "london_break" && (
            <input className="h-8 bg-black/30 border border-white/10 rounded px-2 text-xs" value={timeframe} onChange={(e) => setTimeframe(e.target.value)} placeholder="Timeframe (e.g. M15)" />
          )}
        </div>

        {alertType === "london_break" ? (
          <>
            <div className="grid grid-cols-1 gap-2">
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-400">Volume Multiplier:</span>
                <input className="flex-1 h-8 bg-black/30 border border-white/10 rounded px-2 text-xs" type="number" step="0.1" value={volMult} onChange={(e) => setVolMult(Number(e.target.value))} />
              </div>
            </div>
            <div className="text-[11px] text-gray-500 leading-tight">Triggers when latest bar volume ≥ (volMult × Asian session avg volume)</div>
          </>
        ) : (
          <div className="flex flex-col gap-3 py-1">
            <div className="flex items-center justify-between text-xs text-gray-300">
              <label className="flex items-center gap-1.5">
                <input type="checkbox" checked={enableMSB} onChange={(e) => setEnableMSB(e.target.checked)} />
                MSB Break (BoS/ChoCh)
              </label>
              <div className="flex items-center gap-1">
                <span className="text-gray-500">TF:</span>
                <select className="bg-black/30 border border-white/10 rounded px-1 h-6" value={eventTimeframeMSB} onChange={(e) => setEventTimeframeMSB(e.target.value)}>
                  <option value="M5">M5</option>
                  <option value="M15">M15</option>
                  <option value="H1">H1</option>
                  <option value="H4">H4</option>
                </select>
              </div>
            </div>
            <div className="flex items-center justify-between text-xs text-gray-300">
              <label className="flex items-center gap-1.5">
                <input type="checkbox" checked={enableRajaSR} onChange={(e) => setEnableRajaSR(e.target.checked)} />
                RajaSR Zone Touch
              </label>
              <div className="flex items-center gap-1">
                <span className="text-gray-500">TF:</span>
                <select className="bg-black/30 border border-white/10 rounded px-1 h-6" value={eventTimeframeRajaSR} onChange={(e) => setEventTimeframeRajaSR(e.target.value)}>
                  <option value="M5">M5</option>
                  <option value="M15">M15</option>
                  <option value="H1">H1</option>
                  <option value="H4">H4</option>
                </select>
              </div>
            </div>
          </div>
        )}

        <div className="text-[11px] text-gray-500 pt-1 border-t border-white/10">Notifications (Optional)</div>
        <div className="grid grid-cols-2 gap-2">
          <input
            className="h-8 bg-black/30 border border-white/10 rounded px-2 text-xs"
            value={tg.token}
            onChange={(e) => setTg({ ...tg, token: e.target.value })}
            placeholder="Telegram Bot Token"
          />
          <input
            className="h-8 bg-black/30 border border-white/10 rounded px-2 text-xs"
            value={tg.chat_id}
            onChange={(e) => setTg({ ...tg, chat_id: e.target.value })}
            placeholder="Chat ID"
          />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" className="h-8 px-4 text-xs border-white/10" onClick={refresh}>
            Refresh
          </Button>
          <Button className="h-8 px-4 text-xs bg-[#00bfa5] hover:bg-[#00bfa5]/80 text-black" onClick={create}>
            Create Alert
          </Button>
        </div>
      </div>

      <div className="border border-white/10 rounded p-3 flex-1 overflow-y-auto">
        <div className="text-xs font-medium text-gray-400 mb-3">Active Alerts</div>
        <div className="space-y-3">
          {alerts.map((a) => (
            <div key={a.id} className="bg-white/5 rounded p-2">
              <div className="flex items-center justify-between mb-1">
                <div className="text-[13px] font-medium text-gray-200">{a.name}</div>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    className="h-6 px-2 text-[10px] border-white/10 hover:bg-white/10"
                    onClick={async () => {
                      await fetch("/api/alerts/toggle", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ id: a.id, enabled: !a.enabled }),
                      });
                      refresh();
                    }}
                  >
                    {a.enabled ? "Disable" : "Enable"}
                  </Button>
                  <Button
                    variant="outline"
                    className="h-6 px-2 text-[10px] border-red-500/30 text-red-400 hover:bg-red-500/10"
                    onClick={async () => {
                      await fetch("/api/alerts/delete", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ id: a.id }),
                      });
                      refresh();
                    }}
                  >
                    Delete
                  </Button>
                </div>
              </div>
              <div className="text-[11px] text-gray-400 font-mono overflow-x-auto p-1.5 bg-black/30 rounded">
                {JSON.stringify(a.rule, null, 2)}
              </div>
            </div>
          ))}
          {alerts.length === 0 && <div className="text-xs text-gray-500 text-center py-4">No active alerts</div>}
        </div>
      </div>

      <div className="border border-white/10 rounded p-3 max-h-[220px] overflow-y-auto shrink-0">
        <div className="text-xs font-medium text-gray-400 mb-3">Recent Triggers</div>
        <div className="space-y-2">
          {events.map((e) => (
            <div key={e.id} className="text-xs border-l-2 border-[#00bfa5] bg-white/5 rounded-r p-2">
              <div className="text-[10px] text-gray-500 mb-1">
                #{e.alert_id} · {new Date(e.ts * 1000).toLocaleString()}
              </div>
              <div className="text-gray-300 font-mono">{e.message}</div>
            </div>
          ))}
          {events.length === 0 && <div className="text-xs text-gray-500 text-center py-2">No triggers yet</div>}
        </div>
      </div>
    </div>
  );
}

