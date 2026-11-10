/**
 * Univer 卸载期的已知报错兜底。
 *
 * ## 问题
 *
 * 收起表格 / 文档面板时，`SheetEditor` 的 cleanup 会调 `univer.dispose()`。
 * Univer 内部有一批 `observable.pipe(first())` 的用法，其中两处会在
 * 卸载过程中踩空：
 *
 * - `@univerjs/ui` 的 `FloatDomSingleContent`：
 *   `useObservable(useMemo(() => layer.position$.pipe(first()), ...))`
 * - `@univerjs/docs-ui` 的段落菜单：
 *   `textSelection$.pipe(first()).subscribe(...)`
 *
 * `first()` 在「源已 complete 且一个值都没发过」时抛
 * `EmptyError: no elements in sequence`。卸载时这些 Subject 正好已经被
 * 上层 complete 掉，于是每次关面板都会在控制台留下一条报错。
 *
 * 它是**异步**抛出的（Univer 自己的 React 树在 microtask 里卸载），
 * 所以 `SheetEditor` 里 `try { instance.dispose() } catch {}` 抓不到 ——
 * 那个 try 只能挡住同步异常。
 *
 * ## 为什么在全局兜底而不是改 Univer
 *
 * 那是 node_modules 里的第三方代码，改不动也不该改（升级即丢）。而这条
 * 报错对我们的功能**没有实际影响**：面板已经关了，用户再打开时是一个
 * 全新实例。它只是脏控制台，会掩盖真正的错误。
 *
 * 所以这里用「时间窗 + 消息特征」双重判定把它吞掉，其余错误一律放行：
 * 只有恰好在 Univer 卸载窗口内（默认 2 秒）抛出、且消息是 rxjs 的
 * EmptyError 文案时才算命中。窗口外或文案不符的一律照常上报。
 */

const UNIVER_TEARDOWN_WINDOW_MS = 2000;

/** rxjs `first()` / `last()` 在空流上的报错文案 */
const EMPTY_SEQUENCE_PATTERN = /no elements in sequence/i;

let teardownUntil = 0;
let installed = false;

/** 在调用 `univer.dispose()` 之前打点，开启兜底窗口。 */
export function beginUniverTeardown(): void {
  teardownUntil = Date.now() + UNIVER_TEARDOWN_WINDOW_MS;
  install();
}

function isKnownUniverTeardownNoise(reason: unknown): boolean {
  if (Date.now() > teardownUntil) return false;
  const message =
    reason instanceof Error
      ? reason.message
      : typeof reason === 'string'
        ? reason
        : '';
  return EMPTY_SEQUENCE_PATTERN.test(message);
}

/** 仅供单测：判定函数不依赖 DOM，可独立验证。 */
export { isKnownUniverTeardownNoise };

function install(): void {
  if (installed || typeof window === 'undefined') return;
  installed = true;

  // Univer 走的是 promise 链，EmptyError 以 unhandledrejection 形式冒出来
  window.addEventListener('unhandledrejection', (event) => {
    if (!isKnownUniverTeardownNoise(event.reason)) return;
    event.preventDefault();
    if (import.meta.env.DEV) {
      console.debug('[univer] 忽略卸载期的 EmptyError（rxjs first() 踩空）');
    }
  });

  // 少数路径下它会作为同步异常冒到 window.onerror
  window.addEventListener('error', (event) => {
    if (!isKnownUniverTeardownNoise(event.error ?? event.message)) return;
    event.preventDefault();
  });
}
