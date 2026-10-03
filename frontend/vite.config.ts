import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import legacy from '@vitejs/plugin-legacy';
import path from 'path';
import { defineConfig, loadEnv } from 'vite';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '');
  const apiProxyTarget = env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8001';

  return {
    plugins: [
      react(),
      tailwindcss(),
      // 低版本浏览器兼容（Chrome 85+，CSS 目标同步收紧）
      // 生成降级 bundle + 自动 polyfill
      legacy({
        targets: ['Chrome >= 85', 'Edge >= 85', 'Firefox >= 78', 'Safari >= 13'],
        additionalLegacyPolyfills: ['regenerator-runtime/runtime'],
        modernPolyfills: true,
        renderLegacyChunks: true,
      }),
    ],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, 'src'),
      },
    },
    server: {
      port: 3001,
      proxy: {
        '/api': {
          target: apiProxyTarget,
          changeOrigin: true,
        },
        // 已部署站点与构建产物由后端 StaticFiles 挂载（app/main.py）。
        // 生产环境走 nginx 的 location /sites/；开发环境不转发的话，
        // /sites/xxx 会被 Vite 的 SPA fallback 吞掉、返回 AgenticOS 自己的
        // index.html，管理员点「访问」看起来就像"部署没有任何变化"。
        '/sites': {
          target: apiProxyTarget,
          changeOrigin: true,
        },
        '/preview': {
          target: apiProxyTarget,
          changeOrigin: true,
        },
      },
      hmr: process.env.DISABLE_HMR !== 'true',
    },
    build: {
      // CSS 降级目标，确保低版本浏览器能解析
      cssTarget: 'chrome85',
      rollupOptions: {
        output: {
          manualChunks: {
            'react-core': ['react', 'react-dom', 'react-router-dom'],
            'motion-vendor': ['motion'],
            // 注意：mermaid / echarts（含 zrender）不在此列出 —— 两者仅被动态 import
            // （ChatMessageSubComponents 的 import('mermaid') / import('echarts')），
            // 加入 manualChunks 会废掉动态导入的懒加载语义，打进首屏 chunk。
            'markdown-vendor': [
              'react-markdown',
              'remark-gfm',
              'remark-math',
              'rehype-katex',
              'katex',
              'react-syntax-highlighter',
            ],
            // lucide-react 被聊天组件（ChatMessage 等）直接静态 import，
            // 放入 admin-vendor 会导致聊天页加载 recharts；移除后跟随使用方 chunk 拆分。
            'admin-vendor': ['recharts'],
            // echarts 仅被动态 import（import('echarts')），但实测仍会被并入首屏 entry chunk，
            // 显式独立成 chunk 保证懒加载（zrender 作为其唯一依赖会被一并归入该 chunk）。
            'echarts-vendor': ['echarts'],
          },
        },
      },
    },
  };
});
