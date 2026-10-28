# wuwei 3.0.2 问题清单（供上游反馈）

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
