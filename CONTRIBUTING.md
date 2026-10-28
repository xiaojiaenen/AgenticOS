# 贡献指南

感谢你愿意参与 AgenticOS。

## 开发环境

```bash
# 后端
cd backend
uv sync
uv run pytest          # 679 个测试，提交前必须全绿

# 前端
cd frontend
npm install
npm run lint           # tsc --noEmit
npm run build
```

## 提交前检查清单

- [ ] `cd backend && uv run pytest` 全绿
- [ ] `cd frontend && npm run lint` 无错误
- [ ] 新增功能有对应测试
- [ ] 没有提交 `.env`、密钥、数据库文件、构建产物
- [ ] 提交信息说明了「为什么」而不只是「改了什么」

## 提交信息规范

使用 [Conventional Commits](https://www.conventionalcommits.org/)：

```
feat(workspace): 会话级工作区隔离，修复 AI 看到 /app 源码树
fix(agent): 修复多轮对话 ActionLog 序列化崩溃
docs(deploy): 补充 nginx 上游解析说明
refactor(ppt): 幻灯片目录并入会话工作区
```

类型：`feat` / `fix` / `refactor` / `docs` / `test` / `chore` / `perf`

**优先解释问题与根因**，而不是罗列改动。好的提交信息能让 review 者
不用读 diff 就知道这段代码在解决什么。

## 代码风格

### 后端（Python）

- 遵循 PEP 8，行宽 100
- 类型注解尽量完整（`from __future__ import annotations`）
- **注释解释「为什么」，不解释「是什么」** —— 代码本身能说明是什么
- 遇到上游缺陷/踩坑，把坑写进注释，避免下一个人重踩

### 前端（TypeScript / React）

- 函数组件 + hooks，不写 class 组件
- 样式用 Tailwind 工具类，遵循 `DESIGN.md` 的 token 约定
- 组件文件超过 400 行考虑拆分
- 交互元素必须有 `aria-label` 或可见文本

## 目录约定

| 路径 | 用途 |
|---|---|
| `backend/app/api/v1/endpoints/` | HTTP 接口，按资源分文件 |
| `backend/app/services/` | 业务逻辑，不依赖 FastAPI |
| `backend/app/tools/` | 智能体可调用的工具 |
| `frontend/src/components/admin/` | 管理后台组件 |
| `frontend/src/components/chat/` | 对话界面组件 |
| `docs/design/` | 架构设计文档 |
| `docs/research/` | 技术调研 |

## 新增一个工具

1. 在 `backend/app/tools/` 下实现，用 `@registry.tool(...)` 装饰
2. 在 `tool_config_service.TOOL_CATALOG` 里登记（label / description / 子工具）
3. 若需审批，在 `approval_policy.READ_ONLY_TOOLS` 里判定只读与否
4. 补测试：至少覆盖成功路径 + 一个失败路径

## 新增一个 AI 提供商预设

通用厂商加进 `presets.GENERIC_PRESETS`。企业内网网关**不要**写进仓库，
用外部插件（见 README 的「企业网关」一节）。

## 报告问题

提 Issue 时请包含：

- 复现步骤
- 期望行为 vs 实际行为
- 相关日志（**去掉密钥、Cookie、内网地址**）
- 环境（操作系统、Python/Node 版本、部署方式）

## 行为准则

参与本项目即表示你同意遵守 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。
