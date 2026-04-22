import { ICustomSeriesPaneRenderer, PaneRendererCustomData, Time } from 'lightweight-charts';
import { CanvasRenderingTarget2D } from 'fancy-canvas';
import { VolumeProfileData, VolumeProfileOptions, ProfileResult } from './types';
import { Calculator } from './Calculator';

export class VolumeProfileRenderer implements ICustomSeriesPaneRenderer {
  _data: PaneRendererCustomData<Time, VolumeProfileData> | null = null;
  _options: VolumeProfileOptions | null = null;
  
  private lastRangeStr = '';
  private cachedResult: ProfileResult | null = null;

  draw(target: CanvasRenderingTarget2D, priceConverter: (price: number) => number | null, isHovered: boolean, hitTestData?: unknown): void {
    if (!this._data || !this._options || !this._data.visibleRange) return;

    const { bars, visibleRange } = this._data;
    const rangeStr = `${visibleRange.from}-${visibleRange.to}`;
    
    // Memoize calculation based on visible range
    if (this.lastRangeStr !== rangeStr) {
      const visibleData: VolumeProfileData[] = [];
      for (let i = visibleRange.from; i <= visibleRange.to; i++) {
        if (bars[i] && bars[i].originalData) {
          visibleData.push(bars[i].originalData as VolumeProfileData);
        }
      }
      this.cachedResult = Calculator.calculate(visibleData, this._options.bins, this._options.valueAreaPercentage);
      this.lastRangeStr = rangeStr;
    }

    if (!this.cachedResult) return;

    target.useMediaCoordinateSpace((scope) => {
      const ctx = scope.context;
      const { bins, maxVolume, pocPrice } = this.cachedResult!;
      const { placement, width, upColor, downColor, valueAreaUpColor, valueAreaDownColor, pocColor } = this._options!;

      const canvasWidth = scope.mediaSize.width;
      const maxWidthPx = canvasWidth * (width / 100);

      ctx.save();
      
      // Draw Bins
      for (const bin of bins) {
        const yStart = priceConverter(bin.yStart);
        const yEnd = priceConverter(bin.yEnd);
        if (yStart === null || yEnd === null) continue;

        const yTop = Math.min(yStart, yEnd);
        const yBottom = Math.max(yStart, yEnd);
        const h = Math.max(1, yBottom - yTop);

        const wUp = (bin.volumeUp / maxVolume) * maxWidthPx;
        const wDown = (bin.volumeDown / maxVolume) * maxWidthPx;
        const totalW = wUp + wDown;

        const cUp = bin.inValueArea ? valueAreaUpColor : upColor;
        const cDown = bin.inValueArea ? valueAreaDownColor : downColor;

        if (placement === 'right') {
          const xStart = canvasWidth - totalW;
          // Draw up vol
          ctx.fillStyle = cUp;
          ctx.fillRect(xStart, yTop, wUp, h);
          // Draw down vol
          ctx.fillStyle = cDown;
          ctx.fillRect(xStart + wUp, yTop, wDown, h);
        } else {
          // Draw up vol
          ctx.fillStyle = cUp;
          ctx.fillRect(0, yTop, wUp, h);
          // Draw down vol
          ctx.fillStyle = cDown;
          ctx.fillRect(wUp, yTop, wDown, h);
        }
      }

      // Draw POC
      const yPoc = priceConverter(pocPrice);
      if (yPoc !== null) {
        ctx.beginPath();
        ctx.strokeStyle = pocColor;
        ctx.lineWidth = 1;
        if (placement === 'right') {
          ctx.moveTo(canvasWidth - maxWidthPx, yPoc);
          ctx.lineTo(canvasWidth, yPoc);
        } else {
          ctx.moveTo(0, yPoc);
          ctx.lineTo(maxWidthPx, yPoc);
        }
        ctx.stroke();
      }

      ctx.restore();
    });
  }
}
