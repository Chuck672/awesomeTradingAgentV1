"use client";

import React, { useMemo } from "react";
import { X } from "lucide-react";
import { AiAssistantPanel } from "./AiAssistantPanel";
import { ChatStrategyPanel } from "./ChatStrategyPanel";
import { AlertsPanel } from "./AlertsPanel";
import { PipelineWorkbenchPanel } from "./PipelineWorkbenchPanel";
import { PatternInspectorPanel } from "./PatternInspectorPanel";
import { CalendarPanel } from "./CalendarPanel";
import type { RightPanelId } from "./RightRail";

export function RightPanel(props: {
  open: boolean;
  panel: Exclude<RightPanelId, "none">;
  width: number;
  symbol?: string;
  timeframe?: string;
  theme?: 'dark' | 'light';
  chartEnabled?: { 
    svp?: boolean; 
    vrvp?: boolean; 
    bubble?: boolean;
    RajaSR?: boolean;
    RSI?: boolean;
    MACD?: boolean;
    EMA?: boolean;
    BB?: boolean;
    VWAP?: boolean;
    ATR?: boolean;
    Zigzag?: boolean;
  };
  selectionRange?: { from: number; to: number } | null;
  selectionMode?: boolean;
  onStartSelection?: () => void;
  onClearSelection?: () => void;
  onPickVisibleRange?: () => void;
  onPickSelectedRectangle?: () => void;
  onRequestScreenshot?: () => Promise<string | null> | (string | null);
  focusTime?: number | null;
  onJumpToTime?: (t: number) => void;
  onReplayAtTime?: (t: number) => void;
  onSetTradeMarkers?: (markers: any[]) => void;
  onSetBacktestPositions?: (trades: any[]) => void;
  onSetTimeframe?: (tf: string) => void;
  onClearBacktestPositions?: () => void;
  onSetStudyMarkers?: (markers: any[]) => void;
  onClearStudyMarkers?: () => void;
  onAiExecuteActions?: (actions: any[]) => Promise<string[]> | string[];
  onClose: () => void;
}) {
  const {
    open,
    panel,
    width,
    symbol,
    timeframe,
    chartEnabled,
    selectionRange,
    selectionMode,
    onStartSelection,
    onClearSelection,
    onPickVisibleRange,
    onPickSelectedRectangle,
    onRequestScreenshot,
    focusTime,
    onJumpToTime,
    onReplayAtTime,
    onSetTradeMarkers,
    onSetBacktestPositions,
    onSetTimeframe,
    onClearBacktestPositions,
    onSetStudyMarkers,
    onClearStudyMarkers,
    onAiExecuteActions,
    onClose,
    theme = 'dark',
  } = props;

  const title = useMemo(() => {
    if (panel === "ai") return "AI";
    if (panel === "chat") return "Chat / Strategy";
    if (panel === "alerts") return "Alerts";
    if (panel === "scan") return "Pipeline";
    if (panel === "patterns") return "Patterns Inspector";
    if (panel === "calendar") return "Economic Calendar";
    return "";
  }, [panel]);

  if (!open) return null;

  return (
    <aside
      className="h-full shrink-0 border-l dark:border-white/10 border-black/10 dark:bg-[#0b0f14] bg-white dark:text-gray-200 text-gray-800 flex flex-col"
      style={{ width }}
    >
      <div className="px-3 py-2 border-b dark:border-white/10 border-black/10 flex items-center justify-between">
        <div>
          <div className="text-xs dark:text-gray-400 text-gray-500">awesomeChart</div>
          <div className="text-sm font-semibold">{title}</div>
          {symbol && timeframe && (
            <div className="text-[11px] text-gray-500">
              {symbol} {timeframe}
            </div>
          )}
        </div>
        <button
          className="w-8 h-8 rounded-lg border dark:border-white/10 border-black/10 hover:dark:bg-white/5 bg-black/5 flex items-center justify-center"
          onClick={onClose}
          title="关闭"
        >
          <X size={18} />
        </button>
      </div>

      <div className="flex-1 overflow-hidden p-3">
        {panel === "ai" && (
          <AiAssistantPanel
            chartState={{ symbol, timeframe, enabled: chartEnabled }}
            onExecuteActions={(actions) => (onAiExecuteActions ? onAiExecuteActions(actions) : [])}
            selectionRange={selectionRange || null}
            selectionMode={!!selectionMode}
            onStartSelection={() => onStartSelection?.()}
            onClearSelection={() => onClearSelection?.()}
            onPickVisibleRange={() => onPickVisibleRange?.()}
            onPickSelectedRectangle={() => onPickSelectedRectangle?.()}
            onRequestScreenshot={onRequestScreenshot}
          />
        )}
        {panel === "chat" && <ChatStrategyPanel />}
        {panel === "alerts" && <AlertsPanel symbol={symbol} timeframe={timeframe} />}
        {panel === "scan" && <PipelineWorkbenchPanel onExecuteActions={(actions) => (onAiExecuteActions ? onAiExecuteActions(actions) : [])} />}
        {panel === "patterns" && <PatternInspectorPanel symbol={symbol} timeframe={timeframe} onExecuteActions={onAiExecuteActions} />}
        {panel === "calendar" && <CalendarPanel />}
      </div>
    </aside>
  );
}
