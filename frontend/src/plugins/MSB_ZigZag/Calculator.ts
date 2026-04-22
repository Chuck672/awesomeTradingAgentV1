import { MSBZZData, MSBZZOptions, ComputedMSBZZ, ZigZagPoint, StructLine } from "./types";
import { Time } from "lightweight-charts";

export class Calculator {
  static computeMSBZZ(data: MSBZZData[], options: MSBZZOptions): ComputedMSBZZ {
    const { pivotPeriod } = options;
    if (data.length < pivotPeriod * 2 + 1) return { zigzags: [], lines: [] };

    const points: ZigZagPoint[] = [];
    const lines: StructLine[] = [];

    // 1. Calculate basic Pivot Highs and Lows
    const getPivotHigh = (index: number, period: number) => {
      if (index < period || index >= data.length - period) return null;
      const currentHigh = data[index].high;
      for (let i = 1; i <= period; i++) {
        if (data[index - i].high > currentHigh) return null;
        if (data[index + i].high > currentHigh) return null;
      }
      return currentHigh;
    };

    const getPivotLow = (index: number, period: number) => {
      if (index < period || index >= data.length - period) return null;
      const currentLow = data[index].low;
      for (let i = 1; i <= period; i++) {
        if (data[index - i].low < currentLow) return null;
        if (data[index + i].low < currentLow) return null;
      }
      return currentLow;
    };

    for (let i = pivotPeriod; i < data.length - pivotPeriod; i++) {
      const highPivot = getPivotHigh(i, pivotPeriod);
      const lowPivot = getPivotLow(i, pivotPeriod);
      const barTime = data[i].time;

      if (highPivot !== null && lowPivot !== null) {
        if (points.length === 0) {
          // Init state
        } else {
          const last = points[points.length - 1];
          if (last.type.endsWith('L')) {
            if (lowPivot < last.value) {
              points.pop();
              const type = points.length >= 2 ? (points[points.length - 2].value < lowPivot ? 'HL' : 'LL') : 'L';
              points.push({ time: barTime, value: lowPivot, type, index: i });
            } else {
              const type = points.length >= 2 ? (points[points.length - 2].value < highPivot ? 'HH' : 'LH') : 'H';
              points.push({ time: barTime, value: highPivot, type, index: i });
            }
          } else if (last.type.endsWith('H')) {
            if (highPivot > last.value) {
              points.pop();
              const type = points.length >= 2 ? (points[points.length - 2].value < highPivot ? 'HH' : 'LH') : 'H';
              points.push({ time: barTime, value: highPivot, type, index: i });
            } else {
              const type = points.length >= 2 ? (points[points.length - 2].value < lowPivot ? 'HL' : 'LL') : 'L';
              points.push({ time: barTime, value: lowPivot, type, index: i });
            }
          }
        }
      } else if (highPivot !== null) {
        if (points.length === 0) {
          points.push({ time: barTime, value: highPivot, type: 'H', index: i });
        } else {
          const last = points[points.length - 1];
          if (last.type.endsWith('L')) {
            if (highPivot > last.value) {
              const type = points.length >= 2 ? (points[points.length - 2].value < highPivot ? 'HH' : 'LH') : 'H';
              points.push({ time: barTime, value: highPivot, type, index: i });
            } else if (highPivot < last.value) {
              points.pop();
              const fallbackLow = lowPivot || data[i].low;
              const type = points.length >= 2 ? (points[points.length - 2].value < fallbackLow ? 'HL' : 'LL') : 'L';
              points.push({ time: barTime, value: fallbackLow, type, index: i });
            }
          } else if (last.type.endsWith('H')) {
            if (last.value < highPivot) {
              points.pop();
              const type = points.length >= 2 ? (points[points.length - 2].value < highPivot ? 'HH' : 'LH') : 'H';
              points.push({ time: barTime, value: highPivot, type, index: i });
            }
          }
        }
      } else if (lowPivot !== null) {
        if (points.length === 0) {
          points.push({ time: barTime, value: lowPivot, type: 'L', index: i });
        } else {
          const last = points[points.length - 1];
          if (last.type.endsWith('H')) {
            if (lowPivot < last.value) {
              const type = points.length >= 2 ? (points[points.length - 2].value < lowPivot ? 'HL' : 'LL') : 'L';
              points.push({ time: barTime, value: lowPivot, type, index: i });
            } else if (lowPivot > last.value) {
              points.pop();
              const fallbackHigh = highPivot || data[i].high;
              const type = points.length >= 2 ? (points[points.length - 2].value < fallbackHigh ? 'HH' : 'LH') : 'H';
              points.push({ time: barTime, value: fallbackHigh, type, index: i });
            }
          } else if (last.type.endsWith('L')) {
            if (last.value > lowPivot) {
              points.pop();
              const type = points.length >= 2 ? (points[points.length - 2].value < lowPivot ? 'HL' : 'LL') : 'L';
              points.push({ time: barTime, value: lowPivot, type, index: i });
            }
          }
        }
      }
    }

    // Connect to the latest bar to keep the line active
    const lastBar = data[data.length - 1];
    if (points.length > 0) {
      const lastPoint = points[points.length - 1];
      if (lastPoint.type.endsWith('H')) {
        points.push({ time: lastBar.time, value: lastBar.close, type: 'L', index: data.length - 1 });
      } else {
        points.push({ time: lastBar.time, value: lastBar.close, type: 'H', index: data.length - 1 });
      }
    }

    // Sort to prevent chart crash
    const getTimeVal = (t: any) => {
      if (typeof t === "number") return t;
      if (typeof t === "string") return Date.parse(t);
      if (t && typeof t === "object") return new Date(t.year, t.month - 1, t.day).getTime();
      return 0;
    };
    points.sort((a, b) => getTimeVal(a.time) - getTimeVal(b.time));
    
    const uniquePoints: ZigZagPoint[] = [];
    for (const p of points) {
      const prevTime = uniquePoints.length > 0 ? getTimeVal(uniquePoints[uniquePoints.length - 1].time) : 0;
      const currTime = getTimeVal(p.time);
      if (uniquePoints.length === 0 || prevTime < currTime) {
        uniquePoints.push({ ...p });
      } else if (prevTime === currTime) {
        uniquePoints[uniquePoints.length - 1].value = p.value;
      }
    }

    // 2. Identify Major and Minor Structure Breaks (BoS & ChoCh)
    // A simplified but effective algorithm simulating the PineScript intent:
    let externalTrend: "Up Trend" | "Down Trend" | "No Trend" = "No Trend";
    let majorHighLevel: number | null = null;
    let majorHighIndex: number | null = null;
    let majorHighTime: Time | null = null;

    let majorLowLevel: number | null = null;
    let majorLowIndex: number | null = null;
    let majorLowTime: Time | null = null;

    let lockBreakM = -1;

    for (let i = 0; i < uniquePoints.length; i++) {
      const pt = uniquePoints[i];
      if (pt.type.endsWith('H')) {
        majorHighLevel = pt.value;
        majorHighIndex = pt.index;
        majorHighTime = pt.time;
      } else if (pt.type.endsWith('L')) {
        majorLowLevel = pt.value;
        majorLowIndex = pt.index;
        majorLowTime = pt.time;
      }

      // From this point to the next point, check if any close breaks the level
      const nextIndex = i < uniquePoints.length - 1 ? uniquePoints[i+1].index : data.length - 1;
      for (let j = pt.index; j <= nextIndex; j++) {
        const bar = data[j];
        
        // Bullish Break
        if (majorHighLevel !== null && bar.close > majorHighLevel && lockBreakM !== majorHighIndex) {
          if (externalTrend === "No Trend" || externalTrend === "Up Trend") {
            // BoS Bull
            lines.push({
              type: "MajorBoSBull",
              text: "MSB_Bull",
              startIndex: majorHighIndex!,
              startTime: majorHighTime!,
              endIndex: j,
              endTime: bar.time,
              level: majorHighLevel
            });
          } else if (externalTrend === "Down Trend") {
            // ChoCh Bull
            lines.push({
              type: "MajorChoChBull",
              text: "Shift",
              startIndex: majorHighIndex!,
              startTime: majorHighTime!,
              endIndex: j,
              endTime: bar.time,
              level: majorHighLevel
            });
          }
          externalTrend = "Up Trend";
          lockBreakM = majorHighIndex!;
        }

        // Bearish Break
        if (majorLowLevel !== null && bar.close < majorLowLevel && lockBreakM !== majorLowIndex) {
          if (externalTrend === "No Trend" || externalTrend === "Down Trend") {
            // BoS Bear
            lines.push({
              type: "MajorBoSBear",
              text: "MSB_Bear",
              startIndex: majorLowIndex!,
              startTime: majorLowTime!,
              endIndex: j,
              endTime: bar.time,
              level: majorLowLevel
            });
          } else if (externalTrend === "Up Trend") {
            // ChoCh Bear
            lines.push({
              type: "MajorChoChBear",
              text: "Shift",
              startIndex: majorLowIndex!,
              startTime: majorLowTime!,
              endIndex: j,
              endTime: bar.time,
              level: majorLowLevel
            });
          }
          externalTrend = "Down Trend";
          lockBreakM = majorLowIndex!;
        }
      }
    }

    return {
      zigzags: uniquePoints,
      lines: lines
    };
  }
}