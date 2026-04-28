# Frontend

前端默认运行在 `http://127.0.0.1:3001`，完整启动与 Docker 部署说明请优先查看仓库根目录 [README.md](../README.md)。

## 本地启动

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

默认联调口径：

- 前端：`http://127.0.0.1:3001`
- 后端：`http://127.0.0.1:8001`

开发环境下，Vite 会把 `/api` 代理到 `http://127.0.0.1:8001`。
