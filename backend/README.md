# AgenticOS

一个开箱即用的 FastAPI 项目骨架，包含：

- `app/main.py` 应用入口
- `app/api/` 路由分层
- `app/core/config.py` 环境配置
- `app/services/agent_service.py` Wuwei 智能体封装
- `tests/` 最小接口测试

## 快速开始

```bash
uv sync
uv run python main.py
```

服务启动后可访问：

- `http://127.0.0.1:8000/`
- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/api/v1/health/`
- `http://127.0.0.1:8000/api/v1/agent/stream`

## 开发

复制环境变量模板：

```bash
cp .env.example .env
```

运行测试：

```bash
uv run pytest
```

## Wuwei 流式接口

先配置大模型环境变量：

```bash
cp .env.example .env
```

至少需要填写：

```env
OPENAI_API_KEY=your_key
OPENAI_MODEL=gpt-5.4
```

请求示例：

```bash
curl -N -X POST http://127.0.0.1:8000/api/v1/agent/stream \
  -H "Content-Type: application/json" \
  -d '{"message":"帮我介绍一下这个项目","session_id":"demo-session"}'
```

返回格式是 `text/event-stream`，会按 `session`、`delta`、`tool_calls`、`done` 事件持续输出。
