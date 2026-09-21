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
      // 低版本浏览器兼容（Win7 / Chrome 83+ / Edge 80+）
      // 生成降级 bundle + 自动 polyfill
      legacy({
        targets: ['Chrome >= 80', 'Edge >= 80', 'Firefox >= 78', 'Safari >= 13'],
        additionalLegacyPolyfills: ['regenerator-runtime/runtime'],
        modernPolyfills: true,
        renderLegacyChunks: true,
      }),
    ],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, '.'),
        '@xiaojiaenen/liquid-glass': path.resolve(__dirname, 'node_modules/@xiaojiaenen/liquid-glass/dist/lib/index.js'),
      },
    },
    server: {
      port: 3001,
      proxy: {
        '/api': {
          target: apiProxyTarget,
          changeOrigin: true,
        },
      },
      hmr: process.env.DISABLE_HMR !== 'true',
    },
    build: {
      // CSS 降级目标，确保低版本浏览器能解析
      cssTarget: 'chrome87',
      rollupOptions: {
        output: {
          manualChunks: {
            'react-core': ['react', 'react-dom', 'react-router-dom'],
            'motion-vendor': ['motion'],
            'markdown-vendor': [
              'react-markdown',
              'remark-gfm',
              'remark-math',
              'rehype-katex',
              'katex',
              'mermaid',
              'react-syntax-highlighter',
            ],
            'admin-vendor': ['recharts', 'lucide-react'],
          },
        },
      },
    },
  };
});
