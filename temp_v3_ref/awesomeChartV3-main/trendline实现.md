

# TradingView 趋势线 选中/取消选中 核心逻辑

## 一句话本质

> **每次 mousedown，先做一次「全局命中检测」，命中了就选中它，没命中任何东西就取消当前选中。**

---

## 完整状态流转

```
                        ┌──────────────┐
            ┌──────────►│  IDLE 空闲    │◄─────────────┐
            │           │ selected=null │               │
            │           │ 无控制圆点    │               │
            │           └──────┬───────┘               │
            │                  │                        │
            │          mousedown 事件触发                │
            │                  │                        │
            │           ┌──────▼───────┐                │
            │           │  HitTest     │                │
            │           │  命中检测     │                │
            │           └──┬───────┬───┘                │
            │              │       │                    │
            │         命中画线   未命中任何画线            │
            │              │       │                    │
            │              ▼       └──── (已经是IDLE,    │
            │     ┌────────────────┐      无事发生)      │
            │     │  SELECTED      │                    │
            │     │  selected=该画线│                    │
            │     │  显示控制圆点🔵 │                    │
            │     └───────┬────────┘                    │
            │             │                             │
            │     再次 mousedown                         │
            │             │                             │
            │      ┌──────▼───────┐                     │
            │      │  HitTest     │                     │
            │      └──┬──────┬──┬─┘                     │
            │         │      │  │                       │
            │    命中控制点  命中body  未命中任何东西       │
            │         │      │  │                       │
            │         ▼      ▼  └───────────────────────┘
            │     DRAGGING  DRAGGING         取消选中
            │    (拖控制点) (拖整体)        selected=null
            │         │      │             圆点消失🔵→无
            │      mouseup  mouseup
            │         │      │
            │         ▼      ▼
            │     回到 SELECTED
            │     (圆点仍显示)
            │             │
            │     再次点击空白
            └─────────────┘
```

---

## 核心代码逻辑（伪代码）

```typescript
class DrawingManager {
  
  private _selectedDrawing: BaseDrawing | null = null;
  private _drawings: BaseDrawing[] = [];
  
  /**
   * ========================================
   *  核心：mousedown 处理
   *  这个方法就是一切选中/取消选中的根源
   * ========================================
   */
  private _onMouseDown(e: MouseEvent): void {
    const mousePixel = this._getMousePixel(e);
    
    // ━━━━ Step 1: 对所有画线做命中检测 ━━━━
    const hitResult = this._hitTestAll(mousePixel);
    
    if (hitResult) {
      // ━━━━ 命中了某个画线 ━━━━
      
      if (hitResult.drawing === this._selectedDrawing) {
        // Case A: 点的是「当前已选中的画线」
        
        if (hitResult.type === 'point') {
          // A1: 命中了控制圆点 → 开始拖控制点
          this._startDragPoint(hitResult.drawing, hitResult.pointIndex!);
        } else {
          // A2: 命中了线段body → 开始拖整体
          this._startDragBody(hitResult.drawing);
        }
        
      } else {
        // Case B: 点的是「另一条画线」(不是当前选中的)
        // → 先取消旧的，再选中新的
        this._deselectCurrent();
        this._select(hitResult.drawing);
      }
      
      // 关键：阻止事件继续传播给图表
      e.stopPropagation();
      e.preventDefault();
      
    } else {
      // ━━━━ 没命中任何画线（点了空白处） ━━━━
      
      // Case C: 取消当前选中
      this._deselectCurrent();
      
      // 不阻止事件 → 图表正常拖拽/缩放
    }
  }
  
  /**
   * 选中一条画线
   */
  private _select(drawing: BaseDrawing): void {
    this._selectedDrawing = drawing;
    drawing.setSelected(true);   // ← 画线内部标记 _selected = true
    drawing.requestRedraw();      // ← 触发重绘，这次重绘会画出控制圆点
  }
  
  /**
   * 取消当前选中
   */
  private _deselectCurrent(): void {
    if (this._selectedDrawing) {
      this._selectedDrawing.setSelected(false);  // ← _selected = false
      this._selectedDrawing.requestRedraw();       // ← 重绘，圆点不再绘制
      this._selectedDrawing = null;
    }
  }
  
  /**
   * 遍历所有画线做命中检测
   * 从最上层（后创建的）开始检测，第一个命中的就返回
   */
  private _hitTestAll(pixel: PixelPoint): HitTestResult | null {
    // 倒序遍历：后添加的画线在上层，优先命中
    for (let i = this._drawings.length - 1; i >= 0; i--) {
      const drawing = this._drawings[i];
      const result = drawing.hitTest(pixel, 5); // 5px 容差
      if (result) return result;
    }
    return null;
  }
}
```

---

## 画线内部的渲染分支

```typescript
class TrendlineDrawing extends BaseDrawing {
  
  private _selected: boolean = false;  // ← 这就是控制圆点显示的开关
  
  /**
   * 渲染方法（每帧调用）
   */
  draw(ctx: CanvasRenderingContext2D): void {
    const p0 = this._toPixel(this._points[0]);
    const p1 = this._toPixel(this._points[1]);
    if (!p0 || !p1) return;
    
    // ━━━━ 始终绘制：线段本身 ━━━━
    ctx.strokeStyle = this._style.lineColor;
    ctx.lineWidth = this._style.lineWidth;
    ctx.beginPath();
    ctx.moveTo(p0.x, p0.y);
    ctx.lineTo(p1.x, p1.y);
    ctx.stroke();
    
    // ━━━━ 仅在选中时绘制：控制圆点 ━━━━
    if (this._selected) {
      this._drawControlPoint(ctx, p0);  // 🔵 起点圆点
      this._drawControlPoint(ctx, p1);  // 🔵 终点圆点
    }
  }
  
  /**
   * 绘制单个控制圆点
   */
  private _drawControlPoint(ctx: CanvasRenderingContext2D, p: PixelPoint): void {
    ctx.beginPath();
    ctx.arc(p.x, p.y, 4, 0, Math.PI * 2);   // 半径 4px
    ctx.fillStyle = '#FFFFFF';                 // 白色填充
    ctx.fill();
    ctx.strokeStyle = this._style.lineColor;   // 边框用线段颜色
    ctx.lineWidth = 2;
    ctx.stroke();
  }
}
```

---

## 命中检测细节

```typescript
class TrendlineDrawing extends BaseDrawing {
  
  hitTest(pixel: PixelPoint, tolerance: number): HitTestResult | null {
    const p0 = this._toPixel(this._points[0]);
    const p1 = this._toPixel(this._points[1]);
    if (!p0 || !p1) return null;
    
    // ━━ 优先级1: 检测控制圆点（仅在已选中时才检测） ━━
    if (this._selected) {
      if (distance(pixel, p0) <= 8) {
        return { 
          drawing: this, 
          type: 'point', 
          pointIndex: 0, 
          cursor: 'pointer'   // 手指光标
        };
      }
      if (distance(pixel, p1) <= 8) {
        return { 
          drawing: this, 
          type: 'point', 
          pointIndex: 1, 
          cursor: 'pointer' 
        };
      }
    }
    
    // ━━ 优先级2: 检测线段body ━━
    const dist = pointToSegmentDistance(pixel, p0, p1);
    if (dist <= tolerance) {
      return { 
        drawing: this, 
        type: 'body', 
        cursor: 'move'       // 移动光标
      };
    }
    
    // ━━ 未命中 ━━
    return null;
  }
}
```

> **注意**：控制圆点的命中检测只在 `_selected === true` 时才执行。这意味着：
> - 未选中的画线 → 只能通过点击线段body来命中
> - 已选中的画线 → 先检测圆点，再检测body

---

## 用文字走一遍完整交互流

```
场景：图表上有一条趋势线 T1，初始状态未选中

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【操作1】用户鼠标靠近 T1 线段
  → mousemove → hitTest → 命中 T1 body
  → 光标变为 'move' ✋
  → T1 内部 _hovered = true（可选：线段轻微高亮）

【操作2】用户点击 T1 线段
  → mousedown → hitTest → 命中 T1 body
  → _select(T1)
    → T1._selected = true
    → 重绘 → 线段 + 两个白色控制圆点🔵🔵出现
  → 阻止事件传播（图表不被拖动）
  
  当前状态：T1 被选中，显示圆点

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【操作3】用户鼠标移到圆点上
  → mousemove → hitTest → 命中 T1 的 point(index=0)
  → 光标变为 'pointer' 👆
  
【操作4】用户拖拽圆点
  → mousedown → 命中 point → 开始拖拽
  → mousemove → 更新 points[0] 坐标 → 重绘
  → mouseup → 结束拖拽 → 回到 SELECTED 状态
  → 圆点仍然显示🔵🔵

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【操作5】用户点击空白处
  → mousedown → hitTest → 遍历所有画线 → 没有命中任何东西
  → _deselectCurrent()
    → T1._selected = false
    → 重绘 → 仅线段，圆点消失 🔵🔵→ ∅
  → 不阻止事件 → 图表正常响应（拖拽/缩放）
  
  当前状态：无选中画线

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【操作6】用户再次点击 T1
  → mousedown → hitTest → 命中 T1 body
  → _select(T1) → 圆点再次出现🔵🔵

【操作7】用户再次点击空白处
  → _deselectCurrent() → 圆点再次消失
```

---

## 总结：核心设计模式

```
┌─────────────────────────────────────────────────┐
│                                                  │
│   每次 mousedown:                                │
│                                                  │
│   1. hitTestAll(鼠标位置)                        │
│      └→ 遍历所有画线 → 找第一个命中的             │
│                                                  │
│   2. 命中了？                                    │
│      ├── YES → select(它)    → 圆点出现 🔵       │
│      │         阻止事件冒泡                       │
│      │                                           │
│      └── NO  → deselectAll() → 圆点消失 ∅        │
│               放行事件给图表                      │
│                                                  │
│   3. 画线渲染时:                                  │
│      if (_selected) → 画线段 + 画圆点             │
│      else           → 只画线段                    │
│                                                  │
│   就这么简单。                                    │
│                                                  │
└─────────────────────────────────────────────────┘
```

三个关键点：
1. **`_selected` 布尔值** 控制圆点是否绘制
2. **hitTest 命中检测** 决定点击的是画线还是空白
3. **mousedown 是唯一入口**，所有选中/取消选中都在这里发生