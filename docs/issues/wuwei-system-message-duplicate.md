# 标题

`structured_schema` 注入会额外 `insert(0, SystemMessage(...))`，导致 OpenAI 兼容端 400 `System message must be at the beginning`

---

## 环境

- wuwei 版本：**3.3.2**
- 上游端点：OpenAI 兼容网关（非官方 OpenAI；DeepSeek / vLLM / 内网网关均会校验）
- 相关文件：`wuwei/runtime/agent_runner.py:481-492`

## 现象

智能体在设置了结构化输出（`response_model=` 或 `output_spec`）时，**第一次 LLM 调用即失败**：

```
openai.BadRequestError: Error code: 400 - System message must be at the beginning.
```

调用栈（节选）：

```
File "wuwei/runtime/agent_runner.py", line 535, in _execute_events
    async for chunk in result:
File "wuwei/llm/gateway.py", line 579, in _generate_stream
    self._raise_translated(exc)
File "wuwei/llm/gateway.py", line 512, in _raise_translated
    raise cls._as_llm_error(exc) from exc
wuwei.core.errors.LLMError: Error code: 401 / 400
```

因为 400 不属于可重试错误，异常直接冒泡成 `LLMError`，整个 run 被打断，用户侧表现为「发消息立刻失败」。

## 根因

`agent_runner.py:481-492`：

```python
if not pending:
    ctx = await self._in_context(ctx, self.middleware.execute_before_llm, ctx)
    if meta.get("structured_schema") and self.output_spec is None:
        from wuwei.core.message import SystemMessage

        ctx.state.messages.insert(
            0,
            SystemMessage(
                content="只输出符合以下JSON Schema的JSON对象："
                + json.dumps(meta["structured_schema"], ensure_ascii=False)
            ),
        )
```

会话消息的第 0 条**本来就是** system 提示词（`AgentSession` 初始化时写入 `default_system_prompt`）。这里再 `insert(0, ...)` 就变成：

```
[ 新的 schema system, 原有 system, user, assistant, ... ]
```

OpenAI 兼容端有硬校验：**system 消息必须唯一且位于首位**。两条相邻 system 直接 400。

这个问题只在设置了 `structured_schema` 时触发，所以普通对话正常、一开结构化输出就必挂 —— 排查时容易误判成网关或鉴权问题（异常文本里甚至同时出现 401/400 两种状态码，因为网关把校验失败包成了不同的错误形态）。

## 建议修复

不要新增 `SystemMessage`，而是把 schema 说明**追加到已有的首条 system 消息**里。这样消息条数和顺序都不变，也不会破坏 provider 的 thinking-mode 历史兼容性。

```python
if meta.get("structured_schema") and self.output_spec is None:
    schema_text = (
        "只输出符合以下JSON Schema的JSON对象："
        + json.dumps(meta["structured_schema"], ensure_ascii=False)
    )
    messages = ctx.state.messages
    if messages and getattr(messages[0], "role", None) == "system":
        # 追加到已有的 system，保持「system 唯一且在首位」
        messages[0].content = f"{messages[0].content or ''}\n\n{schema_text}"
    else:
        from wuwei.core.message import SystemMessage
        messages.insert(0, SystemMessage(content=schema_text))
```

### 需要注意的两个点

1. **`messages[0].content` 可能是 list（多模态）**，直接字符串拼接会 TypeError。稳妥写法：

   ```python
   current = messages[0].content
   if isinstance(current, list):
       current = "".join(
           str(b.get("text") or "") if isinstance(b, dict) else str(getattr(b, "text", "") or "")
           for b in current
       )
   messages[0].content = f"{current or ''}\n\n{schema_text}"
   ```

2. **每轮都会执行这段**（`while` 循环内、`if not pending` 分支）。当前实现在多步工具循环里会**反复 insert**，每步都多一条 system —— 即使客户端不校验「system 必须在首位」，上下文也会被同一段 schema 说明刷屏，白烧 token。改成追加同样需要在追加前做幂等判断，例如：

   ```python
   marker = "只输出符合以下JSON Schema的JSON对象："
   if marker not in (messages[0].content or ""):
       messages[0].content = f"{messages[0].content or ''}\n\n{schema_text}"
   ```

   或者更干净：在循环外算一次，进循环前注入。

## 临时绕过（下游可用，但不算修复）

在网关层把多条 system 合并成一条再发请求。我们目前在 `LLMGateway` 子类里这么兜底，但这是**下游为上游 bug 买单** —— 任何直接用 `Agent(response_model=...)` 且自己配 provider 的用户都会踩到，且不会想到要去合并 system。

## 附：同一轮排查中发现的另一个问题（独立 issue）

`agent_runner.py:700-706` 达到 `max_steps` 时：

```python
else:
    status = "incomplete"
    termination_reason = "max_steps"
    final_content = "任务未完成，已达到最大步骤限制。"
    self.session.context.add_ai_message(final_content)
```

这句作为普通 assistant 消息写进上下文，但**没有携带任何上下文信息**（做到了哪一步、为什么没完成、下一步该怎么继续）。下游只能自己按字符串 `==` 匹配这一句来替换文案 —— 我们就是这么做的，但很脆弱（上游改一个字就失效）。

建议在 `final_content` 里带上 `step_index` / 已完成的工具数，或者至少在 `done` 事件的 `data` 里给出 `termination_reason` 与 `steps_used`，让调用方能程序化判断「是被截断了」而不是靠文本匹配。

---

**期望行为**：设置 `response_model` / `output_spec` 后，LLM 请求里的 system 消息保持唯一且在首位，结构化输出正常工作。
