import { ComputedTrendExhaustion, TEBox, TEShape, TrendExhaustionData, TrendExhaustionOptions } from "./types";

export class Calculator {
  static computeTE(data: TrendExhaustionData[], options: TrendExhaustionOptions): ComputedTrendExhaustion {
    const { shortLength, shortSmoothingLength, longLength, longSmoothingLength, threshold } = options;
    
    if (data.length === 0) return { boxes: [], shapes: [] };

    // Helper functions
    const getHighest = (index: number, length: number): number => {
      let max = -Infinity;
      const start = Math.max(0, index - length + 1);
      for (let i = start; i <= index; i++) {
        const val = Number(data[i].high);
        if (val > max) max = val;
      }
      return max;
    };

    const getLowest = (index: number, length: number): number => {
      let min = Infinity;
      const start = Math.max(0, index - length + 1);
      for (let i = start; i <= index; i++) {
        const val = Number(data[i].low);
        if (val < min) min = val;
      }
      return min;
    };

    const s_percentRRaw = new Array(data.length).fill(NaN);
    const l_percentRRaw = new Array(data.length).fill(NaN);

    for (let i = 0; i < data.length; i++) {
      const src = Number(data[i].close);
      
      const s_max = getHighest(i, shortLength);
      const s_min = getLowest(i, shortLength);
      if (s_max !== s_min) {
        s_percentRRaw[i] = 100 * (src - s_max) / (s_max - s_min);
      }

      const l_max = getHighest(i, longLength);
      const l_min = getLowest(i, longLength);
      if (l_max !== l_min) {
        l_percentRRaw[i] = 100 * (src - l_max) / (l_max - l_min);
      }
    }

    // EMA Smoothing Helper
    const calcEMA = (src: number[], length: number): number[] => {
      if (length <= 1) return src;
      const alpha = 2 / (length + 1);
      const result = new Array(src.length).fill(NaN);
      let ema = NaN;
      for (let i = 0; i < src.length; i++) {
        if (isNaN(src[i])) continue;
        if (isNaN(ema)) {
          ema = src[i];
        } else {
          ema = alpha * src[i] + (1 - alpha) * ema;
        }
        result[i] = ema;
      }
      return result;
    };

    const s_percentR = calcEMA(s_percentRRaw, shortSmoothingLength);
    const l_percentR = calcEMA(l_percentRRaw, longSmoothingLength);

    const boxes: TEBox[] = [];
    const shapes: TEShape[] = [];

    let was_ob = false;
    let was_os = false;

    let activeObBox: TEBox | null = null;
    let activeOsBox: TEBox | null = null;

    for (let i = 0; i < data.length; i++) {
      const s_pr = s_percentR[i];
      const l_pr = l_percentR[i];

      if (isNaN(s_pr) || isNaN(l_pr)) {
        continue;
      }

      const overbought = s_pr >= -threshold && l_pr >= -threshold;
      const oversold = s_pr <= -100 + threshold && l_pr <= -100 + threshold;

      const ob_reversal = !overbought && was_ob;
      const os_reversal = !oversold && was_os;
      const ob_trend_start = overbought && !was_ob;
      const os_trend_start = oversold && !was_os;

      const high = Number(data[i].high);
      const low = Number(data[i].low);

      // Shapes logic
      if (ob_reversal) {
        shapes.push({ index: i, y: high, type: 'triangledown', color: options.colorBear, isTop: true });
      }
      if (os_reversal) {
        shapes.push({ index: i, y: low, type: 'triangleup', color: options.colorBull, isTop: false });
      }
      if (overbought) {
        shapes.push({ index: i, y: high, type: 'square', color: options.colorBear, isTop: true });
      }
      if (oversold) {
        shapes.push({ index: i, y: low, type: 'square', color: options.colorBull, isTop: false });
      }

      // Boxes logic
      // OB Box
      if (ob_trend_start) {
        activeObBox = { startIndex: i - 1 < 0 ? 0 : i - 1, endIndex: i, top: high, bottom: low, isBull: false };
        boxes.push(activeObBox);
      } else if (overbought && activeObBox) {
        activeObBox.endIndex = i;
        if (high > activeObBox.top) activeObBox.top = high;
        if (low < activeObBox.bottom) activeObBox.bottom = low;
      } else if (!overbought && activeObBox) {
        activeObBox.endIndex = i - 1;
        activeObBox = null;
      }

      // OS Box
      if (os_trend_start) {
        activeOsBox = { startIndex: i - 1 < 0 ? 0 : i - 1, endIndex: i, top: high, bottom: low, isBull: true };
        boxes.push(activeOsBox);
      } else if (oversold && activeOsBox) {
        activeOsBox.endIndex = i;
        if (high > activeOsBox.top) activeOsBox.top = high;
        if (low < activeOsBox.bottom) activeOsBox.bottom = low;
      } else if (!oversold && activeOsBox) {
        activeOsBox.endIndex = i - 1;
        activeOsBox = null;
      }

      was_ob = overbought;
      was_os = oversold;
    }

    return { boxes, shapes };
  }
}
