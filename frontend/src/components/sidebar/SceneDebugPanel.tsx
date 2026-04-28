"use client";
import { getBaseUrl } from "@/lib/api";

import React, { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";

type SceneLatest = any;

function jsonPretty(v: unknown): string {
  try {
    return JSON.stringify(v, null, 2);
  } catch {
    return String(v);
  }
}

export function SceneDebugPanel(props: { symbol?: string; timeframe?: string; focusTime?: number | null }) {
  const { symbol, timeframe, focusTime } = props;
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [scene, setScene] = useState<SceneLatest | null>(null);

  const title = useMemo(() => {
    const s = symbol || "-";
    const tf = timeframe || "-";
    const t = focusTime ? ` @ ${focusTime}` : "";
    return `${s} ${tf}${t}`;
  }, [symbol, timeframe, focusTime]);

  const fetchLatest = async () => {
    if (!symbol || !timeframe) return;
    setLoading(true);
    setErr(null);
    try {
      const res = await fetch(`${getBaseUrl()}/api/scene/latest?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}`);
      if (!res.ok) {
        setErr(`Scene API 不可用（HTTP ${res.status}）。请先把 ChartScene 后端集成到 awesomeChart backend。`);
        setScene(null);
        return;
      }
      const data = await res.json();
      setScene(data);
    } catch (e: any) {
      setErr(e?.message || "请求失败");
      setScene(null);
    } finally {
      setLoading(false);
    }
  };

  const fetchByTime = async (t: number) => {
    if (!symbol || !timeframe) return;
    setLoading(true);
    setErr(null);
    try {
      const res = await fetch(
        `/api/scene/by-time?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}&time=${encodeURIComponent(
          String(t)
        )}&mode=nearest`
      );
      if (!res.ok) {
        setErr(`Scene API 不可用（HTTP ${res.status}）。`);
        setScene(null);
        return;
      }
      const data = await res.json();
      if (!data?.ok) {
        setErr(data?.message || "未找到对应时间的 scene（请先调用 /api/scene/latest 生成快照）");
        setScene(null);
        return;
      }
      setScene(data?.item?.scene ?? null);
    } catch (e: any) {
      setErr(e?.message || "请求失败");
      setScene(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // symbol/timeframe 切换：先生成一次最新快照（也可触发后端落库）
    fetchLatest();
  }, [symbol, timeframe]);

  useEffect(() => {
    if (!symbol || !timeframe) return;
    if (!focusTime) return;
    // 简单 debounce：避免拖动十字线时疯狂请求
    const h = window.setTimeout(() => {
      fetchByTime(focusTime);
    }, 150);
    return () => window.clearTimeout(h);
  }, [focusTime, symbol, timeframe]);

  const nextActions = scene?.poc_migration?.next_actions ?? [];
  const paths = scene?.poc_migration?.paths ?? scene?.poc_migration?.final_paths ?? null;
  const adjustments = scene?.poc_migration?.paths_explain?.adjustments ?? [];
  const events = scene?.volume_profile?.events ?? [];
  const patterns = scene?.patterns ?? [];
  const workflows = scene?.pattern_workflows ?? null;

  return (
    <div className="h-full flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <div className="text-xs text-gray-400">Scene Debug</div>
        <Button
          variant="outline"
          className="h-7 px-2 text-xs"
          onClick={() => (focusTime ? fetchByTime(focusTime) : fetchLatest())}
          disabled={loading || !symbol || !timeframe}
        >
          {loading ? "刷新中…" : "刷新"}
        </Button>
      </div>

      <div className="text-sm font-semibold">{title}</div>

      {err && <div className="text-xs text-red-400 whitespace-pre-wrap">{err}</div>}

      {!err && !scene && <div className="text-xs text-gray-400">暂无数据</div>}

      {scene && (
        <div className="flex-1 overflow-auto space-y-3 pr-1">
          <section className="border border-white/10 rounded p-2">
            <div className="text-xs text-gray-400 mb-1">next_actions</div>
            <div className="space-y-1">
              {Array.isArray(nextActions) && nextActions.length > 0 ? (
                nextActions.map((a: any, i: number) => (
                  <div key={i} className="text-xs">
                    <span className="font-mono text-emerald-300">{a.action}</span>
                    <span className="text-gray-400"> — {a.trigger}</span>
                  </div>
                ))
              ) : (
                <div className="text-xs text-gray-500">无</div>
              )}
            </div>
          </section>

          <section className="border border-white/10 rounded p-2">
            <div className="text-xs text-gray-400 mb-1">paths</div>
            <pre className="text-[11px] leading-4 text-gray-200 whitespace-pre-wrap">{jsonPretty(paths)}</pre>
          </section>

          <section className="border border-white/10 rounded p-2">
            <div className="text-xs text-gray-400 mb-1">paths_explain.adjustments (last 5)</div>
            <pre className="text-[11px] leading-4 text-gray-200 whitespace-pre-wrap">{jsonPretty(adjustments.slice(-5))}</pre>
          </section>

          <section className="border border-white/10 rounded p-2">
            <div className="text-xs text-gray-400 mb-1">events (last 10)</div>
            <pre className="text-[11px] leading-4 text-gray-200 whitespace-pre-wrap">{jsonPretty(events.slice(-10))}</pre>
          </section>

          <section className="border border-white/10 rounded p-2">
            <div className="text-xs text-gray-400 mb-1">patterns</div>
            <pre className="text-[11px] leading-4 text-gray-200 whitespace-pre-wrap">{jsonPretty(patterns)}</pre>
          </section>

          <section className="border border-white/10 rounded p-2">
            <div className="text-xs text-gray-400 mb-1">pattern_workflows</div>
            <pre className="text-[11px] leading-4 text-gray-200 whitespace-pre-wrap">{jsonPretty(workflows)}</pre>
          </section>

          <section className="border border-white/10 rounded p-2">
            <div className="text-xs text-gray-400 mb-1">raw scene (collapsed)</div>
            <details>
              <summary className="text-xs text-gray-300 cursor-pointer">展开</summary>
              <pre className="text-[11px] leading-4 text-gray-200 whitespace-pre-wrap">{jsonPretty(scene)}</pre>
            </details>
          </section>
        </div>
      )}
    </div>
  );
}
