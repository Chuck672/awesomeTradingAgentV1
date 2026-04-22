import { RajaSRData, RajaSROptions, RajaZone } from "./types";

interface SwingPoint {
  time: any;
  level: number;
  wick: number;
}

export class Calculator {
  private static median(xs: number[]): number {
    const ys = xs.filter((x) => !isNaN(x));
    if (ys.length === 0) return 0.0;
    ys.sort((a, b) => a - b);
    const mid = Math.floor(ys.length / 2);
    if (ys.length % 2 === 1) return ys[mid];
    return 0.5 * (ys[mid - 1] + ys[mid]);
  }

  private static calcTol(bars: RajaSRData[], options: RajaSROptions): number {
    if (options.tolAbs && options.tolAbs > 0) return options.tolAbs;
    const trs: number[] = [];
    const recent = bars.slice(-200);
    for (const b of recent) {
      if (b.high > 0 && b.low > 0 && b.high > b.low) {
        trs.push(b.high - b.low);
      }
    }
    const med = this.median(trs);
    const tol = med * options.tolTrMult;
    return Math.max(tol, 1e-6);
  }

  private static calcMargin(bars: RajaSRData[], options: RajaSROptions): number {
    if (options.marginAbs && options.marginAbs > 0) return options.marginAbs;
    const trs: number[] = [];
    const recent = bars.slice(-200);
    for (const b of recent) {
      if (b.high > 0 && b.low > 0 && b.high > b.low) {
        trs.push(b.high - b.low);
      }
    }
    const med = this.median(trs);
    const m = med * options.marginTrMult;
    return Math.max(m, 1e-6);
  }

  private static collectRejectionPoints(bars: RajaSRData[]): { highs: SwingPoint[]; lows: SwingPoint[] } {
    if (bars.length === 0) return { highs: [], lows: [] };

    const trs: number[] = [];
    for (const b of bars) {
      if (b.high > 0 && b.low > 0 && b.high > b.low) {
        trs.push(b.high - b.low);
      }
    }
    const trMed = Math.max(this.median(trs), 1e-6);
    // 原来是 0.02 (2%)，导致几乎所有K线都被算作触点。改为 0.25 (25%)，确保只有真正的长影线拒绝才被收集。
    const wickMin = trMed * 0.25;

    const highs: SwingPoint[] = [];
    const lows: SwingPoint[] = [];

    for (const b of bars) {
      if (b.high <= 0 || b.low <= 0) continue;
      const bodyHigh = Math.max(b.open, b.close);
      const bodyLow = Math.min(b.open, b.close);
      const upExcess = b.high - bodyHigh;
      const dnExcess = bodyLow - b.low;

      if (upExcess >= wickMin) {
        highs.push({ time: b.time, level: bodyHigh, wick: b.high });
      }
      if (dnExcess >= wickMin) {
        lows.push({ time: b.time, level: bodyLow, wick: b.low });
      }
    }
    return { highs, lows };
  }

  private static findSwings(bars: RajaSRData[], pivot: number): { highs: SwingPoint[]; lows: SwingPoint[] } {
    const n = bars.length;
    if (n < pivot * 2 + 3) return { highs: [], lows: [] };

    const highs: SwingPoint[] = [];
    const lows: SwingPoint[] = [];

    for (let i = pivot; i < n - pivot; i++) {
      const b = bars[i];
      if (b.high <= 0 || b.low <= 0) continue;

      let leftHigh = -Infinity;
      let leftLow = Infinity;
      for (let j = i - pivot; j < i; j++) {
        leftHigh = Math.max(leftHigh, bars[j].high);
        leftLow = Math.min(leftLow, bars[j].low);
      }

      let rightHigh = -Infinity;
      let rightLow = Infinity;
      for (let j = i + 1; j <= i + pivot; j++) {
        rightHigh = Math.max(rightHigh, bars[j].high);
        rightLow = Math.min(rightLow, bars[j].low);
      }

      if (b.high > leftHigh && b.high > rightHigh) {
        const bodyHigh = Math.max(b.open, b.close);
        highs.push({ time: b.time, level: bodyHigh, wick: b.high });
      }

      if (b.low < leftLow && b.low < rightLow) {
        const bodyLow = Math.min(b.open, b.close);
        lows.push({ time: b.time, level: bodyLow, wick: b.low });
      }
    }

    return { highs, lows };
  }

  private static clusterByLevel(points: SwingPoint[], tol: number): SwingPoint[][] {
    if (points.length === 0) return [];
    const pts = [...points].sort((a, b) => a.level - b.level);
    const clusters: SwingPoint[][] = [];

    let cur: SwingPoint[] = [pts[0]];
    let curCenter = pts[0].level;

    for (let i = 1; i < pts.length; i++) {
      const p = pts[i];
      if (Math.abs(p.level - curCenter) <= tol) {
        cur.push(p);
        curCenter = cur.reduce((sum, x) => sum + x.level, 0) / cur.length;
      } else {
        clusters.push(cur);
        cur = [p];
        curCenter = p.level;
      }
    }
    clusters.push(cur);
    return clusters;
  }

  public static computeRajaZones(fullData: RajaSRData[], options: RajaSROptions): RajaZone[] {
    // Only use the last lookbackBars to calculate to avoid performance issues and far-history zones
    const bars = fullData.slice(-options.lookbackBars);
    if (bars.length < 50) return [];

    const tol = this.calcTol(bars, options);
    const margin = this.calcMargin(bars, options);

    let { highs: swingHighs, lows: swingLows } = this.collectRejectionPoints(bars);
    if (swingHighs.length + swingLows.length < 6) {
      const swings = this.findSwings(bars, options.pivot);
      swingHighs = swings.highs;
      swingLows = swings.lows;
    }

    const resClusters = this.clusterByLevel(swingHighs, tol);
    const supClusters = this.clusterByLevel(swingLows, tol);

    const lastT = bars[bars.length - 1].time;
    const lastClose = bars[bars.length - 1].close;

    const recentTrs: number[] = [];
    for (const b of bars.slice(-200)) {
      if (b.high && b.low) recentTrs.push(b.high - b.low);
    }
    const trMed = Math.max(this.median(recentTrs), 1e-6);

    const diffs: number[] = [];
    const recentBars = bars.slice(-80);
    for (let i = 0; i < recentBars.length - 1; i++) {
      const d = (recentBars[i + 1].time as any) - (recentBars[i].time as any);
      if (d > 0) diffs.push(d);
    }
    const barSec = Math.max(diffs.length > 0 ? Math.floor(this.median(diffs)) : 60, 1);
    const lookbackN = bars.length;

    const zoneQualityMetrics = (bottom: number, top: number) => {
      let wickTouch = 0;
      let bodyOverlap = 0;
      let closeInside = 0;
      for (const b of bars) {
        if (b.high >= bottom && b.low <= top) wickTouch++;
        const bodyLow = Math.min(b.open, b.close);
        const bodyHigh = Math.max(b.open, b.close);
        if (bodyHigh >= bottom && bodyLow <= top) bodyOverlap++;
        if (bottom <= b.close && b.close <= top) closeInside++;
      }
      return { wickTouch, bodyOverlap, closeInside };
    };

    const zoneFromCluster = (cluster: SwingPoint[], side: "resistance" | "support"): RajaZone | null => {
      if (cluster.length < options.minTouches) return null;
      const levels = cluster.map((p) => p.level);
      const wicks = cluster.map((p) => p.wick);
      const times = cluster.map((p) => p.time);

      const base = this.median(levels);
      const lastTouchTime = Math.max(...times);

      let top = 0, bottom = 0;
      let wickExcess: number[] = [];

      if (side === "resistance") {
        bottom = base;
        top = base + margin;
        wickExcess = wicks.map((w) => Math.max(0.0, w - base));
      } else {
        top = base;
        bottom = base - margin;
        wickExcess = wicks.map((w) => Math.max(0.0, base - w));
      }

      const avgExcess = wickExcess.length ? wickExcess.reduce((a, b) => a + b, 0) / wickExcess.length : 0.0;
      let score = cluster.length * (margin > 0 ? avgExcess / margin : 1.0);

      const dist = Math.abs(base - lastClose);
      score = score / (1.0 + dist / (trMed * 10.0));

      return {
        bottom,
        top,
        from_time: Math.min(...times),
        to_time: lastT,
        last_touch_time: lastTouchTime,
        touches: cluster.length,
        score,
        level: base,
        avg_wick_excess: avgExcess,
        type: side,
      };
    };

    let resistance = resClusters.map((cl) => zoneFromCluster(cl, "resistance")).filter(Boolean) as RajaZone[];
    let support = supClusters.map((cl) => zoneFromCluster(cl, "support")).filter(Boolean) as RajaZone[];

    const mergeZones = (zs: RajaZone[]): RajaZone[] => {
      if (zs.length === 0) return [];
      
      // 1. Sort by score descending to prioritize stronger zones
      const sortedByScore = [...zs].sort((a, b) => b.score - a.score);
      const deduplicated: RajaZone[] = [];
      
      // 间距阈值：如果两个基准线(level)的距离小于 1.8 倍 ATR 容差，
      // 或者它们的边界有重叠，我们就认为它们是“同一个”或者“离得太近”。
      const minDistance = tol * 1.8;

      for (const current of sortedByScore) {
        let isTooClose = false;
        
        for (const existing of deduplicated) {
          // 判断是否有重叠
          const isOverlapping = (current.top >= existing.bottom) && (current.bottom <= existing.top);
          // 判断基准线(level)距离是否过近
          const isLevelClose = Math.abs(current.level - existing.level) < minDistance;

          if (isOverlapping || isLevelClose) {
            // 如果与已保留的高分 zone 冲突，直接抛弃当前这个弱的 zone，不做任何合并/变宽处理
            isTooClose = true;
            break;
          }
        }
        
        if (!isTooClose) {
          deduplicated.push({ ...current });
        }
      }
      
      // 最后按照价格排序，方便后续按价格区间截取 (如 Nearest 模式)
      return deduplicated.sort((a, b) => a.bottom - b.bottom);
    };

    // 先合并所有阻力支撑候选区，执行全局严格去重（跨阻力和支撑）
    let allCandidates = [...resistance, ...support];
    allCandidates = mergeZones(allCandidates);
    
    // 重新分类，虽然颜色统一了，但为了兼容保留了 type
    resistance = allCandidates.filter(z => z.type === 'resistance');
    support = allCandidates.filter(z => z.type === 'support');

    if (options.scope === "nearest") {
      const pickNearest = (zs: RajaZone[], above: boolean) => {
        let cand = zs;
        if (above) {
          cand = zs.filter((z) => z.bottom >= lastClose - tol);
          cand.sort((a, b) => {
            const distDiff = Math.abs(a.bottom - lastClose) - Math.abs(b.bottom - lastClose);
            return distDiff !== 0 ? distDiff : b.score - a.score;
          });
        } else {
          cand = zs.filter((z) => z.top <= lastClose + tol);
          cand.sort((a, b) => {
            const distDiff = Math.abs(lastClose - a.top) - Math.abs(lastClose - b.top);
            return distDiff !== 0 ? distDiff : b.score - a.score;
          });
        }
        return cand.slice(0, options.maxZonesEachSide);
      };
      resistance = pickNearest(resistance, true);
      support = pickNearest(support, false);
    } else if (options.scope === "all") {
      // 按照得分(score)降序，选取最强的 N 个 zones，然后再按价格排序
      // 避免原先按 bottom 升序切片导致只保留了历史最低价的区域（图表当前不可见）
      resistance.sort((a, b) => b.score - a.score);
      support.sort((a, b) => b.score - a.score);
      if (options.maxZonesEachSide > 0) {
        resistance = resistance.slice(0, options.maxZonesEachSide);
        support = support.slice(0, options.maxZonesEachSide);
      }
      resistance.sort((a, b) => a.bottom - b.bottom);
      support.sort((a, b) => a.bottom - b.bottom);
    } else if (options.scope === "trade") {
      const maxCloseInsideRatio = 0.22;
      const maxBodyOverlapRatio = 0.35;
      // 原来是 6.0，导致在长周期/缩小图表时，稍远一点的 Zone 直接被剔除。改为 20.0 增加视野范围
      const distMult = 20.0;
      const halfLifeBars = Math.max(20.0, lookbackN * 0.75);
      const minSep = Math.max(tol * 1.2, margin * 1.8);

      const tradeScore = (z: RajaZone, side: "resistance" | "support"): number => {
        const dist = Math.abs(z.level - lastClose);
        if (dist > trMed * distMult) return -1e9;

        const m = zoneQualityMetrics(z.bottom, z.top);
        const closeRatio = m.closeInside / Math.max(1.0, lookbackN);
        const bodyRatio = m.bodyOverlap / Math.max(1.0, lookbackN);

        if (closeRatio > maxCloseInsideRatio) return -1e9;
        if (bodyRatio > maxBodyOverlapRatio) return -1e9;

        let sideMult = 1.0;
        if (side === "resistance" && z.bottom < lastClose - tol) sideMult = 0.65;
        if (side === "support" && z.top > lastClose + tol) sideMult = 0.65;

        const clean = 1.0 / (1.0 + closeRatio * 3.0 + bodyRatio * 1.5);
        const ageBars = Math.max(0.0, ((lastT as any) - (z.last_touch_time as any)) / barSec);
        const recency = Math.exp(-ageBars / halfLifeBars);
        const distance = 1.0 / (1.0 + dist / (trMed * 4.0));

        return z.score * clean * recency * distance * sideMult;
      };

      const pickTrade = (zs: RajaZone[], side: "resistance" | "support") => {
        const scored: RajaZone[] = [];
        for (const z of zs) {
          const s = tradeScore(z, side);
          if (s > -1e8) {
            scored.push({ ...z, trade_score: s });
          }
        }

        const picked: RajaZone[] = [];
        if (scored.length > 0) {
          let preferred = side === "resistance" ? scored.filter(z => z.level >= lastClose) : scored.filter(z => z.level <= lastClose);
          let fallback = side === "resistance" ? scored.filter(z => z.level < lastClose) : scored.filter(z => z.level > lastClose);
          let anchorPool = preferred.length > 0 ? preferred : fallback;
          anchorPool.sort((a, b) => Math.abs(a.level - lastClose) - Math.abs(b.level - lastClose));
          if (anchorPool.length > 0) picked.push(anchorPool[0]);
        }

        scored.sort((a, b) => (b.trade_score || 0) - (a.trade_score || 0));
        for (const z of scored) {
          if (picked.length >= options.maxZonesEachSide) break;
          if (picked.some((p) => Math.abs(z.level - p.level) < minSep)) continue;
          picked.push(z);
        }
        picked.sort((a, b) => a.level - b.level);
        return picked;
      };

      resistance = pickTrade(resistance, "resistance");
      support = pickTrade(support, "support");
    }

    return [...resistance, ...support];
  }
}