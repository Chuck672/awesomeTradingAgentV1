import type { NextConfig } from "next";

const isElectron = process.env.ELECTRON === "true";
const allowedDevOriginsEnv = (process.env.ALLOWED_DEV_ORIGINS || "")
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);

const nextConfig: NextConfig = {
  // 允许在受控预览域名下访问 Next dev 资源（否则页面会“无 JS / 无交互”）
  // 说明：该配置仅影响 dev server；生产构建不需要。
  allowedDevOrigins: [
    "localhost:3000",
    "127.0.0.1:3000",
    "localhost:3123",
    "127.0.0.1:3123",
    "127.0.0.1",
    "localhost",
    // 当前预览环境 host（来自 dev server 日志）
    "run-agent-69d71dc31ff99054e6f370ee-mnzclha1-preview.agent-sandbox-my-c1-gw.trae.ai",
    // 另一种预览/代理 host（来自 dev server 日志）
    "run-agent-69d71dc31ff99054e6f370ee-mnzclha1.remote-agent.svc.cluster.local",
    // dev server 当前日志提示被 block 的 host（会导致页面“无交互/无K线”）
    "run-agent-69d71dc31ff99054e6f370ee-mnzv4rii.remote-agent.svc.cluster.local",
    "run-agent-69d71dc31ff99054e6f370ee-mnzv4rii-preview.agent-sandbox-my-c1-gw.trae.ai",
    ...allowedDevOriginsEnv,
  ],
  output: isElectron ? 'export' : undefined,
  images: isElectron ? { unoptimized: true } : undefined,
  assetPrefix: isElectron ? './' : undefined,
  async headers() {
    // 避免浏览器缓存 HTML 导致“无法强制刷新时一直加载旧版本 JS”
    if (isElectron) return [];
    return [
      {
        source: "/",
        headers: [{ key: "Cache-Control", value: "no-store, must-revalidate" }],
      },
      // Next 16 + Turbopack 在某些环境下 chunk 名可能不变，导致浏览器长期使用旧 JS。
      // 这里禁用 _next/static 缓存，确保普通“重新加载”也能拿到最新前端逻辑。
      {
        source: "/_next/static/:path*",
        headers: [{ key: "Cache-Control", value: "no-store, must-revalidate" }],
      },
    ];
  },
  async rewrites() {
    if (isElectron) return [];
    return [
      {
        source: '/api/:path*',
        destination: 'http://127.0.0.1:8123/api/:path*', // Proxy to Backend
      },
    ]
  },
};

export default nextConfig;
