# Frontend（Next.js + Lightweight Charts + Electron）

本目录包含 AwesomeTradingAgent 的桌面端 UI（Next.js App Router）与图表/指标插件实现。

更完整的系统架构、后端与触发器说明请查看仓库根目录 README：

- ../README.md

## 开发

```bash
npm ci
npm run dev
```

默认端口是 `3123`（见 [package.json](package.json)）。

## 构建（Electron）

```bash
npm run dist
```

构建产物输出到 `dist_electron/`（见 [package.json](package.json) build 配置）。
