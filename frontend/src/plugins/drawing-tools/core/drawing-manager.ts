import { IChartApi, ISeriesApi, Logical, Time } from 'lightweight-charts';
import { BaseDrawing } from './base-drawing';
import { DrawingToolType, InteractionMode, DataPoint, PixelPoint, DrawingEventHandler, DrawingEvent, DrawingSerializedData, BaseDrawingStyle } from './types';
import { CoordinateUtils } from './coordinate-utils';

function timeframeToSec(tf: string): number {
  const t = (tf || '').toUpperCase();
  if (t === 'M1') return 60;
  if (t === 'M5') return 300;
  if (t === 'M15') return 900;
  if (t === 'M30') return 1800;
  if (t === 'H1') return 3600;
  if (t === 'H4') return 14400;
  if (t === 'D1') return 86400;
  if (t === 'W1') return 604800;
  // 月线不严格，用 30 天近似（仅用于 floor）
  if (t === 'MN1') return 2592000;
  return 60;
}

function toUnixSeconds(t: Time): number {
  return typeof t === 'number' ? t : new Date(t as string).getTime() / 1000;
}

function floorToTfSec(ts: number, tfSec: number): number {
  if (!tfSec || tfSec <= 0) return ts;
  return Math.floor(ts / tfSec) * tfSec;
}

function nearestBarTimeLte(times: number[], target: number): number | null {
  // times 升序
  if (times.length === 0) return null;
  if (target <= times[0]) return times[0];
  if (target >= times[times.length - 1]) return times[times.length - 1];
  let lo = 0;
  let hi = times.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    const v = times[mid];
    if (v === target) return v;
    if (v < target) lo = mid + 1;
    else hi = mid - 1;
  }
  // hi 是最后一个 < target
  return times[Math.max(0, hi)];
}

function nearestBarTime(times: number[], target: number): number | null {
  if (times.length === 0) return null;
  if (target <= times[0]) return times[0];
  if (target >= times[times.length - 1]) return times[times.length - 1];
  let lo = 0;
  let hi = times.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    const v = times[mid];
    if (v === target) return v;
    if (v < target) lo = mid + 1;
    else hi = mid - 1;
  }
  const right = Math.min(times.length - 1, lo);
  const left = Math.max(0, hi);
  return Math.abs(times[left] - target) <= Math.abs(times[right] - target) ? times[left] : times[right];
}

export class DrawingManager {
  private _chart: IChartApi;
  private _series: ISeriesApi<any>;
  private _container: HTMLElement;

  private _drawings: Map<string, BaseDrawing> = new Map();
  private _mode: InteractionMode = 'idle';
  private _activeTool: DrawingToolType = 'cursor';
  private _selectedDrawing: BaseDrawing | null = null;
  private _hoveredDrawing: BaseDrawing | null = null;
  private _creatingDrawing: BaseDrawing | null = null;

  private _isDragging: boolean = false;
  private _dragTarget: BaseDrawing | null = null;
  private _dragPointIndex: number | null = null;
  private _dragStartPixel: PixelPoint | null = null;
  private _dragStartPoints: DataPoint[] | null = null;

  private _eventListeners: DrawingEventHandler[] = [];
  
  // Store custom default styles per tool type
  private _customDefaultStyles: Map<DrawingToolType, BaseDrawingStyle> = new Map();

  // Factory function to create drawings
  private _drawingFactory: (toolType: DrawingToolType, id?: string) => BaseDrawing | null;

  // 当前图表周期（用于跨周期 remap + future keep）
  private _timeframe: string = 'M1';
  private _tfSec: number = timeframeToSec('M1');

  constructor(
    chart: IChartApi, 
    series: ISeriesApi<any>, 
    container: HTMLElement,
    drawingFactory: (toolType: DrawingToolType, id?: string) => BaseDrawing | null
  ) {
    this._chart = chart;
    this._series = series;
    this._container = container;
    this._drawingFactory = drawingFactory;

    this._bindEvents();
  }

  /**
   * 由外部（SingleChart）在 timeframe 变化时调用。
   * 注意：DrawingManager 本身不会重建，所以必须更新 tfSec。
   */
  public setTimeframe(timeframe: string) {
    const tf = (timeframe || 'M1').toUpperCase();
    this._timeframe = tf;
    this._tfSec = timeframeToSec(tf);
  }

  private _getSeriesTimes(): number[] {
    const data = this._series.data();
    if (!data || data.length === 0) return [];
    return data.map((d: any) => toUnixSeconds(d.time as Time));
  }

  /**
   * 对一个 DataPoint 做时间标准化：
   * - 历史点（<= lastBarTime）：time floor 到 tfSec，然后映射到当前周期已有 bar time（优先 lte）
   * - 未来点（> lastBarTime）：keep_future，time=floor 到 tfSec，不强行映射到 bar
   */
  private _normalizePoint(p: DataPoint): DataPoint {
    const times = this._getSeriesTimes();
    if (!times.length) return p;
    const lastBarTime = times[times.length - 1];
    const ts0 = toUnixSeconds(p.time as Time); // 注意：这里用“锚点 time”，避免跨周期来回 remap 造成漂移
    const floored = floorToTfSec(ts0, this._tfSec);

    let mapped = floored;
    if (floored <= lastBarTime) {
      // 用 lte 更符合“不要把历史点推到未来”的直觉；缺口由 lte 吸附处理
      mapped = nearestBarTimeLte(times, floored) ?? floored;
    } else {
      // keep future
      mapped = floored;
    }

    const out: DataPoint = { ...p, time: p.time, timeMapped: mapped as any };
    const lg = CoordinateUtils.timeToLogical(out.timeMapped as any, this._chart, this._series);
    if (lg !== null) out.logical = lg as any;
    return out;
  }

  /**
   * 跨周期重映射：对所有 drawings 的 points 执行 normalize（历史点映射到 bar，未来点 keep）。
   * 建议在 timeframe 切换 + 新数据 setData 后调用一次。
   */
  public remapAllForTimeframe(): void {
    const times = this._getSeriesTimes();
    if (!times.length) return;
    this._drawings.forEach((d) => {
      const pts = d.getPoints().map((p) => this._normalizePoint(p));
      // 通过 movePoint 批量写回
      pts.forEach((p, i) => d.movePoint(i, p));
    });
  }

  public get activeTool() { return this._activeTool; }
  
  public set activeTool(tool: DrawingToolType) {
    if (this._activeTool === tool) return;
    this._activeTool = tool;
    if (tool !== 'cursor') {
      this._mode = 'placing';
      this.deselectAll();
    } else {
      this._mode = 'idle';
      if (this._creatingDrawing) {
        this.removeDrawing(this._creatingDrawing.id);
        this._creatingDrawing = null;
      }
    }
    this._dispatchEvent({ type: 'toolChanged', toolType: tool });
  }

  public get selectedDrawing() { return this._selectedDrawing; }
  
  public addEventListener(handler: DrawingEventHandler) {
    this._eventListeners.push(handler);
  }

  public removeEventListener(handler: DrawingEventHandler) {
    this._eventListeners = this._eventListeners.filter(h => h !== handler);
  }

  private _dispatchEvent(event: DrawingEvent) {
    this._eventListeners.forEach(handler => handler(event));
  }

  public addDrawing(drawing: BaseDrawing) {
    this._drawings.set(drawing.id, drawing);
    this._series.attachPrimitive(drawing);
    this._dispatchEvent({ type: 'created', drawingId: drawing.id });
  }

  public updateDefaultStyle(toolType: DrawingToolType, style: BaseDrawingStyle) {
    this._customDefaultStyles.set(toolType, { ...style });
  }

  public removeDrawing(id: string) {
    const drawing = this._drawings.get(id);
    if (drawing) {
      if (this._selectedDrawing === drawing) this._selectedDrawing = null;
      if (this._hoveredDrawing === drawing) this._hoveredDrawing = null;
      if (this._creatingDrawing === drawing) this._creatingDrawing = null;
      
      this._series.detachPrimitive(drawing);
      this._drawings.delete(id);
      this._dispatchEvent({ type: 'deleted', drawingId: id });
    }
  }

  public deselectAll() {
    if (this._selectedDrawing) {
      const id = this._selectedDrawing.id;
      this._selectedDrawing.deselect();
      this._selectedDrawing = null;
      this._dispatchEvent({ type: 'deselected', drawingId: id });
    }
  }

  public removeAllDrawings() {
    this.deselectAll();
    const ids = Array.from(this._drawings.keys());
    ids.forEach(id => {
      this.removeDrawing(id);
    });
  }

  public destroy() {
    this._unbindEvents();
    this._drawings.forEach(d => this._series.detachPrimitive(d));
    this._drawings.clear();
  }

  public serialize(): DrawingSerializedData[] {
    return Array.from(this._drawings.values()).map(d => d.serialize());
  }

  public serializeDefaultStyles(): Record<string, BaseDrawingStyle> {
    const obj: Record<string, BaseDrawingStyle> = {};
    this._customDefaultStyles.forEach((style, key) => {
      obj[key] = style;
    });
    return obj;
  }

  public deserializeDefaultStyles(data: Record<string, BaseDrawingStyle>) {
    if (!data) return;
    Object.keys(data).forEach(key => {
      this._customDefaultStyles.set(key as DrawingToolType, data[key]);
    });
  }

  public deserialize(data: DrawingSerializedData[]) {
    this._drawings.forEach(d => this._series.detachPrimitive(d));
    this._drawings.clear();

    data.forEach(serialized => {
      const drawing = this._drawingFactory(serialized.toolType, serialized.id);
      if (drawing) {
        drawing.deserialize(serialized);
        drawing.syncLogicals(this._chart, this._series);
        this._drawings.set(drawing.id, drawing);
        this._series.attachPrimitive(drawing);
      }
    });
  }

  public syncLogicalsWithTime() {
    this._drawings.forEach(d => d.syncLogicals(this._chart, this._series));
  }

  private _lastClickTime: number = 0;
  private _lastClickPixel: PixelPoint | null = null;

  // Use arrow functions to permanently bind `this` and keep a stable reference
  private _onMouseDown = (event: MouseEvent) => {
    const pixel = this._getMousePixel(event);
    const dp0 = CoordinateUtils.pixelToDataPoint(pixel, this._chart, this._series);
    const dataPoint = dp0 ? this._normalizePoint(dp0) : null;
    if (!dataPoint) return;

    if (this._mode === 'placing') {
      event.stopPropagation();
      event.preventDefault();

      if (!this._creatingDrawing) {
        this._creatingDrawing = this._drawingFactory(this._activeTool);
        if (this._creatingDrawing) {
          // Apply custom default style if it exists
          const customStyle = this._customDefaultStyles.get(this._activeTool);
          if (customStyle) {
            this._creatingDrawing.updateStyle(customStyle);
          }

          this._drawings.set(this._creatingDrawing.id, this._creatingDrawing);
          this._series.attachPrimitive(this._creatingDrawing);
        }
      }

      if (this._creatingDrawing) {
        const isComplete = this._creatingDrawing.addPoint(dataPoint);
        if (isComplete) {
          const completedDrawing = this._creatingDrawing;
          this._creatingDrawing = null;
          this.activeTool = 'cursor'; // this will change mode to idle
          
          this.deselectAll();
          completedDrawing.select();
          this._selectedDrawing = completedDrawing;
          
          this._dispatchEvent({ type: 'created', drawingId: completedDrawing.id });
          this._dispatchEvent({ type: 'selected', drawingId: completedDrawing.id });
        }
      }
      return;
    }

    // Hit Testing for Selection and Dragging
    let hitResult = null;
    let hitDrawing = null;

    // Check selected drawing first for control points
    if (this._selectedDrawing) {
      hitResult = this._selectedDrawing.hitTestCustom(pixel, 8);
      if (hitResult) hitDrawing = this._selectedDrawing;
    }

    // Check others if nothing hit yet
    if (!hitResult) {
      for (const drawing of Array.from(this._drawings.values()).reverse()) {
        if (drawing === this._selectedDrawing) continue;
        const result = drawing.hitTestCustom(pixel, 5);
        if (result) {
          hitResult = result;
          hitDrawing = drawing;
          break;
        }
      }
    }

    if (hitResult && hitDrawing) {
      // First, handle the double click check
      const now = Date.now();
      const isDoubleClick = (now - this._lastClickTime < 300) && 
        this._lastClickPixel && 
        Math.abs(pixel.x - this._lastClickPixel.x) < 5 && 
        Math.abs(pixel.y - this._lastClickPixel.y) < 5;

      this._lastClickTime = now;
      this._lastClickPixel = pixel;

      if (isDoubleClick) {
        event.stopPropagation();
        event.preventDefault();
        
        if (this._selectedDrawing !== hitDrawing) {
           this.deselectAll();
           hitDrawing.select();
           this._selectedDrawing = hitDrawing;
           this._dispatchEvent({ type: 'selected', drawingId: hitDrawing.id });
        }
        this._dispatchEvent({ type: 'doubleClicked', drawingId: hitDrawing.id });
        return;
      }

      // Single click processing
      
      // Only stop propagation if we are clicking on a control point or 
      // if we are clicking on an ALREADY selected drawing (to drag it).
      // If we are selecting a NEW drawing, we stop propagation to select it,
      // but we shouldn't block the initial click.
      event.stopPropagation();
      event.preventDefault();

      if (this._selectedDrawing !== hitDrawing) {
        this.deselectAll();
        hitDrawing.select();
        this._selectedDrawing = hitDrawing;
        this._dispatchEvent({ type: 'selected', drawingId: hitDrawing.id });
        
        // Re-evaluate hitResult after selecting, because now control points might be available
        hitResult = hitDrawing.hitTestCustom(pixel, 8);
      }

      // Enter dragging mode
      this._dragTarget = hitDrawing;
      this._dragPointIndex = hitResult && hitResult.type === 'point' ? hitResult.pointIndex! : null;
      this._dragStartPixel = pixel;
      this._dragStartPoints = hitDrawing.getPoints().map(p => ({ ...p }));
      
      this._isDragging = true;
      this._mode = 'dragging';
      
      return;
    }

    // Clicked on empty space
    if (this._selectedDrawing) {
      this.deselectAll();
    }
    
    // Clear last click pixel when clicking on empty space to avoid accidental double clicks across different areas
    this._lastClickPixel = null;
    
    // If we click on empty space, we are not dragging any drawing
    this._mode = 'idle';
  };

  private _onMouseMove = (event: MouseEvent) => {
    const pixel = this._getMousePixel(event);
    const dp0 = CoordinateUtils.pixelToDataPoint(pixel, this._chart, this._series);
    const dataPoint = dp0 ? this._normalizePoint(dp0) : null;

    if (this._mode === 'placing' && this._creatingDrawing && dataPoint) {
      this._creatingDrawing.updateTempPoint(dataPoint);
      // Do not stop propagation here so crosshair follows mouse during placing
      return;
    }

    if (this._mode === 'dragging' && this._dragTarget && this._dragStartPixel && this._dragStartPoints && dataPoint) {
      // Allow lightweight-charts to handle mouse move internally if it's position tool
      // But we still want to prevent panning.
      // So we prevent default but do NOT stop propagation if we want crosshair to update.
      // Actually, lightweight-charts crosshair update relies on the mousemove event on the container.
      // Since we use capture: true, stopping propagation prevents the chart from seeing the mousemove.
      // To fix the crosshair issue while dragging, we should only stop propagation for panning (which is handled by mousedown/mousemove on the chart pane).
      // However, if we don't stop propagation, the chart might pan.
      // Let's stop propagation but manually trigger crosshair update if needed, OR we can let it propagate but disable scrolling?
      // LWC disables scrolling if we preventDefault? No.
      // We can just not stop propagation for mousemove during drag, BUT that might cause panning if the user is dragging.
      // Let's test just removing stopPropagation for mousemove during dragging. Wait, if we remove it, the chart will pan because mousedown was stopped? No, if mousedown propagation was stopped, LWC didn't start a drag/pan operation. So mousemove propagation won't cause panning!
      // Let's try removing event.stopPropagation() here.
      // event.stopPropagation();
      event.preventDefault();

      if (this._dragPointIndex !== null) {
        // Move single point
        this._dragTarget.movePoint(this._dragPointIndex, dataPoint);
      } else {
        // Move whole drawing
        // Calculate delta in price and logical space
        const s0 = CoordinateUtils.pixelToDataPoint(this._dragStartPixel, this._chart, this._series);
        const startDataPoint = s0 ? this._normalizePoint(s0) : null;
        if (startDataPoint) {
          const dPrice = dataPoint.price - startDataPoint.price;
          const dLogical = (dataPoint.logical as number || 0) - ((startDataPoint.logical as number) || 0);
          
          this._dragTarget.moveAll(dPrice, dLogical, this._dragStartPoints);
        }
      }
      this._dispatchEvent({ type: 'modified', drawingId: this._dragTarget.id });
      return;
    }

    // Hover state and cursors
    if (this._mode === 'idle' || this._mode === 'hovering') {
      let hovered = null;
      let cursor = 'default';

      if (this._selectedDrawing) {
        const result = this._selectedDrawing.hitTestCustom(pixel, 8);
        if (result) {
          hovered = this._selectedDrawing;
          cursor = result.cursor;
        }
      }

      if (!hovered) {
        for (const drawing of Array.from(this._drawings.values()).reverse()) {
          const result = drawing.hitTestCustom(pixel, 5);
          if (result) {
            hovered = drawing;
            cursor = result.cursor;
            break;
          }
        }
      }

      if (hovered !== this._hoveredDrawing) {
        if (this._hoveredDrawing) this._hoveredDrawing.setHovered(false);
        if (hovered) hovered.setHovered(true);
        this._hoveredDrawing = hovered;
      }

      if (hovered) {
        this._mode = 'hovering';
        this._container.style.cursor = cursor;
      } else {
        this._mode = 'idle';
        this._container.style.cursor = 'crosshair'; // default chart cursor
      }
    } else if (this._mode === 'placing') {
       this._container.style.cursor = 'crosshair';
    }
  };

  private _onMouseUp = (event: MouseEvent) => {
    if (this._mode === 'dragging') {
      event.stopPropagation();
      event.preventDefault();
      
      this._isDragging = false;
      this._mode = 'selected'; // Return to selected mode after drag
      this._dragTarget = null;
      this._dragPointIndex = null;
      this._dragStartPixel = null;
      this._dragStartPoints = null;
    }
  };

  private _onKeyDown = (event: KeyboardEvent) => {
    if (event.key === 'Escape') {
      if (this._mode === 'placing') {
        this.activeTool = 'cursor'; // will cancel creating drawing
      } else if (this._selectedDrawing) {
        this.deselectAll();
      }
    } else if (event.key === 'Delete' || event.key === 'Backspace') {
      if (this._selectedDrawing) {
        this.removeDrawing(this._selectedDrawing.id);
      }
    }
  };

  private _getMousePixel(event: MouseEvent): PixelPoint {
    const rect = this._container.getBoundingClientRect();
    return {
      x: event.clientX - rect.left,
      y: event.clientY - rect.top
    };
  }

  private _bindEvents() {
    this._container.addEventListener('mousedown', this._onMouseDown, { capture: true });
    this._container.addEventListener('mousemove', this._onMouseMove, { capture: true });
    this._container.addEventListener('mouseup', this._onMouseUp, { capture: true });
    document.addEventListener('keydown', this._onKeyDown);
  }

  private _unbindEvents() {
    this._container.removeEventListener('mousedown', this._onMouseDown, { capture: true });
    this._container.removeEventListener('mousemove', this._onMouseMove, { capture: true });
    this._container.removeEventListener('mouseup', this._onMouseUp, { capture: true });
    document.removeEventListener('keydown', this._onKeyDown);
  }
}
