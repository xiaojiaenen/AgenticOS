import { defineConfig } from 'vite'

// Vite 默认给产物里的 <link rel="stylesheet"> 和 <script type="module"> 加
// crossorigin 属性，浏览器因此按 CORS 规则去取这些资源。站点通常挂在子路径
// 或被直接以 file:// 打开预览，null origin 下 CORS 必然失败 —— 结果是页面
// 有 HTML 但完全没有样式（看着像"白屏/裸文本"）。这里在生成 HTML 时去掉它。
const stripCrossorigin = () => ({
  name: 'strip-crossorigin',
  transformIndexHtml(html) {
    return html.replace(/\s+crossorigin(=["'][^"']*["'])?/g, '')
  },
})

export default defineConfig({
  base: './',
  plugins: [stripCrossorigin()],
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
  },
  server: {
    port: 5173,
    open: false,
  },
})
