import { Time, Logical } from 'lightweight-charts';

export interface DataPoint {
  price: number;
  /**
   * 逻辑锚点时间（绝对时间，不应在切换周期时被“破坏性”改写）
   * - 创建/拖拽时更新
   * - 跨周期 remap 时保持不变
   */
  time: Time;
  /**
   * 当前周期用于渲染/吸附的时间（会随 timeframe 改变而重新计算）
   * - 历史点：floor(tfSec) 后映射到目标周期已有 bar time（lte）
   * - 未来点：keep_future + floor(tfSec)，不夹回最后一根 bar
   */
  timeMapped?: Time;
  /**
   * 当前周期用于渲染的 logical（可用于 future extrapolation）
   * 注意：logical 也属于“渲染态”，会随 timeMapped/timeframe 刷新
   */
  logical?: Logical;
}

export interface PixelPoint {
  x: number;
  y: number;
}

export type DrawingToolType = 
  | 'cursor' // 非画图状态，普通的图表交互模式
  | 'arrow' 
  | 'trendline' 
  | 'horizontal_ray' 
  | 'horizontal_line' 
  | 'rectangle' 
  | 'long_position' 
  | 'short_position' 
  | 'measure';

export type InteractionMode = 'idle' | 'placing' | 'selected' | 'dragging' | 'hovering';
export type DrawingState = 'creating' | 'complete' | 'selected' | 'hidden';

export interface HitTestResult {
  drawingId: string;
  type: 'body' | 'point' | 'edge';
  pointIndex?: number;
  cursor: string;
}

export interface BaseDrawingStyle {
  lineColor: string;
  lineWidth: number;
  lineStyle: 'solid' | 'dashed' | 'dotted';
  showLabel?: boolean;
}

export interface DrawingSerializedData {
  id: string;
  toolType: DrawingToolType;
  points: DataPoint[];
  style: Record<string, any>;
  visible: boolean;
  locked: boolean;
  zIndex: number;
  createdAt: number;
}

export type DrawingEventType = 'created' | 'modified' | 'deleted' | 'selected' | 'deselected' | 'toolChanged' | 'doubleClicked' | 'styleChanged';

export interface DrawingEvent {
  type: DrawingEventType;
  drawingId?: string;
  toolType?: DrawingToolType;
}

export type DrawingEventHandler = (event: DrawingEvent) => void;
