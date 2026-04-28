"use client";

import React, { useEffect, useMemo, useState } from "react";
import { getBaseUrl } from "@/lib/api";

async function readJsonOrThrow(r: Response) {
  const j = await r.json().catch(() => null);
  if (!r.ok) {
    const msg = (j && (j.detail || j.message)) || `${r.status} ${r.statusText}`;
    throw new Error(String(msg));
  }
  return j;
}

export function ToolsPanel(props: { symbol?: string; timeframe?: string }) {
  const symbol = props.symbol || "XAUUSD";
  const timeframe = props.timeframe || "M15";

  const [action, setAction] = useState<"gap_repair_all" | "gap_repair_tf">("gap_repair_all");
  const [daysLookback, setDaysLookback] = useState(15);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [result, setResult] = useState<any>(null);
  const [progress, setProgress] = useState<any[]>([]);

  const baseUrl = useMemo(() => getBaseUrl(), []);

  const refreshProgress = async () => {
    try {
      const p = await fetch(`${baseUrl}/api/symbols/progress`).then(readJsonOrThrow);
      setProgress(Array.isArray(p) ? p : []);
    } catch {
      setProgress([]);
    }
  };

  useEffect(() => {
    refreshProgress();
    const t = setInterval(refreshProgress, 2000);
    return () => clearInterval(t);
  }, [baseUrl]);

  const run = async () => {
    setErr(null);
    setResult(null);
    setBusy(true);
    try {
      const payload =
        action === "gap_repair_all"
          ? { symbol, all_timeframes: true, days_lookback: daysLookback }
          : { symbol, timeframe, all_timeframes: false, days_lookback: daysLookback };
      const r = await fetch(`${baseUrl}/api/tools/gap-repair`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }).then(readJsonOrThrow);
      setResult(r);
      await refreshProgress();
    } catch (e: any) {
      setErr(e?.message || "Failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="h-full flex flex-col gap-3 overflow-auto">
      <div className="bg-black/20 border border-white/10 rounded-lg p-3">
        <div className="text-xs text-gray-400 mb-2">Tools</div>
        <div className="grid grid-cols-2 gap-2">
          <div className="flex flex-col gap-1">
            <span className="text-[10px] text-gray-500">Action</span>
            <select
              className="h-8 bg-[#0b0f14] border border-white/10 rounded px-2 text-xs text-white"
              value={action}
              onChange={(e) => setAction(e.target.value as any)}
            >
              <option value="gap_repair_all">Check & Repair Gaps (All TF)</option>
              <option value="gap_repair_tf">Check & Repair Gaps (Current TF)</option>
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-[10px] text-gray-500">Days Lookback</span>
            <input
              className="h-8 bg-black/30 border border-white/10 rounded px-2 text-xs text-white"
              type="number"
              value={daysLookback}
              min={1}
              max={365}
              onChange={(e) => setDaysLookback(Number(e.target.value))}
            />
          </div>
        </div>

        <div className="mt-3 flex items-center gap-2">
          <button
            type="button"
            className="px-3 py-2 rounded bg-emerald-500/20 border border-emerald-500/30 text-emerald-300 text-xs hover:bg-emerald-500/25 disabled:opacity-50"
            disabled={busy}
            onClick={run}
          >
            {busy ? "Running..." : "Run"}
          </button>
          <div className="text-[11px] text-gray-500">
            {symbol} {action === "gap_repair_tf" ? timeframe : "All TF"}
          </div>
        </div>

        {err && <div className="mt-2 text-xs text-red-400">{err}</div>}
        {result && (
          <pre className="mt-3 text-[11px] leading-4 bg-black/30 border border-white/10 rounded p-2 overflow-auto whitespace-pre-wrap text-gray-200">
            {JSON.stringify(result, null, 2)}
          </pre>
        )}
      </div>

      <div className="bg-black/20 border border-white/10 rounded-lg p-3">
        <div className="text-xs text-gray-400 mb-2">Sync Progress</div>
        {progress.length === 0 ? (
          <div className="text-[11px] text-gray-500">No active progress.</div>
        ) : (
          <div className="flex flex-col gap-2">
            {progress.slice(0, 30).map((p, idx) => (
              <div key={idx} className="border border-white/10 rounded p-2 bg-black/10">
                <div className="flex items-center justify-between">
                  <div className="text-[11px] text-gray-200">
                    {String(p.symbol)} {String(p.timeframe)}
                  </div>
                  <div className="text-[10px] text-gray-500">{String(p.status)} {Number(p.progress || 0)}%</div>
                </div>
                <div className="text-[10px] text-gray-500 mt-1">{String(p.message || "")}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

