"use client";
import { getBaseUrl } from "@/lib/api";

import React, { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";

type ScanJob = any;

type AiSettings = { base_url: string; model: string; api_key: string };
const KEY = "awesome_chart_ai_settings_v1";
function loadSettings(): AiSettings | null {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function ScanPanel(props: { onExecuteActions: (actions: any[]) => Promise<string[]> | string[] }) {
  const [source, setSource] = useState<"active" | "watchlist" | "both">("both");
  const [timeframesText, setTimeframesText] = useState("M30");
  const [lookbackHours, setLookbackHours] = useState(24);
  const [job, setJob] = useState<ScanJob | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [watchlist, setWatchlist] = useState<string[]>([]);
  const [newSym, setNewSym] = useState("");
  const [strategyPrompt, setStrategyPrompt] = useState("寻找：波动放大 + 区间突破（过去 24 小时）");
  const [strategyJob, setStrategyJob] = useState<any | null>(null);
  const [strategyRunning, setStrategyRunning] = useState(false);
  const [breakoutPrompt, setBreakoutPrompt] = useState("找：收盘价突破近48根最高/最低（MVP）");
  const [breakoutParse, setBreakoutParse] = useState<any | null>(null);
  const [breakoutJob, setBreakoutJob] = useState<any | null>(null);
  const [breakoutRunning, setBreakoutRunning] = useState(false);
  const [settings, setSettings] = useState<AiSettings | null>(null);
  const [strategies, setStrategies] = useState<Array<{ id: string; name: string }>>([]);
  const [strategyId, setStrategyId] = useState<string>("reclaim_continuation");
  const [btJobId, setBtJobId] = useState<string | null>(null);
  const [btJob, setBtJob] = useState<any | null>(null);
  const [riskOverride, setRiskOverride] = useState<{ hold_bars: number; atr_stop_mult: number; atr_tp_mult: number } | null>(null);
  const [rrOverride, setRrOverride] = useState<{ retest_window_bars: number; reclaim_window_bars: number } | null>(null);

  const timeframes = useMemo(() => timeframesText.split(",").map((s) => s.trim()).filter(Boolean), [timeframesText]);

  const refreshWatchlist = async () => {
    try {
      const r = await fetch(`${getBaseUrl()}/api/watchlist`);
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(String(j?.detail || `HTTP ${r.status}`));
      setWatchlist(Array.isArray(j?.symbols) ? j.symbols : []);
    } catch (e: any) {
      // 不阻塞页面，但给出可见提示，避免“点了没反应”
      setErr(e?.message || "Watchlist 获取失败");
      setWatchlist([]);
    }
  };

  useEffect(() => {
    refreshWatchlist();
    setSettings(loadSettings());
    fetch(`${getBaseUrl()}/api/strategies`)
      .then((r) => r.json())
      .then((j) => {
        const arr = Array.isArray(j?.strategies) ? j.strategies : [];
        setStrategies(arr.map((x: any) => ({ id: String(x.id), name: String(x.name) })));
      })
      .catch(() => {});
  }, []);

  const run = async () => {
    setErr(null);
    setJob(null);
    setJobId(null);
    try {
      const r = await fetch(`${getBaseUrl()}/api/scan/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source, timeframes, lookback_hours: lookbackHours }),
      }).then((r) => r.json());
      if (!r?.job_id) throw new Error(r?.detail || "启动扫描失败");
      setJobId(r.job_id);
    } catch (e: any) {
      setErr(e?.message || "启动失败");
    }
  };

  useEffect(() => {
    if (!jobId) return;
    let alive = true;
    const t = setInterval(async () => {
      try {
        const r = await fetch(`${getBaseUrl()}/api/scan/status/${jobId}`).then((r) => r.json());
        if (!alive) return;
        setJob(r?.job || null);
        if (r?.job?.status && r.job.status !== "running") {
          clearInterval(t);
        }
      } catch {}
    }, 1000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [jobId]);

  useEffect(() => {
    if (!btJobId) return;
    let alive = true;
    const t = setInterval(async () => {
      try {
        const r = await fetch(`${getBaseUrl()}/api/research/strategy-backtest/status/${btJobId}`).then((r) => r.json());
        if (!alive) return;
        setBtJob(r?.job || null);
        if (r?.job?.status && r.job.status !== "running") {
          clearInterval(t);
        }
      } catch {}
    }, 1200);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [btJobId]);

  return (
    <div className="h-full flex flex-col gap-3">
      <div className="text-xs text-gray-400">扫描（MVP：过去 N 小时波动率上升 + 区间突破）</div>
      {err && <div className="text-xs text-red-400 whitespace-pre-wrap">{err}</div>}

      <div className="border border-white/10 rounded p-2 space-y-2">
        <div className="text-xs text-gray-400">Watchlist</div>
        <div className="flex gap-2">
          <input className="flex-1 h-8 bg-transparent border border-white/10 rounded px-2 text-xs" value={newSym} onChange={(e) => setNewSym(e.target.value)} placeholder="例如：EURUSD" />
          <Button
            className="h-8 px-3 text-xs"
            onClick={async () => {
              if (!newSym.trim()) return;
              try {
                setErr(null);
                const sym = newSym.trim();
                const r = await fetch(`${getBaseUrl()}/api/watchlist/add`, {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ symbol: sym }),
                });
                const j = await r.json().catch(() => ({}));
                if (!r.ok || j?.ok === false) throw new Error(String(j?.detail || `添加失败：${sym}`));
                setNewSym("");
                await refreshWatchlist();
              } catch (e: any) {
                setErr(e?.message || "添加失败");
              }
            }}
          >
            添加
          </Button>
        </div>
        <div className="flex flex-wrap gap-2">
          {watchlist.map((s) => (
            <button
              key={s}
              className="text-xs px-2 py-1 rounded border border-white/10 hover:bg-white/5"
              onClick={async () => {
                try {
                  setErr(null);
                  const r = await fetch(`${getBaseUrl()}/api/watchlist/remove`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ symbol: s }),
                  });
                  const j = await r.json().catch(() => ({}));
                  if (!r.ok || j?.ok === false) throw new Error(String(j?.detail || `删除失败：${s}`));
                  await refreshWatchlist();
                } catch (e: any) {
                  setErr(e?.message || "删除失败");
                }
              }}
              title="点击删除"
            >
              {s}
            </button>
          ))}
          {watchlist.length === 0 && <div className="text-xs text-gray-500">暂无</div>}
        </div>
      </div>

      <div className="border border-white/10 rounded p-2 space-y-2">
        <div className="text-xs text-gray-400">扫描参数</div>
        <div className="grid grid-cols-3 gap-2">
          <select className="h-8 bg-transparent border border-white/10 rounded px-2 text-xs" value={source} onChange={(e) => setSource(e.target.value as any)}>
            <option value="both">both</option>
            <option value="active">active</option>
            <option value="watchlist">watchlist</option>
          </select>
          <input className="h-8 bg-transparent border border-white/10 rounded px-2 text-xs" value={timeframesText} onChange={(e) => setTimeframesText(e.target.value)} placeholder="M5,M30" />
          <input className="h-8 bg-transparent border border-white/10 rounded px-2 text-xs" type="number" value={lookbackHours} onChange={(e) => setLookbackHours(Number(e.target.value))} />
        </div>
        <div className="flex justify-end">
          <Button className="h-8 px-3 text-xs" onClick={run} disabled={!!jobId && job?.status === "running"}>
            开始扫描
          </Button>
        </div>
      </div>

      <div className="border border-white/10 rounded p-2 space-y-2">
        <div className="text-xs text-gray-400">策略寻机（AI Prompt → 扫描候选 → 落图）</div>
        <div className="text-[11px] text-gray-500">会用你的 AI Settings 调一次模型，把策略 prompt 编译成“可执行条件”，再在本地数据上扫。</div>
        <textarea
          className="w-full h-20 bg-transparent border border-white/10 rounded p-2 text-xs outline-none focus:border-emerald-400"
          value={strategyPrompt}
          onChange={(e) => setStrategyPrompt(e.target.value)}
          placeholder="例如：找伦敦盘上破亚洲盘高点，并且成交量放大"
        />
        <div className="flex justify-end gap-2">
          <select
            className="h-8 bg-transparent border border-white/10 rounded px-2 text-xs"
            value={strategyId}
            onChange={(e) => setStrategyId(e.target.value)}
            title="回测策略（用于候选一键回测）"
          >
            {(strategies.length ? strategies : [{ id: "reclaim_continuation", name: "Reclaim Continuation" }]).map((s) => (
              <option key={s.id} value={s.id}>
                回测：{s.name}
              </option>
            ))}
          </select>
          <Button
            variant="outline"
            className="h-8 px-3 text-xs"
            onClick={async () => {
              setErr(null);
              setStrategyJob(null);
              if (!settings?.api_key || !settings?.model || !settings?.base_url) {
                setErr("请先在 AI 面板里配置好 Base URL / Model / API Key");
                return;
              }
              setStrategyRunning(true);
              try {
                const r = await fetch(`${getBaseUrl()}/api/ai/strategy-scan`, {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({
                    settings,
                    prompt: strategyPrompt,
                    source,
                    timeframes,
                    lookback_hours: lookbackHours,
                  }),
                }).then((r) => r.json());
                if (!r?.ok) throw new Error(r?.detail || "策略扫描失败");
                setStrategyJob(r);
                setRiskOverride(null);
                setRrOverride(null);
              } catch (e: any) {
                setErr(e?.message || "策略扫描失败");
              } finally {
                setStrategyRunning(false);
              }
            }}
            disabled={strategyRunning}
          >
            策略扫描
          </Button>
        </div>
        {strategyJob?.dsl && (
          <div className="text-[11px] text-gray-500 whitespace-pre-wrap border border-white/10 rounded p-2">
            dsl：{JSON.stringify(strategyJob.dsl, null, 2)}
          </div>
        )}

        {strategyJob?.dsl?.conditions?.risk && (
          <div className="border border-white/10 rounded p-2">
            <div className="text-xs text-gray-400 mb-2">风险模板（可选覆盖）</div>
            <div className="grid grid-cols-3 gap-2">
              <input
                className="h-8 bg-transparent border border-white/10 rounded px-2 text-xs"
                type="number"
                value={riskOverride?.hold_bars ?? Number(strategyJob.dsl.conditions.risk.hold_bars || 0)}
                onChange={(e) =>
                  setRiskOverride((v) => ({
                    hold_bars: Number(e.target.value),
                    atr_stop_mult: v?.atr_stop_mult ?? Number(strategyJob.dsl.conditions.risk.atr_stop_mult || 2.0),
                    atr_tp_mult: v?.atr_tp_mult ?? Number(strategyJob.dsl.conditions.risk.atr_tp_mult || 3.0),
                  }))
                }
                placeholder="hold_bars"
              />
              <input
                className="h-8 bg-transparent border border-white/10 rounded px-2 text-xs"
                type="number"
                step="0.1"
                value={riskOverride?.atr_stop_mult ?? Number(strategyJob.dsl.conditions.risk.atr_stop_mult || 2.0)}
                onChange={(e) =>
                  setRiskOverride((v) => ({
                    hold_bars: v?.hold_bars ?? Number(strategyJob.dsl.conditions.risk.hold_bars || 0),
                    atr_stop_mult: Number(e.target.value),
                    atr_tp_mult: v?.atr_tp_mult ?? Number(strategyJob.dsl.conditions.risk.atr_tp_mult || 3.0),
                  }))
                }
                placeholder="atr_stop_mult"
              />
              <input
                className="h-8 bg-transparent border border-white/10 rounded px-2 text-xs"
                type="number"
                step="0.1"
                value={riskOverride?.atr_tp_mult ?? Number(strategyJob.dsl.conditions.risk.atr_tp_mult || 3.0)}
                onChange={(e) =>
                  setRiskOverride((v) => ({
                    hold_bars: v?.hold_bars ?? Number(strategyJob.dsl.conditions.risk.hold_bars || 0),
                    atr_stop_mult: v?.atr_stop_mult ?? Number(strategyJob.dsl.conditions.risk.atr_stop_mult || 2.0),
                    atr_tp_mult: Number(e.target.value),
                  }))
                }
                placeholder="atr_tp_mult"
              />
            </div>
          </div>
        )}

        {strategyJob?.dsl?.conditions?.retest_reclaim && (
          <div className="border border-white/10 rounded p-2">
            <div className="text-xs text-gray-400 mb-2">Retest/Reclaim 参数（可选覆盖）</div>
            <div className="grid grid-cols-2 gap-2">
              <input
                className="h-8 bg-transparent border border-white/10 rounded px-2 text-xs"
                type="number"
                value={rrOverride?.retest_window_bars ?? Number(strategyJob.dsl.conditions.retest_reclaim.retest_window_bars || 16)}
                onChange={(e) =>
                  setRrOverride((v) => ({
                    retest_window_bars: Number(e.target.value),
                    reclaim_window_bars: v?.reclaim_window_bars ?? Number(strategyJob.dsl.conditions.retest_reclaim.reclaim_window_bars || 8),
                  }))
                }
                placeholder="retest_window_bars"
              />
              <input
                className="h-8 bg-transparent border border-white/10 rounded px-2 text-xs"
                type="number"
                value={rrOverride?.reclaim_window_bars ?? Number(strategyJob.dsl.conditions.retest_reclaim.reclaim_window_bars || 8)}
                onChange={(e) =>
                  setRrOverride((v) => ({
                    retest_window_bars: v?.retest_window_bars ?? Number(strategyJob.dsl.conditions.retest_reclaim.retest_window_bars || 16),
                    reclaim_window_bars: Number(e.target.value),
                  }))
                }
                placeholder="reclaim_window_bars"
              />
            </div>
          </div>
        )}
        {Array.isArray(strategyJob?.items) && (
          <div className="space-y-2">
            {strategyJob.items.map((it: any, idx: number) => (
              <div key={idx} className="border border-white/10 rounded p-2 text-xs">
                <div className="flex items-center justify-between">
                  <div>
                    {it.symbol} {it.timeframe} · score {Number(it.score || 0).toFixed(2)}
                  </div>
                  <div className="flex gap-2">
                    <Button
                      className="h-7 px-2 text-xs"
                      onClick={async () => {
                        const actions: any[] = [
                          { type: "chart_set_symbol", symbol: it.symbol },
                          { type: "chart_set_timeframe", timeframe: it.timeframe },
                          { type: "chart_set_range", days: 2 },
                        ];
                        if (it.trigger_time) actions.push({ type: "chart_scroll_to_time", time: it.trigger_time });
                        if (Array.isArray(it.draw_objects) && it.draw_objects.length) actions.push({ type: "chart_draw", objects: it.draw_objects });
                        await props.onExecuteActions(actions);
                      }}
                    >
                      落图
                    </Button>
                    <Button
                      variant="outline"
                      className="h-7 px-2 text-xs"
                      onClick={async () => {
                        setErr(null);
                        setBtJobId(null);
                        setBtJob(null);
                        try {
                          const rsk = it?.risk || {};
                          const risk = {
                            hold_bars: riskOverride?.hold_bars ?? Number(rsk.hold_bars ?? 0),
                            atr_stop_mult: riskOverride?.atr_stop_mult ?? Number(rsk.atr_stop_mult ?? 2.0),
                            atr_tp_mult: riskOverride?.atr_tp_mult ?? Number(rsk.atr_tp_mult ?? 3.0),
                          };
                          const ep0 = (it?.engine_params && typeof it.engine_params === "object") ? it.engine_params : {};
                          const ep = {
                            ...ep0,
                            ...(rrOverride ? rrOverride : {}),
                          };
                          // 清理 null/undefined
                          Object.keys(ep).forEach((k) => (ep[k] == null ? delete ep[k] : null));
                          const r = await fetch(`${getBaseUrl()}/api/research/strategy-backtest/run`, {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({
                              symbol: it.symbol,
                              timeframe: it.timeframe,
                              strategy_id: strategyId,
                              fast: true,
                              limit: 8000,
                              hold_bars: risk.hold_bars,
                              atr_stop_mult: risk.atr_stop_mult,
                              atr_tp_mult: risk.atr_tp_mult,
                              engine_params: ep,
                            }),
                          }).then((r) => r.json());
                          if (!r?.ok) throw new Error(r?.detail || "回测启动失败");
                          setBtJobId(r.job_id);
                        } catch (e: any) {
                          setErr(e?.message || "回测启动失败");
                        }
                      }}
                    >
                      回测
                    </Button>
                  </div>
                </div>
                <div className="text-[11px] text-gray-500 mt-1 whitespace-pre-wrap">{it.reason || ""}</div>
              </div>
            ))}
            {strategyJob.items.length === 0 && <div className="text-xs text-gray-500">无候选</div>}
          </div>
        )}

        {btJobId && (
          <div className="border border-white/10 rounded p-2">
            <div className="text-xs text-gray-400 mb-1">回测任务</div>
            <div className="text-[11px] text-gray-500 mb-2">job: {btJobId} · {btJob?.status || "running"} · {Math.round(((btJob?.progress || 0) as number) * 100)}%</div>
            {btJob?.status === "done" && btJob?.result && (
              <div className="text-xs whitespace-pre-wrap">
                trades {btJob.result.trades} · winrate {(btJob.result.winrate * 100).toFixed(1)}% · pf {btJob.result.profit_factor ?? "-"} ·
                ret {(btJob.result.total_return * 100).toFixed(2)}% · mdd {(btJob.result.max_drawdown * 100).toFixed(2)}%
              </div>
            )}
          </div>
        )}
      </div>

      <div className="border border-white/10 rounded p-2 space-y-2">
        <div className="text-xs text-gray-400">突破扫描（线路B：StrategySpec → DSL → EvidencePack）</div>
        <div className="text-[11px] text-gray-500">
          MVP：固定突破窗口 48 根、TopN=20，不依赖 LLM（更快更稳定），输出 StrategySpec/DSL/EvidencePack 便于后续升级多Agent。
        </div>
        <textarea
          className="w-full h-16 bg-transparent border border-white/10 rounded p-2 text-xs outline-none focus:border-emerald-400"
          value={breakoutPrompt}
          onChange={(e) => setBreakoutPrompt(e.target.value)}
          placeholder="例如：找收盘价上破近48根最高点（多头）"
        />
        <div className="flex justify-end">
          <Button
            className="h-8 px-3 text-xs"
            onClick={async () => {
              setErr(null);
              setBreakoutParse(null);
              setBreakoutJob(null);
              setBreakoutRunning(true);
              try {
                const p = await fetch(`${getBaseUrl()}/api/strategy/parse`, {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({
                    prompt: breakoutPrompt,
                    source,
                    timeframes,
                    lookback_hours: lookbackHours,
                  }),
                }).then((r) => r.json());
                if (!p?.ok) throw new Error(p?.detail || "解析失败");
                setBreakoutParse(p);
                if (p?.parse_meta?.status !== "ok" || !p?.strategy_spec) {
                  const qs = Array.isArray(p?.parse_meta?.open_questions) ? p.parse_meta.open_questions : [];
                  const msg =
                    p?.parse_meta?.status === "unsupported"
                      ? "当前 MVP 仅支持突破类策略。"
                      : qs.length
                        ? `需要澄清：${qs.map((x: any) => x.question).join("；")}`
                        : "策略暂不可执行（请调整描述）";
                  throw new Error(msg);
                }
                const r = await fetch(`${getBaseUrl()}/api/strategy/scan`, {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ strategy_spec: p.strategy_spec }),
                }).then((r) => r.json());
                if (!r?.ok) throw new Error(r?.detail || "扫描失败");
                setBreakoutJob(r);
              } catch (e: any) {
                setErr(e?.message || "突破扫描失败");
              } finally {
                setBreakoutRunning(false);
              }
            }}
            disabled={breakoutRunning}
          >
            {breakoutRunning ? "扫描中…" : "突破扫描"}
          </Button>
        </div>

        {(breakoutParse?.parse_meta || breakoutJob) && (
          <div className="text-[11px] text-gray-500">
            状态：
            {breakoutRunning
              ? "运行中"
              : breakoutJob
                ? `完成（候选 ${Number(breakoutJob?.count || (breakoutJob?.items?.length ?? 0))}）`
                : String(breakoutParse?.parse_meta?.status || "unknown")}
            {breakoutParse?.runtime?.symbols_count != null ? ` · symbols=${breakoutParse.runtime.symbols_count}` : ""}
          </div>
        )}

        {breakoutParse?.strategy_spec && (
          <div className="border border-white/10 rounded p-2">
            <div className="text-[11px] text-gray-500 mb-1">StrategySpec</div>
            <pre className="text-[11px] text-gray-400 whitespace-pre-wrap max-h-48 overflow-auto">
              {JSON.stringify(breakoutParse.strategy_spec, null, 2)}
            </pre>
          </div>
        )}
        {breakoutJob?.dsl_text && (
          <div className="border border-white/10 rounded p-2">
            <div className="text-[11px] text-gray-500 mb-1">DSL</div>
            <pre className="text-[11px] text-gray-400 whitespace-pre-wrap max-h-40 overflow-auto">{breakoutJob.dsl_text}</pre>
          </div>
        )}
        {Array.isArray(breakoutJob?.items) && (
          <div className="space-y-2">
            {breakoutJob.items.map((it: any, idx: number) => (
              <div key={idx} className="border border-white/10 rounded p-2 text-xs">
                <div className="flex items-center justify-between">
                  <div>
                    {it.symbol} {it.timeframe} · score {Number(it.score || 0).toFixed(2)}
                  </div>
                  <Button
                    className="h-7 px-2 text-xs"
                    onClick={async () => {
                      const actions: any[] = [
                        { type: "chart_set_symbol", symbol: it.symbol },
                        { type: "chart_set_timeframe", timeframe: it.timeframe },
                        { type: "chart_set_range", days: 3 },
                      ];
                      if (it.trigger_time) actions.push({ type: "chart_scroll_to_time", time: it.trigger_time });
                      if (Array.isArray(it.draw_objects) && it.draw_objects.length) actions.push({ type: "chart_draw", objects: it.draw_objects });
                      await props.onExecuteActions(actions);
                    }}
                  >
                    落图
                  </Button>
                </div>
                <div className="text-[11px] text-gray-500 mt-1 whitespace-pre-wrap">{it.reason || ""}</div>
              </div>
            ))}
            {breakoutJob.items.length === 0 && <div className="text-xs text-gray-500">无候选</div>}
          </div>
        )}
      </div>

      <div className="border border-white/10 rounded p-2 flex-1 overflow-auto">
        <div className="text-xs text-gray-400 mb-2">结果</div>
        {jobId && (
          <div className="text-[11px] text-gray-500 mb-2">
            job: {jobId} · {job?.status || "-"} · {Math.round(((job?.progress || 0) as number) * 100)}% · {job?.message || ""}
          </div>
        )}
        {job?.status === "done" && Array.isArray(job?.result?.items) && (
          <div className="space-y-2">
            {job.result.items.map((it: any, idx: number) => (
              <div key={idx} className="border border-white/10 rounded p-2 text-xs">
                <div className="flex items-center justify-between">
                  <div>
                    {it.symbol} {it.timeframe} · breakout {it.breakout}
                  </div>
                  <div className="text-[11px] text-gray-500">vol×{(it.vol_ratio || 0).toFixed(2)}</div>
                </div>
                <div className="text-[11px] text-gray-500 mt-1">
                  close {it.last_close?.toFixed?.(3)} · prior_high {it.prior_high?.toFixed?.(3)} · prior_low {it.prior_low?.toFixed?.(3)}
                </div>
              </div>
            ))}
            {job.result.items.length === 0 && <div className="text-xs text-gray-500">无命中</div>}
          </div>
        )}
        {!jobId && <div className="text-xs text-gray-500">点击“开始扫描”</div>}
      </div>
    </div>
  );
}
