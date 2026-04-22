import { IPrimitivePaneView, Time } from 'lightweight-charts';
import { CanvasRenderingTarget2D } from 'fancy-canvas';
import { BaseDrawing } from '../core/base-drawing';
import { DataPoint, HitTestResult, PixelPoint, BaseDrawingStyle } from '../core/types';
import { HitTestUtils } from '../core/hit-test';
import { CoordinateUtils } from '../core/coordinate-utils';

export interface TrendlineStyle extends BaseDrawingStyle {
  extendLeft?: boolean;
  extendRight?: boolean;
}

export const defaultTrendlineStyle: TrendlineStyle = {
  lineColor: '#2962FF',
  lineWidth: 2,
  lineStyle: 'solid',
  extendLeft: false,
  extendRight: false
};

class TrendlinePaneRenderer {
  constructor(private _drawing: TrendlineDrawing) {}

  draw(target: CanvasRenderingTarget2D): void {
    const points = this._drawing.getPoints();
    const style = this._drawing.getStyle() as TrendlineStyle;
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
      ctx.strokeStyle = style.lineColor;
      ctx.lineWidth = style.lineWidth;
      if (style.lineStyle === 'dashed') ctx.setLineDash([5, 5]);
      else if (style.lineStyle === 'dotted') ctx.setLineDash([2, 2]);

      ctx.beginPath();
      
      let drawP1 = { ...px1 };
      let drawP2 = { ...px2 };
      
      if (style.extendLeft || style.extendRight) {
        const dx = px2.x - px1.x;
        const dy = px2.y - px1.y;
        
        if (dx !== 0 || dy !== 0) {
          if (style.extendLeft) {
             const t = -px1.x / dx;
             drawP1 = { x: 0, y: px1.y + t * dy };
          }
          if (style.extendRight) {
             const t = (scope.mediaSize.width - px2.x) / dx;
             drawP2 = { x: scope.mediaSize.width, y: px2.y + t * dy };
          }
        }
      }

      ctx.moveTo(drawP1.x, drawP1.y);
      ctx.lineTo(drawP2.x, drawP2.y);
      ctx.stroke();

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

class TrendlinePaneView implements IPrimitivePaneView {
  private _renderer: TrendlinePaneRenderer;
  constructor(drawing: TrendlineDrawing) {
    this._renderer = new TrendlinePaneRenderer(drawing);
  }
  renderer() { return this._renderer; }
  zOrder(): 'normal' { return 'normal'; }
}

export class TrendlineDrawing extends BaseDrawing {
  constructor(id?: string) {
    super('trendline', { ...defaultTrendlineStyle }, id);
    this._paneViews = [new TrendlinePaneView(this)];
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

    const style = this._style as TrendlineStyle;
    let checkP1 = { ...px1 };
    let checkP2 = { ...px2 };
    
    if (style.extendLeft || style.extendRight) {
       const dx = px2.x - px1.x;
       const dy = px2.y - px1.y;
       if (dx !== 0 || dy !== 0) {
         if (style.extendLeft) {
            checkP1 = { x: -10000, y: px1.y + (-10000 - px1.x)/dx * dy };
         }
         if (style.extendRight) {
            checkP2 = { x: 10000, y: px2.y + (10000 - px2.x)/dx * dy };
         }
       }
    }

    const dist = HitTestUtils.pointToSegmentDistance(pixel, checkP1, checkP2);
    if (dist <= tolerance) {
      return { drawingId: this.id, type: 'body', cursor: 'pointer' };
    }

    return null;
  }
}
