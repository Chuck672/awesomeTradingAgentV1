import { ProfileBin, ProfileResult, VolumeProfileData } from './types';

export class Calculator {
  static calculate(
    data: VolumeProfileData[],
    binsCount: number,
    valueAreaPct: number
  ): ProfileResult | null {
    if (data.length === 0) return null;

    let minPrice = Infinity;
    let maxPrice = -Infinity;
    let totalVol = 0;

    for (const d of data) {
      if (d.low < minPrice) minPrice = d.low;
      if (d.high > maxPrice) maxPrice = d.high;
      totalVol += d.volume || 0;
    }

    if (minPrice === Infinity || maxPrice === -Infinity || minPrice === maxPrice || totalVol === 0) {
      return null;
    }

    // Small buffer to ensure maxPrice falls into the last bin
    const epsilon = (maxPrice - minPrice) * 0.000001;
    const binSize = (maxPrice - minPrice + epsilon) / binsCount;
    
    const bins: ProfileBin[] = Array.from({ length: binsCount }, (_, i) => ({
      yStart: minPrice + i * binSize,
      yEnd: minPrice + (i + 1) * binSize,
      volumeUp: 0,
      volumeDown: 0,
      totalVolume: 0,
      inValueArea: false
    }));

    for (const d of data) {
      const isUp = d.close >= d.open;
      const vol = d.volume || 0;
      if (vol === 0) continue;

      const range = d.high - d.low;

      if (range === 0) {
        // Single price point
        const binIdx = Math.min(
          Math.floor((d.close - minPrice) / binSize),
          binsCount - 1
        );
        if (binIdx >= 0 && binIdx < binsCount) {
          if (isUp) bins[binIdx].volumeUp += vol;
          else bins[binIdx].volumeDown += vol;
          bins[binIdx].totalVolume += vol;
        }
        continue;
      }

      // Distribute volume proportionally across overlapping bins
      for (let i = 0; i < binsCount; i++) {
        const bin = bins[i];
        const overlapStart = Math.max(d.low, bin.yStart);
        const overlapEnd = Math.min(d.high, bin.yEnd);
        const overlap = overlapEnd - overlapStart;

        if (overlap > 0) {
          const ratio = overlap / range;
          const allocatedVol = vol * ratio;
          if (isUp) bin.volumeUp += allocatedVol;
          else bin.volumeDown += allocatedVol;
          bin.totalVolume += allocatedVol;
        }
      }
    }

    let maxVol = 0;
    let pocIndex = 0;
    for (let i = 0; i < binsCount; i++) {
      if (bins[i].totalVolume > maxVol) {
        maxVol = bins[i].totalVolume;
        pocIndex = i;
      }
    }

    // Calculate Value Area
    const targetVA = totalVol * (valueAreaPct / 100);
    let currentVA = bins[pocIndex].totalVolume;
    bins[pocIndex].inValueArea = true;

    let upIdx = pocIndex + 1;
    let downIdx = pocIndex - 1;

    while (currentVA < targetVA && (upIdx < binsCount || downIdx >= 0)) {
      const volUp = upIdx < binsCount ? bins[upIdx].totalVolume : -1;
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
        // Equal volume, expand both if possible
        if (upIdx < binsCount) {
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
      bins,
      pocPrice: (bins[pocIndex].yStart + bins[pocIndex].yEnd) / 2,
      pocVolume: maxVol,
      maxVolume: maxVol,
      valueAreaLow: downIdx >= 0 ? bins[downIdx + 1].yStart : bins[0].yStart,
      valueAreaHigh: upIdx < binsCount ? bins[upIdx - 1].yEnd : bins[binsCount - 1].yEnd
    };
  }
}
