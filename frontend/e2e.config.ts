import type { E2EConfig } from 'e2e';
import { web } from '@e2e-dev/web';
import { createOpenAICompatible } from '@ai-sdk/openai-compatible';

/**
 * E2E 配置
 *
 * 模型走 DeepSeek（OpenAI 兼容端点），不引外网 AI 网关 —— 与「内网部署、
 * 前端零外网请求」的约束一致。key 只从环境变量读，不落配置文件。
 *
 * 前置条件：开发服务器已在运行（npm run dev → :3001），后端 :8001 由
 * Vite 代理 /api。这里不声明 app.command，避免与已经跑着的 dev server 抢端口；
 * CI 里改成用 command 拉起即可。
 *
 * 环境变量：
 *   DEEPSEEK_API_KEY   仅 agent.* 步骤需要（纯断言测试不需要模型）
 *   E2E_TEST_EMAIL     测试账号，默认 tester@agenticos.dev
 *   E2E_TEST_PASSWORD  测试账号密码
 */
export default {
  tests: 'tests/**/*.e2e.ts',
  targets: [
    {
      engine: web({ browser: 'chromium', viewport: { width: 1440, height: 900 } }),
      app: { url: process.env.APP_URL ?? 'http://localhost:3001' },
    },
  ],
  agents: {
    default: {
      model: createOpenAICompatible({
        name: 'deepseek',
        baseURL: process.env.DEEPSEEK_BASE_URL ?? 'https://api.deepseek.com',
        apiKey: process.env.DEEPSEEK_API_KEY,
      }).chatModel(process.env.DEEPSEEK_MODEL ?? 'deepseek-flash'),
      system: '你是严谨的 QA 助手。操作界面时只依据屏幕上真实可见的文案，不要臆测。',
      context: [
        '这是 AgenticOS —— 一个企业内部的 AI 智能体平台。',
        '管理后台在 /admin，左侧栏按分组折叠：系统总览、企业上游、对话与内容、智能体与能力、组织与系统。',
        '登录页按钮文案是「进入工作台」，不是「登录」。',
      ].join('\n'),
    },
  },
  credentials: {
    admin: {
      username: process.env.E2E_TEST_EMAIL ?? 'tester@agenticos.dev',
      // 用函数延迟到填表时求值：没设环境变量也不会在加载配置时直接失败
      password: () => process.env.E2E_TEST_PASSWORD ?? 'test123456',
    },
  },
  // 巡检类用例会依次点同一批导航项，串行避免互相干扰
  workers: 1,
  timeout: 120_000,
} satisfies E2EConfig;
