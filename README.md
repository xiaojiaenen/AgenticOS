# AgenticOS

AgenticOS 是一个前后端分离的智能体应用示例项目。

当前项目包含两部分：

- `backend/`：基于 FastAPI 的后端服务，负责封装 `wuwei` 智能体并提供流式接口
- `frontend/`：基于 React + Vite 的聊天前端，负责展示对话内容、Markdown、代码块、表格和工具调用状态

项目目前已经完成了基础聊天闭环：

- 前端发送问题到后端
- 后端通过 `wuwei` 调用模型并流式返回
- 前端实时渲染增量回复
- 工具调用过程和结果可在界面中展示

## 项目结构

```text
AgenticOS/
├─ backend/                # FastAPI 后端
│  ├─ app/
│  │  ├─ api/              # 路由定义
│  │  ├─ core/             # 配置与基础能力
│  │  ├─ schemas/          # 请求/响应数据模型
│  │  ├─ services/         # 智能体服务封装
│  │  └─ main.py           # FastAPI 应用入口
│  ├─ tests/               # 后端测试
│  ├─ .env.example         # 后端环境变量示例
│  ├─ pyproject.toml
│  └─ README.md
├─ frontend/               # React 前端
│  ├─ src/
│  │  ├─ components/       # 界面组件
│  │  ├─ pages/            # 页面
│  │  ├─ services/         # 前端请求封装
│  │  └─ types.ts          # 类型定义
│  ├─ .env.example         # 前端环境变量示例
│  ├─ package.json
│  └─ README.md
└─ README.md               # 当前文档
```

## 技术栈

- 后端：FastAPI、Pydantic Settings、Uvicorn、Wuwei
- 前端：React、TypeScript、Vite、React Markdown
- 模型接入：OpenAI 兼容接口

## 环境要求

建议使用以下环境：

- Python `3.13+`
- Node.js `22`
- `uv`
- `npm`

如果你的本地 Node 版本不是 22，可以先切换：

```bash
nvm use 22
```

## 一、启动后端

进入后端目录：

```bash
cd backend
```

安装依赖：

```bash
uv sync
```

复制环境变量模板：

```bash
cp .env.example .env
```

至少需要配置这些字段：

```env
OPENAI_API_KEY=your_api_key
OPENAI_MODEL=gpt-5.4
```

如需使用兼容网关，也可以补充：

```env
OPENAI_BASE_URL=https://your-openai-compatible-endpoint
```

启动服务：

```bash
uv run python main.py
```

启动后默认地址：

- 首页：[http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- Swagger 文档：[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- 健康检查：`http://127.0.0.1:8000/api/v1/health/`
- 智能体流式接口：`http://127.0.0.1:8000/api/v1/agent/stream`

## 二、启动前端

进入前端目录：

```bash
cd frontend
```

安装依赖：

```bash
npm install
```

复制环境变量模板：

```bash
cp .env.example .env.local
```

默认情况下：

- `VITE_API_BASE_URL` 指向 `http://127.0.0.1:8000`
- 前端开发服务器端口是 `3000`

启动前端：

```bash
npm run dev
```

启动后可在浏览器访问：

- [http://127.0.0.1:3000](http://127.0.0.1:3000)

## 三、联调方式

推荐按下面顺序联调：

1. 启动后端服务，确认 `http://127.0.0.1:8000/docs` 可以打开
2. 调用健康检查接口，确认后端正常
3. 启动前端服务
4. 在页面中直接发起对话，观察流式回复和工具调用展示

你也可以直接用 `curl` 验证后端流式接口：

```bash
curl -N -X POST http://127.0.0.1:8000/api/v1/agent/stream \
  -H "Content-Type: application/json" \
  -d '{
    "message": "请先告诉我现在时间，再总结一下 AgenticOS 是做什么的",
    "session_id": "demo-session"
  }'
```

当前接口返回 `text/event-stream`，前端会消费这些事件：

- `session`
- `delta`
- `tool_calls`
- `tool_results`
- `done`
- `error`

## 四、后端环境变量说明

后端主要环境变量位于 `backend/.env`：

```env
APP_NAME=AgenticOS API
APP_VERSION=0.1.0
ENVIRONMENT=development
API_V1_PREFIX=/api/v1
CORS_ALLOW_ORIGINS=http://127.0.0.1:3000,http://localhost:3000
OPENAI_API_KEY=
OPENAI_BASE_URL=
OPENAI_MODEL=gpt-5.4
AGENT_SYSTEM_PROMPT=你是 AgenticOS 的 AI 助手。
AGENT_MAX_STEPS=10
AGENT_PARALLEL_TOOL_CALLS=false
```

说明：

- `OPENAI_API_KEY`：模型服务密钥
- `OPENAI_BASE_URL`：可选，自定义兼容接口地址
- `OPENAI_MODEL`：模型名称
- `AGENT_SYSTEM_PROMPT`：默认系统提示词
- `AGENT_MAX_STEPS`：智能体最大迭代步数
- `AGENT_PARALLEL_TOOL_CALLS`：是否允许并行工具调用

## 五、当前功能说明

目前项目已经支持：

- 基础聊天问答
- 多轮会话 `session_id`
- SSE 流式回复
- 工具调用信息回传
- Markdown 渲染
- 代码块渲染
- 表格渲染与样式优化
- 前端工具调用区域展示

## 六、常用命令

后端：

```bash
cd backend
uv sync
uv run python main.py
uv run pytest
```

前端：

```bash
cd frontend
npm install
npm run dev
npm run build
npm run lint
```

## 七、后续可继续优化的方向

- 把 `wuwei` 的工具事件输出进一步标准化
- 增加更完整的工具调用时间线展示
- 增加会话持久化能力
- 补充部署文档和 Docker 支持
- 增加管理页与配置页能力

## 八、说明

`backend/README.md` 和 `frontend/README.md` 分别保留了子项目级别的说明。

如果你只想快速跑通整个项目，优先看当前这个根目录 `README.md` 即可。
