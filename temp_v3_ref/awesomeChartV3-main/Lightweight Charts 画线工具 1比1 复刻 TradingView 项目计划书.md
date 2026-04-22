

# Lightweight Charts 画线工具 1:1 复刻 TradingView 项目计划书

---

## 📋 项目概述

### 项目名称
`lightweight-charts-drawing-tools`

### 项目目标
基于 TradingView 开源 **Lightweight Charts (v4.2+)**，1:1 复刻 TradingView 平台的 **8 种核心画线工具**，包括完整的创建流程、选中编辑、拖拽移动、删除、样式配置、坐标吸附等交互行为，达到专业级交易图表标注体验。

### 技术栈

| 类别 | 选型 | 版本 |
|------|------|------|
| 图表库 | `lightweight-charts` | `^4.2.0` |
| 语言 | TypeScript | `^5.0` |
| 构建 | Vite | `^5.0` |
| 样式 | 纯 CSS（无框架） | - |
| 包管理 | pnpm | 最新 |

---

## 📁 项目结构

```
lightweight-charts-drawing-tools/
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
├── src/
│   ├── main.ts                              # 演示页面入口
│   ├── sample-data.ts                       # 示例K线数据（≥300根）
│   ├── styles.css                           # 全局样式（深色主题）
│   │
│   ├── drawing-tools/                       # ====== 核心库 ======
│   │   ├── index.ts                         # 统一导出
│   │   │
│   │   ├── core/                            # ── 核心基础设施 ──
│   │   │   ├── types.ts                     # 所有公共类型定义
│   │   │   ├── constants.ts                 # 常量（颜色、尺寸、光标名）
│   │   │   ├── drawing-manager.ts           # 画线管理器（总调度中心）
│   │   │   ├── base-drawing.ts              # 画线基类（所有工具继承）
│   │   │   ├── interaction-state.ts         # 交互状态机
│   │   │   ├── hit-test.ts                  # 命中检测算法库
│   │   │   ├── coordinate-utils.ts          # 坐标转换工具
│   │   │   ├── snap.ts                      # 磁吸/吸附逻辑
│   │   │   ├── context-menu.ts              # 右键菜单
│   │   │   ├── tooltip.ts                   # 悬浮提示
│   │   │   └── keyboard.ts                  # 快捷键管理
│   │   │
│   │   ├── renderers/                       # ── 渲染工具函数 ──
│   │   │   ├── line-renderer.ts             # 线段/射线渲染
│   │   │   ├── rect-renderer.ts             # 矩形渲染
│   │   │   ├── arrow-renderer.ts            # 箭头头部渲染
│   │   │   ├── text-renderer.ts             # 文字标签渲染
│   │   │   ├── handle-renderer.ts           # 控制点（圆点/方块）渲染
│   │   │   └── dash-patterns.ts             # 虚线模式定义
│   │   │
│   │   ├── tools/                           # ── 8个具体工具 ──
│   │   │   ├── arrow.ts                     # 箭头工具
│   │   │   ├── trendline.ts                 # 趋势线工具
│   │   │   ├── horizontal-ray.ts            # 水平射线工具
│   │   │   ├── horizontal-line.ts           # 水平线工具
│   │   │   ├── rectangle.ts                 # 矩形工具
│   │   │   ├── long-position.ts             # 做多仓位工具
│   │   │   ├── short-position.ts            # 做空仓位工具
│   │   │   └── measure.ts                   # 测量工具
│   │   │
│   │   └── ui/                              # ── UI 组件 ──
│   │       ├── toolbar.ts                   # 左侧工具栏
│   │       ├── property-panel.ts            # 选中后的属性编辑浮窗
│   │       └── toolbar-icons.ts             # 工具栏图标 SVG
│   │
│   └── assets/                              # 静态资源
│       └── cursors/                          # 自定义光标图片（可选）
└── README.md
```

---

## 🏗️ 第一部分：核心基础设施

### 1.1 公共类型定义（types.ts）

```typescript
// ========================================
// 坐标与点
// ========================================

/** 数据坐标（价格+时间） — 持久化存储使用 */
interface DataPoint {
  price: number;          // Y 轴：价格值
  time: number;           // X 轴：Unix 时间戳（秒）
  logical?: number;       // 可选：逻辑索引（用于快速查找）
}

/** 像素坐标 — 仅用于渲染和命中检测 */
interface PixelPoint {
  x: number;
  y: number;
}

// ========================================
// 工具枚举
// ========================================

type DrawingToolType =
  | 'arrow'
  | 'trendline'
  | 'horizontal_ray'
  | 'horizontal_line'
  | 'rectangle'
  | 'long_position'
  | 'short_position'
  | 'measure';

// ========================================
// 交互状态
// ========================================

/** 画线工具的全局交互模式 */
type InteractionMode =
  | 'idle'           // 空闲：无任何画线操作进行中
  | 'placing'        // 放置中：用户正在创建新画线（点击放置锚点）
  | 'selected'       // 已选中：某个画线被选中，显示控制点
  | 'dragging'       // 拖拽中：正在移动整个画线或某个控制点
  | 'hovering';      // 悬停中：鼠标悬停在某个画线上（改变光标样式）

/** 单个画线的内部状态 */
type DrawingState =
  | 'creating'       // 创建中（尚未放置完所有锚点）
  | 'complete'       // 已完成（所有锚点已放置）
  | 'selected'       // 被选中
  | 'hidden';        // 被隐藏

// ========================================
// 命中检测结果
// ========================================

interface HitTestResult {
  drawing: BaseDrawing;                // 命中的画线实例
  type: 'body' | 'point' | 'edge';    // 命中区域类型
  pointIndex?: number;                  // 如果命中控制点，其索引
  cursor: string;                       // 应显示的光标样式
}

// ========================================
// 样式选项（每个工具可各自扩展）
// ========================================

interface BaseDrawingStyle {
  lineColor: string;
  lineWidth: number;
  lineStyle: 'solid' | 'dashed' | 'dotted';
  showLabel: boolean;
}

// ========================================
// 序列化格式
// ========================================

interface DrawingSerializedData {
  id: string;
  toolType: DrawingToolType;
  points: DataPoint[];
  style: Record<string, any>;
  visible: boolean;
  locked: boolean;
  zIndex: number;
  createdAt: number;
}

// ========================================
// 事件
// ========================================

interface DrawingEvent {
  type: 'created' | 'modified' | 'deleted' | 'selected' | 'deselected';
  drawing: BaseDrawing;
}

type DrawingEventHandler = (event: DrawingEvent) => void;
```

### 1.2 画线管理器（drawing-manager.ts）

这是整个画线系统的 **总调度中心**，负责管理所有画线实例、协调交互状态、派发事件。

```typescript
/**
 * DrawingManager — 画线系统总控制器
 *
 * 职责：
 * 1. 管理所有画线实例的生命周期（创建、选中、删除）
 * 2. 管理全局交互状态机（idle/placing/selected/dragging）
 * 3. 拦截图表的鼠标/键盘事件并分发给对应画线
 * 4. 管理工具栏状态（当前选中的工具）
 * 5. 管理事件监听器
 * 6. 序列化/反序列化所有画线
 */
class DrawingManager {

  // ---- 依赖 ----
  private _chart: IChartApi;
  private _series: ISeriesApi<SeriesType>;
  private _container: HTMLElement;       // 图表容器 DOM 元素

  // ---- 状态 ----
  private _drawings: Map<string, BaseDrawing>;   // id → 画线实例
  private _mode: InteractionMode;
  private _activeTool: DrawingToolType | null;    // 当前选中的工具栏工具
  private _selectedDrawing: BaseDrawing | null;   // 当前选中的画线
  private _hoveredDrawing: BaseDrawing | null;    // 当前悬停的画线
  private _creatingDrawing: BaseDrawing | null;   // 正在创建中的画线

  // ---- 拖拽状态 ----
  private _isDragging: boolean;
  private _dragTarget: BaseDrawing | null;
  private _dragPointIndex: number | null;          // null = 拖整体, 数字 = 拖第N个控制点
  private _dragStartPixel: PixelPoint | null;
  private _dragStartPoints: DataPoint[] | null;    // 拖拽开始时所有锚点的快照

  // ---- 事件监听 ----
  private _eventListeners: DrawingEventHandler[];
  private _boundHandlers: Record<string, Function>; // 用于移除事件监听

  constructor(chart: IChartApi, series: ISeriesApi<SeriesType>, container: HTMLElement);

  // ==== 公开 API ====

  /** 激活某个画线工具（用户点击工具栏后调用） */
  activateTool(toolType: DrawingToolType): void;

  /** 取消当前工具（按 Esc 或右键） */
  deactivateTool(): void;

  /** 删除指定画线 */
  removeDrawing(id: string): void;

  /** 删除当前选中的画线 */
  removeSelectedDrawing(): void;

  /** 删除所有画线 */
  removeAllDrawings(): void;

  /** 取消选中 */
  deselectAll(): void;

  /** 获取所有画线 */
  getAllDrawings(): BaseDrawing[];

  /** 序列化所有画线 */
  serialize(): DrawingSerializedData[];

  /** 反序列化恢复画线 */
  deserialize(data: DrawingSerializedData[]): void;

  /** 注册事件监听 */
  addEventListener(handler: DrawingEventHandler): void;

  /** 销毁（清理所有事件和画线） */
  destroy(): void;

  // ==== 内部事件处理（核心交互逻辑） ====

  /**
   * 鼠标按下处理
   * 处理优先级：
   * 1. 如果处于 placing 模式 → 调用 creatingDrawing.addPoint()
   * 2. 如果点击在某个控制点上 → 进入 dragging 模式（拖控制点）
   * 3. 如果点击在某个画线body上 → 进入 dragging 模式（拖整体）
   * 4. 如果点击在空白区域 → 取消选中
   */
  private _onMouseDown(event: MouseEvent): void;

  /**
   * 鼠标移动处理
   * 处理优先级：
   * 1. 如果处于 dragging 模式 → 更新拖拽目标的坐标
   * 2. 如果处于 placing 模式 → 更新创建中画线的临时点
   * 3. 否则 → 命中检测，更新光标样式和悬停状态
   */
  private _onMouseMove(event: MouseEvent): void;

  /**
   * 鼠标松开处理
   * - 结束拖拽
   */
  private _onMouseUp(event: MouseEvent): void;

  /**
   * 双击处理
   * - 在 placing 模式下：完成创建（部分工具支持双击结束）
   */
  private _onDoubleClick(event: MouseEvent): void;

  /**
   * 右键菜单
   * - 如果有选中的画线：显示画线上下文菜单
   * - 否则：取消当前工具
   */
  private _onContextMenu(event: MouseEvent): void;

  /**
   * 键盘事件
   * - Delete/Backspace → 删除选中画线
   * - Escape → 取消当前工具 / 取消选中
   * - Ctrl+Z → 撤销（可选高级功能）
   */
  private _onKeyDown(event: KeyboardEvent): void;
}
```

#### 1.2.1 事件拦截策略

```
┌─────────────────────────────────────────────────────────┐
│  DrawingManager 事件拦截架构                              │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  图表容器 DOM (container)                                 │
│    │                                                     │
│    ├── mousedown ──┐                                     │
│    ├── mousemove ──┤                                     │
│    ├── mouseup ────┤── DrawingManager 在捕获阶段拦截      │
│    ├── dblclick ───┤   (addEventListener 第3参数 true)    │
│    ├── contextmenu─┤                                     │
│    └── keydown ────┘   (绑定在 document 上)              │
│                    │                                     │
│                    ▼                                     │
│         DrawingManager._onXxx()                          │
│                    │                                     │
│          ┌─────────┴──────────┐                          │
│          │ 需要画线系统处理？   │                          │
│          └─────────┬──────────┘                          │
│              是 ↙    ↘ 否                                │
│     event.stopPropagation()   放行给 Lightweight Charts  │
│     event.preventDefault()    （正常的图表拖拽/缩放）      │
│     画线系统处理逻辑                                      │
│                                                          │
│  关键规则：                                               │
│  - 当 mode='placing' 或 mode='dragging' 时：             │
│    阻止事件传播，避免图表被拖动                            │
│  - 当 mode='idle' 且没有悬停在画线上时：                   │
│    放行事件，让图表正常交互                                │
│  - 当鼠标悬停在画线上但未点击时：                          │
│    仅修改光标样式，不阻止事件                              │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

#### 1.2.2 坐标转换流程

```
像素坐标 (MouseEvent) ←→ 数据坐标 (Price + Time)

【像素 → 数据】（鼠标事件处理时使用）

  mouseEvent.clientX / clientY
       │
       ▼  减去容器偏移
  containerX = clientX - container.getBoundingClientRect().left
  containerY = clientY - container.getBoundingClientRect().top
       │
       ▼  X → Time
  time = chart.timeScale().coordinateToTime(containerX)
  如果 time 为 null → 使用 coordinateToLogical 回退
       │
       ▼  Y → Price
  price = series.coordinateToPrice(containerY)
       │
       ▼
  DataPoint { price, time }


【数据 → 像素】（渲染时使用）

  DataPoint { price, time }
       │
       ▼  Time → X
  x = chart.timeScale().timeToCoordinate(time)
       │
       ▼  Price → Y
  y = series.priceToCoordinate(price)
       │
       ▼
  PixelPoint { x, y }
```

### 1.3 画线基类（base-drawing.ts）

```typescript
/**
 * BaseDrawing — 所有画线工具的抽象基类
 *
 * 每个画线实例本质上是一个 ISeriesPrimitive，
 * 通过 series.attachPrimitive(drawing) 附加到图表上。
 *
 * 子类必须实现的抽象方法标注了 abstract 关键字。
 */
abstract class BaseDrawing implements ISeriesPrimitive<Time> {

  // ---- 通用属性 ----
  readonly id: string;                     // UUID
  readonly toolType: DrawingToolType;
  protected _points: DataPoint[];           // 锚点数组
  protected _style: BaseDrawingStyle;       // 样式
  protected _state: DrawingState;
  protected _visible: boolean;
  protected _locked: boolean;               // 锁定后不可编辑/拖拽
  protected _zIndex: number;
  protected _hovered: boolean;              // 鼠标是否悬停在此画线上
  protected _selected: boolean;             // 是否被选中

  // ---- 图表引用（attached时赋值） ----
  protected _chart: IChartApi | null;
  protected _series: ISeriesApi<SeriesType> | null;
  protected _requestUpdate: (() => void) | null;

  // ---- PaneView ----
  protected _paneView: DrawingPaneView;

  constructor(toolType: DrawingToolType, defaultStyle: BaseDrawingStyle);

  // ==== ISeriesPrimitive 生命周期 ====
  attached(param: SeriesAttachedParameter<Time>): void;
  detached(): void;
  paneViews(): ISeriesPrimitivePaneView[];

  // ==== 锚点管理 ====

  /** 获取所有锚点（只读） */
  getPoints(): readonly DataPoint[];

  /**
   * 创建阶段：添加一个新锚点
   * - 第一次点击添加 point[0]
   * - 后续点击添加 point[1], point[2] ...
   * - 返回 true 表示画线创建完成，false 表示还需要更多点
   */
  abstract addPoint(point: DataPoint): boolean;

  /**
   * 创建阶段：更新临时悬浮点（鼠标移动时的预览效果）
   * - 例如趋势线：第一个点已放置，第二个点跟随鼠标
   */
  abstract updateTempPoint(point: DataPoint): void;

  /**
   * 移动单个锚点到新位置（拖拽控制点时调用）
   */
  movePoint(pointIndex: number, newPoint: DataPoint): void;

  /**
   * 平移整个画线（拖拽body时调用）
   * dx, dy 为数据坐标的偏移量
   */
  moveAll(dPrice: number, dTime: number): void;

  // ==== 命中检测 ====

  /**
   * 检测像素坐标是否命中此画线
   * 返回 null 表示未命中
   * 返回 HitTestResult 表示命中，包含命中区域和光标样式
   *
   * 检测范围（tolerance）通常为 5~8 像素
   */
  abstract hitTest(pixel: PixelPoint, tolerance: number): HitTestResult | null;

  // ==== 状态控制 ====
  select(): void;
  deselect(): void;
  setHovered(hovered: boolean): void;
  setVisible(visible: boolean): void;
  setLocked(locked: boolean): void;

  // ==== 样式 ====
  getStyle(): Readonly<BaseDrawingStyle>;
  updateStyle(style: Partial<BaseDrawingStyle>): void;

  // ==== 渲染相关 ====

  /**
   * 将所有锚点转换为像素坐标
   * 任何一个点转换失败（返回null）则整体返回null
   */
  protected _pointsToPixels(): PixelPoint[] | null;

  /**
   * 获取控制点（选中时显示的可拖拽圆点）的像素坐标
   * 默认实现：所有锚点位置显示控制点
   * 子类可覆盖以添加额外控制点（如中点、旋转点等）
   */
  getControlPoints(): PixelPoint[];

  // ==== 序列化 ====
  serialize(): DrawingSerializedData;
  deserialize(data: DrawingSerializedData): void;

  // ==== 触发重绘 ====
  protected _requestRedraw(): void;
}
```

### 1.4 命中检测算法库（hit-test.ts）

```typescript
/**
 * HitTestUtils — 几何命中检测工具函数集
 *
 * 所有函数以像素坐标操作，返回点到目标的距离或 boolean
 */
namespace HitTestUtils {

  /**
   * 点到线段的最短距离
   * 用于: trendline, arrow, rectangle边框
   *
   * 算法：
   * 1. 将点P投影到线段AB所在直线上，得到投影点Q
   * 2. 如果Q在AB之间 → 距离 = PQ 的长度
   * 3. 如果Q在A外侧 → 距离 = PA
   * 4. 如果Q在B外侧 → 距离 = PB
   */
  function pointToSegmentDistance(
    p: PixelPoint,
    a: PixelPoint,
    b: PixelPoint
  ): number;

  /**
   * 点到射线的最短距离
   * 用于: horizontal_ray
   *
   * 射线从 origin 出发，向 direction 方向无限延伸
   * direction: 'left' | 'right'
   *
   * 算法：
   * 水平射线特化：y方向距离 + x方向范围判断
   */
  function pointToHorizontalRayDistance(
    p: PixelPoint,
    origin: PixelPoint,
    direction: 'left' | 'right',
    chartWidth: number
  ): number;

  /**
   * 点到水平线的最短距离
   * 用于: horizontal_line
   *
   * 最简单：|p.y - lineY|
   */
  function pointToHorizontalLineDistance(
    p: PixelPoint,
    lineY: number
  ): number;

  /**
   * 点是否在矩形内部
   * 用于: rectangle, long/short position
   */
  function isPointInRect(
    p: PixelPoint,
    topLeft: PixelPoint,
    bottomRight: PixelPoint
  ): boolean;

  /**
   * 点到矩形边框的最短距离
   * 用于: rectangle 边框命中
   */
  function pointToRectBorderDistance(
    p: PixelPoint,
    topLeft: PixelPoint,
    bottomRight: PixelPoint
  ): number;

  /**
   * 点到圆点的距离
   * 用于: 检测是否命中控制点
   */
  function pointToPointDistance(
    p1: PixelPoint,
    p2: PixelPoint
  ): number;
}
```

### 1.5 吸附逻辑（snap.ts）

```typescript
/**
 * 坐标吸附/磁吸功能
 *
 * TradingView 行为复刻：
 * - 时间轴吸附到最近的K线开盘时间
 * - 价格轴吸附到最近的 OHLC 值（可选功能）
 * - 吸附仅在创建和拖拽时生效
 */
namespace SnapUtils {

  /**
   * 将任意时间戳吸附到最近的K线时间
   *
   * 实现方案：
   * 1. 用 chart.timeScale().coordinateToLogical(x) 获取逻辑索引
   * 2. 四舍五入到最近整数
   * 3. 用 chart.timeScale().logicalToCoordinate(roundedLogical) 转回
   *
   * 或者直接用 coordinateToTime 获取附近时间
   */
  function snapTimeToBar(
    rawTime: number,
    chart: IChartApi
  ): number;

  /**
   * 将价格吸附到最近的 OHLC 值（可选）
   * 遍历附近K线的 O/H/L/C，找最近的
   */
  function snapPriceToOHLC(
    rawPrice: number,
    nearbyBars: OHLCVData[],
    threshold: number
  ): number;
}
```

### 1.6 右键菜单（context-menu.ts）

```typescript
/**
 * 画线右键上下文菜单
 *
 * TradingView 行为复刻：
 * 右键点击已选中的画线时显示菜单，包含：
 * ┌──────────────────────┐
 * │ 🔒 锁定               │
 * │ 👁 隐藏               │
 * │ 📋 克隆               │
 * │ ─────────────────── │
 * │ 🗑 删除               │
 * │ 🗑 删除所有画线        │
 * └──────────────────────┘
 *
 * 实现方式：
 * - 创建一个绝对定位的 div 作为菜单容器
 * - 通过 CSS 类控制显示/隐藏
 * - 点击菜单项后执行对应操作并关闭菜单
 * - 点击其他区域或按 Esc 关闭菜单
 */
class ContextMenu {
  constructor(container: HTMLElement);
  show(x: number, y: number, drawing: BaseDrawing, manager: DrawingManager): void;
  hide(): void;
  destroy(): void;
}
```

---

## 🖱️ 第二部分：交互状态机详细设计

### 2.1 全局状态机

```
                    用户点击工具栏
                         │
            ┌────────────▼────────────┐
            │                          │
   ┌────────┤         IDLE             │◄──── Esc / 右键取消
   │        │   （空闲，正常图表交互）    │◄──── 点击空白区域
   │        └────────────┬─────────────┘
   │                     │
   │          鼠标悬停在画线上
   │                     │
   │        ┌────────────▼────────────┐
   │        │        HOVERING          │
   │        │  （光标变为 pointer/move） │
   │        └────┬──────────┬─────────┘
   │             │          │
   │          点击画线    鼠标移开
   │             │          │
   │             │    回到 IDLE
   │             │
   │   ┌─────────▼──────────────────┐
   │   │        SELECTED             │
   │   │  （显示控制点+选中高亮）      │◄──── 松开鼠标（拖拽结束）
   │   │  （显示属性编辑浮窗）        │
   │   └─────┬───────────┬──────────┘
   │         │           │
   │      按住拖拽     Delete键
   │         │           │
   │   ┌─────▼────┐   删除画线
   │   │ DRAGGING  │   → IDLE
   │   │（拖拽中）  │
   │   └─────┬─────┘
   │         │
   │      松开鼠标
   │         │
   │    回到 SELECTED
   │
   │  用户点击工具栏选择工具
   │         │
   ┌─────────▼──────────────────────┐
   │        PLACING                  │
   │   （放置中，逐步添加锚点）       │
   │   光标变为十字准星              │
   │                                 │
   │  每次点击 → addPoint()          │
   │  鼠标移动 → updateTempPoint()   │
   │  addPoint返回true → 创建完成    │
   │                 → 进入 SELECTED │
   │  Esc / 右键 → 取消创建          │
   │           → 删除未完成画线      │
   │           → 回到 IDLE           │
   └─────────────────────────────────┘
```

### 2.2 拖拽交互细节

```
拖拽画线 / 控制点的完整流程：

1. mousedown 命中画线
   │
   ├── 命中控制点 (type='point', pointIndex=N)
   │   → 记录: dragTarget, dragPointIndex=N
   │   → 记录: dragStartPixel, dragStartPoints（快照所有锚点）
   │   → 进入 DRAGGING 模式
   │   → 阻止事件传播（避免图表拖拽）
   │
   └── 命中画线body (type='body')
       → 记录: dragTarget, dragPointIndex=null
       → 记录: dragStartPixel, dragStartPoints
       → 进入 DRAGGING 模式
       → 阻止事件传播

2. mousemove（DRAGGING 模式）
   │
   ├── 拖控制点 (dragPointIndex !== null)
   │   → 将当前鼠标位置转换为 DataPoint
   │   → 调用 dragTarget.movePoint(dragPointIndex, newDataPoint)
   │   → 请求重绘
   │
   └── 拖整体 (dragPointIndex === null)
       → 计算鼠标偏移: dPixel = currentPixel - dragStartPixel
       → 将 dPixel 转换为 dPrice 和 dTime
       → 对所有锚点: newPoint[i] = dragStartPoints[i] + delta
       → 调用 dragTarget.moveAll(dPrice, dTime)
       → 请求重绘

3. mouseup
   → 退出 DRAGGING 模式
   → 进入 SELECTED 模式
   → 清除拖拽临时变量

关键细节：
- 拖拽整体时使用"快照+偏移"方式，避免浮点累积误差
- 拖拽控制点时直接设置新坐标
- 如果画线被 locked，忽略所有拖拽操作
- 拖拽期间禁止图表的默认拖拽行为
```

---

## 🔧 第三部分：8 个工具详细设计

---

### 3.1 🔧 Arrow（箭头）

#### 3.1.1 TradingView 行为描述

箭头工具绘制一条带箭头的有向线段。起点为箭头尾部，终点为箭头头部（带三角形箭头）。

#### 3.1.2 数据模型

```typescript
interface ArrowStyle extends BaseDrawingStyle {
  lineColor: string;      // 默认 '#FF5252'
  lineWidth: number;      // 默认 2
  lineStyle: 'solid' | 'dashed' | 'dotted';  // 默认 'solid'
  arrowHeadSize: number;  // 箭头三角形大小(px)，默认 15
}

// 锚点：2个
// points[0] = 起点（尾部）
// points[1] = 终点（箭头头部）
```

#### 3.1.3 创建流程

```
Step 1: 用户点击图表 → 放置起点 points[0]
        此时画面上出现一条从起点到鼠标位置的线+箭头（预览）

Step 2: 用户移动鼠标 → 线段终点跟随鼠标（实时预览）
        调用 updateTempPoint(mouseDataPoint) 更新预览

Step 3: 用户再次点击 → 放置终点 points[1]
        addPoint() 返回 true → 创建完成
        → 自动进入 SELECTED 状态
```

#### 3.1.4 渲染逻辑

```
渲染内容：
1. 从 points[0] 到 points[1] 画一条线段
   - 颜色: style.lineColor
   - 宽度: style.lineWidth
   - 线型: style.lineStyle
   
2. 在 points[1] 位置绘制箭头三角形
   - 箭头方向: 从 points[0] 指向 points[1] 的方向
   - 箭头大小: style.arrowHeadSize
   - 填充颜色: style.lineColor

   箭头三角形计算：
   角度 angle = atan2(p1.y - p0.y, p1.x - p0.x)
   箭头两翼分别在 angle ± 150° 方向
   左翼点 = p1 + arrowHeadSize * (cos(angle+5π/6), sin(angle+5π/6))
   右翼点 = p1 + arrowHeadSize * (cos(angle-5π/6), sin(angle-5π/6))
   三角形: [p1, 左翼点, 右翼点] → fillPath

3. 选中时：
   - 在 points[0] 和 points[1] 位置显示控制点圆圈
   - 圆圈: 半径4px, 白色填充, lineColor边框
```

#### 3.1.5 命中检测

```
检测优先级：
1. 检测是否命中控制点（圆圈区域，容差8px）
   → 返回 { type: 'point', pointIndex: 0或1, cursor: 'pointer' }

2. 检测是否命中线段（点到线段距离 ≤ tolerance 5px）
   → 返回 { type: 'body', cursor: 'move' }

3. 检测是否命中箭头三角形区域（点是否在三角形内）
   → 返回 { type: 'body', cursor: 'move' }

4. 都未命中 → 返回 null
```

#### 3.1.6 完整类结构

```typescript
class ArrowDrawing extends BaseDrawing {
  constructor() {
    super('arrow', defaultArrowStyle);
  }

  // 需要2个点才完成
  addPoint(point: DataPoint): boolean {
    this._points.push(point);
    return this._points.length >= 2;  // true = 完成
  }

  updateTempPoint(point: DataPoint): void {
    // 如果已有1个点，用临时点作为预览终点
    if (this._points.length === 1) {
      this._tempPoint = point;  // 存储在临时变量中供渲染使用
    }
  }

  hitTest(pixel: PixelPoint, tolerance: number): HitTestResult | null {
    // 实现如上所述
  }

  // 渲染委托给 ArrowRenderer（在 pane-renderer 中）
}
```

---

### 3.2 📏 Trendline（趋势线）

#### 3.2.1 TradingView 行为描述

绘制一条连接两点的直线段，常用于标记价格趋势。与箭头类似但无箭头，可选择是否将线段向两侧无限延伸。

#### 3.2.2 数据模型

```typescript
interface TrendlineStyle extends BaseDrawingStyle {
  lineColor: string;       // 默认 '#2962FF'
  lineWidth: number;       // 默认 2
  lineStyle: 'solid' | 'dashed' | 'dotted'; // 默认 'solid'
  extendLeft: boolean;     // 向左无限延伸，默认 false
  extendRight: boolean;    // 向右无限延伸，默认 false
  showPriceLabel: boolean; // 在价格轴上显示价格标签，默认 false
  showAngle: boolean;      // 显示角度信息，默认 false
}

// 锚点：2个
// points[0] = 起点
// points[1] = 终点
```

#### 3.2.3 创建流程

```
与 Arrow 完全相同的两步点击流程：
Step 1: 点击放置起点
Step 2: 鼠标移动预览 → 点击放置终点 → 完成
```

#### 3.2.4 渲染逻辑

```
渲染内容：

1. 基础线段：从 points[0] 到 points[1]
   - 颜色/宽度/线型同配置

2. 延伸处理：
   IF extendLeft == true:
     计算线段方向向量 dir = p0 - p1（从p1到p0的方向）
     将 p0 沿 dir 延伸到图表左边界外
     延伸后的左端点 = 与 x=0 或 x=-∞ 的交点
     
   IF extendRight == true:
     计算线段方向向量 dir = p1 - p0
     将 p1 沿 dir 延伸到图表右边界外
     延伸后的右端点 = 与 x=chartWidth 或 x=+∞ 的交点

   具体算法（使用参数方程）：
     线段参数方程: P(t) = p0 + t * (p1 - p0)
     t=0 → p0, t=1 → p1
     延伸左: 找 t 使得 P(t).x = 0 → t_left = -p0.x / (p1.x - p0.x)
     延伸右: 找 t 使得 P(t).x = chartWidth → t_right = (chartWidth - p0.x) / (p1.x - p0.x)
     同时需要 clamp y 到 [0, chartHeight]

3. 选中时：在 points[0] 和 points[1] 显示控制点

4. 可选 - 角度显示：
   IF showAngle == true:
     在线段中点附近显示角度文字
     angle = atan2(p1.y - p0.y, p1.x - p0.x) * 180 / π
     显示 "42.3°" 这样的文字

5. 可选 - 价格标签：
   IF showPriceLabel == true:
     在图表右侧价格轴上显示两个锚点的价格
     （通过 price scale 的 primitiveView 实现，或简单地在图表内右侧绘制）
```

#### 3.2.5 命中检测

```
与 Arrow 类似，但需额外处理延伸部分：

1. 如果有延伸，命中检测的线段范围也要延伸
   - 使用 pointToSegmentDistance，但线段端点为延伸后的端点

2. 控制点检测（仅检测原始 points[0] 和 points[1]，不检测延伸虚拟端点）

3. body命中：点到（可能延伸的）线段距离 ≤ tolerance
```

---

### 3.3 ➡️ Horizontal Ray（水平射线）

#### 3.3.1 TradingView 行为描述

从一个锚点出发，向右（或向左）水平无限延伸的射线。只需设置一个点（价格+时间），射线的 y 值固定为该点的价格。

#### 3.3.2 数据模型

```typescript
interface HorizontalRayStyle extends BaseDrawingStyle {
  lineColor: string;      // 默认 '#FF9800'
  lineWidth: number;      // 默认 2
  lineStyle: 'solid' | 'dashed' | 'dotted'; // 默认 'dashed'
  direction: 'right' | 'left';  // 射线方向，默认 'right'
  showPriceLabel: boolean;       // 在价格轴显示价格标签，默认 true
  showTimeLabel: boolean;        // 在时间轴显示时间标签，默认 false
}

// 锚点：1个
// points[0] = 射线起点（确定价格水平和起始时间位置）
```

#### 3.3.3 创建流程

```
Step 1: 用户点击图表 → 放置唯一锚点 points[0]
        addPoint() 返回 true → 创建立即完成
        射线从该点向右（或向左）无限延伸
        → 自动进入 SELECTED 状态

创建过程中的预览：
- 鼠标移动时显示一条跟随鼠标 y 位置的水平虚线
- 点击后虚线变为实际射线
```

#### 3.3.4 渲染逻辑

```
渲染内容：

1. 水平射线
   起点: points[0] 的像素坐标 (x0, y0)
   
   IF direction == 'right':
     从 (x0, y0) 画到 (chartWidth, y0)
   
   IF direction == 'left':
     从 (x0, y0) 画到 (0, y0)

   颜色/宽度/线型同配置

2. 起点标记（小圆点）
   在 (x0, y0) 画一个小实心圆（半径3px）

3. 价格标签
   IF showPriceLabel == true:
     在射线终端（右边界或左边界）显示价格值
     背景: lineColor
     文字: 白色
     格式: 保留2位小数
     
     ┌──────────┐
     │  45,230.50│ ← 价格标签贴在图表右边界
     └──────────┘

4. 选中时：在 points[0] 位置显示控制点
```

#### 3.3.5 命中检测

```
1. 控制点检测: 点到 points[0] 像素坐标的距离 ≤ 8px

2. 射线线段检测:
   IF direction == 'right':
     如果鼠标 x < x0: 未命中
     如果 |鼠标 y - y0| ≤ tolerance: 命中
   
   IF direction == 'left':
     如果鼠标 x > x0: 未命中
     如果 |鼠标 y - y0| ≤ tolerance: 命中

3. 命中 body 时光标: 'ns-resize'（上下拖拽改变价格水平）
```

#### 3.3.6 拖拽行为

```
- 拖拽控制点: 同时改变 price 和 time
- 拖拽 body（射线线段）: 只改变 price（上下移动），time 不变
  → 这是 TradingView 的特殊行为：水平线类工具拖拽body只改变价格
```

---

### 3.4 ── Horizontal Line（水平线）

#### 3.4.1 TradingView 行为描述

在整个图表宽度上绘制一条水平线，仅由价格决定位置，无时间维度概念。

#### 3.4.2 数据模型

```typescript
interface HorizontalLineStyle extends BaseDrawingStyle {
  lineColor: string;        // 默认 '#787B86'
  lineWidth: number;        // 默认 2
  lineStyle: 'solid' | 'dashed' | 'dotted'; // 默认 'solid'
  showPriceLabel: boolean;  // 默认 true
  showLabel: boolean;       // 显示自定义文字标签，默认 false
  labelText: string;        // 自定义标签文字，默认 ''
  labelPosition: 'left' | 'center' | 'right'; // 标签位置，默认 'left'
}

// 锚点：1个（仅需要 price）
// points[0] = { price: number, time: 0 }
// time 字段无实际意义，可设为0或当前时间
```

#### 3.4.3 创建流程

```
Step 1: 用户点击图表 → 放置锚点（取点击位置的 price）
        addPoint() 返回 true → 创建立即完成
        → 自动进入 SELECTED 状态

预览：鼠标移动时显示一条贯穿全图的水平虚线跟随 y 位置
```

#### 3.4.4 渲染逻辑

```
渲染内容：

1. 水平线
   y = series.priceToCoordinate(points[0].price)
   从 (0, y) 画到 (chartWidth, y)
   颜色/宽度/线型同配置

2. 价格标签（右侧价格轴）
   IF showPriceLabel == true:
     在图表右边界内侧绘制价格标签
     ┌──────────┐
     │  45,230  │
     └──────────┘
     背景: lineColor，文字: 白色

3. 自定义文字标签
   IF showLabel == true && labelText != '':
     在 labelPosition 指定的位置显示文字
     - left: x=10
     - center: x=chartWidth/2
     - right: x=chartWidth-10
     y = 水平线y坐标上方 4px
     字体: 12px, 颜色: lineColor

4. 选中时：
   在水平线上显示一个控制点（位于图表中央 x 位置）
   额外在线段两端显示小方块手柄（视觉提示）
```

#### 3.4.5 命中检测

```
- |鼠标y - lineY| ≤ tolerance → 命中
- 命中光标: 'ns-resize'
- 无论鼠标 x 在何处都可命中（全宽线段）
```

#### 3.4.6 拖拽行为

```
- 拖拽任何部位：仅改变 price（上下移动），不涉及 time
- 拖拽控制点 和 拖拽body 行为完全一致
```

---

### 3.5 ⬜ Rectangle（矩形）

#### 3.5.1 TradingView 行为描述

绘制一个矩形区域，由对角线的两个顶点确定。矩形可以用于标注价格区间+时间区间。矩形有填充背景色和边框。

#### 3.5.2 数据模型

```typescript
interface RectangleStyle extends BaseDrawingStyle {
  lineColor: string;          // 边框颜色，默认 '#2962FF'
  lineWidth: number;          // 边框宽度，默认 1
  lineStyle: 'solid' | 'dashed' | 'dotted'; // 默认 'solid'
  fillColor: string;          // 填充颜色（含透明度），默认 'rgba(41, 98, 255, 0.1)'
  showLabel: boolean;         // 显示信息标签，默认 false
  extendLeft: boolean;        // 向左延伸到图表边界，默认 false
  extendRight: boolean;       // 向右延伸到图表边界，默认 false
}

// 锚点：2个（对角线的两个顶点）
// points[0] = 左上角（或任意一角）
// points[1] = 右下角（或对角）
// 渲染时取 min/max 确定实际的 top-left 和 bottom-right
```

#### 3.5.3 创建流程

```
Step 1: 用户点击图表 → 放置第一个角点 points[0]
        此时矩形从该点开始，另一角跟随鼠标

Step 2: 鼠标移动 → 矩形实时预览（从 points[0] 到鼠标位置的矩形）

Step 3: 用户再次点击 → 放置第二个角点 points[1]
        addPoint() 返回 true → 创建完成
        → 自动进入 SELECTED 状态
```

#### 3.5.4 渲染逻辑

```
坐标计算：
  p0_pixel = toPixel(points[0])
  p1_pixel = toPixel(points[1])
  
  left   = min(p0_pixel.x, p1_pixel.x)
  right  = max(p0_pixel.x, p1_pixel.x)
  top    = min(p0_pixel.y, p1_pixel.y)
  bottom = max(p0_pixel.y, p1_pixel.y)
  
  IF extendLeft:  left = 0
  IF extendRight: right = chartWidth

渲染内容：

1. 填充矩形
   ctx.fillStyle = style.fillColor
   ctx.fillRect(left, top, right-left, bottom-top)

2. 边框矩形
   ctx.strokeStyle = style.lineColor
   ctx.lineWidth = style.lineWidth
   setLineDash(style.lineStyle)
   ctx.strokeRect(left, top, right-left, bottom-top)

3. 选中时：显示 8 个控制点
   ┌───●────●────●───┐
   │                  │
   ●                  ●    4个角 + 4条边中点 = 8个控制点
   │                  │
   └───●────●────●───┘

   控制点行为：
   - 4个角控制点：拖拽时同时改变 x 和 y（对角固定）
   - 上/下边中点：仅改变 price（y方向拉伸）
   - 左/右边中点：仅改变 time（x方向拉伸）
```

#### 3.5.5 命中检测

```
1. 检测8个控制点（选中状态时才有）

2. 检测边框线段
   分别检测4条边的线段距离，取最小值
   如果 ≤ tolerance → 命中 edge, cursor='pointer'

3. 检测填充区域
   如果鼠标点在矩形内部 → 命中 body, cursor='move'
```

#### 3.5.6 控制点拖拽详细逻辑

```
8个控制点的索引与拖拽行为：

  0────1────2
  │         │
  7         3
  │         │
  6────5────4

pointIndex=0 (左上角): 
  改变 points[0].price（取max）和 points[0].time（取min）
  
pointIndex=1 (上中): 
  仅改变 上边价格 → 修改对应点的 price
  
pointIndex=2 (右上角):
  改变 上边price 和 右边time

pointIndex=3 (右中):
  仅改变 右边 time

pointIndex=4 (右下角):
  改变 points[1].price 和 points[1].time

pointIndex=5 (下中):
  仅改变 下边 price

pointIndex=6 (左下角):
  改变 下边 price 和 左边 time

pointIndex=7 (左中):
  仅改变 左边 time

实现策略：
  内部用 { priceHigh, priceLow, timeLeft, timeRight } 四个值表示矩形
  每个控制点的拖拽只修改其中部分值
  渲染时从这四个值反推 points[0] 和 points[1]
```

---

### 3.6 📈 Long Position（做多仓位）

#### 3.6.1 TradingView 行为描述

做多仓位工具绘制一个包含入场价、止盈价、止损价的矩形区域，可视化一笔做多交易的风险回报比。

视觉上是一个分为上下两块的矩形：
- **上方绿色区域**：入场到止盈（利润区）
- **下方红色区域**：入场到止损（亏损区）
- 中间有一条分界线表示入场价
- 显示具体的盈亏数值和百分比

#### 3.6.2 数据模型

```typescript
interface LongPositionStyle extends BaseDrawingStyle {
  profitColor: string;         // 止盈区域颜色，默认 'rgba(38, 166, 154, 0.15)'
  profitBorderColor: string;   // 止盈区域边框，默认 '#26a69a'
  lossColor: string;           // 止损区域颜色，默认 'rgba(239, 83, 80, 0.15)'
  lossBorderColor: string;     // 止损区域边框，默认 '#ef5350'
  entryColor: string;          // 入场线颜色，默认 '#2962FF'
  lineWidth: number;           // 边框宽度，默认 1
  showLabels: boolean;         // 显示文字标签，默认 true
  showPercentage: boolean;     // 显示百分比，默认 true
  showPnL: boolean;            // 显示盈亏金额，默认 true
  showRiskRewardRatio: boolean;// 显示风险回报比，默认 true
  quantity: number;            // 交易数量（用于计算PnL），默认 1
  accountSize: number;         // 账户大小（用于计算百分比），默认 10000
}

// 锚点：3个
// points[0] = 入场点 (entry price + time)
// points[1] = 止盈点 (take-profit price + time) → price > entry
// points[2] = 止损点 (stop-loss price + time)   → price < entry
//
// 实际交互中只需用户放置2个点（入场 + 止盈/止损其中一个）
// 第3个点由默认比例自动计算，之后用户可拖拽调整
```

#### 3.6.3 创建流程

```
Step 1: 用户点击图表 → 放置入场点 points[0]（entry price）
        此时开始显示预览矩形

Step 2: 用户移动鼠标 → 实时预览
        鼠标在入场价上方 → 定义止盈位置
        同时自动计算止损位置（默认 1:1 风险回报比）
        止损距离 = 入场价 - (鼠标价格 - 入场价)

Step 3: 用户再次点击 → 确定止盈位置
        addPoint() 返回 true → 创建完成
        自动计算止损位置 = entry - (tp - entry)

        → 进入 SELECTED 状态
        → 用户可拖拽止损线调整止损价位

特殊处理：
- 做多工具要求止盈 > 入场 > 止损
- 如果用户在入场价下方点击第二个点，则将其视为止损点
  止盈自动设为 entry + (entry - 鼠标价格)
```

#### 3.6.4 渲染逻辑

```
坐标计算：
  entryY = priceToY(entry_price)
  tpY    = priceToY(tp_price)      // 止盈 y（在上方）
  slY    = priceToY(sl_price)      // 止损 y（在下方）
  
  timeLeft  = min(points[0].time, points[1].time)
  timeRight = max(points[0].time, points[1].time)
  
  xLeft  = timeToX(timeLeft)
  xRight = timeToX(timeRight)
  width  = xRight - xLeft   (最小宽度保证 120px)

渲染内容：

1. 止盈区域（上方绿色块）
   ┌─────────────────────────────────────┐ ← tpY
   │                                     │
   │   Target: 46,500.00 (+2.8%)         │ ← 止盈价格和百分比
   │   P&L: +$1,260.00                   │ ← 盈利金额
   │                                     │
   ├─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─┤ ← entryY（入场线）
   
   填充: profitColor
   边框: profitBorderColor

2. 止损区域（下方红色块）
   ├─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─┤ ← entryY
   │                                     │
   │   Stop: 44,220.00 (-2.8%)           │ ← 止损价格和百分比
   │   P&L: -$1,260.00                   │ ← 亏损金额
   │                                     │
   └─────────────────────────────────────┘ ← slY
   
   填充: lossColor
   边框: lossBorderColor

3. 入场线
   从 (xLeft, entryY) 到 (xRight, entryY) 的实线
   颜色: entryColor

4. 信息标签（在入场线右侧）
   Entry: 45,230.00
   R:R = 1:1.5
   
5. 选中时的控制点：
   ● 入场线左端 (可左右+上下拖拽)
   ● 入场线右端 (可左右拖拽宽度)
   ● 止盈线中间 (只能上下拖拽，改变止盈价)
   ● 止损线中间 (只能上下拖拽，改变止损价)
```

#### 3.6.5 标签文字计算公式

```typescript
// 百分比计算
profitPercent = ((tpPrice - entryPrice) / entryPrice) * 100  // 例: +2.8%
lossPercent   = ((entryPrice - slPrice) / entryPrice) * 100  // 例: -2.8%

// 盈亏金额
profitPnL = (tpPrice - entryPrice) * quantity  // 例: +$1,260
lossPnL   = (slPrice - entryPrice) * quantity  // 例: -$1,260 (负数)

// 风险回报比
riskRewardRatio = (tpPrice - entryPrice) / (entryPrice - slPrice) // 例: 1.5
// 显示为 "R:R = 1:1.5"

// 账户百分比（可选）
profitAccountPercent = (profitPnL / accountSize) * 100
lossAccountPercent   = (lossPnL / accountSize) * 100
```

#### 3.6.6 命中检测

```
1. 控制点检测（4个控制点）
2. 入场线命中 → cursor: 'ns-resize'
3. 止盈区域内部命中 → cursor: 'move'
4. 止损区域内部命中 → cursor: 'move'
```

#### 3.6.7 拖拽行为

```
- 拖止盈控制点: 只改变止盈价格 (上下)，不允许拖到入场价以下
- 拖止损控制点: 只改变止损价格 (上下)，不允许拖到入场价以上
- 拖入场线: 整体上下移动（三个价格等差平移）
- 拖整体: 同时移动所有价格和时间
- 拖宽度控制点: 改变矩形左右时间范围
```

---

### 3.7 📉 Short Position（做空仓位）

#### 3.7.1 TradingView 行为描述

与 Long Position 完全对称：
- **上方红色区域**：入场到止损（亏损区，因为做空后价格上涨是亏损）
- **下方绿色区域**：入场到止盈（利润区，因为做空后价格下跌是盈利）

#### 3.7.2 数据模型

```typescript
interface ShortPositionStyle extends BaseDrawingStyle {
  // 与 LongPositionStyle 完全相同的字段
  // 但默认颜色互换：
  // 上方（止损区）用红色
  // 下方（止盈区）用绿色
  profitColor: string;         // 默认 'rgba(38, 166, 154, 0.15)' (绿)
  profitBorderColor: string;   // 默认 '#26a69a'
  lossColor: string;           // 默认 'rgba(239, 83, 80, 0.15)' (红)
  lossBorderColor: string;     // 默认 '#ef5350'
  entryColor: string;
  // ... 其余同 Long
  quantity: number;
  accountSize: number;
}

// 锚点：3个
// points[0] = 入场点 (entry)
// points[1] = 止盈点 (take-profit) → price < entry（做空止盈在下方）
// points[2] = 止损点 (stop-loss)   → price > entry（做空止损在上方）
```

#### 3.7.3 核心差异（与 Long Position 对比）

```
                Long Position              Short Position
止盈位置         入场价上方                  入场价下方
止损位置         入场价下方                  入场价上方
上方矩形颜色     绿色（利润）               红色（亏损）
下方矩形颜色     红色（亏损）               绿色（利润）
盈利计算         (tp - entry) * qty         (entry - tp) * qty
亏损计算         (sl - entry) * qty (负)    (entry - sl) * qty (负)
拖止盈方向约束   不能低于入场价              不能高于入场价
拖止损方向约束   不能高于入场价              不能低于入场价
```

#### 3.7.4 渲染逻辑

```
   ┌─────────────────────────────────────┐ ← slY (止损，上方)
   │  █ LOSS ZONE (红色)                  │
   │  Stop: 46,500.00 (+2.8%)            │
   │  P&L: -$1,260.00                    │
   ├─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─┤ ← entryY (入场线)
   │  █ PROFIT ZONE (绿色)               │
   │  Target: 44,220.00 (-2.8%)          │
   │  P&L: +$1,260.00                    │
   └─────────────────────────────────────┘ ← tpY (止盈，下方)
```

#### 3.7.5 实现建议

```
建议 Long Position 和 Short Position 共享一个基类 PositionDrawing，
通过 direction: 'long' | 'short' 参数区分行为差异。

class PositionDrawing extends BaseDrawing {
  protected _direction: 'long' | 'short';
  
  // 大部分逻辑通用，仅在以下几处根据 direction 分支：
  // 1. 止盈/止损的上下位置关系
  // 2. 盈亏计算公式的正负号
  // 3. 拖拽约束方向
  // 4. 颜色分配
}

class LongPositionDrawing extends PositionDrawing {
  constructor() { super('long'); }
}

class ShortPositionDrawing extends PositionDrawing {
  constructor() { super('short'); }
}
```

---

### 3.8 📐 Measure（测量工具）

#### 3.8.1 TradingView 行为描述

测量工具用于度量两点之间的价格差、时间差、百分比变化和K线根数。它不是持久性画线——通常只在测量过程中显示，可以保留也可以自动消失。

TradingView 中的 Measure 工具视觉上类似一个带信息标签的矩形+对角线：

#### 3.8.2 数据模型

```typescript
interface MeasureStyle extends BaseDrawingStyle {
  lineColor: string;          // 默认 '#787B86'
  lineWidth: number;          // 默认 1
  lineStyle: 'dashed';        // 固定虚线
  fillColor: string;          // 矩形填充色，默认 'rgba(120, 123, 134, 0.05)'
  labelBgColor: string;       // 标签背景色，默认 'rgba(30, 30, 40, 0.9)'
  labelTextColor: string;     // 标签文字颜色，默认 '#d1d4dc'
  positiveColor: string;      // 上涨颜色，默认 '#26a69a'
  negativeColor: string;      // 下跌颜色，默认 '#ef5350'
}

// 锚点：2个
// points[0] = 起始测量点
// points[1] = 结束测量点
```

#### 3.8.3 创建流程

```
Step 1: 用户点击图表 → 放置起点 points[0]

Step 2: 鼠标移动 → 实时显示测量矩形和信息标签
        不断调用 updateTempPoint(mouseDataPoint)

Step 3: 用户再次点击 → 放置终点 points[1]
        addPoint() 返回 true → 创建完成
        → 进入 SELECTED 状态（保留在图表上）
```

#### 3.8.4 渲染逻辑

```
坐标计算：
  p0 = toPixel(points[0])
  p1 = toPixel(points[1])

渲染内容：

1. 虚线矩形（起点和终点为对角线）
   left   = min(p0.x, p1.x)
   right  = max(p0.x, p1.x)
   top    = min(p0.y, p1.y)
   bottom = max(p0.y, p1.y)
   
   ctx.fillStyle = fillColor
   ctx.fillRect(...)
   ctx.strokeStyle = lineColor
   ctx.setLineDash([5, 5])
   ctx.strokeRect(...)

2. 对角线
   从 p0 到 p1 画虚线

3. 信息标签面板（核心重点）
   显示在矩形内部（或外部，取决于空间）
   
   ┌────────────────────────────────┐
   │  ▲ 1,270.50 (2.81%)           │  ← 价格差和百分比（绿色/红色）
   │  45 bars                       │  ← K线根数
   │  2024-01-02 → 2024-03-15      │  ← 时间范围
   │  Vol: 1,234,567                │  ← 区间总成交量（可选）
   └────────────────────────────────┘

   标签位置策略：
   - 默认在矩形右上角内侧
   - 如果空间不足，移到矩形外部
   - 标签有圆角背景 (8px border-radius)

4. 选中时：在 points[0] 和 points[1] 显示控制点
```

#### 3.8.5 信息计算公式

```typescript
// 价格差
priceDiff = points[1].price - points[0].price
// 正数显示 "▲ +1,270.50"（绿色），负数显示 "▼ -1,270.50"（红色）

// 百分比变化
percentChange = (priceDiff / points[0].price) * 100
// 显示 "(+2.81%)" 或 "(-2.81%)"

// K线数量
barCount = |logicalIndex(points[1]) - logicalIndex(points[0])|
// 需要通过 timeScale 的 logical index 计算
// 显示 "45 bars"

// 时间跨度
timeDiff = |points[1].time - points[0].time|
// 转换为人类可读格式
// < 1天: "4h 30m"
// < 30天: "15 days"  
// ≥ 30天: "2 months 3 days"

// 区间总成交量（可选增强）
totalVolume = sum(所有 time 在 [t0, t1] 范围内的K线 volume)
```

#### 3.8.6 命中检测

```
1. 控制点检测
2. 对角线线段命中
3. 矩形内部命中
4. 标签面板矩形命中
```

---

## 🎛️ 第四部分：UI 组件

### 4.1 工具栏（toolbar.ts）

```
工具栏位置：图表左侧，垂直排列

┌────┐
│ ↗  │  Arrow
├────┤
│ ╱  │  Trendline
├────┤
│ →  │  Horizontal Ray
├────┤
│ ── │  Horizontal Line
├────┤
│ □  │  Rectangle
├────┤
│ 📈 │  Long Position
├────┤
│ 📉 │  Short Position
├────┤
│ 📐 │  Measure
├────┤
│ 🗑  │  Delete All (特殊按钮)
└────┘

行为：
- 点击某工具 → 高亮该按钮，调用 manager.activateTool(type)
- 再次点击已激活的工具 → 取消激活，回到 idle
- 工具激活时鼠标光标变为十字准星 (crosshair)
- 按 Esc 取消当前工具
- 鼠标悬停显示工具名称 tooltip
```

#### 4.1.1 工具栏实现要求

```typescript
class Toolbar {
  constructor(
    container: HTMLElement,     // 图表容器（工具栏将定位在其内部左侧）
    manager: DrawingManager
  );

  /** 设置某工具的激活状态（被 manager 回调） */
  setActiveButton(toolType: DrawingToolType | null): void;

  /** 销毁 */
  destroy(): void;
}
```

```
DOM 结构：
<div class="drawing-toolbar">
  <button class="toolbar-btn" data-tool="arrow" title="Arrow">
    <svg>...</svg>
  </button>
  <button class="toolbar-btn" data-tool="trendline" title="Trendline">
    <svg>...</svg>
  </button>
  ...
  <div class="toolbar-separator"></div>
  <button class="toolbar-btn toolbar-btn-danger" data-tool="delete_all" title="Delete All">
    <svg>...</svg>
  </button>
</div>

CSS 要点：
- position: absolute; left: 0; top: 50%; transform: translateY(-50%)
- 深色半透明背景 (rgba(30, 30, 46, 0.9))
- 圆角 (border-radius: 8px)
- 按钮尺寸 36x36px
- hover 时背景变亮
- active（已选中）时背景高亮 + 左边框指示条
- z-index 高于图表但低于弹窗
```

### 4.2 属性编辑面板（property-panel.ts）

```
当画线被选中时，在画线附近（或图表右上角）显示一个浮动面板：

┌──────────────────────────────┐
│  Trendline  ─  Properties    │
├──────────────────────────────┤
│  Color: [■ ▼]  #2962FF      │  ← 颜色选择器（简化版：预设色板）
│  Width: [1] [2] [3] [4]     │  ← 线宽快捷选择
│  Style: [──] [--] [··]      │  ← 线型快捷选择
│  ☐ Extend Left              │  ← 开关选项
│  ☐ Extend Right             │
├──────────────────────────────┤
│  [Clone]  [🗑 Delete]        │  ← 操作按钮
└──────────────────────────────┘

行为：
- 选中画线时显示，取消选中时隐藏
- 修改任何属性 → 立即调用 drawing.updateStyle() 并重绘
- 面板位置跟随画线（但不遮挡画线主体）
- 面板可拖拽移动
```

#### 4.2.1 实现要求

```typescript
class PropertyPanel {
  constructor(container: HTMLElement, manager: DrawingManager);

  /** 显示某个画线的属性面板 */
  show(drawing: BaseDrawing): void;

  /** 隐藏面板 */
  hide(): void;

  /** 更新面板内容（画线属性变化时） */
  update(drawing: BaseDrawing): void;

  destroy(): void;
}
```

---

## 🖥️ 第五部分：演示页面

### 5.1 页面布局

```
┌─────────────────────────────────────────────────────────────────┐
│  Lightweight Charts Drawing Tools Demo                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────┬─────────────────────────────────────────────────────┐   │
│  │工具│                                                      │   │
│  │栏  │                                                      │   │
│  │    │                   图表区域                            │   │
│  │ ↗  │              (宽度100%, 高度600px)                    │   │
│  │ ╱  │                                                      │   │
│  │ →  │           K线图 + 画线工具叠加显示                    │   │
│  │ ── │                                                      │   │
│  │ □  │                                                      │   │
│  │ 📈 │                                                      │   │
│  │ 📉 │                                                      │   │
│  │ 📐 │                                                      │   │
│  │ 🗑  │                                                      │   │
│  └────┴─────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ 状态栏                                                    │    │
│  │ Mode: idle | Tool: none | Drawings: 3 | Selected: none  │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ 操作区                                                    │    │
│  │ [导出JSON]  [导入JSON]  [清除所有]                        │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 演示页面功能

```
1. 图表初始化
   - 创建 Lightweight Charts 实例（深色主题）
   - 加载 ≥ 300 根日线 K 线数据
   - 显示成交量柱状图（子图或叠加）

2. 画线工具集成
   - 创建 DrawingManager 实例
   - 创建 Toolbar 和 PropertyPanel
   - 绑定快捷键

3. 状态栏
   - 实时显示当前交互模式、激活工具、画线数量、选中画线ID
   - 通过 manager.addEventListener 监听事件更新

4. 导出/导入
   - [导出JSON] → 调用 manager.serialize()，下载JSON文件
   - [导入JSON] → 文件上传，调用 manager.deserialize()
   - [清除所有] → 调用 manager.removeAllDrawings()

5. 演示数据
   - sample-data.ts 中使用程序生成的模拟股票数据
   - 生成算法：随机游走 + 趋势 + 波动率聚集
   - 确保数据有明显的趋势和震荡区间
```

### 5.3 示例数据生成

```typescript
// sample-data.ts
export function generateSampleData(count: number = 300): OHLCVData[] {
  const data: OHLCVData[] = [];
  let price = 100;
  const baseDate = new Date('2024-01-02');
  
  for (let i = 0; i < count; i++) {
    const date = new Date(baseDate);
    date.setDate(date.getDate() + i);
    
    // 跳过周末
    if (date.getDay() === 0 || date.getDay() === 6) continue;
    
    const change = (Math.random() - 0.48) * 3; // 轻微上涨趋势
    const volatility = 1 + Math.random() * 2;
    
    const open = price;
    const close = price + change;
    const high = Math.max(open, close) + Math.random() * volatility;
    const low = Math.min(open, close) - Math.random() * volatility;
    const volume = Math.floor(10000 + Math.random() * 50000);
    
    data.push({
      time: date.toISOString().split('T')[0],  // 'YYYY-MM-DD'
      open: +open.toFixed(2),
      high: +high.toFixed(2),
      low: +low.toFixed(2),
      close: +close.toFixed(2),
      volume,
    });
    
    price = close;
  }
  
  return data;
}
```

---

## ⚡ 第六部分：性能与兼容性

### 6.1 渲染性能

```
- 所有画线共享同一个渲染循环（通过 Lightweight Charts 的 requestUpdate 驱动）
- 每个画线独立判断是否需要重绘（脏标记机制）
- 命中检测应在 O(n) 时间内完成（n=画线数量，通常 < 100）
- 如果画线数量 > 50，考虑实现空间索引（四叉树）加速命中检测
```

### 6.2 高 DPI 支持

```
- 所有 Canvas 绘制使用 useBitmapCoordinateSpace 获取的 scope
- 坐标乘以 horizontalPixelRatio / verticalPixelRatio
- 线宽也需要乘以 pixelRatio
- 文字大小也需要乘以 pixelRatio
```

### 6.3 快捷键

```
Delete / Backspace  → 删除选中画线
Escape              → 取消当前工具 / 取消选中
Ctrl+Z              → 撤销最后操作（可选高级功能）
Ctrl+A              → 全选所有画线（可选）
```

---

## 📋 第七部分：验收标准

### 7.1 功能验收矩阵

| # | 工具 | 创建 | 预览 | 选中 | 拖拽body | 拖拽控制点 | 删除 | 样式修改 |
|---|------|------|------|------|----------|-----------|------|----------|
| 1 | Arrow | ✓ 两点 | ✓ 线+箭头 | ✓ | ✓ 整体平移 | ✓ 两端点 | ✓ | ✓ 颜色/粗细/线型 |
| 2 | Trendline | ✓ 两点 | ✓ 线段 | ✓ | ✓ 整体平移 | ✓ 两端点 | ✓ | ✓ +延伸选项 |
| 3 | H-Ray | ✓ 一点 | ✓ 水平线 | ✓ | ✓ 仅上下 | ✓ 起点 | ✓ | ✓ +方向 |
| 4 | H-Line | ✓ 一点 | ✓ 全宽线 | ✓ | ✓ 仅上下 | ✓ | ✓ | ✓ +标签 |
| 5 | Rectangle | ✓ 两点 | ✓ 矩形 | ✓ | ✓ 整体 | ✓ 8个点 | ✓ | ✓ +填充色 |
| 6 | Long Pos | ✓ 两点 | ✓ 双色块 | ✓ | ✓ 整体 | ✓ 4个点 | ✓ | ✓ +数量 |
| 7 | Short Pos | ✓ 两点 | ✓ 双色块 | ✓ | ✓ 整体 | ✓ 4个点 | ✓ | ✓ +数量 |
| 8 | Measure | ✓ 两点 | ✓ 矩形+标签 | ✓ | ✓ 整体 | ✓ 两端点 | ✓ | ✓ |

### 7.2 交互验收

| # | 验收项 | 通过标准 |
|---|--------|----------|
| 1 | 工具栏切换 | 点击工具按钮切换高亮，光标变十字线 |
| 2 | 创建流程 | 按各工具指定的步骤创建，过程中有实时预览 |
| 3 | Esc 取消 | 创建过程中按 Esc，未完成的画线被删除 |
| 4 | 右键取消 | 创建过程中右键，未完成的画线被删除 |
| 5 | 选中高亮 | 点击画线后显示控制点，画线边框略加粗或发光 |
| 6 | 取消选中 | 点击空白区域取消选中，控制点消失 |
| 7 | 拖拽平滑 | 拖拽画线/控制点过程流畅无卡顿 |
| 8 | 拖拽不穿透 | 拖拽画线时图表不会被同时拖动 |
| 9 | 光标正确 | 悬停画线body→move, 控制点→pointer, 水平线→ns-resize |
| 10 | Delete 删除 | 选中画线后按 Delete 键，画线被删除 |
| 11 | 右键菜单 | 选中画线后右键显示菜单，菜单项功能正常 |
| 12 | 属性面板 | 选中画线后显示属性面板，修改属性实时生效 |
| 13 | 多画线共存 | 可同时存在 ≥10 个不同类型的画线 |
| 14 | 滚动/缩放 | 画线跟随图表滚动和缩放正确重定位 |
| 15 | 序列化 | 导出JSON后重新导入，所有画线完全恢复 |

### 7.3 技术验收

| # | 验收项 | 通过标准 |
|---|--------|----------|
| 1 | TS 编译 | `tsc --noEmit` 零错误 |
| 2 | Vite 构建 | `vite build` 成功 |
| 3 | 高 DPI | Retina 屏幕上线条和文字清晰 |
| 4 | 文件结构 | 严格遵循项目结构 |
| 5 | 代码注释 | 每个 public 方法有 JSDoc |

---

## 📆 第八部分：建议实施顺序

```
Phase 1: 基础设施（必须最先完成）
  ├── types.ts              ← 先定义所有类型
  ├── constants.ts
  ├── coordinate-utils.ts   ← 坐标转换是一切的基础
  ├── hit-test.ts           ← 命中检测工具函数
  ├── base-drawing.ts       ← 画线基类
  ├── drawing-manager.ts    ← 交互状态机和事件管理
  └── 渲染器基础工具函数

Phase 2: 最简单的工具（验证架构）
  ├── horizontal-line.ts    ← 最简单：1个点，全宽线
  └── 验证：创建、选中、拖拽、删除全流程

Phase 3: 两点线段工具
  ├── trendline.ts          ← 两点线段
  ├── arrow.ts              ← 线段+箭头
  └── horizontal-ray.ts     ← 一点+方向

Phase 4: 矩形类工具
  ├── rectangle.ts          ← 矩形（8个控制点）
  └── measure.ts            ← 矩形+信息标签

Phase 5: 复杂工具
  ├── long-position.ts      ← 做多仓位
  └── short-position.ts     ← 做空仓位（基于共享基类）

Phase 6: UI 完善
  ├── toolbar.ts            ← 工具栏
  ├── property-panel.ts     ← 属性面板
  ├── context-menu.ts       ← 右键菜单
  └── main.ts               ← 演示页面集成

Phase 7: 收尾
  ├── 序列化/反序列化
  ├── 快捷键
  ├── 样式优化
  └── 最终测试
```

---

## 📎 附录

### 附录 A：Canvas 虚线模式定义

```typescript
// dash-patterns.ts
const LINE_DASH_PATTERNS: Record<string, number[]> = {
  solid:  [],
  dashed: [8, 5],
  dotted: [2, 3],
};
```

### 附录 B：默认颜色方案

```typescript
const DRAWING_COLORS = {
  arrow:           '#FF5252',
  trendline:       '#2962FF',
  horizontalRay:   '#FF9800',
  horizontalLine:  '#787B86',
  rectangle:       '#2962FF',
  longProfit:      'rgba(38, 166, 154, 0.15)',
  longLoss:        'rgba(239, 83, 80, 0.15)',
  shortProfit:     'rgba(38, 166, 154, 0.15)',
  shortLoss:       'rgba(239, 83, 80, 0.15)',
  measure:         '#787B86',
  controlPoint:    '#FFFFFF',
  controlPointBorder: '#2962FF',
  selectedOverlay: 'rgba(41, 98, 255, 0.1)',
};
```

### 附录 C：光标样式映射

```typescript
const CURSOR_MAP = {
  idle:        'default',
  placing:     'crosshair',
  hoverBody:   'move',
  hoverPoint:  'pointer',
  hoverHLine:  'ns-resize',
  hoverVLine:  'ew-resize',
  dragging:    'grabbing',
};
```

### 附录 D：控制点渲染规格

```
选中状态的控制点外观：
- 形状：圆形
- 半径：4px（普通）/ 5px（悬停时）
- 填充：白色
- 边框：2px, 画线主色
- 悬停效果：半径增大 + 阴影

矩形工具的边中点控制点：
- 形状：方形（4x4px）
- 其余同上
```

---

**文档版本**: v1.0
**创建日期**: 2025-01
**目标实现方**: TRAE AI
**工具数量**: 8 个
**预计总代码量**: ~4000-6000 行 TypeScript
**建议分**: 7 个 Phase 逐步实施，每个 Phase 结束后验证