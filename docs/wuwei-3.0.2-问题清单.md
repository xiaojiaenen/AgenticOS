# wuwei 3.0.2 问题清单（供上游反馈）

> **状态更新（2026-10-28）：本清单针对 3.0.2，其中多数问题已在 3.2.1 修复。**
>
> 升级到 3.2.1 后的实测结论（同一组真实 SDK 响应对象做对照）：
>
> | 3.0.2 的问题 | 3.2.1 现状 |
> | --- | --- |
> | usage 收尾帧被吞（流式 token 恒为 0） | **已修** —— `parse_stream_chunk` 对 `choices: []` 的帧返回 `{"usage": ...}`，网关循环直接累加 usage |
> | 非流式缺 usage 直接 `AttributeError` | **已修** —— `_parse_usage` 逐字段 `getattr`，缺字段返回 0 |
> | 非常规 `finish_reason` 触发 pydantic `ValidationError` | **已修** —— `finish_reason` 从 `Literal` 放宽为 `str`，另有 `normalize_finish_reason` 归一化 + `raw_finish_reason` 保留原值 |
> | 错误分类用 `"500" in str(exc)` 字符串匹配 | **已修** —— 改为读 `status_code` 属性，端口 5000 的 401 不会再被当成 5xx 重试 |
> | 除 openai 外四个适配器流式不可用 | **结构性变更** —— zhipu / dashscope / ollama 适配器**已从包内移除**，只保留 openai / anthropic / responses |
> | 工具调用在非标 `finish_reason` 下丢失 | **已修** —— 网关用 `pending` 增量组装，缺失 id/name 直接报错而不是静默丢弃 |
> | 并发工具执行需自行 monkey-patch | **已修** —— `ToolExecutor.execute(concurrent=True)` 原生按 `is_concurrency_safe` 分批并发 |
>
> 仍然存在的差异（升级时必须适配）：
>
> - **`ApprovalRequest` / `ApprovalDecision` 已删除** —— 审批重构为「抛 `InterruptSignal` + checkpointer 持久化 + `Agent.resume()` 恢复」。
>   AgenticOS 的审批是跨进程 + 前端交互的（Redis pub/sub + SSE + DB），
>   走的是 `approval_provider` 回调模式（该模式 3.2.1 保持不变），
>   但那两个数据结构类已不复存在，改由 `app/services/approval_types.py` 自持。
> - **`openai` SDK 跨大版本到 3.x** —— 唯一破坏性变更是「HTTPX2 成为默认客户端」。
>   显式传 `httpx.AsyncClient` 仍可用（实测流式与非流式均正常），
>   但 `httpx` 不再被 openai 自动安装，必须显式声明依赖。
> - **`OpenAIAdapter.__init__` 新增 `client` / `client_factory` / `owns_client` 注入点** ——
>   之前需要手写 `self.client = ...` 绕过父类的做法已不必要，且那种写法会漏掉
>   父类设置的字段（`supports_reasoning_content` 等），3.2.1 下直接 `AttributeError`。
>
> 下面的原始清单保留作为**问题演进的记录**，但不要再照着它去改代码 ——
> 多数缺陷上游已修，照着改会引入不必要的补丁。

审查对象：`wuwei==3.0.2`（`site-packages/wuwei`，Homepage: github.com/xiaojiaenen/wuwei）
审查范围：`llm/gateway.py`、`llm/adapters/*`、`llm/types.py`、`core/types.py`、`core/message.py`、`runtime/agent_runner.py`
方法：通读源码 + 构造真实 SDK 响应对象做动态验证（不依赖网络），另用本地假网关验证重试/fallback 行为。
结论：**非流式只有 `openai` 适配器可用；流式五个 provider 全有缺陷，四个直接崩。**

严重度：**P0 = 功能不可用 / 数据错**，**P1 = 静默错误 / 行为与文档不符**，**P2 = 结构缺陷**。

---

## P0-1 除 openai 外，四个适配器的流式全部不可用

`build_request(stream=True)` 收下了 `stream` 参数，但**没有写进请求体**：

- `llm/adapters/zhipu.py:41-62`
- `llm/adapters/dashscope.py:41-52`
- `llm/adapters/ollama.py`（同结构）
- `llm/adapters/anthropic.py:78-91`

实测（`build_request([], None, stream=True)`）：

```
[Ollama]    stream in request? False  keys=['model','messages','max_tokens','temperature']
[Zhipu]     stream in request? False
[DashScope] stream in request? False
```

后果：`call()` 拿到的是普通响应对象，`gateway._generate_stream:368` 的 `async for chunk in stream` 直接
`TypeError: 'ChatCompletion' object is not async iterable`。

建议：`request["stream"] = stream`；Anthropic 还要走 `client.messages.create(stream=True)`（或 `.stream()`）。

---

## P0-2 ollama / zhipu / dashscope 的 `parse_response` 必然 ValidationError

三个适配器都返回 `LLMResponse(content=..., tool_calls=...)`，但 `llm/types.py:9` 的 `LLMResponse`
要求 `message: Message`，且 `latency_ms` 必填。实测：

```
[Ollama]    parse_response -> ValidationError: 2 validation errors
              message Field required
[Zhipu]     parse_response -> ValidationError: 2 validation errors
[DashScope] parse_response -> ValidationError: 2 validation errors
```

根因是**同名类两份定义**：`core/types.py:15` 的旧 `LLMResponse`（`content`/`tool_calls` 形态）与
`llm/types.py:9` 的新 `LLMResponse`（`message` 形态）。这三个适配器是按旧形态写的，改新形态时漏改。
外部 `from wuwei import LLMResponse` 拿到哪一个取决于 `__init__` 导出，是个隐形地雷。

建议：删掉 `core/types.py` 的重复定义，或改名（`LegacyLLMResponse`）并在 `llm/types.py` 加注释说明契约变更。

---

## P0-3 流式 usage 恒为 0（openai 适配器同样中招）

`OpenAIAdapter.parse_stream_chunk:99-100`：

```python
if not chunk.choices:
    return None
```

而 `stream_options={"include_usage": True}` 的收尾帧恰恰是 `choices: []` + `usage`；
`gateway._generate_stream:370` 见 `None` 就 `continue`。结果：**所有流式调用的 token 统计恒为 0**，
计费、配额、审计、`agent_usage_events` 全部失真。

建议：`not chunk.choices` 但 `chunk.usage` 存在时返回 `{"content": "", "usage": {...}}`；
gateway 优先读 `data["usage"]`，不要绕过适配器直接读 `chunk.usage`（见 P1-8）。

---

## P0-4 `finish_reason` 用严格 Literal，上游换个词整轮就崩

`llm/types.py:11` 与 `:24` 只允许 `stop | tool_calls | length | content_filter`。实测：

```
max_tokens     -> ValidationError (Anthropic 原生)
function_call  -> ValidationError (旧 OpenAI / 部分兼容网关)
eos / abort    -> ValidationError
```

更糟的是这个异常发生在 `parse_response` / 流式循环内部，会被 `_generate_single` 的 `else: 未知错误也重试`
当成可重试错误**重试 3 次**（P1-2），已经生成的 token 白烧三遍，最后仍然失败。

建议：`finish_reason: str`，或加 `field_validator` 归一化到四值并保留 `raw_finish_reason` 字段。

---

## P1-1 流式完全不重试、不走 fallback

`_generate_stream:355-423` 里没有 `retry_policy`、没有 `asyncio.wait_for`、没有 `_fallback_adapter`；
对比 `_generate_single:259-317` 两者能力差一个数量级。

实测：配置 `retry={"max_attempts": 3}` + fallback 网关，上游只收到 **1** 次请求，fallback 收到 **0** 次。

由于绝大多数聊天 UI 走流式，**「重试」和「降级」这两个核心卖点在主路径上等于不存在**。

---

## P1-2 重试分类靠 `str(exc)` 子串匹配

`gateway.py:276-295`：

```python
if "429" in error_str or "rate limit" in error_str: ...
elif any(f"{code}" in error_str for code in ["500", "502", "503", "504"]): ...
elif any(f"{code}" in error_str for code in ["400", "401", "403", "404"]): raise
```

实测反例：一个 **401** 的错误消息里带 `:5000`（端口号）→ 被判成 5xx，白等 3 秒重试 3 次；
反过来一条 500 的消息只要正文里出现 `400` 就提前 `raise`。

另外 `gateway.py:247` 的 docstring 写着「429 → 使用 retry-after header」，
但全仓 `grep retry-after` 只命中这一行注释——**从未实现**，实际是 `2 ** attempt` 硬退避。

建议：`status_code = getattr(exc, "status_code", None)`，或对 `openai.APIStatusError` 分支；
补上 `Retry-After` 解析，或把注释改成实情。

---

## P1-3 确定性错误也被重试

`gateway.py:296-301` 的 `else: # 未知错误也重试几次`，把 `TypeError`、`ValidationError`、
参数拼错这类「重试一万次也不会好」的错误一起重试，每次还要 `asyncio.sleep(2**attempt)`。

本项目实际踩到：往 `OpenAIAdapter` 传 `max_retries` → `TypeError: create() got an unexpected keyword argument`
被重试 3 次、睡 1+2 秒才报出来（我们花了半天以为是网络问题）。

建议：白名单重试（429 / 5xx / timeout / connection），其余直接抛；至少对 `TypeError` 与
`pydantic.ValidationError` 立即抛。

---

## P1-4 `OpenAIAdapter.__init__(**kwargs)` 把所有未知参数摊进请求体

```python
def __init__(self, api_key, model="gpt-4o", base_url=..., **kwargs):
    self.default_params = kwargs          # openai.py:15
...
request = {..., **self.default_params, **kwargs}   # openai.py:44
...
await self.client.chat.completions.create(**request)  # openai.py:58
```

于是 `max_retries`、`timeout`、`default_headers`、`http_client` 这些**客户端**参数会变成**请求字段**。
openai SDK 2.x 的 `create()` 签名里没有 `**kwargs`，直接 `TypeError`。

建议：显式签名（`temperature` / `max_tokens` / `top_p` / `frequency_penalty` / `presence_penalty` /
`seed` / `extra_body`），未识别参数直接拒绝（或在 debug 模式告警），不要静默摊进请求体。

---

## P1-5 工具调用在两处会被静默丢弃

**a) 只在 `finish_reason == "tool_calls"` 时组装 `tool_calls_complete`**（`gateway.py:395-412`）。
不少网关/模型把 tool_calls 增量发完，收尾给的是 `stop`。此时 `pending` 里明明攒好了完整调用，
却一个都不组装 → `agent_runner:329` 的 `full_tool_calls` 保持 `None` → **一个工具都不执行**，
而模型输出看起来像正常回答。已用假网关复现：`tool_calls_complete` 全为 `None`。

**b) 参数 JSON 解析失败静默降级为空对象**（`gateway.py:400-403`）：

```python
except json.JSONDecodeError:
    args = {}
```

工具会带着空参数被真实调用。比抛错难查得多。

建议：`pending` 非空且流结束时（无论 finish_reason 是什么）都组装；
JSON 失败时抛出或塞 `{"_raw_arguments": ...}` 并在 `tool_start` 事件里告警。

---

## P1-6 `parse_response` 直取 `usage.*`，无兜底

`openai.py:89-93` 的 `raw_response.usage.prompt_tokens`，以及流式 `gateway.py:417-421` 的
`chunk.usage.prompt_tokens`。部分网关（Azure 某些部署、错误响应、只回 `total_tokens` 的代理）
会给出 `usage=None` 或字段缺失 → `AttributeError` → 一次**已经成功**的生成被判失败，还要再重试三次。

建议：逐字段 `getattr(usage, "x", 0)`，`usage` 用 `dict` 默认值兜底。

---

## P1-7 Anthropic `partial_json` 被当成正文吐给用户

`anthropic.py:175-179`：

```python
if hasattr(chunk.delta, "text"):
    result["content"] = chunk.delta.text
elif hasattr(chunk.delta, "partial_json"):
    result["content"] = chunk.delta.partial_json
```

Anthropic 的工具参数增量走 `input_json_delta.partial_json`，这里塞进 `content`，
前端会把一串裸 JSON 当回答渲染出来。目前被 P0-1 挡着，修好流式就会立刻暴露。

建议：`partial_json` 应进 `tool_calls_delta[].arguments`，绝不能进 `content`。

---

## P1-8 Anthropic 适配器与网关的 chunk 契约各写一半

`AnthropicAdapter.parse_stream_chunk:196-201` 把 usage 放进返回 dict 的 `usage` 键，
但 `gateway._generate_stream` 只 `data.get()` 了 `content` / `reasoning_content` /
`finish_reason` / `tool_calls_delta`，**从不读 `data["usage"]`**，而是回头去摸原始
`chunk.usage`（OpenAI 的形状）。于是 Anthropic 的 usage 被丢弃，而且那一行
`chunk.usage.input_tokens` 在 `message_delta` 帧上根本不存在（该帧只有 `output_tokens`，
`input_tokens` 在 `message_start` 里）→ 修好流式后先撞 `AttributeError`。

建议：统一成「适配器负责把 usage 放进 dict，网关只读 dict」，并去掉网关对原始 chunk 的字段依赖
（这条同时是 P0-3 的更干净解法）。

---

## P1-9 Anthropic 多工具并行会拼出连续多条 user 消息

`anthropic.py:62-71` 每个 tool 消息单独 append 一条 `{"role": "user", "content": [tool_result]}`。
一次并行调用 2 个以上工具 → 连续 N 条 user → Anthropic 要求多个 `tool_result` 合并在**同一条**
user 消息里，否则 400 `roles must alternate`。

建议：按 tool_call_id 顺序把连续 tool 消息聚合成一条。

---

## P1-10 Anthropic `max_tokens` 截断被报成 `stop`

`anthropic.py:162`：`finish_reason="tool_calls" if tool_calls else "stop"`（非流式）；
流式 `:191-194` 只映射了 `tool_use` / `end_turn`。输出被截断的半截答案，下游会当完整答案用。

建议：映射 `max_tokens → length`、`stop_sequence → stop`、`tool_use → tool_calls`，
未知值保留原文（顺带解决 P0-4）。

---

## P1-11 `AnthropicAdapter` 没有 `base_url`

`llm/adapters/anthropic.py:14-20` 无该参数，`gateway.py:46-53` 也不传。
想走代理或自建 Claude 兼容端点（企业网关形态）没有入口。Zhipu / DashScope / Ollama 都支持，
只有 anthropic 漏了。

---

## P2-1 客户端从不关闭

`llm/` 目录下没有任何 `aclose()` / `__aenter__`（全仓 `aclose` 只在 `mcp/client.py`）。
`AsyncOpenAI` 每个 gateway 建一个，gateway 又常按 agent 缓存新建 → 连接池与 fd 只增不减。

建议：`LLMGateway.aclose()` + `async with`。

---

## P2-2 适配器工厂硬编码，无注入点

`LLMGateway.__init__:32-87` 五个 if-else，没有 `adapter_factory` 参数，也没有注册表。
想接一个 OpenAI 兼容的自建网关，只能「继承 `OpenAIAdapter` 再替换 `gateway.adapter`」——
`adapter` 是公开属性所以能改，但这是**绕过**不是扩展，上游一改属性名就静默退化成裸请求。

建议：`LLMGateway(config, adapter_factory=...)`，或 `register_adapter(name, cls)`。

---

## P2-3 `set_fallback` 只取 `.adapter`

`gateway.py:351-353`：`self._fallback_adapter = fallback_gateway.adapter`。
fallback 自己的 `timeout` / `retry` 全部丢失，且没有流式 fallback（见 P1-1）。

---

## P2-4 `retry` 配置项不健壮

`self.retry_policy["max_attempts"]` 直接下标（`gateway.py:259`），传
`retry={"backoff": ...}` 就 `KeyError`。也没有 per-attempt timeout、没有 jitter。

---

## P2-5 流式没有整体超时

非流式有 `asyncio.wait_for(..., timeout=self.timeout)`（`gateway.py:261`），
`_generate_stream` 一个都没有。上游保持连接不回数据 → 请求永远挂着，只能等客户端断开。

---

## P2-6 `llm_end.latency_ms` 是累计值

`runtime/agent_runner.py:332`：`total_latency_ms += int(...)` 之后，`:338` 直接把累计值当
**本步**延迟发出去。多步任务里第一步 1s、第二步显示 2s、第三步 3s，前端如果拿它做单步耗时就是错的。

建议：`llm_end` 用 `step_latency_ms`，`done` 才用累计值。

---

## P2-7 `parse_stream_chunk` 的返回契约没写清

`llm/adapters/base.py:24-26` 只声明返回 `dict[str, Any] | None`，没规定键名。
zhipu / dashscope / ollama 返回 `{"type": "text", ...}` 正是契约缺失的产物
（其中 `content` 恰好同名能跑，`tool_call` 那份则完全对不上 `tool_calls_delta`）。
`tool_calls_complete` 只在 `finish_reason=="tool_calls"` 那一条 chunk 上有值这件事也只存在于实现里。

建议：在 ABC 里用 `TypedDict` 固定字段，或直接返回 `LLMResponseChunk`。

---

## P2-8 `content` 假定是 `str`

`openai.py:103` 的 `delta.content or ""` 与 `LLMResponseChunk.content: str`。
多模态 / 新版 API 的 `content` 可能是 list → pydantic ValidationError。

---

## P2-9 `BaseMessage.to_openai()` 会丢字段，且与 OpenAI 适配器是两套序列化

`core/message.py:69-71` 只回 `role` / `content`，`tool_calls` / `reasoning_content` / `name` 全丢。
`AIMessage` 覆盖了所以大多数情况能跑，但 `ZhipuAdapter` / `DashScopeAdapter` 用的是
`msg.to_openai()`，而 `OpenAIAdapter` 手写 dict（`openai.py:19-38`）——两份实现迟早不一致。

---

## P2-10 `reasoning_content` 无条件回传上游

`openai.py:21-22` 把历史消息里的 `reasoning_content` 原样发回。实测对 DeepSeek 无害
（同一历史 `prompt_tokens` 49 vs 49，不报错），但对不认该字段的官方 OpenAI 接口是 400 风险。
建议做成开关，默认关。

---

## 附：我们已确认「不是 bug」的两点，避免重复排查

1. **历史 `reasoning_content` 回传不会重复计费、不会 400**（对 DeepSeek 实测）。
   只是可移植性风险，见 P2-10，不是缺陷。
2. **`gateway.adapter` 是公开属性，可以整体替换**。我们正是靠继承 `OpenAIAdapter` 换
   `self.client` 来接入 Cookie 认证网关的。能用，但属于绕过（见 P2-2）。

## 附：本项目当前如何绕过

`backend/app/services/llm_providers/adapter.py`：

- `HardenedOpenAIAdapter`：usage 收尾帧透传（P0-3）、tool_calls 收尾纠正（P1-5a）、
  `parse_response` 逐字段兜底（P1-6）、`finish_reason` 归一化（P0-4）
- `RetryingGateway`：只在「尚未吐字」时重试（P1-1），`_is_retryable` 读 `status_code`（P1-2）

这些补丁都是**边界补丁**：wuwei 升级时最坏退化成原生行为，不会把请求打死。
但 P0-1 / P0-2（四个适配器不可用）无法在边界补，只能等上游修。

---

# 附：值得反向贡献给上游的补丁

判据是**通用性**——不掺我们的业务，任何使用者都会遇到。代码都已在本仓库跑通并有测试，可直接摘出去。
位置：`backend/app/services/llm_providers/adapter.py`、`backend/app/services/agent/factory.py`。

## 一类：对应上面的缺陷，建议直接进主干

### C-1 usage-only 帧透传（对应 P0-3）

现在 `parse_stream_chunk` 见 `not chunk.choices` 就 `return None`，usage 收尾帧被吞。
我们的做法是**在这一帧返回一个空内容帧**，让网关循环走完、末尾那句 `if chunk.usage` 自然读到：

```python
def parse_stream_chunk(self, chunk):
    data = super().parse_stream_chunk(chunk)
    if data is None:
        if getattr(chunk, "usage", None):
            return {"content": "", "reasoning_content": "", "finish_reason": None}
        return None
    ...
```

为什么不改 `_generate_stream` 的循环：那等于把上游的 `async for` 抄一遍，升级即失效。
**在适配器里解决，网关一行都不用动**，副作用最小。

更彻底的做法见 C-6（统一 chunk 契约）。

### C-2 工具调用收尾纠正（对应 P1-5a）

网关只在 `finish_reason == "tool_calls"` 时组装 `tool_calls_complete`。实测不少网关把 tool_calls 增量发完、
收尾给 `stop` → 工具一个都不执行，而模型输出看起来像正常回答。

我们的做法：适配器记住「本轮出现过 tool_calls 增量」，收尾给 `stop` 时改写为 `tool_calls`，
拿到 `finish_reason` 后复位（异常中断时残留标记最多产生一个 falsy 的空列表，不会误执行）：

```python
self._stream_saw_tool_calls = False

def parse_stream_chunk(self, chunk):
    ...
    if data.get("tool_calls_delta"):
        self._stream_saw_tool_calls = True
    finish = data.get("finish_reason")
    if finish == "stop" and self._stream_saw_tool_calls:
        data = {**data, "finish_reason": "tool_calls"}
    if finish:
        self._stream_saw_tool_calls = False
    return data
```

更稳的判据在网关侧：**`pending` 非空且流结束时，无论 finish_reason 是什么都组装**。

### C-3 `finish_reason` 归一化（对应 P0-4）

`LLMResponse.finish_reason` 是严格 `Literal`，`max_tokens` / `function_call` / `eos` / `abort` /
vLLM 的 `insufficient_system_resource` 全部 ValidationError，而且这个异常在重试循环内 → 白烧三次 token。

建议**两件事一起做**：
1. 类型放宽成 `str`，或加 `field_validator` 归一化到四值；
2. 新增 `raw_finish_reason: str | None` 保留上游原值——归一化会丢信息，但下游（尤其 `length`）
   又需要知道「是截断还是正常结束」。

我们的映射表可参考：`max_tokens|length → length`、`eos|stop_sequence|abort → stop`、
`function_call|tool_use → tool_calls`、其余 → `stop`。

### C-4 `parse_response` 逐字段兜底（对应 P1-6）

上游直接取 `raw_response.usage.prompt_tokens`，兼容网关省略 usage 就 `AttributeError`，
把一次**已经成功**的对话变成 500（还会被重试三次）。

建议不包 `try/except` 而是逐字段 `getattr(..., 0)`——包异常只能拿到半个对象，掏不出「有内容、没计费」的响应。
同样适用 `choices` 为空、`model` 缺失、`message.content` 为 `None`。

**顺带一个我们踩到的细节**：工具参数 JSON 解析失败，上游静默给 `args = {}`，
工具会带着空参数被真实调用，比抛错难查得多。建议至少 `logger.warning` 留下原始串（我们就是这么做的），
或者塞 `{"_raw_arguments": ...}` 让中间件能看见。

### C-5 流式「未吐字才重试」+ 按 `status_code` 分类（对应 P1-1 / P1-2 / P1-3）

```python
async def _stream_with_retry(self, messages, tools, **kwargs):
    for attempt in range(self._stream_attempts):
        emitted = False
        try:
            stream = await super().generate(messages, tools=tools, stream=True, **kwargs)
            async for chunk in stream:
                if chunk.content or chunk.reasoning_content or chunk.tool_calls_complete:
                    emitted = True
                yield chunk
            return
        except Exception as exc:
            if emitted or attempt >= self._stream_attempts - 1 or not _is_retryable(exc):
                raise
            await asyncio.sleep(2 ** attempt)
```

两个约束是刻意的，建议写进文档否则实现者会踩：
1. **一旦已经产出内容就绝不重试** —— 否则用户看到半句话重来一遍，更糟的是工具可能被执行两次。
2. **`_is_retryable` 读 `status_code`，不读 `str(exc)`** —— 实测「401 但错误消息里带 `:5000`」会被判成 5xx。
   规则：`APIConnectionError` / `APITimeoutError` 重试；有 `status_code` 时 `429 or >= 500`；
   **其余一律不重试**（`TypeError` / `ValidationError` 重试一万次也不会好，只是多睡 1+2 秒）。

### C-6 适配器 `__init__` 要把「客户端参数」与「请求参数」分开（对应 P1-4）

现在 `OpenAIAdapter.__init__(**kwargs)` 把所有未知参数塞进 `default_params` 并展开进请求体，
于是 `max_retries` / `timeout` / `default_headers` 变成上游不认识的请求字段
（openai SDK 2.x 的 `create()` 没有 `**kwargs`，直接 TypeError）。

我们的绕法是**显式取出**，并用 `client.with_options` 而不是重建客户端（复用同一个 httpx 连接池）：

```python
def __init__(self, *args, max_retries: int | None = None, **kwargs):
    super().__init__(*args, **kwargs)
    if max_retries is not None and max_retries >= 0:
        self.client = self.client.with_options(max_retries=max_retries)
```

建议上游直接做成签名参数，并且**默认把 SDK 自身的重试关掉（`max_retries=0`）**——
与网关自己的重试叠加会变成乘积（3×3=9 次请求），排查时极难看出来。

---

## 二类：做法可作参考，但需要上游先定 API

### C-7 并发工具批处理（上游现在是逐个串行）

模型一次返回 3 个工具调用时，串行执行等于 3 倍延迟。我们的实现（`factory.py:171-273`，约 100 行）：

- 用工具上的 `is_concurrency_safe` 标记分组：**连续安全工具并发、遇到非安全工具切段串行**；
- 并发段用 `asyncio.gather(..., return_exceptions=True)`，单个失败不影响同批其他工具；
- 事件顺序固定为「先收集结果，再按原顺序 yield `tool_start` / `tool_end`」，
  这样前端看到的调用顺序与模型给出的顺序一致，不会因为谁先完成而乱序。

上游要定的是：`is_concurrency_safe` 放在 `Tool` 上还是 `ToolRegistry.register` 的参数上，
以及同一批并发时中间件钩子（`before_tool` / `after_tool`）的并发语义——
我们的做法是**钩子也在协程里跑**，所以中间件作者必须自己保证线程/协程安全，
这条必须写进文档，否则会变成一个隐蔽的数据竞争源。

### C-8 HITL 三档审批 + 拒绝降级为消息（上游现在是二值 + 抛异常）

现在的 `HitlMiddleware`：要么全问、要么不问；用户拒绝时**抛异常**，整轮对话结束。
我们的做法（`LenientHitlMiddleware`）：

- **会话级三档**：`ask`（全问）/ `auto`（只读工具自动放行，写/执行仍确认）/ `full`（全放行，仅管理员）；
- **拒绝不抛异常**，把 `tool_call` 替换成一个「拒绝工具」，让 LLM 收到明确的拒绝原因后**自己换个做法**；
- 细粒度工具按**参数**判只读（同一个 `file` 工具，`read` 放行、`write` 确认）——
  这个 `is_read_only_tool(name, arguments)` 的形态我觉得值得上游借鉴，
  只按工具名判会把一堆「读写混在一个工具里」的实现逼死。

需要上游先定：`auto_approve_tools` 的 `"*"` 哨兵、`approval_mode` 存在 session 还是 middleware 上。

### C-9 工具结果截断（上游完全没有）

一个工具返回 200KB 数据就足以把上下文顶爆，而且下一轮还要重发。建议做成内置中间件，
参数 `max_chars`，在 `after_tool` 里截断并**追加一句显式提示**
（「原始数据共 N 字符，仅展示前 M 字符」）——不加提示的话模型会以为自己看到的是全部，
于是基于残缺数据下结论。

一个易漏的点：**截断前要放过标记类内容**。我们的图表工具在返回值里内嵌了一段 SVG 标记，
被截断就渲染不出来，所以对含标记的结果整体跳过截断。

### C-10 thinking 历史清洗（多提供商可移植性，对应 P2-10）

`build_request` 无条件把历史 `reasoning_content` 发回上游。对 DeepSeek 实测无害
（同一历史 `prompt_tokens` 49 vs 49，不报错），但对不认该字段的官方 OpenAI 接口是 400 风险。

建议做成 `ProviderCapabilities(supports_reasoning_history: bool)`，而不是硬编码在某家适配器里——
这样「自建网关支持 / 官方接口不支持」的差异由配置表达。我们目前只做了「清理本地合成消息」
（`ThinkingHistoryCompatibilityMiddleware`：注入的 `MAX_STEPS_LIMIT_MESSAGE` 这类本地回复
不能留在 thinking 模式的历史里，否则会被当成模型自己说的话）。

---

## 三类：不适合上游，不必提

- **企业 Cookie 认证网关**（`CookieAuthAdapter(OpenAIAdapter)`，只换 `self.client`）——
  这是我们内网特有形态。但它**证明了 P2-2 那个注入点应该做成什么样子**：
  用户想要的就是「基于现成适配器只替换 client」，所以 `adapter_factory` 的签名建议是
  `(config) -> BaseAdapter`，而不是要求用户实现全部四个抽象方法。
- **AI 提供商层**（DB 配置 / 多账号轮换 / 用途绑定 / 分级探测）——业务层，与框架无关。
- **SSE 事件映射、keepalive、审批竞态**（`orchestrator.py` 1,140 行）——我们的前端契约特有。

---

## 建议的 PR 拆分（按「可独立合并」切）

| PR | 内容 | 文件 | 风险 |
|---|---|---|---|
| 1 | C-1 usage 帧 + C-3 finish_reason 归一化 | `adapters/openai.py`、`llm/types.py` | 极低 |
| 2 | C-4 逐字段兜底 + C-6 客户端参数分离 | `adapters/openai.py` | 低 |
| 3 | C-5 重试分类改 `status_code` + 流式重试 | `llm/gateway.py` | 低（只动异常分支） |
| 4 | 修 zhipu/dashscope/ollama/anthropic 的 `parse_response` + `stream` 字段（P0-1/P0-2） | `adapters/*.py` | 中（要真机验） |
| 5 | C-7 并发工具批处理 | `runtime/agent_runner.py` | 中（事件顺序必须保持） |
| 6 | C-8 HITL 审批档位 | `middleware/hitl.py` | 中（行为变更） |

1-3 是纯粹的「让它在更多网关上不崩」，不改变任何正常路径的行为，最容易合；
4 是修 bug 但需要四个 provider 的真机验证；5-6 是能力增强，需要设计讨论。

## 附：建议上游补的回归测试（我们就是被这几个坑绊住的）

1. `stream_options.include_usage` 的收尾帧（`choices: []` + `usage`）→ 断言 usage 被读到；
2. 收尾 `finish_reason="stop"` 但本轮有 tool_calls → 断言工具被组装；
3. `finish_reason` 取 `max_tokens` / `function_call` → 断言不抛 ValidationError；
4. `usage=None` 的响应 → 断言解析成功且 usage 为 0；
5. 错误消息含 `:5000` 的 401 → 断言**不**重试；
6. 传给适配器的 `max_retries` → 断言不出现在请求体里（用 `httpx.MockTransport` 抓 body）；
7. 每个 provider 的 `build_request(stream=True)` → 断言 `request["stream"] is True`；
8. 每个 provider 的 `parse_response` 用真实 SDK 的 typed response 构造 → 断言返回 `LLMResponse`。

---

# 附：wuwei 3.2.1 残留缺陷清单（2026-10-28 实测复核）

> 上面是 3.0.2 的历史清单，多数已修。本节是**针对当前 3.2.1 的新审计**，
> 每条都经过源码定位 + 动态验证（构造真实对象 / 端到端跑 agent），
> 不是凭阅读推测。审计范围：`llm/gateway.py`、`llm/adapters/*`、`llm/types.py`、
> `core/types.py`、`core/errors.py`、`runtime/agent_runner.py`、`tools/executor.py`、
> `middleware/*`、`graph/checkpoint.py`、`agent/session.py`、`agent/agent.py`。

## 一、网关与适配器层

### R-1【高】`finish_reason="length"` 时 tool_calls 被静默丢弃

- **位置**：`llm/adapters/openai.py:97-100`
- **现象**：`parse_response` 只在 `normalize_finish_reason(finish_reason) in ("stop", "tool_calls")`
  时才解析 `message.tool_calls`。若上游因上下文过长返回 `finish_reason="length"`
  但同时给出了 tool_calls，这批工具调用被**无声丢弃**——不报错、不记日志，
  `LLMResponse.message.tool_calls` 直接是空列表。
- **实测**：
  ```
  finish_reason=length
  tool_calls 数量 = 0   <-- 期望 1，实际 0
  ```
  对照组 `finish_reason="stop"` 时 tool_calls 数量 = 1（正常保留），
  证明这是 finish_reason 分类导致的定向丢弃，不是解析失败。
- **影响**：模型「打算调工具但被截断」时，agent 会认为模型没要求调工具，
  直接把空回复交给用户。**无任何错误痕迹**，排障时极难定位。
  自建网关 / 长上下文场景（百通类聚合网关）命中概率不低。
- **建议**：tool_calls 的解析不应以 finish_reason 为前置条件——
  有 tool_calls 就解析，finish_reason 只决定后续路由。

### R-2【中】网关层从不使用自己的错误类型，原始异常直接抛给调用方

- **位置**：`core/errors.py` 定义了 `LLMError` / `ToolError` / `TimeoutError` /
  `ConnectionError` / `ValidationError` / `ConfigError`，但 `llm/gateway.py` 全程
  没有 `raise` 过其中任何一个（grep 确认：仅 `runtime/agent_runner.py:429` 用了 `LLMError`）。
- **现象**：网关的重试/退避完全依赖 `_classify_error(exc)` 对**异常类型名**的字符串匹配
  （`gateway.py:292-310`）：`APIConnectionError` / `APITimeoutError` / `ConnectError` …
- **影响**：我们自己定义了一个错误类型却不用，导致：
  1. 调用方无法用类型捕获，只能匹配字符串；
  2. `_classify_error` 的白名单是硬编码的**类名**，openai SDK 换版本或换供应商
     改个异常类名，这个类就退化成 `"unknown"` → **不可重试也不走 fallback**，
     且不会报错，只是静默地不重试；
  3. `WuweiError.details` 这个为「携带诊断信息」设计的字段全程没用上。
- **建议**：网关统一抛 `LLMError`（保留 `__cause__` 与 details），
  分类走异常层级而非类名字符串。

### R-3【中】`usage.total_tokens` 被强制改写为 `prompt + completion`

- **位置**：`llm/gateway.py:474-479`
- **现象**：
  ```python
  for key, value in data["usage"].items():
      usage[key] = max(usage.get(key, 0), value)
  usage["total_tokens"] = usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
  ```
  先用 `max` 聚合各字段（这个对流式是对的），但**紧接着无条件覆盖** `total_tokens`。
- **影响**：上游若上报的 `total_tokens` 包含 reasoning tokens / cached tokens
  （DeepSeek、部分自建网关会这样），我们记的总数会**偏小**，导致按 token 计费/配额不准。
  流式与非流式两条路径的口径还不一致（非流式直接用上游值）。
- **建议**：`total_tokens` 若上游给了就用上游的（`max` 聚合即可），只在缺失时才用求和补。

### R-4【中】`_classify_error` 把「未知异常」判为不可重试，且失败信息全部丢失

- **位置**：`llm/gateway.py:276-310`、`gateway.py:392-397`
- **现象**：`_classify_error` 兜底返回 `"unknown"`，而 `_retryable` 只认
  `rate_limit / server_error / connection_error / timeout` 四类 → 未知异常**不重试**。
  同时重试耗尽后 `raise` 的是原始异常，上下文（重试了几次、每次的 status）
  没有被聚合进异常。
- **影响**：openai SDK 3.x 若新增异常类（比如新的 `APITimeoutError` 变体），
  自动降级为不重试且无日志。而我们在 `openai_compat.py` 对外暴露错误时
  拿不到「试过几次」这类关键信息。

### R-5【低】`core/errors.py` 的 `TimeoutError` 遮蔽内置同名异常

- **位置**：`core/errors.py:23-25`
- **现象**：自定义的 `TimeoutError(WuweiError)` 与内置 `TimeoutError` 同名。
  `gateway.py:336,445` 里 `raise TimeoutError(...)` 指的是**内置**那个
  （因为 gateway 没 import 自定义版），而 `tools/executor.py:142` 的
  `isinstance(exc, (ValueError, TypeError, TimeoutError))` 判的也是内置。
  任何 `except wuwei.TimeoutError` 的代码会漏接内置超时。
- **建议**：重命名为 `LLMTimeoutError` / `ToolTimeoutError`，避免与内置类型撞名。

## 二、Agent 执行层

### R-6【高】`"status": "unknown"` 子串匹配 → 正常工具输出被误判为「结果不确定」并永久封死会话

- **位置**：`runtime/agent_runner.py:704-706`
  ```python
  unknown = (
      final.metadata.get("status") == "unknown" or '"status": "unknown"' in final.content
  )
  ```
- **现象**：第二项是**裸子串匹配工具输出文本**。任何工具正常返回
  `{"status": "unknown"}` 这类内容（JSON 化的结构化返回、日志片段、
  模型自己写的字符串）都会被判定为「工具结果不确定」。
- **实测**（端到端）：
  ```
  --- 第一次 run ---
    status=unknown content='工具结果不确定，请核对实际结果后再继续，未自动重试。'
  --- 第二次 run（同一会话）---
    异常: ValueError: Session has an unknown tool outcome; reconcile externally before resetting the session
  --- session.reset() 之后 ---
    status=unknown content='工具结果不确定，请核对实际结果后再继续，未自动重试。'
  ```
  即：**第一次 run 的工具结果被整个丢弃并替换成提示文案，第二次 run 直接抛异常，
  会话从此报废**。`session.reset()` 也救不回来——只要工具还返回这串文本，
  reset 后再跑还是同样的误判。
- **隐蔽性**：`json.dumps` 默认带空格 → `'{"status": "unknown"}'` 命中；
  紧凑格式 → `'{"status":"unknown"}'` 不命中。**同一份语义数据，
  仅序列化空格不同就一个误判一个不误判**。
- **对本项目的命中路径**（已核对工具实现）：
  - `wuwei/plugin/builtin/http.py` 的 `http_get` / `http_post` 把上游响应
    **原样拼进返回文本**（`f"状态码: {...}\n内容: {resp.text[:5000]}"`）——
    上游返回 `{"status": "unknown"}` 即命中。
  - MCP 工具返回第三方 server 的原始内容，同样可能带 `status` 字段。
  - 我们项目自身的工具代码里暂未发现固定的 `"status": "unknown"` 字面量，
    所以命中概率主要来自**透传上游内容**，而非项目自有逻辑。
- **建议**：只信任 `metadata["status"]`（上游已正确提供结构化字段），
  删掉内容子串匹配；或至少改为解析 JSON 后比对真实字段。

### R-7【高】任何 `before_tool` 中间件都会静默关闭并发工具执行

- **位置**：`runtime/agent_runner.py:570-578`
  ```python
  can_batch = (
      not self._metadata.get("batch_results")
      and self.session.parallel_tool_calls
      and not self.middleware._before_tool_mws
      and not self.middleware._after_tool_mws
      and len(tool_calls) > 1
  )
  ```
- **现象**：只要中间件栈里有任何一个 `before_tool` / `after_tool` 钩子，
  并发批处理分支整个关闭，工具退回逐个串行。**没有任何日志或警告提示这一退化。**
- **对本项目的实际命中面**（已核对配置，勿高估）：
  - 实测 `LenientHitlMiddleware` → `_before_tool_mws = 1` → `can_batch = False`；
    `AsyncSubAgentMiddleware` → `_before_tool_mws = 1` → `can_batch = False`。
  - 但我们项目 `agent_parallel_tool_calls` **默认是 `False`**
    （`app/core/config.py:26`，DB 模型 `app/db/models.py:106` 默认也是 `False`），
    所以**当前生产配置下并发本来就没开**，R-7 不是「正在发生的性能退化」。
  - 真实风险在**开关打开时失效**：用户通过 `POST` 传入
    `parallel_tool_calls=true`（`app/schemas/agent.py:46`）想开启并发时，
    会因为审批中间件的存在而**静默无效**——界面上开关是开的，行为却是串行，
    且没有任何提示。这是一个「用户可见的配置不生效」型缺陷，而非性能问题。
  - 也意味着：上一轮删除 monkey-patch 后并未「拿回并发能力」——
    真正让并发生效的是这个 `can_batch` 条件，两者是同一条路径。
- **建议**：把「需要审批」表达为工具自身的 `is_concurrency_safe=False`，
  而不是用中间件钩子一刀切关掉整批并发；至少在 `can_batch` 被降级时打一条 warning。

### R-8【高】并发批次中工具抛 `BaseException` 会炸穿整个批次

- **位置**：`tools/executor.py:94-106`（判定）、`runtime/agent_runner.py:587`（引爆）
- **现象**：`asyncio.gather(..., return_exceptions=True)` 收集结果后，
  `executor.py:99` 用 `isinstance(result, Exception)` 判断是否异常。
  但 Python 3.8+ 起 `asyncio.CancelledError` 继承 `BaseException` 而非 `Exception`，
  该判定为 **False** → 原始异常对象被塞进 `results` 列表，
  后续 `msg.model_dump(mode="json")` 对它调用 → `AttributeError`。
- **实测**：
  ```
  execute 返回 2 条结果
    c1: SUCCESS
  异常逃逸: AttributeError: 'CancelledError' object has no attribute 'tool_call_id'
  ```
  **同批次中那个成功的工具结果也被整个丢弃**，`tool_end` 从不发出。
- **影响**：`CancelledError`（任务取消）、`KeyboardInterrupt`、`SystemExit`
  以及自定义 `BaseException` 都会触发。多用户环境下单个用户的异常工具
  即可打断整条会话链路，前端因缺 `tool_end` 而悬挂等待。
- **建议**：判定改为 `isinstance(result, BaseException)`，
  并把 `CancelledError` 单独处理（应当向上传播取消语义，而非当工具错误吞掉）。

### R-9【高】客户端断连后 generator 未关闭 → 会话锁永久占用

- **位置**：`runtime/agent_runner.py:127-140`（持锁 yield）、`504-512`（清理逻辑）
- **现象**：`_iter_events` 在 `async with self.session.lock:` 内部 `yield`，
  生成器在 yield 点挂起时**仍持有锁**。清理代码在
  `except (asyncio.CancelledError, GeneratorExit)` 里，**只有 generator 被真正
  `aclose()` 才会触发**；而 `async for` 中途 `break` **不会**自动关闭生成器。
- **实测**：`break` 后 `session.lock.locked()` 恒为 `True`，工具状态卡在 `preparing`。
  显式 `await g.aclose()` 后锁才释放。
- **对本项目的命中**：我们唯一的消费方是
  `app/services/agent/orchestrator.py:697`
  ```python
  async for event in agent.stream_events(user_message, session=session):
  ```
  **没有 `aclose()` 保护**。上游 `serve/_http.py` 有这层兜底，我们自建路径没有。
  一次 HTTP 断连 / SSE 取消就让该 `AgentSession` 的锁永久占用，
  此会话后续所有 run 全部阻塞在 `async with self.session.lock` 上
  （`asyncio.Lock` 无超时参数），且无人能解锁。
- **建议**：消费方用 `try/finally` 里 `await gen.aclose()`，
  或给锁获取加超时。

### R-10【高】`MemoryCheckpointer` 的 metadata 是浅拷贝，不是快照

- **位置**：`graph/checkpoint.py:57-67`
- **现象**：`state` 走了 JSON roundtrip（真深拷贝，第 61 行），
  但 `metadata` 只做 `dict(metadata)` **浅拷贝**（第 64 行），
  嵌套的 `tool_states` 仍是同一个 dict 对象的引用。
- **实测**：
  ```
  保存后 checkpoints[cid]['metadata']['tool_states'] = {'c1': 'running'}
  事后读 checkpoints[cid]['metadata']['tool_states'] = {'c1': 'success'}
  ```
  快照被事后改写。`SQLiteCheckpointer` 用 `json.dumps` 是真快照，不受影响。
- **影响**：`tool_running` 快照是 `_commit_tool` 判定「工具结果不确定、
  禁止重放」的依据。Memory 后端下所有检查点最终都显示 `success`，
  恢复流程会认为工具已成功而**重放有副作用的工具调用**
  （重复扣款、重复下单、重复写文件）。
  开发/测试用 Memory、生产用 SQLite → 两环境行为不一致。
- **建议**：Memory 后端的 metadata 也走 JSON roundtrip，与 state 保持同语义
  （代码注释里已经写明 state 是为了「与 SQLite 语义一致」，metadata 漏了）。

### R-11【中】异常路径不发终止事件，`agent.run()` 直接抛异常而非返回 `status="error"`

- **位置**：`runtime/agent_runner.py:513-531`
- **现象**：`except Exception` 分支只 `yield` 一个 `error` 事件然后 `raise`，
  **不发 `done` / `run_end`**。正常路径 `_finish()` 会同时发这两个。
  而 `AgentRunResult.status` 明确定义了 `"error"` / `"cancelled"` / `"interrupted"`
  枚举，异常路径根本走不到。
- **影响**：客户端若按「收到 `done` 才算结束」实现，遇到异常会一直等流结束；
  基于 `async for` 的消费者还会因异常向上抛而返回 500，
  已生成的部分内容无法返回给用户。

### R-12【中】工具返回值无大小限制，且 runner 路径不做任何上下文裁剪

- **位置**：`tools/executor.py:197-207`（`serialize_output` 无上限）、
  `runtime/agent_runner.py:703`（无条件入历史）
- **现象**：`serialize_output` 对任意大小的输出直接 `json.dumps`，无上限。
  `agent_runner.py:703` 无条件 `session.context.get_messages().append(final)`。
  `memory/context_window.py` 里的 `SimpleContextWindow`（含 `max_tool_chars=8000`）
  **实现了但 runner 从不调用**（grep 全包确认 `runtime/` 下零引用）；
  `memory/context.py:58` 的 `keep_last_turns` 同理。
- **影响**：单次工具返回 10MB 数据就永久占住该会话的上下文预算，且每轮重发。
  我们虽然启用了 `ContextCompressionMiddleware`，但它靠 `trigger_tokens` 阈值触发，
  且改写的是 `ctx.state.messages` 而**不写回 `session.context`**——
  历史仍在后台无限增长，只是发送时被临时改写。

### R-13【中】并发批次无上限，且经装饰器注册的工具一律默认并发安全

- **位置**：`tools/executor.py:94-97`（无 `Semaphore`）、
  `tools/tool.py:43`（`is_concurrency_safe` 默认 `True`）、
  `tools/registry.py`（装饰器参数表不接受 `is_concurrency_safe`）
- **现象**：整批直接 `asyncio.gather`，`tools/` 包内 grep 无任何 `Semaphore`。
  装饰器注册的工具无法声明 `is_concurrency_safe`，一律默认并发安全。
  对照：`wuwei/fs/tools.py:172` 正确写了 `is_concurrency_safe=not side_effect`，
  但 `plugin/builtin/file.py` 的 `write_text_file` / `append_text_file` /
  `replace_text_in_file` / `delete_file` **只声明了 `side_effect=True`，
  没声明 `is_concurrency_safe=False`**——这些正是会互相覆盖的文件写工具。
- **影响**：模型一次吐 50 个工具调用会瞬间打满下游连接池/文件句柄。
  目前因 R-7 与默认关闭的 `parallel_tool_calls`，并发实际未开启，
  **一旦修复 R-7 或用户显式开启并行，本条会立刻暴露**——属于「修 R-7 时必须同批处理」的项。

### R-14【中】超时不中断同步工具线程，且未声明 `side_effect` 的工具超时后被标为「确定失败」

- **位置**：`tools/tool.py:78`（`asyncio.to_thread`）、
  `tools/executor.py:167-171`（`wait_for`）、`executor.py:150-161`（状态标记）
- **现象**：同步 handler 在 `to_thread` 里跑，`asyncio.wait_for` **只取消 await，
  线程继续跑到底**。但 `executor.py:161` 只在 `side_effect=True` 时才标 `status="unknown"`：
  ```python
  "status": "unknown" if isinstance(last_exception, TimeoutError) and tool.execution.side_effect else "failed"
  ```
- **影响**：未声明 `side_effect` 的 IO 类工具（读大文件、慢网络）超时后被标为
  「确定失败」，下游会安全重试——但底层线程可能仍在写/在提交 = 重复副作用。
  我们项目大量工具是同步函数，全部落在这条路径上。

### R-15【中】审批等待无超时、无取消，且会连带锁住整个会话

- **位置**：`middleware/hitl.py:157`
  ```python
  approved = await self.approval_provider(tool_call)
  ```
  没有 `asyncio.wait_for` 包装，也没有取消通道。
- **影响**：审批期间持有 `session.lock`（`agent_runner.py:128`），
  整个会话被阻塞。用户关掉审批页面/前端断连都不会取消这次等待。
  我们项目 `factory.py:138` 的 `await self.approval_provider(tool_call)`
  是自研版本，同样无超时——把上游的缺口原样继承了。

### R-16【中】缺少重复工具调用检测，且默认无 token/成本上限

- **位置**：`runtime/agent_runner.py:308`（循环上限）、`agent/agent.py:65-79`
- **现象**：循环封顶只有 `while meta["step_index"] < self.session.max_steps`，
  **没有任何「同一工具 + 同一参数重复调用」的检测**。
  token/成本上限只在显式装配 `BudgetMiddleware` 时生效，
  `Agent.__init__` **不提供任何默认预算参数**（我们项目也没装 `BudgetMiddleware`）。
- **影响**：模型陷入「调 A → 失败 → 再调 A」的循环会白白消耗整轮 LLM 调用与工具副作用。

### R-17【低】事件类型声明与实际发出的不一致

- **位置**：`llm/types.py:59-74`（`AgentEventType`）
- **现象**：`task_start` / `task_end` **在 `AgentRunner` 中从不发出**
  （grep `runtime/` + `serve/` 全包确认零发出点），只有 `llm/types.py` 的声明处。
- **影响**：客户端按类型穷举处理时这两个分支永远不会触发（上游 `serve/ag_ui.py:223`
  甚至把它们的映射注释掉了）。另：`usage` 不在事件类型里，
  只能从 `llm_end`/`done` 的 `data` 嵌套取。

## 三、已验证「不是问题」的排除项（避免重复排查）

| 疑点 | 实测结论 |
| --- | --- |
| 并发批次中单个工具抛普通 `Exception` 会不会吞掉整批？ | **不会**。`executor.py:94-106` 正确隔离为该 tool 的结构化 error Message，批次正常完成。仅 `BaseException` 家族有问题（R-8）。 |
| `asyncio.gather(return_exceptions=True)` 会不会漏掉 `CancelledError`？ | gather 本身**没问题**，确实捕获并作为结果值返回。缺陷在 `executor.py:99` 的 `isinstance` 判定过窄（R-8）。 |
| `zip(tool_calls, results)` 会不会错位？ | **不会**。`executor.py:98` 保持原始顺序与 id 对应；第 114 行的过滤理论上会在有 `None` 时错位，但 `execute_one` 永不返回 `None`，不可达。 |
| `AgentSession.lock` 是 `asyncio.Lock`，跨 event loop 复用会不会炸？ | **正常**。Python 3.13 的 `asyncio.Lock` 不再绑定 loop，跨 `asyncio.run` 复用无异常。 |
| `SQLiteCheckpointer` 的 `tool_running` 快照语义对不对？ | **正确**。`checkpoint.py:123` 用 `json.dumps` 是真快照，`claim()` 用 `BEGIN IMMEDIATE` + `INSERT OR IGNORE` 实现原子一次性消费。Memory 后端才有问题（R-10）。 |
| `BudgetMiddleware` 是不是死代码？ | **不是**。`agent_runner.py:311` / `:403` 都会触发它。 |
| `normalize_finish_reason` 归一化是否覆盖常用非标值？ | **覆盖良好**（`eos`/`end_turn`/`stop_sequence`/`tool_use`/`max_tokens`/`aborted`/`failed`/`incomplete` 等），且保留 `raw_finish_reason` 原值。 |
| 审批决策是否会张冠李戴？ | **不会**。`hitl.py:141-142` 用 `tool_call.id` 精确匹配，并校验工具名与参数一致。 |
| 是否有模块级/类级共享可变状态？ | **未发现**。全包 grep 模块级容器赋值与类级可变默认值均零命中。 |
| `AsyncSubAgentMiddleware._tasks` 会不会无限增长？ | **会**（`async_sub_agent.py:378` 写入，全包无 pop），但每次查询按 `owner_session` 过滤，**不跨用户泄漏**，仅内存增长。 |

## 四、给我们自己的处置建议（按优先级）

| 优先级 | 动作 | 对应 |
| --- | --- | --- |
| P0 | 消费方给事件流加 `finally: await gen.aclose()`；会话锁加获取超时 | R-9 |
| P0 | 移除工具输出里的 `"status": "unknown"` 子串匹配（在我们自己的适配层兜住） | R-6 |
| P1 | 把审批从 `before_tool` 挪出或显式串行化审批工具，让 `parallel_tool_calls=true` 真正生效；降级时补 warning | R-7 |
| P1 | `isinstance(result, BaseException)` 修正 + `CancelledError` 单独处理 | R-8 |
| P1 | 工具结果长度上限 + 显式上下文裁剪接线 | R-12 |
| P1 | 生产统一用 `SQLiteCheckpointer`；或给 Memory 后端补 metadata 深拷贝 | R-10 |
| P1 | `finish_reason="length"` 时也要解析 tool_calls | R-1 |
| P2 | 网关统一抛 `LLMError` 并携带诊断 details；`_classify_error` 改走异常层级 | R-2 / R-4 |
| P2 | `usage.total_tokens` 优先用上游值 | R-3 |
| P2 | 审批等待加超时 | R-15 |
| P2 | 补重复工具调用检测 + 默认 token/成本上限 | R-16 |
| P3 | `TimeoutError` 重命名避免遮蔽内置异常 | R-5 |

## 五、值得反向贡献给上游的补丁（续 C-1 ~ C-9）

- **D-1（R-1）**：`parse_response` 里把 tool_calls 解析与 finish_reason 解耦——
  有 tool_calls 就解析，finish_reason 只用于路由。
- **D-2（R-6）**：删掉 `'"status": "unknown"' in final.content` 子串匹配，
  只信任结构化的 `metadata["status"]`。若确需内容兜底，
  应先尝试 `json.loads` 再比对真实字段。
- **D-3（R-7）**：把「需要审批」表达为工具自身的 `is_concurrency_safe=False`，
  而不是用中间件钩子一刀切关掉整批并发；至少在降级时 `logger.warning`。
- **D-4（R-8）**：`executor.py:99` 的 `isinstance(result, Exception)` 改为
  `BaseException`，并对 `CancelledError` 单独处理。
- **D-5（R-10）**：`MemoryCheckpointer.save` 的 metadata 也走 JSON roundtrip，
  与 state 保持同语义（注释里已经写明 state 是为了对齐 SQLite，metadata 漏了）。
- **D-6（R-9）**：在 `_iter_events` 内部保证 generator 被关闭时释放锁，
  而非依赖外部调用方记得 `aclose()`。
- **D-7（R-12）**：`serialize_output` 加默认长度上限（可配），
  并在 runner 里接线 `SimpleContextWindow`——它已经写好了，只是没被调用。

## 六、修复落地状态（2026-10-28）

本节记录 R-1 ~ R-17 的实际落地情况。**补丁层不碰 `site-packages`**，
全部走上游公开注入点（子类化 / 构造参数 / 消费端收尾），
上游修好后对应回归测试会失败，提示可以删。

### 6.1 落地位置

| 层 | 文件 | 内容 |
| --- | --- | --- |
| Agent 执行层 | `backend/app/services/agent/wuwei_patches.py` | `PatchedAgent` / `PatchedAgentRunner` / `BoundedToolExecutor` / `BatchSafeMiddlewareProxy` |
| 网关与适配器层 | `backend/app/services/llm_providers/adapter.py` | `HardenedOpenAIAdapter`（R-1 / R-3）、`RetryingGateway`（R-2 / R-3 / R-4） |
| 装配点 | `backend/app/services/agent/factory.py` | 改用 `PatchedAgent` + `BatchSafeMiddlewareProxy`；审批加超时（R-15） |
| 消费端 | `backend/app/services/agent/orchestrator.py` | 事件流加 `contextlib.aclosing`（R-9）；错误事件纳入完成通知 |
| 回归测试 | `backend/tests/test_wuwei_patches.py` | 26 条用例，逐条对应 R-1 ~ R-16 |

### 6.2 逐条状态

| 编号 | 状态 | 落地方式 |
| --- | --- | --- |
| R-1 | ✅ 已修 | 非流式：`HardenedOpenAIAdapter.parse_response` 与 finish_reason 解耦，始终解析 tool_calls；流式：`finish_reason=length` 时补告警日志。**刻意不把 length 改成 tool_calls**——上游 runner 明确写了「No partial tools execute on length/abort/unknown」，强行执行截断的工具调用反而危险。 |
| R-2 | ✅ 已修 | `RetryingGateway` 统一抛 `LLMError`（保留 `__cause__` 与 `details`：error_type / status_code / attempts / retryable）。原始异常仍在 `__cause__` 里。 |
| R-3 | ✅ 已修 | 适配器 `_parse_usage` 保留上游 `total_tokens`（与 prompt+completion 不同时另存），`RetryingGateway` 在 chunk 离开网关前还原，并摘掉辅助键（不污染 run 的 usage 统计）。 |
| R-4 | ✅ 已修 | `RetryingGateway._classify_error` 在上游「异常类名白名单」之外，按**异常层级**兜底（httpx / openai 的超时与连接异常）。完全未知的异常仍保持 unknown，不盲目重试。 |
| R-5 | ⏸ 不改 | 要改 `site-packages` 的错误类型定义；项目内没有 `except TimeoutError` 的用法（已 grep 确认），无实际风险。 |
| R-6 | ✅ 已修 | `PatchedAgentRunner._commit_tool` 采用「**委托上游 + 事后纠正**」：先 `await super()._commit_tool(...)` 保留上游的全部副作用，再按结构化事实纠正 `unknown` 判定。判定依据从裸子串改成「解析 JSON + 比对框架错误载荷的三个特征（`ok=false` / `status=unknown` / `execution_may_continue=true`）」。 |
| R-7 | ✅ 已修 | 新增 `BatchSafeMiddlewareProxy`：对上游的 `can_batch` 判定隐藏工具钩子，但**批处理路径由 `BoundedToolExecutor` 逐个补跑 `execute_before_tool`**——上游关闭并发的原因正是它的批处理分支不调 before_tool（等于绕过审批）。代理之外的一切行为完全委托真实中间件栈。 |
| R-8 | ✅ 已修 | `BoundedToolExecutor._execute_batched` 的异常判定放宽到 `BaseException`；`CancelledError` 单独向上传播（不伪装成工具失败），其余转成结构化错误消息。 |
| R-9 | ✅ 已修 | 消费端 `orchestrator` 用 `contextlib.aclosing` 包住事件流；runner 侧 `_iter_events` 用 `aclosing` 包住上游生成器，并**确定性地**关闭内层 `_execute_events`（不再依赖 GC 的异步 finalization）。 |
| R-10 | ⏸ 备用 | 项目当前 `Agent(...)` 未装配 checkpointer，暂无实际影响；已备好 `deep_copy_metadata()`（JSON roundtrip 语义），一旦启用检查点即生效。 |
| R-11 | ✅ 已修 | `PatchedAgentRunner._iter_events` 捕获异常后补发 `error`（若上游没发）+ `done` + `run_end`，`agent.run()` 因此返回 `status="error"` 而不是抛异常。 |
| R-12 | ✅ 已修（部分） | `BoundedToolExecutor.serialize_output` 加 20k 字符上限。**上下文裁剪刻意不做**：我们的 orchestrator 从 `session.context` 持久化消息到数据库，裁剪历史会丢用户可见的记录；模型侧已由 `ContextCompressionMiddleware` + 工具输出上限双重兜底。 |
| R-13 | ✅ 已修 | `BoundedToolExecutor` 用 `Semaphore` 限制并发（默认 8）；名字里带写/删/发等动词的工具（上游 `plugin/builtin/file.py` 的写类工具只声明了 `side_effect=True`、没声明 `is_concurrency_safe=False`）一律降级为串行。 |
| R-14 | ✅ 已修 | `BoundedToolExecutor.execute_one` 在出口把「超时 + 可能有副作用」的结果状态从 `failed` 纠正为 `unknown`（上游只看 `execution.side_effect` 声明）。 |
| R-15 | ✅ 已修（部分） | `LenientHitlMiddleware.before_tool` 用 `asyncio.wait_for` 包住审批等待（默认 300s），超时按拒绝处理。**会话锁的持有期间无法释放**是上游设计（审批发生在 run 内），未改动。 |
| R-16 | ✅ 已修（部分） | `BoundedToolExecutor` 增加「同一工具 + 同一参数」连续重复调用检测（默认 3 次），超限直接拦截、不执行工具。**token/成本上限未加**：上游 `BudgetMiddleware` 需要价格表与产品口径，属业务决策。 |
| R-17 | ⏸ 不改 | `task_start` / `task_end` 在上游从不发出（只有类型声明）。改为在文档里记录「实际发出的事件类型」，不伪造事件。 |

### 6.3 验证方式

- **回归测试**：`backend/tests/test_wuwei_patches.py`（26 条）逐条对应上表；
  `tests/test_llm_providers.py` 的两条流式重试用例按 R-2 的新契约更新
  （断言 `LLMError` 且 `__cause__` 是原始 openai 异常）。
- **缺陷复现对照**：R-6 用未打补丁的上游 `Agent` 实测复现——
  第一次 run `status=unknown`、内容被替换成「工具结果不确定…」、
  `session.metadata["_blocked_run"]` 被写入、第二次 run 抛
  `ValueError: Session has an unknown tool outcome`；
  打补丁后同样的脚本返回 `status=completed` 且内容完整。
- **全量门禁**：后端 `pytest` 604 passed / 1 skipped；`ruff check app/ tests/` 全过。

### 6.4 补丁失效是安全的

所有补丁都退化到上游原生行为，不会把请求打死：

- `_commit_tool` 是「先委托上游、再纠正」——上游改判定逻辑时我们只纠正一次，不影响主流程；
- `aclosing` 包一层不会改变事件内容与顺序；
- `BatchSafeMiddlewareProxy` 只影响上游的**并发判定**，钩子本身照常执行；
- `_classify_error` / `LLMError` 只改变异常的**表现形式**，不改变重试决策。

### 6.5 R-17：实际发出的事件类型（客户端按这个写分支）

上游 `llm/types.py` 的 `AgentEventType` 声明了 14 种，但 runner 实际只发 12 种——
`task_start` / `task_end` **只有声明、没有发出点**（`runtime/` 与 `serve/` 全包 grep 零命中），
上游 `serve/ag_ui.py:223` 甚至把它们的映射注释掉了。

**实际会发出的类型**：

| 类型 | 触发时机 |
| --- | --- |
| `run_start` | 一次 run 开始（`data.resumed` 表示是否恢复自挂起点） |
| `llm_start` / `llm_end` | 每轮模型调用的起止；`llm_end` 里带 `usage` |
| `text_delta` | 正文增量 |
| `reasoning_delta` | 思考过程增量 |
| `tool_start` / `tool_end` / `tool_error` | 工具调用的起止与失败 |
| `approval_required` | 需要人工审批（附 `InterruptPayload`） |
| `error` | 异常（**补丁后异常路径会补发 `done` / `run_end`**） |
| `done` / `run_end` | 终止事件，`data` 里带 `content` / `usage` / `status` / `termination_reason` |

另外：`usage` **不是**一种事件类型，只能从 `llm_end` / `done` 的 `data.usage` 里取。
