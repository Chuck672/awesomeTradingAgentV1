import { IChartApi, ISeriesApi, Logical, Time } from 'lightweight-charts';
import { DataPoint, PixelPoint } from './types';

function toUnixSeconds(t: Time): number {
  return typeof t === 'number' ? t : new Date(t as string).getTime() / 1000;
}

export const CoordinateUtils = {
  // Extrapolate time from logical if it's in the future
  logicalToTime(logical: Logical, chart: IChartApi, series: ISeriesApi<any>): Time | null {
    const data = series.data();
    if (!data || data.length === 0) return null;
    const idx = logical as number;

    const getTime = (i: number) => {
      return toUnixSeconds(data[i].time as Time);
    };

    if (idx <= 0) {
      if (data.length >= 2) {
        const interval = getTime(1) - getTime(0);
        return (getTime(0) + idx * interval) as Time;
      }
      return getTime(0) as Time;
    }

    if (idx >= data.length - 1) {
      if (data.length >= 2) {
        const interval = getTime(data.length - 1) - getTime(data.length - 2);
        return (getTime(data.length - 1) + (idx - (data.length - 1)) * interval) as Time;
      }
      return getTime(data.length - 1) as Time;
    }

    const lower = Math.floor(idx);
    const upper = Math.ceil(idx);
    if (lower === upper) return getTime(lower) as Time;

    const t1 = getTime(lower);
    const t2 = getTime(upper);
    return (t1 + (t2 - t1) * (idx - lower)) as Time;
  },

  // Extrapolate logical from time if it's in the future
  timeToLogical(time: Time, chart: IChartApi, series: ISeriesApi<any>): Logical | null {
    const targetTime = toUnixSeconds(time);
    const data = series.data();
    if (!data || data.length === 0) return null;

    const getTime = (i: number) => {
      return toUnixSeconds(data[i].time as Time);
    };

    const firstTime = getTime(0);
    const lastTime = getTime(data.length - 1);

    if (targetTime <= firstTime) {
      if (data.length >= 2) {
        const interval = getTime(1) - firstTime;
        if (interval > 0) return ((targetTime - firstTime) / interval) as Logical;
      }
      return 0 as Logical;
    }

    if (targetTime >= lastTime) {
      if (data.length >= 2) {
        const interval = lastTime - getTime(data.length - 2);
        if (interval > 0) return (data.length - 1 + (targetTime - lastTime) / interval) as Logical;
      }
      return (data.length - 1) as Logical;
    }

    let left = 0;
    let right = data.length - 1;
    while (left <= right) {
      const mid = Math.floor((left + right) / 2);
      const midTime = getTime(mid);
      if (midTime === targetTime) return mid as Logical;
      if (midTime < targetTime) left = mid + 1;
      else right = mid - 1;
    }
    
    const t1 = getTime(right);
    const t2 = getTime(left);
    if (t2 > t1) {
      const ratio = (targetTime - t1) / (t2 - t1);
      return (right + ratio) as Logical;
    }
    return right as Logical;
  },

  dataPointToPixel(point: DataPoint, chart: IChartApi, series: ISeriesApi<any>): PixelPoint | null {
    const timeScale = chart.timeScale();
    const t = (point.timeMapped ?? point.time) as Time;

    /**
     * 重要：跨周期稳定性
     * - 优先使用 timeMapped/time->coordinate（如果该 time 在当前时间轴可解析）
     * - 如果 time 不可解析（例如 future、或 time 不在当前周期 bar 上），再回退到 logical（支持 future extrapolation）
     */
    let x: number | null = null;
    if (t !== null && t !== undefined) {
      try {
        x = timeScale.timeToCoordinate(t);
      } catch {
        x = null;
      }
    }
    if (x === null) {
      // 如果没显式 logical，则尝试从 time 推导一个 logical（支持 time 落在 bar 之间）
      if ((point.logical === undefined || point.logical === null) && t !== null && t !== undefined) {
        const lg = this.timeToLogical(t, chart, series);
        if (lg !== null) {
          point.logical = lg as Logical;
        }
      }
      if (point.logical !== undefined && point.logical !== null) {
        x = timeScale.logicalToCoordinate(point.logical as Logical);
      }
    }

    if (x === null) return null;
    
    const y = series.priceToCoordinate(point.price);
    if (y === null) return null;
    
    return { x, y };
  },

  pixelToDataPoint(pixel: PixelPoint, chart: IChartApi, series: ISeriesApi<any>): DataPoint | null {
    const timeScale = chart.timeScale();
    const logical = timeScale.coordinateToLogical(pixel.x);
    if (logical === null) return null;

    // 优先取 timeScale 的离散 time（对齐到 bar）；若为空则用 extrapolated time（支持 future）
    const directTime = timeScale.coordinateToTime(pixel.x);
    const time = directTime ?? this.logicalToTime(logical, chart, series);
    const price = series.coordinateToPrice(pixel.y);
    if (price === null) return null;
    
    return {
      price,
      time: time as Time,
      timeMapped: time as Time,
      logical: logical as Logical,
    };
  }
};
