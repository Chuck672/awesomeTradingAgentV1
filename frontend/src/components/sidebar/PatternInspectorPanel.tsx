"use client";

import React, { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { getBaseUrl } from "@/lib/api";

type DetectorId = "rectangle_range" | "close_outside_level_zone" | "breakout_retest_hold" | "false_breakout" | "liquidity_sweep" | "bos" | "choch";
type Dir = "Bullish" | "Bearish" | "Neutral" | string;

function apiUrl(path: string) {
  return `${getBaseUrl()}${path}`;
}

function tfToSchemaV2(tf: string): string {
  const t = String(tf || "").toUpperCase();
  if (t === "M1") return "1m";
  if (t === "M5") return "5m";
  if (t === "M15") return "15m";
  if (t === "M30") return "30m";
  if (t === "H1") return "1h";
  if (t === "H4") return "4h";
  if (t === "D1") return "1d";
  return "30m";
}

function tfToSeconds(tf: string): number {
  const t = String(tf || "").toUpperCase();
  if (t === "M1") return 60;
  if (t === "M5") return 5 * 60;
  if (t === "M15") return 15 * 60;
  if (t === "M30") return 30 * 60;
  if (t === "H1") return 60 * 60;
  if (t === "H4") return 4 * 60 * 60;
  if (t === "D1") return 24 * 60 * 60;
  return 30 * 60;
}

function typicalBarRange(bars: any[]): number {
  if (!Array.isArray(bars) || bars.length < 10) return 0;
  const tail = bars.slice(Math.max(0, bars.length - 200));
  const rs: number[] = [];
  for (const b of tail) {
    const h = Number(b?.high);
    const l = Number(b?.low);
    if (Number.isFinite(h) && Number.isFinite(l) && h > l) rs.push(h - l);
  }
  if (rs.length === 0) return 0;
  rs.sort((a, b) => a - b);
  return rs[Math.floor(rs.length / 2)];
}

function safeJson(v: any) {
  try {
    return JSON.stringify(v ?? null, null, 2);
  } catch {
    return "";
  }
}

function dirColor(dir: Dir) {
  if (dir === "Bullish") return "#22c55e";
  if (dir === "Bearish") return "#ef4444";
  return "#60a5fa";
}

function fmtTs(t: number) {
  const x = Number(t);
  if (!Number.isFinite(x) || x <= 0) return "-";
  try {
    const d = new Date(x * 1000);
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    const hh = String(d.getHours()).padStart(2, "0");
    const mi = String(d.getMinutes()).padStart(2, "0");
    return `${mm}-${dd} ${hh}:${mi}`;
  } catch {
    return String(x);
  }
}

export function PatternInspectorPanel(props: {
  symbol?: string;
  timeframe?: string;
  onExecuteActions?: (actions: any[]) => Promise<string[]> | string[];
}) {
  const { symbol, timeframe, onExecuteActions } = props;
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [rawResp, setRawResp] = useState<any | null>(null);
  const [items, setItems] = useState<any[]>([]);
  // 缓存本次运行用到的 bars，供点击条目高亮时做时间裁剪/兜底
  const [barsCache, setBarsCache] = useState<any[]>([]);

  const [lookback, setLookback] = useState(300);
  const [rangeEmitMode, setRangeEmitMode] = useState<"distinct" | "all" | "best">("distinct");
  const [rangeMaxResults, setRangeMaxResults] = useState(120);
  const [rangeDedupIou, setRangeDedupIou] = useState(0.7);
  const [selected, setSelected] = useState<Record<DetectorId, boolean>>({
    rectangle_range: true,
    close_outside_level_zone: true,
    breakout_retest_hold: true,
    false_breakout: true,
    liquidity_sweep: true,
    bos: true,
    choch: true,
  });

  const [viz, setViz] = useState({
    // 为了保持图表干净：只绘制箱体（不绘制水平线/marker）
    drawBoxes: true,
    autoClearBeforeDraw: true,
    maxBoxesToDraw: 8,
  });

  const enabledDetectors = useMemo(() => Object.entries(selected).filter(([, v]) => v).map(([k]) => k as DetectorId), [selected]);

  const run = async () => {
    setErr(null);
    if (!symbol || !timeframe) {
      setErr("当前没有选中图表的 symbol/timeframe。请先在主图表选择品种与周期。");
      return;
    }
    if (!onExecuteActions) {
      setErr("当前面板未绑定 chart action 执行器，无法落图。");
      return;
    }
    if (enabledDetectors.length === 0) {
      setErr("请至少选择一个 detector。");
      return;
    }
    setBusy(true);
    try {
      // 1) fetch bars
      const limit = Math.max(120, Math.min(5000, Number(lookback) || 300));
      const r = await fetch(apiUrl(`/api/history?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}&limit=${limit}`));
      const bars = await r.json().catch(() => []);
      if (!r.ok || !Array.isArray(bars) || bars.length < 30) throw new Error("获取历史K线失败或数据不足");
      setBarsCache(bars);

      const tf2 = tfToSchemaV2(timeframe);
      // 实际可用 bars 数（history limit 可能小于 lookback 输入）
      const lbBars = Math.min(limit, bars.length);

      // 2) build schema v2 (minimal)
      const patterns: any[] = [];
      for (const d of enabledDetectors) {
        if (d === "rectangle_range")
          patterns.push({
            type: "rectangle_range",
            timeframe: tf2,
            // 注意：这里之前写死了 300，会导致你输入 3000 也只按 300 计算
            lookback_bars: lbBars,
            min_touches_per_side: 2,
            tolerance_atr_mult: 0.25,
            // 趋势过滤（默认偏宽松：先确保能找到箱体；你可再按需要收紧）
            min_containment: 0.78,
            max_height_atr: 12.0,
            max_drift_atr: 3.5,
            max_efficiency: 0.55,
            // 输出模式说明：
            // - distinct：去重后输出“不同箱体结构”（推荐）
            // - all：输出所有候选窗口（会出现大量重复箱体，不建议直接画到图上）
            // - best：只输出一个最佳箱体
            emit: rangeEmitMode,
            max_results: rangeEmitMode === "best" ? 1 : Math.max(1, Math.min(2000, Number(rangeMaxResults) || 120)),
            distinct_no_overlap: true,
            dedup_iou: Math.max(0, Math.min(1, Number(rangeDedupIou) || 0.7)),
          });
        else if (d === "close_outside_level_zone")
          patterns.push({
            type: "close_outside_level_zone",
            timeframe: tf2,
            close_buffer: 0.0,
            scan_mode: "historical",
            lookback_bars: lbBars,
            confirm_mode: "one_body",
            confirm_n: 2,
            max_events: 200,
          });
        else if (d === "breakout_retest_hold")
          patterns.push({
            type: "breakout_retest_hold",
            timeframe: tf2,
            scan_mode: "historical",
            lookback_bars: lbBars,
            confirm_mode: "one_body",
            confirm_n: 2,
            retest_window_bars: 16,
            continue_window_bars: 8,
            buffer: 0.0,
            pullback_margin: 0.0,
            max_events: 200,
          });
        else if (d === "false_breakout") patterns.push({ type: "false_breakout", timeframe: tf2, lookback_bars: lbBars, buffer: 0.0 });
        else if (d === "liquidity_sweep") patterns.push({ type: "liquidity_sweep", timeframe: tf2, lookback_bars: lbBars, buffer: 0.0, recover_within_bars: 3 });
        else if (d === "bos") patterns.push({ type: "bos", timeframe: tf2, lookback_bars: lbBars, pivot_left: 3, pivot_right: 3, buffer: 0.0 });
        else if (d === "choch") patterns.push({ type: "choch", timeframe: tf2, lookback_bars: lbBars, pivot_left: 3, pivot_right: 3, buffer: 0.0 });
      }

      const schema: any = {
        spec_version: "2.0",
        meta: { strategy_id: "pattern_inspector", name: "Pattern Inspector", version: "0.1.0", description: "前端可视化检查用" },
        universe: { symbols: [symbol], primary_timeframe: tf2 },
        data: { history_lookback_bars: Math.min(2000, bars.length), higher_timeframes: [] },
        indicators: [],
        structures: {
          level_generator: {
            sources: [
              { type: "prev_day_high_low" },
              { type: "fractal_levels", timeframe: tf2, fractal_left: 3, fractal_right: 3 }
            ],
            merge: { distance_pips: { default: { type: "fixed_pips", pips: 20 } } },
            // lookback 越大，历史扫描需要更多 levels/zones 覆盖整个区间
            output: {
              max_levels: Math.min(100, Math.max(12, Math.floor(lbBars / 25))),
              emit_zone: true,
              zone_half_width_pips: { default: { type: "fixed_pips", pips: 25 } },
              zone_max_age_bars: 300,
            }
          }
        },
        patterns,
        action: { type: "breakout" },
        outputs: { emit_evidence_pack: true, emit_draw_plan: true, emit_compilation_report: true, emit_trace: true, emit_intermediate_artifacts: false }
      };

      // 3) execute (offline via bars_override)
      const payload = { strategy_schema: schema, bars_override: { [tf2]: bars } };
      const r2 = await fetch(apiUrl("/api/strategy/schema/v2/execute"), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      const j2 = await r2.json().catch(() => ({}));
      if (!r2.ok) throw new Error(String((j2 as any)?.detail || `HTTP ${r2.status}`));
      setRawResp(j2);

      // 4) build draw objects
      const exec = (j2 as any)?.exec || {};
      const outs = exec?.outputs || {};
      const structs = outs?.structures || {};
      const pack = outs?.patterns?.pattern_pack || outs?.patterns || (outs?.patterns?.pattern_pack ?? null);
      // 不在这里截断（否则你会误以为只有 80 个结果）
      const allItems = Array.isArray(pack?.items) ? pack.items : [];
      setItems(allItems);

      const objects: any[] = [];

      const lastTime = Number(bars[bars.length - 1]?.time);
      const firstTime = Number(bars[0]?.time);
      const barSpanSec = tfToSeconds(timeframe || "H1");
      const medRange = typicalBarRange(bars);

      const normalizeTimeRange = (fromT: number, toT: number) => {
        let a = Number(fromT);
        let b = Number(toT);
        if (!Number.isFinite(a) || !Number.isFinite(b)) return { fromT: 0, toT: 0 };
        if (Number.isFinite(firstTime) && firstTime > 0) a = Math.max(a, firstTime);
        if (Number.isFinite(lastTime) && lastTime > 0) b = Math.min(b, lastTime);
        // 避免 to==from 或时间缺口导致 box 退化成“一个角/一条短线”：
        // 给一个更明显的最小宽度（默认 6 根 bar）
        if (b <= a) b = a + Math.max(1, barSpanSec) * 6;
        return { fromT: a, toT: b };
      };

      // close_outside_level_zone 的 zone 可能早于本次 lookback 的第一根K线。
      // 如果强行 clip 到 firstTime，会导致 box 退化成“短角标”，看起来像显示错误。
      // 因此单独提供一个“不裁剪，只保证最小宽度”的时间归一化。
      const normalizeTimeRangeNoClip = (fromT: number, toT: number) => {
        let a = Number(fromT);
        let b = Number(toT);
        if (!Number.isFinite(a) || !Number.isFinite(b)) return { fromT: 0, toT: 0 };
        if (b <= a) b = a + Math.max(1, barSpanSec) * 6;
        return { fromT: a, toT: b };
      };

      const overlapWithWindow = (fromT: number, toT: number) => {
        const a = Number(fromT);
        const b = Number(toT);
        if (!Number.isFinite(a) || !Number.isFinite(b)) return false;
        if (!Number.isFinite(firstTime) || !Number.isFinite(lastTime) || firstTime <= 0 || lastTime <= 0) return true;
        return b >= firstTime && a <= lastTime;
      };

      // 避免 box 高度过小（会在图上退化成“两个角/短线”），对可视化做最小高度扩展
      const normalizePriceRange = (bottom: number, top: number) => {
        let lo = Number(bottom);
        let hi = Number(top);
        if (!Number.isFinite(lo) || !Number.isFinite(hi)) return { lo: lo, hi: hi };
        if (hi < lo) [lo, hi] = [hi, lo];
        const h = hi - lo;
        const minH = medRange > 0 ? medRange * 0.25 : 0;
        if (minH > 0 && h < minH) {
          const pad = (minH - h) * 0.5;
          lo -= pad;
          hi += pad;
        }
        return { lo, hi };
      };

      // close_outside_level_zone 需要可视化 level zones（矩形区间），否则很难判断为什么 0 items
      if (enabledDetectors.includes("close_outside_level_zone")) {
        // 优先画“事件里裁剪后的 zone”（突破确认即结束），满足交易语义
        const eventZones: any[] = [];
        for (const it of allItems) {
          if (String(it?.type || "") !== "close_outside_level_zone") continue;
          const z = (it?.evidence as any)?.zone;
          if (!z) continue;
          const top = Number(z?.top);
          const bottom = Number(z?.bottom);
          const fromT = Number(z?.from_time);
          const toT = Number(z?.to_time);
          if (!Number.isFinite(top) || !Number.isFinite(bottom) || !Number.isFinite(fromT) || !Number.isFinite(toT) || fromT <= 0 || toT <= 0) continue;
          eventZones.push({ top, bottom, fromT, toT });
        }
        // 去重 + 限制数量，避免刷屏
        const seen = new Set<string>();
        const uniq = [];
        for (const z of eventZones) {
          const key = `${z.fromT}_${z.toT}_${z.top.toFixed(3)}_${z.bottom.toFixed(3)}`;
          if (seen.has(key)) continue;
          seen.add(key);
          uniq.push(z);
          if (uniq.length >= 40) break;
        }
        if (viz.drawBoxes && uniq.length > 0) {
          for (const z of uniq) {
            // 对 close_outside：不做时间裁剪（让 chart.drawObjects 自动补历史，并避免退化成角标）
            const tr = normalizeTimeRangeNoClip(z.fromT, z.toT);
            const pr = normalizePriceRange(z.bottom, z.top);
            objects.push({
              type: "box",
              from_time: tr.fromT,
              to_time: tr.toT,
              low: pr.lo,
              high: pr.hi,
              color: "#60a5fa",
              fillColor: "#60a5fa",
              fillOpacity: 0.12,
              lineStyle: "solid",
              lineWidth: 2,
            });
          }
        } else if (Array.isArray(structs?.zones)) {
          // 若没有任何事件（0 items），退化画少量结构 zones 作为参考
          const zs = (structs?.zones || []).slice(0, 20);
          for (const z of zs) {
            const top = Number(z?.top ?? (Number(z?.center) + Number(z?.half_width || z?.half_width_pips || 0)));
            const bottom = Number(z?.bottom ?? (Number(z?.center) - Number(z?.half_width || z?.half_width_pips || 0)));
            const fromT = Number(z?.from_time || 0);
            const toT = Number(z?.to_time || 0);
            if (!Number.isFinite(top) || !Number.isFinite(bottom) || !Number.isFinite(fromT) || !Number.isFinite(toT) || fromT <= 0 || toT <= 0) continue;
            if (viz.drawBoxes) {
              const tr = normalizeTimeRange(fromT, toT);
              const pr = normalizePriceRange(bottom, top);
              objects.push({
                type: "box",
                from_time: tr.fromT,
                to_time: tr.toT,
                low: pr.lo,
                high: pr.hi,
                color: "#475569",
                fillColor: "#475569",
                fillOpacity: 0.03,
                lineStyle: "solid",
                lineWidth: 1,
              });
            }
          }
        }
      }

      let boxesDrawn = 0;
      for (const it of allItems) {
        const id = String(it?.id || "");
        const type = String(it?.type || "");
        const ev = it?.evidence || {};

        if (type === "rectangle_range" && it?.zone) {
          // 避免一次画太多 box 让图表不可读；列表仍会显示全部箱体
          if (boxesDrawn >= Number(viz.maxBoxesToDraw || 0)) {
            continue;
          }
          const top = Number(it.zone?.top);
          const bottom = Number(it.zone?.bottom);
          const evFrom = Number(it?.evidence?.from_time || 0);
          const evTo = Number(it?.evidence?.to_time || 0);
          // 优先使用后端给出的箱体起止时间（更准确），否则再退化用 lookback 推算
          const lb = Number(it?.evidence?.lookback_bars || 0);
          const fromIdx = lb > 0 ? Math.max(0, bars.length - lb) : Math.max(0, bars.length - 150);
          const fromT = Number.isFinite(evFrom) && evFrom > 0 ? evFrom : Number(bars[fromIdx]?.time);
          const toT = Number.isFinite(evTo) && evTo > 0 ? evTo : lastTime;
          if (viz.drawBoxes && Number.isFinite(top) && Number.isFinite(bottom) && Number.isFinite(fromT) && Number.isFinite(toT)) {
            objects.push({
              type: "box",
              from_time: fromT,
              to_time: toT,
              low: bottom,
              high: top,
              color: "#94a3b8",
              fillColor: "#94a3b8",
              fillOpacity: 0.06,
              lineStyle: "dotted",
              lineWidth: 1,
            });
            boxesDrawn += 1;
          }
        }

        // breakout + pullback：默认画 breakout 线段 + retest_hold 区间（更好理解）
        if (type === "breakout_retest_hold") {
          if (boxesDrawn >= Number(viz.maxBoxesToDraw || 0)) continue;
          const z = (ev as any)?.zone || null;
          const top = Number(z?.top);
          const bottom = Number(z?.bottom);
          const fromT = Number(z?.from_time);
          const toT = Number(z?.to_time);
          const brk = (ev as any)?.breakout || null;
          const pb = (ev as any)?.pullback || null;
          const cont = (ev as any)?.continuation || null;
          const tTrig = Number(brk?.trigger_time || 0);
          const tBrk = Number(brk?.confirm_time || 0);
          const tPb = Number(pb?.retest_time || 0);
          const tCf = Number(cont?.continue_time || 0);
          const margin = Number(pb?.margin || 0);
          if (viz.drawBoxes && Number.isFinite(top) && Number.isFinite(bottom) && Number.isFinite(fromT) && Number.isFinite(toT) && fromT > 0 && toT > 0) {
            const dir = String(it?.direction || "");
            const col = dir === "Bullish" ? "#22c55e" : dir === "Bearish" ? "#ef4444" : "#94a3b8";
            // 1) zone box（事件视角已裁剪到确认结束）
            const tr = normalizeTimeRange(fromT, toT);
            objects.push({
              type: "box",
              from_time: tr.fromT,
              to_time: tr.toT,
              low: bottom,
              high: top,
              color: col,
              fillColor: col,
              fillOpacity: 0.03,
              lineStyle: "solid",
              lineWidth: 1,
            });

            // 2) breakout：画一个短 trendline（线段）
            const level = dir === "Bearish" ? bottom : top;
            if (Number.isFinite(level) && Number.isFinite(tBrk) && tBrk > 0) {
              const t1 = Number.isFinite(tTrig) && tTrig > 0 ? tTrig : tBrk - barSpanSec;
              const t2 = tBrk;
              const tr2 = normalizeTimeRange(t1, t2);
              objects.push({
                type: "trendline",
                t1: tr2.fromT,
                p1: level,
                t2: tr2.toT,
                p2: level,
                color: "#a78bfa",
                text: "BRK",
              });
            }

            // 3) retest_hold：用 rectangle 表示“回踩与保持”区间
            if (Number.isFinite(tPb) && tPb > 0 && Number.isFinite(tCf) && tCf > 0 && Number.isFinite(level)) {
              const rr = normalizeTimeRange(tPb, tCf);
              const m = Number.isFinite(margin) && margin > 0 ? margin : 0;
              const low = level - (m > 0 ? m : 0);
              const high = level + (m > 0 ? m : 0);
              // margin 过小会看不见：兜底给一个最小高度（按 zone 高度的 3%）
              const minH = Math.max(1e-6, (top - bottom) * 0.03);
              const lo2 = Number.isFinite(low) ? low : level - minH;
              const hi2 = Number.isFinite(high) ? high : level + minH;
              objects.push({
                type: "box",
                from_time: rr.fromT,
                to_time: rr.toT,
                low: Math.min(lo2, hi2 - minH),
                high: Math.max(hi2, lo2 + minH),
                color: "#eab308",
                fillColor: "#eab308",
                fillOpacity: 0.08,
                lineStyle: "solid",
                lineWidth: 1,
              });
            }

            boxesDrawn += 1;
          }
        }
      }

      // 5) clear ai overlays then draw
      if (viz.autoClearBeforeDraw) await onExecuteActions([{ type: "chart_clear_ai_overlays" }]);
      await onExecuteActions([{ type: "chart_draw", objects }]);
    } catch (e: any) {
      setErr(e?.message || "运行失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="h-full flex flex-col gap-3 overflow-hidden bg-white dark:bg-transparent text-gray-800 dark:text-gray-200">
      <div className="text-xs text-gray-500 dark:text-gray-400">
        当前：{symbol || "-"} {timeframe || "-"}
      </div>

      <div className="flex items-center gap-2">
        <label className="text-xs text-gray-700 dark:text-gray-300">
          lookback
          <input
            type="number"
            className="ml-2 w-24 px-2 py-1 rounded bg-gray-50 dark:bg-black/40 border border-gray-200 dark:border-white/10 text-gray-800 dark:text-white"
            value={lookback}
            onChange={(e) => setLookback(Number(e.target.value))}
          />
        </label>
        <Button onClick={run} disabled={busy} className="bg-[#00bfa5] hover:bg-[#00a68f] text-white">
          {busy ? "运行中…" : "运行检测并落图"}
        </Button>
        <Button
          variant="secondary"
          onClick={async () => {
            setErr(null);
            setRawResp(null);
            setItems([]);
            await onExecuteActions?.([{ type: "chart_clear_ai_overlays" }]);
          }}
          disabled={!onExecuteActions}
          className="bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-200"
        >
          清除标注
        </Button>
      </div>

      <div className="border border-gray-200 dark:border-white/10 rounded-lg p-2 bg-gray-50 dark:bg-black/20">
        <div className="text-xs text-gray-500 dark:text-gray-400 mb-2">可视化选项</div>
        <div className="grid grid-cols-2 gap-2">
          <label className="text-xs text-gray-700 dark:text-gray-200 flex items-center gap-2 col-span-2">
            <input type="checkbox" checked={viz.drawBoxes} onChange={(e) => setViz((v) => ({ ...v, drawBoxes: e.target.checked }))} />
            仅显示区间 box
          </label>
          <label className="text-xs text-gray-700 dark:text-gray-200 flex items-center gap-2 col-span-2">
            <input type="checkbox" checked={viz.autoClearBeforeDraw} onChange={(e) => setViz((v) => ({ ...v, autoClearBeforeDraw: e.target.checked }))} />
            每次运行前自动清除旧标注
          </label>
          <label className="text-xs text-gray-700 dark:text-gray-200 flex items-center gap-2 col-span-2">
            绘制箱体上限
            <input
              type="number"
              className="ml-2 w-20 px-2 py-1 rounded bg-white dark:bg-black/40 border border-gray-200 dark:border-white/10 text-gray-800 dark:text-white"
              value={viz.maxBoxesToDraw}
              min={0}
              max={200}
              onChange={(e) => setViz((v) => ({ ...v, maxBoxesToDraw: Number(e.target.value) }))}
            />
            <span className="text-gray-400 dark:text-gray-500 text-[11px]">(0=不画)</span>
          </label>
        </div>
        <div className="mt-2 text-[11px] text-gray-500 dark:text-gray-500">
          说明：为避免图表过于杂乱，当前仅落图箱体（不绘制水平线与 marker）。
        </div>
      </div>

      <div className="border border-gray-200 dark:border-white/10 rounded-lg p-2 bg-gray-50 dark:bg-black/20">
        <div className="text-xs text-gray-500 dark:text-gray-400 mb-2">箱体输出模式（rectangle_range）</div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="text-xs text-gray-700 dark:text-gray-200 flex items-center gap-2">
            模式
            <select
              className="ml-2 px-2 py-1 rounded bg-white dark:bg-black/40 border border-gray-200 dark:border-white/10 text-gray-800 dark:text-gray-200"
              value={rangeEmitMode}
              onChange={(e) => setRangeEmitMode(e.target.value as any)}
            >
              <option value="distinct">distinct（推荐）</option>
              <option value="all">all（会重复）</option>
              <option value="best">best（1个）</option>
            </select>
          </label>

          {rangeEmitMode !== "best" && (
            <label className="text-xs text-gray-700 dark:text-gray-200 flex items-center gap-2">
              max_results
              <input
                type="number"
                className="ml-2 w-20 px-2 py-1 rounded bg-white dark:bg-black/40 border border-gray-200 dark:border-white/10 text-gray-800 dark:text-white"
                value={rangeMaxResults}
                min={1}
                max={2000}
                onChange={(e) => setRangeMaxResults(Number(e.target.value))}
              />
            </label>
          )}

          {rangeEmitMode === "distinct" && (
            <label className="text-xs text-gray-700 dark:text-gray-200 flex items-center gap-2">
              去重 IoU
              <input
                type="number"
                step="0.05"
                className="ml-2 w-20 px-2 py-1 rounded bg-white dark:bg-black/40 border border-gray-200 dark:border-white/10 text-gray-800 dark:text-white"
                value={rangeDedupIou}
                min={0}
                max={1}
                onChange={(e) => setRangeDedupIou(Number(e.target.value))}
              />
              <span className="text-gray-400 dark:text-gray-500 text-[11px]">越大越严格</span>
            </label>
          )}
        </div>
        <div className="mt-2 text-[11px] text-gray-500 dark:text-gray-500">
          你看到“同一段画出 80 个箱体”是因为 all 会把不同起止窗口都当候选输出（必然大量重复）。一般应使用 distinct 来输出“不同结构”。
        </div>
      </div>

      <div className="border border-gray-200 dark:border-white/10 rounded-lg p-2 bg-gray-50 dark:bg-black/20 overflow-auto">
        <div className="text-xs text-gray-500 dark:text-gray-400 mb-2">Detectors</div>
        <div className="grid grid-cols-2 gap-2">
          {(Object.keys(selected) as DetectorId[]).map((k) => (
            <label key={k} className="text-xs text-gray-700 dark:text-gray-200 flex items-center gap-2">
              <input type="checkbox" checked={!!selected[k]} onChange={(e) => setSelected((s) => ({ ...s, [k]: e.target.checked }))} />
              {k}
            </label>
          ))}
        </div>
      </div>

      <div className="border border-gray-200 dark:border-white/10 rounded-lg p-2 bg-gray-50 dark:bg-black/20 overflow-auto max-h-[28vh]">
        <div className="flex items-center justify-between mb-2">
          <div className="text-xs text-gray-500 dark:text-gray-400">检测结果（可点击跳转）</div>
          <div className="text-[11px] text-gray-400 dark:text-gray-500">{items.length} items</div>
        </div>
        {items.length === 0 ? (
          <div className="text-xs text-gray-400 dark:text-gray-500">暂无结果（可尝试增大 lookback 或切换品种/周期）</div>
        ) : (
          <div className="space-y-1">
            {items.slice(0, 400).map((it, idx) => {
              const id = String(it?.id || "");
              const type = String(it?.type || "");
              const dir = String(it?.direction || "") as Dir;
              const color = dirColor(dir);
              const ev = it?.evidence || {};
              const t = Number(ev?.bar_time || ev?.sweep_time || ev?.break_time || 0);
              const score = it?.score != null ? Number(it.score) : null;
              return (
                <button
                  key={`${id}_${idx}`}
                  className="w-full text-left text-[12px] px-2 py-1 rounded border border-gray-200 dark:border-white/10 hover:bg-gray-100 dark:hover:bg-white/5 text-gray-800 dark:text-gray-200"
                  onClick={async () => {
                    if (!onExecuteActions) return;
                    if (Number.isFinite(t) && t > 0) await onExecuteActions([{ type: "chart_scroll_to_time", time: t }]);

                    // 如果点击的是箱体：只高亮该箱体（避免几十个 box 堆在一起看不清）
                    if (type === "rectangle_range" && it?.zone) {
                      const top = Number(it.zone?.top);
                      const bottom = Number(it.zone?.bottom);
                      const fromT = Number(ev?.from_time || 0);
                      const toT = Number(ev?.to_time || 0);
                      if (Number.isFinite(top) && Number.isFinite(bottom) && Number.isFinite(fromT) && Number.isFinite(toT)) {
                        await onExecuteActions([{ type: "chart_clear_ai_overlays" }]);
                        const objs: any[] = [];
                        objs.push({
                          type: "box",
                          from_time: fromT,
                          to_time: toT,
                          low: bottom,
                          high: top,
                          color: "#a78bfa",
                          fillColor: "#a78bfa",
                          fillOpacity: 0.08,
                          lineStyle: "solid",
                          lineWidth: 2,
                        });
                        await onExecuteActions([{ type: "chart_draw", objects: objs }]);
                      }
                    }

                    // 点击 close_outside_level_zone：高亮对应的 level zone（矩形区间）
                    if (type === "close_outside_level_zone") {
                      const z = (ev as any)?.zone || null;
                      const top = Number(z?.top);
                      const bottom = Number(z?.bottom);
                      const fromT = Number(z?.from_time);
                      const toT = Number(z?.to_time);
                      if (Number.isFinite(top) && Number.isFinite(bottom) && Number.isFinite(fromT) && Number.isFinite(toT)) {
                        await onExecuteActions([{ type: "chart_clear_ai_overlays" }]);
                        // 先滚到触发附近，避免用户看不到（尤其当 from_time 很早，drawObjects 会补历史）
                        await onExecuteActions([{ type: "chart_scroll_to_time", time: toT }]);
                        const objs: any[] = [];
                        const barSpan = tfToSeconds(timeframe || "H1");
                        const a0 = fromT;
                        const b0 = toT;
                        // 避免 box 宽度为 0：至少 1 根 bar
                        const to2 = b0 <= a0 ? a0 + Math.max(1, barSpan) * 6 : b0;
                        // 避免 box 高度过小
                        const medRange2 = typicalBarRange(barsCache);
                        const minH = medRange2 > 0 ? medRange2 * 0.25 : 0;
                        let lo = bottom, hi = top;
                        if (hi < lo) [lo, hi] = [hi, lo];
                        if (minH > 0 && hi - lo < minH) {
                          const pad = (minH - (hi - lo)) * 0.5;
                          lo -= pad;
                          hi += pad;
                        }
                        objs.push({
                          type: "box",
                          from_time: a0,
                          to_time: to2,
                          low: lo,
                          high: hi,
                          color: "#60a5fa",
                          fillColor: "#60a5fa",
                          fillOpacity: 0.06,
                          lineStyle: "solid",
                          lineWidth: 2,
                        });
                        await onExecuteActions([{ type: "chart_draw", objects: objs }]);
                      }
                    }

                    // breakout + pullback：点击后高亮（zone + breakout/pullback/confirm 三个窄 box）
                    if (type === "breakout_retest_hold") {
                      const z = (ev as any)?.zone || null;
                      const top = Number(z?.top);
                      const bottom = Number(z?.bottom);
                      const fromT = Number(z?.from_time);
                      const toT = Number(z?.to_time);
                      const brk = (ev as any)?.breakout || null;
                      const pb = (ev as any)?.pullback || null;
                      const cont = (ev as any)?.continuation || null;
                      const tTrig = Number(brk?.trigger_time || 0);
                      const tBrk = Number(brk?.confirm_time || 0);
                      const tPb = Number(pb?.retest_time || 0);
                      const tCf = Number(cont?.continue_time || 0);
                      const margin = Number(pb?.margin || 0);
                      const barSpan = tfToSeconds(timeframe || "H1");
                      if (Number.isFinite(top) && Number.isFinite(bottom) && Number.isFinite(fromT) && Number.isFinite(toT)) {
                        await onExecuteActions([{ type: "chart_clear_ai_overlays" }]);
                        const objs: any[] = [];
                        const dir = String(it?.direction || "");
                        const col = dir === "Bullish" ? "#22c55e" : dir === "Bearish" ? "#ef4444" : "#94a3b8";
                        const level = dir === "Bearish" ? bottom : top;
                        const firstT = Number(barsCache?.[0]?.time || 0);
                        const lastT = Number(barsCache?.[barsCache.length - 1]?.time || 0);
                        const a = firstT > 0 ? Math.max(firstT, fromT) : fromT;
                        const b = lastT > 0 ? Math.min(lastT, toT) : toT;
                        const to2 = b <= a ? a + Math.max(1, barSpan) : b;
                        objs.push({
                          type: "box",
                          from_time: a,
                          to_time: to2,
                          low: bottom,
                          high: top,
                          color: col,
                          fillColor: col,
                          fillOpacity: 0.06,
                          lineStyle: "solid",
                          lineWidth: 2,
                        });
                        // breakout：线段（trendline）
                        if (Number.isFinite(level) && Number.isFinite(tBrk) && tBrk > 0) {
                          const t1 = Number.isFinite(tTrig) && tTrig > 0 ? tTrig : tBrk - barSpan;
                          const t2 = tBrk;
                          objs.push({ type: "trendline", t1, p1: level, t2, p2: level, color: "#a78bfa", text: "BRK" });
                        }
                        // retest_hold：矩形（回踩到延续确认）
                        if (Number.isFinite(level) && Number.isFinite(tPb) && tPb > 0 && Number.isFinite(tCf) && tCf > 0) {
                          const m = Number.isFinite(margin) && margin > 0 ? margin : (top - bottom) * 0.03;
                          const rrFrom = firstT > 0 ? Math.max(firstT, tPb) : tPb;
                          const rrTo0 = lastT > 0 ? Math.min(lastT, tCf) : tCf;
                          const rrTo = rrTo0 <= rrFrom ? rrFrom + Math.max(1, barSpan) : rrTo0;
                          objs.push({
                            type: "box",
                            from_time: rrFrom,
                            to_time: rrTo,
                            low: level - m,
                            high: level + m,
                            color: "#eab308",
                            fillColor: "#eab308",
                            fillOpacity: 0.10,
                            lineStyle: "solid",
                            lineWidth: 1,
                          });
                        }
                        // confirm：一个窄 box 用于定位（可选）
                        if (Number.isFinite(tCf) && tCf > 0) {
                          objs.push({
                            type: "box",
                            from_time: tCf - barSpan,
                            to_time: tCf + barSpan,
                            low: bottom,
                            high: top,
                            color: "#06b6d4",
                            fillColor: "#06b6d4",
                            fillOpacity: 0.08,
                            lineStyle: "solid",
                            lineWidth: 1,
                          });
                        }
                        await onExecuteActions([{ type: "chart_draw", objects: objs }]);
                      }
                    }
                  }}
                  title="点击跳转"
                >
                  <span style={{ color }} className="font-semibold">
                    {id}
                  </span>
                  <span className="text-gray-600 mx-2">·</span>
                  <span className="text-gray-300">{type}</span>
                  <span className="text-gray-600 mx-2">·</span>
                  <span className="text-gray-400">{fmtTs(t)}</span>
                  {Number.isFinite(score as any) && <span className="text-gray-500 ml-2">score={Math.round(Number(score))}</span>}
                </button>
              );
            })}
          </div>
        )}
      </div>

      {err && <div className="text-xs text-red-300 border border-red-500/30 bg-red-500/10 rounded p-2">{err}</div>}

      {rawResp && (
        <details className="border border-white/10 rounded-lg bg-black/20 p-2 overflow-auto">
          <summary className="text-xs text-gray-300 cursor-pointer select-none">查看原始响应（execute）</summary>
          <pre className="mt-2 text-[11px] whitespace-pre-wrap">{safeJson(rawResp)}</pre>
        </details>
      )}
    </div>
  );
}
