"use client";

import React, { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";

type Job = any;

function EquitySparkline(props: { values: number[] }) {
  const { values } = props;
  if (!values || values.length < 2) return null;
  const w = 320;
  const h = 56;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pts = values.map((v, i) => {
    const x = (i / (values.length - 1)) * w;
    const y = h - ((v - min) / span) * h;
    return [x, y] as const;
  });
  const d = pts.map((p, i) => `${i === 0 ? "M" : "L"} ${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(" ");
  const up = values[values.length - 1] >= values[0];
  return (
    <svg width="100%" viewBox={`0 0 ${w} ${h}`} className="block">
      <path d={d} fill="none" stroke={up ? "#34d399" : "#f87171"} strokeWidth="2" />
    </svg>
  );
}

export function BacktestPanel(props: {
  symbol?: string;
  timeframe?: string;
  onJumpToTime?: (t: number) => void;
  onReplayAtTime?: (t: number) => void;
  onSetTradeMarkers?: (markers: any[]) => void;
  onSetBacktestPositions?: (trades: any[]) => void;
  onSetTimeframe?: (tf: string) => void;
  onClearBacktestPositions?: () => void;
}) {
  const {
    symbol,
    timeframe,
    onJumpToTime,
    onReplayAtTime,
    onSetTradeMarkers,
    onSetBacktestPositions,
    onSetTimeframe,
    onClearBacktestPositions,
  } = props;
  const [running, setRunning] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [report, setReport] = useState<any | null>(null);
  const [strategies, setStrategies] = useState<any[]>([]);
  const [strategyId, setStrategyId] = useState<string>("sweep_recover_reversal");
  const [customStrategy, setCustomStrategy] = useState<string>("");
  const [selectedTf, setSelectedTf] = useState<string>(timeframe || "M5");
  const [fast, setFast] = useState(true);
  const [limit, setLimit] = useState<number>(8000);
  const [holdBars, setHoldBars] = useState<number>(30);
  const [atrStop, setAtrStop] = useState<number>(2.0);
  const [atrTp, setAtrTp] = useState<number>(3.0);

  const tf = timeframe || "M5";
  const sym = symbol || "XAUUSDz";

  // 拉取策略列表
  React.useEffect(() => {
    fetch("/api/strategies")
      .then((r) => r.json())
      .then((d) => {
        if (d?.ok && Array.isArray(d.strategies)) setStrategies(d.strategies);
      })
      .catch(() => {});
  }, []);

  React.useEffect(() => {
    // 默认策略：高周期更容易出现 sweep_detected，而 sweep_recover 在 M15/M30 上可能 0 trades
    if (strategyId === "custom") return;
    if (selectedTf === "M15" || selectedTf === "M30") {
      if (strategyId === "sweep_recover_reversal") setStrategyId("sweep_detected_reversal");
    }
  }, [selectedTf]);

  // 根据 timeframe 更新默认 limit
  React.useEffect(() => {
    const t = selectedTf || tf;
    setLimit(t === "M1" ? 5000 : 8000);
  }, [selectedTf, tf]);

  // 根据策略默认参数更新 hold/SL/TP（仅非 custom）
  React.useEffect(() => {
    if (strategyId === "custom") return;
    const s = (strategies || []).find((x) => x.id === strategyId);
    const dp = s?.default_params;
    if (dp) {
      if (dp.hold_bars != null) setHoldBars(Number(dp.hold_bars));
      if (dp.atr_stop_mult != null) setAtrStop(Number(dp.atr_stop_mult));
      if (dp.atr_tp_mult != null) setAtrTp(Number(dp.atr_tp_mult));
    }
  }, [strategyId, strategies]);

  const run = async () => {
    setErr(null);
    setRunning(true);
    setJob(null);
    setReport(null);
    try {
      // 如果用户选择的周期与当前图表不同，先切换图表周期，避免标记/回放对不上
      if (selectedTf && selectedTf !== tf) onSetTimeframe?.(selectedTf);

      let strategy_spec: any = undefined;
      if (strategyId === "custom") {
        if (!customStrategy.trim()) throw new Error("自定义策略为空（请输入 JSON）");
        try {
          strategy_spec = JSON.parse(customStrategy);
        } catch (e) {
          throw new Error("自定义策略 JSON 解析失败");
        }
      }

      const r = await fetch("/api/research/strategy-backtest/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: sym,
          timeframe: selectedTf || tf,
          strategy_id: strategyId === "custom" ? "sweep_recover_reversal" : strategyId,
          strategy_spec,
          fast,
          limit,
          hold_bars: holdBars,
          atr_stop_mult: atrStop,
          atr_tp_mult: atrTp,
        }),
      });
      const data = await r.json();
      if (!data?.ok) throw new Error(data?.detail || "启动失败");
      const jobId = data.job_id;

      for (let i = 0; i < 240; i++) {
        const s = await fetch(`/api/research/strategy-backtest/status/${jobId}`);
        const js = await s.json();
        const j = js?.job;
        setJob(j);
        if (j?.status === "done" || j?.status === "error") break;
        await new Promise((res) => setTimeout(res, 500));
      }

      // done => 拉 report.json 用于可视化（equity/trades）
      const st = await fetch(`/api/research/strategy-backtest/status/${jobId}`);
      const stJson = await st.json();
      const j = stJson?.job;
      if (j?.status === "done") {
        const rep = await fetch(`/api/research/strategy-backtest/download/${jobId}?file=json`).then((x) => x.json());
        setReport(rep);

        // 设置图表 markers（仅在当前图表上）
        const trades = rep?.trades || [];
        onSetBacktestPositions?.(trades);
        if (trades.length > 0) {
          // 自动跳到最近一笔，避免“画了但不在可视区”造成误解
          onJumpToTime?.(trades[trades.length - 1].entry_time);
        }
        const markers = trades
          .slice(-400)
          .flatMap((t: any) => {
            const dir = t.dir;
            const entry = {
              time: t.entry_time,
              position: dir === "LONG" ? "belowBar" : "aboveBar",
              color: dir === "LONG" ? "#34d399" : "#f87171",
              shape: dir === "LONG" ? "arrowUp" : "arrowDown",
              text: "IN",
            };
            const exit = {
              time: t.exit_time,
              position: dir === "LONG" ? "aboveBar" : "belowBar",
              color: t.pnl_pct > 0 ? "#34d399" : "#f87171",
              shape: "circle",
              text: "OUT",
            };
            return [entry, exit];
          });
        onSetTradeMarkers?.(markers);
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
      json: `/api/research/strategy-backtest/download/${job.id}?file=json`,
      trades: `/api/research/strategy-backtest/download/${job.id}?file=trades_csv`,
      equity: `/api/research/strategy-backtest/download/${job.id}?file=equity_csv`,
      zip: `/api/research/strategy-backtest/download/${job.id}?file=zip`,
    };
  }, [job]);

  const trades = report?.trades || [];
  const equity = report?.equity || [];

  return (
    <div className="h-full flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="text-xs text-gray-400">Backtest · Strategy (MVP)</div>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            className="h-7 px-2 text-xs border border-white/10"
            onClick={() => onClearBacktestPositions?.()}
            disabled={running}
            title="仅清除回测生成的三线盒子（bt-）与 IN/OUT 标记"
          >
            清除回测标记
          </Button>
          <Button variant="outline" className="h-7 px-2 text-xs" onClick={run} disabled={running || !sym || !tf}>
            {running ? "运行中…" : "运行"}
          </Button>
        </div>
      </div>

      <div className="text-sm font-semibold">
        {sym} {selectedTf || tf}
      </div>

      <label className="flex items-center gap-2 text-xs text-gray-400">
        <input type="checkbox" checked={fast} onChange={(e) => setFast(e.target.checked)} />
        fast 模式
      </label>

      <div className="grid grid-cols-2 gap-2">
        <label className="text-xs text-gray-400">
          limit
          <input
            className="mt-1 w-full h-8 bg-transparent border border-white/10 rounded px-2 text-xs"
            type="number"
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
          />
        </label>
        <label className="text-xs text-gray-400">
          hold_bars（0=不超时）
          <input
            className="mt-1 w-full h-8 bg-transparent border border-white/10 rounded px-2 text-xs"
            type="number"
            value={holdBars}
            onChange={(e) => setHoldBars(Number(e.target.value))}
          />
        </label>
        <label className="text-xs text-gray-400">
          atr_stop_mult
          <input
            className="mt-1 w-full h-8 bg-transparent border border-white/10 rounded px-2 text-xs"
            type="number"
            step="0.1"
            value={atrStop}
            onChange={(e) => setAtrStop(Number(e.target.value))}
          />
        </label>
        <label className="text-xs text-gray-400">
          atr_tp_mult
          <input
            className="mt-1 w-full h-8 bg-transparent border border-white/10 rounded px-2 text-xs"
            type="number"
            step="0.1"
            value={atrTp}
            onChange={(e) => setAtrTp(Number(e.target.value))}
          />
        </label>
      </div>

      <div className="flex gap-2">
        <select
          className="h-8 flex-1 bg-transparent border border-white/10 rounded px-2 text-xs"
          value={selectedTf}
          onChange={(e) => setSelectedTf(e.target.value)}
          title="回测周期"
        >
          {["M1", "M5", "M15", "M30"].map((x) => (
            <option key={x} value={x}>
              {x}
            </option>
          ))}
        </select>

        <select
          className="h-8 flex-[1.4] bg-transparent border border-white/10 rounded px-2 text-xs"
          value={strategyId}
          onChange={(e) => setStrategyId(e.target.value)}
          title="策略选择"
        >
          {(strategies || []).map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
          <option value="custom">Custom(JSON)</option>
        </select>
      </div>

      {strategyId === "custom" && (
        <textarea
          className="w-full h-[120px] bg-transparent border border-white/10 rounded p-2 text-[11px] font-mono"
          value={customStrategy}
          onChange={(e) => setCustomStrategy(e.target.value)}
          placeholder={`{\n  \"name\": \"MyStrategy\",\n  \"long_event_ids\": [\"reclaim_struct_high_confirmed\"],\n  \"short_event_ids\": [\"reclaim_struct_low_confirmed\"],\n  \"default_params\": {\"hold_bars\": 40, \"atr_stop_mult\": 2.0, \"atr_tp_mult\": 3.0},\n  \"default_engine_params\": {\"retest_window_bars\": 16, \"reclaim_window_bars\": 8}\n}`}
        />
      )}

      {err && <div className="text-xs text-red-400 whitespace-pre-wrap">{err}</div>}
      {job && job.status === "error" && (
        <div className="text-xs text-red-400 space-y-2">
          <div className="whitespace-pre-wrap">{job.error || job.message || "回测失败"}</div>
          <Button variant="outline" className="h-7 px-2 text-xs" onClick={run} disabled={running}>
            重试
          </Button>
        </div>
      )}
      {job && job.status === "running" && (
        <div className="text-xs text-gray-400 space-y-1">
          <div>进度：{Math.round((job.progress || 0) * 100)}%</div>
          {job.message && <div className="text-[11px] text-gray-500">{job.message}</div>}
        </div>
      )}

      {summary && (
        <div className="border border-white/10 rounded p-2 space-y-1">
          <div className="text-xs text-gray-400">summary</div>
          <div className="text-xs">trades: {summary.trades}</div>
          <div className="text-xs">winrate: {(summary.winrate * 100).toFixed(1)}%</div>
          <div className="text-xs">
            total_return: {(summary.total_return * 100).toFixed(2)}% · max_dd: {(summary.max_drawdown * 100).toFixed(2)}%
          </div>
          <div className="text-xs">profit_factor: {summary.profit_factor?.toFixed ? summary.profit_factor.toFixed(2) : "-"}</div>
        </div>
      )}

      {equity.length > 1 && (
        <div className="border border-white/10 rounded p-2">
          <div className="text-xs text-gray-400 mb-1">equity</div>
          <EquitySparkline values={equity.slice(Math.max(0, equity.length - 300))} />
        </div>
      )}

      {trades.length > 0 && (
        <div className="border border-white/10 rounded p-2">
          <div className="text-xs text-gray-400 mb-2">trades（点击跳转 / 回放）</div>
          <div className="max-h-[240px] overflow-auto space-y-1">
            {trades.slice(-60).reverse().map((t: any, idx: number) => (
              <div key={idx} className="flex items-center justify-between gap-2 text-xs">
                <button
                  className="text-left flex-1 hover:underline"
                  onClick={() => onJumpToTime?.(t.entry_time)}
                  title="跳转到入场"
                >
                  {t.dir} · {t.reason || "-"} · pnl {(t.pnl_pct * 100).toFixed(2)}% · hold {t.hold_bars}
                </button>
                <button
                  className="px-2 py-1 rounded border border-white/10 hover:bg-white/5"
                  onClick={() => onReplayAtTime?.(t.entry_time)}
                  title="从入场时间开始 bar replay"
                >
                  回放
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {downloads && (
        <div className="flex flex-wrap gap-2">
          <a className="text-xs text-emerald-300 underline" href={downloads.trades} target="_blank" rel="noreferrer">
            trades.csv
          </a>
          <a className="text-xs text-emerald-300 underline" href={downloads.equity} target="_blank" rel="noreferrer">
            equity.csv
          </a>
          <a className="text-xs text-emerald-300 underline" href={downloads.json} target="_blank" rel="noreferrer">
            report.json
          </a>
          <a className="text-xs text-emerald-300 underline" href={downloads.zip} target="_blank" rel="noreferrer">
            zip
          </a>
        </div>
      )}

      <div className="text-[11px] text-gray-500 leading-4">
        已支持：策略下拉选择 + 周期选择 + 自定义 JSON；交易列表跳转、回放、图表标记与 equity 小图。
      </div>
    </div>
  );
}
