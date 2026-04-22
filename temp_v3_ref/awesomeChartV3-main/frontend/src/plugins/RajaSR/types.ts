import { CustomSeriesOptions, customSeriesDefaultOptions, Time } from "lightweight-charts";

export interface RajaSROptions extends CustomSeriesOptions {
  pivot: number;
  minTouches: number;
  tolAbs?: number;
  tolTrMult: number;
  marginAbs?: number;
  marginTrMult: number;
  maxZonesEachSide: number;
  scope: "nearest" | "all" | "trade";
  zoneColor: string;
  zoneBorderColor: string;
  lookbackBars: number;
}

export const defaultRajaSROptions: RajaSROptions = {
  ...customSeriesDefaultOptions,
  visible: false,
  pivot: 2,
  minTouches: 2,
  tolTrMult: 0.20,
  marginTrMult: 0.06,
  maxZonesEachSide: 6,
  scope: "nearest",
  zoneColor: "rgba(60, 60, 60, 0.4)",        // Semi-transparent dark gray filling
  zoneBorderColor: "rgba(120, 120, 120, 0.8)", // Lighter gray for the border
  lookbackBars: 1000,
};

export interface RajaZone {
  bottom: number;
  top: number;
  from_time: any;
  to_time: any;
  last_touch_time: any;
  touches: number;
  score: number;
  level: number;
  avg_wick_excess: number;
  trade_score?: number;
  type: "resistance" | "support";
}

export interface RajaSRData {
  time: Time;
  open: number;
  high: number;
  low: number;
  close: number;
}