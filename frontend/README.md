<div align="center">
<img width="1200" height="475" alt="GHBanner" src="https://github.com/user-attachments/assets/0aa67016-6eaf-458a-adb2-6e31a0763ed6" />
</div>

# AgenticOS Frontend

这是 AgenticOS 的前端项目，负责聊天界面、管理页和流式响应展示。

## 本地运行

前置要求：`Node.js`

1. 安装依赖：`npm install`
2. 如有需要，复制环境变量模板并调整后端地址：`cp .env.example .env.local`
3. 启动开发服务器：`npm run dev`

默认情况下，Vite 会把 `/api` 请求代理到 `http://127.0.0.1:8000`，对应当前 FastAPI 后端。
