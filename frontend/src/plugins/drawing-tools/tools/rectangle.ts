import { IPrimitivePaneView } from 'lightweight-charts';
import { CanvasRenderingTarget2D } from 'fancy-canvas';
import { BaseDrawing } from '../core/base-drawing';
import { DataPoint, HitTestResult, PixelPoint, BaseDrawingStyle } from '../core/types';
import { HitTestUtils } from '../core/hit-test';
import { CoordinateUtils } from '../core/coordinate-utils';

export interface RectangleStyle extends BaseDrawingStyle {
  fillColor: string;
  fillOpacity: number;
}

export const defaultRectangleStyle: RectangleStyle = {
  lineColor: '#2962FF',
  lineWidth: 2,
  lineStyle: 'solid',
  fillColor: '#2962FF',
  fillOpacity: 0.2
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

class RectanglePaneRenderer {
  constructor(private _drawing: RectangleDrawing) {}

  draw(target: CanvasRenderingTarget2D): void {
    const points = this._drawing.getPoints();
    const style = this._drawing.getStyle() as RectangleStyle;
    const tempPoint = this._drawing.getTempPoint();
    
    const p1 = points[0];
    const p2 = points[1] || tempPoint;

    if (!p1 || !p2) return;

    const px1 = this._drawing.dataToPixel(p1);
    const px2 = this._drawing.dataToPixel(p2);

    if (!px1 || !px2) return;

    target.useMediaCoordinateSpace((scope) => {
      const ctx = scope.context;
      ctx.save();
      
      const x = Math.min(px1.x, px2.x);
      const y = Math.min(px1.y, px2.y);
      const w = Math.abs(px2.x - px1.x);
      const h = Math.abs(px2.y - px1.y);

      // Fill
      ctx.fillStyle = applyOpacity(style.fillColor, style.fillOpacity);
      ctx.fillRect(x, y, w, h);

      // Border
      ctx.strokeStyle = style.lineColor;
      ctx.lineWidth = style.lineWidth;
      if (style.lineStyle === 'dashed') ctx.setLineDash([5, 5]);
      else if (style.lineStyle === 'dotted') ctx.setLineDash([2, 2]);
      ctx.strokeRect(x, y, w, h);

      // Control points
      if (this._drawing.selected || this._drawing.hovered) {
        const controlPoints = this._drawing.getControlPoints();
        ctx.fillStyle = '#ffffff';
        ctx.setLineDash([]);
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

class RectanglePaneView implements IPrimitivePaneView {
  private _renderer: RectanglePaneRenderer;
  constructor(drawing: RectangleDrawing) {
    this._renderer = new RectanglePaneRenderer(drawing);
  }
  renderer() { return this._renderer; }
  zOrder(): 'normal' { return 'normal'; }
}

export class RectangleDrawing extends BaseDrawing {
  constructor(id?: string) {
    super('rectangle', { ...defaultRectangleStyle }, id);
    this._paneViews = [new RectanglePaneView(this)];
  }

  getTempPoint() { return this._tempPoint; }

  dataToPixel(p: DataPoint): PixelPoint | null {
    if (!this._chart || !this._series) return null;
    return CoordinateUtils.dataPointToPixel(p, this._chart, this._series);
  }

  addPoint(point: DataPoint): boolean {
    this._points.push(point);
    if (this._points.length >= 2) {
      this._tempPoint = null;
      this._state = 'complete';
      this.updateAllViews();
      return true;
    }
    this.updateAllViews();
    return false;
  }

  updateTempPoint(point: DataPoint): void {
    if (this._points.length === 1) {
      this._tempPoint = point;
      this.updateAllViews();
    }
  }

  hitTestCustom(pixel: PixelPoint, tolerance: number): HitTestResult | null {
    if (this._points.length < 2) return null;
    
    if (this._selected) {
      const controlPoints = this.getControlPoints();
      for (let i = 0; i < controlPoints.length; i++) {
        if (HitTestUtils.pointToPointDistance(pixel, controlPoints[i]) <= tolerance + 4) {
          return { drawingId: this.id, type: 'point', pointIndex: i, cursor: 'move' };
        }
      }
    }

    const px1 = this.dataToPixel(this._points[0]);
    const px2 = this.dataToPixel(this._points[1]);
    if (!px1 || !px2) return null;

    if (HitTestUtils.isPointInRect(pixel, px1, px2)) {
      return { drawingId: this.id, type: 'body', cursor: 'pointer' };
    }

    return null;
  }
}
