/**
 * A2UI 数据模型同步（双向绑定）。
 *
 * 之前的问题：表单填了值、点了按钮，只把快照随消息带走，
 * 界面本身不刷新 —— 用户改筛选条件，表格纹丝不动。
 *
 * A2UI 的 DataModel 提供了完整能力：
 *   subscribe(path, cb)  值变化时回调（组件输入 → 宿主）
 *   set(path, value)     写值并通知订阅者（宿主/智能体 → 组件）
 *   data                 当前快照
 *
 * 本模块做两件事：
 *   1. 订阅整个数据模型，把变化上报给外层（用于"跟随刷新"研判）
 *   2. 接收智能体下发的新数据，写回 DataModel 触发界面局部刷新
 */
import type { DataModel } from '@a2ui/web_core/v0_9';

export type DataModelSnapshot = Record<string, unknown>;

/** 读取数据模型的完整快照。 */
export function snapshotDataModel(dm: DataModel | null | undefined): DataModelSnapshot {
  if (!dm) return {};
  try {
    const raw = (dm as unknown as { data?: unknown }).data;
    if (raw && typeof raw === 'object') {
      return JSON.parse(JSON.stringify(raw)) as DataModelSnapshot;
    }
  } catch {
    /* 序列化失败时退回空对象，不让 UI 崩 */
  }
  return {};
}

/**
 * 订阅数据模型变化。
 *
 * A2UI 的 subscribe 以路径为单位；这里订阅根路径，
 * 任何子字段变化都会冒泡上来。返回取消订阅函数。
 */
export function watchDataModel(
  dm: DataModel | null | undefined,
  onChange: (snapshot: DataModelSnapshot) => void,
): () => void {
  if (!dm || typeof dm.subscribe !== 'function') return () => {};

  let disposed = false;
  try {
    const unsub = dm.subscribe('/', () => {
      if (disposed) return;
      onChange(snapshotDataModel(dm));
    });
    // subscribe 可能返回 unsubscribe 函数或对象
    return () => {
      disposed = true;
      if (typeof unsub === 'function') {
        (unsub as () => void)();
      } else if (unsub && typeof (unsub as { unsubscribe?: () => void }).unsubscribe === 'function') {
        (unsub as { unsubscribe: () => void }).unsubscribe();
      }
    };
  } catch {
    return () => {};
  }
}

/**
 * 把数据写回模型，触发依赖该路径的组件局部刷新。
 *
 * 智能体在 settle 阶段会下发 updateDataModel；宿主收到后调用本函数，
 * 界面里绑定了 `{path: '/xxx'}` 的组件就会自动更新 —— 不需要重渲染整个界面。
 */
export function applyDataModel(
  dm: DataModel | null | undefined,
  value: DataModelSnapshot,
  path = '/',
): void {
  if (!dm || typeof dm.set !== 'function') return;
  try {
    if (path === '/' || path === '') {
      // 整棵替换：逐键写入，避免 set('/') 的语义差异
      const current = snapshotDataModel(dm);
      for (const key of Object.keys(current)) {
        if (!(key in value)) {
          try {
            dm.delete(`/${key}`);
          } catch {
            /* 单键删除失败不阻断 */
          }
        }
      }
      for (const [key, v] of Object.entries(value)) {
        dm.set(`/${key}`, v);
      }
      return;
    }
    dm.set(path, value);
  } catch {
    /* 写入失败不该让界面崩，顶多这次不刷新 */
  }
}
