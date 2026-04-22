import { IPrimitivePaneView, Logical, Time } from 'lightweight-charts';
import { CanvasRenderingTarget2D } from 'fancy-canvas';
import { BaseDrawing } from '../core/base-drawing';
import { DataPoint, HitTestResult, PixelPoint, BaseDrawingStyle } from '../core/types';
import { HitTestUtils } from '../core/hit-test';
import { CoordinateUtils } from '../core/coordinate-utils';

export interface PositionStyle extends BaseDrawingStyle {
  targetColor: string;
  stopColor: string;
  fillOpacity: number;
  textColor: string;
}

export const defaultPositionStyle: PositionStyle = {
  lineColor: '#787B86',
  lineWidth: 1,
  lineStyle: 'solid',
  targetColor: '#00BCD4', // Cyan/Greenish
  stopColor: '#FF5252',   // Red
  fillOpacity: 0.2,
  textColor: '#FFFFFF'
};

function applyOpacity(color: string, opacity: number): string {
  if (color.startsWith('rgba')) {
    return color.replace(/rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*[\d.]+)?\)/, `rgba($1, $2, $3, ${opacity})`);
  } else if (color.startsWith('#')) {
    const h = color.replace('#', '');
    if (h.length >= 6) {
      const r = parseInt(h.substring(0, 2), 16);
      const g = parseInt(h.substring(2, 4), 16);
      const b = parseInt(h.substring(4, 6), 16);
      return `rgba(${r}, ${g}, ${b}, ${opacity})`;
    }
  }
  return color;
}

class PositionPaneRenderer {
  constructor(private _drawing: PositionDrawing) {}

  draw(target: CanvasRenderingTarget2D): void {
    const points = this._drawing.getPoints();
    const style = this._drawing.getStyle() as PositionStyle;
    
    if (points.length < 3) return;

    const px0 = this._drawing.dataToPixel(points[0]); // Entry
    const px1 = this._drawing.dataToPixel(points[1]); // TP
    const px2 = this._drawing.dataToPixel(points[2]); // SL

    if (!px0 || !px1 || !px2) return;

    target.useMediaCoordinateSpace((scope) => {
      const ctx = scope.context;
      ctx.save();
      
      const xStart = px0.x;
      const xEnd = px1.x;
      const w = xEnd - xStart;

      const yEntry = px0.y;
      const yTP = px1.y;
      const ySL = px2.y;

      // Draw Target Box
      ctx.fillStyle = applyOpacity(style.targetColor, style.fillOpacity);
      ctx.fillRect(xStart, Math.min(yEntry, yTP), w, Math.abs(yEntry - yTP));

      // Draw Stop Box
      ctx.fillStyle = applyOpacity(style.stopColor, style.fillOpacity);
      ctx.fillRect(xStart, Math.min(yEntry, ySL), w, Math.abs(yEntry - ySL));

      // Separator Line
      ctx.strokeStyle = style.lineColor;
      ctx.lineWidth = style.lineWidth;
      if (style.lineStyle === 'dashed') ctx.setLineDash([5, 5]);
      else if (style.lineStyle === 'dotted') ctx.setLineDash([2, 2]);
      
      ctx.beginPath();
      ctx.moveTo(xStart, yEntry);
      ctx.lineTo(xEnd, yEntry);
      ctx.stroke();

      // Text R/R Ratio
      const risk = Math.abs(points[0].price - points[2].price);
      const reward = Math.abs(points[0].price - points[1].price);
      const ratio = risk > 0 ? (reward / risk).toFixed(2) : '∞';

      ctx.setLineDash([]);
      ctx.font = '12px sans-serif';
      ctx.fillStyle = style.textColor;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      
      const textX = xStart + w / 2;
      const textY = yEntry; // R/R exactly in the middle of entry level
      
      // Add text background for R/R
      const textMetrics = ctx.measureText(`R/R: ${ratio}`);
      const textWidth = textMetrics.width + 8;
      ctx.fillStyle = 'rgba(0, 0, 0, 0.5)';
      ctx.beginPath();
      ctx.roundRect(textX - textWidth / 2, textY - 8, textWidth, 16, 2);
      ctx.fill();

      // Draw Text
      ctx.fillStyle = style.textColor;
      ctx.fillText(`R/R: ${ratio}`, textX, textY);

      // Draw TP and SL Diff Text
      const tpDiff = (points[1].price - points[0].price).toFixed(2);
      const slDiff = (points[2].price - points[0].price).toFixed(2);
      const tpPercent = ((points[1].price - points[0].price) / points[0].price * 100).toFixed(2);
      const slPercent = ((points[2].price - points[0].price) / points[0].price * 100).toFixed(2);

      ctx.font = '11px sans-serif';
      
      // TP Text (At the outer edge of the TP box)
      const tpText = `${tpDiff > '0' ? '+' : ''}${tpDiff} (${tpPercent}%)`;
      const tpTextMetrics = ctx.measureText(tpText);
      const tpTextWidth = tpTextMetrics.width + 8;
      
      // Position TP text based on whether it's Long or Short. 
      // Put it OUTSIDE the box. 
      const isLong = this._drawing.toolType === 'long_position';
      const tpTextY = isLong ? Math.min(yEntry, yTP) - 12 : Math.max(yEntry, yTP) + 12;
      
      ctx.fillStyle = 'rgba(0, 0, 0, 0.4)';
      ctx.beginPath();
      ctx.roundRect(textX - tpTextWidth / 2, tpTextY - 8, tpTextWidth, 16, 2);
      ctx.fill();
      ctx.fillStyle = style.textColor;
      ctx.fillText(tpText, textX, tpTextY);

      // SL Text (At the outer edge of the SL box)
      const slText = `${slDiff > '0' ? '+' : ''}${slDiff} (${slPercent}%)`;
      const slTextMetrics = ctx.measureText(slText);
      const slTextWidth = slTextMetrics.width + 8;
      
      // Position SL text based on whether it's Long or Short
      // Put it OUTSIDE the box.
      const slTextY = isLong ? Math.max(yEntry, ySL) + 12 : Math.min(yEntry, ySL) - 12;
      
      ctx.fillStyle = 'rgba(0, 0, 0, 0.4)';
      ctx.beginPath();
      ctx.roundRect(textX - slTextWidth / 2, slTextY - 8, slTextWidth, 16, 2);
      ctx.fill();
      ctx.fillStyle = style.textColor;
      ctx.fillText(slText, textX, slTextY);

      // Control points
      if (this._drawing.hovered) {
        const controlPoints = [px0, px1, px2];
        ctx.fillStyle = '#ffffff';
        ctx.lineWidth = 2;
        ctx.strokeStyle = style.lineColor;
        for (const cp of controlPoints) {
          ctx.beginPath();
          ctx.arc(cp.x, cp.y, 5, 0, Math.PI * 2);
          ctx.fill();
          ctx.stroke();
        }
      }

      ctx.restore();
    });
  }
}

class PositionPaneView implements IPrimitivePaneView {
  private _renderer: PositionPaneRenderer;
  constructor(drawing: PositionDrawing) {
    this._renderer = new PositionPaneRenderer(drawing);
  }
  renderer() { return this._renderer; }
  zOrder(): 'normal' { return 'normal'; }
}

export class PositionDrawing extends BaseDrawing {
  constructor(toolType: 'long_position' | 'short_position', id?: string) {
    super(toolType, { ...defaultPositionStyle }, id);
    this._paneViews = [new PositionPaneView(this)];
  }

  dataToPixel(p: DataPoint): PixelPoint | null {
    if (!this._chart || !this._series) return null;
    return CoordinateUtils.dataPointToPixel(p, this._chart, this._series);
  }

  addPoint(point: DataPoint): boolean {
    this._points.push(point);
    
    // Auto-generate Target and Stop points based on 1-click
    if (this._chart && this._series) {
      const offset = point.price * 0.01; // 1% default target offset
      const stopOffset = offset / 2;     // 0.5% default stop offset (1:2 R/R)

      const tpPrice = this.toolType === 'long_position' ? point.price + offset : point.price - offset;
      const slPrice = this.toolType === 'long_position' ? point.price - stopOffset : point.price + stopOffset;

      const rightLogical = ((point.logical !== undefined ? point.logical : 0) + 15) as Logical;
      
      const rightTime = CoordinateUtils.logicalToTime(rightLogical, this._chart, this._series) || point.time;

      this._points.push({ price: tpPrice, logical: rightLogical, time: rightTime, timeMapped: rightTime });
      this._points.push({ price: slPrice, logical: rightLogical, time: rightTime, timeMapped: rightTime });
    }

    this._state = 'complete';
    this.updateAllViews();
    return true;
  }

  updateTempPoint(point: DataPoint): void {}

  hitTestCustom(pixel: PixelPoint, tolerance: number): HitTestResult | null {
    if (this._points.length < 3) return null;
    
    if (this._selected) {
      const controlPoints = this.getControlPoints();
      for (let i = 0; i < controlPoints.length; i++) {
        if (HitTestUtils.pointToPointDistance(pixel, controlPoints[i]) <= tolerance + 4) {
          return { drawingId: this.id, type: 'point', pointIndex: i, cursor: 'move' };
        }
      }
    }

    const px0 = this.dataToPixel(this._points[0]);
    const px1 = this.dataToPixel(this._points[1]);
    const px2 = this.dataToPixel(this._points[2]);
    if (!px0 || !px1 || !px2) return null;

    const topLeft = { x: Math.min(px0.x, px1.x), y: Math.min(px0.y, px1.y, px2.y) };
    const bottomRight = { x: Math.max(px0.x, px1.x), y: Math.max(px0.y, px1.y, px2.y) };

    if (HitTestUtils.isPointInRect(pixel, topLeft, bottomRight)) {
      return { drawingId: this.id, type: 'body', cursor: 'pointer' };
    }

    return null;
  }

  movePoint(pointIndex: number, newPoint: DataPoint): void {
    const entryPrice = this._points[0].price;
    const isLong = this.toolType === 'long_position';
    
    // Prevent TP/SL from crossing the Entry level
    let safePoint = { ...newPoint };
    if (pointIndex === 1) { // Moving TP
      if (isLong && newPoint.price < entryPrice) safePoint.price = entryPrice;
      if (!isLong && newPoint.price > entryPrice) safePoint.price = entryPrice;
    } else if (pointIndex === 2) { // Moving SL
      if (isLong && newPoint.price > entryPrice) safePoint.price = entryPrice;
      if (!isLong && newPoint.price < entryPrice) safePoint.price = entryPrice;
    }

    super.movePoint(pointIndex, safePoint);
    
    // Keep X axis synced between TP (index 1) and SL (index 2)
    if (pointIndex === 1 && this._points[2]) {
       this._points[2] = { ...this._points[2], time: safePoint.time, logical: safePoint.logical };
    } else if (pointIndex === 2 && this._points[1]) {
       this._points[1] = { ...this._points[1], time: safePoint.time, logical: safePoint.logical };
    }
    
    this.updateAllViews();
  }

  moveAll(dPrice: number, dLogical: number, originalPoints: DataPoint[]): void {
    if (this._locked || !this._chart || !this._series || originalPoints.length < 3) return;
    
    // For Position tool, we must ensure the logical width (X axis) and price diffs (Y axis) stay exactly the same.
    // Instead of computing new logicals independently, we compute the offset for the Entry point (index 0)
    // and apply that exact same offset to TP (1) and SL (2).
    
    const op0 = originalPoints[0];
    const newPrice0 = op0.price + dPrice;
    const newLogical0 = ((op0.logical as number) || 0) + Math.round(dLogical);
    
    const newTime0 = this._chart.timeScale().coordinateToTime(
      this._chart.timeScale().logicalToCoordinate(newLogical0 as Logical) || 0
    );

    this._points[0] = {
      price: newPrice0,
      logical: newLogical0 as Logical,
      time: newTime0 !== null ? (newTime0 as Time) : op0.time
    };

    // Calculate logical width from original points
    const logicalWidth = ((originalPoints[1].logical as number) || 0) - ((op0.logical as number) || 0);
    const newLogicalRight = newLogical0 + logicalWidth;
    
    const newTimeRight = this._chart.timeScale().coordinateToTime(
      this._chart.timeScale().logicalToCoordinate(newLogicalRight as Logical) || 0
    );

    // Apply exact same price offsets
    this._points[1] = {
      price: originalPoints[1].price + dPrice,
      logical: newLogicalRight as Logical,
      time: newTimeRight !== null ? (newTimeRight as Time) : originalPoints[1].time
    };

    this._points[2] = {
      price: originalPoints[2].price + dPrice,
      logical: newLogicalRight as Logical,
      time: newTimeRight !== null ? (newTimeRight as Time) : originalPoints[2].time
    };
    
    this.updateAllViews();
  }
}
