"""
ContentGraph 多帧 Storyboard
完整对标 html-video 原版 content-graph 包
"""

from typing import Optional
from collections import defaultdict

from .types import (
    ContentGraph,
    Node,
    GraphEdge,
    EdgeKind,
    NodeKind,
    GraphValidationResult,
    GraphValidationError,
)


DEFAULT_FRAME_DURATION_SEC = 3.0


def validate(graph: ContentGraph) -> GraphValidationResult:
    """
    校验 ContentGraph：
    1. 空图检测
    2. 重复节点 ID
    3. 无效 kind
    4. 自环边
    5. 边端点引用未知节点
    6. 依赖边环路检测（DFS 着色法：WHITE→GRAY→BLACK）
    """
    errors: list[GraphValidationError] = []
    warnings: list[GraphValidationError] = []

    # 1. 空图检测
    if not graph.nodes:
        errors.append(GraphValidationError(
            code="empty-graph",
            message="ContentGraph must have at least one node",
        ))
        return GraphValidationResult(ok=False, errors=errors, warnings=warnings)

    # 2. 重复节点 ID
    seen_ids: set[str] = set()
    for node in graph.nodes:
        if node.id in seen_ids:
            errors.append(GraphValidationError(
                code="duplicate-node-id",
                message=f"Duplicate node ID: {node.id}",
                ref=node.id,
            ))
        seen_ids.add(node.id)

    # 3. 无效 kind
    valid_kinds = {k.value for k in NodeKind}
    for node in graph.nodes:
        if node.kind.value not in valid_kinds:
            errors.append(GraphValidationError(
                code="invalid-node-kind",
                message=f"Invalid node kind '{node.kind}' for node '{node.id}'",
                ref=node.id,
            ))

    # 构建节点 ID 集合
    node_ids = {node.id for node in graph.nodes}

    # 4. 自环边
    # 5. 边端点引用未知节点
    for edge in graph.edges:
        if edge.from_node == edge.to_node:
            errors.append(GraphValidationError(
                code="self-edge",
                message=f"Self-edge detected: {edge.from_node} -> {edge.to_node}",
                ref=f"{edge.from_node}->{edge.to_node}",
            ))
        if edge.from_node not in node_ids:
            errors.append(GraphValidationError(
                code="edge-from-unknown-node",
                message=f"Edge references unknown source node: {edge.from_node}",
                ref=edge.from_node,
            ))
        if edge.to_node not in node_ids:
            errors.append(GraphValidationError(
                code="edge-to-unknown-node",
                message=f"Edge references unknown target node: {edge.to_node}",
                ref=edge.to_node,
            ))

    # 6. 依赖边环路检测（DFS 着色法）
    # 只检测 dependency 边的环路
    dep_edges: dict[str, list[str]] = defaultdict(list)
    for edge in graph.edges:
        if edge.kind == EdgeKind.DEPENDENCY:
            dep_edges[edge.from_node].append(edge.to_node)

    if dep_edges and _has_cycle(dep_edges, node_ids):
        errors.append(GraphValidationError(
            code="cycle",
            message="Dependency edges form a cycle",
        ))

    ok = len(errors) == 0
    return GraphValidationResult(ok=ok, errors=errors, warnings=warnings)


def _has_cycle(edges: dict[str, list[str]], all_nodes: set[str]) -> bool:
    """
    DFS 着色法检测环路
    WHITE (0): 未访问
    GRAY (1): 正在访问（在当前 DFS 路径上）
    BLACK (2): 已完成访问
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {node: WHITE for node in all_nodes}

    def dfs(node: str) -> bool:
        color[node] = GRAY
        for neighbor in edges.get(node, []):
            if color[neighbor] == GRAY:
                return True  # 找到环
            if color[neighbor] == WHITE and dfs(neighbor):
                return True
        color[node] = BLACK
        return False

    for node in all_nodes:
        if color[node] == WHITE:
            if dfs(node):
                return True
    return False


def topo_sort(graph: ContentGraph) -> list[str]:
    """
    Kahn 拓扑排序：
    - 只有 dependency 边约束顺序
    - sequence 边作为软偏好（tiebreaker）
    - 同级节点按原始数组顺序稳定排序
    - 返回节点 ID 列表（播放顺序）
    - 如果存在环，抛出异常
    """
    # 构建依赖图（只使用 dependency 边）
    in_degree: dict[str, int] = {node.id: 0 for node in graph.nodes}
    dep_adj: dict[str, list[str]] = defaultdict(list)
    seq_adj: dict[str, list[str]] = defaultdict(list)

    for edge in graph.edges:
        if edge.kind == EdgeKind.DEPENDENCY:
            dep_adj[edge.from_node].append(edge.to_node)
            in_degree[edge.to_node] += 1
        elif edge.kind == EdgeKind.SEQUENCE:
            seq_adj[edge.from_node].append(edge.to_node)

    # 原始节点顺序（用于稳定排序）
    node_order = {node.id: i for i, node in enumerate(graph.nodes)}

    # Kahn 算法
    # 初始队列：入度为 0 的节点，按原始顺序排序
    queue = sorted(
        [node.id for node in graph.nodes if in_degree[node.id] == 0],
        key=lambda x: node_order[x],
    )
    result: list[str] = []

    while queue:
        # 从队列中取出第一个节点
        current = queue.pop(0)
        result.append(current)

        # 收集所有后继节点
        successors = set(dep_adj.get(current, []))

        # 更新入度
        for successor in successors:
            in_degree[successor] -= 1
            if in_degree[successor] == 0:
                queue.append(successor)

        # 使用 sequence 边作为 tiebreaker 排序
        if queue:
            # 构建 sequence 偏好
            seq_prefs: dict[str, int] = {}
            for node_id in queue:
                # 计算有多少 sequence 边指向队列中的其他节点
                pref_score = 0
                for seq_target in seq_adj.get(current, []):
                    if seq_target in queue:
                        pref_score += 1
                seq_prefs[node_id] = pref_score

            queue.sort(key=lambda x: (-seq_prefs.get(x, 0), node_order[x]))

    # 检测环路
    if len(result) != len(graph.nodes):
        missing = set(node_order.keys()) - set(result)
        raise ValueError(f"Cycle detected in dependency edges. Missing nodes: {missing}")

    return result


def total_duration_sec(graph: ContentGraph) -> float:
    """沿 topo 顺序累加每帧 duration_sec（默认 3s）"""
    order = topo_sort(graph)
    node_map = {node.id: node for node in graph.nodes}
    total = 0.0
    for node_id in order:
        node = node_map.get(node_id)
        if node:
            total += node.duration_sec or DEFAULT_FRAME_DURATION_SEC
    return total


def get_node(graph: ContentGraph, node_id: str) -> Optional[Node]:
    """按 ID 查找节点"""
    for node in graph.nodes:
        if node.id == node_id:
            return node
    return None
