import { getBaseUrl } from "@/lib/api";
"use client";

import React, { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";

type Job = any;

export function ResearchPanel(props: {
  symbol?: string;
  timeframe?: string;
  onJumpToTime?: (t: number) => void;
  onReplayAtTime?: (t: number) => void;
  onSetStudyMarkers?: (markers: any[]) => void;
  onClearStudyMarkers?: () => void;
}) {
  const { symbol, timeframe, onJumpToTime, onReplayAtTime, onSetStudyMarkers, onClearStudyMarkers } = props;
  const [running, setRunning] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [report, setReport] = useState<any | null>(null);
  const [horizonFilter, setHorizonFilter] = useState<number | "all">("all");
  const [fast, setFast] = useState(true);
  const [limit, setLimit] = useState<number>(8000);
  const [mode, setMode] = useState<"any" | "all">("any");
  const [eventIdsText, setEventIdsText] = useState<string>("liquidity_sweep_down_recover,liquidity_sweep_up_recover");
  const [horizonsText, setHorizonsText] = useState<string>("10,30");

  const tf = timeframe || "M1";
  const sym = symbol || "XAUUSDz";

  React.useEffect(() => {
    setLimit(tf === "M1" ? 5000 : 8000);
    setHorizonsText(tf === "M1" ? "10,30,60" : "10,30");
  }, [tf]);

  const run = async () => {
    setErr(null);
    setRunning(true);
    setJob(null);
    setReport(null);
    try {
      const r = await fetch(`${getBaseUrl()}/api/research/event-study/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: sym,
          timeframe: tf,
          limit,
          horizons: horizonsText
            .split(/[,\s]+/)
            .map((x) => Number(x))
            .filter((x) => Number.isFinite(x) && x > 0),
          event_ids: eventIdsText
            .split(/[,\s]+/)
            .map((x) => x.trim())
            .filter(Boolean),
          mode,
          fast,
        }),
      });
      const data = await r.json();
      if (!data?.ok) throw new Error(data?.detail || "启动失败");
      const jobId = data.job_id;

      // poll
      for (let i = 0; i < 240; i++) {
        const s = await fetch(`${getBaseUrl()}/api/research/event-study/status/${jobId}`);
        const js = await s.json();
        const j = js?.job;
        setJob(j);
        if (j?.status === "done" || j?.status === "error") break;
        await new Promise((res) => setTimeout(res, 500));
      }

      // done => 拉 report.json 用于样本列表
      const st = await fetch(`${getBaseUrl()}/api/research/event-study/status/${jobId}`);
      const stJson = await st.json();
      const j = stJson?.job;
      if (j?.status === "done") {
        const rep = await fetch(`${getBaseUrl()}/api/research/event-study/download/${jobId}?format=json`).then((x) => x.json());
        setReport(rep);
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
      csv: `/api/research/event-study/download/${job.id}?format=csv`,
      json: `/api/research/event-study/download/${job.id}?format=json`,
      zip: `/api/research/event-study/download/${job.id}?format=zip`,
    };
  }, [job]);

  const summary2 = report?.summary || summary;
  const samples: any[] = report?.samples || [];
  const horizons = useMemo(() => {
    const hs = new Set<number>();
    for (const s of samples) hs.add(Number(s.horizon));
    return Array.from(hs).filter((x) => Number.isFinite(x)).sort((a, b) => a - b);
  }, [samples]);
  const filtered = useMemo(() => {
    const ss = [...samples].sort((a, b) => (b.time || 0) - (a.time || 0));
    const ss2 = horizonFilter === "all" ? ss : ss.filter((x) => Number(x.horizon) === horizonFilter);
    return ss2.slice(0, 300);
  }, [samples, horizonFilter]);

  const markSamplesOnChart = () => {
    const ms = filtered.slice(0, 220).map((s) => {
      const r = Number(s.ret) || 0;
      return {
        time: s.time,
        position: r >= 0 ? "belowBar" : "aboveBar",
        color: r >= 0 ? "#34d399" : "#f87171",
        shape: "circle",
        text: `H${s.horizon}`,
      };
    });
    onSetStudyMarkers?.(ms);
  };

  return (
    <div className="h-full flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="text-xs text-gray-400">Analysis · Event Study (MVP)</div>
        <Button variant="outline" className="h-7 px-2 text-xs" onClick={run} disabled={running || !sym || !tf}>
          {running ? "运行中…" : "运行"}
        </Button>
      </div>

      <div className="text-sm font-semibold">
        {sym} {tf}
      </div>

      <label className="flex items-center gap-2 text-xs text-gray-400">
        <input type="checkbox" checked={fast} onChange={(e) => setFast(e.target.checked)} />
        fast 模式（更快；关闭会更慢但更完整）
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
          mode
          <select className="mt-1 w-full h-8 bg-transparent border border-white/10 rounded px-2 text-xs" value={mode} onChange={(e) => setMode(e.target.value as any)}>
            <option value="any">any</option>
            <option value="all">all</option>
          </select>
        </label>
      </div>

      <label className="text-xs text-gray-400">
        event_ids（逗号分隔）
        <input
          className="mt-1 w-full h-8 bg-transparent border border-white/10 rounded px-2 text-xs font-mono"
          value={eventIdsText}
          onChange={(e) => setEventIdsText(e.target.value)}
        />
      </label>

      <label className="text-xs text-gray-400">
        horizons（bars，逗号分隔）
        <input
          className="mt-1 w-full h-8 bg-transparent border border-white/10 rounded px-2 text-xs font-mono"
          value={horizonsText}
          onChange={(e) => setHorizonsText(e.target.value)}
        />
      </label>

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

      {summary2 && (
        <div className="space-y-2">
          <div className="border border-white/10 rounded p-2">
            <div className="text-xs text-gray-400 mb-1">summary</div>
            <div className="text-xs">samples: {summary2.samples}</div>
            <div className="text-xs">winrate: {(summary2.winrate * 100).toFixed(1)}%</div>
            <div className="text-xs">
              ret p50: {summary2.ret?.p50?.toFixed ? (summary2.ret.p50 * 100).toFixed(2) + "%" : "-"} / p75:{" "}
              {summary2.ret?.p75?.toFixed ? (summary2.ret.p75 * 100).toFixed(2) + "%" : "-"}
            </div>
          </div>

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

          {samples.length > 0 && (
            <div className="border border-white/10 rounded p-2">
              <div className="flex items-center justify-between mb-2">
                <div className="text-xs text-gray-400">samples（最近 {filtered.length} 条）</div>
                <div className="flex items-center gap-2">
                  <select
                    className="h-7 bg-transparent border border-white/10 rounded px-2 text-xs"
                    value={horizonFilter}
                    onChange={(e) => setHorizonFilter(e.target.value === "all" ? "all" : Number(e.target.value))}
                  >
                    <option value="all">all</option>
                    {horizons.map((h) => (
                      <option key={h} value={h}>
                        H{h}
                      </option>
                    ))}
                  </select>
                  <button className="h-7 px-2 rounded border border-white/10 text-xs hover:bg-white/5" onClick={markSamplesOnChart}>
                    标记
                  </button>
                  <button className="h-7 px-2 rounded border border-white/10 text-xs hover:bg-white/5" onClick={() => onClearStudyMarkers?.()}>
                    清除
                  </button>
                </div>
              </div>

              <div className="max-h-[280px] overflow-auto space-y-1">
                {filtered.map((s, idx) => (
                  <div key={idx} className="flex items-center justify-between gap-2 text-xs">
                    <button className="text-left flex-1 hover:underline" onClick={() => onJumpToTime?.(s.time)} title="跳转到样本时间">
                      t={s.time} · H{s.horizon} · ret {(Number(s.ret) * 100).toFixed(2)}% · {Array.isArray(s.triggered) ? s.triggered.join("|") : ""}
                    </button>
                    <button
                      className="px-2 py-1 rounded border border-white/10 hover:bg-white/5"
                      onClick={() => onReplayAtTime?.(s.time)}
                      title="从该时间点开始 bar replay"
                    >
                      回放
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      <div className="text-[11px] text-gray-500 leading-4">
        MVP 策略：使用 fast scene（跳过 SessionVP 重计算），仅统计 sweep recover 类事件；后续会扩展到 reclaim/acceptance 等事件与策略回测。
      </div>
    </div>
  );
}
