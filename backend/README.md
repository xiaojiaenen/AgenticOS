# Backend

后端默认运行在 `http://127.0.0.1:8001`，完整启动与 Docker 部署说明请优先查看仓库根目录 [README.md](../README.md)。

## 本地启动

```bash
cd backend
uv sync
cp .env.example .env
uv run python main.py
```

常用地址：

- `http://127.0.0.1:8001/`
- `http://127.0.0.1:8001/docs`
- `http://127.0.0.1:8001/api/v1/health/`

## 关键说明

- 默认数据库：`./data/agenticos.db`
- 默认 Skill 目录：`./data/skills`
- 第一个注册账号会自动成为管理员
- Skill 工具默认开启审批，管理员可在后台继续调整
