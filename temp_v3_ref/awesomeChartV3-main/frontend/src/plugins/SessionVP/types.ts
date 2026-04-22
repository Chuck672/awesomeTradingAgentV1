import { CustomSeriesOptions, customSeriesDefaultOptions, CustomData, Time } from 'lightweight-charts';

export interface SessionVPData extends CustomData<Time> {
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface SessionVPOptions extends CustomSeriesOptions {
  daysToCalculate: number;
  maxWidthPercent: number; // e.g. 60 for 60% of session width
  bins: number;
  valueAreaPct: number;
  colorPart1: string;
  colorPart2: string;
  colorPart3: string;
  pocColor: string;
}

export const defaultSessionVPOptions: SessionVPOptions = {
  ...customSeriesDefaultOptions,
  daysToCalculate: 5,
  maxWidthPercent: 65,
  bins: 70,
  valueAreaPct: 70,
  colorPart1: '#778899', // LightSlateGray
  colorPart2: '#CD5C5C', // IndianRed
  colorPart3: '#3CB371', // MediumSeaGreen
  pocColor: '#FFD700',   // Yellow
};

export interface SessionProfileBin {
  yStart: number;
  yEnd: number;
  vol1: number; // Volume in 1st third of session
  vol2: number; // Volume in 2nd third of session
  vol3: number; // Volume in 3rd third of session
  totalVolume: number;
  inValueArea: boolean;
}

export interface SessionBlock {
  id: string;
  type: string;
  firstBarTime: number; // Start X coordinate
  lastBarTime: number;  // End X coordinate
  minPrice: number;
  maxPrice: number;
  bins: SessionProfileBin[];
  pocPrice: number;
  pocVolume: number;
  maxVolume: number;
  valueAreaLow: number;
  valueAreaHigh: number;
}
