import { ICustomSeriesPaneRenderer, PaneRendererCustomData, Time } from "lightweight-charts";
import { CanvasRenderingTarget2D } from "fancy-canvas";
import { RajaSRData, RajaSROptions, RajaZone } from "./types";
import { Calculator } from "./Calculator";

export class RajaSRRenderer implements ICustomSeriesPaneRenderer {
  _data: PaneRendererCustomData<Time, any> | null = null;
  _options: RajaSROptions | null = null;
  fullData: RajaSRData[] = [];
  timeToCoordinate?: (time: Time) => number | null;

  private lastDataLength = 0;
  private lastOptionsStr = "";
  private cachedZones: RajaZone[] = [];

  update(data: PaneRendererCustomData<Time, any>, seriesOptions: RajaSROptions): void {
    // console.log("RajaSR _renderer update called", {
    //   dataLength: data.bars.length,
    //   visible: seriesOptions.visible,
    //   pivot: seriesOptions.pivot,
    //   minTouches: seriesOptions.minTouches
    // });
    this._data = data;
    this._options = seriesOptions;
  }

  clearCache() {
    this.lastDataLength = 0;
    this.cachedZones = [];
  }

  draw(
    target: CanvasRenderingTarget2D,
    priceConverter: (price: number) => number | null,
    isHovered: boolean,
    hitTestData?: unknown
  ): void {
    if (!this._data || !this._options || this._options.visible === false || this.fullData.length === 0) {
      return;
    }

    const optionsStr = JSON.stringify(this._options);
    if (this.lastDataLength !== this.fullData.length || this.lastOptionsStr !== optionsStr || this.cachedZones.length === 0) {
      // console.log("RajaSR RECALCULATING ZONES:", {
      //   oldOptions: this.lastOptionsStr,
      //   newOptions: optionsStr,
      //   dataLen: this.fullData.length
      // });
      this.clearCache(); // Force cache clear before recompute
      this.cachedZones = Calculator.computeRajaZones(this.fullData, this._options);
      this.lastDataLength = this.fullData.length;
      this.lastOptionsStr = optionsStr;
    }

    if (this.cachedZones.length === 0) return;

    target.useMediaCoordinateSpace((scope) => {
      const ctx = scope.context;
      if (!this.timeToCoordinate) {
        console.warn("RajaSR: timeToCoordinate is not set!");
        return;
      }

      ctx.save();

      // We draw zones from their from_time to the right edge of the visible chart.
      const chartWidth = scope.mediaSize.width;

      for (const zone of this.cachedZones) {
        // Find x coordinate
        let xStart = this.timeToCoordinate(zone.from_time as Time);
        
        // If the time is off the left edge, xStart might be null or negative.
        // We can clamp it to 0 if it's off-screen, or if timeToCoordinate fails, we can assume it starts off-screen (0)
        if (xStart === null) {
            xStart = 0; 
        }

        const xEnd = chartWidth;

        const yTop = priceConverter(zone.top);
        const yBottom = priceConverter(zone.bottom);

        if (yTop === null || yBottom === null) continue;

        const y1 = Math.min(yTop, yBottom);
        const y2 = Math.max(yTop, yBottom);
        const h = Math.max(1, y2 - y1);
        const w = Math.max(1, xEnd - xStart);

        ctx.fillStyle = zone.type === "resistance" ? this._options!.zoneColor : this._options!.zoneColor;
        ctx.fillRect(xStart, y1, w, h);
        
        // Remove the hardcoded red/green horizontal line
        /*
        const yBase = priceConverter(zone.level);
        if (yBase !== null) {
          ctx.beginPath();
          ctx.strokeStyle = zone.type === "resistance" ? "rgba(239, 83, 80, 0.8)" : "rgba(38, 166, 154, 0.8)";
          ctx.lineWidth = 1;
          ctx.moveTo(xStart, yBase);
          ctx.lineTo(xEnd, yBase);
          ctx.stroke();
        }
        */
      }

      ctx.restore();
    });
  }
}