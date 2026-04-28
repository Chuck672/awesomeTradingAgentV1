"use client";

import React, { useEffect, useMemo, useState } from "react";
import { getBaseUrl } from "@/lib/api";
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, AreaChart, Area, BarChart, Bar, Cell } from "recharts";
import { Settings, ChartLine } from "lucide-react";

type DailyAgg = {
  day: string;
  pl: number;
  trades: number;
  winning_trades: number;
  gross_profit: number;
  gross_loss: number;
  fees: number;
};

type DayDetail = {
  ticket: number;
  time: number;
  symbol: string;
  type: number;
  entry: number;
  volume: number;
  price: number;
  profit: number;
  commission: number;
  swap: number;
  pl: number;
  position_id: number;
  comment: string;
};

type CalendarEvent = {
  id: string;
  title: string;
  impact: string;
  timestamp: number;
  time_str: string;
  date_group: string;
  previous: string;
  forecast: string;
  actual: string;
};

type TradingStatsResponse = {
  ok: boolean;
  account_id: string;
  current: {
    from: string;
    to: string;
    summary: any;
    daily_pl: Array<{ day: string; pl: number }>;
    equity_curve: Array<{ day: string; equity: number; drawdown: number }>;
    by_symbol: Array<{ symbol: string; pl: number; trades: number; winning_trades: number; win_rate: number }>;
    by_weekday: Array<{ weekday: number; pl: number; trades: number; win_rate: number }>;
    by_session: Array<{ session: string; pl: number; trades: number; win_rate: number }>;
  };
  previous: {
    from: string;
    to: string;
    summary: any;
  } | null;
  delta: any;
};

async function readJsonOrThrow(r: Response) {
  const j = await r.json().catch(() => null);
  if (!r.ok) {
    const msg = (j && (j.detail || j.message)) || `${r.status} ${r.statusText}`;
    throw new Error(String(msg));
  }
  return j;
}

function dayStr(d: Date) {
  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(d.getUTCDate()).padStart(2, "0");
  return `${y}-${m}-${dd}`;
}

function startOfWeekUtc(d: Date) {
  const x = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));
  const wd = x.getUTCDay();
  const offset = wd === 0 ? -6 : 1 - wd;
  x.setUTCDate(x.getUTCDate() + offset);
  return x;
}

function addDaysUtc(d: Date, n: number) {
  const x = new Date(d.getTime());
  x.setUTCDate(x.getUTCDate() + n);
  return x;
}

function clamp(n: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, n));
}

function plColor(pl: number) {
  if (pl > 0) return "bg-emerald-500/20 border-emerald-500/30 text-emerald-200";
  if (pl < 0) return "bg-red-500/20 border-red-500/30 text-red-200";
  return "bg-white/5 border-white/10 text-gray-200";
}

function fmtMoney(v: number) {
  const s = (Number.isFinite(v) ? v : 0).toFixed(2);
  return (v >= 0 ? "+" : "") + s;
}

function loadAgentConfigs(): any {
  try {
    const raw = localStorage.getItem("awesome_trading_agent_settings_v3");
    if (!raw) return {};
    const s = JSON.parse(raw);
    return s?.configs || {};
  } catch {
    return {};
  }
}

function loadAgentSettingsRaw(): any {
  try {
    const raw = localStorage.getItem("awesome_trading_agent_settings_v3");
    if (!raw) return { configs: {} };
    const s = JSON.parse(raw);
    if (s && typeof s === "object") return s;
    return { configs: {} };
  } catch {
    return { configs: {} };
  }
}

function saveAgentSettingsRaw(next: any) {
  try {
    localStorage.setItem("awesome_trading_agent_settings_v3", JSON.stringify(next));
  } catch {}
}

function Modal(props: { open: boolean; title: string; onClose: () => void; children: React.ReactNode }) {
  if (!props.open) return null;
  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="w-full max-w-3xl rounded-xl border border-gray-200 dark:border-white/10 bg-white dark:bg-[#0b0f14] text-gray-800 dark:text-gray-200 shadow-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-200 dark:border-white/10 flex items-center justify-between">
          <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">{props.title}</div>
          <button
            className="w-8 h-8 rounded-lg border border-gray-200 dark:border-white/10 hover:bg-black/5 dark:hover:bg-white/5 flex items-center justify-center"
            onClick={props.onClose}
            title="关闭"
            type="button"
          >
            ×
          </button>
        </div>
        <div className="p-4 max-h-[80vh] overflow-auto custom-scrollbar">{props.children}</div>
      </div>
    </div>
  );
}

export function TradingDashboardPanel(props: { symbol?: string; timeframe?: string }) {
  const baseUrl = useMemo(() => getBaseUrl(), []);

  const [mode, setMode] = useState<"week" | "month" | "year">("month");
  const [anchor, setAnchor] = useState(() => new Date());

  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [days, setDays] = useState<DailyAgg[]>([]);
  const [accountId, setAccountId] = useState<string>("");

  const [selectedDay, setSelectedDay] = useState<string | null>(null);
  const [dayDetail, setDayDetail] = useState<DayDetail[]>([]);
  const [daySummary, setDaySummary] = useState<any>(null);
  const [calendarEvents, setCalendarEvents] = useState<CalendarEvent[]>([]);

  const [coachBusy, setCoachBusy] = useState(false);
  const [coachText, setCoachText] = useState<string>("");
  const [coachRules, setCoachRules] = useState<any>(null);
  const [coachOpen, setCoachOpen] = useState(false);
  const [coachSettingsOpen, setCoachSettingsOpen] = useState(false);
  const [coachApiKey, setCoachApiKey] = useState<string>(() => {
    const s = loadAgentSettingsRaw();
    return String(s?.configs?.analyzer?.api_key || "");
  });

  const [insightsOpen, setInsightsOpen] = useState(false);
  const [statsBusy, setStatsBusy] = useState(false);
  const [stats, setStats] = useState<TradingStatsResponse | null>(null);
  const [insightsTab, setInsightsTab] = useState<"equity" | "dist" | "symbol" | "heatmap">("equity");

  const range = useMemo(() => {
    if (mode === "year") {
      const y = anchor.getUTCFullYear();
      const from = new Date(Date.UTC(y, 0, 1));
      const to = new Date(Date.UTC(y, 11, 31));
      return { from, to };
    }
    if (mode === "week") {
      const from = startOfWeekUtc(anchor);
      const to = addDaysUtc(from, 6);
      return { from, to };
    }
    const y = anchor.getUTCFullYear();
    const m = anchor.getUTCMonth();
    const from = new Date(Date.UTC(y, m, 1));
    const to = new Date(Date.UTC(y, m + 1, 0));
    return { from, to };
  }, [mode, anchor]);

  const fromDay = useMemo(() => dayStr(range.from), [range.from]);
  const toDay = useMemo(() => dayStr(range.to), [range.to]);

  const daysMap = useMemo(() => {
    const m: Record<string, DailyAgg> = {};
    for (const d of days) m[d.day] = d;
    return m;
  }, [days]);

  const monthGrid = useMemo(() => {
    if (mode !== "month") return [];
    const y = anchor.getUTCFullYear();
    const m = anchor.getUTCMonth();
    const first = new Date(Date.UTC(y, m, 1));
    const last = new Date(Date.UTC(y, m + 1, 0));
    const firstWd = first.getUTCDay();
    const padBefore = firstWd === 0 ? 6 : firstWd - 1;
    const totalDays = last.getUTCDate();
    const cells: Array<{ day: number | null; dayStr?: string }> = [];
    for (let i = 0; i < padBefore; i++) cells.push({ day: null });
    for (let d = 1; d <= totalDays; d++) {
      const dd = new Date(Date.UTC(y, m, d));
      cells.push({ day: d, dayStr: dayStr(dd) });
    }
    while (cells.length % 7 !== 0) cells.push({ day: null });
    return cells;
  }, [mode, anchor]);

  const summary = useMemo(() => {
    const totalPl = days.reduce((a, x) => a + (Number(x.pl) || 0), 0);
    const totalTrades = days.reduce((a, x) => a + (Number(x.trades) || 0), 0);
    const wins = days.reduce((a, x) => a + (Number(x.winning_trades) || 0), 0);
    const gp = days.reduce((a, x) => a + (Number(x.gross_profit) || 0), 0);
    const gl = days.reduce((a, x) => a + (Number(x.gross_loss) || 0), 0);
    const fees = days.reduce((a, x) => a + (Number(x.fees) || 0), 0);
    const winRate = totalTrades > 0 ? (wins / totalTrades) * 100 : 0;
    const pf = gl > 0 ? gp / gl : gp > 0 ? gp : 0;
    return { totalPl, totalTrades, wins, winRate, pf, fees };
  }, [days]);

  const fetchDaily = async () => {
    setErr(null);
    setLoading(true);
    try {
      const r = await fetch(`${baseUrl}/api/trading/daily?from_day=${encodeURIComponent(fromDay)}&to_day=${encodeURIComponent(toDay)}`).then(readJsonOrThrow);
      setAccountId(String(r?.account_id || ""));
      setDays(Array.isArray(r?.days) ? r.days : []);
    } catch (e: any) {
      setErr(e?.message || "Failed to load trading data");
      setDays([]);
    } finally {
      setLoading(false);
    }
  };

  const fetchCalendar = async () => {
    try {
      const r = await fetch(`${baseUrl}/api/calendar?_t=${Date.now()}`, { cache: "no-store" }).then(readJsonOrThrow);
      if (r?.ok) setCalendarEvents(Array.isArray(r?.events) ? r.events : []);
      else setCalendarEvents([]);
    } catch {
      setCalendarEvents([]);
    }
  };

  useEffect(() => {
    fetchDaily();
  }, [baseUrl, fromDay, toDay]);

  useEffect(() => {
    fetchCalendar();
  }, [baseUrl]);

  const fetchDay = async (day: string) => {
    setErr(null);
    setSelectedDay(day);
    setDayDetail([]);
    setDaySummary(null);
    try {
      const r = await fetch(`${baseUrl}/api/trading/day?day=${encodeURIComponent(day)}`).then(readJsonOrThrow);
      setDayDetail(Array.isArray(r?.deals) ? r.deals : []);
      setDaySummary(r?.daily || null);
    } catch (e: any) {
      setErr(e?.message || "Failed to load day detail");
    }
  };

  const runCoach = async () => {
    setCoachBusy(true);
    setCoachText("");
    setCoachRules(null);
    try {
      const payload = { from_day: fromDay, to_day: toDay, configs: loadAgentConfigs() };
      const r = await fetch(`${baseUrl}/api/trading/coach`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }).then(readJsonOrThrow);
      setCoachText(String(r?.coach || ""));
      setCoachRules(r?.rules || null);
    } catch (e: any) {
      setCoachText(e?.message || "Coach failed");
    } finally {
      setCoachBusy(false);
    }
  };

  const fetchStats = async () => {
    setStatsBusy(true);
    try {
      const r = await fetch(`${baseUrl}/api/trading/stats?from_day=${encodeURIComponent(fromDay)}&to_day=${encodeURIComponent(toDay)}`).then(readJsonOrThrow);
      setStats(r as TradingStatsResponse);
    } catch (e: any) {
      setErr(e?.message || "Failed to load stats");
      setStats(null);
    } finally {
      setStatsBusy(false);
    }
  };

  const dayEvents = useMemo(() => {
    if (!selectedDay) return [];
    const start = Date.parse(selectedDay + "T00:00:00Z") / 1000;
    const end = Date.parse(selectedDay + "T23:59:59Z") / 1000;
    return calendarEvents.filter((x) => Number(x.timestamp || 0) >= start && Number(x.timestamp || 0) <= end);
  }, [calendarEvents, selectedDay]);

  const move = (dir: -1 | 1) => {
    if (mode === "year") {
      const x = new Date(anchor.getTime());
      x.setUTCFullYear(x.getUTCFullYear() + dir);
      setAnchor(x);
      return;
    }
    if (mode === "week") {
      setAnchor(addDaysUtc(anchor, dir * 7));
      return;
    }
    const x = new Date(anchor.getTime());
    x.setUTCMonth(x.getUTCMonth() + dir);
    setAnchor(x);
  };

  return (
    <div className="h-full flex flex-col gap-3 overflow-hidden text-gray-800 dark:text-gray-200">
      <div className="bg-black/20 border border-white/10 rounded-lg p-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <div className="text-sm font-semibold">Trading Dashboard</div>
            <div className="text-[11px] text-gray-500">{accountId || ""}</div>
          </div>
          <div className="flex items-center gap-2">
            <button
              className="text-xs px-2 py-1 rounded bg-white/10 hover:bg-white/15 border border-white/10 text-gray-200"
              type="button"
              onClick={async () => {
                setInsightsOpen(true);
                if (!stats) await fetchStats();
              }}
              disabled={statsBusy}
              title="查看图表与对比"
            >
              <span className="inline-flex items-center gap-1">
                <ChartLine size={14} />
                Insights
              </span>
            </button>
            <button
              className="text-xs px-2 py-1 rounded bg-white/10 hover:bg-white/15 border border-white/10 text-gray-200"
              type="button"
              onClick={fetchDaily}
              disabled={loading}
            >
              {loading ? "Loading..." : "Refresh"}
            </button>
          </div>
        </div>

        <div className="mt-3 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <button className="w-8 h-8 rounded border border-white/10 hover:bg-white/5" type="button" onClick={() => move(-1)}>
              ←
            </button>
            <button className="w-8 h-8 rounded border border-white/10 hover:bg-white/5" type="button" onClick={() => move(1)}>
              →
            </button>
            <select
              className="h-8 bg-[#0b0f14] border border-white/10 rounded px-2 text-xs text-white"
              value={mode}
              onChange={(e) => setMode(e.target.value as any)}
            >
              <option value="week">Week</option>
              <option value="month">Month</option>
              <option value="year">Year</option>
            </select>
            <div className="text-[11px] text-gray-400">
              {fromDay} → {toDay}
            </div>
          </div>
          {err && <div className="text-[11px] text-red-400">{err}</div>}
        </div>

        <div className="mt-3 grid grid-cols-3 gap-2">
          <div className="border border-white/10 rounded bg-black/10 p-2">
            <div className="text-[10px] text-gray-500">Net P/L</div>
            <div className={`text-sm font-mono ${summary.totalPl >= 0 ? "text-emerald-300" : "text-red-300"}`}>{fmtMoney(summary.totalPl)}</div>
          </div>
          <div className="border border-white/10 rounded bg-black/10 p-2">
            <div className="text-[10px] text-gray-500">Win Rate</div>
            <div className="text-sm font-mono">{summary.winRate.toFixed(1)}%</div>
          </div>
          <div className="border border-white/10 rounded bg-black/10 p-2">
            <div className="text-[10px] text-gray-500">Profit Factor</div>
            <div className="text-sm font-mono">{Number.isFinite(summary.pf) ? summary.pf.toFixed(2) : "0.00"}</div>
          </div>
          <div className="border border-white/10 rounded bg-black/10 p-2">
            <div className="text-[10px] text-gray-500">Trades</div>
            <div className="text-sm font-mono">{summary.totalTrades}</div>
          </div>
          <div className="border border-white/10 rounded bg-black/10 p-2">
            <div className="text-[10px] text-gray-500">Fees</div>
            <div className="text-sm font-mono">{fmtMoney(summary.fees)}</div>
          </div>
          <div className="border border-white/10 rounded bg-black/10 p-2">
            <div className="text-[10px] text-gray-500">Compare</div>
            <div className="text-[11px] text-gray-400">Phase1: month/week/year</div>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-auto custom-scrollbar bg-black/20 border border-white/10 rounded-lg p-3">
        {mode === "month" && (
          <div className="grid grid-cols-7 gap-2">
            {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((x) => (
              <div key={x} className="text-[10px] text-gray-500 px-1">
                {x}
              </div>
            ))}
            {monthGrid.map((c, idx) => {
              if (!c.day || !c.dayStr) {
                return <div key={idx} className="h-16 rounded border border-white/5 bg-black/10" />;
              }
              const d = daysMap[c.dayStr];
              const pl = d ? Number(d.pl || 0) : 0;
              const trades = d ? Number(d.trades || 0) : 0;
              return (
                <button
                  key={idx}
                  type="button"
                  className={`h-16 rounded border text-left px-2 py-1 hover:bg-white/5 ${plColor(pl)}`}
                  onClick={() => fetchDay(c.dayStr!)}
                >
                  <div className="flex items-center justify-between">
                    <div className="text-[11px] text-gray-200">{c.day}</div>
                    <div className="text-[10px] text-gray-400">{trades ? `${trades}t` : ""}</div>
                  </div>
                  <div className={`text-[11px] font-mono ${pl >= 0 ? "text-emerald-200" : "text-red-200"}`}>{fmtMoney(pl)}</div>
                </button>
              );
            })}
          </div>
        )}

        {mode !== "month" && (
          <div className="flex flex-col gap-2">
            {Array.from({ length: mode === "week" ? 7 : 12 }).map((_, i) => {
              const d = mode === "week" ? addDaysUtc(range.from, i) : new Date(Date.UTC(anchor.getUTCFullYear(), i, 1));
              const label = mode === "week" ? dayStr(d) : `${anchor.getUTCFullYear()}-${String(i + 1).padStart(2, "0")}`;
              const pl = mode === "week"
                ? Number(daysMap[label]?.pl || 0)
                : days.filter((x) => x.day.startsWith(label)).reduce((a, x) => a + Number(x.pl || 0), 0);
              return (
                <div key={label} className="flex items-center justify-between border border-white/10 rounded p-2 bg-black/10">
                  <div className="text-[11px] text-gray-300">{label}</div>
                  <div className={`text-[11px] font-mono ${pl >= 0 ? "text-emerald-200" : "text-red-200"}`}>{fmtMoney(pl)}</div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="bg-black/20 border border-white/10 rounded-lg p-3">
        <div className="flex items-center justify-between">
          <div className="text-xs text-gray-400">Coach (Rules + AI)</div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="w-8 h-8 rounded border border-white/10 hover:bg-white/5 flex items-center justify-center text-gray-200"
              onClick={() => setCoachSettingsOpen(true)}
              title="Coach 设置"
            >
              <Settings size={16} />
            </button>
            <button
              type="button"
              className="text-xs px-2 py-1 rounded bg-emerald-500/20 border border-emerald-500/30 text-emerald-300 hover:bg-emerald-500/25 disabled:opacity-50"
              onClick={async () => {
                await runCoach();
                setCoachOpen(true);
              }}
              disabled={coachBusy}
            >
              {coachBusy ? "Generating..." : "Generate"}
            </button>
          </div>
        </div>
        {coachText ? (
          <div className="mt-2 text-[11px] text-gray-300">
            {String(coachText).split("\n").filter(Boolean)[0] || "Coach report generated."}
            <button className="ml-2 text-[11px] text-emerald-300 hover:underline" type="button" onClick={() => setCoachOpen(true)}>
              查看全文
            </button>
          </div>
        ) : (
          <div className="mt-2 text-[11px] text-gray-500">点击 Generate 生成规则诊断 + AI 教练建议（生成后在弹窗中查看）。</div>
        )}
      </div>

      <Modal open={!!selectedDay} title={selectedDay ? `Daily Detail • ${selectedDay}` : "Daily Detail"} onClose={() => setSelectedDay(null)}>
        {daySummary && (
          <div className="grid grid-cols-3 gap-2 mb-4">
            <div className="border border-white/10 rounded bg-black/10 p-2">
              <div className="text-[10px] text-gray-500">P/L</div>
              <div className={`text-sm font-mono ${Number(daySummary.pl || 0) >= 0 ? "text-emerald-300" : "text-red-300"}`}>{fmtMoney(Number(daySummary.pl || 0))}</div>
            </div>
            <div className="border border-white/10 rounded bg-black/10 p-2">
              <div className="text-[10px] text-gray-500">Trades</div>
              <div className="text-sm font-mono">{Number(daySummary.trades || 0)}</div>
            </div>
            <div className="border border-white/10 rounded bg-black/10 p-2">
              <div className="text-[10px] text-gray-500">Fees</div>
              <div className="text-sm font-mono">{fmtMoney(Number(daySummary.fees || 0))}</div>
            </div>
          </div>
        )}

        {dayEvents.length > 0 && (
          <div className="mb-4 border border-white/10 rounded bg-black/10 p-2">
            <div className="text-xs text-gray-400 mb-2">Economic Calendar (USD)</div>
            <div className="flex flex-col gap-2">
              {dayEvents.slice(0, 12).map((ev) => (
                <div key={ev.id} className="border border-white/10 rounded p-2 bg-black/20">
                  <div className="flex items-center justify-between">
                    <div className="text-[11px] text-gray-200">{ev.title}</div>
                    <div className="text-[10px] text-gray-500">{ev.time_str}</div>
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-[10px] mt-1 text-gray-400">
                    <div>Prev: {ev.previous || "-"}</div>
                    <div>Fcst: {ev.forecast || "-"}</div>
                    <div>Act: {ev.actual || "-"}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="border border-white/10 rounded bg-black/10 overflow-hidden">
          <div className="px-2 py-2 text-xs text-gray-400 border-b border-white/10">Deals</div>
          {dayDetail.length === 0 ? (
            <div className="p-3 text-[11px] text-gray-500">No deals.</div>
          ) : (
            <div className="max-h-[40vh] overflow-auto custom-scrollbar">
              <table className="w-full text-[11px]">
                <thead className="sticky top-0 bg-white dark:bg-[#0b0f14]">
                  <tr className="text-gray-400 border-b border-white/10">
                    <th className="text-left p-2">Time</th>
                    <th className="text-left p-2">Symbol</th>
                    <th className="text-right p-2">Vol</th>
                    <th className="text-right p-2">Price</th>
                    <th className="text-right p-2">P/L</th>
                  </tr>
                </thead>
                <tbody>
                  {dayDetail.map((d) => {
                    const t = new Date(Number(d.time || 0) * 1000);
                    const ts = `${String(t.getUTCHours()).padStart(2, "0")}:${String(t.getUTCMinutes()).padStart(2, "0")}`;
                    const pl = Number(d.pl || 0);
                    return (
                      <tr key={d.ticket} className="border-b border-white/5">
                        <td className="p-2 text-gray-300 font-mono">{ts}</td>
                        <td className="p-2 text-gray-200">{d.symbol}</td>
                        <td className="p-2 text-right text-gray-300 font-mono">{Number(d.volume || 0).toFixed(2)}</td>
                        <td className="p-2 text-right text-gray-300 font-mono">{Number(d.price || 0).toFixed(3)}</td>
                        <td className={`p-2 text-right font-mono ${pl >= 0 ? "text-emerald-300" : "text-red-300"}`}>{fmtMoney(pl)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </Modal>

      <Modal open={coachOpen} title="Coach Report" onClose={() => setCoachOpen(false)}>
        {coachText ? (
          <div className="text-sm leading-6 whitespace-pre-wrap">{coachText}</div>
        ) : (
          <div className="text-sm text-gray-500">No coach report.</div>
        )}
        {coachRules && (
          <details className="mt-4">
            <summary className="cursor-pointer text-xs text-gray-500 dark:text-gray-400">Rules JSON</summary>
            <pre className="mt-2 text-[11px] leading-4 bg-black/5 dark:bg-black/30 border border-gray-200 dark:border-white/10 rounded p-2 overflow-auto custom-scrollbar whitespace-pre-wrap text-gray-800 dark:text-gray-200">
              {JSON.stringify(coachRules, null, 2)}
            </pre>
          </details>
        )}
      </Modal>

      <Modal open={coachSettingsOpen} title="Coach Settings" onClose={() => setCoachSettingsOpen(false)}>
        <div className="text-xs text-gray-500 dark:text-gray-400 mb-2">
          保存后会写入本地设置（awesome_trading_agent_settings_v3），仅影响本机。
        </div>
        <div className="flex flex-col gap-2">
          <label className="text-xs text-gray-700 dark:text-gray-300">
            API Key
            <input
              type="password"
              className="mt-1 w-full px-2 py-2 rounded bg-gray-50 dark:bg-black/40 border border-gray-200 dark:border-white/10 text-gray-800 dark:text-white"
              value={coachApiKey}
              onChange={(e) => setCoachApiKey(e.target.value)}
              placeholder="sk-..."
            />
          </label>
          <div className="flex items-center gap-2 mt-2">
            <button
              type="button"
              className="px-3 py-2 rounded bg-emerald-500/20 border border-emerald-500/30 text-emerald-300 hover:bg-emerald-500/25"
              onClick={() => {
                const s = loadAgentSettingsRaw();
                const next = { ...(s || {}) };
                const cfgs = { ...(next.configs || {}) };
                const analyzer = { ...(cfgs.analyzer || {}) };
                analyzer.api_key = coachApiKey || "";
                cfgs.analyzer = analyzer;
                next.configs = cfgs;
                saveAgentSettingsRaw(next);
                setCoachSettingsOpen(false);
              }}
            >
              Save
            </button>
            <button
              type="button"
              className="px-3 py-2 rounded bg-gray-100 hover:bg-gray-200 dark:bg-white/10 dark:hover:bg-white/15 border border-gray-200 dark:border-white/10 text-gray-700 dark:text-gray-200"
              onClick={() => setCoachSettingsOpen(false)}
            >
              Cancel
            </button>
          </div>
        </div>
      </Modal>

      <Modal open={insightsOpen} title="Insights" onClose={() => setInsightsOpen(false)}>
        <div className="flex items-center justify-between gap-2 mb-3">
          <div className="flex items-center gap-2">
            <button
              type="button"
              className={`px-2 py-1 rounded border text-xs ${insightsTab === "equity" ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-500 dark:text-emerald-300" : "border-gray-200 dark:border-white/10 bg-transparent text-gray-600 dark:text-gray-300 hover:bg-black/5 dark:hover:bg-white/5"}`}
              onClick={() => setInsightsTab("equity")}
            >
              Equity
            </button>
            <button
              type="button"
              className={`px-2 py-1 rounded border text-xs ${insightsTab === "dist" ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-500 dark:text-emerald-300" : "border-gray-200 dark:border-white/10 bg-transparent text-gray-600 dark:text-gray-300 hover:bg-black/5 dark:hover:bg-white/5"}`}
              onClick={() => setInsightsTab("dist")}
            >
              Distribution
            </button>
            <button
              type="button"
              className={`px-2 py-1 rounded border text-xs ${insightsTab === "symbol" ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-500 dark:text-emerald-300" : "border-gray-200 dark:border-white/10 bg-transparent text-gray-600 dark:text-gray-300 hover:bg-black/5 dark:hover:bg-white/5"}`}
              onClick={() => setInsightsTab("symbol")}
            >
              Symbols
            </button>
            <button
              type="button"
              className={`px-2 py-1 rounded border text-xs ${insightsTab === "heatmap" ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-500 dark:text-emerald-300" : "border-gray-200 dark:border-white/10 bg-transparent text-gray-600 dark:text-gray-300 hover:bg-black/5 dark:hover:bg-white/5"}`}
              onClick={() => setInsightsTab("heatmap")}
            >
              Heatmap
            </button>
          </div>
          <button
            type="button"
            className="text-xs px-2 py-1 rounded bg-white/10 hover:bg-white/15 border border-white/10 text-gray-200 disabled:opacity-50"
            onClick={fetchStats}
            disabled={statsBusy}
          >
            {statsBusy ? "Loading..." : "Refresh"}
          </button>
        </div>

        {!stats && (
          <div className="text-sm text-gray-500">
            {statsBusy ? "Loading..." : "No stats. Click Refresh."}
          </div>
        )}

        {stats && (
          <div className="flex flex-col gap-4">
            <div className="grid grid-cols-3 gap-2">
              <div className="border border-gray-200 dark:border-white/10 rounded bg-gray-50 dark:bg-black/10 p-2">
                <div className="text-[10px] text-gray-500">Current P/L</div>
                <div className={`text-sm font-mono ${Number(stats.current?.summary?.total_pl || 0) >= 0 ? "text-emerald-400" : "text-red-400"}`}>{fmtMoney(Number(stats.current?.summary?.total_pl || 0))}</div>
              </div>
              <div className="border border-gray-200 dark:border-white/10 rounded bg-gray-50 dark:bg-black/10 p-2">
                <div className="text-[10px] text-gray-500">Prev P/L</div>
                <div className="text-sm font-mono">{stats.previous ? fmtMoney(Number(stats.previous?.summary?.total_pl || 0)) : "-"}</div>
              </div>
              <div className="border border-gray-200 dark:border-white/10 rounded bg-gray-50 dark:bg-black/10 p-2">
                <div className="text-[10px] text-gray-500">Δ P/L</div>
                <div className={`text-sm font-mono ${Number(stats.delta?.total_pl || 0) >= 0 ? "text-emerald-400" : "text-red-400"}`}>{stats.previous ? fmtMoney(Number(stats.delta?.total_pl || 0)) : "-"}</div>
              </div>
            </div>

            {insightsTab === "equity" && (
              <div className="border border-gray-200 dark:border-white/10 rounded bg-gray-50 dark:bg-black/10 p-3">
                <div className="text-xs text-gray-500 mb-2">Equity & Drawdown</div>
                <div className="h-52">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={stats.current.equity_curve || []} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                      <XAxis dataKey="day" hide />
                      <YAxis hide />
                      <Tooltip contentStyle={{ backgroundColor: "var(--color-popover)", border: "1px solid var(--color-border)" }} labelStyle={{ color: "var(--color-foreground)" }} />
                      <Line type="monotone" dataKey="equity" stroke="var(--color-foreground)" strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
                <div className="h-36 mt-3">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={stats.current.equity_curve || []} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                      <XAxis dataKey="day" hide />
                      <YAxis hide />
                      <Tooltip contentStyle={{ backgroundColor: "var(--color-popover)", border: "1px solid var(--color-border)" }} />
                      <Area type="monotone" dataKey="drawdown" stroke="var(--color-destructive)" fill="var(--color-destructive)" fillOpacity={0.12} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}

            {insightsTab === "dist" && (
              <div className="border border-gray-200 dark:border-white/10 rounded bg-gray-50 dark:bg-black/10 p-3">
                <div className="text-xs text-gray-500 mb-2">Daily P/L Distribution</div>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={stats.current.daily_pl || []}
                      margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
                    >
                      <XAxis dataKey="day" hide />
                      <YAxis hide />
                      <Tooltip contentStyle={{ backgroundColor: "var(--color-popover)", border: "1px solid var(--color-border)" }} />
                      <Bar dataKey="pl" barSize={10}>
                        {(stats.current.daily_pl || []).map((x, i) => (
                          <Cell key={i} fill={Number((x as any).pl || 0) >= 0 ? "rgba(16,185,129,0.75)" : "rgba(239,68,68,0.75)"} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}

            {insightsTab === "symbol" && (
              <div className="border border-gray-200 dark:border-white/10 rounded bg-gray-50 dark:bg-black/10 p-3">
                <div className="text-xs text-gray-500 mb-2">By Symbol</div>
                <div className="overflow-auto custom-scrollbar max-h-[55vh]">
                  <table className="w-full text-[11px]">
                    <thead className="sticky top-0 bg-white dark:bg-[#0b0f14]">
                      <tr className="text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-white/10">
                        <th className="text-left p-2">Symbol</th>
                        <th className="text-right p-2">Trades</th>
                        <th className="text-right p-2">Win%</th>
                        <th className="text-right p-2">P/L</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(stats.current.by_symbol || [])
                        .slice()
                        .sort((a, b) => Math.abs(b.pl) - Math.abs(a.pl))
                        .slice(0, 30)
                        .map((x) => (
                          <tr key={x.symbol} className="border-b border-gray-100 dark:border-white/5">
                            <td className="p-2 text-gray-800 dark:text-gray-200">{x.symbol}</td>
                            <td className="p-2 text-right font-mono text-gray-700 dark:text-gray-300">{x.trades}</td>
                            <td className="p-2 text-right font-mono text-gray-700 dark:text-gray-300">{Number(x.win_rate || 0).toFixed(1)}%</td>
                            <td className={`p-2 text-right font-mono ${x.pl >= 0 ? "text-emerald-400" : "text-red-400"}`}>{fmtMoney(x.pl)}</td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {insightsTab === "heatmap" && (
              <div className="border border-gray-200 dark:border-white/10 rounded bg-gray-50 dark:bg-black/10 p-3">
                <div className="text-xs text-gray-500 mb-2">Weekday / Session</div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="border border-gray-200 dark:border-white/10 rounded p-2 bg-white/40 dark:bg-black/10">
                    <div className="text-[11px] text-gray-500 mb-2">Weekday</div>
                    <div className="grid grid-cols-7 gap-2">
                      {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((lab, i) => {
                        const it = (stats.current.by_weekday || []).find((x) => Number(x.weekday) === i);
                        const pl = Number(it?.pl || 0);
                        const pct = clamp(Math.abs(pl) / 500, 0, 1);
                        const bg = pl >= 0 ? `rgba(16,185,129,${0.12 + pct * 0.35})` : `rgba(239,68,68,${0.12 + pct * 0.35})`;
                        return (
                          <div key={lab} className="rounded border border-gray-200 dark:border-white/10 p-2" style={{ background: bg }}>
                            <div className="text-[10px] text-gray-500">{lab}</div>
                            <div className={`text-[11px] font-mono ${pl >= 0 ? "text-emerald-500 dark:text-emerald-300" : "text-red-500 dark:text-red-300"}`}>{fmtMoney(pl)}</div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                  <div className="border border-gray-200 dark:border-white/10 rounded p-2 bg-white/40 dark:bg-black/10">
                    <div className="text-[11px] text-gray-500 mb-2">Session</div>
                    <div className="flex flex-col gap-2">
                      {(stats.current.by_session || []).map((x) => (
                        <div key={x.session} className="flex items-center justify-between border border-gray-200 dark:border-white/10 rounded p-2 bg-white/30 dark:bg-black/10">
                          <div className="text-[11px] text-gray-700 dark:text-gray-200">{x.session}</div>
                          <div className={`text-[11px] font-mono ${Number(x.pl || 0) >= 0 ? "text-emerald-500 dark:text-emerald-300" : "text-red-500 dark:text-red-300"}`}>{fmtMoney(Number(x.pl || 0))}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}
