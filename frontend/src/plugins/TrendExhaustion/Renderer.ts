import { ComputedTrendExhaustion, TrendExhaustionOptions, TrendExhaustionData } from "./types";
import { Calculator } from "./Calculator";

// Helper function for converting hex/rgb to rgba
function hexToRgba(hex: string, alpha: number) {
  let r = 0, g = 0, b = 0;
  if (hex.startsWith("#")) {
    const cleanHex = hex.slice(1);
    if (cleanHex.length === 3) {
      r = parseInt(cleanHex[0] + cleanHex[0], 16);
      g = parseInt(cleanHex[1] + cleanHex[1], 16);
      b = parseInt(cleanHex[2] + cleanHex[2], 16);
    } else if (cleanHex.length === 6) {
      r = parseInt(cleanHex.substring(0, 2), 16);
      g = parseInt(cleanHex.substring(2, 4), 16);
      b = parseInt(cleanHex.substring(4, 6), 16);
    }
  } else if (hex.startsWith("rgb")) {
    const vals = hex.match(/\d+/g);
    if (vals && vals.length >= 3) {
      r = parseInt(vals[0], 10);
      g = parseInt(vals[1], 10);
      b = parseInt(vals[2], 10);
    }
  }
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

export class Renderer {
  _data: any = null;
  _options: TrendExhaustionOptions | null = null;
  timeToCoordinate: ((time: any) => number | null) | null = null;

  private computedData: ComputedTrendExhaustion = { boxes: [], shapes: [] };
  private fullData: TrendExhaustionData[] = [];
  private lastDataLength: number = -1;
  private lastOptionsStr: string = "";

  setFullData(data: TrendExhaustionData[]) {
    this.fullData = data;
    this.clearCache();
  }

  clearCache() {
    this.lastDataLength = -1;
    this.computedData = { boxes: [], shapes: [] };
  }

  draw(
    target: any,
    priceConverter: (price: number) => number | null,
    _isHovered: boolean,
    _hitTestData?: unknown
  ): void {
    if (!this._data || !this._options || this._options.visible === false || this.fullData.length === 0) {
      return;
    }

    try {
      const optionsStr = JSON.stringify(this._options);
      if (this.lastDataLength !== this.fullData.length || this.lastOptionsStr !== optionsStr) {
        this.clearCache();
        this.computedData = Calculator.computeTE(this.fullData, this._options);
        this.lastDataLength = this.fullData.length;
        this.lastOptionsStr = optionsStr;
      }
    } catch (e) {
      console.error("TrendExhaustion Error in computation:", e);
      return;
    }

    const currentData = this._data;
    const currentOptions = this._options;

    target.useMediaCoordinateSpace((scope: any) => {
      const ctx = scope.context;
      const timeToCoord = this.timeToCoordinate;
      if (!timeToCoord) return;

      ctx.save();

      // Fast lookup for visible bars
      const visibleBars = new Map<string, number>();
      const timeToString = (t: any): string => {
        if (t === undefined || t === null) return "";
        if (typeof t === 'object') return JSON.stringify(t);
        return String(t);
      };

      if (currentData.bars) {
        for (const bar of currentData.bars) {
          const tKey = timeToString(bar.time);
          if (tKey) visibleBars.set(tKey, bar.x);
        }
      }

      const getXByIndex = (index: number): number | null => {
        if (index < 0 || index >= this.fullData.length) return null;
        const time = this.fullData[index].time;
        const tKey = timeToString(time);
        if (tKey && visibleBars.has(tKey)) {
          return visibleBars.get(tKey)!;
        }
        // Approximate if not exactly in visible range
        if (currentData.visibleRange) {
          if (index < currentData.visibleRange.from) {
            const diff = currentData.visibleRange.from - index;
            return -diff * currentData.barSpacing; // Extrapolate left
          }
          if (index > currentData.visibleRange.to) {
            const diff = index - currentData.visibleRange.to;
            return scope.mediaSize.width + diff * currentData.barSpacing; // Extrapolate right
          }
        }
        const coord = timeToCoord(time);
        if (coord === null) {
          // Final fallback
          if (currentData.visibleRange) {
             if (index < currentData.visibleRange.from) return -1000;
             if (index > currentData.visibleRange.to) return scope.mediaSize.width + 1000;
          }
        }
        return coord;
      };

      // 1. Draw Boxes
      if (currentOptions.showBoxes) {
        for (const box of this.computedData.boxes) {
          const x1 = getXByIndex(box.startIndex);
          const x2 = getXByIndex(box.endIndex);
          const yTop = priceConverter(box.top);
          const yBottom = priceConverter(box.bottom);

          if (x1 !== null && x2 !== null && yTop !== null && yBottom !== null) {
            const width = Math.max(1, x2 - x1);
            const height = yBottom - yTop; // Canvas Y goes down
            const color = box.isBull ? currentOptions.colorBull : currentOptions.colorBear;
            
            ctx.fillStyle = hexToRgba(color, 0.2);
            ctx.strokeStyle = color;
            ctx.lineWidth = 1;

            ctx.beginPath();
            ctx.rect(x1, yTop, width, height);
            ctx.fill();
            ctx.stroke();
          }
        }
      }

      // 2. Draw Shapes (Triangles and Squares)
      if (currentOptions.showShapes) {
        for (const shape of this.computedData.shapes) {
          const x = getXByIndex(shape.index);
          const y = priceConverter(shape.y);

          if (x !== null && y !== null) {
            ctx.fillStyle = shape.color;
            ctx.beginPath();

            const size = 5;
            const offset = shape.isTop ? -10 : 10;
            const drawY = y + offset;

            if (shape.type === 'square') {
              ctx.rect(x - size, drawY - size, size * 2, size * 2);
            } else if (shape.type === 'triangleup') {
              ctx.moveTo(x, drawY - size);
              ctx.lineTo(x + size, drawY + size);
              ctx.lineTo(x - size, drawY + size);
            } else if (shape.type === 'triangledown') {
              ctx.moveTo(x - size, drawY - size);
              ctx.lineTo(x + size, drawY - size);
              ctx.lineTo(x, drawY + size);
            }
            
            ctx.fill();
          }
        }
      }

      ctx.restore();
    });
  }
}
