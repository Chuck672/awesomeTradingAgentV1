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
  const [symbol, setSymbol] = useState(props.symbol || "XAUUSDz");
  const [timeframe, setTimeframe] = useState(props.timeframe || "M5");
  const [volMult, setVolMult] = useState(1.5);
  const [tg, setTg] = useState<{ token: string; chat_id: string }>(() => ({ token: "", chat_id: "" }));

  useEffect(() => setTg(loadTelegram()), []);
  useEffect(() => setSymbol(props.symbol || "XAUUSDz"), [props.symbol]);
  useEffect(() => setTimeframe(props.timeframe || "M5"), [props.timeframe]);

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
      const rule = {
        type: "london_break_asia_high_volume",
        symbol,
        timeframe,
        volume_mult: volMult,
        telegram: tg?.token && tg?.chat_id ? { token: tg.token, chat_id: tg.chat_id } : undefined,
      };
      const r = await fetch("/api/alerts/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: `London break AsiaHigh ${symbol} ${timeframe}`, rule, enabled: true }),
      }).then((r) => r.json());
      if (!r?.ok) throw new Error(r?.detail || "创建失败");
      await refresh();
    } catch (e: any) {
      setErr(e?.message || "创建失败");
    }
  };

  return (
    <div className="h-full flex flex-col gap-3">
      <div className="text-xs text-gray-400">告警（MVP：UTC AsiaHigh → London breakout + 成交量放大）</div>
      {err && <div className="text-xs text-red-400 whitespace-pre-wrap">{err}</div>}

      <div className="border border-white/10 rounded p-2 space-y-2">
        <div className="text-xs text-gray-400">新建告警</div>
        <div className="grid grid-cols-3 gap-2">
          <input className="h-8 bg-transparent border border-white/10 rounded px-2 text-xs" value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="symbol" />
          <input className="h-8 bg-transparent border border-white/10 rounded px-2 text-xs" value={timeframe} onChange={(e) => setTimeframe(e.target.value)} placeholder="M5/M15..." />
          <input className="h-8 bg-transparent border border-white/10 rounded px-2 text-xs" type="number" value={volMult} onChange={(e) => setVolMult(Number(e.target.value))} />
        </div>
        <div className="text-[11px] text-gray-500">volume_mult：最新 bar volume ≥ volume_mult × 亚洲盘平均量</div>
        <div className="grid grid-cols-2 gap-2">
          <input
            className="h-8 bg-transparent border border-white/10 rounded px-2 text-xs"
            value={tg.token}
            onChange={(e) => setTg({ ...tg, token: e.target.value })}
            placeholder="Telegram bot token（可选）"
          />
          <input
            className="h-8 bg-transparent border border-white/10 rounded px-2 text-xs"
            value={tg.chat_id}
            onChange={(e) => setTg({ ...tg, chat_id: e.target.value })}
            placeholder="chat_id（可选）"
          />
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="outline" className="h-8 px-3 text-xs" onClick={refresh}>
            刷新
          </Button>
          <Button className="h-8 px-3 text-xs" onClick={create}>
            创建
          </Button>
        </div>
      </div>

      <div className="border border-white/10 rounded p-2 flex-1 overflow-auto">
        <div className="text-xs text-gray-400 mb-2">告警列表</div>
        <div className="space-y-2">
          {alerts.map((a) => (
            <div key={a.id} className="border border-white/10 rounded p-2">
              <div className="flex items-center justify-between">
                <div className="text-xs">{a.name}</div>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    className="h-7 px-2 text-xs"
                    onClick={async () => {
                      await fetch("/api/alerts/toggle", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ id: a.id, enabled: !a.enabled }),
                      });
                      refresh();
                    }}
                  >
                    {a.enabled ? "禁用" : "启用"}
                  </Button>
                  <Button
                    variant="outline"
                    className="h-7 px-2 text-xs"
                    onClick={async () => {
                      await fetch("/api/alerts/delete", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ id: a.id }),
                      });
                      refresh();
                    }}
                  >
                    删除
                  </Button>
                </div>
              </div>
              <div className="text-[11px] text-gray-500 mt-1 whitespace-pre-wrap">{JSON.stringify(a.rule)}</div>
            </div>
          ))}
          {alerts.length === 0 && <div className="text-xs text-gray-500">暂无告警</div>}
        </div>
      </div>

      <div className="border border-white/10 rounded p-2 max-h-[220px] overflow-auto">
        <div className="text-xs text-gray-400 mb-2">最近触发</div>
        <div className="space-y-2">
          {events.map((e) => (
            <div key={e.id} className="text-xs whitespace-pre-wrap border border-white/10 rounded p-2">
              <div className="text-[11px] text-gray-500 mb-1">
                #{e.alert_id} · {new Date(e.ts * 1000).toISOString()}
              </div>
              {e.message}
            </div>
          ))}
          {events.length === 0 && <div className="text-xs text-gray-500">暂无触发记录</div>}
        </div>
      </div>
    </div>
  );
}

