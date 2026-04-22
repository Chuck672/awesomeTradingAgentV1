# 项目需求说明书：基于 Lightweight Charts 构建 Volume Profile (VRVP) 插件

## 1. 项目概述
本项目旨在利用 TradingView 的 `lightweight-charts` (版本需 >= 4.0.0) 的 `Custom Series API`，开发一个高级指标插件：**可见范围成交量分布图 (VRVP - Visible Range Volume Profile)**。
该指标需要在主图表表层通过 Canvas 绘制水平方向的直方图、POC 线（控制点）以及价值区域（Value Area）。

## 2. 技术栈约束
- **构建工具**: Vite
- **语言**: TypeScript (纯 TS/JS 环境，不使用 React/Vue 等前端框架，以保证插件的通用性)
- **核心库**: `lightweight-charts` (最新版)
- **其他**: 无其他第三方依赖（如 lodash 等请手动实现简单版本以保持轻量）

## 3. 项目目录结构预设
请严格按照以下目录结构生成代码：
```text
/src
  /plugins
    /VolumeProfile
      types.ts           # 数据接口和配置项类型定义
      Calculator.ts      # 纯逻辑：将 OHLCV 数据转换为 Profile Bins
      Renderer.ts        # 纯 UI：实现 ICustomSeriesPaneRenderer 操作 Canvas
      View.ts            # 桥梁：实现 ICustomSeriesPaneView
      index.ts           # 插件导出统一入口
  /utils
    mockData.ts          # 生成 500 条随机的带有 Volume 的 OHLCV K线数据
    debounce.ts          # 防抖函数
  main.ts                # 项目入口：初始化图表、加载插件、监听范围变化
  style.css              # 基础全屏图表样式
index.html
package.json