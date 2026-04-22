import { IChartApi, ISeriesApi, ISeriesPrimitive, IPrimitivePaneView, SeriesAttachedParameter, Time, Logical, PrimitiveHoveredItem } from 'lightweight-charts';
import { DataPoint, DrawingToolType, DrawingState, BaseDrawingStyle, HitTestResult, PixelPoint, DrawingSerializedData } from './types';
import { CoordinateUtils } from './coordinate-utils';

export abstract class BaseDrawing implements ISeriesPrimitive<Time> {
  public readonly id: string;
  public readonly toolType: DrawingToolType;
  
  protected _points: DataPoint[] = [];
  protected _tempPoint: DataPoint | null = null;
  protected _style: BaseDrawingStyle;
  protected _state: DrawingState = 'creating';
  protected _visible: boolean = true;
  protected _locked: boolean = false;
  protected _zIndex: number = 0;
  protected _hovered: boolean = false;
  protected _selected: boolean = false;

  protected _chart: IChartApi | null = null;
  protected _series: ISeriesApi<any> | null = null;
  protected _requestUpdate: (() => void) | null = null;

  protected _paneViews: IPrimitivePaneView[] = [];

  constructor(toolType: DrawingToolType, defaultStyle: BaseDrawingStyle, id?: string) {
    this.id = id || crypto.randomUUID();
    this.toolType = toolType;
    this._style = defaultStyle;
  }

  attached(param: SeriesAttachedParameter<Time>): void {
    this._chart = param.chart;
    this._series = param.series;
    this._requestUpdate = param.requestUpdate;
    this.updateAllViews();
  }

  detached(): void {
    this._chart = null;
    this._series = null;
    this._requestUpdate = null;
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return this._paneViews;
  }

  updateAllViews(): void {
    if (this._requestUpdate) {
      this._requestUpdate();
    } else if (this._series) {
      // Fallback: If requestUpdate is not available, trigger a redraw by applying an invisible option
      this._series.applyOptions({ priceScaleId: this._series.options().priceScaleId });
    }
  }

  syncLogicals(chart: IChartApi, series: ISeriesApi<any>) {
    this._points.forEach(p => {
      const t = (p.timeMapped ?? p.time) as any;
      if (t !== null && t !== undefined) {
        const logical = CoordinateUtils.timeToLogical(t, chart, series);
        if (logical !== null) {
          p.logical = logical;
        }
      }
    });
    this.updateAllViews();
  }

  getPoints(): readonly DataPoint[] {
    return this._points;
  }

  get state(): DrawingState { return this._state; }
  get hovered(): boolean { return this._hovered; }
  get selected(): boolean { return this._selected; }

  /**
   * Add a new point to the drawing.
   * @returns true if drawing is complete, false if more points are needed
   */
  abstract addPoint(point: DataPoint): boolean;
  abstract updateTempPoint(point: DataPoint): void;
  // We rename the custom hitTest method to something else to avoid conflict with ISeriesPrimitive's hitTest
  abstract hitTestCustom(pixel: PixelPoint, tolerance: number): HitTestResult | null;

  hitTest?(x: number, y: number): PrimitiveHoveredItem | null {
    return null;
  }

  // 控制点的像素坐标（选中状态时渲染和拖拽）
  getControlPoints(): PixelPoint[] {
    if (!this._chart || !this._series) return [];
    return this._points
      .map(p => CoordinateUtils.dataPointToPixel(p, this._chart!, this._series!))
      .filter((p): p is PixelPoint => p !== null);
  }

  movePoint(pointIndex: number, newPoint: DataPoint): void {
    if (this._locked || pointIndex < 0 || pointIndex >= this._points.length) return;
    this._points[pointIndex] = newPoint;
    this.updateAllViews();
  }

  moveAll(dPrice: number, dLogical: number, originalPoints: DataPoint[]): void {
    if (this._locked || !this._chart || !this._series) return;
    
    // Check boundaries before applying move
    let minLogical = Infinity;
    let maxLogical = -Infinity;
    
    // 更新每个锚点的位置
    for (let i = 0; i < this._points.length; i++) {
      if (!originalPoints[i]) continue;
      const op = originalPoints[i];
      let newLogical = ((op.logical as number) || 0) + dLogical;
      
      // Prevent logical index from going into completely invalid areas (e.g., negative indices far before first bar)
      // Usually index 0 is the first bar. We allow some buffer.
      if (newLogical < -100) newLogical = -100;
      
      const newPrice = op.price + dPrice;
      
      // 用 logical 推导 time（支持 future 空白区）
      const newTime = CoordinateUtils.logicalToTime(newLogical as Logical, this._chart, this._series);

      this._points[i] = {
        price: newPrice,
        logical: newLogical as Logical,
        time: newTime !== null ? (newTime as Time) : op.time,
        timeMapped: newTime !== null ? (newTime as Time) : (op.timeMapped ?? op.time),
      };
    }
    
    this.updateAllViews();
  }

  select(): void {
    this._selected = true;
    this._state = 'selected';
    this.updateAllViews();
  }

  deselect(): void {
    this._selected = false;
    this._state = 'complete';
    this.updateAllViews();
  }

  setHovered(hovered: boolean): void {
    if (this._hovered !== hovered) {
      this._hovered = hovered;
      this.updateAllViews();
    }
  }

  getStyle(): Readonly<BaseDrawingStyle> {
    return this._style;
  }

  updateStyle(style: Partial<BaseDrawingStyle>): void {
    this._style = { ...this._style, ...style };
    this.updateAllViews();
  }

  serialize(): DrawingSerializedData {
    return {
      id: this.id,
      toolType: this.toolType,
      points: [...this._points],
      style: { ...this._style },
      visible: this._visible,
      locked: this._locked,
      zIndex: this._zIndex,
      createdAt: Date.now()
    };
  }

  deserialize(data: DrawingSerializedData): void {
    this._points = [...data.points];
    // 兼容旧数据：缺少 timeMapped 的，默认使用 time
    this._points = this._points.map(p => ({ ...p, timeMapped: (p as any).timeMapped ?? p.time }));
    this._style = { ...this._style, ...data.style };
    this._visible = data.visible;
    this._locked = data.locked;
    this._zIndex = data.zIndex;
    this._state = 'complete'; // Load as complete
    this.updateAllViews();
  }
}
