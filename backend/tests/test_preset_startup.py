"""外部预设插件在启动路径上真的被加载（防止再次漏接）。

这个测试覆盖一个曾经真实发生的缺陷：`load_external_presets()` 实现了，
但只在测试里被调用，生产启动路径（FastAPI lifespan / ARQ worker on_startup）
从来没调过 —— 结果设置 `PROVIDER_PRESETS_DIR` 完全不生效。
"""
from __future__ import annotations

import pathlib
import textwrap

import pytest


def _write_plugin(directory: pathlib.Path, slug: str = "startup_probe") -> None:
    (directory / f"{slug}.py").write_text(
        textwrap.dedent(
            f'''
            from app.services.llm_providers.presets import ProviderPreset

            PROBE = ProviderPreset(
                slug="{slug}",
                label="启动探针预设",
                provider_type="openai_compatible",
                base_url="https://probe.test/v1",
                model="probe-model",
            )
            PRESETS = [PROBE]
            '''
        ).strip()
        + "\n",
        encoding="utf-8",
    )


def test_worker_startup_loads_external_presets(tmp_path, monkeypatch) -> None:
    """ARQ worker 的 on_startup 必须加载外部预设。

    PPT 导出等任务在 worker 进程里跑，那里没有 backend 的 lifespan；
    漏掉这一步会让 worker 拿不到预设里的 base_url / 模型名。
    """
    import asyncio

    from app.services.llm_providers import presets
    from app.services.task_queue import WorkerSettings

    _write_plugin(tmp_path)
    monkeypatch.setenv("PROVIDER_PRESETS_DIR", str(tmp_path))
    presets.PRESETS.pop("startup_probe", None)

    asyncio.run(WorkerSettings.on_startup({}))

    assert "startup_probe" in presets.PRESETS
    assert presets.PRESETS["startup_probe"].base_url == "https://probe.test/v1"


def test_fastapi_lifespan_loads_external_presets(tmp_path, monkeypatch) -> None:
    """backend 的 lifespan 也必须加载外部预设。"""
    import asyncio

    from app.main import lifespan
    from app.services.llm_providers import presets

    _write_plugin(tmp_path, slug="lifespan_probe")
    monkeypatch.setenv("PROVIDER_PRESETS_DIR", str(tmp_path))
    presets.PRESETS.pop("lifespan_probe", None)

    async def _run() -> None:
        async with lifespan(None):  # type: ignore[arg-type]
            # 启动阶段完成即可断言，不需要真的跑请求
            assert "lifespan_probe" in presets.PRESETS

    asyncio.run(_run())


def test_startup_survives_broken_plugin(tmp_path, monkeypatch) -> None:
    """坏插件不能让进程起不来 —— 只记 warning。"""
    import asyncio

    from app.services.llm_providers import presets
    from app.services.task_queue import WorkerSettings

    (tmp_path / "broken.py").write_text("raise RuntimeError('boom')\n", encoding="utf-8")
    monkeypatch.setenv("PROVIDER_PRESETS_DIR", str(tmp_path))

    # 不应抛异常
    asyncio.run(WorkerSettings.on_startup({}))
