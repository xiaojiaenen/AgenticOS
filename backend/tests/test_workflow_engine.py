"""工作流引擎（P0-3 v1）单元测试。

engine.py 是纯计算（handler 注入、无 DB/LLM 依赖），这里把调度语义钉死：
校验规则、线性执行、条件分支与汇聚、skipped 传播、人工输入暂停/恢复
（跨 executor 实例模拟进程重启）、超时、变量解析安全性。
"""

from __future__ import annotations

import asyncio
import time

import pytest

from app.services.workflow.engine import (
    NODE_OUTPUT_MAX_CHARS,
    WorkflowError,
    WorkflowNodeError,
    WorkflowExecutor,
    resolve_value,
    truncate_text,
    validate_workflow_graph,
)


def _linear_graph(nodes: list[dict], skip_start_end: bool = False) -> dict:
    """按顺序把节点串成单路径流；默认首尾自动补 start/end。"""
    built = [] if skip_start_end else [{"id": "start", "type": "start"}]
    built.extend(nodes)
    if not skip_start_end:
        built.append({"id": "end", "type": "end"})
    edges = [
        {"from": built[i]["id"], "to": built[i + 1]["id"]}
        for i in range(len(built) - 1)
    ]
    return {"nodes": built, "edges": edges}


async def _start_handler(params, context):
    """与 nodes._run_start 同语义：start 的输出 = 触发输入。"""
    return dict(context.get("inputs") or {})


async def _run(graph: dict, inputs: dict | None = None, handlers=None, **kwargs) -> dict:
    handlers = dict(handlers or {})
    handlers.setdefault("start", _start_handler)
    if "template" not in handlers and any(
        n["type"] == "template" for n in graph["nodes"]
    ):
        async def _tpl(params, context):
            return params.get("template", "")

        handlers["template"] = _tpl
    ex = WorkflowExecutor(graph, handlers=handlers)
    return await ex.execute(inputs or {}, **kwargs)


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------

class TestValidation:
    def test_cycle_rejected(self):
        graph = {
            "nodes": [
                {"id": "start", "type": "start"},
                {"id": "a", "type": "template", "params": {"template": "x"}},
                {"id": "end", "type": "end"},
            ],
            "edges": [
                {"from": "start", "to": "a"},
                {"from": "a", "to": "end"},
                {"from": "end", "to": "a"},  # 回边
            ],
        }
        errors = validate_workflow_graph(graph)
        assert any("环" in e for e in errors)

    def test_missing_start_and_end(self):
        graph = {
            "nodes": [{"id": "a", "type": "template", "params": {"template": "x"}}],
            "edges": [],
        }
        errors = validate_workflow_graph(graph)
        assert any("start" in e for e in errors)
        assert any("end" in e for e in errors)

    def test_unknown_node_type(self):
        graph = _linear_graph([{"id": "a", "type": "quantum"}])
        assert any("type 非法" in e for e in validate_workflow_graph(graph))

    def test_dangling_edge(self):
        graph = {
            "nodes": [{"id": "start", "type": "start"}, {"id": "end", "type": "end"}],
            "edges": [{"from": "start", "to": "ghost"}],
        }
        assert any("不存在" in e for e in validate_workflow_graph(graph))

    def test_condition_needs_two_labeled_edges(self):
        graph = {
            "nodes": [
                {"id": "start", "type": "start"},
                {"id": "c", "type": "condition", "params": {"left": "1", "op": "==", "right": "1"}},
                {"id": "a", "type": "template", "params": {"template": "t"}},
                {"id": "end", "type": "end"},
            ],
            "edges": [
                {"from": "start", "to": "c"},
                {"from": "c", "to": "a"},  # 缺第二条出边
                {"from": "a", "to": "end"},
            ],
        }
        assert any("2 条出边" in e for e in validate_workflow_graph(graph))

        graph2 = {
            "nodes": [
                {"id": "start", "type": "start"},
                {"id": "c", "type": "condition", "params": {"left": "1", "op": "==", "right": "1"}},
                {"id": "a", "type": "template", "params": {"template": "t"}},
                {"id": "b", "type": "template", "params": {"template": "t"}},
                {"id": "end", "type": "end"},
            ],
            "edges": [
                {"from": "start", "to": "c"},
                {"from": "c", "to": "a"},
                {"from": "c", "to": "b", "label": "true"},  # 一条没标
                {"from": "a", "to": "end"},
                {"from": "b", "to": "end"},
            ],
        }
        assert any("label=true / label=false" in e for e in validate_workflow_graph(graph2))

    def test_unreachable_node_reported(self):
        graph = {
            "nodes": [
                {"id": "start", "type": "start"},
                {"id": "island", "type": "template", "params": {"template": "t"}},
                {"id": "end", "type": "end"},
            ],
            "edges": [
                {"from": "start", "to": "end"},
                # island 无入边：不可达（校验要报，运行时它会被 skipped 语义兜住）
            ],
        }
        # island 无出边也缺 1 条出边 → 两条错误都在
        errors = validate_workflow_graph(graph)
        assert any("不可达" in e for e in errors)
        assert any("出边" in e for e in errors)

    def test_valid_graph_passes(self):
        graph = _linear_graph([{"id": "t", "type": "template", "params": {"template": "ok"}}])
        assert validate_workflow_graph(graph) == []


# ---------------------------------------------------------------------------
# 变量解析
# ---------------------------------------------------------------------------

class TestResolveValue:
    def test_simple_paths(self):
        ctx = {"inputs": {"q": "问题"}, "nodes": {"n1": {"output": "答案"}}}
        assert resolve_value("问：{{inputs.q}} 答：{{nodes.n1.output}}", ctx) == "问：问题 答：答案"

    def test_structural_rendering(self):
        ctx = {"nodes": {"k": {"output": {"results": [1, 2]}}}}
        assert resolve_value("检索={{nodes.k.output}}", ctx) == '检索={"results": [1, 2]}'

    def test_unknown_path_raises(self):
        with pytest.raises(KeyError):
            resolve_value("{{inputs.missing}}", {"inputs": {}})

    def test_no_attr_chain_execution(self):
        # 路径只能进 dict 键，不能借属性链/下标逃逸到对象方法
        ctx = {"inputs": {"a": {"b": {"__class__": "fake"}}}}
        assert resolve_value("{{inputs.a.b.__class__}}", ctx) == "fake"  # 只是键名，不是属性访问
        with pytest.raises(KeyError):
            resolve_value("{{inputs.a.b.c.d}}", ctx)

    def test_truncate_marks_original_length(self):
        text = "x" * (NODE_OUTPUT_MAX_CHARS + 10)
        out = truncate_text(text)
        # 截断体不超过上限，加标注后略超几字符是刻意的（标注本身有长度）
        assert len(out) <= NODE_OUTPUT_MAX_CHARS + 30
        assert "截断" in out and "32010" in out


# ---------------------------------------------------------------------------
# 执行语义
# ---------------------------------------------------------------------------

class TestExecution:
    def test_linear_flow_with_variables(self):
        async def case():
            graph = _linear_graph([
                {"id": "greet", "type": "template", "params": {"template": "你好 {{inputs.name}}"}},
                {"id": "shout", "type": "template", "params": {"template": "{{nodes.greet.output}}！"}},
            ])
            result = await _run(graph, {"name": "小 AG"})
            assert result["paused"] is None
            assert result["outputs"]["greet"] == "你好 小 AG"
            assert result["outputs"]["shout"] == "你好 小 AG！"
            assert result["outputs"]["end"] == {"shout": "你好 小 AG！"}

        asyncio.run(case())

    def test_condition_branch_and_rejoin(self):
        """分支两端走不同路径，end 汇聚只收到实际执行侧的输出。"""
        async def case():
            graph = {
                "nodes": [
                    {"id": "start", "type": "start"},
                    {"id": "c", "type": "condition", "params": {"left": "{{inputs.score}}", "op": ">=", "right": "60"}},
                    {"id": "pass", "type": "template", "params": {"template": "及格"}},
                    {"id": "fail", "type": "template", "params": {"template": "不及格"}},
                    {"id": "end", "type": "end"},
                ],
                "edges": [
                    {"from": "start", "to": "c"},
                    {"from": "c", "to": "pass", "label": "true"},
                    {"from": "c", "to": "fail", "label": "false"},
                    {"from": "pass", "to": "end"},
                    {"from": "fail", "to": "end"},
                ],
            }
            hit = await _run(graph, {"score": "88"})
            assert hit["outputs"]["c"] is True
            assert hit["outputs"]["pass"] == "及格"
            assert "fail" not in hit["outputs"]
            assert hit["outputs"]["end"] == {"pass": "及格"}  # 汇聚只收执行侧

            miss = await _run(graph, {"score": "30"})
            assert miss["outputs"]["c"] is False
            assert miss["outputs"]["fail"] == "不及格"
            assert "pass" not in miss["outputs"]

        asyncio.run(case())

    def test_skipped_propagates_downstream(self):
        async def case():
            graph = {
                "nodes": [
                    {"id": "start", "type": "start"},
                    {"id": "c", "type": "condition", "params": {"left": "no", "op": "==", "right": "yes"}},
                    {"id": "a", "type": "template", "params": {"template": "A"}},
                    {"id": "a2", "type": "template", "params": {"template": "A2"}},
                    {"id": "b", "type": "template", "params": {"template": "B"}},
                    {"id": "end", "type": "end"},
                ],
                "edges": [
                    {"from": "start", "to": "c"},
                    {"from": "c", "to": "a", "label": "true"},
                    {"from": "c", "to": "b", "label": "false"},
                    {"from": "a", "to": "a2"},
                    {"from": "a2", "to": "end"},
                    {"from": "b", "to": "end"},
                ],
            }
            seen: list[tuple[str, str]] = []

            def on_step(nid, status, dur, out, err):
                seen.append((nid, status))

            ex = WorkflowExecutor(graph, handlers={"start": _start_handler, "template": _passthrough}, on_step=on_step)
            result = await ex.execute({})
            statuses = dict(seen)
            assert statuses["a"] == "skipped"
            assert statuses["a2"] == "skipped", "skipped 要沿链路传播到汇聚点"
            assert statuses["b"] == "done"
            assert result["outputs"]["end"] == {"b": "B"}

        asyncio.run(case())

    def test_human_input_pause_and_resume_across_instances(self):
        """暂停 → 用**新 executor**（模拟进程重启）恢复，输出连续。"""
        async def case():
            graph = _linear_graph([
                {"id": "ask", "type": "human_input", "params": {"prompt": "请确认发布"}},
                {"id": "final", "type": "template", "params": {"template": "已确认：{{nodes.ask.output}}"}},
            ])
            steps = []

            def on_step(nid, status, dur, out, err):
                steps.append((nid, status, out))

            ex1 = WorkflowExecutor(graph, handlers={"start": _start_handler, "template": _passthrough}, on_step=on_step)
            paused_result = await ex1.execute({"x": "1"})
            assert paused_result["paused"]["node_id"] == "ask"
            assert paused_result["paused"]["prompt"] == "请确认发布"
            # 节点未声明 fields 时为 None（工具桥回退到默认单字段表单）
            assert paused_result["paused"]["fields"] is None
            assert paused_result["outputs"] is None, "暂停时 outputs 为空（未走到 end）"

            # steps 里应该有 start（done）而没有 ask
            assert ("start", "done") in [(s[0], s[1]) for s in steps]

            # 恢复：快照 = 暂停时各节点终态 + 输出（steps/context 落库内容）
            resume_state = {
                "node_status": {"start": "done"},
                "outputs": {"start": {"x": "1"}},
                "answer_node": "ask",
                "answer_value": {"confirmed": True},
            }
            ex2 = WorkflowExecutor(graph, handlers={"start": _start_handler, "template": _passthrough}, on_step=on_step)
            resumed = await ex2.execute({"x": "1"}, resume_state=resume_state)
            assert resumed["paused"] is None
            assert resumed["outputs"]["ask"] == {"confirmed": True}
            assert resumed["outputs"]["final"] == "已确认：{'confirmed': True}" or \
                resumed["outputs"]["final"] == '已确认：{"confirmed": true}'

        asyncio.run(case())

    def test_human_input_after_resume_still_pauses(self):
        """恢复后路径上遇到**第二个** human_input 仍要正常暂停（resumed 标志
        不能只放行一次就吞掉后续暂停点）。"""
        async def case():
            graph = _linear_graph([
                {"id": "h1", "type": "human_input", "params": {"prompt": "第一问"}},
                {"id": "h2", "type": "human_input", "params": {"prompt": "第二问"}},
            ])
            ex = WorkflowExecutor(graph, handlers={"start": _start_handler})
            first = await ex.execute({})
            assert first["paused"]["node_id"] == "h1"
            # 恢复 h1 后应走到 h2 并再次暂停
            ex2 = WorkflowExecutor(graph, handlers={"start": _start_handler})
            second = await ex2.execute({}, resume_state={
                "node_status": {"start": "done"},
                "outputs": {"start": {}},
                "answer_node": "h1",
                "answer_value": "答1",
            })
            assert second["paused"]["node_id"] == "h2"
            assert second["paused"]["prompt"] == "第二问"

        asyncio.run(case())

    def test_human_input_fields_pass_through_pause(self):
        """human_input 节点声明的 fields 原样进入暂停信息（对话内表单渲染用）。"""
        async def case():
            graph = _linear_graph([
                {
                    "id": "h",
                    "type": "human_input",
                    "params": {
                        "prompt": "请选择发布渠道",
                        "fields": [
                            {"key": "channel", "label": "渠道", "type": "text", "required": True},
                            "junk-not-a-dict",
                        ],
                    },
                },
            ])
            ex = WorkflowExecutor(graph, handlers={"start": _start_handler})
            result = await ex.execute({})
            paused = result["paused"]
            assert paused["prompt"] == "请选择发布渠道"
            # 非 dict 项被过滤，合法项原样保留
            assert paused["fields"] == [{"key": "channel", "label": "渠道", "type": "text", "required": True}]

        asyncio.run(case())

    def test_resume_path_with_condition_branch_reconstruction(self):
        """恢复路径经过条件节点：只复活实际走过的出边（否则历史分支下游
        会被错误激活）。"""
        async def case():
            graph = {
                "nodes": [
                    {"id": "start", "type": "start"},
                    {"id": "c", "type": "condition", "params": {"left": "1", "op": "==", "right": "1"}},
                    {"id": "ask", "type": "human_input", "params": {"prompt": "?"}},
                    {"id": "never", "type": "template", "params": {"template": "N"}},
                    {"id": "end", "type": "end"},
                ],
                "edges": [
                    {"from": "start", "to": "c"},
                    {"from": "c", "to": "ask", "label": "true"},
                    {"from": "c", "to": "never", "label": "false"},
                    {"from": "ask", "to": "end"},
                    {"from": "never", "to": "end"},
                ],
            }
            seen: list[tuple[str, str]] = []

            def on_step(nid, status, dur, out, err):
                seen.append((nid, status))

            ex = WorkflowExecutor(graph, handlers={"start": _start_handler, "template": _passthrough}, on_step=on_step)
            result = await ex.execute({}, resume_state={
                "node_status": {"start": "done", "c": "done", "never": "skipped"},
                "outputs": {"start": {}, "c": True},
                "answer_node": "ask",
                "answer_value": "答复",
            })
            assert result["paused"] is None
            statuses = dict(seen)
            # 快照重建是静默的：历史节点（含 skipped 的 never）不重发轨迹；
            # 关键是「never」绝不能被执行
            assert "never" not in statuses or statuses["never"] != "done"
            assert result["outputs"]["end"] == {"ask": "答复"}

        asyncio.run(case())

    def test_resume_path_breakage_detected(self):
        async def case():
            graph = _linear_graph([
                {"id": "t", "type": "template", "params": {"template": "T"}},
            ])
            ex = WorkflowExecutor(graph, handlers={"start": _start_handler, "template": _passthrough})
            with pytest.raises(WorkflowError, match="不存在"):
                await ex.execute({}, resume_state={
                    "node_status": {"ghost": "done"},
                    "outputs": {},
                    "answer_node": None,
                    "answer_value": None,
                })

        asyncio.run(case())

    def test_node_failure_raises_with_node_id(self):
        async def boom(params, context):
            raise RuntimeError("外部依赖炸了")

        async def case():
            graph = _linear_graph([{"id": "bad", "type": "llm"}])
            ex = WorkflowExecutor(graph, handlers={"start": _start_handler, "llm": boom})
            with pytest.raises(WorkflowNodeError) as exc_info:
                await ex.execute({})
            assert exc_info.value.node_id == "bad"
            assert "外部依赖炸了" in str(exc_info.value)

        asyncio.run(case())

    def test_node_timeout(self):
        async def slow(params, context):
            await asyncio.sleep(1.0)

        async def case():
            graph = _linear_graph([{"id": "slow", "type": "llm"}])
            ex = WorkflowExecutor(graph, handlers={"start": _start_handler, "llm": slow}, node_timeout_seconds=1)
            # 总超时给足，节点超时先生效
            with pytest.raises(WorkflowNodeError, match="超过"):
                await ex.execute({}, run_timeout_seconds=30)

        asyncio.run(case())

    def test_run_total_timeout(self):
        async def slow(params, context):
            await asyncio.sleep(5.0)

        async def case():
            graph = _linear_graph([{"id": "slow", "type": "llm"}])
            ex = WorkflowExecutor(graph, handlers={"start": _start_handler, "llm": slow}, node_timeout_seconds=60)
            with pytest.raises(WorkflowError, match="总超时"):
                await ex.execute({}, run_timeout_seconds=1)

        asyncio.run(case())

    def test_output_string_truncation(self):
        async def big(params, context):
            return "y" * (NODE_OUTPUT_MAX_CHARS + 100)

        async def case():
            graph = _linear_graph([{"id": "big", "type": "llm"}])
            ex = WorkflowExecutor(graph, handlers={"start": _start_handler, "llm": big})
            result = await ex.execute({})
            assert len(result["outputs"]["big"]) <= NODE_OUTPUT_MAX_CHARS + 50

        asyncio.run(case())

    def test_steps_callbacks_fire_in_order(self):
        async def case():
            graph = _linear_graph([
                {"id": "t1", "type": "template", "params": {"template": "一"}},
                {"id": "t2", "type": "template", "params": {"template": "二"}},
            ])
            order: list[str] = []

            def on_step(nid, status, dur, out, err):
                order.append(f"{nid}:{status}")

            ex = WorkflowExecutor(graph, handlers={"start": _start_handler, "template": _passthrough}, on_step=on_step)
            await ex.execute({})
            assert order == ["start:done", "t1:done", "t2:done", "end:done"]

        asyncio.run(case())

    def test_condition_numeric_vs_string_compare(self):
        async def case():
            from app.services.workflow.engine import _evaluate_condition
            assert _evaluate_condition({"left": "9", "op": ">", "right": "10"}, "c") is False
            assert _evaluate_condition({"left": "10", "op": ">=", "right": "9.5"}, "c") is True
            assert _evaluate_condition({"left": "abc", "op": ">", "right": "abd"}, "c") is False
            assert _evaluate_condition({"left": "", "op": "is_empty", "right": None}, "c") is True
            assert _evaluate_condition({"left": "x", "op": "not_empty", "right": None}, "c") is True
            assert _evaluate_condition({"left": "hello world", "op": "contains", "right": "world"}, "c") is True

        asyncio.run(case())


class TestParallelV2:
    """v2 并行语义：fan-out 并发执行、汇合、屏障暂停、快照恢复。"""

    def _fanout_graph(self) -> dict:
        return {
            "nodes": [
                {"id": "start", "type": "start"},
                {"id": "a", "type": "template", "params": {"template": "A"}},
                {"id": "b", "type": "template", "params": {"template": "B"}},
                {"id": "end", "type": "end"},
            ],
            "edges": [
                {"from": "start", "to": "a"},
                {"from": "start", "to": "b"},
                {"from": "a", "to": "end"},
                {"from": "b", "to": "end"},
            ],
        }

    def test_fanout_runs_both_branches_and_joins(self):
        async def case():
            graph = self._fanout_graph()
            ex = WorkflowExecutor(
                graph, handlers={"start": _start_handler, "template": _passthrough}
            )
            result = await ex.execute({})
            assert result["paused"] is None
            assert result["outputs"]["a"] == "A"
            assert result["outputs"]["b"] == "B"
            # 汇聚 end 默认输出 = 两个执行侧来源
            assert result["outputs"]["end"] == {"a": "A", "b": "B"}

        asyncio.run(case())

    def test_fanout_executes_concurrently(self):
        """墙钟证明：两个 0.25s 的节点并行跑应显著快于串行的 0.5s。"""
        async def case():
            async def slow(params, context):
                await asyncio.sleep(0.25)
                return params.get("template", "")

            graph = self._fanout_graph()
            ex = WorkflowExecutor(graph, handlers={"start": _start_handler, "template": slow})
            started = time.monotonic()
            await ex.execute({})
            elapsed = time.monotonic() - started
            assert elapsed < 0.45, f"两节点应并发执行（实测 {elapsed:.2f}s ≥ 串行 0.5s）"

        asyncio.run(case())

    def test_human_input_barrier_waits_for_parallel_branches(self):
        """人工输入是屏障：并行分支还在跑时不会提问，全部终态后才暂停。"""
        async def case():
            graph = {
                "nodes": [
                    {"id": "start", "type": "start"},
                    {"id": "h", "type": "human_input", "params": {"prompt": "确认？"}},
                    {"id": "w", "type": "template", "params": {"template": "慢活"}},
                    {"id": "end", "type": "end", "params": {
                        "output": "{{nodes.h.output}}/{{nodes.w.output}}"}},
                ],
                "edges": [
                    {"from": "start", "to": "h"},
                    {"from": "start", "to": "w"},
                    {"from": "h", "to": "end"},
                    {"from": "w", "to": "end"},
                ],
            }
            pauses: list[str] = []

            def on_pause(nid, prompt, fields=None):
                pauses.append(nid)

            async def slow(params, context):
                await asyncio.sleep(0.15)
                return params.get("template", "")

            ex = WorkflowExecutor(
                graph,
                handlers={"start": _start_handler, "template": slow},
                on_pause=on_pause,
            )
            result = await ex.execute({})
            # 慢分支（0.15s）先完成，屏障等到它终态后才提问
            assert pauses == ["h"], pauses
            assert result["paused"]["node_id"] == "h"

        asyncio.run(case())

    def test_snapshot_resume_after_parallel_join(self):
        """并行汇合后的人工输入恢复：快照（与完成顺序无关）正确重建。"""
        async def case():
            graph = {
                "nodes": [
                    {"id": "start", "type": "start"},
                    {"id": "a", "type": "template", "params": {"template": "A"}},
                    {"id": "b", "type": "template", "params": {"template": "B"}},
                    {"id": "ask", "type": "human_input", "params": {"prompt": "定稿？"}},
                    {"id": "end", "type": "end", "params": {
                        "output": "{{nodes.a.output}}{{nodes.b.output}}{{nodes.ask.output}}"}},
                ],
                "edges": [
                    {"from": "start", "to": "a"},
                    {"from": "start", "to": "b"},
                    {"from": "a", "to": "ask"},
                    {"from": "b", "to": "ask"},
                    {"from": "ask", "to": "end"},
                ],
            }
            # 暂停时快照（b 先完成 —— 顺序故意与边序相反，验证顺序无关性）
            resume_state = {
                "node_status": {"start": "done", "b": "done", "a": "done"},
                "outputs": {"start": {}, "b": "B", "a": "A"},
                "answer_node": "ask",
                "answer_value": "OK",
            }
            ex = WorkflowExecutor(
                graph, handlers={"start": _start_handler, "template": _passthrough}
            )
            result = await ex.execute({}, resume_state=resume_state)
            assert result["paused"] is None
            assert result["outputs"]["end"] == "ABOK"

        asyncio.run(case())

    def test_parallel_failure_reports_after_batch_completes(self):
        """并发批内某节点失败：其余节点跑完（轨迹完整）后上抛首个错误。"""
        async def boom(params, context):
            raise RuntimeError("炸了")

        async def ok(params, context):
            await asyncio.sleep(0.05)
            return params.get("template", "")

        async def case():
            graph = self._fanout_graph()
            graph["nodes"][1]["type"] = "llm"  # 让 a 走 llm（失败）
            seen: list[tuple[str, str]] = []

            def on_step(nid, status, dur, out, err):
                seen.append((nid, status))

            ex = WorkflowExecutor(
                graph,
                handlers={"start": _start_handler, "template": ok, "llm": boom},
                on_step=on_step,
            )
            with pytest.raises(WorkflowNodeError, match="炸了"):
                await ex.execute({})
            statuses = dict(seen)
            assert statuses["b"] == "done", "批内成功节点应跑完并记录轨迹"
            assert statuses["a"] == "failed"

        asyncio.run(case())


async def _passthrough(params, context):
    return params.get("template", "")
