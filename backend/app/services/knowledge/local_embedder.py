"""离线（本地）嵌入后端。

为什么要它：线上 embedding API 有两个现实问题 ——
1. 内网/断网部署根本没有出口；
2. 知识库动辄几万页，每次重建索引都在烧 API 额度。

本地模型把这两件事一次性解决。默认用 sentence-transformers（最成熟、
模型最多），没装时给出可执行的安装提示而不是静默失败。

设计取舍
--------
- **懒加载**：模型加载要几秒到几十秒、占几百 MB 内存。只在第一次真正
  需要向量时才加载，避免「配了但没用到」的部署白付内存。
- **单例 + 线程锁**：模型对象不是线程安全的，检索是同步调用（可能在
  FastAPI 的线程池里并发跑），必须串行化推理。
- **维度自检**：本地模型维度与配置不符时报错而不是截断 —— 维度错了
  向量库里已有的数据全部作废，静默截断会让检索结果莫名其妙地差。
"""

from __future__ import annotations

import logging
import threading
from typing import Sequence

logger = logging.getLogger("knowledge.embedder.local")

# 推荐的本地模型（按体积/效果平衡排序，供前端提示用）
SUGGESTED_MODELS: tuple[dict[str, str], ...] = (
    {
        "id": "BAAI/bge-m3",
        "dims": "1024",
        "note": "多语言效果最好，1.2GB。中文知识库首选",
    },
    {
        "id": "BAAI/bge-base-zh-v1.5",
        "dims": "768",
        "note": "中文专用，400MB。体积与效果平衡",
    },
    {
        "id": "BAAI/bge-small-zh-v1.5",
        "dims": "512",
        "note": "中文专用，100MB。轻量部署",
    },
    {
        "id": "sentence-transformers/all-MiniLM-L6-v2",
        "dims": "384",
        "note": "英文为主，90MB。最轻",
    },
)


class LocalEmbedderUnavailable(RuntimeError):
    """本地嵌入不可用（未安装依赖或模型加载失败）。"""


class LocalEmbedder:
    """sentence-transformers 本地嵌入。"""

    def __init__(self, model_name: str, *, expected_dims: int | None = None) -> None:
        self._model_name = model_name
        self._expected_dims = expected_dims
        self._model = None
        self._lock = threading.Lock()
        self._dims: int | None = None

    @property
    def model(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int | None:
        return self._dims

    def _ensure_model(self):
        """懒加载模型。首次调用会阻塞（下载/加载），之后复用。"""
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is not None:
                return self._model
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise LocalEmbedderUnavailable(
                    "未安装 sentence-transformers。安装方式：\n"
                    "  pip install sentence-transformers\n"
                    "首次使用会自动下载模型（需要外网或本地模型目录）。"
                ) from exc

            logger.info("loading local embedding model: %s", self._model_name)
            try:
                model = SentenceTransformer(self._model_name)
            except Exception as exc:  # noqa: BLE001
                raise LocalEmbedderUnavailable(
                    f"加载本地模型「{self._model_name}」失败：{exc}\n"
                    "如果是离线环境，请先把模型下载到本地目录，"
                    "然后把「离线模型路径」填成该目录的绝对路径。"
                ) from exc

            dims = int(model.get_sentence_embedding_dimension() or 0)
            if not dims:
                raise LocalEmbedderUnavailable(
                    f"无法确定模型「{self._model_name}」的输出维度"
                )
            if self._expected_dims and dims != self._expected_dims:
                raise LocalEmbedderUnavailable(
                    f"模型维度不匹配：模型「{self._model_name}」输出 {dims} 维，"
                    f"但配置里写的是 {self._expected_dims} 维。\n"
                    "维度不一致会让向量库里已有数据全部失效，请改配置后再试。"
                )
            self._model = model
            self._dims = dims
            logger.info("local embedding model ready: %s (%d dims)", self._model_name, dims)
            return model

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        """批量向量化。失败抛异常（由上层决定降级）。"""
        if not texts:
            return []
        model = self._ensure_model()
        with self._lock:
            vectors = model.encode(
                list(texts),
                batch_size=32,
                normalize_embeddings=True,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
        return [v.tolist() for v in vectors]


_instances: dict[str, LocalEmbedder] = {}
_instances_lock = threading.Lock()


def get_local_embedder(
    model_name: str, *, expected_dims: int | None = None
) -> LocalEmbedder:
    """按模型名取单例（同一模型只加载一次）。"""
    key = f"{model_name}:{expected_dims or ''}"
    with _instances_lock:
        inst = _instances.get(key)
        if inst is None:
            inst = LocalEmbedder(model_name, expected_dims=expected_dims)
            _instances[key] = inst
        return inst


def reset_local_embedders() -> None:
    """清空单例缓存（配置变更后调用）。"""
    with _instances_lock:
        _instances.clear()
