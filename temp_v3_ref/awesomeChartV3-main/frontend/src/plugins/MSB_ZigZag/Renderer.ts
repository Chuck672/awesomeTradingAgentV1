import { ICustomSeriesPaneRenderer, PaneRendererCustomData, Time } from "lightweight-charts";
import { CanvasRenderingTarget2D } from "fancy-canvas";
import { MSBZZData, MSBZZOptions, ComputedMSBZZ } from "./types";
import { Calculator } from "./Calculator";

export class MSBZZRenderer implements ICustomSeriesPaneRenderer {
  _data: PaneRendererCustomData<Time, any> | null = null;
  _options: MSBZZOptions | null = null;
  fullData: MSBZZData[] = [];
  timeToCoordinate?: (time: Time) => number | null;

  private lastDataLength = 0;
  private lastOptionsStr = "";
  private computedData: ComputedMSBZZ = { zigzags: [], lines: [] };

  update(data: PaneRendererCustomData<Time, any>, seriesOptions: MSBZZOptions): void {
    this._data = data;
    this._options = seriesOptions;
  }

  clearCache() {
    this.lastDataLength = 0;
    this.computedData = { zigzags: [], lines: [] };
  }

  draw(
    target: CanvasRenderingTarget2D,
    priceConverter: (price: number) => number | null,
    _isHovered: boolean,
    _hitTestData?: unknown
  ): void {
    if (!this._data || !this._options || this._options.visible === false || this.fullData.length === 0) {
      return;
    }

    try {
      const optionsStr = JSON.stringify(this._options);
      if (this.lastDataLength !== this.fullData.length || this.lastOptionsStr !== optionsStr || this.computedData.zigzags.length === 0) {
        this.clearCache();
        this.computedData = Calculator.computeMSBZZ(this.fullData, this._options);
        this.lastDataLength = this.fullData.length;
        this.lastOptionsStr = optionsStr;
      }
    } catch (e) {
      console.error("MSBZZ Error in computation:", e);
      return;
    }

    const currentData = this._data;
    const currentOptions = this._options;

    target.useMediaCoordinateSpace((scope) => {
      const ctx = scope.context;
      if (!this.timeToCoordinate) return;

      ctx.save();

      // 1. Draw ZigZag Lines
      if (currentOptions.showZigZag && this.computedData.zigzags.length > 1) {
        ctx.beginPath();
        ctx.strokeStyle = currentOptions.zigZagColor;
        ctx.lineWidth = currentOptions.zigZagWidth;

        // Line styles: 0=solid, 1=dotted, 2=dashed
        if (currentOptions.zigZagStyle === 1) ctx.setLineDash([2, 2]);
        else if (currentOptions.zigZagStyle === 2) ctx.setLineDash([5, 5]);
        else ctx.setLineDash([]);

        let hasStarted = false;
        for (let i = 0; i < this.computedData.zigzags.length; i++) {
          const pt = this.computedData.zigzags[i];
          const x = this.timeToCoordinate(pt.time as Time);
          const y = priceConverter(pt.value);
          
          if (x !== null && y !== null) {
            if (!hasStarted) {
              ctx.moveTo(x, y);
              hasStarted = true;
            } else {
              ctx.lineTo(x, y);
            }
          }
        }
        ctx.stroke();
      }

      // 2. Draw ZigZag Labels
      if (currentOptions.showLabel) {
        ctx.font = "10px Arial";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        
        for (const pt of this.computedData.zigzags) {
          const x = this.timeToCoordinate(pt.time as Time);
          const y = priceConverter(pt.value);
          if (x !== null && y !== null) {
            const isHigh = pt.type.endsWith('H');
            const labelY = isHigh ? y - 15 : y + 15;
            
            // Background box for label
            const textWidth = ctx.measureText(pt.type).width;
            ctx.fillStyle = "rgba(255, 255, 255, 0.7)";
            ctx.fillRect(x - textWidth / 2 - 2, labelY - 6, textWidth + 4, 12);
            
            ctx.fillStyle = currentOptions.labelColor;
            ctx.fillText(pt.type, x, labelY);
          }
        }
      }

      // 3. Draw BoS / ChoCh Lines
      for (const line of this.computedData.lines) {
        const drawLine = (color: string, style: number, text: string) => {
          const x1 = this.timeToCoordinate!(line.startTime as Time);
          const x2 = this.timeToCoordinate!(line.endTime as Time);
          const y = priceConverter(line.level);
          
          if (x1 !== null && x2 !== null && y !== null) {
            ctx.beginPath();
            ctx.strokeStyle = color;
            ctx.lineWidth = 1;
            if (style === 1) ctx.setLineDash([2, 2]);
            else if (style === 2) ctx.setLineDash([5, 5]);
            else ctx.setLineDash([]);
            
            ctx.moveTo(x1, y);
            ctx.lineTo(x2, y);
            ctx.stroke();

            // Label at midpoint
            const midX = (x1 + x2) / 2;
            ctx.font = "10px Arial";
            ctx.textAlign = "center";
            ctx.textBaseline = "bottom";
            ctx.fillStyle = color;
            ctx.fillText(text, midX, y - 2);
          }
        };

        if (line.type === "MajorBoSBull" && currentOptions.showMajorBuBoS) {
          drawLine(currentOptions.majorBuBoSColor, currentOptions.majorBuBoSStyle, line.text);
        } else if (line.type === "MajorBoSBear" && currentOptions.showMajorBeBoS) {
          drawLine(currentOptions.majorBeBoSColor, currentOptions.majorBeBoSStyle, line.text);
        } else if (line.type === "MajorChoChBull" && currentOptions.showMajorBuChoCh) {
          drawLine(currentOptions.majorBuChoChColor, currentOptions.majorBuChoChStyle, line.text);
        } else if (line.type === "MajorChoChBear" && currentOptions.showMajorBeChoCh) {
          drawLine(currentOptions.majorBeChoChColor, currentOptions.majorBeChoChStyle, line.text);
        } else if (line.type === "MinorBoSBull" && currentOptions.showMinorBuBoS) {
          drawLine(currentOptions.minorBuBoSColor, currentOptions.minorBuBoSStyle, line.text);
        } else if (line.type === "MinorBoSBear" && currentOptions.showMinorBeBoS) {
          drawLine(currentOptions.minorBeBoSColor, currentOptions.minorBeBoSStyle, line.text);
        } else if (line.type === "MinorChoChBull" && currentOptions.showMinorBuChoCh) {
          drawLine(currentOptions.minorBuChoChColor, currentOptions.minorBuChoChStyle, line.text);
        } else if (line.type === "MinorChoChBear" && currentOptions.showMinorBeChoCh) {
          drawLine(currentOptions.minorBeChoChColor, currentOptions.minorBeChoChStyle, line.text);
        }
      }

      ctx.restore();
    });
  }
}