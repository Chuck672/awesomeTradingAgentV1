import { ICustomSeriesPaneRenderer, PaneRendererCustomData, Time } from 'lightweight-charts';
import { CanvasRenderingTarget2D } from 'fancy-canvas';
import { SessionVPData, SessionVPOptions, SessionBlock } from './types';
import { Calculator } from './Calculator';

export class SessionVPRenderer implements ICustomSeriesPaneRenderer {
  _data: PaneRendererCustomData<Time, SessionVPData> | null = null;
  _options: SessionVPOptions | null = null;
  fullData: SessionVPData[] = [];
  timeToCoordinate?: (time: Time) => number | null;
  
  private lastDataLength = 0;
  private lastOptionsStr = '';
  private cachedBlocks: SessionBlock[] = [];

  clearCache() {
    this.lastDataLength = 0;
    this.cachedBlocks = [];
  }

  draw(target: CanvasRenderingTarget2D, priceConverter: (price: number) => number | null, isHovered: boolean, hitTestData?: unknown): void {
    if (!this._data || !this._options || this.fullData.length === 0) return;

    const optionsStr = JSON.stringify(this._options);
    if (this.lastDataLength !== this.fullData.length || this.lastOptionsStr !== optionsStr) {
      this.cachedBlocks = Calculator.calculateAll(this.fullData, this._options);
      this.lastDataLength = this.fullData.length;
      this.lastOptionsStr = optionsStr;
    }

    if (this.cachedBlocks.length === 0) return;

    target.useMediaCoordinateSpace((scope) => {
      const ctx = scope.context;
      const { maxWidthPercent, colorPart1, colorPart2, colorPart3, pocColor } = this._options!;
      
      // If timeToCoordinate function is provided by View, use it for exact physical pixel mapping
      if (!this.timeToCoordinate) return;

      ctx.save();
      
      for (const block of this.cachedBlocks) {
        const xStart = this.timeToCoordinate(block.firstBarTime as Time);
        const xEnd = this.timeToCoordinate(block.lastBarTime as Time);
        
        if (xStart === null || xEnd === null) continue;

        // Session width in pixels
        const sessionWidthPx = Math.max(xEnd - xStart, 20); // Fallback min width
        const maxWidthPx = sessionWidthPx * (maxWidthPercent / 100);

        for (const bin of block.bins) {
          const yStart = priceConverter(bin.yStart);
          const yEnd = priceConverter(bin.yEnd);
          if (yStart === null || yEnd === null) continue;

          const yTop = Math.min(yStart, yEnd);
          const yBottom = Math.max(yStart, yEnd);
          const h = Math.max(1, yBottom - yTop);

          const w1 = (bin.vol1 / block.maxVolume) * maxWidthPx;
          const w2 = (bin.vol2 / block.maxVolume) * maxWidthPx;
          const w3 = (bin.vol3 / block.maxVolume) * maxWidthPx;

          ctx.globalAlpha = bin.inValueArea ? 0.8 : 0.3;

          // Part 1
          if (w1 > 0) {
            ctx.fillStyle = colorPart1;
            ctx.fillRect(xStart, yTop, w1, h);
          }
          // Part 2
          if (w2 > 0) {
            ctx.fillStyle = colorPart2;
            ctx.fillRect(xStart + w1, yTop, w2, h);
          }
          // Part 3
          if (w3 > 0) {
            ctx.fillStyle = colorPart3;
            ctx.fillRect(xStart + w1 + w2, yTop, w3, h);
          }
        }

        // Draw POC
        ctx.globalAlpha = 1.0;
        const yPoc = priceConverter(block.pocPrice);
        if (yPoc !== null) {
          ctx.beginPath();
          ctx.strokeStyle = pocColor;
          ctx.lineWidth = 1;
          ctx.moveTo(xStart, yPoc);
          const totalPocW = (block.pocVolume / block.maxVolume) * maxWidthPx;
          ctx.lineTo(xStart + totalPocW, yPoc);
          ctx.stroke();
        }
      }

      ctx.restore();
    });
  }
}
