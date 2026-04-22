export class EMA {
  private period: number;
  private alpha: number;
  private value: number | null = null;
  private count: number = 0;
  private sum: number = 0;

  constructor(period: number) {
    this.period = period;
    this.alpha = 2 / (period + 1);
  }

  next(price: number): number | null {
    if (this.value === null) {
      this.sum += price;
      this.count++;
      if (this.count === this.period) {
        this.value = this.sum / this.period; // Initial SMA
        return this.value;
      }
      return null;
    } else {
      this.value = (price - this.value) * this.alpha + this.value;
      return this.value;
    }
  }
}

export class RMA {
  private period: number;
  private alpha: number;
  private value: number | null = null;
  private sum: number = 0;
  private count: number = 0;

  constructor(period: number) {
    this.period = period;
    this.alpha = 1 / period;
  }

  next(val: number): number | null {
    if (this.value === null) {
      this.sum += val;
      this.count++;
      if (this.count === this.period) {
        this.value = this.sum / this.period; // Initial SMA
        return this.value;
      }
      return null;
    } else {
      this.value = (val - this.value) * this.alpha + this.value;
      return this.value;
    }
  }
}

export class SMA {
  private period: number;
  private values: number[] = [];
  private sum: number = 0;

  constructor(period: number) {
    this.period = period;
  }

  next(value: number): number | null {
    this.values.push(value);
    this.sum += value;
    if (this.values.length > this.period) {
      this.sum -= this.values.shift()!;
    }
    if (this.values.length === this.period) {
      return this.sum / this.period;
    }
    return null;
  }
}

export class RSI {
  private rmaGain: RMA;
  private rmaLoss: RMA;
  private lastClose: number | null = null;

  constructor(period: number = 14) {
    this.rmaGain = new RMA(period);
    this.rmaLoss = new RMA(period);
  }

  next(close: number): number | null {
    if (this.lastClose === null) {
      this.lastClose = close;
      return null;
    }
    const change = close - this.lastClose;
    this.lastClose = close;

    const gain = change > 0 ? change : 0;
    const loss = change < 0 ? -change : 0;

    const avgGain = this.rmaGain.next(gain);
    const avgLoss = this.rmaLoss.next(loss);

    if (avgGain === null || avgLoss === null) return null;

    if (avgLoss === 0) {
      return avgGain === 0 ? 50 : 100;
    }
    const rs = avgGain / avgLoss;
    return 100 - (100 / (1 + rs));
  }
}

export class MACD {
  private fastEMA: EMA;
  private slowEMA: EMA;
  private signalEMA: EMA;

  constructor(fastPeriod: number = 12, slowPeriod: number = 26, signalPeriod: number = 9) {
    this.fastEMA = new EMA(fastPeriod);
    this.slowEMA = new EMA(slowPeriod);
    this.signalEMA = new EMA(signalPeriod);
  }

  next(close: number): { macd: number | null; signal: number | null; histogram: number | null } {
    const fast = this.fastEMA.next(close);
    const slow = this.slowEMA.next(close);
    
    if (fast === null || slow === null) return { macd: null, signal: null, histogram: null };
    
    const macdLine = fast - slow;
    const signalLine = this.signalEMA.next(macdLine);
    
    if (signalLine === null) return { macd: macdLine, signal: null, histogram: null };
    
    return {
      macd: macdLine,
      signal: signalLine,
      histogram: macdLine - signalLine
    };
  }
}

export class BollingerBands {
  private period: number;
  private stdDevMultiplier: number;
  private history: number[] = [];
  private sum: number = 0;

  constructor(period: number = 20, stdDevMultiplier: number = 2) {
    this.period = period;
    this.stdDevMultiplier = stdDevMultiplier;
  }

  next(close: number): { upper: number | null; middle: number | null; lower: number | null } {
    this.history.push(close);
    this.sum += close;
    
    if (this.history.length > this.period) {
      const removed = this.history.shift()!;
      this.sum -= removed;
    }

    if (this.history.length < this.period) {
      return { upper: null, middle: null, lower: null };
    }

    const sma = this.sum / this.period;
    let varianceSum = 0;
    for (const price of this.history) {
      varianceSum += Math.pow(price - sma, 2);
    }
    // Using sample standard deviation (N) for simple standard deviation like tradingview
    const stdDev = Math.sqrt(varianceSum / this.period);

    return {
      middle: sma,
      upper: sma + stdDev * this.stdDevMultiplier,
      lower: sma - stdDev * this.stdDevMultiplier
    };
  }
}

export class ATR {
  private rma: RMA;
  private lastClose: number | null = null;

  constructor(period: number = 14) {
    this.rma = new RMA(period);
  }

  next(high: number, low: number, close: number): number | null {
    let tr = high - low;
    if (this.lastClose !== null) {
      tr = Math.max(
        high - low,
        Math.abs(high - this.lastClose),
        Math.abs(low - this.lastClose)
      );
    }
    this.lastClose = close;
    return this.rma.next(tr);
  }
}

export class VWAP {
  private sumPriceVolume: number = 0;
  private sumVolume: number = 0;
  private lastDate: string | null = null;

  next(high: number, low: number, close: number, volume: number, timestamp: number): number | null {
    // Determine if it's a new day
    const date = new Date(timestamp * 1000).toISOString().split('T')[0];
    
    if (this.lastDate !== date) {
      // Reset for new day
      this.sumPriceVolume = 0;
      this.sumVolume = 0;
      this.lastDate = date;
    }

    const typicalPrice = (high + low + close) / 3;
    this.sumPriceVolume += typicalPrice * volume;
    this.sumVolume += volume;

    if (this.sumVolume === 0) return null;
    return this.sumPriceVolume / this.sumVolume;
  }
}

export function calculateZigzag(data: any[], pivotPeriod: number = 5): any[] {
  if (data.length < pivotPeriod * 2 + 1) return [];

  const points: { time: number; value: number; type: string; index: number }[] = [];

  // Helper to find pivot high
  const getPivotHigh = (index: number, period: number) => {
    if (index < period || index >= data.length - period) return null;
    const currentHigh = Number(data[index].high);
    for (let i = 1; i <= period; i++) {
      if (Number(data[index - i].high) > currentHigh) return null;
      if (Number(data[index + i].high) > currentHigh) return null;
    }
    return currentHigh;
  };

  // Helper to find pivot low
  const getPivotLow = (index: number, period: number) => {
    if (index < period || index >= data.length - period) return null;
    const currentLow = Number(data[index].low);
    for (let i = 1; i <= period; i++) {
      if (Number(data[index - i].low) < currentLow) return null;
      if (Number(data[index + i].low) < currentLow) return null;
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
            const type = points.length >= 2 ? (points[points.length - 2].value < lowPivot! ? 'HL' : 'LL') : 'L'; // Using fallback logic
            // Note: Pine script relies on `LowValue` state here, simplifying for basic ZZ
            points.push({ time: barTime, value: lowPivot || Number(data[i].low), type, index: i });
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
            const type = points.length >= 2 ? (points[points.length - 2].value < highPivot! ? 'HH' : 'LH') : 'H';
            points.push({ time: barTime, value: highPivot || Number(data[i].high), type, index: i });
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

  // Connect to the latest bar
  const lastBar = data[data.length - 1];
  if (points.length > 0) {
    const lastPoint = points[points.length - 1];
    if (lastPoint.type.endsWith('H')) {
      points.push({ time: lastBar.time, value: Number(lastBar.close), type: 'L', index: data.length - 1 });
    } else {
      points.push({ time: lastBar.time, value: Number(lastBar.close), type: 'H', index: data.length - 1 });
    }
  }

  const getTimeVal = (t: any) => {
    if (typeof t === "number") return t;
    if (typeof t === "string") return Date.parse(t);
    if (t && typeof t === "object") return new Date(t.year, t.month - 1, t.day).getTime();
    return 0;
  };

  // MUST strictly sort and deduplicate by time to avoid Lightweight Charts crash
  points.sort((a, b) => getTimeVal(a.time) - getTimeVal(b.time));
  const uniquePoints: any[] = [];
  for (const p of points) {
    const prevTime = uniquePoints.length > 0 ? getTimeVal(uniquePoints[uniquePoints.length - 1].time) : 0;
    const currTime = getTimeVal(p.time);
    if (uniquePoints.length === 0 || prevTime < currTime) {
      uniquePoints.push({ ...p });
    } else if (prevTime === currTime) {
      uniquePoints[uniquePoints.length - 1].value = p.value;
    }
  }

  return uniquePoints;
}
