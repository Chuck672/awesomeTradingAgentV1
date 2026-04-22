import { IPrimitivePaneView } from 'lightweight-charts';
import { CanvasRenderingTarget2D } from 'fancy-canvas';
import { BaseDrawing } from '../core/base-drawing';
import { DataPoint, HitTestResult, PixelPoint, BaseDrawingStyle } from '../core/types';
import { HitTestUtils } from '../core/hit-test';
import { CoordinateUtils } from '../core/coordinate-utils';

export const defaultHorizontalLineStyle: BaseDrawingStyle = {
  lineColor: '#00BCD4',
  lineWidth: 2,
  lineStyle: 'solid'
};

class HorizontalLinePaneRenderer {
  constructor(private _drawing: HorizontalLineDrawing) {}

  draw(target: CanvasRenderingTarget2D): void {
    const points = this._drawing.getPoints();
    const style = this._drawing.getStyle();
    
    const p1 = points[0];
    if (!p1) return;

    const px1 = this._drawing.dataToPixel(p1);
    if (!px1) return;

    target.useMediaCoordinateSpace((scope) => {
      const ctx = scope.context;
      ctx.save();
      ctx.strokeStyle = style.lineColor;
      ctx.lineWidth = style.lineWidth;
      
      if (style.lineStyle === 'dashed') ctx.setLineDash([5, 5]);
      else if (style.lineStyle === 'dotted') ctx.setLineDash([2, 2]);

      ctx.beginPath();
      ctx.moveTo(0, px1.y);
      ctx.lineTo(scope.mediaSize.width, px1.y);
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

class HorizontalLinePaneView implements IPrimitivePaneView {
  private _renderer: HorizontalLinePaneRenderer;
  constructor(drawing: HorizontalLineDrawing) {
    this._renderer = new HorizontalLinePaneRenderer(drawing);
  }
  renderer() { return this._renderer; }
  zOrder(): 'normal' { return 'normal'; }
}

export class HorizontalLineDrawing extends BaseDrawing {
  constructor(id?: string) {
    super('horizontal_line', { ...defaultHorizontalLineStyle }, id);
    this._paneViews = [new HorizontalLinePaneView(this)];
  }

  dataToPixel(p: DataPoint): PixelPoint | null {
    if (!this._chart || !this._series) return null;
    return CoordinateUtils.dataPointToPixel(p, this._chart, this._series);
  }

  addPoint(point: DataPoint): boolean {
    // Horizontal Line only needs 1 point
    this._points.push(point);
    this._state = 'complete';
    this.updateAllViews();
    return true;
  }

  updateTempPoint(point: DataPoint): void {
    // No temp point needed for 1-click drawing
  }

  hitTestCustom(pixel: PixelPoint, tolerance: number): HitTestResult | null {
    if (this._points.length < 1) return null;
    
    if (this._selected) {
      const controlPoints = this.getControlPoints();
      for (let i = 0; i < controlPoints.length; i++) {
        if (HitTestUtils.pointToPointDistance(pixel, controlPoints[i]) <= tolerance + 4) {
          return { drawingId: this.id, type: 'point', pointIndex: i, cursor: 'move' };
        }
      }
    }

    const px1 = this.dataToPixel(this._points[0]);
    if (!px1) return null;

    const dist = HitTestUtils.pointToHorizontalLineDistance(pixel, px1.y);
    if (dist <= tolerance) {
      return { drawingId: this.id, type: 'body', cursor: 'pointer' };
    }

    return null;
  }
  
  // Override moveAll because horizontal line only cares about Y (price) movement
  moveAll(dPrice: number, dLogical: number, originalPoints: DataPoint[]): void {
    if (this._locked || !this._chart || !this._series) return;
    
    if (originalPoints.length > 0) {
      const op = originalPoints[0];
      const newPrice = op.price + dPrice;
      // We don't move X for horizontal line body drag, keep original time
      this._points[0] = {
        ...this._points[0],
        price: newPrice,
      };
      this.updateAllViews();
    }
  }
}
