import { CustomSeriesOptions, customSeriesDefaultOptions, Time } from "lightweight-charts";

export interface MSBZZOptions extends CustomSeriesOptions {
  pivotPeriod: number;
  
  // ZigZag Lines
  showZigZag: boolean;
  zigZagStyle: number; // 0=solid, 1=dotted, 2=dashed
  zigZagColor: string;
  zigZagWidth: number;
  
  // Labels
  showLabel: boolean;
  labelColor: string;
  
  // Major Bullish BoS
  showMajorBuBoS: boolean;
  majorBuBoSStyle: number;
  majorBuBoSColor: string;
  
  // Major Bearish BoS
  showMajorBeBoS: boolean;
  majorBeBoSStyle: number;
  majorBeBoSColor: string;
  
  // Minor Bullish BoS
  showMinorBuBoS: boolean;
  minorBuBoSStyle: number;
  minorBuBoSColor: string;
  
  // Minor Bearish BoS
  showMinorBeBoS: boolean;
  minorBeBoSStyle: number;
  minorBeBoSColor: string;
  
  // Major Bullish ChoCh
  showMajorBuChoCh: boolean;
  majorBuChoChStyle: number;
  majorBuChoChColor: string;
  
  // Major Bearish ChoCh
  showMajorBeChoCh: boolean;
  majorBeChoChStyle: number;
  majorBeChoChColor: string;
  
  // Minor Bullish ChoCh
  showMinorBuChoCh: boolean;
  minorBuChoChStyle: number;
  minorBuChoChColor: string;
  
  // Minor Bearish ChoCh
  showMinorBeChoCh: boolean;
  minorBeChoChStyle: number;
  minorBeChoChColor: string;
}

export const defaultMSBZZOptions: MSBZZOptions = {
  ...customSeriesDefaultOptions,
  visible: false,
  pivotPeriod: 5,
  
  showZigZag: true,
  zigZagStyle: 0,
  zigZagColor: "#2484bb",
  zigZagWidth: 1,
  
  showLabel: false,
  labelColor: "#0a378a",
  
  showMajorBuBoS: true,
  majorBuBoSStyle: 0,
  majorBuBoSColor: "rgb(11, 95, 204)",
  
  showMajorBeBoS: true,
  majorBeBoSStyle: 0,
  majorBeBoSColor: "rgb(192, 123, 5)",
  
  showMinorBuBoS: false,
  minorBuBoSStyle: 2,
  minorBuBoSColor: "rgb(0, 0, 0)",
  
  showMinorBeBoS: false,
  minorBeBoSStyle: 2,
  minorBeBoSColor: "rgb(0, 0, 0)",
  
  showMajorBuChoCh: true,
  majorBuChoChStyle: 0,
  majorBuChoChColor: "rgb(5, 119, 24)",
  
  showMajorBeChoCh: true,
  majorBeChoChStyle: 0,
  majorBeChoChColor: "rgb(134, 23, 58)",
  
  showMinorBuChoCh: false,
  minorBuChoChStyle: 2,
  minorBuChoChColor: "rgb(0, 0, 0)",
  
  showMinorBeChoCh: false,
  minorBeChoChStyle: 2,
  minorBeChoChColor: "rgb(0, 0, 0)",
};

export interface MSBZZData {
  time: Time;
  open: number;
  high: number;
  low: number;
  close: number;
  timestamp: number; // useful for index tracking
}

export interface ZigZagPoint {
  time: Time;
  value: number;
  type: string;
  index: number;
  advancedType?: string; // e.g. MHH, mHH, etc.
}

export interface StructLine {
  type: "MajorBoSBull" | "MajorBoSBear" | "MinorBoSBull" | "MinorBoSBear" | "MajorChoChBull" | "MajorChoChBear" | "MinorChoChBull" | "MinorChoChBear";
  text: string;
  startIndex: number;
  endIndex: number;
  startTime: Time;
  endTime: Time;
  level: number;
}

export interface ComputedMSBZZ {
  zigzags: ZigZagPoint[];
  lines: StructLine[];
}
