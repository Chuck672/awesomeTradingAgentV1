import { CustomData, CustomSeriesOptions, Time } from "lightweight-charts";

export interface TrendExhaustionData extends CustomData<Time> {
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

export interface TrendExhaustionOptions extends CustomSeriesOptions {
  colorBull: string;
  colorBear: string;
  threshold: number;
  shortLength: number;
  shortSmoothingLength: number;
  longLength: number;
  longSmoothingLength: number;
  showBoxes: boolean;
  showShapes: boolean;
}

export const defaultTrendExhaustionOptions: TrendExhaustionOptions = {
  colorBull: '#2466A7',
  colorBear: '#CA0017',
  threshold: 20,
  shortLength: 21,
  shortSmoothingLength: 7,
  longLength: 112,
  longSmoothingLength: 3,
  showBoxes: true,
  showShapes: true,
  color: '#2466A7',
  lastValueVisible: false,
  title: '',
  visible: true,
  priceLineVisible: false,
  priceLineSource: 0,
  priceLineWidth: 1,
  priceLineColor: '#2466A7',
  priceLineStyle: 0,
  baseLineVisible: false,
  baseLineColor: '#2466A7',
  baseLineWidth: 1,
  baseLineStyle: 0,
  priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
};

export interface TEBox {
  startIndex: number;
  endIndex: number;
  top: number;
  bottom: number;
  isBull: boolean;
}

export interface TEShape {
  index: number;
  y: number;
  type: 'triangleup' | 'triangledown' | 'square';
  color: string;
  isTop: boolean;
}

export interface ComputedTrendExhaustion {
  boxes: TEBox[];
  shapes: TEShape[];
}
