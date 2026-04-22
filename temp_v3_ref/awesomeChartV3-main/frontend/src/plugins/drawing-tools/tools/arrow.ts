import { IPrimitivePaneView } from 'lightweight-charts';
import { CanvasRenderingTarget2D } from 'fancy-canvas';
import { BaseDrawing } from '../core/base-drawing';
import { DataPoint, HitTestResult, PixelPoint, BaseDrawingStyle } from '../core/types';
import { HitTestUtils } from '../core/hit-test';
import { CoordinateUtils } from '../core/coordinate-utils';

export interface ArrowStyle extends BaseDrawingStyle {
  arrowSize?: number;
}

export const defaultArrowStyle: ArrowStyle = {
  lineColor: '#FF5252',
  lineWidth: 2,
  lineStyle: 'solid',
  arrowSize: 12
};

class ArrowPaneRenderer {
  constructor(private _drawing: ArrowDrawing) {}

  draw(target: CanvasRenderingTarget2D): void {
    const points = this._drawing.getPoints();
    const style = this._drawing.getStyle() as ArrowStyle;
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
      ctx.fillStyle = style.lineColor;
      ctx.lineWidth = style.lineWidth;
      
      if (style.lineStyle === 'dashed') ctx.setLineDash([5, 5]);
      else if (style.lineStyle === 'dotted') ctx.setLineDash([2, 2]);

      // Draw the line
      ctx.beginPath();
      ctx.moveTo(px1.x, px1.y);
      ctx.lineTo(px2.x, px2.y);
      ctx.stroke();

      // Draw the arrow head at p2
      ctx.setLineDash([]);
      const angle = Math.atan2(px2.y - px1.y, px2.x - px1.x);
      const size = style.arrowSize || 12;
      
      ctx.beginPath();
      ctx.moveTo(px2.x, px2.y);
      ctx.lineTo(
        px2.x - size * Math.cos(angle - Math.PI / 6),
        px2.y - size * Math.sin(angle - Math.PI / 6)
      );
      ctx.lineTo(
        px2.x - size * Math.cos(angle + Math.PI / 6),
        px2.y - size * Math.sin(angle + Math.PI / 6)
      );
      ctx.closePath();
      ctx.fill();

      // Draw control points if selected or hovered
      if (this._drawing.selected || this._drawing.hovered) {
        const controlPoints = this._drawing.getControlPoints();
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

class ArrowPaneView implements IPrimitivePaneView {
  private _renderer: ArrowPaneRenderer;
  constructor(drawing: ArrowDrawing) {
    this._renderer = new ArrowPaneRenderer(drawing);
  }
  renderer() { return this._renderer; }
  zOrder(): 'normal' { return 'normal'; }
}

export class ArrowDrawing extends BaseDrawing {
  constructor(id?: string) {
    super('arrow', { ...defaultArrowStyle }, id);
    this._paneViews = [new ArrowPaneView(this)];
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

    const dist = HitTestUtils.pointToSegmentDistance(pixel, px1, px2);
    if (dist <= tolerance) {
      return { drawingId: this.id, type: 'body', cursor: 'pointer' };
    }

    return null;
  }
}
