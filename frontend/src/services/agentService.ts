/**
 * Agent SSE 服务（原 1023 行单文件，3G.3 拆分为 agent/ 模块）。
 *
 * 拆分后本文件是**纯 re-export 门面**：18 个消费方的 import 路径不变，
 * 语义零改动。分层：
 * - agent/shared.ts   —— 类型契约 + 工具结果映射 helpers + 端点常量
 * - agent/events.ts   —— applyAgentEvent（16 事件分发，纯函数）
 * - agent/stream.ts   —— sendMessageStream（fetchEventSource + 心跳超时）
 * - agent/api.ts      —— 审批/决策/制品/会话等 REST 调用
 */
export * from './agent/shared';
export * from './agent/events';
export * from './agent/stream';
export * from './agent/api';
