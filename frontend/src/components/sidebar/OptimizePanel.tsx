import { getBaseUrl } from "@/lib/api";
"use client";

import React, { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";

type Job = any;

export function OptimizePanel(props: { symbol?: string; timeframe?: string }) {
  const { symbol, timeframe } = props;
  const [running, setRunning] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [fast, setFast] = useState(true);
  const [strategies, setStrategies] = useState<any[]>([]);
  const [strategyId, setStrategyId] = useState<string>("sweep_recover_reversal");
  const [trials, setTrials] = useState<number>(12);
  const [seed, setSeed] = useState<number>(7);
  const [limit, setLimit] = useState<number>(8000);

  const tf = timeframe || "M5";
  const sym = symbol || "XAUUSDz";

  React.useEffect(() => {
    fetch(`${getBaseUrl()}/api/strategies")
      .then((r) => r.json())
      .then((d) => {
        if (d?.ok && Array.isArray(d.strategies)) setStrategies(d.strategies);
      })
      .catch(() => {});
  }, []);

  React.useEffect(() => {
    if (tf === "M15" || tf === "M30") setStrategyId("sweep_detected_reversal");
    else setStrategyId("sweep_recover_reversal");
    setLimit(tf === "M1" ? 5000 : 8000);
  }, [tf]);

  const run = async () => {
    setErr(null);
    setRunning(true);
    setJob(null);
    try {
      const r = await fetch(`${getBaseUrl()}/api/optimize/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: sym,
          timeframe: tf,
          limit,
          trials,
          seed,
          fast,
          strategy_id: strategyId,
        }),
      });
      const data = await r.json();
      if (!data?.ok) throw new Error(data?.detail || "启动失败");
      const jobId = data.job_id;

      for (let i = 0; i < 600; i++) {
        const s = await fetch(`${getBaseUrl()}/api/optimize/status/${jobId}`);
        const js = await s.json();
        const j = js?.job;
        setJob(j);
        if (j?.status === "done" || j?.status === "error") break;
        await new Promise((res) => setTimeout(res, 1000));
      }
    } catch (e: any) {
      setErr(e?.message || "运行失败");
    } finally {
      setRunning(false);
    }
  };

  const summary = job?.result;
  const downloads = useMemo(() => {
    if (!job || job.status !== "done") return null;
    return {
      csv: `/api/optimize/download/${job.id}?format=csv`,
      json: `/api/optimize/download/${job.id}?format=json`,
      zip: `/api/optimize/download/${job.id}?format=zip`,
    };
  }, [job]);

  const best = summary?.best;

  return (
    <div className="h-full flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="text-xs text-gray-400">Optimize (MVP)</div>
        <Button variant="outline" className="h-7 px-2 text-xs" onClick={run} disabled={running || !sym || !tf}>
          {running ? "运行中…" : "运行"}
        </Button>
      </div>

      <div className="text-sm font-semibold">
        {sym} {tf}
      </div>

      <label className="flex items-center gap-2 text-xs text-gray-400">
        <input type="checkbox" checked={fast} onChange={(e) => setFast(e.target.checked)} />
        fast 模式
      </label>

      <div className="flex gap-2">
        <select
          className="h-8 flex-1 bg-transparent border border-white/10 rounded px-2 text-xs"
          value={strategyId}
          onChange={(e) => setStrategyId(e.target.value)}
          title="优化使用的策略"
        >
          {(strategies || []).map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
      </div>

      <div className="grid grid-cols-3 gap-2">
        <label className="text-xs text-gray-400">
          trials
          <input
            className="mt-1 w-full h-8 bg-transparent border border-white/10 rounded px-2 text-xs"
            type="number"
            value={trials}
            onChange={(e) => setTrials(Number(e.target.value))}
          />
        </label>
        <label className="text-xs text-gray-400">
          seed
          <input
            className="mt-1 w-full h-8 bg-transparent border border-white/10 rounded px-2 text-xs"
            type="number"
            value={seed}
            onChange={(e) => setSeed(Number(e.target.value))}
          />
        </label>
        <label className="text-xs text-gray-400">
          limit
          <input
            className="mt-1 w-full h-8 bg-transparent border border-white/10 rounded px-2 text-xs"
            type="number"
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
          />
        </label>
      </div>

      {err && <div className="text-xs text-red-400 whitespace-pre-wrap">{err}</div>}
      {job && job.status === "error" && (
        <div className="text-xs text-red-400 space-y-2">
          <div className="whitespace-pre-wrap">{job.error || job.message || "运行失败"}</div>
          <Button variant="outline" className="h-7 px-2 text-xs" onClick={run} disabled={running}>
            重试
          </Button>
        </div>
      )}
      {job && job.status === "running" && (
        <div className="text-xs text-gray-400">
          进度：{Math.round((job.progress || 0) * 100)}% {job.message || ""}
        </div>
      )}

      {best && (
        <div className="border border-white/10 rounded p-2 space-y-1">
          <div className="text-xs text-gray-400">best</div>
          <div className="text-xs">score: {best.score?.toFixed ? best.score.toFixed(4) : best.score}</div>
          <div className="text-xs">total_return: {(best.total_return * 100).toFixed(2)}%</div>
          <div className="text-xs">max_drawdown: {(best.max_drawdown * 100).toFixed(2)}%</div>
          <div className="text-xs">trades: {best.trades}</div>
          <div className="text-xs">hold_bars: {best.hold_bars}</div>
          <div className="text-xs">
            SL/TP(ATR): {best.atr_stop_mult} / {best.atr_tp_mult}
          </div>
          <div className="text-xs">
            sweep_window: {best.sweep_recover_window_bars} · reclaim_pct: {best.sweep_min_reclaim_pct_of_range} ·
            break_buf: {best.break_buffer_atr_mult}
          </div>
        </div>
      )}

      {downloads && (
        <div className="flex gap-2">
          <a className="text-xs text-emerald-300 underline" href={downloads.csv} target="_blank" rel="noreferrer">
            下载 CSV
          </a>
          <a className="text-xs text-emerald-300 underline" href={downloads.json} target="_blank" rel="noreferrer">
            下载 JSON
          </a>
          <a className="text-xs text-emerald-300 underline" href={downloads.zip} target="_blank" rel="noreferrer">
            下载 ZIP
          </a>
        </div>
      )}

      <div className="text-[11px] text-gray-500 leading-4">
        MVP 优化：随机搜索 sweep 相关 SceneParams + 策略参数，以（收益-回撤惩罚）为目标函数选优。后续可加入 walk-forward / 多目标指标。
      </div>
    </div>
  );
}
