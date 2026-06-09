"""线程安全的单例工厂工具。

用法：
    _my_service = ThreadSafeSingleton(MyService)
    def get_my_service() -> MyService:
        return _my_service.get()
"""

from __future__ import annotations

import threading
from typing import Callable, Generic, TypeVar

T = TypeVar("T")


class ThreadSafeSingleton(Generic[T]):
    """Double-checked locking 单例，首次创建时加锁，后续调用零开销。"""

    def __init__(self, factory: Callable[[], T]) -> None:
        self._factory = factory
        self._instance: T | None = None
        self._lock = threading.Lock()

    def get(self) -> T:
        if self._instance is None:
            with self._lock:
                if self._instance is None:
                    self._instance = self._factory()
        return self._instance

    def reset(self) -> None:
        """测试用：重置实例"""
        with self._lock:
            self._instance = None
