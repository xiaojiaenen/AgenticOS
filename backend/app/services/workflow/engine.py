"""工作流引擎 v1（P0-3，借鉴 Dify Workflow / Coze 的节点流模型）。

v2 形态：**条件分叉 + 并行分支 + 汇聚**，8 类节点 ——
``start / llm / knowledge / http / template / condition / human_input / end``。
就绪的同批节点并发执行（LLM/HTTP 真并行）；汇聚节点等所有入边来源终态；
人工输入是屏障（其它节点全部终态后才提问）。循环节点仍不支持（有环校验
直接拒绝）—— Dify 的循环节点同样以「子流程迭代」形态出现，需要时再立项。

分层（便于测试与后续替换执行载体）：

- ``engine.py``（本文件）：纯计算 —— 图校验、变量解析、调度器。
  节点处理器由调用方注入，本文件不 import 任何 LLM/DB/HTTP 依赖。
- ``nodes.py``：内置节点处理器（LLM/知识检索/HTTP/条件/模板）。
- ``service.py``：DB 编排 —— run 记录、每步落库、暂停/恢复的持久化。

变量解析：``{{inputs.x}}`` / ``{{nodes.<id>.output}}`` 走**受限的点路径
查找**（正则白名单字符 + 逐段 dict 取键），没有 eval、没有属性链访问 ——
工作流定义是管理员输入的 JSON，绝不能变成代码执行入口。

暂停/恢复：human_input 节点就绪且**其它全部节点终态**（屏障）时暂停；
service 把「各节点状态 + 输出」落库（steps_json + context_json 天然构成
快照）。恢复时把 ``resume_state``（node_status/outputs + 答复）交回引擎
—— 引擎静默重建状态并按「done 来源按子节点终态决定携带」推进出边。
快照不依赖执行顺序，**并行完成顺序不稳定也能正确重建**。恢复不依赖
任何内存态，进程重启后照常可续（与 approvals 的 Redis Future 不同，
这里 DB 是唯一事实源）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections import deque
from typing import Any, Awaitable, Callable

logger = logging.getLogger("agenticos.workflow")

NODE_TYPES = (
    "start", "llm", "knowledge", "http", "template", "condition", "human_input", "end",
)

# 单节点输出上限：超过截断并打标。字符串类输出（LLM 文本、HTTP 响应体、
# 模板渲染结果）走这里；结构化输出（知识检索结果）由 nodes.py 自行限额。
NODE_OUTPUT_MAX_CHARS = 32_000
# 步骤轨迹里的输出预览长度（steps_json 是给人看的，全量在 context_json）
TRACE_PREVIEW_CHARS = 1_000

# 默认超时（settings 可覆盖）
DEFAULT_NODE_TIMEOUT_SECONDS = 60
DEFAULT_RUN_TIMEOUT_SECONDS = 300

_VAR_RE = re.compile(r"\{\{\s*([A-Za-z0-9_][A-Za-z0-9_.]*?)\s*\}\}")
# 整串恰好是一个变量：返回原始值（保类型）—— end 节点输出结构化数据时
# 不该被强行 JSON.stringify 成字符串
_VAR_WHOLE_RE = re.compile(r"^\s*\{\{\s*([A-Za-z0-9_][A-Za-z0-9_.]*?)\s*\}\}\s*$")

CONDITION_OPS = (
    "==", "!=", ">", "<", ">=", "<=",
    "contains", "not_contains", "startswith", "endswith", "is_empty", "not_empty",
)


class WorkflowError(Exception):
    """工作流配置/执行错误的基类。"""


class WorkflowValidationError(WorkflowError):
    """图结构非法（保存/运行前被 validate_workflow_graph 拦下）。"""


class WorkflowNodeError(WorkflowError):
    """某个节点执行失败（带 node_id，便于轨迹定位）。"""

    def __init__(self, node_id: str, message: str) -> None:
        super().__init__(f"节点 {node_id} 执行失败: {message}")
        self.node_id = node_id


# ---------------------------------------------------------------------------
# 图校验
# ---------------------------------------------------------------------------

def validate_workflow_graph(graph: dict[str, Any]) -> list[str]:
    """校验节点图，返回**全部**问题（保存配置时一次说清，别让管理员改一轮报一个）。"""
    errors: list[str] = []
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return ["graph.nodes / graph.edges 必须是数组"]

    by_id: dict[str, dict] = {}
    for node in nodes:
        if not isinstance(node, dict):
            errors.append("nodes 里存在非对象元素")
            continue
        node_id = node.get("id")
        node_type = node.get("type")
        if not isinstance(node_id, str) or not node_id.strip():
            errors.append(f"节点缺少合法 id: {node!r}")
            continue
        if node_id in by_id:
            errors.append(f"节点 id 重复: {node_id}")
            continue
        if node_type not in NODE_TYPES:
            errors.append(
                f"节点 {node_id} 的 type 非法: {node_type}（可用: {', '.join(NODE_TYPES)}）"
            )
            continue
        params = node.get("params") or {}
        if not isinstance(params, dict):
            errors.append(f"节点 {node_id} 的 params 必须是对象")
            continue
        if node_type == "condition":
            op = params.get("op")
            if op not in CONDITION_OPS:
                errors.append(
                    f"条件节点 {node_id} 的 op 非法: {op}（可用: {', '.join(CONDITION_OPS)}）"
                )
        by_id[node_id] = node

    starts = [n for n in by_id.values() if n.get("type") == "start"]
    if len(starts) != 1:
        errors.append(f"必须有且只有一个 start 节点，当前 {len(starts)} 个")
    if not any(n.get("type") == "end" for n in by_id.values()):
        errors.append("缺少 end 节点")

    out_edges: dict[str, list[dict]] = {nid: [] for nid in by_id}
    in_degree: dict[str, int] = {nid: 0 for nid in by_id}
    for edge in edges:
        if not isinstance(edge, dict):
            errors.append("edges 里存在非对象元素")
            continue
        src, dst = edge.get("from"), edge.get("to")
        if src not in by_id or dst not in by_id:
            errors.append(f"边引用了不存在的节点: {edge!r}")
            continue
        out_edges[src].append(edge)
        in_degree[dst] += 1

    for nid, node in by_id.items():
        ntype = node.get("type")
        outs = out_edges[nid]
        if ntype == "end":
            if outs:
                errors.append(f"end 节点 {nid} 不能有出边")
            continue
        if ntype == "condition":
            if len(outs) != 2:
                errors.append(
                    f"条件节点 {nid} 必须恰有 2 条出边（true/false），当前 {len(outs)} 条"
                )
            else:
                labels = {str(e.get("label", "")).lower() for e in outs}
                if labels != {"true", "false"}:
                    errors.append(
                        f"条件节点 {nid} 的两条出边必须分别标 label=true / label=false"
                    )
        elif len(outs) < 1:
            errors.append(f"节点 {nid}（{ntype}）至少需要 1 条出边，当前 {len(outs)} 条")

    # 环检测：Kahn。汇聚（多入边）是允许的，调度器按「所有入边来源终态」就绪。
    indeg = dict(in_degree)
    ready = deque([nid for nid, deg in indeg.items() if deg == 0])
    seen = 0
    while ready:
        nid = ready.popleft()
        seen += 1
        for edge in out_edges[nid]:
            indeg[edge["to"]] -= 1
            if indeg[edge["to"]] == 0:
                ready.append(edge["to"])
    if seen != len(by_id):
        cyclic = sorted(nid for nid, deg in indeg.items() if deg > 0)
        errors.append(f"图里存在环，涉及节点: {', '.join(cyclic)}")

    # 可达性：从 start 出发所有节点都应可达（孤立节点多半是画布漏连线）
    if starts:
        seen_reach: set[str] = set()
        queue = deque([starts[0]["id"]])
        while queue:
            nid = queue.popleft()
            if nid in seen_reach:
                continue
            seen_reach.add(nid)
            for edge in out_edges[nid]:
                queue.append(edge["to"])
        unreachable = sorted(set(by_id) - seen_reach)
        if unreachable:
            errors.append(f"从 start 不可达的节点: {', '.join(unreachable)}")

    return errors


# ---------------------------------------------------------------------------
# 变量解析（受限点路径，绝无 eval）
# ---------------------------------------------------------------------------

def _lookup_path(path: str, context: dict[str, Any]) -> Any:
    """按点路径查值。未知路径抛 KeyError（工作流要确定性，静默空串会掩盖配置错误）。"""
    current: Any = context
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise KeyError(path)
    return current


def stringify_output(value: Any) -> str:
    """输出值 → 字符串（模板插值 / 轨迹预览共用）。"""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def resolve_value(value: Any, context: dict[str, Any]) -> Any:
    """递归解析 str / list / dict 里的 ``{{path}}`` 变量。

    整串恰好是一个变量的返回原始值（保类型）；混排文本里子串替换为字符串。
    """
    if isinstance(value, str):
        whole = _VAR_WHOLE_RE.match(value)
        if whole:
            return _lookup_path(whole.group(1), context)
        return _VAR_RE.sub(lambda m: stringify_output(_lookup_path(m.group(1), context)), value)
    if isinstance(value, list):
        return [resolve_value(item, context) for item in value]
    if isinstance(value, dict):
        return {key: resolve_value(item, context) for key, item in value.items()}
    return value


def truncate_text(text: str, limit: int = NODE_OUTPUT_MAX_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n…[截断，原长 {len(text)} 字符]"


# ---------------------------------------------------------------------------
# 调度器
# ---------------------------------------------------------------------------

Handler = Callable[[dict[str, Any], dict[str, Any]], Awaitable[Any]]
"""节点处理器签名：(resolved_params, context) -> output。由 nodes.py 提供。"""

StepCallback = Callable[[str, str, int, Any, str | None], None]
"""步骤回调签名：(node_id, status, duration_ms, output_preview, error)。status: done/failed/skipped。"""


class WorkflowExecutor:
    """事件驱动的单路径流调度器。

    v2 语义：
    - fan-out：非条件节点允许多条出边，就绪同批并发执行；
    - 汇聚：节点在**所有入边来源终态**后就绪；任一来源 done 即执行，
      全部 skipped 则跳过（skipped 向下游传播）；
    - 人工输入屏障：human_input 延迟到其它全部节点终态才提问；
    - 失败：并发批内其余节点跑完（轨迹完整）后上抛首个 WorkflowNodeError。
    """

    def __init__(
        self,
        graph: dict[str, Any],
        *,
        handlers: dict[str, Handler],
        node_timeout_seconds: int = DEFAULT_NODE_TIMEOUT_SECONDS,
        on_step: StepCallback | None = None,
        on_pause: Callable[..., None] | None = None,
    ) -> None:
        errors = validate_workflow_graph(graph)
        if errors:
            raise WorkflowValidationError("; ".join(errors))
        self.graph = graph
        self.handlers = handlers
        self.node_timeout_seconds = node_timeout_seconds
        self.on_step = on_step
        self.on_pause = on_pause

        self._nodes: dict[str, dict] = {n["id"]: n for n in graph["nodes"]}
        self._out: dict[str, list[dict]] = {nid: [] for nid in self._nodes}
        self._in: dict[str, list[str]] = {nid: [] for nid in self._nodes}
        for edge in graph["edges"]:
            self._out[edge["from"]].append(edge)
            self._in[edge["to"]].append(edge["from"])
        self.start_id = next(n["id"] for n in graph["nodes"] if n["type"] == "start")

    async def execute(
        self,
        inputs: dict[str, Any],
        *,
        resume_state: dict[str, Any] | None = None,
        run_timeout_seconds: int = DEFAULT_RUN_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        """执行整条流。

        返回 ``{"outputs": {node_id: output}, "paused": None}``；
        人工输入暂停时 ``{"outputs": None, "paused": {"node_id", "prompt", "fields"}}``。

        **v2 并行语义**：
        - 非条件节点允许多条出边（fan-out）——就绪的同批节点并发执行
          （asyncio.gather），LLM/HTTP 节点真正并行跑；
        - 汇聚（多入边）：**所有入边来源终态**后，任一来源 done 即执行；
          全部 skipped 则跳过（skipped 向下游传播）；
        - 人工输入是**屏障**：其它非终态节点全部结束（done/skipped）后才
          提问 —— 不会在并行分支还在跑时就打断；
        - 同图多个人工输入节点按就绪顺序逐个提问（恢复后下一个继续）。

        恢复：``resume_state`` = 暂停时的快照 +
        ``{"node_status": {nid: done|skipped}, "outputs": {nid: output},
        "answer_node": ..., "answer_value": ...}``。引擎静默重建各节点状态
        （done 节点的出边按子节点终态决定携带：done→携带、skipped→死边、
        答复节点→携带），从答复节点的下游继续。快照不依赖执行顺序，
        并行完成顺序不稳定也能正确重建。

        节点失败抛 ``WorkflowNodeError``（同批其余节点会跑完、轨迹完整）；
        总超时抛 ``WorkflowError``。
        """
        if not isinstance(inputs, dict):
            raise WorkflowError("inputs 必须是对象")

        outputs: dict[str, Any] = {}
        node_status: dict[str, str] = {}
        context: dict[str, Any] = {"inputs": inputs, "nodes": {}}
        queue: deque[str] = deque()

        # pending_in：尚未终态的入边来源集合；in_ready：已 done（携带数据）的来源
        pending_in: dict[str, set[str]] = {nid: set(self._in[nid]) for nid in self._nodes}
        in_ready: dict[str, set[str]] = {nid: set() for nid in self._nodes}

        def _advance_edge(edge: dict, from_id: str, *, carried: bool) -> None:
            to = edge["to"]
            if carried:
                in_ready[to].add(from_id)
            pending_in[to].discard(from_id)
            if not pending_in[to] and to not in node_status:
                queue.append(to)

        def _advance(from_id: str, *, carried: bool) -> None:
            for edge in self._out[from_id]:
                _advance_edge(edge, from_id, carried=carried)

        def _mark_done(nid: str, output: Any, duration_ms: int, *, silent: bool = False) -> None:
            outputs[nid] = output
            context["nodes"][nid] = {"output": output}
            node_status[nid] = "done"
            if not silent and self.on_step:
                preview = stringify_output(output)[:TRACE_PREVIEW_CHARS]
                self.on_step(nid, "done", duration_ms, preview, None)

        # ── 快照重建（静默，不回调 on_step —— 历史轨迹已在 run 记录里）──
        resume_state = resume_state or {}
        if resume_state:
            status_map: dict[str, str] = resume_state.get("node_status") or {}
            out_map: dict[str, Any] = resume_state.get("outputs") or {}
            answer_node: str | None = resume_state.get("answer_node")
            answer_value: Any = resume_state.get("answer_value")
            for nid, st in status_map.items():
                if nid not in self._nodes:
                    raise WorkflowError(f"恢复快照中的节点不存在: {nid}")
                if nid in node_status:
                    raise WorkflowError(f"恢复快照中节点重复: {nid}")
                if nid == answer_node:
                    continue  # 答复节点的输出来自本次答复
                if st == "done":
                    _mark_done(nid, out_map.get(nid), 0, silent=True)
                elif st == "skipped":
                    node_status[nid] = "skipped"
            if answer_node is not None:
                if answer_node not in self._nodes:
                    raise WorkflowError(f"恢复快照中的答复节点不存在: {answer_node}")
                _mark_done(answer_node, answer_value, 0, silent=True)
            # 推进出边：done 来源按子节点终态决定携带（done/答复→携带，
            # skipped→死边）；skipped 来源全死边。
            for nid, st in status_map.items():
                if nid not in self._nodes or nid == answer_node:
                    continue
                if node_status.get(nid) not in ("done", "skipped"):
                    continue
                for edge in self._out[nid]:
                    to = edge["to"]
                    carried = (
                        node_status.get(nid) == "done"
                        and (node_status.get(to) == "done" or to == answer_node)
                    )
                    _advance_edge(edge, nid, carried=carried)
            # 答复节点的出边全部携带 —— 它的孩子（含 end）此前从未执行，
            # 靠这里入队；否则恢复后 end 永远不会就绪，run 以"无 end 输出"收场。
            if answer_node is not None:
                _advance(answer_node, carried=True)
        else:
            queue.append(self.start_id)

        async def _exec_one(nid: str) -> None:
            """单个节点执行（不含 end/跳过/人工输入 —— 那些在同步扫描段处理）。

            失败时先落 failed 步骤轨迹再抛 WorkflowNodeError；并发批内
            其余节点会跑完（gather 收集），轨迹完整后统一上抛首个错误。
            """
            node = self._nodes[nid]
            try:
                params = resolve_value(node.get("params") or {}, context)
            except KeyError as exc:
                # 变量解析失败 = 配置错误，要落成带节点号的 failed 步骤，
                # 不能裸抛 KeyError 让 run 只剩一句 "内部错误: 'missing'"
                if self.on_step:
                    self.on_step(nid, "failed", 0, None, f"无法解析变量 {exc}")
                raise WorkflowNodeError(
                    nid, f"无法解析变量 {exc}（检查 inputs 键名与上游节点 id）"
                ) from exc

            if node["type"] == "condition":
                # 控制节点：不走 handler，直接内建判定
                hit = _evaluate_condition(params, nid)
                _mark_done(nid, hit, 0)
                for edge in self._out[nid]:
                    label = str(edge.get("label", "")).lower()
                    _advance_edge(
                        edge, nid, carried=(label == ("true" if hit else "false"))
                    )
                return

            handler = self.handlers.get(node["type"])
            if handler is None:
                raise WorkflowNodeError(nid, f"没有注册 {node['type']} 类型的处理器")
            started = time.monotonic()
            try:
                result = await asyncio.wait_for(
                    handler(params, context), timeout=self.node_timeout_seconds
                )
            except asyncio.TimeoutError as exc:
                duration = int((time.monotonic() - started) * 1000)
                if self.on_step:
                    self.on_step(nid, "failed", duration, None, "节点执行超时")
                raise WorkflowNodeError(
                    nid, f"执行超过 {self.node_timeout_seconds}s"
                ) from exc
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 —— 节点失败要带上下文向上抛
                duration = int((time.monotonic() - started) * 1000)
                if self.on_step:
                    self.on_step(nid, "failed", duration, None, str(exc))
                raise WorkflowNodeError(nid, str(exc)) from exc

            duration = int((time.monotonic() - started) * 1000)
            if isinstance(result, str):
                result = truncate_text(result)
            _mark_done(nid, result, duration)
            _advance(nid, carried=True)

        try:
            async with asyncio.timeout(run_timeout_seconds):
                while True:
                    # 同步扫描段：消费跳过/条件/end（瞬时），把真执行节点凑批。
                    # human_input 进屏障缓冲 —— 等其它节点全部终态才提问。
                    batch: list[str] = []
                    deferred_humans: list[str] = []
                    while queue:
                        nid = queue.popleft()
                        if nid in node_status:
                            continue
                        node = self._nodes[nid]

                        # 跳过判定：入边全部终态但没有一条携带数据（分支未命中）
                        if self._in[nid] and not in_ready[nid]:
                            node_status[nid] = "skipped"
                            if self.on_step:
                                self.on_step(nid, "skipped", 0, None, None)
                            _advance(nid, carried=False)
                            continue

                        if node["type"] == "end":
                            params = node.get("params") or {}
                            if "output" in params:
                                end_out = resolve_value(params["output"], context)
                            else:
                                end_out = {
                                    p: outputs[p] for p in self._in[nid] if p in outputs
                                }
                            _mark_done(nid, end_out, 0)
                            continue

                        if node["type"] == "human_input":
                            deferred_humans.append(nid)
                            continue

                        batch.append(nid)

                    if not batch:
                        if deferred_humans:
                            # 屏障成立：能走到这里说明除人工输入外全部终态
                            # （就绪节点必然已入队被消费；非终态节点链必然
                            # 延伸到就绪节点 —— 无环校验保证）。
                            nid = deferred_humans.pop(0)
                            node = self._nodes[nid]
                            params_human = node.get("params") or {}
                            prompt = str(params_human.get("prompt") or "需要人工输入")
                            raw_fields = params_human.get("fields")
                            fields = (
                                [f for f in raw_fields if isinstance(f, dict)]
                                if isinstance(raw_fields, list)
                                else None
                            )
                            if self.on_pause:
                                self.on_pause(nid, prompt, fields)
                            return {
                                "outputs": None,
                                "paused": {
                                    "node_id": nid,
                                    "prompt": prompt,
                                    "fields": fields,
                                },
                            }
                        break  # 全部终态（end 已处理）

                    # 并发执行一批（LLM/HTTP 真并行）。收集全部结果：
                    # 先把成功的标记/推进完（轨迹完整），再统一上抛首个错误。
                    results = await asyncio.gather(
                        *[_exec_one(nid) for nid in batch],
                        return_exceptions=True,
                    )
                    first_error: WorkflowNodeError | None = None
                    for outcome in results:
                        if isinstance(outcome, WorkflowNodeError):
                            if first_error is None:
                                first_error = outcome
                        elif isinstance(outcome, BaseException):
                            # CancelledError 等控制流异常立即上抛
                            raise outcome
                    if first_error is not None:
                        raise first_error

                    # 屏障缓冲的人工输入放回队列，下一轮扫描重新评估
                    for h in deferred_humans:
                        queue.append(h)
                    deferred_humans.clear()
        except TimeoutError as exc:
            raise WorkflowError(
                f"工作流总超时（{run_timeout_seconds}s），已终止"
            ) from exc

        return {"outputs": outputs, "paused": None}


def _evaluate_condition(params: dict[str, Any], node_id: str) -> bool:
    left, right, op = params.get("left"), params.get("right"), params.get("op")
    if op not in CONDITION_OPS:
        raise WorkflowNodeError(node_id, f"非法 op: {op}")
    if op == "is_empty":
        if isinstance(left, (list, dict)):
            return len(left) == 0
        return stringify_output(left).strip() == ""
    if op == "not_empty":
        return not _evaluate_condition({**params, "op": "is_empty"}, node_id)
    if op in (">", "<", ">=", "<="):
        try:
            a, b = float(left), float(right)
        except (TypeError, ValueError):
            a, b = stringify_output(left), stringify_output(right)
        if op == ">":
            return a > b
        if op == "<":
            return a < b
        if op == ">=":
            return a >= b
        return a <= b
    ls, rs = stringify_output(left), stringify_output(right)
    if op == "==":
        return ls == rs
    if op == "!=":
        return ls != rs
    if op == "contains":
        return rs in ls
    if op == "not_contains":
        return rs not in ls
    if op == "startswith":
        return ls.startswith(rs)
    return ls.endswith(rs)
