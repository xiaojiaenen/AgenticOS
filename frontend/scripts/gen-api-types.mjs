#!/usr/bin/env node
/**
 * OpenAPI → TypeScript 类型生成（docs/design/项目逐功能优化方案.md 2.2 / 战线 D）。
 *
 * 后端 FastAPI 原生导出 openapi.json；本脚本把它生成为
 * `src/types/api-schema.ts`（openapi-typescript 纯类型，无运行时依赖）。
 * 手写的 27 个 service 逐步迁移：新模块直接用本文件里的 path 类型
 * （配合 `openapi-fetch`），旧模块保持不动，接口变更会在 tsc 阶段暴露。
 *
 * 数据源优先级：
 * 1. `--url <openapi-url>` —— 从运行中的后端拉取（CI / 本地 dev server）
 * 2. `../backend/openapi.json` —— `python -c "from app.main import app; ..."`
 *    预先导出的快照（无后端运行时）
 */
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const frontendRoot = resolve(__dirname, "..");
const outFile = resolve(frontendRoot, "src/types/api-schema.ts");
const snapshot = resolve(frontendRoot, "../backend/openapi.json");

const args = process.argv.slice(2);
const urlIndex = args.indexOf("--url");
const source = urlIndex >= 0 ? args[urlIndex + 1] : snapshot;

if (!source || !existsSync(source)) {
  if (urlIndex < 0) {
    console.error(
      "[gen-api-types] 未找到 backend/openapi.json 快照，也没有 --url 参数。\n" +
        "先导出快照：cd backend && uv run python -c \"import json; from app.main import app; json.dump(app.openapi(), open('../backend/openapi.json','w'), ensure_ascii=False)\"\n" +
        "或从运行中的后端生成：npm run gen:api -- --url http://127.0.0.1:8001/openapi.json",
    );
    process.exit(1);
  }
}

mkdirSync(dirname(outFile), { recursive: true });
execFileSync("npx", ["openapi-typescript", source, "-o", outFile], {
  stdio: "inherit",
  cwd: frontendRoot,
});
console.log(`[gen-api-types] generated ${outFile}`);
