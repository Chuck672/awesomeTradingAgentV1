import { SessionVPData, SessionVPOptions, SessionBlock, SessionProfileBin } from './types';

export class Calculator {
  static calculateAll(data: SessionVPData[], options: SessionVPOptions): SessionBlock[] {
    if (data.length === 0) return [];

    // 1. Find the last N days
    const daysToCalc = options.daysToCalculate;
    let uniqueDays = new Set<string>();
    let startIndex = 0;
    
    for (let i = data.length - 1; i >= 0; i--) {
      const d = new Date((data[i].time as number) * 1000);
      const dayStr = `${d.getUTCFullYear()}-${d.getUTCMonth()}-${d.getUTCDate()}`;
      uniqueDays.add(dayStr);
      if (uniqueDays.size > daysToCalc) {
        startIndex = i + 1;
        break;
      }
    }

    const activeData = data.slice(startIndex);
    if (activeData.length === 0) return [];

    // 2. Group into sessions
    // MQL5 Logic:
    // Sydney: 21:00 - 00:00 (ONLY ON MONDAYS! Other days this time belongs to ASIA)
    // Asia:   00:00 - 07:00 (On Tue-Fri, Asia is effectively 21:00(prev day) - 07:00)
    // Europe: 07:00 - 12:00
    // US:     12:00 - 21:00
    const blocks: SessionBlock[] = [];
    let currentBars: SessionVPData[] = [];
    let currentId = '';
    let currentType = '';

    for (const bar of activeData) {
      const d = new Date((bar.time as number) * 1000);
      const h = d.getUTCHours();
      const dayOfWeek = d.getUTCDay(); // 0=Sun, 1=Mon, ..., 6=Sat
      
      let sType = '';
      if (h >= 21 || h < 0) {
        // Between 21:00 and 00:00. 
        // In MQL5, Monday 21:00 starts the trading week (Sydney). 
        // Wait, normally Monday 21:00 GMT is actually Tuesday morning in Sydney.
        // Let's strictly follow your rule: "Sydney VP ONLY ON MONDAY".
        if (dayOfWeek === 1) { // Monday
          sType = 'SYDNEY';
        } else {
          sType = 'ASIA';
        }
      }
      else if (h >= 0 && h < 7) {
        sType = 'ASIA';
      }
      else if (h >= 7 && h < 12) {
        sType = 'EUROPE';
      }
      else if (h >= 12 && h < 21) {
        sType = 'US';
      }

      // Adjust date string for hours >= 21 because they belong to the "next" trading day
      const adjDate = new Date(d.getTime());
      if (h >= 21) adjDate.setUTCDate(adjDate.getUTCDate() + 1);
      const dayStr = `${adjDate.getUTCFullYear()}-${adjDate.getUTCMonth()}-${adjDate.getUTCDate()}`;
      
      // Special case: If it's ASIA but originated from 21:00-00:00, it shares the same blockId as the 00:00-07:00 ASIA session
      const blockId = `${dayStr}-${sType}`;

      if (currentId !== blockId) {
        if (currentBars.length > 0) {
          const result = this.calculateBlock(currentId, currentType, currentBars, options);
          if (result) blocks.push(result);
        }
        currentId = blockId;
        currentType = sType;
        currentBars = [bar];
      } else {
        currentBars.push(bar);
      }
    }

    if (currentBars.length > 0) {
      const result = this.calculateBlock(currentId, currentType, currentBars, options);
      if (result) blocks.push(result);
    }

    return blocks;
  }

  static calculateBlock(
    id: string,
    type: string,
    bars: SessionVPData[],
    options: SessionVPOptions
  ): SessionBlock | null {
    if (bars.length === 0) return null;

    const firstBarTime = bars[0].time as number;
    const lastBarTime = bars[bars.length - 1].time as number;
    const duration = lastBarTime - firstBarTime;
    
    // Time boundaries for Old/New money split (1/3 and 2/3)
    const t1 = firstBarTime + duration / 3;
    const t2 = firstBarTime + (2 * duration) / 3;

    let minPrice = Infinity;
    let maxPrice = -Infinity;
    let totalVol = 0;

    for (const d of bars) {
      if (d.low < minPrice) minPrice = d.low;
      if (d.high > maxPrice) maxPrice = d.high;
      totalVol += d.volume || 0;
    }

    if (minPrice === Infinity || maxPrice === -Infinity || minPrice === maxPrice || totalVol === 0) {
      return null;
    }

    const epsilon = (maxPrice - minPrice) * 0.000001;
    const binSize = (maxPrice - minPrice + epsilon) / options.bins;
    
    const bins: SessionProfileBin[] = Array.from({ length: options.bins }, (_, i) => ({
      yStart: minPrice + i * binSize,
      yEnd: minPrice + (i + 1) * binSize,
      vol1: 0,
      vol2: 0,
      vol3: 0,
      totalVolume: 0,
      inValueArea: false
    }));

    for (const d of bars) {
      const vol = d.volume || 0;
      if (vol === 0) continue;

      const time = d.time as number;
      const part = time < t1 ? 1 : (time < t2 ? 2 : 3);
      const range = d.high - d.low;

      if (range === 0) {
        const binIdx = Math.min(Math.floor((d.close - minPrice) / binSize), options.bins - 1);
        if (binIdx >= 0 && binIdx < options.bins) {
          if (part === 1) bins[binIdx].vol1 += vol;
          else if (part === 2) bins[binIdx].vol2 += vol;
          else bins[binIdx].vol3 += vol;
          bins[binIdx].totalVolume += vol;
        }
        continue;
      }

      for (let i = 0; i < options.bins; i++) {
        const bin = bins[i];
        const overlapStart = Math.max(d.low, bin.yStart);
        const overlapEnd = Math.min(d.high, bin.yEnd);
        const overlap = overlapEnd - overlapStart;

        if (overlap > 0) {
          const ratio = overlap / range;
          const allocatedVol = vol * ratio;
          if (part === 1) bin.vol1 += allocatedVol;
          else if (part === 2) bin.vol2 += allocatedVol;
          else bin.vol3 += allocatedVol;
          bin.totalVolume += allocatedVol;
        }
      }
    }

    let maxVol = 0;
    let pocIndex = 0;
    for (let i = 0; i < options.bins; i++) {
      if (bins[i].totalVolume > maxVol) {
        maxVol = bins[i].totalVolume;
        pocIndex = i;
      }
    }

    // Calculate Value Area
    const targetVA = totalVol * (options.valueAreaPct / 100);
    let currentVA = bins[pocIndex].totalVolume;
    bins[pocIndex].inValueArea = true;

    let upIdx = pocIndex + 1;
    let downIdx = pocIndex - 1;

    while (currentVA < targetVA && (upIdx < options.bins || downIdx >= 0)) {
      const volUp = upIdx < options.bins ? bins[upIdx].totalVolume : -1;
      const volDown = downIdx >= 0 ? bins[downIdx].totalVolume : -1;

      if (volUp > volDown) {
        currentVA += volUp;
        bins[upIdx].inValueArea = true;
        upIdx++;
      } else if (volDown > volUp) {
        currentVA += volDown;
        bins[downIdx].inValueArea = true;
        downIdx--;
      } else {
        if (upIdx < options.bins) {
          currentVA += volUp;
          bins[upIdx].inValueArea = true;
          upIdx++;
        }
        if (downIdx >= 0 && currentVA < targetVA) {
          currentVA += volDown;
          bins[downIdx].inValueArea = true;
          downIdx--;
        }
      }
    }

    return {
      id,
      type,
      firstBarTime,
      lastBarTime,
      minPrice,
      maxPrice,
      bins,
      pocPrice: (bins[pocIndex].yStart + bins[pocIndex].yEnd) / 2,
      pocVolume: maxVol,
      maxVolume: maxVol,
      valueAreaLow: downIdx >= 0 ? bins[downIdx + 1].yStart : bins[0].yStart,
      valueAreaHigh: upIdx < options.bins ? bins[upIdx - 1].yEnd : bins[options.bins - 1].yEnd
    };
  }
}