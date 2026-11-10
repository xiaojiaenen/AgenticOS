import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 去掉产物里的 crossorigin：站点常挂在子路径或被 file:// 直接预览，
// null origin 下带 crossorigin 的 CSS/JS 会被 CORS 拦掉，页面只剩裸 HTML。
const stripCrossorigin = () => ({
  name: 'strip-crossorigin',
  transformIndexHtml(html) {
    return html.replace(/\s+crossorigin(=["'][^"']*["'])?/g, '')
  },
})

export default defineConfig({
  plugins: [react(), stripCrossorigin()],
  base: './',
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
  },
  resolve: {
    alias: {
      '@': '/src',
    },
  },
  server: {
    port: 5173,
    open: false,
  },
})
