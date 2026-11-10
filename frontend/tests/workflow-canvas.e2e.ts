import { test, expect } from 'e2e';
import type { Locator } from 'e2e';

/**
 * 类型化断言包装：e2e 的 expect 有 Locator / 值两种重载，`await expect(x)`
 * 时 TS 会选中值重载，导致 toBeVisible 报「属性不存在」。
 */
const expectLocator = expect as unknown as (
  loc: Locator,
) => { toBeVisible(opts?: { timeout?: number }): Promise<void> };

/**
 * 工作流拖拽画布（React Flow）真实浏览器验证。
 *
 * jsdom 没有布局引擎，React Flow 的节点 DOM 依赖测量后才渲染 —— 单测只能
 * 证明「挂载不崩」，真实拖拽行为必须在浏览器里验。
 *
 * 断言策略（都基于**屏幕上真实存在**的元素）：
 * 1. 打开工作流 → 画布渲染出 6 个节点 + 5 条边；
 * 2. 拖动节点后，图数据里该节点的 position 被写回（拖拽真的生效）；
 * 3. 从 start 的出口圆点拖到 fail 节点，建立新连线（拖线真的连上）。
 *
 * 前置数据：backend 运行 ../scripts/seed_workflow_canvas_e2e.py
 */

const WF_NAME = 'E2E 画布工作流';

/** React Flow 为每个节点渲染 testid=rf__node-<nodeId>，比按文本定位精确。 */
const node = (screen: { getByTestId: (id: string) => import('e2e').Locator }, id: string) =>
  screen.getByTestId(`rf__node-${id}`);

/** 与 scripts/seed_workflow_canvas_e2e.py 保持一致的种子图。 */
const SEED_GRAPH = {
  nodes: [
    { id: 'start', type: 'start' },
    { id: 'greet', type: 'template', params: { template: '你好 {{inputs.name}}' } },
    { id: 'gate', type: 'condition', params: { left: '{{inputs.score}}', op: '>=', right: '60' } },
    { id: 'pass', type: 'template', params: { template: '及格' } },
    { id: 'fail', type: 'template', params: { template: '不及格' } },
    { id: 'end', type: 'end', params: { output: '{{nodes.greet.output}}' } },
  ],
  edges: [
    { from: 'start', to: 'greet' },
    { from: 'greet', to: 'gate' },
    { from: 'gate', to: 'pass', label: 'true' },
    { from: 'gate', to: 'fail', label: 'false' },
    { from: 'pass', to: 'end' },
    { from: 'fail', to: 'end' },
  ],
};

const BACKEND = 'http://127.0.0.1:8001';

/**
 * 重置用例数据：画布用例会保存图（删/加边、移动节点），
 * 不重置的话后一个用例会读到上一个用例改过的图，断言互相污染。
 * 直接打后端 API 把图改回种子形态（登录态复用 e2e.config 的 admin 账号）。
 */
async function adminAuth(): Promise<Record<string, string>> {
  const loginRes = await fetch(`${BACKEND}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      email: process.env.E2E_TEST_EMAIL ?? 'tester@agenticos.dev',
      // 与 e2e.config.ts 的 credentials 默认值保持一致（本地测试账号）
      password: process.env.E2E_TEST_PASSWORD ?? 'test123456',
    }),
  });
  if (!loginRes.ok) throw new Error(`login failed: ${loginRes.status}`);
  const { access_token } = (await loginRes.json()) as { access_token: string };
  return { Authorization: `Bearer ${access_token}`, 'Content-Type': 'application/json' };
}

async function resetWorkflowGraph() {
  const auth = await adminAuth();

  const list = await (await fetch(`${BACKEND}/api/v1/workflows`, { headers: auth })).json();
  const wf = (list.items as Array<{ id: number; name: string }>).find((w) => w.name === WF_NAME);
  if (!wf) throw new Error(`seed 数据缺失：${WF_NAME}`);

  const put = await fetch(`${BACKEND}/api/v1/workflows/${wf.id}`, {
    method: 'PUT',
    headers: auth,
    body: JSON.stringify({
      name: WF_NAME,
      description: '画布 e2e 用例数据',
      enabled: true,
      graph: SEED_GRAPH,
    }),
  });
  if (!put.ok) throw new Error(`reset failed: ${put.status} ${(await put.text()).slice(0, 200)}`);
  const check = await (await fetch(`${BACKEND}/api/v1/workflows/${wf.id}`, { headers: auth })).json();
  if (check.graph.edges.length !== SEED_GRAPH.edges.length) {
    throw new Error(`reset 未生效：期望 ${SEED_GRAPH.edges.length} 条边，实际 ${check.graph.edges.length}`);
  }
}

/** 读后端当前图数据（校验拖拽/连线是否真的落库）。 */
async function fetchWorkflowGraph(): Promise<{
  nodes: Array<{ id: string; type: string; position?: { x: number; y: number } }>;
  edges: Array<{ from: string; to: string; label?: string }>;
}> {
  const auth = await adminAuth();
  const list = await (await fetch(`${BACKEND}/api/v1/workflows`, { headers: auth })).json();
  const wf = (list.items as Array<{ id: number; name: string }>).find((w) => w.name === WF_NAME);
  if (!wf) throw new Error(`seed 数据缺失：${WF_NAME}`);
  const detail = await (await fetch(`${BACKEND}/api/v1/workflows/${wf.id}`, { headers: auth })).json();
  return detail.graph;
}

/** 侧边栏是分组折叠结构：先进「工作流」分组项（自动展开该组）。 */
async function gotoWorkflows(app: any, screen: any) {
  await app.open('/admin');
  // 侧边栏是「分组 → 展开 → 子项」两级结构：先展开分组再点子项
  await screen.getByRole('button', /^智能体与能力/).tap();
  const navItem = screen.getByRole('button', /^工作流/);
  await expectLocator(navItem).toBeVisible({ timeout: 10_000 });
  await navItem.tap();
  await expectLocator(screen.getByText('把预编排的节点流程', { exact: false })).toBeVisible({
    timeout: 15_000,
  });
}

async function openWorkflow(screen: any) {
  // 用 CSS + hasText 定位列表行（e2e 框架的 getByRole 不支持祖先链组合），
  // 再在该行内找「编辑」按钮
  const row = screen.getByRole('listitem').filter({ hasText: WF_NAME });
  await expectLocator(row).toBeVisible({ timeout: 20_000 });
  await row.getByRole('button', '编辑').tap();
  await expectLocator(screen.getByText('节点图').first()).toBeVisible({ timeout: 15_000 });
}

test.describe('workflow drag canvas', () => {
  test('renders nodes and edges from the graph', { session: 'admin' }, async ({ app, screen }) => {
    await resetWorkflowGraph();
    await gotoWorkflows(app, screen);
    await openWorkflow(screen);

    // 画布已渲染：每个节点都在 DOM 中且有多边形尺寸（React Flow 测量后渲染）
    for (const id of ['start', 'greet', 'gate', 'pass', 'fail', 'end']) {
      const box = await node(screen, id).boundingBox();
      expect(box, `节点 ${id} 未渲染`).not.toBeNull();
      expect(box!.width).toBeGreaterThan(0);
    }
    // 分支标签可读（condition 的 true/false）
    await expect(screen.getByText('true', { exact: true }).first()).toBeVisible();
    await expect(screen.getByText('false', { exact: true }).first()).toBeVisible();
    // 侧栏连线列表与图一致（种子 6 条边；用删除按钮的可访问名断言最稳）
    await expect(screen.getByRole('button', '删除连线 start->greet')).toBeVisible();
    await expect(screen.getByRole('button', '删除连线 fail->end')).toBeVisible();
  });

  test('dragging a node persists its position into the graph', { session: 'admin' }, async ({ app, screen }) => {
    await resetWorkflowGraph();
    await gotoWorkflows(app, screen);
    await openWorkflow(screen);

    const greet = node(screen, 'greet');
    await expectLocator(greet).toBeVisible({ timeout: 15_000 });
    const before = await greet.boundingBox();
    expect(before).not.toBeNull();

    // 指针拖拽：screen.swipe 走视口坐标路径（from → to），文档平台上是 mouse drag
    await screen.swipe({
      from: { x: before!.x + before!.width / 2, y: before!.y + before!.height / 2 },
      to: { x: before!.x + before!.width / 2 + 140, y: before!.y + before!.height / 2 + 90 },
    });

    const after = await greet.boundingBox();
    expect(after!.x).toBeGreaterThan(before!.x + 60);

    // 拖节点不应误增删边
    await expect(screen.getByRole('button', '删除连线 start->greet')).toBeVisible();
    await expect(screen.getByRole('button', '删除连线 fail->end')).toBeVisible();

    // 保存后直接读后端图数据：position 必须已写入（屏幕坐标受 fitView 缩放影响，
    // 不能跨次比较；图数据才是「拖拽是否真的落库」的判据）
    await screen.getByRole('button', '保存').tap();
    await expect(screen.getByText(WF_NAME)).toBeVisible({ timeout: 15_000 });

    const saved = await fetchWorkflowGraph();
    const greetNode = saved.nodes.find((n) => n.id === 'greet') as
      | { position?: { x: number; y: number } }
      | undefined;
    expect(greetNode?.position, '拖拽后的 position 没有写进图').toBeDefined();
    expect(greetNode!.position!.x).toBeGreaterThan(0);
  });

  test('dragging from a handle creates a new edge', { session: 'admin' }, async ({ app, screen }) => {
    await resetWorkflowGraph();
    await gotoWorkflows(app, screen);
    await openWorkflow(screen);
    await expect(screen.getByRole('button', '删除连线 start->greet')).toBeVisible({ timeout: 15_000 });

    const failNode = node(screen, 'fail');
    await expectLocator(failNode).toBeVisible({ timeout: 15_000 });

    const sourceHandle = screen.getByLabel('start 的输出连接点');
    await expectLocator(sourceHandle).toBeVisible();
    const h = await sourceHandle.boundingBox();
    const f = await failNode.boundingBox();
    expect(h).not.toBeNull();
    expect(f).not.toBeNull();

    // React Flow 要求拖到**目标节点的 target handle** 才建立连接
    const targetHandle = screen.getByLabel('fail 的输入连接点');
    await expectLocator(targetHandle).toBeVisible();
    await sourceHandle.dragTo(targetHandle);

    // 新连线 start→fail 出现在边列表里（边不存在 = 拖线没建成）
    await expect(screen.getByRole('button', '删除连线 start->fail')).toBeVisible({ timeout: 10_000 });
  });
});
