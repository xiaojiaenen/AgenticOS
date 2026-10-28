# AgenticOS

[![CI](https://github.com/xiaojiaenen/AgenticOS/actions/workflows/ci.yml/badge.svg)](https://github.com/xiaojiaenen/AgenticOS/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/)
[![React 19](https://img.shields.io/badge/react-19-61dafb.svg)](https://react.dev/)

> 可自托管的 AI 智能体平台 —— 用对话生成 PPT、网站和文档，工具调用全程可审批。

AgenticOS 是一个前后端分离的智能体平台。它把「大模型 + 工具 + 技能 + 审批策略」
组装成可复用的智能体，让普通用户通过对话完成原本需要写代码或反复操作软件的任务。

**核心卖点**：用户用现有的 Skill、工具和审批策略**拼装**自己的智能体，
内置智能体只是示例。平台不锁定模型厂商，支持任意 OpenAI 兼容接口。

---

## 它能做什么

| 智能体 | 模式 | 产出 |
|---|---|---|
| **通用助手** | `general` | 日常问答、资料整理、轻量工具调用 |
| **PPT 设计师** | `ppt` | SVG 原生图形生成演示文稿，导出可编辑 `.pptx` |
| **网站工程师** | `website` | 页面方案、前端代码、交互原型，支持 Vue / React |
| **办公助手** | `office` | 可编辑的电子表格与文档（公式、样式保留） |
| **邮箱助手** | `email` | 邮件读取、搜索、发送、统计（IMAP / SMTP） |

### 关键能力

- **多智能体编排** —— Leader-Worker 并行分解复杂任务
- **HITL 人工审批** —— 工具调用按粒度授权，危险操作必须人工确认后才执行
- **会话级工作区** —— 每个会话独立文件沙箱，AI 只能读写自己的 `uploads/` 与 `outputs/`
- **知识库 + 知识图谱** —— 混合检索（字面 + 语义 + 重排），Wiki 化沉淀
- **Skill 系统** —— 本地技能包，可热插拔
- **MCP 支持** —— 接入外部 MCP 服务作为工具来源
- **企业级后台** —— 用户/角色/策略、审计日志、用量统计、AI 提供商管理
- **私有化部署** —— Docker Compose 一键起，数据不出内网

---

## 快速开始

### 前置要求

- Python 3.13
- Node.js 22+（仅构建前端时需要）
- [uv](https://docs.astral.sh/uv/)（Python 包管理）

### 本地开发

```bash
# 1. 后端
cd backend
cp .env.example .env          # 填入 OPENAI_API_KEY 与 AUTH_SECRET_KEY
uv sync
uv run python main.py         # http://127.0.0.1:8001

# 2. 前端（另开终端）
cd frontend
npm install
npm run dev                   # http://127.0.0.1:3001
```

首次访问时**第一个注册的用户自动成为管理员**。

### Docker 部署

```bash
cd deploy
cp .env.example .env          # 必填：AUTH_SECRET_KEY、DATABASE_URL、OPENAI_API_KEY
docker compose up -d --build
```

- 前端：`http://<host>:10008`
- 后端：`http://<host>:10007`

详见 [deploy/DEPLOY.md](deploy/DEPLOY.md)。

---

## 配置

最小可用配置（`backend/.env`）：

```bash
# 必填
AUTH_SECRET_KEY=<随机 32+ 字符>
OPENAI_API_KEY=<你的 key>

# 模型端点（支持任意 OpenAI 兼容接口）
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_MODEL=deepseek-chat
```

完整环境变量见 `backend/.env.example`。

### 企业网关 / 自建模型

平台内置通用厂商预设（OpenAI、DeepSeek 等）。企业内网网关（自签证书、
SSO 登录、私有模型注册表）通过**外部预设插件**接入，无需改代码：

```bash
# 1. 写一个插件文件，例如 /opt/presets/my_gateway.py
#    导出 PRESETS = [ProviderPreset(...)]
# 2. 指向该目录
PROVIDER_PRESETS_DIR=/opt/presets
```

参考 `backend/tests/fixtures/presets/acme_gateway.py` 的完整示例。

---

## 项目结构

```text
AgenticOS/
├── backend/                  # FastAPI 后端
│   ├── app/
│   │   ├── api/v1/endpoints/ # 接口定义
│   │   ├── core/             # 配置、安全、路径
│   │   ├── db/               # ORM 模型
│   │   ├── services/         # Agent / Skill / 知识库 / PPT 等
│   │   └── tools/            # 工具实现
│   ├── alembic/              # 数据库迁移
│   └── tests/                # 679 个测试
├── frontend/                 # React 19 + Vite + Tailwind 4
│   └── src/
│       ├── pages/            # 路由页面
│       ├── components/       # chat / admin / ppt / ui
│       └── services/         # API 客户端
├── data/                     # 运行数据
│   ├── icons/ design-themes/ # 只读资产
│   └── workspaces/ websites/ # 运行时产物（不入库）
├── docs/                     # 设计文档、调研、部署说明
└── deploy/                   # Docker 与 nginx 配置
```

---

## 开发

```bash
# 后端测试
cd backend && uv run pytest

# 前端类型检查
cd frontend && npm run lint

# 前端构建
cd frontend && npm run build
```

### 设计约定

- 品牌色 `#2b87c2`，只用于主 CTA 与焦点态
- 字号权重只用 `font-medium`(500) / `font-semibold`(600)
- 圆角：控件 8px / 卡片 12px / 弹层 16px
- 阴影：双层叠加，`shadow-sm` 到 `shadow-xl`

详见 [DESIGN.md](DESIGN.md)。

---

## 贡献

欢迎提 Issue 和 PR。请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。

发现安全漏洞请**不要**公开提 Issue，按 [SECURITY.md](SECURITY.md) 的渠道私下报告。

---

## 许可

[MIT](LICENSE)
