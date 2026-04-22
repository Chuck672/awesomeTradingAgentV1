"use client";

import React, { useEffect, useRef, useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Play, Pause, StepForward, StepBack, Database, Plus, Camera, LayoutGrid, ArrowLeftToLine } from "lucide-react";
import { SingleChart, ChartRef, ReplayState } from "./single-chart";
import { ColorPicker } from "./color-picker";
import { LogicalRange, MouseEventParams } from "lightweight-charts";
import { getBaseUrl, getWsUrl } from "@/lib/api";
import { RightRail, RightPanelId } from "@/components/sidebar/RightRail";
import { RightPanel } from "@/components/sidebar/RightPanel";

interface ChartConfig {
  id: string;
  symbol: string;
  timeframe: string;
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
}

export type IndicatorType = 'VRVP' | 'SVP' | 'RajaSR' | 'RSI' | 'MACD' | 'EMA' | 'BB' | 'VWAP' | 'ATR' | 'Zigzag' | 'MSB_Zigzag' | 'TrendExhaustion';

export interface ChartSettings {
  backgroundColor: string;
  candleUpColor: string;
  candleDownColor: string;
  wickUpColor: string;
  wickDownColor: string;
  showGrid: boolean;
  showBidLine: boolean;
  showAskLine: boolean;
  vrvpPlacement: "left" | "right";
  vrvpWidth: number;
  vrvpBins: number;
  vrvpUpColor: string;
  vrvpDownColor: string;
  vrvpValueAreaUpColor: string;
  vrvpValueAreaDownColor: string;
  vrvpPocColor: string;
  vrvpValueAreaPercentage: number;
  svpDaysToCalculate: number;
  svpMaxWidthPercent: number;
  svpBins: number;
  svpValueAreaPct: number;
  svpColorPart1: string;
  svpColorPart2: string;
  svpColorPart3: string;
  svpPocColor: string;
  rajaSRPivot: number;
  rajaSRMinTouches: number;
  rajaSRTolTrMult: number;
  rajaSRMarginTrMult: number;
  rajaSRMaxZonesEachSide: number;
  rajaSRScope: "nearest" | "all" | "trade";
  rajaSRZoneColor: string;
  rajaSRZoneBorderColor: string;
  rajaSRLookbackBars: number;
  
  // Indicator B Settings (Zero Dependency)
  indB_RsiPeriod: number;
  indB_RsiColor: string;
  indB_RsiSmaPeriod: number;
  indB_RsiSmaColor: string;
  indB_MacdFast: number;
  indB_MacdSlow: number;
  indB_MacdSignal: number;
  indB_MacdLineColor: string;
  indB_MacdSignalColor: string;
  indB_Ema1: number;
  indB_Ema2: number;
  indB_Ema3: number;
  indB_Ema4: number;
  indB_Ema1Color: string;
  indB_Ema2Color: string;
  indB_Ema3Color: string;
  indB_Ema4Color: string;
  indB_BbPeriod: number;
  indB_BbStdDev: number;
  indB_BbColor: string;
  indB_VwapColor: string;
  indB_AtrPeriod: number;
  indB_AtrColor: string;
  indB_ZigzagDeviation: number;
  indB_ZigzagColor: string;
  indB_ZigzagWidth: number;
  indB_MSB_ZigzagLength: number;
  indB_MSB_ZigzagWidth: number;
  indB_MSB_ZigzagColor: string;
  indB_MSB_showZigZag: boolean;
  indB_MSB_zigZagStyle: number;
  indB_MSB_showLabel: boolean;
  indB_MSB_labelColor: string;
  indB_MSB_showMajorBuBoS: boolean;
  indB_MSB_majorBuBoSStyle: number;
  indB_MSB_majorBuBoSColor: string;
  indB_MSB_showMajorBeBoS: boolean;
  indB_MSB_majorBeBoSStyle: number;
  indB_MSB_majorBeBoSColor: string;
  indB_MSB_showMinorBuBoS: boolean;
  indB_MSB_minorBuBoSStyle: number;
  indB_MSB_minorBuBoSColor: string;
  indB_MSB_showMinorBeBoS: boolean;
  indB_MSB_minorBeBoSStyle: number;
  indB_MSB_minorBeBoSColor: string;
  indB_MSB_showMajorBuChoCh: boolean;
  indB_MSB_majorBuChoChStyle: number;
  indB_MSB_majorBuChoChColor: string;
  indB_MSB_showMajorBeChoCh: boolean;
  indB_MSB_majorBeChoChStyle: number;
  indB_MSB_majorBeChoChColor: string;
  indB_MSB_showMinorBuChoCh: boolean;
  indB_MSB_minorBuChoChStyle: number;
  indB_MSB_minorBuChoChColor: string;
  indB_MSB_showMinorBeChoCh: boolean;
  indB_MSB_minorBeChoChStyle: number;
  indB_MSB_minorBeChoChColor: string;

  // Trend Exhaustion Settings
  indB_TE_colorBull: string;
  indB_TE_colorBear: string;
  indB_TE_threshold: number;
  indB_TE_shortLength: number;
  indB_TE_shortSmoothingLength: number;
  indB_TE_longLength: number;
  indB_TE_longSmoothingLength: number;
  indB_TE_showBoxes: boolean;
  indB_TE_showShapes: boolean;
}

export const defaultSettings: ChartSettings = {
  backgroundColor: "", // Empty string means follow theme
  candleUpColor: "#00bfa5",
  candleDownColor: "#ff4444",
  wickUpColor: "#00bfa5",
  wickDownColor: "#ff4444",
  showGrid: true,
  showBidLine: false,
  showAskLine: false,
  vrvpPlacement: "right",
  vrvpWidth: 25,
  vrvpBins: 70,
  vrvpUpColor: "rgba(0, 191, 165, 0.2)",
  vrvpDownColor: "rgba(255, 68, 68, 0.2)",
  vrvpValueAreaUpColor: "rgba(0, 191, 165, 0.6)",
  vrvpValueAreaDownColor: "rgba(255, 68, 68, 0.6)",
  vrvpPocColor: "#FFD700",
  vrvpValueAreaPercentage: 70,
  svpDaysToCalculate: 5,
  svpMaxWidthPercent: 65,
  svpBins: 70,
  svpValueAreaPct: 70,
  svpColorPart1: "#778899",
  svpColorPart2: "#CD5C5C",
  svpColorPart3: "#3CB371",
  svpPocColor: "#FFD700",
  rajaSRPivot: 2,
  rajaSRMinTouches: 5,
  rajaSRTolTrMult: 0.35,
  rajaSRMarginTrMult: 0.1,
  rajaSRMaxZonesEachSide: 3,
  rajaSRScope: "trade",
  rajaSRZoneColor: "rgba(60, 60, 60, 0.4)",
  rajaSRZoneBorderColor: "rgba(120, 120, 120, 0.8)",
  rajaSRLookbackBars: 300,
  
  // Indicator B defaults
  indB_RsiPeriod: 14,
  indB_RsiColor: '#7E57C2',
  indB_RsiSmaPeriod: 14,
  indB_RsiSmaColor: '#FFEB3B',
  indB_MacdFast: 12,
  indB_MacdSlow: 26,
  indB_MacdSignal: 9,
  indB_MacdLineColor: '#2962FF',
  indB_MacdSignalColor: '#FF6D00',
  indB_Ema1: 9,
  indB_Ema2: 20,
  indB_Ema3: 50,
  indB_Ema4: 200,
  indB_Ema1Color: '#2962FF',
  indB_Ema2Color: '#FF6D00',
  indB_Ema3Color: '#00C853',
  indB_Ema4Color: '#D50000',
  indB_BbPeriod: 20,
  indB_BbStdDev: 2.0,
  indB_BbColor: '#2196F3',
  indB_VwapColor: '#E91E63',
  indB_AtrPeriod: 14,
  indB_AtrColor: '#9C27B0',
  indB_ZigzagDeviation: 5,
  indB_ZigzagColor: '#2484bb',
  indB_ZigzagWidth: 1,
  indB_MSB_ZigzagLength: 5,
  indB_MSB_ZigzagWidth: 1,
  indB_MSB_ZigzagColor: '#FF9800',
  indB_MSB_showZigZag: false,
  indB_MSB_zigZagStyle: 0,
  indB_MSB_showLabel: false,
  indB_MSB_labelColor: '#0A378A',
  indB_MSB_showMajorBuBoS: true,
  indB_MSB_majorBuBoSStyle: 0,
  indB_MSB_majorBuBoSColor: '#0B5FCC',
  indB_MSB_showMajorBeBoS: true,
  indB_MSB_majorBeBoSStyle: 0,
  indB_MSB_majorBeBoSColor: '#C07B05',
  indB_MSB_showMinorBuBoS: false,
  indB_MSB_minorBuBoSStyle: 2,
  indB_MSB_minorBuBoSColor: '#000000',
  indB_MSB_showMinorBeBoS: false,
  indB_MSB_minorBeBoSStyle: 2,
  indB_MSB_minorBeBoSColor: '#000000',
  indB_MSB_showMajorBuChoCh: true,
  indB_MSB_majorBuChoChStyle: 0,
  indB_MSB_majorBuChoChColor: '#057718',
  indB_MSB_showMajorBeChoCh: true,
  indB_MSB_majorBeChoChStyle: 0,
  indB_MSB_majorBeChoChColor: '#86173A',
  indB_MSB_showMinorBuChoCh: false,
  indB_MSB_minorBuChoChStyle: 2,
  indB_MSB_minorBuChoChColor: '#000000',
  indB_MSB_showMinorBeChoCh: false,
  indB_MSB_minorBeChoChStyle: 2,
  indB_MSB_minorBeChoChColor: '#000000',
  indB_TE_colorBull: '#2466A7',
  indB_TE_colorBear: '#CA0017',
  indB_TE_threshold: 20,
  indB_TE_shortLength: 21,
  indB_TE_shortSmoothingLength: 7,
  indB_TE_longLength: 112,
  indB_TE_longSmoothingLength: 3,
  indB_TE_showBoxes: true,
  indB_TE_showShapes: true,
};

export function TradingChart() {
  const [activeBroker, setActiveBroker] = useState<any>(null);
  const [showBrokerModal, setShowBrokerModal] = useState(false);
  const [brokerForm, setBrokerForm] = useState({ server: "", login: "", password: "", path: "" });
  const [connectingBroker, setConnectingBroker] = useState(false);

  const [availableSymbols, setAvailableSymbols] = useState<string[]>([]);
  const [showSymbolDropdown, setShowSymbolDropdown] = useState(false);
  const [showSymbolSearchModal, setShowSymbolSearchModal] = useState(false);
  const [mt5Symbols, setMt5Symbols] = useState<any[]>([]);
  const [symbolSearchQuery, setSymbolSearchQuery] = useState("");
  const [searchingSymbols, setSearchingSymbols] = useState(false);
  const [addingSymbol, setAddingSymbol] = useState<string | null>(null);
  
  // Sync Progress State
  const [syncProgressMap, setSyncProgressMap] = useState<Record<string, any>>({});
  
  // Custom Modal States
  const [alertMessage, setAlertMessage] = useState<string | null>(null);
  const [confirmDialog, setConfirmDialog] = useState<{
    message: string;
    onConfirm: () => void;
    onCancel: () => void;
  } | null>(null);

  // Use the state to avoid lint error or remove it if totally unused
  useEffect(() => {
    if (confirmDialog) {
       // Just a dummy to avoid unused var
    }
  }, [confirmDialog]);

  // Listen to Global WS for sync progress
  useEffect(() => {
    if (availableSymbols.length === 0) return;
    
    let isMounted = true;
    let ws: WebSocket | null = null;
    let timeoutId: NodeJS.Timeout;

    const connectGlobalWS = () => {
      // Connect to the first available symbol just to listen to its progress
      // Add a slight delay so it doesn't try to connect before the server is fully ready
      // especially when the page is just loaded.
      const wsHost = getWsUrl();
      
      ws = new WebSocket(`${wsHost}/api/ws/${availableSymbols[0]}/H1`);
      
      ws.onopen = () => {
        console.log("Global progress WebSocket connected.");
      };

      ws.onmessage = (event) => {
        if (!isMounted) return;
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "sync_progress") {
            const key = `${msg.symbol}_${msg.timeframe}`;
            setSyncProgressMap(prev => {
              const next = { ...prev };
              next[key] = msg;
              return next;
            });
          }
        } catch (e) {
          // ignore
        }
      };

      ws.onerror = (e) => {
        console.warn("Global progress WebSocket error.", e);
      };

      ws.onclose = () => {
        if (isMounted) {
          // Reconnect with exponential backoff or fixed delay
          timeoutId = setTimeout(connectGlobalWS, 3000);
        }
      };
    };

    // Small delay to allow the React app to mount and backend to settle
    timeoutId = setTimeout(connectGlobalWS, 500);
    
    return () => {
      isMounted = false;
      if (timeoutId) clearTimeout(timeoutId);
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.onclose = null;
        ws.close();
      }
    };
  }, [availableSymbols]);

  // Global Theme & Settings
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const [settings, setSettings] = useState<ChartSettings>(defaultSettings);
  
  // Sync document theme class for Tailwind dark mode
  useEffect(() => {
    if (theme === 'dark') {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [theme]);
  
  // Modals & Menus
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [indicatorSettingsModal, setIndicatorSettingsModal] = useState<IndicatorType | null>(null);
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; show: boolean } | null>(null);

  // Multi-chart State
  const [charts, setCharts] = useState<ChartConfig[]>([]);
  const [activeChartId, setActiveChartId] = useState<string>("");
  const [layoutCount, setLayoutCount] = useState<number>(1);
  const [syncDragEnabled, setSyncDragEnabled] = useState<boolean>(true);
  const [isLoadedFromStorage, setIsLoadedFromStorage] = useState(false);

  // Load state from localStorage on mount
  useEffect(() => {
    try {
      const savedTheme = localStorage.getItem("awesomeChart_theme");
      if (savedTheme === "dark" || savedTheme === "light") setTheme(savedTheme);

      const savedSettings = localStorage.getItem("awesomeChart_settings");
      if (savedSettings) setSettings({ ...defaultSettings, ...JSON.parse(savedSettings) });

      const savedCharts = localStorage.getItem("awesomeChart_charts");
      if (savedCharts) {
        const parsedCharts = JSON.parse(savedCharts);
        if (Array.isArray(parsedCharts) && parsedCharts.length > 0) {
          setCharts(parsedCharts);
        }
      }

      const savedLayoutCount = localStorage.getItem("awesomeChart_layoutCount");
      if (savedLayoutCount) setLayoutCount(Number(savedLayoutCount));

      const savedSyncDrag = localStorage.getItem("awesomeChart_syncDragEnabled");
      if (savedSyncDrag !== null) setSyncDragEnabled(savedSyncDrag === "true");

      const savedActiveChartId = localStorage.getItem("awesomeChart_activeChartId");
      if (savedActiveChartId) setActiveChartId(savedActiveChartId);
    } catch (e) {
      console.error("Failed to load chart settings from local storage", e);
    } finally {
      setIsLoadedFromStorage(true);
    }
  }, []);

  // Save state to localStorage whenever it changes
  useEffect(() => {
    if (!isLoadedFromStorage) return;
    localStorage.setItem("awesomeChart_theme", theme);
    localStorage.setItem("awesomeChart_settings", JSON.stringify(settings));
    localStorage.setItem("awesomeChart_charts", JSON.stringify(charts));
    localStorage.setItem("awesomeChart_layoutCount", String(layoutCount));
    localStorage.setItem("awesomeChart_syncDragEnabled", String(syncDragEnabled));
    localStorage.setItem("awesomeChart_activeChartId", activeChartId);
  }, [theme, settings, charts, layoutCount, syncDragEnabled, activeChartId, isLoadedFromStorage]);

  // Sidebar linkage: 当前十字线时间（用于回放/研究联动）
  const [focusTime, setFocusTime] = useState<number | null>(null);

  // 右侧面板（默认隐藏；点击右侧 Dock 按钮弹出）
  const [rightPanel, setRightPanel] = useState<RightPanelId>("none");
  // 详情面板宽度（可拖拽调整）。右侧状态栏宽度固定 56px。
  const [rightPanelWidth, setRightPanelWidth] = useState<number>(440);
  const resizingRef = useRef(false);
  const startXRef = useRef(0);
  const startWRef = useRef(440);

  // 选区（Explain selection）
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectionRange, setSelectionRange] = useState<{ from: number; to: number } | null>(null);
  const [selectionDrawingId, setSelectionDrawingId] = useState<string | null>(null);
  
  // Refs
  const chartRefs = useRef<Record<string, ChartRef | null>>({});
  const [replayStates, setReplayStates] = useState<Record<string, ReplayState>>({});
  const isSyncingCrosshair = useRef(false);
  const isSyncingRange = useRef(false);

  const timeframes = ["M1", "M5", "M15", "M30", "H1"];
  const extendedTimeframes = ["H4", "D1", "W1", "MN1"];
  const [showExtendedTf, setShowExtendedTf] = useState(false);
  const [showIndicatorsDropdown, setShowIndicatorsDropdown] = useState(false);
  const [showIndicatorBDropdown, setShowIndicatorBDropdown] = useState(false);

  const fetchActiveBroker = async () => {
    try {
      const res = await fetch(`${getBaseUrl()}/api/broker/active`);
      if (res.ok) {
        const data = await res.json();
        if (data.active) {
          setActiveBroker(data.broker);
          fetchSymbols();
        } else {
          setShowBrokerModal(true);
        }
      }
    } catch (err) {
      console.error("Failed to fetch active broker", err);
    }
  };

  const handleConnectBroker = async () => {
    if (!brokerForm.server) {
      setAlertMessage("Server is required");
      return;
    }
    setConnectingBroker(true);
    try {
      const res = await fetch(`${getBaseUrl()}/api/broker/connect`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(brokerForm)
      });
      if (res.ok) {
        setShowBrokerModal(false);
        fetchActiveBroker();
      } else {
        const err = await res.json();
        setAlertMessage(`Failed to connect: ${err.detail}`);
      }
    } catch (e) {
      setAlertMessage("Network error connecting to broker.");
    } finally {
      setConnectingBroker(false);
    }
  };

  const fetchSymbols = async () => {
    try {
      const res = await fetch(`${getBaseUrl()}/api/symbols`);
      if (!res.ok) throw new Error(`API error: ${res.status}`);
      const data = await res.json();
      // data is [{name: "EURUSD", ...}, ...] from the new backend
      const symbolNames = data.map((item: any) => item.name);
      setAvailableSymbols(symbolNames);
      
      // Fetch current sync progress for all symbols
      try {
        const progRes = await fetch(`${getBaseUrl()}/api/symbols/progress`);
        if (progRes.ok) {
          const progData = await progRes.json();
          setSyncProgressMap(prev => {
            const next = { ...prev };
            progData.forEach((item: any) => {
              next[`${item.symbol}_${item.timeframe}`] = item;
            });
            return next;
          });
        }
      } catch (e) {
        console.error('Error fetching progress:', e);
      }
      
      setCharts(prevCharts => {
        if (symbolNames.length === 0) {
          // If there are no symbols configured in backend, clear charts
          // and show the symbol search modal
          setTimeout(() => {
            setShowSymbolSearchModal(true);
            fetchMt5Symbols();
            setActiveChartId("");
          }, 0);
          return [];
        }

        if (prevCharts.length === 0) {
          // System has symbols, but UI has no charts, initialize one
          const preferredSymbol = symbolNames.includes("XAUUSD") ? "XAUUSD" : symbolNames[0];
          const initId = Date.now().toString();
          setTimeout(() => setActiveChartId(initId), 0);
          return [{ id: initId, symbol: preferredSymbol, timeframe: "H1", showBubble: false, showVRVP: false, showSVP: false, showRajaSR: false, showIndB_RSI: false, showIndB_MACD: false, showIndB_EMA: false, showIndB_BB: false, showIndB_VWAP: false, showIndB_ATR: false, showIndB_Zigzag: false, showIndB_MSB_Zigzag: false, showIndB_TrendExhaustion: false }];
      }

      // We have symbols and we have charts. Just ensure no chart has an empty/invalid symbol
      return prevCharts.map(c => {
        const updatedC = { 
          ...c, 
          showRajaSR: c.showRajaSR ?? false,
          showIndB_RSI: c.showIndB_RSI ?? false,
          showIndB_MACD: c.showIndB_MACD ?? false,
          showIndB_EMA: c.showIndB_EMA ?? false,
          showIndB_BB: c.showIndB_BB ?? false,
          showIndB_VWAP: c.showIndB_VWAP ?? false,
          showIndB_ATR: c.showIndB_ATR ?? false,
          showIndB_Zigzag: c.showIndB_Zigzag ?? false,
          showIndB_MSB_Zigzag: c.showIndB_MSB_Zigzag ?? false,
          showIndB_TrendExhaustion: c.showIndB_TrendExhaustion ?? false
        };
        if (!updatedC.symbol || !symbolNames.includes(updatedC.symbol)) {
            updatedC.symbol = symbolNames[0];
          }
          return updatedC;
        });
      });
    } catch (err) {
      console.error("Failed to fetch symbols", err);
    }
  };

  useEffect(() => {
    fetchActiveBroker();
  }, []);

  const handleLayoutChange = (count: number) => {
    setLayoutCount(count);
    if (count > 1) setSyncDragEnabled(true);
    setCharts(prev => {
      const newCharts = [...prev];
      if (newCharts.length > count) {
        return newCharts.slice(0, count);
      }
      const tfs = ["H1", "M15", "M5", "M1", "H1", "M15", "M5", "M1"];
      while (newCharts.length < count) {
        newCharts.push({
          id: Date.now().toString() + Math.random().toString(),
          symbol: newCharts[0]?.symbol || availableSymbols[0] || "",
          timeframe: tfs[newCharts.length % tfs.length],
          showBubble: false,
          showVRVP: false,
          showSVP: false,
          showRajaSR: false,
          showIndB_RSI: false,
          showIndB_MACD: false,
          showIndB_EMA: false,
          showIndB_BB: false,
          showIndB_VWAP: false,
          showIndB_ATR: false,
          showIndB_Zigzag: false,
          showIndB_MSB_Zigzag: false,
          showIndB_TrendExhaustion: false
        });
      }
      return newCharts;
    });
    // Ensure activeChartId is valid
    if (charts.length > count && !charts.slice(0, count).find(c => c.id === activeChartId)) {
      setActiveChartId(charts[0].id);
    }
  };

  const activeChart = charts.find(c => c.id === activeChartId);
  const activeReplayState = replayStates[activeChartId] || { isReplayMode: false, isPlaying: false, isSelectingReplayStart: false, replaySpeed: 1000 };

  // 兜底：如果 charts 已初始化但 activeChartId 为空（例如启动时后端短暂不可用导致 init 丢失），
  // UI 会表现为“无K线、按钮无反应”。这里自动恢复到第一个 chart。
  useEffect(() => {
    if (!activeChartId && Array.isArray(charts) && charts.length > 0) {
      setActiveChartId(charts[0].id);
    }
  }, [activeChartId, charts]);

  const updateActiveChart = (updates: Partial<ChartConfig>) => {
    setCharts(prev => prev.map(c => {
      if (c.id === activeChartId) {
        // If switching symbol, reset indicator settings so they don't carry over
        if (updates.symbol && updates.symbol !== c.symbol) {
          return {
            ...c,
            ...updates,
            showBubble: false,
            showVRVP: false,
            showSVP: false,
            showRajaSR: false,
            showIndB_RSI: false,
            showIndB_MACD: false,
            showIndB_EMA: false,
            showIndB_BB: false,
            showIndB_VWAP: false,
    showIndB_ATR: false,
    showIndB_Zigzag: false,
    showIndB_MSB_Zigzag: false,
  };
        }
        return { ...c, ...updates };
      }
      return c;
    }));
  };

  // Sync Handlers
  const handleCrosshairMove = useCallback((sourceId: string, param: MouseEventParams) => {
    if (isSyncingCrosshair.current) return;
    if (syncDragEnabled && charts.length > 1) {
      isSyncingCrosshair.current = true;
      charts.forEach(c => {
        if (c.id !== sourceId) {
          chartRefs.current[c.id]?.syncCrosshair(param);
        }
      });
      isSyncingCrosshair.current = false;
    }

    // 只记录 active chart 的 focusTime（避免多图干扰）
    try {
      if (sourceId === activeChartId && (param as any)?.time) {
        const t = (param as any).time;
        // lightweight-charts 的 time 可能是 number 或 BusinessDay；这里只处理 unix seconds number
        if (typeof t === "number") setFocusTime(t);
      }
    } catch {
      // ignore
    }
  }, [charts, syncDragEnabled, activeChartId]);

  const handleRangeChange = useCallback((sourceId: string, range: LogicalRange | null) => {
    if (isSyncingRange.current) return;
    if (!syncDragEnabled || charts.length <= 1) return;
    if (!range) return;
    const timeRange = chartRefs.current[sourceId]?.getVisibleTimeRange?.() ?? null;
    if (!timeRange) return;
    isSyncingRange.current = true;
    charts.forEach(c => {
      if (c.id !== sourceId) {
        chartRefs.current[c.id]?.syncTimeRange?.(timeRange);
      }
    });
    isSyncingRange.current = false;
  }, [charts, syncDragEnabled]);

  const handleContextMenu = useCallback((e: React.MouseEvent, id: string) => {
    e.preventDefault();
    setActiveChartId(id);
    setContextMenu({ x: e.clientX, y: e.clientY, show: true });
  }, []);

  const fetchMt5Symbols = async (query: string = "") => {
    setSearchingSymbols(true);
    try {
      const url = query ? `${getBaseUrl()}/api/mt5/symbols?search=${encodeURIComponent(query)}` : `${getBaseUrl()}/api/mt5/symbols`;
      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        setMt5Symbols(data);
      }
    } catch (err) {
      console.error("Failed to fetch MT5 symbols", err);
    } finally {
      setSearchingSymbols(false);
    }
  };

  const handleAddSymbol = async (symbolName: string) => {
    if (availableSymbols.includes(symbolName)) {
      setAlertMessage(`品种 ${symbolName} 已经存在`);
      return;
    }

    setAddingSymbol(symbolName);
    try {
      // Create a fetch request with AbortController to handle timeout manually
      // because browser fetch doesn't have a built-in timeout and might hang up
      // if the server takes exactly the same time as the browser's default timeout.
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 35000); // 35s timeout
      
      // Initialize progress to 0% immediately for UI responsiveness
      const defaultTfs = ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1"];
      setSyncProgressMap(prev => {
        const next = { ...prev };
        defaultTfs.forEach(tf => {
          next[`${symbolName}_${tf}`] = { symbol: symbolName, timeframe: tf, progress: 0, status: "syncing" };
        });
        return next;
      });
      
      const res = await fetch(`${getBaseUrl()}/api/symbols/add?symbol=${encodeURIComponent(symbolName)}`, {
        method: 'POST',
        signal: controller.signal
      });
      
      clearTimeout(timeoutId);
      
      if (res.ok) {
        await fetchSymbols();
        
        // If there were no charts, create the first one with this symbol
        if (charts.length === 0) {
            const initId = Date.now().toString();
            setCharts([{ id: initId, symbol: symbolName, timeframe: "H1", showBubble: false, showVRVP: false, showSVP: false, showRajaSR: false, showIndB_RSI: false, showIndB_MACD: false, showIndB_EMA: false, showIndB_BB: false, showIndB_VWAP: false, showIndB_ATR: false, showIndB_Zigzag: false, showIndB_MSB_Zigzag: false, showIndB_TrendExhaustion: false }]);
            setActiveChartId(initId);
        } else {
          updateActiveChart({ symbol: symbolName });
        }
        
        setShowSymbolSearchModal(false);
        // Show info message that data is fetching in background
        setAlertMessage(`成功添加 ${symbolName}！\n\n当前正在后台高速拉取该品种所有周期的历史数据。请留意右上角的进度面板，待当前图表周期（如 H1）进度走动或完成后，点击键盘 F5 刷新页面即可查看完整历史 K 线。`);
      } else {
        const error = await res.json();
        setAlertMessage(`添加失败: ${error.detail}`);
      }
    } catch (err) {
      console.error('Error adding symbol:', err);
      setAlertMessage('添加失败：网络错误或服务异常');
    } finally {
      setAddingSymbol(null);
    }
  };

  const getGridClass = (count: number) => {
    if (count === 1) return "grid-cols-1 grid-rows-1";
    if (count === 2) return "grid-cols-2 grid-rows-1";
    if (count === 4) return "grid-cols-2 grid-rows-2";
    return "grid-cols-1 grid-rows-1";
  };

  // 拖拽调整详情面板宽度（右侧 rail 固定不变，chart 区域 flex-1 自动跟随）
  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!resizingRef.current) return;
      const dx = startXRef.current - e.clientX; // 往左拖 => dx 正 => 面板变宽
      const maxW = Math.floor(window.innerWidth * 0.66); // 最大可到屏幕宽度约 2/3
      const next = Math.min(maxW, Math.max(280, startWRef.current + dx));
      setRightPanelWidth(next);
    };
    const onUp = () => {
      if (!resizingRef.current) return;
      resizingRef.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, []);

  return (
    <div className={`w-full h-full relative flex overflow-hidden ${theme === 'dark' ? 'bg-black' : 'bg-white'}`}>
      <div className={`flex-1 h-full relative flex flex-col overflow-hidden ${theme === 'dark' ? 'bg-black' : 'bg-white'}`}>
      {/* Global Shared Toolbar */}
        {/* 重要：右侧面板变宽时，不应导致顶部工具栏“消失”。这里允许换行来兜底，同时移除 overflow-x 以免裁剪下拉菜单。 */}
        <div
          className={`flex gap-4 items-center p-2 border-b ${
            theme === "dark" ? "bg-[#0b0f14] border-[#2B2B43]" : "bg-white border-[#e0e3eb]"
          } shadow-md z-20 flex-wrap`}
        >
        
        {/* Layout Selector */}
        <div className="flex items-center gap-2 border-r pr-4 mr-2 border-opacity-20 border-white">
          <LayoutGrid size={16} className={theme === 'dark' ? 'text-gray-400' : 'text-gray-600'} />
          <select
            className={`h-8 bg-transparent border rounded text-xs px-2 focus:outline-none focus:border-[#00bfa5] ${theme === 'dark' ? 'border-white/20 text-white' : 'border-black/20 text-black'}`}
            value={layoutCount}
            onChange={(e) => handleLayoutChange(Number(e.target.value))}
          >
                <option value={1} className={theme === 'dark' ? 'bg-black' : 'bg-white'}>1 图表</option>
            <option value={2} className={theme === 'dark' ? 'bg-black' : 'bg-white'}>2 图表</option>
            <option value={4} className={theme === 'dark' ? 'bg-black' : 'bg-white'}>4 图表</option>
          </select>
          <button
            disabled={layoutCount === 1}
            onClick={() => setSyncDragEnabled(v => !v)}
            className={`h-8 px-3 rounded text-xs font-semibold flex items-center justify-center transition-colors border ${
              layoutCount === 1
                ? theme === "dark"
                  ? "bg-transparent border-[#2B2B43] text-gray-500 cursor-not-allowed"
                  : "bg-transparent border-[#e0e3eb] text-gray-400 cursor-not-allowed"
                : syncDragEnabled
                  ? "bg-[#00bfa5] text-black border-[#00bfa5] hover:bg-[#00a68f]"
                  : theme === "dark"
                    ? "bg-transparent border-[#2B2B43] text-gray-300 hover:text-white hover:bg-white/10"
                    : "bg-transparent border-[#e0e3eb] text-gray-600 hover:text-black hover:bg-black/10"
            }`}
            title={layoutCount === 1 ? "单窗口无需同步" : syncDragEnabled ? "拖拽/滚轮会同步到其它窗口" : "拖拽/滚轮不会同步到其它窗口"}
          >
            同步拖拽
          </button>
        </div>

        {/* Symbol Selector (Controls Active Chart) */}
        <div className="relative">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowSymbolDropdown(!showSymbolDropdown)}
            className={`h-8 text-sm font-semibold flex items-center gap-2 ${
              theme === 'dark'
                ? "bg-black/50 border-white/20 text-white hover:bg-white/10"
                : "bg-white/50 border-black/20 text-black hover:bg-black/10"
            }`}
          >
            {activeChart?.symbol || "Select Symbol"}
            
            {/* Inline Sync Progress */}
            {(() => {
              if (!activeChart?.symbol) return null;
              const items = Object.values(syncProgressMap).filter(item => item.symbol === activeChart.symbol);
              if (items.length === 0) return null;
              const totalProgress = Math.round(items.reduce((acc, item) => acc + item.progress, 0) / items.length);
              if (totalProgress === 100) {
                return <span title="历史数据已完全同步"><Database size={12} className="text-[#00bfa5] opacity-80" /></span>;
              }
              return (
                <div className="flex items-center gap-1 text-blue-400" title={`历史数据同步中: ${totalProgress}%`}>
                  <Database size={12} className="animate-pulse" />
                  <span className="text-[10px]">{totalProgress}%</span>
                </div>
              );
            })()}
          </Button>
          
          {showSymbolDropdown && (
            <div className={`absolute top-full left-0 mt-1 w-48 rounded-md border shadow-xl overflow-hidden z-50 ${
              theme === 'dark' ? 'bg-[#1e222d] border-[#2B2B43]' : 'bg-white border-[#e0e3eb]'
            }`}>
              <div className="max-h-60 overflow-y-auto">
                {availableSymbols.length === 0 ? (
                  <div className={`p-2 text-xs text-center ${theme === 'dark' ? 'text-gray-400' : 'text-gray-500'}`}>
                      No symbols found
                    </div>
                ) : (
                  availableSymbols.map(s => (
                    <div 
                      key={s}
                      onClick={() => {
                        updateActiveChart({ symbol: s });
                        setShowSymbolDropdown(false);
                      }}
                      className={`px-3 py-2 text-sm cursor-pointer ${
                        activeChart?.symbol === s 
                          ? (theme === 'dark' ? 'bg-[#2a2e39] text-[#00bfa5]' : 'bg-[#e0e3eb] text-[#00bfa5]')
                          : (theme === 'dark' ? 'text-white hover:bg-[#2a2e39]' : 'text-black hover:bg-[#e0e3eb]')
                      }`}
                    >
                      {s}
                    </div>
                  ))
                )}
              </div>
              <div className={`border-t ${theme === 'dark' ? 'border-[#2B2B43]' : 'border-[#e0e3eb]'}`}>
                <Button 
                  variant="ghost" 
                  className={`w-full justify-start text-xs rounded-none h-8 ${theme === 'dark' ? 'text-gray-300 hover:text-white hover:bg-[#2a2e39]' : 'text-gray-600 hover:text-black hover:bg-[#e0e3eb]'}`}
                  onClick={() => {
                    setShowSymbolDropdown(false);
                    setShowSymbolSearchModal(true);
                    fetchMt5Symbols();
                  }}
                >
                  <Plus size={14} className="mr-2" />
                  Search Symbol
                </Button>
              </div>
            </div>
          )}
        </div>

        <div className={`h-6 w-px ${theme === 'dark' ? 'bg-[#2B2B43]' : 'bg-[#e0e3eb]'}`}></div>

        {/* IndicatorB Dropdown */}
        <div className="relative">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowIndicatorBDropdown(!showIndicatorBDropdown)}
            className={`h-8 text-xs font-semibold flex items-center gap-1 ${
              theme === 'dark'
                ? "bg-transparent border-[#2B2B43] text-gray-300 hover:text-white hover:bg-white/10"
                : "bg-transparent border-[#e0e3eb] text-gray-600 hover:text-black hover:bg-black/10"
            }`}
          >
            通用指标
          </Button>
          
          {showIndicatorBDropdown && (
            <div className={`absolute top-full left-0 mt-1 w-48 rounded-md border shadow-xl overflow-hidden z-50 ${
              theme === 'dark' ? 'bg-[#1e222d] border-[#2B2B43]' : 'bg-white border-[#e0e3eb]'
            }`}>
              <div 
                  onClick={() => { updateActiveChart({ showIndB_RSI: !activeChart?.showIndB_RSI }); setShowIndicatorBDropdown(false); }}
                  className={`px-3 py-2 text-xs cursor-pointer flex justify-between items-center ${theme === 'dark' ? 'hover:bg-[#2a2e39] text-white' : 'hover:bg-[#e0e3eb] text-black'}`}
              >
                <span>RSI</span>
                {activeChart?.showIndB_RSI && <span className="text-[#00bfa5] font-bold">✓</span>}
              </div>
              <div 
                  onClick={() => { updateActiveChart({ showIndB_MACD: !activeChart?.showIndB_MACD }); setShowIndicatorBDropdown(false); }}
                  className={`px-3 py-2 text-xs cursor-pointer flex justify-between items-center ${theme === 'dark' ? 'hover:bg-[#2a2e39] text-white' : 'hover:bg-[#e0e3eb] text-black'}`}
              >
                <span>MACD</span>
                {activeChart?.showIndB_MACD && <span className="text-[#00bfa5] font-bold">✓</span>}
              </div>
              <div 
                  onClick={() => { updateActiveChart({ showIndB_EMA: !activeChart?.showIndB_EMA }); setShowIndicatorBDropdown(false); }}
                  className={`px-3 py-2 text-xs cursor-pointer flex justify-between items-center ${theme === 'dark' ? 'hover:bg-[#2a2e39] text-white' : 'hover:bg-[#e0e3eb] text-black'}`}
              >
                <span>EMA (9/20/50/200)</span>
                {activeChart?.showIndB_EMA && <span className="text-[#00bfa5] font-bold">✓</span>}
              </div>
              <div 
                  onClick={() => { updateActiveChart({ showIndB_BB: !activeChart?.showIndB_BB }); setShowIndicatorBDropdown(false); }}
                  className={`px-3 py-2 text-xs cursor-pointer flex justify-between items-center ${theme === 'dark' ? 'hover:bg-[#2a2e39] text-white' : 'hover:bg-[#e0e3eb] text-black'}`}
              >
                <span>Bollinger Bands</span>
                {activeChart?.showIndB_BB && <span className="text-[#00bfa5] font-bold">✓</span>}
              </div>
              <div 
                  onClick={() => { updateActiveChart({ showIndB_VWAP: !activeChart?.showIndB_VWAP }); setShowIndicatorBDropdown(false); }}
                  className={`px-3 py-2 text-xs cursor-pointer flex justify-between items-center ${theme === 'dark' ? 'hover:bg-[#2a2e39] text-white' : 'hover:bg-[#e0e3eb] text-black'}`}
              >
                <span>VWAP</span>
                {activeChart?.showIndB_VWAP && <span className="text-[#00bfa5] font-bold">✓</span>}
              </div>
              <div 
                  onClick={() => { updateActiveChart({ showIndB_ATR: !activeChart?.showIndB_ATR }); setShowIndicatorBDropdown(false); }}
                  className={`px-3 py-2 text-xs cursor-pointer flex justify-between items-center ${theme === 'dark' ? 'hover:bg-[#2a2e39] text-white' : 'hover:bg-[#e0e3eb] text-black'}`}
              >
                <span>ATR</span>
                {activeChart?.showIndB_ATR && <span className="text-[#00bfa5] font-bold">✓</span>}
              </div>
              <div 
                  onClick={() => { updateActiveChart({ showIndB_Zigzag: !activeChart?.showIndB_Zigzag }); setShowIndicatorBDropdown(false); }}
                  className={`px-3 py-2 text-xs cursor-pointer flex justify-between items-center ${theme === 'dark' ? 'hover:bg-[#2a2e39] text-white' : 'hover:bg-[#e0e3eb] text-black'}`}
              >
                <span>Zigzag</span>
                {activeChart?.showIndB_Zigzag && <span className="text-[#00bfa5] font-bold">✓</span>}
              </div>
            </div>
          )}
        </div>

        <div className={`h-6 w-px ${theme === 'dark' ? 'bg-[#2B2B43]' : 'bg-[#e0e3eb]'}`}></div>

        {/* Timeframe Selector (Controls Active Chart) */}
        <div className="flex gap-1">
          {timeframes.map((tf) => (
            <Button
              key={tf}
              variant={activeChart?.timeframe === tf ? "default" : "outline"}
              size="sm"
              onClick={() => {
                if (activeReplayState.isReplayMode) chartRefs.current[activeChartId]?.stopReplay();
                updateActiveChart({ timeframe: tf });
              }}
              className={`h-8 text-xs ${
                activeChart?.timeframe === tf 
                  ? "bg-[#00bfa5] text-black hover:bg-[#00a68f]" 
                  : theme === 'dark'
                    ? "bg-transparent border-transparent text-white hover:bg-white/10"
                    : "bg-transparent border-transparent text-black hover:bg-black/10"
              }`}
            >
              {tf}
            </Button>
          ))}
          
          <div className="relative">
            <Button
              variant={extendedTimeframes.includes(activeChart?.timeframe || "") ? "default" : "outline"}
              size="sm"
              onClick={() => setShowExtendedTf(!showExtendedTf)}
              className={`h-8 px-2 text-xs flex items-center gap-1 ${
                extendedTimeframes.includes(activeChart?.timeframe || "")
                  ? "bg-[#00bfa5] text-black hover:bg-[#00a68f]" 
                  : theme === 'dark'
                    ? "bg-transparent border-transparent text-white hover:bg-white/10"
                    : "bg-transparent border-transparent text-black hover:bg-black/10"
              }`}
            >
              {extendedTimeframes.includes(activeChart?.timeframe || "") ? activeChart?.timeframe : "▼"}
            </Button>
            
            {showExtendedTf && (
              <div className={`absolute top-full right-0 mt-1 w-16 rounded-md border shadow-xl overflow-hidden z-50 flex flex-col ${
                theme === 'dark' ? 'bg-[#1e222d] border-[#2B2B43]' : 'bg-white border-[#e0e3eb]'
              }`}>
                {extendedTimeframes.map(tf => (
                  <div 
                    key={tf}
                    onClick={() => {
                      if (activeReplayState.isReplayMode) chartRefs.current[activeChartId]?.stopReplay();
                      updateActiveChart({ timeframe: tf });
                      setShowExtendedTf(false);
                    }}
                    className={`px-3 py-2 text-xs cursor-pointer text-center ${
                      activeChart?.timeframe === tf 
                        ? (theme === 'dark' ? 'bg-[#00bfa5]/20 text-[#00bfa5]' : 'bg-[#00bfa5]/10 text-[#00a68f]')
                        : (theme === 'dark' ? 'text-white hover:bg-[#2a2e39]' : 'text-black hover:bg-[#f0f3fa]')
                    }`}
                  >
                    {tf}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
        
        <div className={`h-6 w-px ${theme === 'dark' ? 'bg-[#2B2B43]' : 'bg-[#e0e3eb]'}`}></div>

        {/* Indicators Dropdown (Controls Active Chart) */}
        <div className="relative">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowIndicatorsDropdown(!showIndicatorsDropdown)}
            className={`h-8 text-xs font-semibold flex items-center gap-1 ${
              theme === 'dark'
                ? "bg-transparent border-[#2B2B43] text-gray-300 hover:text-white hover:bg-white/10"
                : "bg-transparent border-[#e0e3eb] text-gray-600 hover:text-black hover:bg-black/10"
            }`}
          >
            高级指标
          </Button>
          
          {showIndicatorsDropdown && (
            <div className={`absolute top-full left-0 mt-1 w-48 rounded-md border shadow-xl overflow-hidden z-50 ${
              theme === 'dark' ? 'bg-[#1e222d] border-[#2B2B43]' : 'bg-white border-[#e0e3eb]'
            }`}>
              <div 
                  onClick={() => { updateActiveChart({ showBubble: !activeChart?.showBubble }); setShowIndicatorsDropdown(false); }}
                  className={`px-3 py-2 text-xs cursor-pointer flex justify-between items-center ${theme === 'dark' ? 'hover:bg-[#2a2e39] text-white' : 'hover:bg-[#e0e3eb] text-black'}`}
              >
                <span>Bubble</span>
                {activeChart?.showBubble && <span className="text-[#00bfa5] font-bold">✓</span>}
              </div>
              <div 
                  onClick={() => { updateActiveChart({ showVRVP: !activeChart?.showVRVP }); setShowIndicatorsDropdown(false); }}
                  className={`px-3 py-2 text-xs cursor-pointer flex justify-between items-center ${theme === 'dark' ? 'hover:bg-[#2a2e39] text-white' : 'hover:bg-[#e0e3eb] text-black'}`}
              >
                <span>Volume Profile (VRVP)</span>
                {activeChart?.showVRVP && <span className="text-[#00bfa5] font-bold">✓</span>}
              </div>
              <div 
                  onClick={() => { updateActiveChart({ showSVP: !activeChart?.showSVP }); setShowIndicatorsDropdown(false); }}
                  className={`px-3 py-2 text-xs cursor-pointer flex justify-between items-center ${theme === 'dark' ? 'hover:bg-[#2a2e39] text-white' : 'hover:bg-[#e0e3eb] text-black'}`}
              >
                <span>Session VP</span>
                {activeChart?.showSVP && <span className="text-[#00bfa5] font-bold">✓</span>}
              </div>
              <div 
                  onClick={() => { updateActiveChart({ showRajaSR: !activeChart?.showRajaSR }); setShowIndicatorsDropdown(false); }}
                  className={`px-3 py-2 text-xs cursor-pointer flex justify-between items-center ${theme === 'dark' ? 'hover:bg-[#2a2e39] text-white' : 'hover:bg-[#e0e3eb] text-black'}`}
              >
                <span>RajaSR Level Zone</span>
                {activeChart?.showRajaSR && <span className="text-[#00bfa5] font-bold">✓</span>}
              </div>
              <div 
                  onClick={() => { updateActiveChart({ showIndB_MSB_Zigzag: !activeChart?.showIndB_MSB_Zigzag }); setShowIndicatorsDropdown(false); }}
                  className={`px-3 py-2 text-xs cursor-pointer flex justify-between items-center ${theme === 'dark' ? 'hover:bg-[#2a2e39] text-white' : 'hover:bg-[#e0e3eb] text-black'}`}
              >
                <span>MSB Zigzag</span>
                {activeChart?.showIndB_MSB_Zigzag && <span className="text-[#00bfa5] font-bold">✓</span>}
              </div>
              <div 
                  onClick={() => { updateActiveChart({ showIndB_TrendExhaustion: !activeChart?.showIndB_TrendExhaustion }); setShowIndicatorsDropdown(false); }}
                  className={`px-3 py-2 text-xs cursor-pointer flex justify-between items-center ${theme === 'dark' ? 'hover:bg-[#2a2e39] text-white' : 'hover:bg-[#e0e3eb] text-black'}`}
              >
                <span>Trend Exhaustion</span>
                {activeChart?.showIndB_TrendExhaustion && <span className="text-[#00bfa5] font-bold">✓</span>}
              </div>
            </div>
          )}
        </div>

        <div className={`h-6 w-px ${theme === 'dark' ? 'bg-[#2B2B43]' : 'bg-[#e0e3eb]'}`}></div>
        
        {/* Global Theme Toggle */}
        <Button
          variant="outline"
          size="sm"
          onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
          className={`h-8 text-xs ${
            theme === 'dark'
              ? "bg-transparent border-white/20 text-white hover:bg-white/10"
              : "bg-transparent border-black/20 text-black hover:bg-black/10"
          }`}
        >
          {theme === 'dark' ? 'Light Mode' : 'Dark Mode'}
        </Button>
        
        <div className={`h-6 w-px ${theme === 'dark' ? 'bg-[#2B2B43]' : 'bg-[#e0e3eb]'}`}></div>

        {/* Snapshot Button (Controls Active Chart) */}
        <Button
          variant="outline"
          size="icon"
          onClick={() => chartRefs.current[activeChartId]?.takeScreenshot()}
          className={`h-8 w-8 ${theme === 'dark' ? 'bg-transparent border-white/20 text-white hover:bg-white/10' : 'bg-transparent border-black/20 text-black hover:bg-black/10'}`}
          title="快照截图"
        >
          <Camera size={14} />
        </Button>
        
        {/* Bar Replay Controls (Controls Active Chart) */}
        {!activeReplayState.isReplayMode ? (
          <Button
            variant="outline"
            size="sm"
            onClick={() => chartRefs.current[activeChartId]?.enterReplaySelectionMode()}
            className={`h-8 text-xs font-semibold ${
              activeReplayState.isSelectingReplayStart 
                ? "bg-[#00bfa5] text-black border-[#00bfa5] hover:bg-[#00a68f]" 
                : theme === 'dark'
                  ? "bg-transparent border-[#2B2B43] text-gray-300 hover:text-white hover:bg-white/10"
                  : "bg-transparent border-[#e0e3eb] text-gray-600 hover:text-black hover:bg-black/10"
            }`}
          >
            {activeReplayState.isSelectingReplayStart ? "Select start point..." : "Bar Replay"}
          </Button>
        ) : (
          <div className={`flex items-center gap-1 border rounded px-2 h-8 ${theme === 'dark' ? 'border-[#2B2B43] bg-black/50' : 'border-[#e0e3eb] bg-white/50'}`}>
            <Button
              variant="ghost"
              size="sm"
              className={`w-6 h-6 p-0 hover:bg-transparent ${activeReplayState.isSelectingReplayStart ? 'text-[#00bfa5]' : (theme === 'dark' ? 'text-gray-300 hover:text-white' : 'text-gray-600 hover:text-black')}`}
              onClick={() => chartRefs.current[activeChartId]?.enterReplaySelectionMode()}
              title="Select Replay Start"
            >
              <ArrowLeftToLine size={14} />
            </Button>
            
            <div className={`h-4 w-px mx-1 ${theme === 'dark' ? 'bg-[#2B2B43]' : 'bg-[#e0e3eb]'}`}></div>

            <Button
              variant="ghost"
              size="sm"
              className={`w-6 h-6 p-0 hover:bg-transparent ${theme === 'dark' ? 'text-gray-300 hover:text-white' : 'text-gray-600 hover:text-black'}`}
              onClick={() => chartRefs.current[activeChartId]?.prevReplayStep()}
              title="Step Back"
            >
              <StepBack size={14} />
            </Button>

            <Button
              variant="ghost"
              size="sm"
              className={`w-6 h-6 p-0 hover:bg-transparent ${theme === 'dark' ? 'text-[#00bfa5] hover:text-[#00a68f]' : 'text-[#00bfa5] hover:text-[#00a68f]'}`}
              onClick={() => chartRefs.current[activeChartId]?.togglePlay()}
            >
              {activeReplayState.isPlaying ? <Pause size={14} /> : <Play size={14} />}
            </Button>
            
            <Button
              variant="ghost"
              size="sm"
              className={`w-6 h-6 p-0 hover:bg-transparent ${theme === 'dark' ? 'text-gray-300 hover:text-white' : 'text-gray-600 hover:text-black'}`}
              onClick={() => chartRefs.current[activeChartId]?.nextReplayStep()}
              title="Step Forward"
            >
              <StepForward size={14} />
            </Button>

            <div className={`h-4 w-px mx-1 ${theme === 'dark' ? 'bg-[#2B2B43]' : 'bg-[#e0e3eb]'}`}></div>

            <select
              className={`h-6 bg-transparent border-none text-xs focus:outline-none cursor-pointer ${theme === 'dark' ? 'text-gray-300' : 'text-gray-600'}`}
              value={activeReplayState.replaySpeed}
              onChange={(e) => chartRefs.current[activeChartId]?.setReplaySpeed(Number(e.target.value))}
            >
              <option value={2000} className={theme === 'dark' ? 'bg-black' : 'bg-white'}>0.5x</option>
              <option value={1000} className={theme === 'dark' ? 'bg-black' : 'bg-white'}>1x</option>
              <option value={500} className={theme === 'dark' ? 'bg-black' : 'bg-white'}>2x</option>
              <option value={250} className={theme === 'dark' ? 'bg-black' : 'bg-white'}>4x</option>
              <option value={125} className={theme === 'dark' ? 'bg-black' : 'bg-white'}>8x</option>
            </select>

            <div className={`h-4 w-px mx-1 ${theme === 'dark' ? 'bg-[#2B2B43]' : 'bg-[#e0e3eb]'}`}></div>

            <Button
              variant="ghost"
              size="sm"
              className={`w-6 h-6 p-0 hover:bg-transparent text-red-500 hover:text-red-400`}
              onClick={() => chartRefs.current[activeChartId]?.stopReplay()}
              title="Stop Replay"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect></svg>
            </Button>
          </div>
        )}
      </div>

      {/* Settings Modal */}
      {showSettingsModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className={`w-[360px] p-5 rounded-lg shadow-xl ${theme === 'dark' ? 'bg-[#1e222d] text-white border border-[#2B2B43]' : 'bg-white text-black border border-[#e0e3eb]'}`}>
            <h2 className="text-lg font-bold mb-3">图表设置 (Settings)</h2>
            <div className="space-y-3 max-h-[60vh] overflow-y-auto pr-2 custom-scrollbar">
              
              {/* General Settings */}
              <div className="font-semibold text-sm pt-2 border-b border-white/10 pb-1">常规图表 (General)</div>
              <div className="flex justify-between items-center">
                <span className="text-xs">背景色 (Background)</span>
                <ColorPicker 
                  color={settings.backgroundColor || (theme === "dark" ? "#000000" : "#ffffff")} 
                  onChange={(color) => setSettings({ ...settings, backgroundColor: color })}
                  theme={theme}
                />
              </div>
              <div className="flex justify-between items-center">
                <span className="text-xs">阳线实体 (Candle Up)</span>
                <ColorPicker 
                  color={settings.candleUpColor} 
                  onChange={(color) => setSettings({ ...settings, candleUpColor: color })}
                  theme={theme}
                />
              </div>
              <div className="flex justify-between items-center">
                <span className="text-xs">阴线实体 (Candle Down)</span>
                <ColorPicker 
                  color={settings.candleDownColor} 
                  onChange={(color) => setSettings({ ...settings, candleDownColor: color })}
                  theme={theme}
                />
              </div>
              <div className="flex justify-between items-center">
                <span className="text-xs">阳线影线 (Wick Up)</span>
                <ColorPicker 
                  color={settings.wickUpColor} 
                  onChange={(color) => setSettings({ ...settings, wickUpColor: color })}
                  theme={theme}
                />
              </div>
              <div className="flex justify-between items-center">
                <span className="text-xs">阴线影线 (Wick Down)</span>
                <ColorPicker 
                  color={settings.wickDownColor} 
                  onChange={(color) => setSettings({ ...settings, wickDownColor: color })}
                  theme={theme}
                />
              </div>
              <div className="flex justify-between items-center">
                <span className="text-xs">显示网格 (Show Grid)</span>
                <input 
                  type="checkbox" 
                  checked={settings.showGrid} 
                  onChange={(e) => setSettings({ ...settings, showGrid: e.target.checked })}
                  className="w-3.5 h-3.5 rounded cursor-pointer"
                />
              </div>
              <div className="flex justify-between items-center">
                <span className="text-xs">显示买入价 (Show Bid Line)</span>
                <input 
                  type="checkbox" 
                  checked={settings.showBidLine} 
                  onChange={(e) => setSettings({ ...settings, showBidLine: e.target.checked })}
                  className="w-3.5 h-3.5 rounded cursor-pointer"
                />
              </div>
              <div className="flex justify-between items-center">
                <span className="text-xs">显示卖出价 (Show Ask Line)</span>
                <input 
                  type="checkbox" 
                  checked={settings.showAskLine} 
                  onChange={(e) => setSettings({ ...settings, showAskLine: e.target.checked })}
                  className="w-3.5 h-3.5 rounded cursor-pointer"
                />
              </div>

            </div>
            
            <div className="flex justify-end mt-5 gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setSettings(defaultSettings)}
                className={`flex-1 text-xs h-8 ${theme === 'dark' ? 'bg-transparent border-[#2B2B43] text-gray-300 hover:text-white hover:bg-[#2a2e39]' : 'bg-transparent border-[#e0e3eb] text-gray-600 hover:text-black hover:bg-[#f0f3fa]'}`}
              >
                恢复默认
              </Button>
              <Button 
                size="sm"
                onClick={() => setShowSettingsModal(false)}
                className="flex-1 text-xs h-8 bg-[#00bfa5] text-black hover:bg-[#00a68f]"
              >
                关闭
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Indicator Settings Modal */}
      {indicatorSettingsModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className={`w-[360px] p-5 rounded-lg shadow-xl ${theme === 'dark' ? 'bg-[#1e222d] text-white border border-[#2B2B43]' : 'bg-white text-black border border-[#e0e3eb]'}`}>
            <h2 className="text-lg font-bold mb-3">
              {indicatorSettingsModal === 'VRVP' ? 'Volume Profile (VRVP) 设置' : 
               indicatorSettingsModal === 'SVP' ? 'Session VP 设置' : 
               indicatorSettingsModal === 'RajaSR' ? 'RajaSR 设置' :
               indicatorSettingsModal === 'RSI' ? 'RSI 设置' :
               indicatorSettingsModal === 'MACD' ? 'MACD 设置' :
               indicatorSettingsModal === 'EMA' ? 'EMA 设置' :
               indicatorSettingsModal === 'BB' ? 'Bollinger Bands 设置' :
               indicatorSettingsModal === 'VWAP' ? 'VWAP 设置' :
               indicatorSettingsModal === 'ATR' ? 'ATR 设置' : 
               indicatorSettingsModal === 'Zigzag' ? 'Zigzag 设置' : 
               indicatorSettingsModal === 'MSB_Zigzag' ? 'MSB Zigzag 设置' : 
               indicatorSettingsModal === 'TrendExhaustion' ? 'Trend Exhaustion 设置' : ''}
            </h2>
            <div className="space-y-3 max-h-[60vh] overflow-y-auto pr-2 custom-scrollbar">
              
              {indicatorSettingsModal === 'VRVP' && (
                <>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">显示位置 (Placement)</span>
                    <select 
                      className={`h-6 bg-transparent border rounded text-xs px-1 focus:outline-none ${theme === 'dark' ? 'border-white/20' : 'border-black/20'}`}
                      value={settings.vrvpPlacement}
                      onChange={(e) => setSettings({ ...settings, vrvpPlacement: e.target.value as 'left'|'right' })}
                    >
                      <option value="right" className={theme === 'dark' ? 'bg-black text-white' : 'bg-white text-black'}>Right</option>
                      <option value="left" className={theme === 'dark' ? 'bg-black text-white' : 'bg-white text-black'}>Left</option>
                    </select>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">图表占比宽度 (Width %)</span>
                    <input 
                      type="number" min="10" max="100" step="5"
                      value={settings.vrvpWidth} 
                      onChange={(e) => setSettings({ ...settings, vrvpWidth: Number(e.target.value) })}
                      className={`w-16 h-6 px-1 text-xs bg-transparent border rounded focus:outline-none ${theme === 'dark' ? 'border-white/20' : 'border-black/20'}`}
                    />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">箱体数量 (Row Size)</span>
                    <input 
                      type="number" min="10" max="300" step="10"
                      value={settings.vrvpBins} 
                      onChange={(e) => setSettings({ ...settings, vrvpBins: Number(e.target.value) })}
                      className={`w-16 h-6 px-1 text-xs bg-transparent border rounded focus:outline-none ${theme === 'dark' ? 'border-white/20' : 'border-black/20'}`}
                    />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">价值区域占比 (VA Volume %)</span>
                    <input 
                      type="number" min="10" max="100" step="5"
                      value={settings.vrvpValueAreaPercentage} 
                      onChange={(e) => setSettings({ ...settings, vrvpValueAreaPercentage: Number(e.target.value) })}
                      className={`w-16 h-6 px-1 text-xs bg-transparent border rounded focus:outline-none ${theme === 'dark' ? 'border-white/20' : 'border-black/20'}`}
                    />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">控制点颜色 (POC Color)</span>
                    <ColorPicker color={settings.vrvpPocColor} onChange={(color) => setSettings({ ...settings, vrvpPocColor: color })} theme={theme} />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">买量颜色 (Up Volume)</span>
                    <ColorPicker color={settings.vrvpUpColor} onChange={(color) => setSettings({ ...settings, vrvpUpColor: color })} theme={theme} />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">卖量颜色 (Down Volume)</span>
                    <ColorPicker color={settings.vrvpDownColor} onChange={(color) => setSettings({ ...settings, vrvpDownColor: color })} theme={theme} />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">VA 内买量 (VA Up Volume)</span>
                    <ColorPicker color={settings.vrvpValueAreaUpColor} onChange={(color) => setSettings({ ...settings, vrvpValueAreaUpColor: color })} theme={theme} />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">VA 内卖量 (VA Down Volume)</span>
                    <ColorPicker color={settings.vrvpValueAreaDownColor} onChange={(color) => setSettings({ ...settings, vrvpValueAreaDownColor: color })} theme={theme} />
                  </div>
                </>
              )}

              {indicatorSettingsModal === 'SVP' && (
                <>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">计算天数 (Days)</span>
                    <input 
                      type="number" min="1" max="30" step="1"
                      value={settings.svpDaysToCalculate} 
                      onChange={(e) => setSettings({ ...settings, svpDaysToCalculate: Number(e.target.value) })}
                      className={`w-16 h-6 px-1 text-xs bg-transparent border rounded focus:outline-none ${theme === 'dark' ? 'border-white/20' : 'border-black/20'}`}
                    />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">宽度占比 (Max Width %)</span>
                    <input 
                      type="number" min="10" max="100" step="5"
                      value={settings.svpMaxWidthPercent} 
                      onChange={(e) => setSettings({ ...settings, svpMaxWidthPercent: Number(e.target.value) })}
                      className={`w-16 h-6 px-1 text-xs bg-transparent border rounded focus:outline-none ${theme === 'dark' ? 'border-white/20' : 'border-black/20'}`}
                    />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">箱体数量 (Row Size)</span>
                    <input 
                      type="number" min="10" max="300" step="10"
                      value={settings.svpBins} 
                      onChange={(e) => setSettings({ ...settings, svpBins: Number(e.target.value) })}
                      className={`w-16 h-6 px-1 text-xs bg-transparent border rounded focus:outline-none ${theme === 'dark' ? 'border-white/20' : 'border-black/20'}`}
                    />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">控制点颜色 (POC Color)</span>
                    <ColorPicker color={settings.svpPocColor} onChange={(color) => setSettings({ ...settings, svpPocColor: color })} theme={theme} />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">前1/3颜色 (Part 1)</span>
                    <ColorPicker color={settings.svpColorPart1} onChange={(color) => setSettings({ ...settings, svpColorPart1: color })} theme={theme} />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">中1/3颜色 (Part 2)</span>
                    <ColorPicker color={settings.svpColorPart2} onChange={(color) => setSettings({ ...settings, svpColorPart2: color })} theme={theme} />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">后1/3颜色 (Part 3)</span>
                    <ColorPicker color={settings.svpColorPart3} onChange={(color) => setSettings({ ...settings, svpColorPart3: color })} theme={theme} />
                  </div>
                </>
              )}

              {indicatorSettingsModal === 'RajaSR' && (
                <>
                  <div className="flex justify-between items-center">
                    <span className="text-xs" title="定义高低点的左右K线数量，默认2，过滤微小波动建议设为5">拐点阈值 (Pivot)</span>
                    <input type="number" min="1" max="20" className={`w-20 text-xs px-2 py-1 rounded border ${theme === 'dark' ? 'bg-[#2a2e39] border-[#2B2B43] text-white' : 'bg-white border-[#e0e3eb] text-black'}`} value={settings.rajaSRPivot} onChange={(e) => setSettings({ ...settings, rajaSRPivot: Number(e.target.value) })} />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs" title="回溯计算的K线数量，默认300根，太多可能影响性能">回溯K线数 (Lookback Bars)</span>
                    <input type="number" min="100" max="5000" step="100" className={`w-20 text-xs px-2 py-1 rounded border ${theme === 'dark' ? 'bg-[#2a2e39] border-[#2B2B43] text-white' : 'bg-white border-[#e0e3eb] text-black'}`} value={settings.rajaSRLookbackBars} onChange={(e) => setSettings({ ...settings, rajaSRLookbackBars: Number(e.target.value) })} />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs" title="形成支撑/阻力区域的最小历史触点数，默认5">最小触点数 (Min Touches)</span>
                    <input type="number" min="1" max="10" className={`w-20 text-xs px-2 py-1 rounded border ${theme === 'dark' ? 'bg-[#2a2e39] border-[#2B2B43] text-white' : 'bg-white border-[#e0e3eb] text-black'}`} value={settings.rajaSRMinTouches} onChange={(e) => setSettings({ ...settings, rajaSRMinTouches: Number(e.target.value) })} />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs" title="聚类吸附的容差(ATR倍数)，越小精度越高，默认0.35">聚类容差 (Tol ATR)</span>
                    <input type="number" step="0.01" min="0.01" max="1.0" className={`w-20 text-xs px-2 py-1 rounded border ${theme === 'dark' ? 'bg-[#2a2e39] border-[#2B2B43] text-white' : 'bg-white border-[#e0e3eb] text-black'}`} value={settings.rajaSRTolTrMult} onChange={(e) => setSettings({ ...settings, rajaSRTolTrMult: Number(e.target.value) })} />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs" title="单根K线的区域边距宽度，默认0.1">区域边距 (Margin ATR)</span>
                    <input type="number" step="0.01" min="0.01" max="0.5" className={`w-20 text-xs px-2 py-1 rounded border ${theme === 'dark' ? 'bg-[#2a2e39] border-[#2B2B43] text-white' : 'bg-white border-[#e0e3eb] text-black'}`} value={settings.rajaSRMarginTrMult} onChange={(e) => setSettings({ ...settings, rajaSRMarginTrMult: Number(e.target.value) })} />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">过滤策略 (Scope)</span>
                    <select 
                      className={`h-6 bg-transparent border rounded text-xs px-1 focus:outline-none ${theme === 'dark' ? 'border-white/20' : 'border-black/20'}`}
                      value={settings.rajaSRScope}
                      onChange={(e) => setSettings({ ...settings, rajaSRScope: e.target.value as 'nearest'|'all'|'trade' })}
                    >
                      <option value="nearest" className={theme === 'dark' ? 'bg-black text-white' : 'bg-white text-black'}>Nearest</option>
                      <option value="trade" className={theme === 'dark' ? 'bg-black text-white' : 'bg-white text-black'}>Trade</option>
                      <option value="all" className={theme === 'dark' ? 'bg-black text-white' : 'bg-white text-black'}>All</option>
                    </select>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">单侧最大显示数 (Max Zones)</span>
                    <input type="number" min="1" max="10" className={`w-20 text-xs px-2 py-1 rounded border ${theme === 'dark' ? 'bg-[#2a2e39] border-[#2B2B43] text-white' : 'bg-white border-[#e0e3eb] text-black'}`} value={settings.rajaSRMaxZonesEachSide} onChange={(e) => setSettings({ ...settings, rajaSRMaxZonesEachSide: Number(e.target.value) })} />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">区域填充颜色</span>
                    <ColorPicker color={settings.rajaSRZoneColor} onChange={(color) => setSettings({ ...settings, rajaSRZoneColor: color })} theme={theme} />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">区域边框颜色</span>
                    <ColorPicker color={settings.rajaSRZoneBorderColor} onChange={(color) => setSettings({ ...settings, rajaSRZoneBorderColor: color })} theme={theme} />
                  </div>
                </>
              )}

              {indicatorSettingsModal === 'RSI' && (
                <>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">RSI 周期 (Period)</span>
                    <input type="number" min="1" max="100" className={`w-20 text-xs px-2 py-1 rounded border ${theme === 'dark' ? 'bg-[#2a2e39] border-[#2B2B43] text-white' : 'bg-white border-[#e0e3eb] text-black'}`} value={settings.indB_RsiPeriod} onChange={(e) => setSettings({ ...settings, indB_RsiPeriod: Number(e.target.value) })} />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">RSI 线条颜色</span>
                    <ColorPicker color={settings.indB_RsiColor} onChange={(color) => setSettings({ ...settings, indB_RsiColor: color })} theme={theme} />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">SMA 周期 (Period)</span>
                    <input type="number" min="1" max="100" className={`w-20 text-xs px-2 py-1 rounded border ${theme === 'dark' ? 'bg-[#2a2e39] border-[#2B2B43] text-white' : 'bg-white border-[#e0e3eb] text-black'}`} value={settings.indB_RsiSmaPeriod} onChange={(e) => setSettings({ ...settings, indB_RsiSmaPeriod: Number(e.target.value) })} />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">SMA 线条颜色</span>
                    <ColorPicker color={settings.indB_RsiSmaColor} onChange={(color) => setSettings({ ...settings, indB_RsiSmaColor: color })} theme={theme} />
                  </div>
                </>
              )}

              {indicatorSettingsModal === 'MACD' && (
                <>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">快线周期 (Fast)</span>
                    <input type="number" min="1" max="100" className={`w-20 text-xs px-2 py-1 rounded border ${theme === 'dark' ? 'bg-[#2a2e39] border-[#2B2B43] text-white' : 'bg-white border-[#e0e3eb] text-black'}`} value={settings.indB_MacdFast} onChange={(e) => setSettings({ ...settings, indB_MacdFast: Number(e.target.value) })} />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">慢线周期 (Slow)</span>
                    <input type="number" min="1" max="200" className={`w-20 text-xs px-2 py-1 rounded border ${theme === 'dark' ? 'bg-[#2a2e39] border-[#2B2B43] text-white' : 'bg-white border-[#e0e3eb] text-black'}`} value={settings.indB_MacdSlow} onChange={(e) => setSettings({ ...settings, indB_MacdSlow: Number(e.target.value) })} />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">信号线周期 (Signal)</span>
                    <input type="number" min="1" max="100" className={`w-20 text-xs px-2 py-1 rounded border ${theme === 'dark' ? 'bg-[#2a2e39] border-[#2B2B43] text-white' : 'bg-white border-[#e0e3eb] text-black'}`} value={settings.indB_MacdSignal} onChange={(e) => setSettings({ ...settings, indB_MacdSignal: Number(e.target.value) })} />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">MACD 线颜色</span>
                    <ColorPicker color={settings.indB_MacdLineColor} onChange={(color) => setSettings({ ...settings, indB_MacdLineColor: color })} theme={theme} />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">Signal 线颜色</span>
                    <ColorPicker color={settings.indB_MacdSignalColor} onChange={(color) => setSettings({ ...settings, indB_MacdSignalColor: color })} theme={theme} />
                  </div>
                </>
              )}

              {indicatorSettingsModal === 'EMA' && (
                <>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">EMA 1</span>
                    <div className="flex items-center gap-2">
                      <ColorPicker color={settings.indB_Ema1Color} onChange={(color) => setSettings({ ...settings, indB_Ema1Color: color })} theme={theme} />
                      <input type="number" min="1" max="500" className={`w-16 text-xs px-2 py-1 rounded border ${theme === 'dark' ? 'bg-[#2a2e39] border-[#2B2B43] text-white' : 'bg-white border-[#e0e3eb] text-black'}`} value={settings.indB_Ema1} onChange={(e) => setSettings({ ...settings, indB_Ema1: Number(e.target.value) })} />
                    </div>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">EMA 2</span>
                    <div className="flex items-center gap-2">
                      <ColorPicker color={settings.indB_Ema2Color} onChange={(color) => setSettings({ ...settings, indB_Ema2Color: color })} theme={theme} />
                      <input type="number" min="1" max="500" className={`w-16 text-xs px-2 py-1 rounded border ${theme === 'dark' ? 'bg-[#2a2e39] border-[#2B2B43] text-white' : 'bg-white border-[#e0e3eb] text-black'}`} value={settings.indB_Ema2} onChange={(e) => setSettings({ ...settings, indB_Ema2: Number(e.target.value) })} />
                    </div>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">EMA 3</span>
                    <div className="flex items-center gap-2">
                      <ColorPicker color={settings.indB_Ema3Color} onChange={(color) => setSettings({ ...settings, indB_Ema3Color: color })} theme={theme} />
                      <input type="number" min="1" max="500" className={`w-16 text-xs px-2 py-1 rounded border ${theme === 'dark' ? 'bg-[#2a2e39] border-[#2B2B43] text-white' : 'bg-white border-[#e0e3eb] text-black'}`} value={settings.indB_Ema3} onChange={(e) => setSettings({ ...settings, indB_Ema3: Number(e.target.value) })} />
                    </div>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">EMA 4</span>
                    <div className="flex items-center gap-2">
                      <ColorPicker color={settings.indB_Ema4Color} onChange={(color) => setSettings({ ...settings, indB_Ema4Color: color })} theme={theme} />
                      <input type="number" min="1" max="500" className={`w-16 text-xs px-2 py-1 rounded border ${theme === 'dark' ? 'bg-[#2a2e39] border-[#2B2B43] text-white' : 'bg-white border-[#e0e3eb] text-black'}`} value={settings.indB_Ema4} onChange={(e) => setSettings({ ...settings, indB_Ema4: Number(e.target.value) })} />
                    </div>
                  </div>
                </>
              )}

              {indicatorSettingsModal === 'BB' && (
                <>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">周期 (Period)</span>
                    <input type="number" min="1" max="200" className={`w-20 text-xs px-2 py-1 rounded border ${theme === 'dark' ? 'bg-[#2a2e39] border-[#2B2B43] text-white' : 'bg-white border-[#e0e3eb] text-black'}`} value={settings.indB_BbPeriod} onChange={(e) => setSettings({ ...settings, indB_BbPeriod: Number(e.target.value) })} />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">标准差倍数 (StdDev)</span>
                    <input type="number" step="0.1" min="0.1" max="10" className={`w-20 text-xs px-2 py-1 rounded border ${theme === 'dark' ? 'bg-[#2a2e39] border-[#2B2B43] text-white' : 'bg-white border-[#e0e3eb] text-black'}`} value={settings.indB_BbStdDev} onChange={(e) => setSettings({ ...settings, indB_BbStdDev: Number(e.target.value) })} />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">线条颜色</span>
                    <ColorPicker color={settings.indB_BbColor} onChange={(color) => setSettings({ ...settings, indB_BbColor: color })} theme={theme} />
                  </div>
                </>
              )}

              {indicatorSettingsModal === 'VWAP' && (
                <>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">线条颜色</span>
                    <ColorPicker color={settings.indB_VwapColor} onChange={(color) => setSettings({ ...settings, indB_VwapColor: color })} theme={theme} />
                  </div>
                  <div className="text-xs text-gray-500 italic mt-2">
                    VWAP 是基于每日 (UTC) 重新计算的成交量加权平均价，暂无其他可调参数。
                  </div>
                </>
              )}

              {indicatorSettingsModal === 'ATR' && (
                <>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">周期 (Period)</span>
                    <input type="number" min="1" max="100" className={`w-20 text-xs px-2 py-1 rounded border ${theme === 'dark' ? 'bg-[#2a2e39] border-[#2B2B43] text-white' : 'bg-white border-[#e0e3eb] text-black'}`} value={settings.indB_AtrPeriod} onChange={(e) => setSettings({ ...settings, indB_AtrPeriod: Number(e.target.value) })} />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">线条颜色</span>
                    <ColorPicker color={settings.indB_AtrColor} onChange={(color) => setSettings({ ...settings, indB_AtrColor: color })} theme={theme} />
                  </div>
                </>
              )}

              {indicatorSettingsModal === 'Zigzag' && (
                <>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">枢轴周期 (Pivot Period)</span>
                    <input type="number" min="1" max="100" step="1" className={`w-20 text-xs px-2 py-1 rounded border ${theme === 'dark' ? 'bg-[#2a2e39] border-[#2B2B43] text-white' : 'bg-white border-[#e0e3eb] text-black'}`} value={settings.indB_ZigzagDeviation} onChange={(e) => setSettings({ ...settings, indB_ZigzagDeviation: Number(e.target.value) })} />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">线条颜色</span>
                    <ColorPicker color={settings.indB_ZigzagColor} onChange={(color) => setSettings({ ...settings, indB_ZigzagColor: color })} theme={theme} />
                  </div>
                </>
              )}

              {indicatorSettingsModal === 'MSB_Zigzag' && (
                <>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">枢轴周期 (Pivot Period)</span>
                    <input type="number" min="1" max="100" step="1" className={`w-20 text-xs px-2 py-1 rounded border ${theme === 'dark' ? 'bg-[#2a2e39] border-[#2B2B43] text-white' : 'bg-white border-[#e0e3eb] text-black'}`} value={settings.indB_MSB_ZigzagLength} onChange={(e) => setSettings({ ...settings, indB_MSB_ZigzagLength: Number(e.target.value) })} />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">线条颜色</span>
                    <ColorPicker color={settings.indB_MSB_ZigzagColor} onChange={(color) => setSettings({ ...settings, indB_MSB_ZigzagColor: color })} theme={theme} />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">线条粗细</span>
                    <input type="number" min="1" max="5" step="1" className={`w-20 text-xs px-2 py-1 rounded border ${theme === 'dark' ? 'bg-[#2a2e39] border-[#2B2B43] text-white' : 'bg-white border-[#e0e3eb] text-black'}`} value={settings.indB_MSB_ZigzagWidth} onChange={(e) => setSettings({ ...settings, indB_MSB_ZigzagWidth: Number(e.target.value) })} />
                  </div>
                  <div className="flex justify-between items-center mt-2">
                    <span className="text-xs">显示 ZigZag 线</span>
                    <input type="checkbox" checked={settings.indB_MSB_showZigZag} onChange={(e) => setSettings({ ...settings, indB_MSB_showZigZag: e.target.checked })} className="w-3.5 h-3.5" />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">显示标签 (HH/LL)</span>
                    <input type="checkbox" checked={settings.indB_MSB_showLabel} onChange={(e) => setSettings({ ...settings, indB_MSB_showLabel: e.target.checked })} className="w-3.5 h-3.5" />
                  </div>
                  <div className="h-px w-full bg-gray-500/20 my-1"></div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">Major Bullish BoS Color</span>
                    <ColorPicker color={settings.indB_MSB_majorBuBoSColor} onChange={(color) => setSettings({ ...settings, indB_MSB_majorBuBoSColor: color })} theme={theme} />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">Major Bullish BoS</span>
                    <input type="checkbox" checked={settings.indB_MSB_showMajorBuBoS} onChange={(e) => setSettings({ ...settings, indB_MSB_showMajorBuBoS: e.target.checked })} className="w-3.5 h-3.5" />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">Major Bearish BoS Color</span>
                    <ColorPicker color={settings.indB_MSB_majorBeBoSColor} onChange={(color) => setSettings({ ...settings, indB_MSB_majorBeBoSColor: color })} theme={theme} />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">Major Bearish BoS</span>
                    <input type="checkbox" checked={settings.indB_MSB_showMajorBeBoS} onChange={(e) => setSettings({ ...settings, indB_MSB_showMajorBeBoS: e.target.checked })} className="w-3.5 h-3.5" />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">Major Bullish ChoCh Color</span>
                    <ColorPicker color={settings.indB_MSB_majorBuChoChColor} onChange={(color) => setSettings({ ...settings, indB_MSB_majorBuChoChColor: color })} theme={theme} />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">Major Bullish ChoCh</span>
                    <input type="checkbox" checked={settings.indB_MSB_showMajorBuChoCh} onChange={(e) => setSettings({ ...settings, indB_MSB_showMajorBuChoCh: e.target.checked })} className="w-3.5 h-3.5" />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">Major Bearish ChoCh Color</span>
                    <ColorPicker color={settings.indB_MSB_majorBeChoChColor} onChange={(color) => setSettings({ ...settings, indB_MSB_majorBeChoChColor: color })} theme={theme} />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">Major Bearish ChoCh</span>
                    <input type="checkbox" checked={settings.indB_MSB_showMajorBeChoCh} onChange={(e) => setSettings({ ...settings, indB_MSB_showMajorBeChoCh: e.target.checked })} className="w-3.5 h-3.5" />
                  </div>
                  <div className="h-px w-full bg-gray-500/20 my-1"></div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">Minor Bullish BoS Color</span>
                    <ColorPicker color={settings.indB_MSB_minorBuBoSColor} onChange={(color) => setSettings({ ...settings, indB_MSB_minorBuBoSColor: color })} theme={theme} />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">Minor Bullish BoS</span>
                    <input type="checkbox" checked={settings.indB_MSB_showMinorBuBoS} onChange={(e) => setSettings({ ...settings, indB_MSB_showMinorBuBoS: e.target.checked })} className="w-3.5 h-3.5" />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">Minor Bearish BoS Color</span>
                    <ColorPicker color={settings.indB_MSB_minorBeBoSColor} onChange={(color) => setSettings({ ...settings, indB_MSB_minorBeBoSColor: color })} theme={theme} />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">Minor Bearish BoS</span>
                    <input type="checkbox" checked={settings.indB_MSB_showMinorBeBoS} onChange={(e) => setSettings({ ...settings, indB_MSB_showMinorBeBoS: e.target.checked })} className="w-3.5 h-3.5" />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">Minor Bullish ChoCh Color</span>
                    <ColorPicker color={settings.indB_MSB_minorBuChoChColor} onChange={(color) => setSettings({ ...settings, indB_MSB_minorBuChoChColor: color })} theme={theme} />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">Minor Bullish ChoCh</span>
                    <input type="checkbox" checked={settings.indB_MSB_showMinorBuChoCh} onChange={(e) => setSettings({ ...settings, indB_MSB_showMinorBuChoCh: e.target.checked })} className="w-3.5 h-3.5" />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">Minor Bearish ChoCh Color</span>
                    <ColorPicker color={settings.indB_MSB_minorBeChoChColor} onChange={(color) => setSettings({ ...settings, indB_MSB_minorBeChoChColor: color })} theme={theme} />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">Minor Bearish ChoCh</span>
                    <input type="checkbox" checked={settings.indB_MSB_showMinorBeChoCh} onChange={(e) => setSettings({ ...settings, indB_MSB_showMinorBeChoCh: e.target.checked })} className="w-3.5 h-3.5" />
                  </div>
                </>
              )}

              {indicatorSettingsModal === 'TrendExhaustion' && (
                <>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">Cold Color (Bull)</span>
                    <ColorPicker color={settings.indB_TE_colorBull} onChange={(color) => setSettings({ ...settings, indB_TE_colorBull: color })} theme={theme} />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">Hot Color (Bear)</span>
                    <ColorPicker color={settings.indB_TE_colorBear} onChange={(color) => setSettings({ ...settings, indB_TE_colorBear: color })} theme={theme} />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">Exhaustion Threshold</span>
                    <input type="number" min="1" max="50" step="1" className={`w-20 text-xs px-2 py-1 rounded border ${theme === 'dark' ? 'bg-[#2a2e39] border-[#2B2B43] text-white' : 'bg-white border-[#e0e3eb] text-black'}`} value={settings.indB_TE_threshold} onChange={(e) => setSettings({ ...settings, indB_TE_threshold: Number(e.target.value) })} />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">Fast Length</span>
                    <input type="number" min="1" max="500" step="1" className={`w-20 text-xs px-2 py-1 rounded border ${theme === 'dark' ? 'bg-[#2a2e39] border-[#2B2B43] text-white' : 'bg-white border-[#e0e3eb] text-black'}`} value={settings.indB_TE_shortLength} onChange={(e) => setSettings({ ...settings, indB_TE_shortLength: Number(e.target.value) })} />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">Fast Smoothing Length</span>
                    <input type="number" min="1" max="100" step="1" className={`w-20 text-xs px-2 py-1 rounded border ${theme === 'dark' ? 'bg-[#2a2e39] border-[#2B2B43] text-white' : 'bg-white border-[#e0e3eb] text-black'}`} value={settings.indB_TE_shortSmoothingLength} onChange={(e) => setSettings({ ...settings, indB_TE_shortSmoothingLength: Number(e.target.value) })} />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">Slow Length</span>
                    <input type="number" min="1" max="500" step="1" className={`w-20 text-xs px-2 py-1 rounded border ${theme === 'dark' ? 'bg-[#2a2e39] border-[#2B2B43] text-white' : 'bg-white border-[#e0e3eb] text-black'}`} value={settings.indB_TE_longLength} onChange={(e) => setSettings({ ...settings, indB_TE_longLength: Number(e.target.value) })} />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">Slow Smoothing Length</span>
                    <input type="number" min="1" max="100" step="1" className={`w-20 text-xs px-2 py-1 rounded border ${theme === 'dark' ? 'bg-[#2a2e39] border-[#2B2B43] text-white' : 'bg-white border-[#e0e3eb] text-black'}`} value={settings.indB_TE_longSmoothingLength} onChange={(e) => setSettings({ ...settings, indB_TE_longSmoothingLength: Number(e.target.value) })} />
                  </div>
                  <div className="h-px w-full bg-gray-500/20 my-1"></div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">Draw Boxes on Chart</span>
                    <input type="checkbox" checked={settings.indB_TE_showBoxes} onChange={(e) => setSettings({ ...settings, indB_TE_showBoxes: e.target.checked })} className="w-3.5 h-3.5" />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs">Draw Shapes (Warnings/Reversals)</span>
                    <input type="checkbox" checked={settings.indB_TE_showShapes} onChange={(e) => setSettings({ ...settings, indB_TE_showShapes: e.target.checked })} className="w-3.5 h-3.5" />
                  </div>
                </>
              )}
            </div>
            
            <div className="flex justify-end mt-5 gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  if (indicatorSettingsModal === 'MSB_Zigzag') {
                    setSettings({
                      ...settings,
                      indB_MSB_ZigzagLength: defaultSettings.indB_MSB_ZigzagLength,
                      indB_MSB_ZigzagWidth: defaultSettings.indB_MSB_ZigzagWidth,
                      indB_MSB_ZigzagColor: defaultSettings.indB_MSB_ZigzagColor,
                      indB_MSB_showZigZag: defaultSettings.indB_MSB_showZigZag,
                      indB_MSB_zigZagStyle: defaultSettings.indB_MSB_zigZagStyle,
                      indB_MSB_showLabel: defaultSettings.indB_MSB_showLabel,
                      indB_MSB_labelColor: defaultSettings.indB_MSB_labelColor,
                      indB_MSB_showMajorBuBoS: defaultSettings.indB_MSB_showMajorBuBoS,
                      indB_MSB_majorBuBoSStyle: defaultSettings.indB_MSB_majorBuBoSStyle,
                      indB_MSB_majorBuBoSColor: defaultSettings.indB_MSB_majorBuBoSColor,
                      indB_MSB_showMajorBeBoS: defaultSettings.indB_MSB_showMajorBeBoS,
                      indB_MSB_majorBeBoSStyle: defaultSettings.indB_MSB_majorBeBoSStyle,
                      indB_MSB_majorBeBoSColor: defaultSettings.indB_MSB_majorBeBoSColor,
                      indB_MSB_showMinorBuBoS: defaultSettings.indB_MSB_showMinorBuBoS,
                      indB_MSB_minorBuBoSStyle: defaultSettings.indB_MSB_minorBuBoSStyle,
                      indB_MSB_minorBuBoSColor: defaultSettings.indB_MSB_minorBuBoSColor,
                      indB_MSB_showMinorBeBoS: defaultSettings.indB_MSB_showMinorBeBoS,
                      indB_MSB_minorBeBoSStyle: defaultSettings.indB_MSB_minorBeBoSStyle,
                      indB_MSB_minorBeBoSColor: defaultSettings.indB_MSB_minorBeBoSColor,
                      indB_MSB_showMajorBuChoCh: defaultSettings.indB_MSB_showMajorBuChoCh,
                      indB_MSB_majorBuChoChStyle: defaultSettings.indB_MSB_majorBuChoChStyle,
                      indB_MSB_majorBuChoChColor: defaultSettings.indB_MSB_majorBuChoChColor,
                      indB_MSB_showMajorBeChoCh: defaultSettings.indB_MSB_showMajorBeChoCh,
                      indB_MSB_majorBeChoChStyle: defaultSettings.indB_MSB_majorBeChoChStyle,
                      indB_MSB_majorBeChoChColor: defaultSettings.indB_MSB_majorBeChoChColor,
                      indB_MSB_showMinorBuChoCh: defaultSettings.indB_MSB_showMinorBuChoCh,
                      indB_MSB_minorBuChoChStyle: defaultSettings.indB_MSB_minorBuChoChStyle,
                      indB_MSB_minorBuChoChColor: defaultSettings.indB_MSB_minorBuChoChColor,
                      indB_MSB_showMinorBeChoCh: defaultSettings.indB_MSB_showMinorBeChoCh,
                      indB_MSB_minorBeChoChStyle: defaultSettings.indB_MSB_minorBeChoChStyle,
                      indB_MSB_minorBeChoChColor: defaultSettings.indB_MSB_minorBeChoChColor,
                    });
                  } else if (indicatorSettingsModal === 'TrendExhaustion') {
                    setSettings({
                      ...settings,
                      indB_TE_colorBull: defaultSettings.indB_TE_colorBull,
                      indB_TE_colorBear: defaultSettings.indB_TE_colorBear,
                      indB_TE_threshold: defaultSettings.indB_TE_threshold,
                      indB_TE_shortLength: defaultSettings.indB_TE_shortLength,
                      indB_TE_shortSmoothingLength: defaultSettings.indB_TE_shortSmoothingLength,
                      indB_TE_longLength: defaultSettings.indB_TE_longLength,
                      indB_TE_longSmoothingLength: defaultSettings.indB_TE_longSmoothingLength,
                      indB_TE_showBoxes: defaultSettings.indB_TE_showBoxes,
                      indB_TE_showShapes: defaultSettings.indB_TE_showShapes,
                    });
                  } else if (indicatorSettingsModal === 'RajaSR') {
                    setSettings({
                      ...settings,
                      rajaSRPivot: defaultSettings.rajaSRPivot,
                      rajaSRLookbackBars: defaultSettings.rajaSRLookbackBars,
                      rajaSRMinTouches: defaultSettings.rajaSRMinTouches,
                      rajaSRTolTrMult: defaultSettings.rajaSRTolTrMult,
                      rajaSRMarginTrMult: defaultSettings.rajaSRMarginTrMult,
                      rajaSRScope: defaultSettings.rajaSRScope,
                      rajaSRMaxZonesEachSide: defaultSettings.rajaSRMaxZonesEachSide,
                      rajaSRZoneColor: defaultSettings.rajaSRZoneColor,
                    });
                  } else if (indicatorSettingsModal === 'VRVP') {
                    setSettings({
                      ...settings,
                      vrvpPlacement: defaultSettings.vrvpPlacement,
                      vrvpWidth: defaultSettings.vrvpWidth,
                      vrvpBins: defaultSettings.vrvpBins,
                      vrvpValueAreaPercentage: defaultSettings.vrvpValueAreaPercentage,
                      vrvpUpColor: defaultSettings.vrvpUpColor,
                      vrvpDownColor: defaultSettings.vrvpDownColor,
                      vrvpValueAreaUpColor: defaultSettings.vrvpValueAreaUpColor,
                      vrvpValueAreaDownColor: defaultSettings.vrvpValueAreaDownColor,
                      vrvpPocColor: defaultSettings.vrvpPocColor,
                    });
                  } else if (indicatorSettingsModal === 'SVP') {
                    setSettings({
                      ...settings,
                      svpDaysToCalculate: defaultSettings.svpDaysToCalculate,
                      svpMaxWidthPercent: defaultSettings.svpMaxWidthPercent,
                      svpBins: defaultSettings.svpBins,
                      svpValueAreaPct: defaultSettings.svpValueAreaPct,
                      svpColorPart1: defaultSettings.svpColorPart1,
                      svpColorPart2: defaultSettings.svpColorPart2,
                      svpColorPart3: defaultSettings.svpColorPart3,
                      svpPocColor: defaultSettings.svpPocColor,
                    });
                  } else {
                    // 对于基础指标等，直接全量恢复（如果需要更细化可后续补充）
                    setSettings(defaultSettings);
                  }
                }}
                className={`flex-1 text-xs h-8 ${theme === 'dark' ? 'bg-transparent border-[#2B2B43] text-gray-300 hover:text-white hover:bg-white/10' : 'bg-transparent border-[#e0e3eb] text-gray-600 hover:text-black hover:bg-black/5'}`}
              >
                恢复当前默认
              </Button>
              <Button
                size="sm"
                onClick={() => setIndicatorSettingsModal(null)}
                className="flex-1 text-xs h-8 bg-[#00bfa5] text-black hover:bg-[#00a68f]"
              >
                完成 (Done)
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Broker Connection Modal */}
      {showBrokerModal && (
        <div className="absolute inset-0 z-[70] flex items-center justify-center bg-black/80 backdrop-blur-sm">
          <div className={`p-6 rounded-xl border w-[400px] shadow-2xl flex flex-col ${theme === 'dark' ? 'bg-[#131722] border-[#2B2B43]' : 'bg-white border-[#e0e3eb]'}`}>
            <h3 className={`text-lg font-bold mb-4 flex justify-between items-center ${theme === 'dark' ? 'text-white' : 'text-black'}`}>
              关联经纪商 MT5
              {activeBroker && (
                <Button variant="ghost" size="sm" onClick={() => setShowBrokerModal(false)} className={`h-8 px-2 ${theme === 'dark' ? 'text-gray-400 hover:text-white' : 'text-gray-500 hover:text-black'}`}>
                  Close
                </Button>
              )}
            </h3>
            <p className={`text-xs mb-4 ${theme === 'dark' ? 'text-gray-400' : 'text-gray-500'}`}>
              Please enter your MT5 broker details. Only the Server is required for pulling data from an active terminal.
            </p>
            <div className="flex flex-col gap-3">
              <input
                type="text" placeholder="Server (e.g. MetaQuotes-Demo) *"
                value={brokerForm.server} onChange={e => setBrokerForm({...brokerForm, server: e.target.value})}
                className={`h-10 px-3 text-sm border rounded focus:outline-none focus:ring-1 focus:ring-[#00bfa5] ${theme === 'dark' ? 'bg-[#1e222d] border-[#2B2B43] text-white' : 'bg-gray-50 border-gray-300 text-black'}`}
              />
              <input
                type="text" placeholder="Login ID (Optional)"
                value={brokerForm.login} onChange={e => setBrokerForm({...brokerForm, login: e.target.value})}
                className={`h-10 px-3 text-sm border rounded focus:outline-none focus:ring-1 focus:ring-[#00bfa5] ${theme === 'dark' ? 'bg-[#1e222d] border-[#2B2B43] text-white' : 'bg-gray-50 border-gray-300 text-black'}`}
              />
              <input
                type="password" placeholder="Password (Optional)"
                value={brokerForm.password} onChange={e => setBrokerForm({...brokerForm, password: e.target.value})}
                className={`h-10 px-3 text-sm border rounded focus:outline-none focus:ring-1 focus:ring-[#00bfa5] ${theme === 'dark' ? 'bg-[#1e222d] border-[#2B2B43] text-white' : 'bg-gray-50 border-gray-300 text-black'}`}
              />
              <input
                type="text" placeholder="Terminal Path (Optional)"
                value={brokerForm.path} onChange={e => setBrokerForm({...brokerForm, path: e.target.value})}
                className={`h-10 px-3 text-sm border rounded focus:outline-none focus:ring-1 focus:ring-[#00bfa5] ${theme === 'dark' ? 'bg-[#1e222d] border-[#2B2B43] text-white' : 'bg-gray-50 border-gray-300 text-black'}`}
              />
              <Button 
                onClick={handleConnectBroker}
                disabled={connectingBroker}
                className="h-10 bg-[#00bfa5] text-black hover:bg-[#00a68f] mt-2 font-bold"
              >
                {connectingBroker ? "Connecting..." : "Connect"}
              </Button>
            </div>
          </div>
        </div>
      )}
      {showSymbolSearchModal && (
        <div className="absolute inset-0 z-[60] flex items-center justify-center bg-black/80 backdrop-blur-sm">
          <div className={`p-6 rounded-xl border w-[500px] shadow-2xl flex flex-col max-h-[80vh] ${theme === 'dark' ? 'bg-[#131722] border-[#2B2B43]' : 'bg-white border-[#e0e3eb]'}`}>
            <h3 className={`text-lg font-bold mb-4 flex justify-between items-center ${theme === 'dark' ? 'text-white' : 'text-black'}`}>
              {availableSymbols.length === 0 ? "Welcome! Add a Symbol" : "Search & Add MT5 Symbol"}
              <div className="flex items-center gap-2">
                <Button 
                  variant="outline" 
                  size="sm" 
                  onClick={() => setShowBrokerModal(true)}
                  className={`h-8 px-2 text-xs ${theme === 'dark' ? 'border-[#00bfa5] text-[#00bfa5] hover:bg-[#00bfa5]/10' : 'border-[#00bfa5] text-[#00a68f] hover:bg-[#00bfa5]/10'}`}
                >
                  Broker: {activeBroker?.server || 'None'}
                </Button>
                <Button 
                  variant="ghost" 
                  size="sm" 
                  onClick={() => setShowSymbolSearchModal(false)}
                  className={`h-8 px-2 ${theme === 'dark' ? 'text-gray-400 hover:text-white' : 'text-gray-500 hover:text-black'}`}
                >
                  Close
                </Button>
              </div>
            </h3>
            
            <div className="flex gap-2 mb-4">
              <input
                type="text"
                placeholder="Search symbol (e.g. EURUSD, XAU)..."
                value={symbolSearchQuery}
                onChange={(e) => setSymbolSearchQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    fetchMt5Symbols(symbolSearchQuery);
                  }
                }}
                className={`flex-1 h-10 px-3 text-sm border rounded focus:outline-none focus:ring-1 focus:ring-[#00bfa5] ${
                  theme === 'dark' 
                    ? 'bg-[#1e222d] border-[#2B2B43] text-white placeholder-gray-500' 
                    : 'bg-gray-50 border-gray-300 text-black placeholder-gray-400'
                }`}
              />
              <Button 
                onClick={() => fetchMt5Symbols(symbolSearchQuery)}
                disabled={searchingSymbols}
                className="h-10 bg-[#00bfa5] text-black hover:bg-[#00a68f]"
              >
                {searchingSymbols ? "..." : "Search"}
              </Button>
            </div>

            <div className={`flex-1 overflow-y-auto border rounded-lg ${theme === 'dark' ? 'border-[#2B2B43]' : 'border-gray-200'}`}>
              {searchingSymbols ? (
                <div className={`p-8 text-center text-sm ${theme === 'dark' ? 'text-gray-400' : 'text-gray-500'}`}>
                  Searching MT5 broker...
                </div>
              ) : mt5Symbols.length === 0 ? (
                <div className={`p-8 text-center text-sm ${theme === 'dark' ? 'text-gray-400' : 'text-gray-500'}`}>
                  No symbols found.
                </div>
              ) : (
                <div className="flex flex-col divide-y divide-opacity-10 divide-white">
                  {mt5Symbols.map(sym => (
                    <div 
                      key={sym.name} 
                      className={`flex items-center justify-between p-3 ${
                        theme === 'dark' ? 'hover:bg-[#1e222d]' : 'hover:bg-gray-50'
                      }`}
                    >
                      <div className="flex flex-col">
                        <span className={`font-semibold text-sm ${theme === 'dark' ? 'text-white' : 'text-black'}`}>
                          {sym.name}
                        </span>
                        <span className={`text-xs ${theme === 'dark' ? 'text-gray-400' : 'text-gray-500'}`}>
                          {sym.description} • {sym.category}
                        </span>
                      </div>
                      <Button 
                        size="sm"
                        onClick={() => handleAddSymbol(sym.name)}
                        disabled={availableSymbols.includes(sym.name) || addingSymbol === sym.name}
                        className={`h-7 text-xs ${
                          availableSymbols.includes(sym.name)
                            ? 'bg-gray-500 text-gray-300 cursor-not-allowed'
                            : addingSymbol === sym.name
                            ? 'bg-[#00bfa5] text-black cursor-wait'
                            : 'bg-transparent border border-[#00bfa5] text-[#00bfa5] hover:bg-[#00bfa5] hover:text-black'
                        }`}
                      >
                        {availableSymbols.includes(sym.name) ? 'Added' : addingSymbol === sym.name ? 'Loading...' : 'Add'}
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Alert Modal */}
      {alertMessage && (
        <div className="absolute inset-0 z-[60] flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className={`p-6 rounded-xl border w-80 shadow-2xl ${theme === 'dark' ? 'bg-[#1e222d] border-[#2B2B43]' : 'bg-white border-[#e0e3eb]'}`}>
            <h3 className={`text-lg font-bold mb-4 ${theme === 'dark' ? 'text-white' : 'text-black'}`}>
              提示
            </h3>
            <p className={`text-sm mb-6 ${theme === 'dark' ? 'text-gray-300' : 'text-gray-600'}`}>
              {alertMessage}
            </p>
            <div className="flex justify-end">
              <Button 
                variant="default" 
                onClick={() => setAlertMessage(null)}
                className="bg-[#00bfa5] text-black hover:bg-[#00a68f]"
              >
                确定
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Confirm Modal */}
      {confirmDialog && (
        <div className="absolute inset-0 z-[60] flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className={`p-6 rounded-xl border w-96 shadow-2xl ${theme === 'dark' ? 'bg-[#1e222d] border-[#2B2B43]' : 'bg-white border-[#e0e3eb]'}`}>
            <h3 className={`text-lg font-bold mb-4 ${theme === 'dark' ? 'text-white' : 'text-black'}`}>
              确认操作
            </h3>
            <p className={`text-sm mb-6 ${theme === 'dark' ? 'text-gray-300' : 'text-gray-600'}`}>
              {confirmDialog.message}
            </p>
            <div className="flex justify-end gap-3">
              <Button 
                variant="outline" 
                onClick={confirmDialog.onCancel}
                className={theme === 'dark' ? 'bg-transparent text-white border-gray-600 hover:bg-white/10' : 'bg-transparent text-black border-gray-300 hover:bg-black/5'}
              >
                取消
              </Button>
              <Button 
                variant="default" 
                onClick={confirmDialog.onConfirm}
                className="bg-[#00bfa5] text-black hover:bg-[#00a68f]"
              >
                确认覆盖
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Chart Grid */}
      <div className={`flex-1 w-full p-[2px] gap-[2px] grid ${getGridClass(layoutCount)} ${theme === 'dark' ? 'bg-[#2B2B43]' : 'bg-[#e0e3eb]'} overflow-hidden`}>
        {charts.map(c => (
          <div 
            key={c.id}
            onClickCapture={() => setActiveChartId(c.id)}
            className={`relative w-full h-full min-h-0 min-w-0 ${theme === 'dark' ? 'bg-black' : 'bg-white'} ${activeChartId === c.id ? 'ring-2 ring-inset ring-[#00bfa5] z-10' : ''}`}
          >
            <SingleChart 
                  ref={el => { chartRefs.current[c.id] = el; }}
                  id={c.id}
                  symbol={c.symbol}
                  timeframe={c.timeframe}
                  theme={theme}
                  showBubble={c.showBubble}
                  showVRVP={c.showVRVP}
                  showSVP={c.showSVP}
                  showRajaSR={c.showRajaSR}
                  showIndB_RSI={c.showIndB_RSI}
                  showIndB_MACD={c.showIndB_MACD}
                  showIndB_EMA={c.showIndB_EMA}
                  showIndB_BB={c.showIndB_BB}
                  showIndB_VWAP={c.showIndB_VWAP}
                  showIndB_ATR={c.showIndB_ATR}
                  showIndB_Zigzag={c.showIndB_Zigzag}
                  showIndB_MSB_Zigzag={c.showIndB_MSB_Zigzag}
                  showIndB_TrendExhaustion={c.showIndB_TrendExhaustion}
                  isActive={activeChartId === c.id}
                  selectionMode={activeChartId === c.id ? selectionMode : false}
                  onSelectRange={(fromTime, toTime, drawingId) => {
                    if (activeChartId !== c.id) return;
                    setSelectionRange({ from: fromTime, to: toTime });
                    setSelectionMode(false);
                    setSelectionDrawingId(drawingId || null);
                    setRightPanel("agent");
                  }}
              onReplayStateChange={(id, state) => setReplayStates(p => ({...p, [id]: state}))}
              onCrosshairMove={handleCrosshairMove}
              onRangeChange={handleRangeChange}
              onContextMenu={handleContextMenu}
              settings={settings}
              onToggleIndicator={(indicator) => {
                setCharts(prev => prev.map(ch => {
                  if (ch.id === c.id) {
                    if (indicator === 'VRVP') return { ...ch, showVRVP: !ch.showVRVP };
                    if (indicator === 'SVP') return { ...ch, showSVP: !ch.showSVP };
                    if (indicator === 'RajaSR') return { ...ch, showRajaSR: !ch.showRajaSR };
                    if (indicator === 'RSI') return { ...ch, showIndB_RSI: !ch.showIndB_RSI };
                    if (indicator === 'MACD') return { ...ch, showIndB_MACD: !ch.showIndB_MACD };
                    if (indicator === 'EMA') return { ...ch, showIndB_EMA: !ch.showIndB_EMA };
                    if (indicator === 'BB') return { ...ch, showIndB_BB: !ch.showIndB_BB };
                    if (indicator === 'VWAP') return { ...ch, showIndB_VWAP: !ch.showIndB_VWAP };
                    if (indicator === 'ATR') return { ...ch, showIndB_ATR: !ch.showIndB_ATR };
                    if (indicator === 'Zigzag') return { ...ch, showIndB_Zigzag: !ch.showIndB_Zigzag };
                    if (indicator === 'MSB_Zigzag') return { ...ch, showIndB_MSB_Zigzag: !ch.showIndB_MSB_Zigzag };
                    if (indicator === 'TrendExhaustion') return { ...ch, showIndB_TrendExhaustion: !ch.showIndB_TrendExhaustion };
                  }
                  return ch;
                }));
              }}
              onOpenSettings={(indicator) => {
                setIndicatorSettingsModal(indicator as IndicatorType);
              }}
            />
          </div>
        ))}
      </div>

      {/* Right Click Context Menu */}
      {contextMenu?.show && (
        <>
          <div 
            className="fixed inset-0 z-40" 
            onClick={() => setContextMenu(null)}
            onContextMenu={(e) => { e.preventDefault(); setContextMenu(null); }}
          />
          <div 
            className={`fixed z-50 min-w-[150px] rounded-md border shadow-xl py-1 flex flex-col ${theme === 'dark' ? 'bg-[#1e222d] border-[#2B2B43]' : 'bg-white border-[#e0e3eb]'}`}
            style={{ top: contextMenu.y, left: contextMenu.x }}
          >
            <button
              className={`w-full text-left px-4 py-2 text-sm ${theme === 'dark' ? 'text-gray-300 hover:text-white hover:bg-[#2a2e39]' : 'text-gray-600 hover:text-black hover:bg-[#e0e3eb]'}`}
              onClick={() => {
                setContextMenu(null);
                setShowSettingsModal(true);
              }}
            >
              图表设置 (Settings)
            </button>
            <div className={`h-px w-full ${theme === 'dark' ? 'bg-[#2B2B43]' : 'bg-[#e0e3eb]'}`}></div>
            <button
              className={`w-full text-left px-4 py-2 text-sm text-red-500 hover:text-red-400 ${theme === 'dark' ? 'hover:bg-[#2a2e39]' : 'hover:bg-[#e0e3eb]'}`}
              onClick={() => {
                setContextMenu(null);
                if (activeChartId) {
                  updateActiveChart({
                    showSVP: false,
                    showVRVP: false,
                    showBubble: false,
                    showRajaSR: false,
                    showIndB_RSI: false,
                    showIndB_MACD: false,
                    showIndB_EMA: false,
                    showIndB_BB: false,
                    showIndB_VWAP: false,
                  showIndB_ATR: false,
                  showIndB_Zigzag: false,
                });
                }
              }}
            >
              移除所有指标 (Remove All Indicators)
            </button>
            <button
              className={`w-full text-left px-4 py-2 text-sm text-red-500 hover:text-red-400 ${theme === 'dark' ? 'hover:bg-[#2a2e39]' : 'hover:bg-[#e0e3eb]'}`}
              onClick={() => {
                setContextMenu(null);
                if (activeChartId && chartRefs.current[activeChartId]) {
                  chartRefs.current[activeChartId]?.removeAllDrawings();
                }
              }}
            >
              移除所有绘图 (Remove All Drawings)
            </button>
          </div>
        </>
      )}
      </div>

      {/* 右侧：顶部状态栏占位（避免与上方工具栏打架） + 固定状态栏 + 详情面板 */}
      <div className="h-full shrink-0 flex flex-col">
        {/* 顶部占位条：让右侧区域与顶部工具栏对齐（视觉一致且不遮挡） */}
        <div
          className={`h-[52px] border-b ${
            theme === "dark" ? "bg-[#0b0f14] border-[#2B2B43]" : "bg-white border-[#e0e3eb]"
          }`}
        />

        <div className="flex-1 min-h-0 flex">
          {/* Resize handle：仅当详情面板打开时出现 */}
          {rightPanel !== "none" && (
            <div
              className="w-1 cursor-col-resize bg-transparent hover:bg-white/10"
              onMouseDown={(e) => {
                resizingRef.current = true;
                startXRef.current = e.clientX;
                startWRef.current = rightPanelWidth;
                document.body.style.cursor = "col-resize";
                document.body.style.userSelect = "none";
                e.preventDefault();
              }}
              title="拖拽调整面板宽度"
            />
          )}
          {rightPanel !== "none" && (
            <RightPanel
              open={true}
              panel={rightPanel}
              width={rightPanelWidth}
              symbol={activeChart?.symbol}
              timeframe={activeChart?.timeframe}
              theme={theme}
              chartEnabled={{
                svp: !!activeChart?.showSVP,
                vrvp: !!activeChart?.showVRVP,
                bubble: !!activeChart?.showBubble,
                RajaSR: !!activeChart?.showRajaSR,
                RSI: !!activeChart?.showIndB_RSI,
                MACD: !!activeChart?.showIndB_MACD,
                EMA: !!activeChart?.showIndB_EMA,
                BB: !!activeChart?.showIndB_BB,
                VWAP: !!activeChart?.showIndB_VWAP,
                ATR: !!activeChart?.showIndB_ATR,
                Zigzag: !!activeChart?.showIndB_Zigzag,
              }}
              selectionRange={selectionRange}
              selectionMode={selectionMode}
              onStartSelection={() => {
                // 清除旧选区框（不影响其它绘图）
                if (activeChartId && selectionDrawingId) {
                  chartRefs.current[activeChartId]?.removeDrawing?.(selectionDrawingId);
                }
                setSelectionDrawingId(null);
                setSelectionRange(null);
                setSelectionMode(true);
              }}
              onClearSelection={() => {
                if (activeChartId && selectionDrawingId) {
                  chartRefs.current[activeChartId]?.removeDrawing?.(selectionDrawingId);
                }
                setSelectionDrawingId(null);
                setSelectionRange(null);
                setSelectionMode(false);
              }}
              onPickVisibleRange={() => {
                if (!activeChartId) return;
                const r = (chartRefs.current[activeChartId] as any)?.getVisibleTimeRange?.() ?? null;
                if (!r) {
                  setAlertMessage("无法获取可视区间（请先加载K线数据）");
                  return;
                }
                setSelectionDrawingId(null);
                setSelectionRange({ from: r.from, to: r.to });
                setSelectionMode(false);
                setRightPanel("agent");
              }}
              onPickSelectedRectangle={() => {
                if (!activeChartId) return;
                const r = (chartRefs.current[activeChartId] as any)?.getSelectedRectangleTimeRange?.() ?? null;
                if (!r) {
                  setAlertMessage("请先用 Rectangle 工具画一个框，并点击选中该框（边框高亮）");
                  return;
                }
                setSelectionDrawingId(null);
                setSelectionRange({ from: r.from, to: r.to });
                setSelectionMode(false);
                setRightPanel("agent");
              }}
              focusTime={focusTime}
              onJumpToTime={(t) => {
                if (activeChartId && chartRefs.current[activeChartId]) {
                  chartRefs.current[activeChartId]?.scrollToTime(t);
                }
              }}
              onReplayAtTime={(t) => {
                if (activeChartId && chartRefs.current[activeChartId]) {
                  chartRefs.current[activeChartId]?.startReplayAtTime(t);
                }
              }}
              onSetTradeMarkers={(markers) => {
                if (activeChartId && chartRefs.current[activeChartId]) {
                  chartRefs.current[activeChartId]?.setTradeMarkers(markers || []);
                }
              }}
              onSetTimeframe={(tf) => {
                if (!tf) return;
                if (activeReplayState.isReplayMode) chartRefs.current[activeChartId]?.stopReplay();
                updateActiveChart({ timeframe: tf });
              }}
              onSetBacktestPositions={(trades) => {
                if (activeChartId && chartRefs.current[activeChartId]) {
                  chartRefs.current[activeChartId]?.setBacktestPositions(trades || []);
                }
              }}
              onClearBacktestPositions={() => {
                if (activeChartId && chartRefs.current[activeChartId]) {
                  chartRefs.current[activeChartId]?.clearBacktestPositions();
                }
              }}
              onSetStudyMarkers={(markers) => {
                if (activeChartId && chartRefs.current[activeChartId]) {
                  chartRefs.current[activeChartId]?.setStudyMarkers(markers || []);
                }
              }}
              onClearStudyMarkers={() => {
                if (activeChartId && chartRefs.current[activeChartId]) {
                  chartRefs.current[activeChartId]?.clearStudyMarkers();
                }
              }}
              onRequestScreenshot={async () => {
                if (!activeChartId || !chartRefs.current[activeChartId]) return null;
                return (chartRefs.current[activeChartId] as any)?.captureScreenshotDataUrl?.() ?? null;
              }}
              onAiExecuteActions={async (actions: any[]) => {
                const out: string[] = [];
                if (!Array.isArray(actions) || !activeChartId) return out;
                for (const a of actions) {
                  const t = String(a?.type || a?.action || "");
                  try {
                    if (t === "draw_trendline" || t === "add_marker" || t === "draw_box" || t === "trendline" || t === "marker" || t === "hline" || t === "box" || t === "arrow") {
                      // AI Agent System sends simplified JSON objects
                      const objs = [a];
                      await (chartRefs.current[activeChartId] as any)?.drawObjects?.(objs);
                      out.push(`draw ${t}`);
                    } else if (t === "chart_set_symbol") {
                      const s = String(a?.symbol || "").trim();
                      if (s) {
                        updateActiveChart({ symbol: s });
                        out.push(`set_symbol ${s}`);
                      }
                    } else if (t === "chart_set_timeframe") {
                      const tf = String(a?.timeframe || "").trim();
                      if (tf) {
                        if (activeReplayState.isReplayMode) chartRefs.current[activeChartId]?.stopReplay();
                        updateActiveChart({ timeframe: tf });
                        out.push(`set_timeframe ${tf}`);
                      }
                    } else if (t === "chart_toggle_indicator") {
                      const id = String(a?.id || "");
                      const enabled = !!a?.enabled;
                      if (id === "svp") updateActiveChart({ showSVP: enabled });
                      else if (id === "vrvp") updateActiveChart({ showVRVP: enabled });
                      else if (id === "bubble") updateActiveChart({ showBubble: enabled });
                      else if (id === "RajaSR") updateActiveChart({ showRajaSR: enabled });
                      else if (id === "RSI") updateActiveChart({ showIndB_RSI: enabled });
                      else if (id === "MACD") updateActiveChart({ showIndB_MACD: enabled });
                      else if (id === "EMA") updateActiveChart({ showIndB_EMA: enabled });
                      else if (id === "BB") updateActiveChart({ showIndB_BB: enabled });
                      else if (id === "VWAP") updateActiveChart({ showIndB_VWAP: enabled });
                      else if (id === "ATR") updateActiveChart({ showIndB_ATR: enabled });
                      else if (id === "Zigzag") updateActiveChart({ showIndB_Zigzag: enabled });
                      out.push(`toggle ${id}=${enabled ? "on" : "off"}`);
                    } else if (t === "chart_clear_all_indicators") {
                      updateActiveChart({
                        showSVP: false,
                        showVRVP: false,
                        showBubble: false,
                        showRajaSR: false,
                        showIndB_RSI: false,
                        showIndB_MACD: false,
                        showIndB_EMA: false,
                        showIndB_BB: false,
                        showIndB_VWAP: false,
                        showIndB_ATR: false,
                        showIndB_Zigzag: false,
                      });
                      out.push("clear_all_indicators");
                    } else if (t === "chart_clear_drawings") {
                      chartRefs.current[activeChartId]?.removeAllDrawings();
                      out.push("clear_drawings");
                    } else if (t === "chart_take_screenshot") {
                      chartRefs.current[activeChartId]?.takeScreenshot();
                      out.push("screenshot");
                    } else if (t === "chart_scroll_to_time") {
                      const time = Number(a?.time);
                      if (Number.isFinite(time)) {
                        chartRefs.current[activeChartId]?.scrollToTime(time);
                        out.push(`scroll_to ${Math.floor(time)}`);
                      }
                    } else if (t === "chart_start_replay_at_time") {
                      const time = Number(a?.time);
                      if (Number.isFinite(time)) {
                        chartRefs.current[activeChartId]?.startReplayAtTime(time);
                        out.push(`replay_at ${Math.floor(time)}`);
                      }
                    } else if (t === "chart_set_replay_speed") {
                      const mul = Math.max(1, Math.min(20, Number(a?.speed_multiplier || 1)));
                      const ms = Math.max(50, Math.round(1000 / mul));
                      chartRefs.current[activeChartId]?.setReplaySpeed(ms);
                      out.push(`set_replay_speed ${mul}x (${ms}ms)`);
                    } else if (t === "chart_play") {
                      // 说明：setPlaying 内部有防护（依赖 isReplayMode state），
                      // 在刚执行 startReplayAtTime 的同一轮 action 里直接 setPlaying(true)
                      // 可能因为 state 尚未更新而被忽略；延迟到下一帧可确保生效。
                      setTimeout(() => chartRefs.current[activeChartId]?.setPlaying?.(true), 0);
                      out.push("play");
                    } else if (t === "chart_pause") {
                      chartRefs.current[activeChartId]?.setPlaying?.(false);
                      out.push("pause");
                    } else if (t === "chart_stop_replay") {
                      chartRefs.current[activeChartId]?.stopReplay();
                      out.push("stop_replay");
                    } else if (t === "chart_next") {
                      chartRefs.current[activeChartId]?.nextReplayStep();
                      out.push("next");
                    } else if (t === "chart_prev") {
                      chartRefs.current[activeChartId]?.prevReplayStep();
                      out.push("prev");
                    } else if (t === "chart_reset_view") {
                      chartRefs.current[activeChartId]?.resetView();
                      out.push("reset_view");
                    } else if (t === "chart_clear_markers") {
                      chartRefs.current[activeChartId]?.setTradeMarkers([]);
                      chartRefs.current[activeChartId]?.clearStudyMarkers();
                      out.push("clear_markers");
                    } else if (t === "chart_clear_ai_overlays") {
                      (chartRefs.current[activeChartId] as any)?.removeAiOverlays?.();
                      out.push("clear_ai_overlays");
                    } else if (t === "chart_draw") {
                      const objs = Array.isArray(a?.objects) ? a.objects : [];
                      // drawObjects 可能需要确保历史数据覆盖到标注时间点，因此支持 async
                      await (chartRefs.current[activeChartId] as any)?.drawObjects?.(objs);
                      out.push(`draw ${objs.length}`);
                    } else if (t === "chart_set_range") {
                      const days = a?.days != null ? Number(a.days) : null;
                      const bars = a?.bars != null ? Number(a.bars) : null;
                      // 用“当前图表最新一根K线时间”作为基准（离线历史数据时，Date.now() 会导致回看无效）
                      const latest = await (chartRefs.current[activeChartId] as any)?.getLatestBarTime?.();
                      const baseSec = Number.isFinite(Number(latest)) ? Math.floor(Number(latest)) : Math.floor(Date.now() / 1000);
                      const tf = String(activeChart?.timeframe || "M5");
                      const tfSec =
                        tf === "M1"
                          ? 60
                          : tf === "M5"
                            ? 300
                            : tf === "M15"
                              ? 900
                              : tf === "M30"
                                ? 1800
                                : tf === "H1"
                                  ? 3600
                                  : tf === "H4"
                                    ? 14400
                                    : 86400;
                      let target = null as null | number;
                      if (days && Number.isFinite(days)) target = baseSec - Math.floor(days * 86400);
                      else if (bars && Number.isFinite(bars)) target = baseSec - Math.floor(bars * tfSec);
                      if (target) {
                        // 关键：先确保历史数据覆盖到目标时间，否则 scrollToTime 会被 clamp 到最老的一根，看起来像“没动”
                        try {
                          const ok = await (chartRefs.current[activeChartId] as any)?.ensureHistoryBefore?.(target);
                          if (ok === false) out.push("提示：历史数据不足，已滚动到最早可用K线附近");
                        } catch {}
                        chartRefs.current[activeChartId]?.scrollToTime(target);
                        out.push(`set_range ${days ? `${days}d` : `${bars} bars`}`);
                      }
                    } else if (t === "chart_replay_from_range") {
                      const days = a?.days != null ? Number(a.days) : null;
                      const bars = a?.bars != null ? Number(a.bars) : null;
                      const mul = Math.max(1, Math.min(20, Number(a?.speed_multiplier || 8)));
                      const latest = await (chartRefs.current[activeChartId] as any)?.getLatestBarTime?.();
                      const baseSec = Number.isFinite(Number(latest)) ? Math.floor(Number(latest)) : Math.floor(Date.now() / 1000);
                      const tf = String(activeChart?.timeframe || "M5");
                      const tfSec =
                        tf === "M1"
                          ? 60
                          : tf === "M5"
                            ? 300
                            : tf === "M15"
                              ? 900
                              : tf === "M30"
                                ? 1800
                                : tf === "H1"
                                  ? 3600
                                  : tf === "H4"
                                    ? 14400
                                    : 86400;
                      let target = null as null | number;
                      if (days && Number.isFinite(days)) target = baseSec - Math.floor(days * 86400);
                      else if (bars && Number.isFinite(bars)) target = baseSec - Math.floor(bars * tfSec);
                      if (target) {
                        try {
                          const ok = await (chartRefs.current[activeChartId] as any)?.ensureHistoryBefore?.(target);
                          if (ok === false) out.push("提示：历史数据不足，回放将从最早可用K线附近开始");
                        } catch {}
                        chartRefs.current[activeChartId]?.scrollToTime(target);
                        const ms = Math.max(50, Math.round(1000 / mul));
                        chartRefs.current[activeChartId]?.setReplaySpeed(ms);
                        chartRefs.current[activeChartId]?.startReplayAtTime(target);
                        // startReplayAtTime 会触发 setIsReplayMode(true)（异步 state），
                        // 若在同一 tick 立刻 setPlaying(true)，可能因为旧 state 未更新而被内部 guard 忽略。
                        // 延迟到下一帧再 play，确保可靠自动播放。
                        setTimeout(() => chartRefs.current[activeChartId]?.setPlaying?.(true), 0);
                        out.push(`replay_from_range ${days ? `${days}d` : `${bars} bars`} @ ${mul}x`);
                      }
                    } else {
                      out.push(`skip unknown: ${t || "?"}`);
                    }
                  } catch (e: any) {
                    out.push(`error ${t}: ${e?.message || e}`);
                  }
                }
                return out;
              }}
              onClose={() => setRightPanel("none")}
            />
          )}
          <RightRail active={rightPanel} onToggle={setRightPanel} />
        </div>
      </div>
    </div>
  );
}
