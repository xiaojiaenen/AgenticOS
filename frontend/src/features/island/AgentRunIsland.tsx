/**
 * AI 对话运行中的实时状态岛（本项目最核心的「耗时长任务」）。
 *
 * 这个应用里一次 agent 运行可能持续几十秒到几分钟，期间经历
 * thinking → streaming → generating_ppt → rendering_ppt 几个阶段，
 * 而且**用户在滚动/切会话时看不到输入区那条进度提示**。
 *
 * 映射依据（skill §3 三问）：
 * - 是什么：一个笔尖 glyph（它在替你干活）
 * - 一眼要看什么：步数（第 3/10 步）或流式百分比
 * - 展开看什么：当前阶段 + 智能体名 + 已输出的字数 + 步进条
 *
 * 用 `group="agent-run"`：同一个会话的多次运行应当轮流显示，而不是并排。
 * 结束时不 alert（常规完成不该抢注意力），失败时 alert（用户必须知道）。
 */
import * as React from 'react';

import { Glyph } from '@/components/islandcn/glyph';
import { PencilGlyph, WarningGlyph, CheckGlyph } from '@/components/islandcn/glyphs';
import { BottomBar, CaptionButton, ExpandedBottom, SensorRow } from '@/components/islandcn/island-layout';
import {
  CompactText,
  ContextLabel,
  ExpandedSubtitle,
  ExpandedValue,
  MinimalPair,
  NumberText,
} from '@/components/islandcn/island-text';
import { LinearProgress } from '@/components/islandcn/linear-progress';
import { islandAccent, islandInk, islandMono } from '@/components/islandcn/theme';
import { useActivity } from '@/components/islandcn/use-activity';
import { useChatStore } from '@/stores/chatStore';
import { useRunControlStore } from './runControlStore';

/**
 * 阶段 → 措辞 + 进度权重。
 *
 * 三档措辞各有宽度预算（15pt semibold 实测）：
 * - `verb` 进展开视图的 ContextLabel，可以长
 * - `compactWord` 进紧凑胶囊，**必须 ≤ 4 个汉字**（4 字 = 60px，
 *   槽位上限 72px；5 字 = 75px 会被省略成"生成幻…"）
 * - `short` 与步数拼接（"思考 3/10" = 64px），同样 2 字
 */
const PHASES: Record<
  string,
  { verb: string; compactWord: string; short: string; weight: number; accent: string }
> = {
  thinking: {
    verb: '思考中',
    compactWord: '正在思考',
    short: '思考',
    weight: 0.15,
    accent: islandAccent.blue,
  },
  streaming: {
    verb: '生成回答',
    compactWord: '正在回复',
    short: '回复',
    weight: 0.6,
    accent: islandAccent.blue,
  },
  generating_ppt: {
    verb: '生成幻灯片',
    compactWord: '生成PPT',
    short: '做PPT',
    weight: 0.35,
    accent: islandAccent.purple,
  },
  rendering_ppt: {
    verb: '渲染预览',
    compactWord: '渲染中',
    short: '渲染',
    weight: 0.85,
    accent: islandAccent.purple,
  },
  rendering_website: {
    verb: '构建网站',
    compactWord: '建站中',
    short: '建站',
    weight: 0.85,
    accent: islandAccent.green,
  },
};

/**
 * 用 `label` 细分同一 phase 内的子状态。
 *
 * 后端把「正在上传文件」也归在 thinking 阶段（先传文件、再推理）。岛上
 * 措辞要跟着 label 变，否则用户在传一个 20MB 附件时只看到"思考中"。
 */
function wordsFor(
  phase: string,
  label: string,
): { verb: string; compactWord: string; short: string } {
  if (label.includes('上传')) return { verb: '上传文件', compactWord: '正在上传', short: '上传' };
  if (label.includes('读取') || label.includes('解析'))
    return { verb: '读取文档', compactWord: '读取文档', short: '读取' };
  const preset = PHASES[phase];
  if (preset) return preset;
  const fallback = label || '处理中';
  return { verb: fallback, compactWord: fallback, short: fallback.slice(0, 4) };
}

/** 这段脏活只在这一个组件里：把 runStatus 变成 island 的四个槽位。 */
export const AgentRunIsland: React.FC = () => {
  const runStatus = useChatStore((s) => s.runStatus);
  const currentSessionId = useChatStore((s) => s.currentSessionId);
  const sessions = useChatStore((s) => s.sessions);
  // 「停止」由 Chat 页注册（岛在 App 根，拿不到 useChatStream 的闭包）
  const stop = useRunControlStore((s) => s.stop);
  const handleStop = React.useCallback(() => stop?.(), [stop]);

  const { phase, label, step, maxSteps } = runStatus;
  const running = phase !== 'idle' && phase !== 'done' && phase !== 'error';

  // 当前会话的智能体名（展开视图里显示"谁在干活"）
  const currentSession = React.useMemo(
    () => sessions.find((s) => s.id === currentSessionId),
    [sessions, currentSessionId],
  );
  const agentName = currentSession?.agentName || '智能体';

  // 已输出的字数：流式阶段最直观的"在动"的指标
  const outputChars = React.useMemo(() => {
    const last = [...(currentSession?.messages ?? [])].reverse().find((m) => m.role === 'model');
    return (last?.text ?? '').length;
  }, [currentSession]);

  // 上下文状态（展开视图）：第几轮对话 + 是否已压缩。
  // 数据是真实的：轮数 = 会话里用户消息数；压缩标记来自后端每轮回传的会话状态。
  const turnCount = React.useMemo(
    () => (currentSession?.messages ?? []).filter((m) => m.role === 'user').length,
    [currentSession],
  );
  const contextCompressed = currentSession?.contextCompressed ?? false;

  const base = PHASES[phase];
  const words = wordsFor(phase, label);
  const accent = base?.accent ?? islandAccent.blue;
  const weight = base?.weight ?? 0.3;
  const stepText = step && maxSteps ? `${step}/${maxSteps}` : '';
  // 总体进度：阶段基线 + 阶段内的步数推进
  const progress = step && maxSteps
    ? Math.min(0.95, weight + (step / maxSteps) * (1 - weight))
    : weight;

  // 非运行态（done/error/idle）不渲染 —— 结束由外层 effect 驱动
  if (!running) return null;

  return (
    <AgentRunActivity
      phase={phase}
      verb={words.verb}
      accent={accent}
      progress={progress}
      stepText={stepText}
      compactWord={words.short}
      agentName={agentName}
      outputChars={outputChars}
      turnCount={turnCount}
      contextCompressed={contextCompressed}
      canStop={stop !== null}
      onStop={handleStop}
    />
  );
};

/**
 * 真正的 activity 组件：只在运行中挂载，卸载即结束活动。
 * （`useActivity` 的语义就是「渲染即开始，卸载即结束」。）
 */
const AgentRunActivity: React.FC<{
  phase: string;
  verb: string;
  accent: string;
  progress: number;
  stepText: string;
  compactWord: string;
  agentName: string;
  outputChars: number;
  turnCount: number;
  contextCompressed: boolean;
  canStop: boolean;
  onStop: () => void;
}> = ({ phase, verb, accent, progress, stepText, compactWord, agentName, outputChars, turnCount, contextCompressed, canStop, onStop }) => {
  useActivity(
    () => ({
      id: 'agent-run',
      // 同一会话的多次运行轮流显示，不并排
      group: 'agent-run',
      // 屏幕阅读器读这句
      label: `${agentName}${verb}${stepText ? `，第 ${stepText} 步` : ''}${turnCount > 0 ? `，第 ${turnCount} 轮对话` : ''}${contextCompressed ? '，上下文已压缩' : ''}`,
      compact: {
        leading: <Glyph icon={PencilGlyph} color={accent} />,
        // 紧凑槽上限 72px（15pt semibold 实测）：必须"词 + 数字"一起说清在干什么，
        // 只给数字（"3/10"）用户不知道那是什么。带步数时用两字词，"PPT 3/10"=65.5px。
        trailing: (
          <CompactText>
            {stepText ? `${compactWord} ${stepText}` : verb}
          </CompactText>
        ),
      },
      minimal: (
        <MinimalPair
          leading={<Glyph icon={PencilGlyph} color={accent} />}
          trailing={
            <CompactText>{stepText ? `${compactWord} ${stepText}` : verb}</CompactText>
          }
        />
      ),
      expanded: {
        leading: (
          <SensorRow glyph={<Glyph icon={PencilGlyph} color={accent} size={18} />}>
            <ContextLabel>{verb}</ContextLabel>
          </SensorRow>
        ),
        bottom: (
          <ExpandedBottom gap={6}>
            <ExpandedValue>
              {/* 流式阶段用字数当"大数字"：它是真在变的量 */}
              <NumberText value={outputChars} />
            </ExpandedValue>
            <ExpandedSubtitle color={islandInk.primary}>
              {agentName}
              {stepText ? ` · 第 ${stepText} 步` : ''}
              {turnCount > 0 ? ` · 第 ${turnCount} 轮对话` : ''}
              {contextCompressed ? ' · 上下文已压缩' : ''}
            </ExpandedSubtitle>
            <BottomBar>
              <LinearProgress value={progress} color={accent} height={5} />
            </BottomBar>
            {/* 展开就说明用户在盯着它看 —— 这时最可能想做的是「停掉」。
                只在聊天页注册过停止实现时显示（其它页面没有可停的运行）。 */}
            {canStop ? (
              <div style={{ display: 'flex', justifyContent: 'flex-end', paddingTop: 2 }}>
                <CaptionButton color={islandInk.secondary} label="停止本轮生成" onPress={onStop}>
                  停止
                </CaptionButton>
              </div>
            ) : null}
          </ExpandedBottom>
        ),
      },
    }),
    [phase, verb, accent, progress, stepText, compactWord, agentName, outputChars, turnCount, contextCompressed, canStop, onStop],
  );

  return null;
};

/** 运行失败时的短促提示：用户必须注意到，所以 alert。 */
export const AgentRunErrorIsland: React.FC = () => {
  const runStatus = useChatStore((s) => s.runStatus);
  const [armed, setArmed] = React.useState(false);

  // phase 变成 error 的那一刻 armed=true；用户看到后 6 秒自动收掉
  React.useEffect(() => {
    if (runStatus.phase !== 'error') {
      setArmed(false);
      return;
    }
    setArmed(true);
    const timer = window.setTimeout(() => setArmed(false), 6000);
    return () => window.clearTimeout(timer);
  }, [runStatus.phase]);

  if (!armed) return null;
  return <AgentErrorActivity message={runStatus.label || '本轮回复失败'} />;
};

const AgentErrorActivity: React.FC<{ message: string }> = ({ message }) => {
  useActivity(
    () => ({
      id: 'agent-run-error',
      label: `运行失败：${message}`,
      // 失败必须让用户注意到
      alert: true,
      compact: {
        leading: <Glyph icon={WarningGlyph} color={islandAccent.red} />,
      },
      minimal: <Glyph icon={WarningGlyph} color={islandAccent.red} />,
      expanded: {
        leading: (
          <SensorRow glyph={<Glyph icon={WarningGlyph} color={islandAccent.red} size={18} />}>
            <ContextLabel>失败</ContextLabel>
          </SensorRow>
        ),
        bottom: (
          <ExpandedBottom gap={4}>
            <ExpandedSubtitle color={islandInk.primary}>{message}</ExpandedSubtitle>
          </ExpandedBottom>
        ),
      },
    }),
    [message],
  );

  return null;
};

/** 成功完成的轻提示：不 alert，几秒后自己走。 */
export const AgentRunDoneIsland: React.FC = () => {
  const runStatus = useChatStore((s) => s.runStatus);
  const [armed, setArmed] = React.useState(false);

  React.useEffect(() => {
    if (runStatus.phase !== 'done') {
      setArmed(false);
      return;
    }
    setArmed(true);
    const timer = window.setTimeout(() => setArmed(false), 2500);
    return () => window.clearTimeout(timer);
  }, [runStatus.phase]);

  if (!armed) return null;
  return <AgentDoneActivity />;
};

const AgentDoneActivity: React.FC = () => {
  // 结束那一刻的会话用量：本轮 token 数、耗时、模型调用次数。
  // lastUsage 由后端随会话状态回传（每轮结束更新），是真实值不是估算的 UI 数字。
  const session = useChatStore((s) => s.sessions.find((x) => x.id === s.currentSessionId));
  const usage = session?.lastUsage ?? null;
  const totalTokens = usage
    ? Number(
        usage.total_tokens ??
          (Number(usage.input_tokens ?? usage.prompt_tokens ?? 0) +
            Number(usage.output_tokens ?? usage.completion_tokens ?? 0)),
      )
    : 0;
  const tokenText = totalTokens >= 1000 ? `${(totalTokens / 1000).toFixed(1)}k` : `${totalTokens}`;
  const latencyMs = session?.latencyMs ?? null;
  const llmCalls = session?.llmCalls ?? null;

  useActivity(
    () => ({
      id: 'agent-run-done',
      group: 'agent-run',
      label: `本轮回复已完成${totalTokens > 0 ? `，${tokenText} tokens` : ''}`,
      compact: {
        leading: <Glyph icon={CheckGlyph} color={islandAccent.green} />,
        // 光给 "12.3k" 没人知道是什么量。实测 "用量 12.3k"=71.6px 贴边，
        // 换字体就可能被裁，所以用单位本身当词（"12.3k 字" 更短也更准）
        trailing: totalTokens > 0 ? (
          <CompactText>{`${tokenText} 字`}</CompactText>
        ) : undefined,
      },
      minimal: <Glyph icon={CheckGlyph} color={islandAccent.green} />,
      expanded: {
        leading: (
          <SensorRow glyph={<Glyph icon={CheckGlyph} color={islandAccent.green} size={18} />}>
            <ContextLabel>已完成</ContextLabel>
          </SensorRow>
        ),
        bottom: totalTokens > 0 ? (
          <ExpandedBottom gap={4}>
            <ExpandedValue>
              <NumberText value={tokenText} />
              <span style={{ fontFamily: islandMono }}>tokens</span>
            </ExpandedValue>
            <ExpandedSubtitle color={islandInk.secondary}>
              {latencyMs ? `用时 ${(latencyMs / 1000).toFixed(1)}s` : ''}
              {llmCalls ? `${latencyMs ? ' · ' : ''}${llmCalls} 次模型调用` : ''}
            </ExpandedSubtitle>
          </ExpandedBottom>
        ) : undefined,
      },
    }),
    [totalTokens, tokenText, latencyMs, llmCalls],
  );

  return null;
};
