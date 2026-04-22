"use client";

import React, { useEffect, useRef, useState, useCallback, forwardRef, useImperativeHandle } from "react";
import { createChart, ColorType, CandlestickSeries, LineSeries, HistogramSeries, CrosshairMode, IChartApi, ISeriesApi, LogicalRange, MouseEventParams } from "lightweight-charts";
import { BubbleSeries, BubbleData } from "./bubble-series";
import { VolumeProfileSeries } from "../plugins/VolumeProfile";
import { SessionVPSeries } from "../plugins/SessionVP";
import { RajaSRSeries } from "../plugins/RajaSR";
import { MSBZZSeries } from "../plugins/MSB_ZigZag";
import { TrendExhaustionSeries } from "../plugins/TrendExhaustion";
import { RSI, MACD, EMA, BollingerBands, VWAP, ATR, calculateZigzag } from "../plugins/indicators";
import { DrawingManager } from "../plugins/drawing-tools/core/drawing-manager";
import { TrendlineDrawing } from "../plugins/drawing-tools/tools/trendline";
import { ArrowDrawing } from "../plugins/drawing-tools/tools/arrow";
import { HorizontalLineDrawing } from "../plugins/drawing-tools/tools/horizontal-line";
import { HorizontalRayDrawing } from "../plugins/drawing-tools/tools/horizontal-ray";
import { RectangleDrawing } from "../plugins/drawing-tools/tools/rectangle";
import { MeasureDrawing } from "../plugins/drawing-tools/tools/measure";
import { PositionDrawing } from "../plugins/drawing-tools/tools/position";
import { DrawingToolType, DrawingEvent } from "../plugins/drawing-tools/core/types";
import { DrawingToolbar } from "./drawing-toolbar";
import { DrawingSettingsModal } from "./drawing-settings-modal";
import { ArrowRightToLine, EyeOff, Eye, Settings, X } from "lucide-react";
import { getBaseUrl, getWsUrl } from "@/lib/api";

import { ChartSettings } from "./chart";

const MAX_BARS = 50000;
const RIGHT_SPACE_BARS = 12;

function findIndexAtOrBeforeTime(data: any[], t: number): number {
  let lo = 0;
  let hi = data.length - 1;
  let ans = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    const v = Number(data[mid]?.time);
    if (!Number.isFinite(v)) return -1;
    if (v <= t) {
      ans = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return ans;
}

export interface ChartRef {
  takeScreenshot: () => void;
  captureScreenshotDataUrl: () => string | null;
  enterReplaySelectionMode: () => void;
  togglePlay: () => void;
  setPlaying: (playing: boolean) => void;
  getReplayState: () => { isReplayMode: boolean; isPlaying: boolean; isSelectingReplayStart: boolean; replaySpeed: number };
  nextReplayStep: () => void;
  prevReplayStep: () => void;
  stopReplay: () => void;
  setReplaySpeed: (speed: number) => void;
  syncCrosshair: (param: MouseEventParams) => void;
  syncLogicalRange: (range: LogicalRange | null) => void;
  syncTimeRange: (range: { from: number; to: number } | null) => void;
  removeAllDrawings: () => void;
  removeDrawing: (id: string) => void;
  resetView: () => void;
  scrollToTime: (time: number) => void;
  ensureHistoryBefore: (time: number) => Promise<boolean>;
  getLatestBarTime: () => number | null;
  drawObjects: (objects: any[]) => void;
  removeAiOverlays: () => void;
  startReplayAtTime: (time: number) => void;
  setTradeMarkers: (markers: any[]) => void;
  setBacktestPositions: (trades: any[]) => void;
  clearBacktestPositions: () => void;
  setStudyMarkers: (markers: any[]) => void;
  clearStudyMarkers: () => void;
  // 新选区获取方式（避免“点两次”受绘图层吞事件影响）
  getVisibleTimeRange: () => { from: number; to: number } | null;
  getSelectedRectangleTimeRange: () => { from: number; to: number } | null;
}

export interface ReplayState {
  isReplayMode: boolean;
  isPlaying: boolean;
  isSelectingReplayStart: boolean;
  replaySpeed: number;
}

interface SingleChartProps {
  id: string;
  symbol: string;
  timeframe: string;
  theme: 'dark' | 'light';
  showBubble: boolean;
  showVRVP: boolean;
  showSVP: boolean;
  showRajaSR: boolean;
  showIndB_RSI: boolean;
  showIndB_MACD: boolean;
  showIndB_EMA: boolean;
  showIndB_BB: boolean;
  showIndB_VWAP: boolean;
  showIndB_ATR: boolean;
  showIndB_Zigzag: boolean;
  showIndB_MSB_Zigzag: boolean;
  showIndB_TrendExhaustion: boolean;
  isActive: boolean;
  settings: ChartSettings;
  selectionMode?: boolean;
  onSelectRange?: (fromTime: number, toTime: number, selectionDrawingId?: string) => void;
  onReplayStateChange: (id: string, state: ReplayState) => void;
  onCrosshairMove: (id: string, param: MouseEventParams) => void;
  onRangeChange: (id: string, range: LogicalRange | null) => void;
  onContextMenu: (e: React.MouseEvent, id: string) => void;
  onToggleIndicator?: (indicator: 'VRVP' | 'SVP' | 'RajaSR' | 'RSI' | 'MACD' | 'EMA' | 'BB' | 'VWAP' | 'ATR' | 'Zigzag' | 'MSB_Zigzag' | 'TrendExhaustion') => void;
  onOpenSettings?: (indicator: 'VRVP' | 'SVP' | 'RajaSR' | 'RSI' | 'MACD' | 'EMA' | 'BB' | 'VWAP' | 'ATR' | 'Zigzag' | 'MSB_Zigzag' | 'TrendExhaustion') => void;
}

export const SingleChart = forwardRef<ChartRef, SingleChartProps>(({
  id,
  symbol,
  timeframe,
  theme,
  showBubble,
  showVRVP,
  showSVP,
  showRajaSR,
  showIndB_RSI,
  showIndB_MACD,
  showIndB_EMA,
  showIndB_BB,
  showIndB_VWAP,
  showIndB_ATR,
  showIndB_Zigzag,
  showIndB_MSB_Zigzag,
  showIndB_TrendExhaustion,
  isActive,
  settings,
  selectionMode,
  onSelectRange,
  onReplayStateChange,
  onCrosshairMove,
  onRangeChange,
  onContextMenu,
  onToggleIndicator,
  onOpenSettings
}, ref) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const bubbleSeriesRef = useRef<any>(null);
  const volumeProfileSeriesRef = useRef<any>(null);
  const sessionVPSeriesRef = useRef<any>(null);
  const sessionVPViewRef = useRef<any>(null);
  const rajaSRSeriesRef = useRef<any>(null);
  const rajaSRViewRef = useRef<any>(null);
  const bidLineRef = useRef<any>(null);
  const askLineRef = useRef<any>(null);

  // Indicator B Refs
  const rsiSeriesRef = useRef<any>(null);
  const macdLineSeriesRef = useRef<any>(null);
  const macdSignalSeriesRef = useRef<any>(null);
  const macdHistSeriesRef = useRef<any>(null);
  const ema1SeriesRef = useRef<any>(null);
  const ema2SeriesRef = useRef<any>(null);
  const ema3SeriesRef = useRef<any>(null);
  const ema4SeriesRef = useRef<any>(null);
  const bbUpperSeriesRef = useRef<any>(null);
  const bbMiddleSeriesRef = useRef<any>(null);
  const bbLowerSeriesRef = useRef<any>(null);
  const vwapSeriesRef = useRef<any>(null);
  const atrSeriesRef = useRef<any>(null);
  const zigzagSeriesRef = useRef<any>(null);
  const msbZigzagSeriesRef = useRef<any>(null);
  const msbZigzagViewRef = useRef<any>(null);
  const trendExhaustionSeriesRef = useRef<any>(null);
  const trendExhaustionViewRef = useRef<any>(null);
  
  const indicatorInstancesRef = useRef<any>(null);

  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [hasMoreHistory, setHasMoreHistory] = useState(true);
  const [chartReadyTick, setChartReadyTick] = useState(0);
  
  const dataRef = useRef<any[]>([]);
  const loadingHistoryRef = useRef(false);
  const lastFetchedTimeRef = useRef<number | null>(null);
  const lastUserInteractAtRef = useRef<number>(0);
  const pointerDownRef = useRef<boolean>(false);
  const onRangeChangeRef = useRef(onRangeChange);
  const onCrosshairMoveRef = useRef(onCrosshairMove);

  useEffect(() => {
    onRangeChangeRef.current = onRangeChange;
  }, [onRangeChange]);

  useEffect(() => {
    onCrosshairMoveRef.current = onCrosshairMove;
  }, [onCrosshairMove]);

  // Replay Mode States
  const [isReplayMode, setIsReplayMode] = useState(false);
  const [isSelectingReplayStart, setIsSelectingReplayStart] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [replaySpeed, setReplaySpeed] = useState(1000);
  
  // Local toggle states for the floating legend eyes
  const [hideVRVP, setHideVRVP] = useState(false);
  const [hideSVP, setHideSVP] = useState(false);
  const [hideRajaSR, setHideRajaSR] = useState(false);
  const [hideIndB_RSI, setHideIndB_RSI] = useState(false);
  const [hideIndB_MACD, setHideIndB_MACD] = useState(false);
  const [hideIndB_EMA, setHideIndB_EMA] = useState(false);
  const [hideIndB_BB, setHideIndB_BB] = useState(false);
  const [hideIndB_VWAP, setHideIndB_VWAP] = useState(false);
  const [hideIndB_ATR, setHideIndB_ATR] = useState(false);
  const [hideIndB_Zigzag, setHideIndB_Zigzag] = useState(false);
  const [hideIndB_MSB_Zigzag, setHideIndB_MSB_Zigzag] = useState(false);
  const [hideIndB_TrendExhaustion, setHideIndB_TrendExhaustion] = useState(false);
  
  const [activeTool, setActiveTool] = useState<DrawingToolType>('cursor');
  const [selectedDrawingId, setSelectedDrawingId] = useState<string | null>(null);
  const [settingsModalDrawingId, setSettingsModalDrawingId] = useState<string | null>(null);
  const drawingManagerRef = useRef<DrawingManager | null>(null);
  const pendingBacktestTradesRef = useRef<any[] | null>(null);
  const tradeMarkersRef = useRef<any[]>([]);
  const studyMarkersRef = useRef<any[]>([]);

  const currentSymbolRef = useRef(symbol);
  useEffect(() => {
    currentSymbolRef.current = symbol;
  }, [symbol]);

  const applyMarkers = useCallback(() => {
    const s: any = seriesRef.current as any;
    if (!s || typeof s.setMarkers !== "function") return;
    const merged = [...(tradeMarkersRef.current || []), ...(studyMarkersRef.current || [])];
    // 轻量排序，避免 marker 重叠错乱
    merged.sort((a, b) => (Number(a.time) || 0) - (Number(b.time) || 0));
    try {
      s.setMarkers(merged);
    } catch (e) {
      console.warn("setMarkers failed", e);
    }
  }, []);

  const applyBacktestPositions = useCallback((trades: any[]) => {
    if (!drawingManagerRef.current || !chartRef.current || !seriesRef.current) return;
    const dm = drawingManagerRef.current as any;

    // 清理旧的 backtest drawings（仅清理 id 前缀 bt-）
    try {
      const serialized = dm.serialize?.() || [];
      for (const d of serialized) {
        if (d?.id && String(d.id).startsWith("bt-")) dm.removeDrawing(d.id);
      }
    } catch {}

    const times = (dataRef.current || []).map((d) => d.time);
    if (times.length === 0) return;
    const mapLte = (t: number) => {
      const target = Number(t);
      if (!Number.isFinite(target) || times.length === 0) return null;
      if (target <= times[0]) return times[0];
      for (let i = times.length - 1; i >= 0; i--) {
        if (times[i] <= target) return times[i];
      }
      return times[0];
    };

    for (const tr of (trades || []).slice(-120)) {
      const entryTime = mapLte(tr.entry_time);
      const exitTime = mapLte(tr.exit_time) || entryTime;
      if (!entryTime || !exitTime) continue;

      const toolType = tr.dir === "LONG" ? "long_position" : "short_position";
      const id = `bt-${tr.entry_time}-${tr.exit_time}-${tr.dir}`;
      const drawing = new PositionDrawing(toolType, id);
      // 重要：必须先 attach（addDrawing）再 addPoint，否则 PositionDrawing 无法自动生成 TP/SL 两个点
      dm.addDrawing(drawing);
      drawing.addPoint({ time: entryTime, timeMapped: entryTime, price: Number(tr.entry) });
      drawing.movePoint(1, { time: exitTime, timeMapped: exitTime, price: Number(tr.tp) });
      drawing.movePoint(2, { time: exitTime, timeMapped: exitTime, price: Number(tr.stop) });
    }
    dm.remapAllForTimeframe?.();
  }, []);

  const clearBacktestPositions = useCallback(() => {
    if (!drawingManagerRef.current) return;
    const dm = drawingManagerRef.current as any;
    try {
      const serialized = dm.serialize?.() || [];
      for (const d of serialized) {
        if (d?.id && String(d.id).startsWith("bt-")) dm.removeDrawing(d.id);
      }
    } catch {}
    // 清空回测 IN/OUT markers（不影响其它 markers，例如研究样本）
    tradeMarkersRef.current = [];
    applyMarkers();
  }, []);
  const lastDrawingRemapKeyRef = useRef<string>("");

  const [showScrollToRealTime, setShowScrollToRealTime] = useState(false);

  const isReplayModeRef = useRef(false);
  const isSelectingReplayStartRef = useRef(false);
  const isSelectingRangeRef = useRef(false);
  const rangeStartRef = useRef<number | null>(null);
  const selectionDrawingIdRef = useRef<string | null>(null);
  const selectionPriceRangeRef = useRef<{ low: number; high: number } | null>(null);
  const selectionDrawingRef = useRef<RectangleDrawing | null>(null);

  // Helper state to trigger re-renders for legend values when data updates
  const [, setForceRender] = useState({});

  useEffect(() => {
    let animationFrameId: number;
    const handleUpdate = () => {
      cancelAnimationFrame(animationFrameId);
      animationFrameId = requestAnimationFrame(() => {
        setForceRender({});
      });
    };
    if (chartRef.current) {
      chartRef.current.subscribeCrosshairMove(handleUpdate);
    }
    return () => {
      cancelAnimationFrame(animationFrameId);
      if (chartRef.current) {
        chartRef.current.unsubscribeCrosshairMove(handleUpdate);
      }
    };
  }, []);

  const timeToUnixSeconds = (t: any): number | null => {
    if (t == null) return null;
    if (typeof t === "number") return Math.floor(t);
    if (typeof t === "string") {
      const ms = Date.parse(t);
      if (!Number.isFinite(ms)) return null;
      return Math.floor(ms / 1000);
    }
    // lightweight-charts BusinessDay: {year, month, day}
    if (typeof t === "object" && Number.isFinite(t.year) && Number.isFinite(t.month) && Number.isFinite(t.day)) {
      const ms = Date.UTC(Number(t.year), Number(t.month) - 1, Number(t.day));
      return Math.floor(ms / 1000);
    }
    return null;
  };

  const computeIndicators = useCallback((allData: any[]) => {
    const rsi = new RSI(settings.indB_RsiPeriod);
    const macd = new MACD(settings.indB_MacdFast, settings.indB_MacdSlow, settings.indB_MacdSignal);
    const ema1 = new EMA(settings.indB_Ema1);
    const ema2 = new EMA(settings.indB_Ema2);
    const ema3 = new EMA(settings.indB_Ema3);
    const ema4 = new EMA(settings.indB_Ema4);
    const bb = new BollingerBands(settings.indB_BbPeriod, settings.indB_BbStdDev);
    const atr = new ATR(settings.indB_AtrPeriod);
    const vwap = new VWAP();

    const result = {
      rsiData: [] as any[],
      macdLineData: [] as any[],
      macdSignalData: [] as any[],
      macdHistData: [] as any[],
      ema1Data: [] as any[],
      ema2Data: [] as any[],
      ema3Data: [] as any[],
      ema4Data: [] as any[],
      bbUpperData: [] as any[],
      bbMiddleData: [] as any[],
      bbLowerData: [] as any[],
      atrData: [] as any[],
      vwapData: [] as any[],
      zigzagData: [] as any[],
      instances: { rsi, macd, ema1, ema2, ema3, ema4, bb, atr, vwap }
    };

    for (const d of allData) {
      const time = d.time;
      const c = Number(d.close);
      const h = Number(d.high);
      const l = Number(d.low);
      const v = Number(d.volume) || 0;

      const rsiVal = rsi.next(c);
      if (rsiVal !== null) {
        result.rsiData.push({ time, value: rsiVal });
      }

      const m = macd.next(c);
      if (m.macd !== null) result.macdLineData.push({ time, value: m.macd });
      if (m.signal !== null) result.macdSignalData.push({ time, value: m.signal });
      if (m.histogram !== null) result.macdHistData.push({ time, value: m.histogram, color: m.histogram >= 0 ? 'rgba(38, 166, 154, 0.8)' : 'rgba(239, 83, 80, 0.8)' });

      const e1 = ema1.next(c); if (e1 !== null) result.ema1Data.push({ time, value: e1 });
      const e2 = ema2.next(c); if (e2 !== null) result.ema2Data.push({ time, value: e2 });
      const e3 = ema3.next(c); if (e3 !== null) result.ema3Data.push({ time, value: e3 });
      const e4 = ema4.next(c); if (e4 !== null) result.ema4Data.push({ time, value: e4 });

      const b = bb.next(c);
      if (b.middle !== null) result.bbMiddleData.push({ time, value: b.middle });
      if (b.upper !== null) result.bbUpperData.push({ time, value: b.upper });
      if (b.lower !== null) result.bbLowerData.push({ time, value: b.lower });

      const a = atr.next(h, l, c);
      if (a !== null) result.atrData.push({ time, value: a });

      const tUnix = timeToUnixSeconds(time) || 0;
      const vw = vwap.next(h, l, c, v, tUnix);
      if (vw !== null) result.vwapData.push({ time, value: vw });
    }

    result.zigzagData = calculateZigzag(allData, settings.indB_ZigzagDeviation);

    indicatorInstancesRef.current = result.instances;
    return result;
  }, [settings]);

  // 选区/回放选点：统一处理函数（支持来自 DOM click 或 chart.subscribeClick）
  const handleSelectionOrReplayClick = (chart: any, tRaw: any) => {
    // 选区模式：点击两次确定 from/to
    if (isSelectingRangeRef.current) {
      const tUnix = timeToUnixSeconds(tRaw);
      console.debug("[selection] click", { tRaw, tUnix, hasStart: rangeStartRef.current != null });
      if (tUnix == null) return true; // handled

      if (rangeStartRef.current == null) {
        rangeStartRef.current = tUnix;
        console.debug("[selection] start", tUnix);
        // 创建一个可视化选区框（固定纵向范围为当前可视 price range）
        const dm = drawingManagerRef.current;
        if (dm && seriesRef.current) {
          const pr =
            (seriesRef.current as any)?.priceScale?.()?.getVisiblePriceRange?.() ||
            (chartRef.current as any)?.priceScale?.("right")?.getVisiblePriceRange?.() ||
            null;
          let low = 0;
          let high = 0;
          if (pr && Number.isFinite(pr.from) && Number.isFinite(pr.to)) {
            low = Math.min(pr.from, pr.to);
            high = Math.max(pr.from, pr.to);
          } else {
            // fallback：用最近 150 根的 high/low
            const tail = dataRef.current.slice(Math.max(0, dataRef.current.length - 150));
            low = Math.min(...tail.map((d) => Number(d.low)));
            high = Math.max(...tail.map((d) => Number(d.high)));
          }
          selectionPriceRangeRef.current = { low, high };
          const did = `selection_${Date.now()}_${Math.random().toString(16).slice(2)}`;
          selectionDrawingIdRef.current = did;
          const d = new RectangleDrawing(did);
          d.updateStyle({ lineColor: "#fbbf24", fillColor: "#fbbf24", fillOpacity: 0.12, lineWidth: 1 } as any);
          dm.addDrawing(d);
          // 以可视区间低点作为起点，临时点随鼠标移动
          d.addPoint({ time: tRaw, price: low });
          d.updateTempPoint({ time: tRaw, price: high });
          selectionDrawingRef.current = d;
        }
        // 用黄色提示“已选中起点”
        chart.applyOptions({
          crosshair: {
            vertLine: {
              color: "#fbbf24",
              width: 2,
              style: 0,
            },
          },
        });
        return true;
      }

      const a = rangeStartRef.current;
      rangeStartRef.current = null;
      isSelectingRangeRef.current = false;
      console.debug("[selection] finalize", { from: Math.min(a, tUnix), to: Math.max(a, tUnix) });
      const selectionId = selectionDrawingIdRef.current || undefined;
      // 恢复默认 crosshair 颜色
      chart.applyOptions({
        crosshair: {
          vertLine: {
            color: theme === "dark" ? "#758696" : "#2B2B43",
            width: 1,
            style: 3,
          },
        },
      });
      const from = Math.min(a, tUnix);
      const to = Math.max(a, tUnix);
      // finalize selection box（第二个点：高点；时间=终点）
      try {
        const pr = selectionPriceRangeRef.current;
        const d = selectionDrawingRef.current;
        if (d && pr) d.addPoint({ time: tRaw, price: pr.high });
      } catch {}
      onSelectRange?.(from, to, selectionId);
      return true;
    }

    // 回放选起点
    if (isSelectingReplayStartRef.current) {
      const tUnix = timeToUnixSeconds(tRaw);
      if (tUnix == null) return true;
      // 找到 <= tUnix 的最近一根
      let timeIndex = -1;
      for (let i = dataRef.current.length - 1; i >= 0; i--) {
        if (Number(dataRef.current[i].time) <= tUnix) {
          timeIndex = i;
          break;
        }
      }
      if (timeIndex !== -1) {
        setIsSelectingReplayStart(false);
        chart.applyOptions({
          crosshair: {
            vertLine: {
              color: theme === "dark" ? "#758696" : "#2B2B43",
              width: 1,
              style: 3,
            },
          },
        });
        setIsReplayMode(true);
        replayIndexRef.current = timeIndex + 1;
        setData([...dataRef.current]);
      }
      return true;
    }

    return false;
  };
  const replayIndexRef = useRef<number>(-1);
  const replayIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const lastAutoScaledRef = useRef<string>("");
  const lastRightSpaceKeyRef = useRef<string>("");
  
  const lastSyncedStateRef = useRef<string>("");

  // Sync state to parent
  const prevReplayStep = useCallback(() => {
    if (replayIndexRef.current > 1) {
      replayIndexRef.current -= 1;
      const slicedData = dataRef.current.slice(0, replayIndexRef.current);
      
      seriesRef.current?.setData(slicedData);
      bubbleSeriesRef.current?.setData(slicedData.map(d => ({
        time: d.time,
        high: d.high,
        low: d.low,
        delta: d.delta_volume || 0,
      })));
      volumeProfileSeriesRef.current?.setData(slicedData.map(d => ({
        time: d.time,
        open: d.open,
        high: d.high,
        low: d.low,
        close: d.close,
        volume: d.volume || 0,
      })));

      const mappedSlicedData = slicedData.map(d => ({
        time: d.time,
        open: d.open,
        high: d.high,
        low: d.low,
        close: d.close,
        volume: d.volume || 0,
        }));
        sessionVPSeriesRef.current?.setData(mappedSlicedData);
        sessionVPViewRef.current?.setFullData(mappedSlicedData);
        rajaSRSeriesRef.current?.setData(mappedSlicedData);
        rajaSRViewRef.current?.setFullData(mappedSlicedData);

        const inds = computeIndicators(slicedData);
        rsiSeriesRef.current?.setData(inds.rsiData);
        macdLineSeriesRef.current?.setData(inds.macdLineData);
        macdSignalSeriesRef.current?.setData(inds.macdSignalData);
        macdHistSeriesRef.current?.setData(inds.macdHistData);
        ema1SeriesRef.current?.setData(inds.ema1Data);
        ema2SeriesRef.current?.setData(inds.ema2Data);
        ema3SeriesRef.current?.setData(inds.ema3Data);
        ema4SeriesRef.current?.setData(inds.ema4Data);
        bbUpperSeriesRef.current?.setData(inds.bbUpperData);
        bbMiddleSeriesRef.current?.setData(inds.bbMiddleData);
        bbLowerSeriesRef.current?.setData(inds.bbLowerData);
        atrSeriesRef.current?.setData(inds.atrData);
        vwapSeriesRef.current?.setData(inds.vwapData);
        zigzagSeriesRef.current?.setData(inds.zigzagData);
        
        if (mappedSlicedData.length > 0) {
          msbZigzagSeriesRef.current?.setData(mappedSlicedData);
          msbZigzagViewRef.current?.setFullData(mappedSlicedData);
          trendExhaustionSeriesRef.current?.setData(mappedSlicedData);
          trendExhaustionViewRef.current?.setFullData(mappedSlicedData);
        }

        const nextData = slicedData[slicedData.length - 1];
      if (bidLineRef.current && nextData) {
        bidLineRef.current.applyOptions({ price: nextData.close });
      }
      if (askLineRef.current && nextData) {
        askLineRef.current.applyOptions({ price: nextData.close + 0.5 });
      }

      if (chartRef.current && chartContainerRef.current) {
        const timeScale = chartRef.current.timeScale();
        const logicalRange = timeScale.getVisibleLogicalRange();
        if (logicalRange) {
          const visibleBars = logicalRange.to - logicalRange.from;
          const targetOffset = Math.floor(visibleBars / 4);
          timeScale.applyOptions({ rightOffset: targetOffset });
        }
      }
    }
  }, []);

  useEffect(() => {
    // To prevent infinite render loops when parent updates its state
    // we should only call onReplayStateChange if something actually changed.
    // However, since we are passing primitives, the simplest way to avoid
    // the infinite loop is to stringify the state or rely on a ref to check if it changed.
    
    const currentStateStr = JSON.stringify({
      isReplayMode,
      isPlaying,
      isSelectingReplayStart,
      replaySpeed
    });
    
    if (lastSyncedStateRef.current !== currentStateStr) {
      lastSyncedStateRef.current = currentStateStr;
      onReplayStateChange(id, {
        isReplayMode,
        isPlaying,
        isSelectingReplayStart,
        replaySpeed
      });
    }
  }, [id, isReplayMode, isPlaying, isSelectingReplayStart, replaySpeed, onReplayStateChange]);

  useEffect(() => {
    isReplayModeRef.current = isReplayMode;
    isSelectingReplayStartRef.current = isSelectingReplayStart;
  }, [isReplayMode, isSelectingReplayStart]);

  useEffect(() => {
    isSelectingRangeRef.current = !!selectionMode;
    // 进入选区模式时，强制切回 Cursor，避免绘图工具“placing/dragging”吞掉点击事件
    if (selectionMode) {
      setActiveTool("cursor");
      try {
        if (drawingManagerRef.current) drawingManagerRef.current.activeTool = "cursor";
      } catch {}
    }
    if (!selectionMode) {
      // 如果选区还在“第一下已点”的中间态，说明用户取消了选区：清掉临时框
      if (rangeStartRef.current != null && selectionDrawingIdRef.current && drawingManagerRef.current) {
        drawingManagerRef.current.removeDrawing(selectionDrawingIdRef.current);
      }
      rangeStartRef.current = null;
      selectionPriceRangeRef.current = null;
      selectionDrawingIdRef.current = null;
      selectionDrawingRef.current = null;
    }
  }, [selectionMode]);

  useEffect(() => {
    dataRef.current = data;
  }, [data]);

  // WebSocket connection for real-time updates
  useEffect(() => {
    if (!symbol || !timeframe) return;

    let ws: WebSocket | null = null;
    let isMounted = true;
    let timeoutId: ReturnType<typeof setTimeout>;
    
    const connectWS = () => {
      const wsHost = getWsUrl();
      const wsUrl = `${wsHost}/api/ws/${symbol}/${timeframe}`;
      
      ws = new WebSocket(wsUrl);
      
      ws.onopen = () => {
        console.log(`WebSocket connected: ${symbol} ${timeframe}`);
      };
      
      ws.onmessage = (event) => {
        if (!isMounted) return;
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "update" && msg.data) {
            // Update data array
            const newBar = msg.data;
            setData(prev => {
              // If it's a new bar or update to current bar
              const lastBar = prev[prev.length - 1];
              if (lastBar && lastBar.time === newBar.time) {
                // Update existing
                const updated = [...prev];
                updated[updated.length - 1] = newBar;
                return updated;
              } else if (!lastBar || newBar.time > lastBar.time) {
                // Append new
                const next = [...prev, newBar];
                if (next.length > MAX_BARS) return next.slice(next.length - MAX_BARS);
                return next;
              }
              return prev;
            });
          }
        } catch (e) {
          console.error("WS message error", e);
        }
      };
      
      ws.onclose = () => {
        console.log(`WebSocket disconnected: ${symbol} ${timeframe}`);
        if (isMounted) {
          // Reconnect after 3 seconds
          timeoutId = setTimeout(connectWS, 3000);
        }
      };
    };
    
    connectWS();
    
    return () => {
      isMounted = false;
      if (timeoutId) clearTimeout(timeoutId);
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.onclose = null;
        ws.close();
      }
    };
  }, [symbol, timeframe]);

  // Fetch initial data
  useEffect(() => {
    if (!symbol) {
      setLoading(false);
      return;
    }
    const fetchData = async () => {
      setLoading(true);
      setHasMoreHistory(true);
      lastFetchedTimeRef.current = null;
      try {
        const res = await fetch(`${getBaseUrl()}/api/history?symbol=${symbol}&timeframe=${timeframe}&limit=2000`);
        if (!res.ok) {
          setData([]);
          throw new Error(`API error: ${res.status}`);
        }
        const json = await res.json();
        
        // Remove duplicates and sort by time ascending just in case
        const uniqueData = Array.from(new Map(json.map((item: any) => [item.time, item])).values());
        uniqueData.sort((a: any, b: any) => a.time - b.time);
        
        setData(uniqueData as any[]);
      } catch (error) {
        console.error("Failed to fetch data:", error);
        setData([]);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [timeframe, symbol]);

  const fetchHistoricalData = useCallback(async (beforeTime: number) => {
    if (!symbol || loadingHistoryRef.current || !hasMoreHistory || lastFetchedTimeRef.current === beforeTime) return;
    
    loadingHistoryRef.current = true;
    setLoadingHistory(true);
    lastFetchedTimeRef.current = beforeTime;
    
    try {
        const res = await fetch(`${getBaseUrl()}/api/history?symbol=${symbol}&timeframe=${timeframe}&limit=2000&before_time=${beforeTime}`);
        if (!res.ok) throw new Error(`API error: ${res.status}`);
        
        const json = await res.json();
      
      if (json.length === 0) {
        setHasMoreHistory(false);
      } else {
        setData(prevData => {
          let newData = [...json, ...prevData];
          // Remove duplicates
          newData = Array.from(new Map(newData.map(item => [item.time, item])).values());
          newData.sort((a, b) => a.time - b.time);
          
          if (newData.length > MAX_BARS) newData = newData.slice(0, MAX_BARS);
          return newData;
        });
      }
    } catch (error) {
      console.error("Failed to fetch historical data:", error);
    } finally {
      loadingHistoryRef.current = false;
      setLoadingHistory(false);
    }
  }, [symbol, timeframe, hasMoreHistory]);

  // Chart initialization and theme changes
  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: theme === "dark" ? "#000000" : "#ffffff" },
        textColor: theme === "dark" ? "#d1d4dc" : "#131722",
      },
      width: chartContainerRef.current.clientWidth,
      height: chartContainerRef.current.clientHeight,
      grid: {
        vertLines: { color: theme === "dark" ? "#2B2B43" : "#e0e3eb" },
        horzLines: { color: theme === "dark" ? "#2B2B43" : "#e0e3eb" },
      },
      timeScale: {
        borderColor: theme === "dark" ? "#2B2B43" : "#e0e3eb",
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 12, // Default small right offset
        barSpacing: 6,
        minBarSpacing: 0.5,
        shiftVisibleRangeOnNewBar: true,
      },
      rightPriceScale: {
        borderColor: theme === "dark" ? "#2B2B43" : "#e0e3eb",
      },
      crosshair: {
        mode: CrosshairMode.Normal,
      },
      handleScroll: {
        mouseWheel: true,
        pressedMouseMove: true,
      },
      handleScale: {
        axisPressedMouseMove: true,
        mouseWheel: true,
        pinch: true,
      }
    });

    // Unfortunately, the lightweight-charts library (free version) automatically adds
    // a TradingView logo to the bottom left. We can hide it using CSS.
    if (chartContainerRef.current) {
      const tvLogo = chartContainerRef.current.querySelector('a[href*="tradingview"]');
      if (tvLogo) {
        (tvLogo as HTMLElement).style.display = 'none';
      }
    }

    chartRef.current = chart;

    const candlestickSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#00bfa5",
      downColor: "#ff4444",
      borderVisible: false,
      wickUpColor: "#00bfa5",
      wickDownColor: "#ff4444",
    });

    seriesRef.current = candlestickSeries;

    const bubbleSeries = chart.addCustomSeries(new BubbleSeries(), {
      minRadius: 8,
      maxRadius: 30,
      lastValueVisible: false,
      priceLineVisible: false,
      visible: showBubble,
    });
    bubbleSeriesRef.current = bubbleSeries;

    const volumeProfileSeries = chart.addCustomSeries(new VolumeProfileSeries(), {
      lastValueVisible: false,
      priceLineVisible: false,
      visible: showVRVP,
    });
    volumeProfileSeriesRef.current = volumeProfileSeries;

    const svpView = new SessionVPSeries(chart);
      const svpSeries = chart.addCustomSeries(svpView, {
        lastValueVisible: false,
        priceLineVisible: false,
        visible: showSVP,
      });
      sessionVPViewRef.current = svpView;
      sessionVPSeriesRef.current = svpSeries;

      const rajaView = new RajaSRSeries(chart);
    const rajaSeries = chart.addCustomSeries(rajaView as any, {
      lastValueVisible: false,
      priceLineVisible: false,
      visible: showRajaSR,
    });
    rajaSRViewRef.current = rajaView;
    rajaSRSeriesRef.current = rajaSeries;

    // --- INDICATOR B INITIALIZATION ---
    // Overlay indicators (right scale)
    const overlayProps = { lineWidth: 2 as const, crosshairMarkerVisible: false, lastValueVisible: false, priceLineVisible: false };
    ema1SeriesRef.current = chart.addSeries(LineSeries, { ...overlayProps, color: settings.indB_Ema1Color });
    ema2SeriesRef.current = chart.addSeries(LineSeries, { ...overlayProps, color: settings.indB_Ema2Color });
    ema3SeriesRef.current = chart.addSeries(LineSeries, { ...overlayProps, color: settings.indB_Ema3Color });
    ema4SeriesRef.current = chart.addSeries(LineSeries, { ...overlayProps, color: settings.indB_Ema4Color });
    
    // We parse the BB color to add transparency for upper/lower bands
    const hexToRgba = (hex: string, alpha: number) => {
      let r = 33, g = 150, b = 243;
      if (hex.startsWith('#')) {
        const h = hex.replace('#', '');
        if (h.length === 3) {
          r = parseInt(h.charAt(0) + h.charAt(0), 16);
          g = parseInt(h.charAt(1) + h.charAt(1), 16);
          b = parseInt(h.charAt(2) + h.charAt(2), 16);
        } else if (h.length === 6) {
          r = parseInt(h.substring(0, 2), 16);
          g = parseInt(h.substring(2, 4), 16);
          b = parseInt(h.substring(4, 6), 16);
        }
      } else if (hex.startsWith('rgb')) {
        const parts = hex.match(/\d+/g);
        if (parts && parts.length >= 3) {
          r = parseInt(parts[0]);
          g = parseInt(parts[1]);
          b = parseInt(parts[2]);
        }
      }
      return `rgba(${r}, ${g}, ${b}, ${alpha})`;
    };

    bbUpperSeriesRef.current = chart.addSeries(LineSeries, { color: hexToRgba(settings.indB_BbColor, 0.5), lineWidth: 1, lastValueVisible: false, priceLineVisible: false });
    bbMiddleSeriesRef.current = chart.addSeries(LineSeries, { color: settings.indB_BbColor, lineWidth: 1, lastValueVisible: false, priceLineVisible: false });
    bbLowerSeriesRef.current = chart.addSeries(LineSeries, { color: hexToRgba(settings.indB_BbColor, 0.5), lineWidth: 1, lastValueVisible: false, priceLineVisible: false });

    vwapSeriesRef.current = chart.addSeries(LineSeries, { color: settings.indB_VwapColor, lineWidth: 2, lastValueVisible: false, priceLineVisible: false });

    // Pane indicators (custom scales)
    const RSI_SCALE = 'rsi_scale';
    rsiSeriesRef.current = chart.addSeries(LineSeries, {
      color: settings.indB_RsiColor,
      lineWidth: 2,
      priceScaleId: RSI_SCALE,
      title: 'RSI'
    });
    chart.priceScale(RSI_SCALE).applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
      autoScale: true,
      visible: true
    });

    const MACD_SCALE = 'macd_scale';
    macdHistSeriesRef.current = chart.addSeries(HistogramSeries, {
      priceScaleId: MACD_SCALE,
      title: 'MACD Hist'
    });
    macdLineSeriesRef.current = chart.addSeries(LineSeries, {
      color: settings.indB_MacdLineColor,
      lineWidth: 2,
      priceScaleId: MACD_SCALE,
      title: 'MACD'
    });
    macdSignalSeriesRef.current = chart.addSeries(LineSeries, {
      color: settings.indB_MacdSignalColor,
      lineWidth: 2,
      priceScaleId: MACD_SCALE,
      title: 'Signal'
    });
    chart.priceScale(MACD_SCALE).applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
      autoScale: true,
      visible: true
    });

    const ATR_SCALE = 'atr_scale';
    atrSeriesRef.current = chart.addSeries(LineSeries, {
      color: settings.indB_AtrColor,
      lineWidth: 2,
      priceScaleId: ATR_SCALE,
      title: 'ATR'
    });
    chart.priceScale(ATR_SCALE).applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
      autoScale: true,
      visible: true
    });

    zigzagSeriesRef.current = chart.addSeries(LineSeries, {
      color: settings.indB_ZigzagColor,
      lineWidth: (settings.indB_ZigzagWidth || 2) as any,
      lastValueVisible: false,
      priceLineVisible: false,
      visible: showIndB_Zigzag && !hideIndB_Zigzag,
    });

    msbZigzagViewRef.current = new MSBZZSeries(chart);
    msbZigzagSeriesRef.current = chart.addCustomSeries(msbZigzagViewRef.current, {
      lastValueVisible: false,
      priceLineVisible: false,
      visible: showIndB_MSB_Zigzag && !hideIndB_MSB_Zigzag,
      pivotPeriod: settings.indB_MSB_ZigzagLength || 5,
      zigZagColor: settings.indB_MSB_ZigzagColor || '#FF9800',
      zigZagWidth: settings.indB_MSB_ZigzagWidth || 1,
      showZigZag: settings.indB_MSB_showZigZag ?? true,
      zigZagStyle: settings.indB_MSB_zigZagStyle ?? 0,
      showLabel: settings.indB_MSB_showLabel ?? false,
      labelColor: settings.indB_MSB_labelColor ?? '#0a378a',
      showMajorBuBoS: settings.indB_MSB_showMajorBuBoS ?? true,
      majorBuBoSStyle: settings.indB_MSB_majorBuBoSStyle ?? 0,
      majorBuBoSColor: settings.indB_MSB_majorBuBoSColor ?? '#0B5FCC',
      showMajorBeBoS: settings.indB_MSB_showMajorBeBoS ?? true,
      majorBeBoSStyle: settings.indB_MSB_majorBeBoSStyle ?? 0,
      majorBeBoSColor: settings.indB_MSB_majorBeBoSColor ?? '#C07B05',
      showMinorBuBoS: settings.indB_MSB_showMinorBuBoS ?? false,
      minorBuBoSStyle: settings.indB_MSB_minorBuBoSStyle ?? 2,
      minorBuBoSColor: settings.indB_MSB_minorBuBoSColor ?? '#000000',
      showMinorBeBoS: settings.indB_MSB_showMinorBeBoS ?? false,
      minorBeBoSStyle: settings.indB_MSB_minorBeBoSStyle ?? 2,
      minorBeBoSColor: settings.indB_MSB_minorBeBoSColor ?? '#000000',
      showMajorBuChoCh: settings.indB_MSB_showMajorBuChoCh ?? true,
      majorBuChoChStyle: settings.indB_MSB_majorBuChoChStyle ?? 0,
      majorBuChoChColor: settings.indB_MSB_majorBuChoChColor ?? '#057718',
      showMajorBeChoCh: settings.indB_MSB_showMajorBeChoCh ?? true,
      majorBeChoChStyle: settings.indB_MSB_majorBeChoChStyle ?? 0,
      majorBeChoChColor: settings.indB_MSB_majorBeChoChColor ?? '#86173A',
      showMinorBuChoCh: settings.indB_MSB_showMinorBuChoCh ?? false,
      minorBuChoChStyle: settings.indB_MSB_minorBuChoChStyle ?? 2,
      minorBuChoChColor: settings.indB_MSB_minorBuChoChColor ?? '#000000',
      showMinorBeChoCh: settings.indB_MSB_showMinorBeChoCh ?? false,
      minorBeChoChStyle: settings.indB_MSB_minorBeChoChStyle ?? 2,
      minorBeChoChColor: settings.indB_MSB_minorBeChoChColor ?? '#000000',
    } as any);

    trendExhaustionViewRef.current = new TrendExhaustionSeries(chart);
    trendExhaustionSeriesRef.current = chart.addCustomSeries(trendExhaustionViewRef.current, {
      lastValueVisible: false,
      priceLineVisible: false,
      visible: showIndB_TrendExhaustion && !hideIndB_TrendExhaustion,
      colorBull: settings.indB_TE_colorBull ?? '#2466A7',
      colorBear: settings.indB_TE_colorBear ?? '#CA0017',
      threshold: settings.indB_TE_threshold ?? 20,
      shortLength: settings.indB_TE_shortLength ?? 21,
      shortSmoothingLength: settings.indB_TE_shortSmoothingLength ?? 7,
      longLength: settings.indB_TE_longLength ?? 112,
      longSmoothingLength: settings.indB_TE_longSmoothingLength ?? 3,
      showBoxes: settings.indB_TE_showBoxes ?? true,
      showShapes: settings.indB_TE_showShapes ?? true,
    } as any);

    // We must adjust the main scale margin if any pane is active, but we can do that in an effect
    // ----------------------------------

    // Restore data if available
    if (dataRef.current.length > 0) {
      if (isReplayModeRef.current && replayIndexRef.current >= 0) {
        const slicedData = dataRef.current.slice(0, replayIndexRef.current);
        candlestickSeries.setData(slicedData);
        bubbleSeries.setData(slicedData.map(d => ({
          time: d.time,
          high: d.high,
          low: d.low,
          delta: d.delta_volume || 0,
        })));
        volumeProfileSeries.setData(slicedData.map(d => ({
          time: d.time,
          open: d.open,
          high: d.high,
          low: d.low,
          close: d.close,
          volume: d.volume || 0,
        })));
        
        const mappedSlicedData = slicedData.map(d => ({
          time: d.time,
          open: d.open,
          high: d.high,
          low: d.low,
          close: d.close,
          volume: d.volume || 0,
        }));
        svpSeries.setData(mappedSlicedData);
        svpView.setFullData(mappedSlicedData);
        rajaSeries.setData(mappedSlicedData);
        rajaView.setFullData(mappedSlicedData);

        const inds = computeIndicators(slicedData);
        rsiSeriesRef.current.setData(inds.rsiData);
        macdLineSeriesRef.current.setData(inds.macdLineData);
        macdSignalSeriesRef.current.setData(inds.macdSignalData);
        macdHistSeriesRef.current.setData(inds.macdHistData);
        ema1SeriesRef.current.setData(inds.ema1Data);
        ema2SeriesRef.current.setData(inds.ema2Data);
        ema3SeriesRef.current.setData(inds.ema3Data);
        ema4SeriesRef.current.setData(inds.ema4Data);
        bbUpperSeriesRef.current.setData(inds.bbUpperData);
        bbMiddleSeriesRef.current.setData(inds.bbMiddleData);
        bbLowerSeriesRef.current.setData(inds.bbLowerData);
        atrSeriesRef.current.setData(inds.atrData);
        vwapSeriesRef.current.setData(inds.vwapData);
        zigzagSeriesRef.current.setData(inds.zigzagData);
        if (mappedSlicedData.length > 0) {
          msbZigzagSeriesRef.current.setData(mappedSlicedData);
          msbZigzagViewRef.current.setFullData(mappedSlicedData);
          trendExhaustionSeriesRef.current.setData(mappedSlicedData);
          trendExhaustionViewRef.current.setFullData(mappedSlicedData);
        }

      } else {
        candlestickSeries.setData(dataRef.current);
        bubbleSeries.setData(dataRef.current.map(d => ({
          time: d.time,
          high: d.high,
          low: d.low,
          delta: d.delta_volume || 0,
        })));
        volumeProfileSeries.setData(dataRef.current.map(d => ({
          time: d.time,
          open: d.open,
          high: d.high,
          low: d.low,
          close: d.close,
          volume: d.volume || 0,
        })));
        
        const mappedData = dataRef.current.map(d => ({
          time: d.time,
          open: d.open,
          high: d.high,
          low: d.low,
          close: d.close,
          volume: d.volume || 0,
        }));
        svpSeries.setData(mappedData);
        svpView.setFullData(mappedData);
        rajaSeries.setData(mappedData);
        rajaView.setFullData(mappedData);

        const inds = computeIndicators(dataRef.current);
        rsiSeriesRef.current.setData(inds.rsiData);
        macdLineSeriesRef.current.setData(inds.macdLineData);
        macdSignalSeriesRef.current.setData(inds.macdSignalData);
        macdHistSeriesRef.current.setData(inds.macdHistData);
        ema1SeriesRef.current.setData(inds.ema1Data);
        ema2SeriesRef.current.setData(inds.ema2Data);
        ema3SeriesRef.current.setData(inds.ema3Data);
        ema4SeriesRef.current.setData(inds.ema4Data);
        bbUpperSeriesRef.current.setData(inds.bbUpperData);
        bbMiddleSeriesRef.current.setData(inds.bbMiddleData);
        bbLowerSeriesRef.current.setData(inds.bbLowerData);
        atrSeriesRef.current.setData(inds.atrData);
        vwapSeriesRef.current.setData(inds.vwapData);
        zigzagSeriesRef.current.setData(inds.zigzagData);
        if (mappedData.length > 0) {
          msbZigzagSeriesRef.current.setData(mappedData);
          msbZigzagViewRef.current.setFullData(mappedData);
          trendExhaustionSeriesRef.current.setData(mappedData);
          trendExhaustionViewRef.current.setFullData(mappedData);
        }

        if (dataRef.current.length <= 1000) {
          chart.timeScale().fitContent();
          chart.timeScale().applyOptions({ rightOffset: RIGHT_SPACE_BARS });
        }
      }
    }

    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({
          width: chartContainerRef.current.clientWidth,
          height: chartContainerRef.current.clientHeight,
        });
      }
    };
    
    const resizeObserver = new ResizeObserver(handleResize);
    resizeObserver.observe(chartContainerRef.current);

    const onVisibleLogicalRangeChanged = (newVisibleLogicalRange: LogicalRange | null) => {
      if (newVisibleLogicalRange === null) return;
      
      if (dataRef.current.length > 0 && (pointerDownRef.current || Date.now() - lastUserInteractAtRef.current < 400)) {
        onRangeChangeRef.current(id, newVisibleLogicalRange);
      }

      if (chartRef.current && dataRef.current.length > 0) {
        const ts = chartRef.current.timeScale();
        // Calculate distance to the newest bar. Logical range 'to' index.
        const distanceToRight = dataRef.current.length - newVisibleLogicalRange.to;
        // If user scrolls left more than ~5 bars, show the button
        setShowScrollToRealTime(distanceToRight > 5);
      }

      if (isReplayModeRef.current) return;
      if (newVisibleLogicalRange.from < 50 && dataRef.current.length > 0) {
        const oldestTime = dataRef.current[0].time;
        fetchHistoricalData(oldestTime);
      }
    };
    chart.timeScale().subscribeVisibleLogicalRangeChange(onVisibleLogicalRangeChanged);

    const handleCrosshairMove = (param: MouseEventParams) => {
      // Notify parent for sync
      onCrosshairMoveRef.current(id, param);

      // 选区模式：动态更新选区框（只更新 time，价格固定为当前可视区间）
      if (isSelectingRangeRef.current && rangeStartRef.current != null && selectionDrawingRef.current && (param.time || param.point)) {
        const pr = selectionPriceRangeRef.current;
        if (pr) {
          const tRaw = (param.time as any) ?? (chart.timeScale().coordinateToTime(param.point!.x) as any);
          if (tRaw != null) selectionDrawingRef.current.updateTempPoint({ time: tRaw, price: pr.high });
        }
      }

      if (!isSelectingReplayStartRef.current) return;
      // 注意：在空白区域 param.time 可能为 undefined，此时仍允许显示“选中态”的提示线
      if (param.point === undefined || param.point.x < 0 || param.point.y < 0) {
        chart.applyOptions({
          crosshair: {
            vertLine: {
              color: theme === "dark" ? "#758696" : "#2B2B43",
              width: 1,
              style: 3,
            }
          }
        });
        return;
      }
      chart.applyOptions({
        crosshair: {
          vertLine: {
            color: '#00ff00',
            width: 2,
            style: 0,
          }
        }
      });
    };
    chart.subscribeCrosshairMove(handleCrosshairMove);
    
    const handleClick = (param: MouseEventParams) => {
      if (param.point === undefined) return;
      const tRaw = (param.time as any) ?? (chart.timeScale().coordinateToTime(param.point.x) as any);
      if (tRaw == null) return;
      handleSelectionOrReplayClick(chart, tRaw);
    };
    chart.subscribeClick(handleClick);

    const onWheel = () => {
      lastUserInteractAtRef.current = Date.now();
    };
    const onMouseDown = () => {
      pointerDownRef.current = true;
      lastUserInteractAtRef.current = Date.now();
    };
    const onTouchStart = () => {
      pointerDownRef.current = true;
      lastUserInteractAtRef.current = Date.now();
    };
    const onMouseUp = () => {
      pointerDownRef.current = false;
    };

    chartContainerRef.current?.addEventListener("wheel", onWheel, { passive: true } as any);
    chartContainerRef.current?.addEventListener("mousedown", onMouseDown, true);
    chartContainerRef.current?.addEventListener("touchstart", onTouchStart, { passive: true } as any);
    window.addEventListener("mouseup", onMouseUp, true);

    // DOM 层兜底：绘图层会在 mousedown 里 stopPropagation（尤其是命中 rectangle body 会进入 dragging），
    // 导致选区第二次点击永远到不了 chart.subscribeClick。
    // 这里用 mousedown + capture + stopImmediatePropagation 先截获事件，确保“点两次”能完成。
    const domMouseDown = (ev: MouseEvent) => {
      if (!chartContainerRef.current) return;
      if (!isSelectingRangeRef.current && !isSelectingReplayStartRef.current) return;
      const rect = chartContainerRef.current.getBoundingClientRect();
      const x = ev.clientX - rect.left;
      const y = ev.clientY - rect.top;
      if (x < 0 || y < 0 || x > rect.width || y > rect.height) return;
      const t = (chart.timeScale().coordinateToTime(x) as any) ?? null;
      if (t == null) return;
      // 阻止 overlay/工具吞事件（选区期间我们只想要“点两次”）
      ev.preventDefault();
      (ev as any).stopImmediatePropagation?.();
      ev.stopPropagation();
      handleSelectionOrReplayClick(chart, t);
    };
    chartContainerRef.current?.addEventListener("mousedown", domMouseDown, true);

    // Initialize DrawingManager
    if (chartContainerRef.current) {
      drawingManagerRef.current = new DrawingManager(
        chart,
        candlestickSeries,
        chartContainerRef.current,
        (toolType, id) => {
          if (toolType === 'trendline') return new TrendlineDrawing(id);
          if (toolType === 'arrow') return new ArrowDrawing(id);
          if (toolType === 'horizontal_line') return new HorizontalLineDrawing(id);
          if (toolType === 'horizontal_ray') return new HorizontalRayDrawing(id);
          if (toolType === 'rectangle') return new RectangleDrawing(id);
          if (toolType === 'measure') return new MeasureDrawing(id);
          if (toolType === 'long_position' || toolType === 'short_position') return new PositionDrawing(toolType, id);
          return null;
        }
      );

      const storageKey = `drawing-tools-${symbol}`;
      const stylesStorageKey = `drawing-tools-styles-${symbol}`;
      try {
        const stored = localStorage.getItem(storageKey);
        if (stored) {
          drawingManagerRef.current.deserialize(JSON.parse(stored));
        }
        const storedStyles = localStorage.getItem(stylesStorageKey);
        if (storedStyles) {
          drawingManagerRef.current.deserializeDefaultStyles(JSON.parse(storedStyles));
        }
      } catch (e) {
        console.error('Failed to load drawing tools', e);
      }

      drawingManagerRef.current.addEventListener((event: DrawingEvent) => {
        if (event.type === 'toolChanged' && event.toolType) {
          setActiveTool(event.toolType);
        }
        if (event.type === 'selected' && event.drawingId) {
          setSelectedDrawingId(event.drawingId);
        }
        if (event.type === 'deselected') {
          setSelectedDrawingId(null);
          setSettingsModalDrawingId(null);
        }
        if (event.type === 'deleted') {
          setSelectedDrawingId(curr => curr === event.drawingId ? null : curr);
          setSettingsModalDrawingId(curr => curr === event.drawingId ? null : curr);
        }
        if (event.type === 'doubleClicked' && event.drawingId) {
          setSettingsModalDrawingId(event.drawingId);
        }

        // Save to localStorage whenever drawings change
        if (['created', 'modified', 'deleted'].includes(event.type)) {
          if (drawingManagerRef.current) {
            const dynStorageKey = `drawing-tools-${currentSymbolRef.current}`;
            localStorage.setItem(dynStorageKey, JSON.stringify(drawingManagerRef.current.serialize()));
          }
        }

        if (event.type === 'styleChanged') {
          if (drawingManagerRef.current) {
            const dynStylesStorageKey = `drawing-tools-styles-${currentSymbolRef.current}`;
            localStorage.setItem(dynStylesStorageKey, JSON.stringify(drawingManagerRef.current.serializeDefaultStyles()));
          }
        }
      });
    }

    setChartReadyTick((v) => v + 1);

    return () => {
      if (drawingManagerRef.current) {
        drawingManagerRef.current.destroy();
        drawingManagerRef.current = null;
      }
      chartContainerRef.current?.removeEventListener("mousedown", domMouseDown as any, true);
      chartContainerRef.current?.removeEventListener("wheel", onWheel as any);
      chartContainerRef.current?.removeEventListener("mousedown", onMouseDown as any, true);
      chartContainerRef.current?.removeEventListener("touchstart", onTouchStart as any);
      window.removeEventListener("mouseup", onMouseUp as any, true);
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(onVisibleLogicalRangeChanged);
      chart.unsubscribeCrosshairMove(handleCrosshairMove);
      chart.unsubscribeClick(handleClick);
      resizeObserver.disconnect();
      chart.remove();
    };
  }, [theme, id]); // Intentionally left out other deps to avoid unnecessary recreations

  // Apply bubble visibility when showBubble changes
  useEffect(() => {
    if (bubbleSeriesRef.current) {
      bubbleSeriesRef.current.applyOptions({
        visible: showBubble,
      });
    }
  }, [showBubble, chartReadyTick]);

  useEffect(() => {
    if (volumeProfileSeriesRef.current) {
      volumeProfileSeriesRef.current.applyOptions({
        visible: showVRVP && !hideVRVP,
        placement: settings.vrvpPlacement,
        width: settings.vrvpWidth,
        bins: settings.vrvpBins,
        upColor: settings.vrvpUpColor,
        downColor: settings.vrvpDownColor,
        valueAreaUpColor: settings.vrvpValueAreaUpColor,
        valueAreaDownColor: settings.vrvpValueAreaDownColor,
        pocColor: settings.vrvpPocColor,
        valueAreaPercentage: settings.vrvpValueAreaPercentage,
      });
    }
  }, [showVRVP, hideVRVP, settings, chartReadyTick]);

  useEffect(() => {
    if (sessionVPSeriesRef.current) {
      sessionVPSeriesRef.current.applyOptions({
        visible: showSVP && !hideSVP,
        daysToCalculate: settings.svpDaysToCalculate,
        maxWidthPercent: settings.svpMaxWidthPercent,
        bins: settings.svpBins,
        valueAreaPct: settings.svpValueAreaPct,
        colorPart1: settings.svpColorPart1,
        colorPart2: settings.svpColorPart2,
        colorPart3: settings.svpColorPart3,
        pocColor: settings.svpPocColor,
      });
      }
    }, [showSVP, hideSVP, settings, chartReadyTick]);

    useEffect(() => {
      if (rajaSRSeriesRef.current && rajaSRViewRef.current) {
        rajaSRSeriesRef.current.applyOptions({
          visible: showRajaSR && !hideRajaSR,
          pivot: settings.rajaSRPivot,
          minTouches: settings.rajaSRMinTouches,
          tolTrMult: settings.rajaSRTolTrMult,
          marginTrMult: settings.rajaSRMarginTrMult,
          maxZonesEachSide: settings.rajaSRMaxZonesEachSide,
          scope: settings.rajaSRScope,
          zoneColor: settings.rajaSRZoneColor,
          zoneBorderColor: settings.rajaSRZoneBorderColor,
          lookbackBars: settings.rajaSRLookbackBars,
        });

        // Force a recalculation and redraw when settings change
        if (dataRef.current.length > 0) {
          // get the data we need
          const currentData = isReplayModeRef.current && replayIndexRef.current >= 0 
            ? dataRef.current.slice(0, replayIndexRef.current) 
            : dataRef.current;
            
          if (currentData.length > 0) {
            const mappedData = currentData.map(d => ({
              time: d.time,
              open: d.open,
              high: d.high,
              low: d.low,
              close: d.close,
              volume: d.volume || 0,
            }));
            
            // clear cache and update full data
            rajaSRViewRef.current.setFullData(mappedData);
            
            // force a lightweight-charts redraw by updating the last bar
            rajaSRSeriesRef.current.update(mappedData[mappedData.length - 1]);
          }
        }
      }
    }, [showRajaSR, hideRajaSR, settings, chartReadyTick]);

    useEffect(() => {
    if (!chartRef.current) return;

    let bottomPanesCount = 0;
    if (showIndB_RSI && !hideIndB_RSI) bottomPanesCount++;
    if (showIndB_MACD && !hideIndB_MACD) bottomPanesCount++;
    if (showIndB_ATR && !hideIndB_ATR) bottomPanesCount++;

    const mainBottomMargin = bottomPanesCount * 0.15;
    
    try {
      chartRef.current.priceScale('right').applyOptions({
        scaleMargins: { top: 0.1, bottom: mainBottomMargin },
      });
    } catch {}

    let currentPaneIdx = 0;
    
    if (rsiSeriesRef.current) {
      const visible = showIndB_RSI && !hideIndB_RSI;
      rsiSeriesRef.current.applyOptions({ visible, color: settings.indB_RsiColor });
      if (visible) {
        chartRef.current.priceScale('rsi_scale').applyOptions({
          scaleMargins: { top: 1 - mainBottomMargin + currentPaneIdx * 0.15, bottom: mainBottomMargin - (currentPaneIdx + 1) * 0.15 },
          visible: true,
        });
        currentPaneIdx++;
      } else {
        chartRef.current.priceScale('rsi_scale').applyOptions({ visible: false });
      }
    }

    if (macdHistSeriesRef.current) {
      const visible = showIndB_MACD && !hideIndB_MACD;
      macdHistSeriesRef.current.applyOptions({ visible });
      macdLineSeriesRef.current.applyOptions({ visible, color: settings.indB_MacdLineColor });
      macdSignalSeriesRef.current.applyOptions({ visible, color: settings.indB_MacdSignalColor });
      if (visible) {
        chartRef.current.priceScale('macd_scale').applyOptions({
          scaleMargins: { top: 1 - mainBottomMargin + currentPaneIdx * 0.15, bottom: mainBottomMargin - (currentPaneIdx + 1) * 0.15 },
          visible: true,
        });
        currentPaneIdx++;
      } else {
        chartRef.current.priceScale('macd_scale').applyOptions({ visible: false });
      }
    }

    if (atrSeriesRef.current) {
      const visible = showIndB_ATR && !hideIndB_ATR;
      atrSeriesRef.current.applyOptions({ visible, color: settings.indB_AtrColor });
      if (visible) {
        chartRef.current.priceScale('atr_scale').applyOptions({
          scaleMargins: { top: 1 - mainBottomMargin + currentPaneIdx * 0.15, bottom: mainBottomMargin - (currentPaneIdx + 1) * 0.15 },
          visible: true,
        });
        currentPaneIdx++;
      } else {
        chartRef.current.priceScale('atr_scale').applyOptions({ visible: false });
      }
    }

    // Overlay indicators
    if (ema1SeriesRef.current) ema1SeriesRef.current.applyOptions({ visible: showIndB_EMA && !hideIndB_EMA, color: settings.indB_Ema1Color });
    if (ema2SeriesRef.current) ema2SeriesRef.current.applyOptions({ visible: showIndB_EMA && !hideIndB_EMA, color: settings.indB_Ema2Color });
    if (ema3SeriesRef.current) ema3SeriesRef.current.applyOptions({ visible: showIndB_EMA && !hideIndB_EMA, color: settings.indB_Ema3Color });
    if (ema4SeriesRef.current) ema4SeriesRef.current.applyOptions({ visible: showIndB_EMA && !hideIndB_EMA, color: settings.indB_Ema4Color });

    if (bbUpperSeriesRef.current) {
      const visible = showIndB_BB && !hideIndB_BB;
      const hexToRgba = (hex: string, alpha: number) => {
        let r = 33, g = 150, b = 243;
        if (hex.startsWith('#')) {
          const h = hex.replace('#', '');
          if (h.length === 3) {
            r = parseInt(h.charAt(0) + h.charAt(0), 16);
            g = parseInt(h.charAt(1) + h.charAt(1), 16);
            b = parseInt(h.charAt(2) + h.charAt(2), 16);
          } else if (h.length === 6) {
            r = parseInt(h.substring(0, 2), 16);
            g = parseInt(h.substring(2, 4), 16);
            b = parseInt(h.substring(4, 6), 16);
          }
        } else if (hex.startsWith('rgb')) {
          const parts = hex.match(/\d+/g);
          if (parts && parts.length >= 3) {
            r = parseInt(parts[0]);
            g = parseInt(parts[1]);
            b = parseInt(parts[2]);
          }
        }
        return `rgba(${r}, ${g}, ${b}, ${alpha})`;
      };
      
      bbUpperSeriesRef.current.applyOptions({ visible, color: hexToRgba(settings.indB_BbColor, 0.5) });
      bbMiddleSeriesRef.current.applyOptions({ visible, color: settings.indB_BbColor });
      bbLowerSeriesRef.current.applyOptions({ visible, color: hexToRgba(settings.indB_BbColor, 0.5) });
    }

    if (vwapSeriesRef.current) vwapSeriesRef.current.applyOptions({ visible: showIndB_VWAP && !hideIndB_VWAP, color: settings.indB_VwapColor });
    if (zigzagSeriesRef.current) zigzagSeriesRef.current.applyOptions({ visible: showIndB_Zigzag && !hideIndB_Zigzag, color: settings.indB_ZigzagColor, lineWidth: (settings.indB_ZigzagWidth || 2) as any });
    if (msbZigzagSeriesRef.current && msbZigzagViewRef.current) {
      msbZigzagSeriesRef.current.applyOptions({
        lastValueVisible: false,
        priceLineVisible: false,
        visible: showIndB_MSB_Zigzag && !hideIndB_MSB_Zigzag,
        pivotPeriod: settings.indB_MSB_ZigzagLength || 5,
        zigZagColor: settings.indB_MSB_ZigzagColor || '#FF9800',
        zigZagWidth: settings.indB_MSB_ZigzagWidth || 1,
        showZigZag: settings.indB_MSB_showZigZag ?? true,
        zigZagStyle: settings.indB_MSB_zigZagStyle ?? 0,
        showLabel: settings.indB_MSB_showLabel ?? false,
        labelColor: settings.indB_MSB_labelColor ?? '#0a378a',
        showMajorBuBoS: settings.indB_MSB_showMajorBuBoS ?? true,
        majorBuBoSStyle: settings.indB_MSB_majorBuBoSStyle ?? 0,
        majorBuBoSColor: settings.indB_MSB_majorBuBoSColor ?? '#0B5FCC',
        showMajorBeBoS: settings.indB_MSB_showMajorBeBoS ?? true,
        majorBeBoSStyle: settings.indB_MSB_majorBeBoSStyle ?? 0,
        majorBeBoSColor: settings.indB_MSB_majorBeBoSColor ?? '#C07B05',
        showMinorBuBoS: settings.indB_MSB_showMinorBuBoS ?? false,
        minorBuBoSStyle: settings.indB_MSB_minorBuBoSStyle ?? 2,
        minorBuBoSColor: settings.indB_MSB_minorBuBoSColor ?? '#000000',
        showMinorBeBoS: settings.indB_MSB_showMinorBeBoS ?? false,
        minorBeBoSStyle: settings.indB_MSB_minorBeBoSStyle ?? 2,
        minorBeBoSColor: settings.indB_MSB_minorBeBoSColor ?? '#000000',
        showMajorBuChoCh: settings.indB_MSB_showMajorBuChoCh ?? true,
        majorBuChoChStyle: settings.indB_MSB_majorBuChoChStyle ?? 0,
        majorBuChoChColor: settings.indB_MSB_majorBuChoChColor ?? '#057718',
        showMajorBeChoCh: settings.indB_MSB_showMajorBeChoCh ?? true,
        majorBeChoChStyle: settings.indB_MSB_majorBeChoChStyle ?? 0,
        majorBeChoChColor: settings.indB_MSB_majorBeChoChColor ?? '#86173A',
        showMinorBuChoCh: settings.indB_MSB_showMinorBuChoCh ?? false,
        minorBuChoChStyle: settings.indB_MSB_minorBuChoChStyle ?? 2,
        minorBuChoChColor: settings.indB_MSB_minorBuChoChColor ?? '#000000',
        showMinorBeChoCh: settings.indB_MSB_showMinorBeChoCh ?? false,
        minorBeChoChStyle: settings.indB_MSB_minorBeChoChStyle ?? 2,
        minorBeChoChColor: settings.indB_MSB_minorBeChoChColor ?? '#000000',
      } as any);

      // Force a recalculation and redraw when settings change
      if (dataRef.current.length > 0) {
        const currentData = isReplayModeRef.current && replayIndexRef.current >= 0 
          ? dataRef.current.slice(0, replayIndexRef.current) 
          : dataRef.current;
          
        if (currentData.length > 0) {
          const mappedData = currentData.map(d => ({
            time: d.time,
            open: d.open,
            high: d.high,
            low: d.low,
            close: d.close,
            volume: d.volume || 0,
          }));
          
          msbZigzagViewRef.current.setFullData(mappedData);
          msbZigzagSeriesRef.current.update(mappedData[mappedData.length - 1]);
        }
      }
    }

    if (trendExhaustionSeriesRef.current) {
      trendExhaustionSeriesRef.current.applyOptions({
        lastValueVisible: false,
        priceLineVisible: false,
        visible: showIndB_TrendExhaustion && !hideIndB_TrendExhaustion,
        colorBull: settings.indB_TE_colorBull ?? '#2466A7',
        colorBear: settings.indB_TE_colorBear ?? '#CA0017',
        threshold: settings.indB_TE_threshold ?? 20,
        shortLength: settings.indB_TE_shortLength ?? 21,
        shortSmoothingLength: settings.indB_TE_shortSmoothingLength ?? 7,
        longLength: settings.indB_TE_longLength ?? 112,
        longSmoothingLength: settings.indB_TE_longSmoothingLength ?? 3,
        showBoxes: settings.indB_TE_showBoxes ?? true,
        showShapes: settings.indB_TE_showShapes ?? true,
      } as any);

      if (dataRef.current.length > 0) {
        const currentData = isReplayModeRef.current && replayIndexRef.current >= 0 
          ? dataRef.current.slice(0, replayIndexRef.current) 
          : dataRef.current;
          
        if (currentData.length > 0) {
          const mappedData = currentData.map(d => ({
            time: d.time,
            open: d.open,
            high: d.high,
            low: d.low,
            close: d.close,
            volume: d.volume || 0,
          }));
          
          if (trendExhaustionViewRef.current && trendExhaustionSeriesRef.current) {
            trendExhaustionViewRef.current.setFullData(mappedData);
            trendExhaustionSeriesRef.current.update(mappedData[mappedData.length - 1]);
          }
        }
      }
    }

  }, [
    showIndB_RSI, hideIndB_RSI, 
    showIndB_MACD, hideIndB_MACD, 
    showIndB_EMA, hideIndB_EMA, 
    showIndB_BB, hideIndB_BB, 
    showIndB_VWAP, hideIndB_VWAP, 
    showIndB_ATR, hideIndB_ATR,
    showIndB_Zigzag, hideIndB_Zigzag,
    showIndB_MSB_Zigzag, hideIndB_MSB_Zigzag,
    showIndB_TrendExhaustion, hideIndB_TrendExhaustion,
    settings,
    chartReadyTick
  ]);

  const generateWhitespace = (baseData: any[], count: number) => {
    if (baseData.length < 2) return [];
    const lastTime = baseData[baseData.length - 1].time;
    const prevTime = baseData[baseData.length - 2].time;
    const interval = lastTime - prevTime;
    const ws = [];
    let curr = lastTime;
    for (let i = 0; i < count; i++) {
      curr += interval;
      if (interval <= 86400) {
        const d = new Date(curr * 1000);
        while (d.getUTCDay() === 0 || d.getUTCDay() === 6) {
          curr += interval;
          d.setTime(curr * 1000);
        }
      }
      ws.push({ time: curr });
    }
    return ws;
  };

  // Update data when not in replay or during replay selection
  useEffect(() => {
    if (!chartRef.current || !seriesRef.current || !bubbleSeriesRef.current || !volumeProfileSeriesRef.current || !sessionVPSeriesRef.current || !sessionVPViewRef.current) return;
    
    if (data.length > 0) {
      if (isReplayMode && replayIndexRef.current >= 0) {
        const slicedData = data.slice(0, replayIndexRef.current);
        seriesRef.current.setData(slicedData);
        bubbleSeriesRef.current.setData(slicedData.map(d => ({
          time: d.time,
          high: d.high,
          low: d.low,
          delta: d.delta_volume || 0,
        })));
        volumeProfileSeriesRef.current.setData(slicedData.map(d => ({
          time: d.time,
          open: d.open,
          high: d.high,
          low: d.low,
          close: d.close,
          volume: d.volume || 0,
        })));
        
        const mappedSlicedData = slicedData.map(d => ({
          time: d.time,
          open: d.open,
          high: d.high,
          low: d.low,
          close: d.close,
          volume: d.volume || 0,
        }));
        sessionVPSeriesRef.current.setData(mappedSlicedData);
        sessionVPViewRef.current.setFullData(mappedSlicedData);
        rajaSRSeriesRef.current.setData(mappedSlicedData);
        rajaSRViewRef.current.setFullData(mappedSlicedData);

        const inds = computeIndicators(slicedData);
        rsiSeriesRef.current.setData(inds.rsiData);
        macdLineSeriesRef.current.setData(inds.macdLineData);
        macdSignalSeriesRef.current.setData(inds.macdSignalData);
        macdHistSeriesRef.current.setData(inds.macdHistData);
        ema1SeriesRef.current.setData(inds.ema1Data);
        ema2SeriesRef.current.setData(inds.ema2Data);
        ema3SeriesRef.current.setData(inds.ema3Data);
        ema4SeriesRef.current.setData(inds.ema4Data);
        bbUpperSeriesRef.current.setData(inds.bbUpperData);
        bbMiddleSeriesRef.current.setData(inds.bbMiddleData);
        bbLowerSeriesRef.current.setData(inds.bbLowerData);
        atrSeriesRef.current.setData(inds.atrData);
        vwapSeriesRef.current.setData(inds.vwapData);
        zigzagSeriesRef.current.setData(inds.zigzagData);
        if (mappedSlicedData.length > 0) {
          if (msbZigzagSeriesRef.current) msbZigzagSeriesRef.current.setData(mappedSlicedData);
          if (msbZigzagViewRef.current) msbZigzagViewRef.current.setFullData(mappedSlicedData);
          if (trendExhaustionSeriesRef.current) trendExhaustionSeriesRef.current.setData(mappedSlicedData);
          if (trendExhaustionViewRef.current) trendExhaustionViewRef.current.setFullData(mappedSlicedData);
        }

      } else {
        seriesRef.current.setData(data);
        bubbleSeriesRef.current.setData(data.map(d => ({
          time: d.time,
          high: d.high,
          low: d.low,
          delta: d.delta_volume || 0,
        })));
        volumeProfileSeriesRef.current.setData(data.map(d => ({
          time: d.time,
          open: d.open,
          high: d.high,
          low: d.low,
          close: d.close,
          volume: d.volume || 0,
        })));
        
        const mappedData = data.map(d => ({
          time: d.time,
          open: d.open,
          high: d.high,
          low: d.low,
          close: d.close,
          volume: d.volume || 0,
        }));
        sessionVPSeriesRef.current.setData(mappedData);
        sessionVPViewRef.current.setFullData(mappedData);
        rajaSRSeriesRef.current.setData(mappedData);
        rajaSRViewRef.current.setFullData(mappedData);

        const inds = computeIndicators(data);
        rsiSeriesRef.current.setData(inds.rsiData);
        macdLineSeriesRef.current.setData(inds.macdLineData);
        macdSignalSeriesRef.current.setData(inds.macdSignalData);
        macdHistSeriesRef.current.setData(inds.macdHistData);
        ema1SeriesRef.current.setData(inds.ema1Data);
        ema2SeriesRef.current.setData(inds.ema2Data);
        ema3SeriesRef.current.setData(inds.ema3Data);
        ema4SeriesRef.current.setData(inds.ema4Data);
        bbUpperSeriesRef.current.setData(inds.bbUpperData);
        bbMiddleSeriesRef.current.setData(inds.bbMiddleData);
        bbLowerSeriesRef.current.setData(inds.bbLowerData);
        atrSeriesRef.current.setData(inds.atrData);
        vwapSeriesRef.current.setData(inds.vwapData);
        zigzagSeriesRef.current.setData(inds.zigzagData);
        if (mappedData.length > 0) {
          if (msbZigzagSeriesRef.current) msbZigzagSeriesRef.current.setData(mappedData);
          if (msbZigzagViewRef.current) msbZigzagViewRef.current.setFullData(mappedData);
          if (trendExhaustionSeriesRef.current) trendExhaustionSeriesRef.current.setData(mappedData);
          if (trendExhaustionViewRef.current) trendExhaustionViewRef.current.setFullData(mappedData);
        }

        // Track whether this is the first load for a symbol to trigger autoscale
        // We only autoscale when the SYMBOL changes, not when the timeframe changes.
        // This keeps the user's zoom level intact when switching from M5 to H1 for example.
        const cacheKey = `${symbol}`;
        if (!loading && data.length >= 50 && chartRef.current && lastAutoScaledRef.current !== cacheKey) {
          // Instead of fitting the entire content (which causes extreme zoom out for 5000+ bars),
          // we zoom in to show roughly the last 150 bars. This is the industry standard default view.
          const totalBars = data.length;
          const barsToShow = Math.min(150, totalBars);
          const to = totalBars - 1 + RIGHT_SPACE_BARS;
          const from = Math.max(0, to - barsToShow);
          chartRef.current.timeScale().setVisibleLogicalRange({ from, to });
          chartRef.current.timeScale().applyOptions({ rightOffset: RIGHT_SPACE_BARS });
          
          // Force price scale to auto-fit to the new symbol's price range
          try {
            chartRef.current.priceScale('right').applyOptions({ autoScale: true });
          } catch (e) {}

          lastAutoScaledRef.current = cacheKey;
        }

        const spaceKey = `${symbol}_${timeframe}`;
        if (chartRef.current && lastRightSpaceKeyRef.current !== spaceKey) {
          chartRef.current.timeScale().applyOptions({ rightOffset: RIGHT_SPACE_BARS });
          lastRightSpaceKeyRef.current = spaceKey;
        }
      }

      if (drawingManagerRef.current) {
        // 1) 更新时间周期（DrawingManager 不会随 timeframe 重建）
        drawingManagerRef.current.setTimeframe(timeframe);

        // If symbol changed, we must load the drawings for the new symbol
        const prevSymbol = lastDrawingRemapKeyRef.current.split('_')[0];
        if (prevSymbol && prevSymbol !== symbol) {
          // Clear current drawings
          drawingManagerRef.current.removeAllDrawings();
          
          // Load new drawings from local storage
          const storageKey = `drawing-tools-${symbol}`;
          try {
            const stored = localStorage.getItem(storageKey);
            if (stored) {
              drawingManagerRef.current.deserialize(JSON.parse(stored));
            }
          } catch (e) {
            console.error('Failed to load drawing tools on symbol change', e);
          }
        }

        // 2) 仅在 symbol/timeframe 切换后，对所有 drawing 做一次跨周期 remap
        //    避免每次 WS 更新都 remap（开销大且会“抖动”）
        const key = `${symbol}_${timeframe}`;
        if (lastDrawingRemapKeyRef.current !== key) {
          lastDrawingRemapKeyRef.current = key;
          drawingManagerRef.current.remapAllForTimeframe();
        } else {
          // 常规：只同步 logical（用于 future extrapolation）
          drawingManagerRef.current.syncLogicalsWithTime();
        }
      }
    }
  }, [data, isReplayMode, loading, symbol, timeframe, chartReadyTick]);

  const nextReplayStep = useCallback(() => {
    if (replayIndexRef.current < dataRef.current.length) {
      const nextData = dataRef.current[replayIndexRef.current];
      seriesRef.current?.update(nextData);
      bubbleSeriesRef.current?.update({
        time: nextData.time,
        high: nextData.high,
        low: nextData.low,
        delta: nextData.delta_volume || 0,
      });
      volumeProfileSeriesRef.current?.update({
        time: nextData.time,
        open: nextData.open,
        high: nextData.high,
        low: nextData.low,
        close: nextData.close,
        volume: nextData.volume || 0,
      });
      sessionVPSeriesRef.current?.update({
        time: nextData.time,
        open: nextData.open,
        high: nextData.high,
        low: nextData.low,
        close: nextData.close,
        volume: nextData.volume || 0,
      });
      rajaSRSeriesRef.current?.update({
        time: nextData.time,
        open: nextData.open,
        high: nextData.high,
        low: nextData.low,
        close: nextData.close,
        volume: nextData.volume || 0,
      });

      if (indicatorInstancesRef.current) {
        const { rsi, macd, ema1, ema2, ema3, ema4, bb, atr, vwap } = indicatorInstancesRef.current;
        const time = nextData.time;
        const c = Number(nextData.close);
        const h = Number(nextData.high);
        const l = Number(nextData.low);
        const v = Number(nextData.volume) || 0;

        const rsiVal = rsi.next(c);
        if (rsiVal !== null && rsiSeriesRef.current) {
          rsiSeriesRef.current.update({ time, value: rsiVal });
        }

        const m = macd.next(c);
        if (m.macd !== null && macdLineSeriesRef.current) macdLineSeriesRef.current.update({ time, value: m.macd });
        if (m.signal !== null && macdSignalSeriesRef.current) macdSignalSeriesRef.current.update({ time, value: m.signal });
        if (m.histogram !== null && macdHistSeriesRef.current) macdHistSeriesRef.current.update({ time, value: m.histogram, color: m.histogram >= 0 ? 'rgba(38, 166, 154, 0.8)' : 'rgba(239, 83, 80, 0.8)' });

        const e1 = ema1.next(c); if (e1 !== null && ema1SeriesRef.current) ema1SeriesRef.current.update({ time, value: e1 });
        const e2 = ema2.next(c); if (e2 !== null && ema2SeriesRef.current) ema2SeriesRef.current.update({ time, value: e2 });
        const e3 = ema3.next(c); if (e3 !== null && ema3SeriesRef.current) ema3SeriesRef.current.update({ time, value: e3 });
        const e4 = ema4.next(c); if (e4 !== null && ema4SeriesRef.current) ema4SeriesRef.current.update({ time, value: e4 });

        const b = bb.next(c);
        if (b.middle !== null && bbMiddleSeriesRef.current) bbMiddleSeriesRef.current.update({ time, value: b.middle });
        if (b.upper !== null && bbUpperSeriesRef.current) bbUpperSeriesRef.current.update({ time, value: b.upper });
        if (b.lower !== null && bbLowerSeriesRef.current) bbLowerSeriesRef.current.update({ time, value: b.lower });

        const a = atr.next(h, l, c);
        if (a !== null && atrSeriesRef.current) atrSeriesRef.current.update({ time, value: a });

        const tUnix = timeToUnixSeconds(time) || 0;
        const vw = vwap.next(h, l, c, v, tUnix);
        if (vw !== null && vwapSeriesRef.current) vwapSeriesRef.current.update({ time, value: vw });

        if (msbZigzagSeriesRef.current && msbZigzagViewRef.current) {
          const mappedNextData = { time, open: nextData.open, high: h, low: l, close: c, volume: v };
          const slicedData = dataRef.current.slice(0, replayIndexRef.current + 1).map(d => ({
            time: d.time, open: d.open, high: d.high, low: d.low, close: d.close, volume: d.volume || 0
          }));
          msbZigzagViewRef.current.setFullData(slicedData);
          msbZigzagSeriesRef.current.update(mappedNextData);
        }

        if (trendExhaustionSeriesRef.current && trendExhaustionViewRef.current) {
          const mappedNextData = { time, open: nextData.open, high: h, low: l, close: c, volume: v };
          const slicedData = dataRef.current.slice(0, replayIndexRef.current + 1).map(d => ({
            time: d.time, open: d.open, high: d.high, low: d.low, close: d.close, volume: d.volume || 0
          }));
          trendExhaustionViewRef.current.setFullData(slicedData);
          trendExhaustionSeriesRef.current.update(mappedNextData);
        }
      }
      
      // Update fullData for SessionVP so it recalculates the new maxVolume and Value Area
      if (sessionVPViewRef.current && replayIndexRef.current >= 0) {
        const slicedData = dataRef.current.slice(0, replayIndexRef.current + 1);
        const mappedSlicedData = slicedData.map(d => ({
          time: d.time,
          open: d.open,
          high: d.high,
          low: d.low,
          close: d.close,
          volume: d.volume || 0,
        }));
        sessionVPViewRef.current.setFullData(mappedSlicedData);
      }
      
      if (rajaSRViewRef.current && replayIndexRef.current >= 0) {
        const slicedData = dataRef.current.slice(0, replayIndexRef.current + 1);
        const mappedSlicedData = slicedData.map(d => ({
          time: d.time,
          open: d.open,
          high: d.high,
          low: d.low,
          close: d.close,
          volume: d.volume || 0,
        }));
        rajaSRViewRef.current.setFullData(mappedSlicedData);
      }

      if (bidLineRef.current) {
        bidLineRef.current.applyOptions({ price: nextData.close });
      }
      if (askLineRef.current) {
        askLineRef.current.applyOptions({ price: nextData.close + 0.5 });
      }

      replayIndexRef.current += 1;
      
      if (chartRef.current && chartContainerRef.current) {
        const timeScale = chartRef.current.timeScale();
        const logicalRange = timeScale.getVisibleLogicalRange();
        if (logicalRange) {
          const visibleBars = logicalRange.to - logicalRange.from;
          const targetOffset = Math.floor(visibleBars / 4);
          timeScale.applyOptions({ rightOffset: targetOffset });
        }
      }
    } else {
      setIsPlaying(false);
      if (replayIntervalRef.current) clearInterval(replayIntervalRef.current);
    }
  }, []);

  useEffect(() => {
    if (isPlaying) {
      replayIntervalRef.current = setInterval(nextReplayStep, replaySpeed);
    } else if (replayIntervalRef.current) {
      clearInterval(replayIntervalRef.current);
    }
    return () => {
      if (replayIntervalRef.current) clearInterval(replayIntervalRef.current);
    };
  }, [isPlaying, replaySpeed, nextReplayStep]);

  // Apply Chart & Series Settings
  useEffect(() => {
    if (drawingManagerRef.current && drawingManagerRef.current.activeTool !== activeTool) {
      drawingManagerRef.current.activeTool = activeTool;
    }
  }, [activeTool]);

  useEffect(() => {
    if (!chartRef.current || !seriesRef.current) return;

    const bgColor = settings.backgroundColor || (theme === "dark" ? "#000000" : "#ffffff");
    const gridColor = settings.showGrid ? (theme === "dark" ? "#2B2B43" : "#e0e3eb") : "transparent";

    chartRef.current.applyOptions({
      layout: {
        background: { type: ColorType.Solid, color: bgColor },
        textColor: theme === "dark" ? "#d1d4dc" : "#131722",
      },
      grid: {
        vertLines: { color: gridColor },
        horzLines: { color: gridColor },
      },
    });

    seriesRef.current.applyOptions({
      upColor: settings.candleUpColor,
      downColor: settings.candleDownColor,
      wickUpColor: settings.wickUpColor,
      wickDownColor: settings.wickDownColor,
    });
  }, [settings, theme]);

  // Apply Price Lines
  useEffect(() => {
    if (!seriesRef.current || dataRef.current.length === 0) return;
    
    const latestData = isReplayModeRef.current && replayIndexRef.current >= 0 
      ? dataRef.current[replayIndexRef.current - 1] 
      : dataRef.current[dataRef.current.length - 1];

    if (!latestData) return;

    if (settings.showBidLine) {
      if (!bidLineRef.current) {
        bidLineRef.current = seriesRef.current.createPriceLine({
          price: latestData.close,
          color: '#2962FF',
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: 'Bid',
        });
      } else {
        bidLineRef.current.applyOptions({ price: latestData.close });
      }
    } else if (bidLineRef.current) {
      seriesRef.current.removePriceLine(bidLineRef.current);
      bidLineRef.current = null;
    }

    if (settings.showAskLine) {
      if (!askLineRef.current) {
        askLineRef.current = seriesRef.current.createPriceLine({
          price: latestData.close + 0.5, // Dummy spread
          color: '#FF6D00',
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: 'Ask',
        });
      } else {
        askLineRef.current.applyOptions({ price: latestData.close + 0.5 }); // Dummy spread
      }
    } else if (askLineRef.current) {
      seriesRef.current.removePriceLine(askLineRef.current);
      askLineRef.current = null;
    }
  }, [settings.showBidLine, settings.showAskLine, data, isReplayMode]);

  const stopReplay = () => {
    setIsReplayMode(false);
    setIsSelectingReplayStart(false);
    setIsPlaying(false);
    if (replayIntervalRef.current) clearInterval(replayIntervalRef.current);
    if (chartRef.current) {
      chartRef.current.timeScale().applyOptions({ rightOffset: RIGHT_SPACE_BARS });
      chartRef.current.applyOptions({
        crosshair: {
          vertLine: {
            color: theme === "dark" ? "#758696" : "#2B2B43",
            width: 1,
            style: 3,
          }
        }
      });
    }
    setData([...dataRef.current]);
  };

  // Expose methods to parent
  useImperativeHandle(ref, () => ({
    takeScreenshot: () => {
      if (chartRef.current && chartContainerRef.current) {
        const canvas = chartRef.current.takeScreenshot();
        const dataUrl = canvas.toDataURL('image/png');
        const a = document.createElement('a');
        a.href = dataUrl;
        a.download = `${symbol}-${timeframe}-snapshot.png`;
        a.click();
      }
    },
    captureScreenshotDataUrl: () => {
      if (!chartRef.current || !chartContainerRef.current) return null;
      try {
        const canvas = chartRef.current.takeScreenshot();
        return canvas.toDataURL("image/webp", 0.6);
      } catch {
        return null;
      }
    },
    enterReplaySelectionMode: () => {
      if (data.length === 0) return;
      setIsPlaying(false);
      if (replayIntervalRef.current) clearInterval(replayIntervalRef.current);
      setIsSelectingReplayStart(true);
    },
    togglePlay: () => setIsPlaying(p => !p),
    setPlaying: (playing: boolean) => {
      // 防止在非回放模式误触发（会导致 replayIndexRef=-1 时 nextReplayStep 取到 undefined）
      if (playing) {
        if (!isReplayMode || replayIndexRef.current < 0) return;
      }
      setIsPlaying(!!playing);
    },
    getReplayState: () => ({
      isReplayMode: !!isReplayMode,
      isPlaying: !!isPlaying,
      isSelectingReplayStart: !!isSelectingReplayStart,
      replaySpeed: Number(replaySpeed),
    }),
    nextReplayStep: () => nextReplayStep(),
    prevReplayStep: () => prevReplayStep(),
    stopReplay: () => stopReplay(),
    setReplaySpeed: (speed) => setReplaySpeed(speed),
    syncCrosshair: (param) => {
      if (!chartRef.current || !seriesRef.current) return;
      if (!param || !param.time) {
        chartRef.current.clearCrosshairPosition();
      } else {
        const targetTime = param.time as number;
        // Find the closest candle that is less than or equal to the target time
        // This ensures that when hovering over a small timeframe (e.g. M1 10:04), 
        // the large timeframe (e.g. H1 10:00) will still show its crosshair properly.
        let closestDataPoint = null;
        
        // Since dataRef.current is chronologically ordered (oldest to newest)
        // we can iterate backwards to find the first candle <= targetTime
        for (let i = dataRef.current.length - 1; i >= 0; i--) {
          if (dataRef.current[i].time <= targetTime) {
            closestDataPoint = dataRef.current[i];
            break;
          }
        }
        
        if (closestDataPoint) {
          chartRef.current.setCrosshairPosition(closestDataPoint.close, closestDataPoint.time, seriesRef.current);
        } else {
          chartRef.current.clearCrosshairPosition();
        }
      }
    },
    syncLogicalRange: (range) => {
      if (!chartRef.current || !range) return;
      chartRef.current.timeScale().setVisibleLogicalRange(range);
    },
    syncTimeRange: (r) => {
      if (!chartRef.current || !r) return;
      if (!dataRef.current || dataRef.current.length === 0) return;
      const fromT = Number(r.from);
      const toT = Number(r.to);
      if (!Number.isFinite(fromT) || !Number.isFinite(toT)) return;
      const minT = Math.min(fromT, toT);
      const maxT = Math.max(fromT, toT);
      let a = findIndexAtOrBeforeTime(dataRef.current, minT);
      let b = findIndexAtOrBeforeTime(dataRef.current, maxT);
      if (a < 0) a = 0;
      if (b < 0) b = 0;
      const from = Math.min(a, b);
      const to = Math.max(a, b) + RIGHT_SPACE_BARS;
      chartRef.current.timeScale().setVisibleLogicalRange({ from, to });
      chartRef.current.timeScale().applyOptions({ rightOffset: RIGHT_SPACE_BARS });
    },
    removeAllDrawings: () => {
      if (drawingManagerRef.current) {
        drawingManagerRef.current.removeAllDrawings();
      }
    },
    removeDrawing: (drawingId: string) => {
      if (drawingManagerRef.current && drawingId) {
        drawingManagerRef.current.removeDrawing(drawingId);
        if (selectionDrawingIdRef.current === drawingId) {
          selectionDrawingIdRef.current = null;
          selectionPriceRangeRef.current = null;
          selectionDrawingRef.current = null;
        }
      }
    },
    resetView: () => {
      if (!chartRef.current) return;
      const totalBars = dataRef.current.length;
      if (totalBars <= 0) return;
      const barsToShow = Math.min(150, totalBars);
      const to = totalBars - 1 + RIGHT_SPACE_BARS;
      const from = Math.max(0, to - barsToShow);
      chartRef.current.timeScale().setVisibleLogicalRange({ from, to });
      chartRef.current.timeScale().applyOptions({ rightOffset: RIGHT_SPACE_BARS });
    },
    scrollToTime: (t: number) => {
      if (!chartRef.current || !seriesRef.current) return;
      const target = Number(t);
      if (!Number.isFinite(target) || dataRef.current.length === 0) return;
      // 找到 <= target 的最近一根（与跨周期 crosshair 规则一致）
      let idx = -1;
      for (let i = dataRef.current.length - 1; i >= 0; i--) {
        if (dataRef.current[i].time <= target) {
          idx = i;
          break;
        }
      }
      if (idx < 0) idx = 0;
      const barsToShow = 120;
      const from = Math.max(0, idx - Math.floor(barsToShow * 0.7));
      const to = Math.min(dataRef.current.length - 1 + RIGHT_SPACE_BARS, from + barsToShow + RIGHT_SPACE_BARS);
      chartRef.current.timeScale().setVisibleLogicalRange({ from, to });
      const bar = dataRef.current[idx];
      chartRef.current.setCrosshairPosition(bar.close, bar.time, seriesRef.current);
      chartRef.current.timeScale().applyOptions({ rightOffset: RIGHT_SPACE_BARS });

      // 关键：用户在图表上拖拽/缩放后，priceScale 可能进入“手动缩放”状态，导致切换候选只滚动 X 不调整 Y，
      // 看起来像“找不到对应 candle”。这里强制开启 autoScale，让价格轴按当前可视区间重新拟合。
      try {
        (chartRef.current as any).priceScale?.("right")?.applyOptions?.({ autoScale: true });
      } catch {}
      try {
        chartRef.current.applyOptions({ rightPriceScale: { autoScale: true } as any });
      } catch {}
    },
    ensureHistoryBefore: async (t: number) => {
      const target = Number(t);
      if (!Number.isFinite(target)) return false;
      // 最多尝试拉取多次历史（每次 5000 bars），直到覆盖到目标时间 or 没有更多数据
      for (let k = 0; k < 10; k++) {
        const oldest = dataRef.current.length ? Number(dataRef.current[0]?.time) : 0;
        if (!oldest) return false;
        if (oldest <= target) return true;
        if (!hasMoreHistory) break;
        // 拉更早的数据：before_time=oldest（后端会返回 time < oldest）
        await fetchHistoricalData(oldest);
        // 等待 state/render 推进，让 dataRef.current 刷新
        await new Promise((r) => setTimeout(r, 220));
      }
      const oldest2 = dataRef.current.length ? Number(dataRef.current[0]?.time) : 0;
      return !!oldest2 && oldest2 <= target;
    },
    getLatestBarTime: () => {
      if (!dataRef.current || dataRef.current.length === 0) return null;
      const v = Number(dataRef.current[dataRef.current.length - 1]?.time);
      return Number.isFinite(v) ? v : null;
    },
    drawObjects: async (objects: any[]) => {
      const dm = drawingManagerRef.current;
      if (!dm || !chartRef.current || !seriesRef.current) return;
      if (!Array.isArray(objects) || objects.length === 0) return;

      // 如果刚切换 symbol/timeframe，图表可能还没把第一批 5000 bars 拉下来。
      // 这时如果直接 draw，会导致 mapTime=null，marker/box/arrow 被跳过，看起来“第一次只有 hline”。
      // 这里先等待数据可用（最多 ~2s），确保第一次落图也能完整画出所有对象。
      if (!dataRef.current || dataRef.current.length === 0) {
        for (let i = 0; i < 10; i++) {
          await new Promise((r) => setTimeout(r, 200));
          if (dataRef.current && dataRef.current.length > 0) break;
        }
      }

      // 关键：确保历史数据覆盖到标注所需的最早时间点，否则 marker/box 会因为 mapTime=null 被跳过，
      // 用户只能看到“横线”，看不到“触发K线三角标记”。
      try {
        const times: number[] = [];
        for (const o of objects) {
          const type = String(o?.type || "");
          if (type === "marker") times.push(Number(o?.time));
          else if (type === "hline") times.push(Number(o?.time));
          else if (type === "trendline") {
            times.push(Number(o?.t1));
            times.push(Number(o?.t2));
          } else if (type === "box") {
            times.push(Number(o?.from_time));
            times.push(Number(o?.to_time));
          }
        }
        const tMin = Math.min(...times.filter((x) => Number.isFinite(x)));
        const oldest = dataRef.current.length ? Number(dataRef.current[0]?.time) : 0;
        if (Number.isFinite(tMin) && tMin > 0 && (!oldest || oldest > tMin)) {
          // 复用 ensureHistoryBefore 的逻辑（这里内联一份，避免依赖 handle 里其它方法）
          for (let k = 0; k < 10; k++) {
            const o2 = dataRef.current.length ? Number(dataRef.current[0]?.time) : 0;
            if (!o2) break;
            if (o2 <= tMin) break;
            if (!hasMoreHistory) break;
            await fetchHistoricalData(o2);
            await new Promise((r) => setTimeout(r, 240));
          }
        }
      } catch {}

      // 将时间对齐到已加载K线（<= t 的最近一根）
      const mapTime = (t: number) => {
        const target = Number(t);
        if (!Number.isFinite(target) || dataRef.current.length === 0) return null;
        let idx = 0;
        while (idx < dataRef.current.length && Number(dataRef.current[idx].time) <= target) idx++;
        idx = Math.max(0, idx - 1);
        return dataRef.current[idx]?.time ?? null;
      };

      const defaultTime = dataRef.current.length ? dataRef.current[dataRef.current.length - 1]?.time : 0;

      for (const o of objects) {
        const type = String(o?.type || o?.action || "");
        try {
          if (type === "hline") {
            const price = Number(o?.price);
            if (!Number.isFinite(price)) continue;
            const t = mapTime(Number(o?.time || defaultTime || 0)) ?? (dataRef.current[0]?.time ?? 0);
            const id = `ai_hline_${Date.now()}_${Math.random().toString(16).slice(2)}`;
            const d = new HorizontalLineDrawing(id);
            dm.addDrawing(d);
            // 支持样式（颜色/线型/粗细），否则用户很难区分“突破位/区间上下沿/其它水平位”
            d.updateStyle({
              lineColor: String(o?.color || "#60a5fa"),
              lineWidth: Math.max(1, Math.min(4, Number(o?.lineWidth || 2))),
              lineStyle: (["solid", "dashed", "dotted"].includes(String(o?.lineStyle)) ? String(o?.lineStyle) : "solid") as any,
            });
            d.addPoint({ time: t, price });
          } else if (type === "trendline") {
            const t1 = mapTime(Number(o?.t1));
            const t2 = mapTime(Number(o?.t2));
            const p1 = Number(o?.p1);
            const p2 = Number(o?.p2);
            if (t1 == null || t2 == null || !Number.isFinite(p1) || !Number.isFinite(p2)) continue;
            const id = `ai_line_${Date.now()}_${Math.random().toString(16).slice(2)}`;
            const d = new TrendlineDrawing(id);
            dm.addDrawing(d);
            d.updateStyle({
              lineColor: String(o?.color || "#60a5fa"),
              lineWidth: Math.max(1, Math.min(4, Number(o?.lineWidth || 2))),
              lineStyle: (["solid", "dashed", "dotted"].includes(String(o?.lineStyle)) ? String(o?.lineStyle) : "solid") as any,
            });
            d.addPoint({ time: t1, price: p1 });
            d.addPoint({ time: t2, price: p2 });
          } else if (type === "box") {
            const ft = mapTime(Number(o?.from_time));
            const tt = mapTime(Number(o?.to_time));
            const low = Number(o?.low);
            const high = Number(o?.high);
            if (ft == null || tt == null || !Number.isFinite(low) || !Number.isFinite(high)) continue;
            const id = `ai_box_${Date.now()}_${Math.random().toString(16).slice(2)}`;
            const d = new RectangleDrawing(id);
            dm.addDrawing(d);
            // Rectangle 支持填充，用于“突破前区间”高亮
            const fillColor = String(o?.fillColor || o?.color || "#94a3b8");
            const fillOpacity = Math.max(0, Math.min(0.8, Number(o?.fillOpacity ?? 0.08)));
            (d as any).updateStyle?.({
              lineColor: String(o?.color || "#94a3b8"),
              lineWidth: Math.max(1, Math.min(4, Number(o?.lineWidth || 1))),
              lineStyle: (["solid", "dashed", "dotted"].includes(String(o?.lineStyle)) ? String(o?.lineStyle) : "dotted") as any,
              fillColor,
              fillOpacity,
            });
            d.addPoint({ time: ft, price: low });
            d.addPoint({ time: tt, price: high });
          } else if (type === "arrow") {
            const t1 = mapTime(Number(o?.t1));
            const t2 = mapTime(Number(o?.t2));
            const p1 = Number(o?.p1);
            const p2 = Number(o?.p2);
            if (t1 == null || t2 == null || !Number.isFinite(p1) || !Number.isFinite(p2)) continue;
            const id = `ai_arrow_${Date.now()}_${Math.random().toString(16).slice(2)}`;
            const d = new ArrowDrawing(id);
            dm.addDrawing(d);
            (d as any).updateStyle?.({
              lineColor: String(o?.color || "#22c55e"),
              lineWidth: Math.max(1, Math.min(4, Number(o?.lineWidth || 2))),
              lineStyle: (["solid", "dashed", "dotted"].includes(String(o?.lineStyle)) ? String(o?.lineStyle) : "solid") as any,
              arrowSize: Math.max(8, Math.min(24, Number(o?.arrowSize || 14))),
            });
            d.addPoint({ time: t1, price: p1 });
            d.addPoint({ time: t2, price: p2 });
          } else if (type === "marker") {
            const t = mapTime(Number(o?.time));
            if (t == null) continue;
            const pos = String(o?.position || "aboveBar");
            const color = String(o?.color || "#60a5fa");
            const text = String(o?.text || "");
            const shape = String(o?.shape || "circle");
            const ms = [...(studyMarkersRef.current || [])];
            ms.push({ time: t, position: pos, color, shape, text });
            studyMarkersRef.current = ms;
            applyMarkers();
          }
        } catch (e) {
          console.warn("drawObjects failed", e);
        }
      }
    },
    removeAiOverlays: () => {
      // 清理由 AI/Pattern Inspector 落图生成的 overlays（id 前缀为 ai_）
      try {
        const dm: any = drawingManagerRef.current as any;
        const serialized = dm?.serialize?.() || [];
        for (const d of serialized) {
          if (d?.id && String(d.id).startsWith("ai_")) dm.removeDrawing(d.id);
        }
      } catch {}
      // 清理 study markers（AI/研究标注），不影响 trade markers
      try {
        studyMarkersRef.current = [];
        applyMarkers();
      } catch {}
    },
    startReplayAtTime: (t: number) => {
      if (!chartRef.current || !seriesRef.current) return;
      const target = Number(t);
      if (!Number.isFinite(target) || dataRef.current.length === 0) return;
      let idx = -1;
      for (let i = dataRef.current.length - 1; i >= 0; i--) {
        if (dataRef.current[i].time <= target) {
          idx = i;
          break;
        }
      }
      if (idx < 0) idx = 0;
      // 直接进入 replay 模式（不需要手动选点）
      if (replayIntervalRef.current) clearInterval(replayIntervalRef.current);
      setIsSelectingReplayStart(false);
      setIsPlaying(false);
      setIsReplayMode(true);
      replayIndexRef.current = idx + 1;
      // 触发 slicedData 渲染
      setData([...dataRef.current]);
      // 视图对齐到附近
      const barsToShow = 120;
      const from = Math.max(0, idx - Math.floor(barsToShow * 0.7));
      const to = Math.min(dataRef.current.length - 1 + RIGHT_SPACE_BARS, from + barsToShow + RIGHT_SPACE_BARS);
      chartRef.current.timeScale().setVisibleLogicalRange({ from, to });
      chartRef.current.timeScale().applyOptions({ rightOffset: RIGHT_SPACE_BARS });
      const bar = dataRef.current[idx];
      chartRef.current.setCrosshairPosition(bar.close, bar.time, seriesRef.current);
    },
    setTradeMarkers: (markers: any[]) => {
      tradeMarkersRef.current = Array.isArray(markers) ? markers : [];
      applyMarkers();
    },
    setBacktestPositions: (trades: any[]) => {
      // 如果此刻图表还没把 bars 拉下来（time 映射依赖 dataRef），先缓存，等 data ready 再渲染
      pendingBacktestTradesRef.current = Array.isArray(trades) ? trades : [];
      applyBacktestPositions(pendingBacktestTradesRef.current);
    },
    clearBacktestPositions: () => {
      pendingBacktestTradesRef.current = null;
      clearBacktestPositions();
    },
    setStudyMarkers: (markers: any[]) => {
      studyMarkersRef.current = Array.isArray(markers) ? markers : [];
      applyMarkers();
    },
    clearStudyMarkers: () => {
      studyMarkersRef.current = [];
      applyMarkers();
    },
    getVisibleTimeRange: () => {
      if (!chartRef.current || dataRef.current.length === 0) return null;
      const r = chartRef.current.timeScale().getVisibleLogicalRange?.() || null;
      if (!r) return null;
      const fromIdx = Math.max(0, Math.floor(Number(r.from)));
      const toIdx = Math.min(dataRef.current.length - 1, Math.ceil(Number(r.to)));
      const fromT = Number(dataRef.current[fromIdx]?.time);
      const toT = Number(dataRef.current[toIdx]?.time);
      if (!Number.isFinite(fromT) || !Number.isFinite(toT)) return null;
      return { from: Math.min(fromT, toT), to: Math.max(fromT, toT) };
    },
    getSelectedRectangleTimeRange: () => {
      const dm: any = drawingManagerRef.current as any;
      const sel: any = dm?.selectedDrawing || null;
      if (!sel || sel.toolType !== "rectangle") return null;
      const pts: any[] = Array.from(sel.getPoints?.() || []);
      if (pts.length < 2) return null;
      const t1 = timeToUnixSeconds(pts[0]?.timeMapped ?? pts[0]?.time);
      const t2 = timeToUnixSeconds(pts[1]?.timeMapped ?? pts[1]?.time);
      if (t1 == null || t2 == null) return null;
      return { from: Math.min(t1, t2), to: Math.max(t1, t2) };
    },
  }));

  // 如果回测 trades 提前到了（但当时 data 还没 ready），在 data ready 后补画
  useEffect(() => {
    if (!pendingBacktestTradesRef.current) return;
    if (!drawingManagerRef.current || dataRef.current.length === 0) return;
    applyBacktestPositions(pendingBacktestTradesRef.current);
    pendingBacktestTradesRef.current = null;
  }, [data]);

  return (
    <div 
      className={`w-full h-full relative flex flex-col ${isActive ? 'ring-2 ring-[#00bfa5]' : ''}`}
      onContextMenu={(e) => onContextMenu(e, id)}
    >
      <div className="absolute inset-0" ref={chartContainerRef} />
      {/* Watermark/Label indicating symbol and timeframe */}
      <div className={`absolute top-4 left-4 z-10 text-xl font-bold opacity-30 pointer-events-none ${theme === 'dark' ? 'text-white' : 'text-black'}`}>
        {symbol} {timeframe}
      </div>

      {/* Floating Indicators Legend */}
      <div className="absolute top-12 left-4 z-10 flex flex-col gap-1 pointer-events-none">
        {showVRVP && (
          <div className={`group flex items-center gap-2 pointer-events-auto cursor-default ${hideVRVP ? 'opacity-40' : ''}`}>
            <span className={`text-xs font-semibold px-2 py-1 rounded backdrop-blur-sm transition-colors ${theme === 'dark' ? 'bg-[#1e222d]/60 text-gray-300 group-hover:text-white' : 'bg-white/60 text-gray-600 group-hover:text-black'}`}>Volume Profile</span>
            <div className={`hidden group-hover:flex items-center gap-1 rounded px-1 backdrop-blur-sm ${theme === 'dark' ? 'bg-[#1e222d]/80 text-gray-400' : 'bg-white/80 text-gray-500'}`}>
              <button className="p-1 hover:text-[#00bfa5]" onClick={() => setHideVRVP(!hideVRVP)} title={hideVRVP ? "Show" : "Hide"}>
                {hideVRVP ? <Eye size={14}/> : <EyeOff size={14}/>}
              </button>
              <button className="p-1 hover:text-[#00bfa5]" onClick={() => onOpenSettings?.('VRVP')} title="Settings"><Settings size={14}/></button>
              <button className="p-1 hover:text-red-500" onClick={() => onToggleIndicator?.('VRVP')} title="Remove"><X size={14}/></button>
            </div>
          </div>
        )}
        {showSVP && (
          <div className={`group flex items-center gap-2 pointer-events-auto cursor-default ${hideSVP ? 'opacity-40' : ''}`}>
            <span className={`text-xs font-semibold px-2 py-1 rounded backdrop-blur-sm transition-colors ${theme === 'dark' ? 'bg-[#1e222d]/60 text-gray-300 group-hover:text-white' : 'bg-white/60 text-gray-600 group-hover:text-black'}`}>Session VP</span>
            <div className={`hidden group-hover:flex items-center gap-1 rounded px-1 backdrop-blur-sm ${theme === 'dark' ? 'bg-[#1e222d]/80 text-gray-400' : 'bg-white/80 text-gray-500'}`}>
              <button className="p-1 hover:text-[#00bfa5]" onClick={() => setHideSVP(!hideSVP)} title={hideSVP ? "Show" : "Hide"}>
                {hideSVP ? <Eye size={14}/> : <EyeOff size={14}/>}
              </button>
              <button className="p-1 hover:text-[#00bfa5]" onClick={() => onOpenSettings?.('SVP')} title="Settings"><Settings size={14}/></button>
              <button className="p-1 hover:text-red-500" onClick={() => onToggleIndicator?.('SVP')} title="Remove"><X size={14}/></button>
            </div>
          </div>
        )}
        {showRajaSR && (
          <div className={`group flex items-center gap-2 pointer-events-auto cursor-default ${hideRajaSR ? 'opacity-40' : ''}`}>
            <span className={`text-xs font-semibold px-2 py-1 rounded backdrop-blur-sm transition-colors ${theme === 'dark' ? 'bg-[#1e222d]/60 text-gray-300 group-hover:text-white' : 'bg-white/60 text-gray-600 group-hover:text-black'}`}>RajaSR</span>
            <div className={`hidden group-hover:flex items-center gap-1 rounded px-1 backdrop-blur-sm ${theme === 'dark' ? 'bg-[#1e222d]/80 text-gray-400' : 'bg-white/80 text-gray-500'}`}>
              <button className="p-1 hover:text-[#00bfa5]" onClick={() => setHideRajaSR(!hideRajaSR)} title={hideRajaSR ? "Show" : "Hide"}>
                {hideRajaSR ? <Eye size={14}/> : <EyeOff size={14}/>}
              </button>
              <button className="p-1 hover:text-[#00bfa5]" onClick={() => onOpenSettings?.('RajaSR')} title="Settings"><Settings size={14}/></button>
              <button className="p-1 hover:text-red-500" onClick={() => onToggleIndicator?.('RajaSR')} title="Remove"><X size={14}/></button>
            </div>
          </div>
        )}
        
        {/* Indicator B Legends */}
        {showIndB_RSI && (
          <div className={`group flex items-center gap-2 pointer-events-auto cursor-default ${hideIndB_RSI ? 'opacity-40' : ''}`}>
            <span className={`text-xs font-semibold px-2 py-1 rounded backdrop-blur-sm transition-colors ${theme === 'dark' ? 'bg-[#1e222d]/60 text-gray-300 group-hover:text-white' : 'bg-white/60 text-gray-600 group-hover:text-black'}`}>
              RSI {settings.indB_RsiPeriod} 
              <span style={{color: settings.indB_RsiColor}} className="ml-1">
                {rsiSeriesRef.current?.dataByIndex?.(rsiSeriesRef.current.data()?.length - 1)?.value?.toFixed(2) || ''}
              </span>
            </span>
            <div className={`hidden group-hover:flex items-center gap-1 rounded px-1 backdrop-blur-sm ${theme === 'dark' ? 'bg-[#1e222d]/80 text-gray-400' : 'bg-white/80 text-gray-500'}`}>
              <button className="p-1 hover:text-[#00bfa5]" onClick={() => setHideIndB_RSI(!hideIndB_RSI)} title={hideIndB_RSI ? "Show" : "Hide"}>
                {hideIndB_RSI ? <Eye size={14}/> : <EyeOff size={14}/>}
              </button>
              <button className="p-1 hover:text-[#00bfa5]" onClick={() => onOpenSettings?.('RSI')} title="Settings"><Settings size={14}/></button>
              <button className="p-1 hover:text-red-500" onClick={() => onToggleIndicator?.('RSI')} title="Remove"><X size={14}/></button>
            </div>
          </div>
        )}
        {showIndB_MACD && (
          <div className={`group flex items-center gap-2 pointer-events-auto cursor-default ${hideIndB_MACD ? 'opacity-40' : ''}`}>
            <span className={`text-xs font-semibold px-2 py-1 rounded backdrop-blur-sm transition-colors ${theme === 'dark' ? 'bg-[#1e222d]/60 text-gray-300 group-hover:text-white' : 'bg-white/60 text-gray-600 group-hover:text-black'}`}>MACD</span>
            <div className={`hidden group-hover:flex items-center gap-1 rounded px-1 backdrop-blur-sm ${theme === 'dark' ? 'bg-[#1e222d]/80 text-gray-400' : 'bg-white/80 text-gray-500'}`}>
              <button className="p-1 hover:text-[#00bfa5]" onClick={() => setHideIndB_MACD(!hideIndB_MACD)} title={hideIndB_MACD ? "Show" : "Hide"}>
                {hideIndB_MACD ? <Eye size={14}/> : <EyeOff size={14}/>}
              </button>
              <button className="p-1 hover:text-[#00bfa5]" onClick={() => onOpenSettings?.('MACD')} title="Settings"><Settings size={14}/></button>
              <button className="p-1 hover:text-red-500" onClick={() => onToggleIndicator?.('MACD')} title="Remove"><X size={14}/></button>
            </div>
          </div>
        )}
        {showIndB_EMA && (
          <div className={`group flex items-center gap-2 pointer-events-auto cursor-default ${hideIndB_EMA ? 'opacity-40' : ''}`}>
            <span className={`text-xs font-semibold px-2 py-1 rounded backdrop-blur-sm transition-colors ${theme === 'dark' ? 'bg-[#1e222d]/60 text-gray-300 group-hover:text-white' : 'bg-white/60 text-gray-600 group-hover:text-black'}`}>EMA (9/20/50/200)</span>
            <div className={`hidden group-hover:flex items-center gap-1 rounded px-1 backdrop-blur-sm ${theme === 'dark' ? 'bg-[#1e222d]/80 text-gray-400' : 'bg-white/80 text-gray-500'}`}>
              <button className="p-1 hover:text-[#00bfa5]" onClick={() => setHideIndB_EMA(!hideIndB_EMA)} title={hideIndB_EMA ? "Show" : "Hide"}>
                {hideIndB_EMA ? <Eye size={14}/> : <EyeOff size={14}/>}
              </button>
              <button className="p-1 hover:text-[#00bfa5]" onClick={() => onOpenSettings?.('EMA')} title="Settings"><Settings size={14}/></button>
              <button className="p-1 hover:text-red-500" onClick={() => onToggleIndicator?.('EMA')} title="Remove"><X size={14}/></button>
            </div>
          </div>
        )}
        {showIndB_BB && (
          <div className={`group flex items-center gap-2 pointer-events-auto cursor-default ${hideIndB_BB ? 'opacity-40' : ''}`}>
            <span className={`text-xs font-semibold px-2 py-1 rounded backdrop-blur-sm transition-colors ${theme === 'dark' ? 'bg-[#1e222d]/60 text-gray-300 group-hover:text-white' : 'bg-white/60 text-gray-600 group-hover:text-black'}`}>Bollinger Bands</span>
            <div className={`hidden group-hover:flex items-center gap-1 rounded px-1 backdrop-blur-sm ${theme === 'dark' ? 'bg-[#1e222d]/80 text-gray-400' : 'bg-white/80 text-gray-500'}`}>
              <button className="p-1 hover:text-[#00bfa5]" onClick={() => setHideIndB_BB(!hideIndB_BB)} title={hideIndB_BB ? "Show" : "Hide"}>
                {hideIndB_BB ? <Eye size={14}/> : <EyeOff size={14}/>}
              </button>
              <button className="p-1 hover:text-[#00bfa5]" onClick={() => onOpenSettings?.('BB')} title="Settings"><Settings size={14}/></button>
              <button className="p-1 hover:text-red-500" onClick={() => onToggleIndicator?.('BB')} title="Remove"><X size={14}/></button>
            </div>
          </div>
        )}
        {showIndB_VWAP && (
          <div className={`group flex items-center gap-2 pointer-events-auto cursor-default ${hideIndB_VWAP ? 'opacity-40' : ''}`}>
            <span className={`text-xs font-semibold px-2 py-1 rounded backdrop-blur-sm transition-colors ${theme === 'dark' ? 'bg-[#1e222d]/60 text-gray-300 group-hover:text-white' : 'bg-white/60 text-gray-600 group-hover:text-black'}`}>VWAP</span>
            <div className={`hidden group-hover:flex items-center gap-1 rounded px-1 backdrop-blur-sm ${theme === 'dark' ? 'bg-[#1e222d]/80 text-gray-400' : 'bg-white/80 text-gray-500'}`}>
              <button className="p-1 hover:text-[#00bfa5]" onClick={() => setHideIndB_VWAP(!hideIndB_VWAP)} title={hideIndB_VWAP ? "Show" : "Hide"}>
                {hideIndB_VWAP ? <Eye size={14}/> : <EyeOff size={14}/>}
              </button>
              <button className="p-1 hover:text-red-500" onClick={() => onToggleIndicator?.('VWAP')} title="Remove"><X size={14}/></button>
            </div>
          </div>
        )}
        {showIndB_ATR && (
          <div className={`group flex items-center gap-2 pointer-events-auto cursor-default ${hideIndB_ATR ? 'opacity-40' : ''}`}>
            <span className={`text-xs font-semibold px-2 py-1 rounded backdrop-blur-sm transition-colors ${theme === 'dark' ? 'bg-[#1e222d]/60 text-gray-300 group-hover:text-white' : 'bg-white/60 text-gray-600 group-hover:text-black'}`}>ATR</span>
            <div className={`hidden group-hover:flex items-center gap-1 rounded px-1 backdrop-blur-sm ${theme === 'dark' ? 'bg-[#1e222d]/80 text-gray-400' : 'bg-white/80 text-gray-500'}`}>
              <button className="p-1 hover:text-[#00bfa5]" onClick={() => setHideIndB_ATR(!hideIndB_ATR)} title={hideIndB_ATR ? "Show" : "Hide"}>
                {hideIndB_ATR ? <Eye size={14}/> : <EyeOff size={14}/>}
              </button>
              <button className="p-1 hover:text-[#00bfa5]" onClick={() => onOpenSettings?.('ATR')} title="Settings"><Settings size={14}/></button>
              <button className="p-1 hover:text-red-500" onClick={() => onToggleIndicator?.('ATR')} title="Remove"><X size={14}/></button>
            </div>
          </div>
        )}

        {showIndB_Zigzag && (
          <div className={`group flex items-center gap-2 pointer-events-auto cursor-default ${hideIndB_Zigzag ? 'opacity-40' : ''}`}>
            <span className={`text-xs font-semibold px-2 py-1 rounded backdrop-blur-sm transition-colors ${theme === 'dark' ? 'bg-[#1e222d]/60 text-gray-300 group-hover:text-white' : 'bg-white/60 text-gray-600 group-hover:text-black'}`}>Zigzag ({settings.indB_ZigzagDeviation})</span>
            <div className={`hidden group-hover:flex items-center gap-1 rounded px-1 backdrop-blur-sm ${theme === 'dark' ? 'bg-[#1e222d]/80 text-gray-400' : 'bg-white/80 text-gray-500'}`}>
              <button className="p-1 hover:text-[#00bfa5]" onClick={() => setHideIndB_Zigzag(!hideIndB_Zigzag)} title={hideIndB_Zigzag ? "Show" : "Hide"}>
                {hideIndB_Zigzag ? <Eye size={14}/> : <EyeOff size={14}/>}
              </button>
              <button className="p-1 hover:text-[#00bfa5]" onClick={() => onOpenSettings?.('Zigzag')} title="Settings"><Settings size={14}/></button>
              <button className="p-1 hover:text-red-500" onClick={() => onToggleIndicator?.('Zigzag')} title="Remove"><X size={14}/></button>
            </div>
          </div>
        )}
        {showIndB_MSB_Zigzag && (
          <div className={`group flex items-center gap-2 pointer-events-auto cursor-default ${hideIndB_MSB_Zigzag ? 'opacity-40' : ''}`}>
            <span className={`text-xs font-semibold px-2 py-1 rounded backdrop-blur-sm transition-colors ${theme === 'dark' ? 'bg-[#1e222d]/60 text-gray-300 group-hover:text-white' : 'bg-white/60 text-gray-600 group-hover:text-black'}`}>MSB Zigzag ({settings.indB_MSB_ZigzagLength})</span>
            <div className={`hidden group-hover:flex items-center gap-1 rounded px-1 backdrop-blur-sm ${theme === 'dark' ? 'bg-[#1e222d]/80 text-gray-400' : 'bg-white/80 text-gray-500'}`}>
              <button className="p-1 hover:text-[#00bfa5]" onClick={() => setHideIndB_MSB_Zigzag(!hideIndB_MSB_Zigzag)} title={hideIndB_MSB_Zigzag ? "Show" : "Hide"}>
                {hideIndB_MSB_Zigzag ? <Eye size={14}/> : <EyeOff size={14}/>}
              </button>
              <button className="p-1 hover:text-[#00bfa5]" onClick={() => onOpenSettings?.('MSB_Zigzag')} title="Settings"><Settings size={14}/></button>
              <button className="p-1 hover:text-red-500" onClick={() => onToggleIndicator?.('MSB_Zigzag')} title="Remove"><X size={14}/></button>
            </div>
          </div>
        )}
        {showIndB_TrendExhaustion && (
          <div className={`group flex items-center gap-2 pointer-events-auto cursor-default ${hideIndB_TrendExhaustion ? 'opacity-40' : ''}`}>
            <span className={`text-xs font-semibold px-2 py-1 rounded backdrop-blur-sm transition-colors ${theme === 'dark' ? 'bg-[#1e222d]/60 text-gray-300 group-hover:text-white' : 'bg-white/60 text-gray-600 group-hover:text-black'}`}>Trend Exhaustion</span>
            <div className={`hidden group-hover:flex items-center gap-1 rounded px-1 backdrop-blur-sm ${theme === 'dark' ? 'bg-[#1e222d]/80 text-gray-400' : 'bg-white/80 text-gray-500'}`}>
              <button className="p-1 hover:text-[#00bfa5]" onClick={() => setHideIndB_TrendExhaustion(!hideIndB_TrendExhaustion)} title={hideIndB_TrendExhaustion ? "Show" : "Hide"}>
                {hideIndB_TrendExhaustion ? <Eye size={14}/> : <EyeOff size={14}/>}
              </button>
              <button className="p-1 hover:text-[#00bfa5]" onClick={() => onOpenSettings?.('TrendExhaustion')} title="Settings"><Settings size={14}/></button>
              <button className="p-1 hover:text-red-500" onClick={() => onToggleIndicator?.('TrendExhaustion')} title="Remove"><X size={14}/></button>
            </div>
          </div>
        )}
      </div>
      
      {loading && (
        <div className="absolute inset-0 z-20 flex items-center justify-center bg-black/10 backdrop-blur-sm">
          <div className="text-[#00bfa5] animate-pulse">Loading data...</div>
        </div>
      )}
      <DrawingToolbar activeTool={activeTool} onToolChange={setActiveTool} theme={theme} />
      {settingsModalDrawingId && drawingManagerRef.current && drawingManagerRef.current.selectedDrawing && (
        <DrawingSettingsModal 
          drawing={drawingManagerRef.current.selectedDrawing} 
          theme={theme}
          onClose={() => {
            setSettingsModalDrawingId(null);
          }}
          onDelete={() => {
            drawingManagerRef.current?.removeDrawing(settingsModalDrawingId);
            setSettingsModalDrawingId(null);
            setSelectedDrawingId(null);
          }}
          onChange={() => {
             if (drawingManagerRef.current && drawingManagerRef.current.selectedDrawing) {
               drawingManagerRef.current.updateDefaultStyle(
                 drawingManagerRef.current.selectedDrawing.toolType,
                 drawingManagerRef.current.selectedDrawing.getStyle()
               );
               const storageKey = `drawing-tools-${currentSymbolRef.current}`;
               localStorage.setItem(storageKey, JSON.stringify(drawingManagerRef.current.serialize()));
               
               const stylesStorageKey = `drawing-tools-styles-${currentSymbolRef.current}`;
               localStorage.setItem(stylesStorageKey, JSON.stringify(drawingManagerRef.current.serializeDefaultStyles()));
             }
          }}
        />
      )}
      <div ref={chartContainerRef} className="flex-1 w-full h-full" />
      
      {showScrollToRealTime && (
        <button
          onClick={() => {
            if (chartRef.current) {
              chartRef.current.timeScale().scrollToRealTime();
              // Maintain right margin
              chartRef.current.timeScale().applyOptions({ rightOffset: 12 });
            }
          }}
          className={`absolute bottom-6 right-[60px] z-30 p-2 rounded-full shadow-lg border backdrop-blur-sm transition-all hover:scale-105 ${
            theme === 'dark' 
              ? 'bg-[#1e222d]/80 border-[#2B2B43] text-[#00bfa5] hover:bg-[#2B2B43]' 
              : 'bg-white/80 border-[#e0e3eb] text-[#00a68f] hover:bg-[#e0e3eb]'
          }`}
          title="Scroll to Real-Time"
        >
          <ArrowRightToLine size={18} />
        </button>
      )}
    </div>
  );
});

SingleChart.displayName = 'SingleChart';
