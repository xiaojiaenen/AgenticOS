"""
渲染引擎 - Chromium 录制 + ffmpeg 编码
完整对标 html-video 原版 HyperframesEngine
"""

import asyncio
import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional, Any

from .types import RenderConfig, RenderOutput
from .errors import HtmlVideoError, ErrorCode


ADAPTER_VERSION = "0.2.0-playwright-python"


class HyperframesEngine:
    """Chromium 录制 + ffmpeg 编码引擎"""

    async def render(
        self,
        html_path: str,
        config: RenderConfig,
        work_dir: str,
        on_progress: Optional[Callable] = None,
        signal: Optional[asyncio.Event] = None,
    ) -> RenderOutput:
        """
        完整渲染管线（10 步，与原版完全一致）：

        Step 1: 准备输出目录
        Step 2: Playwright 启动 Chromium headless
        Step 3: 注入动画冻结 CSS
        Step 4: 多帧合成处理（prepare_source_html）
        Step 5: 加载 HTML
        Step 6: 等待 Web Fonts
        Step 7: 探测动画时长
        Step 8: 驱动多帧合成
        Step 9: 解冻动画 + 录制
        Step 10: 关闭 + ffmpeg 编码
        """
        t0 = time.time()

        # Step 1: 准备输出目录
        if on_progress:
            on_progress(5, "preparing")
        out_dir = os.path.dirname(config.output_path)
        os.makedirs(out_dir, exist_ok=True)

        if not os.path.exists(html_path):
            raise HtmlVideoError(
                code=ErrorCode.TEMPLATE_INVALID,
                message=f"Source HTML not found: {html_path}",
            )

        # 计算总时长
        total_duration = (
            5.0 if config.duration == "auto" else max(0.5, float(config.duration))
        )
        width = config.resolution.get("width", 1920)
        height = config.resolution.get("height", 1080)
        fps = config.fps or 30

        # Step 2: Playwright 启动 Chromium
        if on_progress:
            on_progress(15, "launching browser")

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise HtmlVideoError(
                code=ErrorCode.ENGINE_NOT_INSTALLED,
                message="playwright not installed. Run: pip install playwright && playwright install chromium",
            )

        record_dir = tempfile.mkdtemp(prefix="hv-render-")
        browser = None
        webm_path = None
        cleanup_src = None
        lead_in_ms = 0

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
                )

                # recordVideo starts capturing the moment the context exists
                t_webm_start = int(time.time() * 1000)
                context = await browser.new_context(
                    viewport={"width": width, "height": height},
                    device_scale_factor=1,
                    record_video_dir=record_dir,
                    record_video_size={"width": width, "height": height},
                )
                page = await context.new_page()

                # Step 3: 注入动画冻结 CSS
                await page.add_init_script("""
                    (() => {
                        const style = document.createElement('style');
                        style.id = '__hv_freeze';
                        style.textContent = '*, *::before, *::after { animation-play-state: paused !important; -webkit-animation-play-state: paused !important; }';
                        const attach = () => (document.head || document.documentElement).appendChild(style);
                        if (document.head || document.documentElement) attach();
                        else document.addEventListener('DOMContentLoaded', attach, { once: true });
                        window.__hvUnfreeze = () => { document.getElementById('__hv_freeze')?.remove(); };
                    })();
                """)

                # Step 4: 多帧合成处理
                if on_progress:
                    on_progress(30, "loading frame")
                prepared = await self._prepare_source_html(html_path)
                cleanup_src = prepared.get("cleanup")
                load_path = prepared["load_path"]

                # Step 5: 加载 HTML
                file_url = f"file://{load_path}"
                await page.goto(file_url, wait_until="domcontentloaded")

                # Step 6: 等待 Web Fonts
                if on_progress:
                    on_progress(32, "loading fonts")
                await self._wait_for_fonts(page)

                # 等待动画启动
                await page.wait_for_timeout(100)

                # Step 7: 探测动画时长
                try:
                    anim_ms = await self._probe_animation_duration(page)
                    needed = min(30, (anim_ms + 400) / 1000)
                    if config.duration_mode != "explicit" and needed > total_duration:
                        if on_progress:
                            on_progress(38, f"extending to {needed:.1f}s for animation")
                        total_duration = needed
                except Exception:
                    pass  # 探测失败，使用请求的时长

                # Step 8: 驱动多帧合成
                await page.evaluate("""
                    () => {
                        if (typeof window.__hvPlayAll === 'function') {
                            window.__hvPlayed = true;
                            window.__hvPlayAll();
                        }
                    }
                """).catch(lambda: None)

                # Step 9: 解冻动画 + 录制
                await page.evaluate("() => { window.__hvUnfreeze?.(); }").catch(
                    lambda: None
                )
                lead_in_ms = int(time.time() * 1000) - t_webm_start

                if on_progress:
                    on_progress(40, f"recording {total_duration}s")

                # 录制指定时长
                total_ms = int(total_duration * 1000)
                tick = 250
                start = time.time() * 1000
                while (time.time() * 1000 - start) < total_ms:
                    if signal and signal.is_set():
                        raise HtmlVideoError(code=ErrorCode.CANCELLED, message="Aborted")
                    await asyncio.sleep(min(tick, total_ms - (time.time() * 1000 - start)) / 1000)
                    if on_progress:
                        pct = 40 + int(((time.time() * 1000 - start) / total_ms) * 45)
                        on_progress(pct, "recording")

                # Step 10: 关闭 context
                if on_progress:
                    on_progress(85, "finalising recording")
                await context.close()

                # 获取 webm 文件
                webm_files = [f for f in os.listdir(record_dir) if f.endswith(".webm")]
                if not webm_files:
                    raise HtmlVideoError(
                        code=ErrorCode.RENDER_FAILED,
                        message=f"Playwright produced no webm in {record_dir}",
                    )
                webm_files.sort()
                webm_path = os.path.join(record_dir, webm_files[-1])

        finally:
            if browser:
                await browser.close()
            if cleanup_src:
                await cleanup_src()

        # ---- ffmpeg: webm → mp4 ----
        if on_progress:
            on_progress(90, "encoding mp4")

        # 修剪死区开头
        seek_sec = max(0, (lead_in_ms - 120) / 1000) if lead_in_ms > 200 else 0
        explicit = config.duration_mode == "explicit"

        # 构建 ffmpeg 命令
        ffmpeg_args = ["-y"]
        if seek_sec > 0:
            ffmpeg_args.extend(["-ss", f"{seek_sec:.3f}"])
        ffmpeg_args.extend(["-i", webm_path])
        if explicit:
            ffmpeg_args.extend(
                ["-vf", f"tpad=stop_mode=clone:stop_duration={total_duration}"]
            )
        ffmpeg_args.extend(
            [
                "-t",
                str(total_duration),
                "-r",
                str(fps),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-preset",
                "medium",
                "-crf",
                "20",
                "-movflags",
                "+faststart",
                config.output_path,
            ]
        )

        await self._run_ffmpeg(ffmpeg_args)

        # 清理临时目录
        shutil.rmtree(record_dir, ignore_errors=True)

        # 获取输出文件信息
        file_size = os.path.getsize(config.output_path)
        if on_progress:
            on_progress(100, "done")

        wall_clock = time.time() - t0

        return RenderOutput(
            output_path=config.output_path,
            duration_sec=total_duration,
            file_size_bytes=file_size,
            resolution=config.resolution,
            fps=fps,
            rendered_frames=int(total_duration * fps),
            render_wall_clock_sec=wall_clock,
            engine_version=f"hyperframes-playwright@{ADAPTER_VERSION}",
        )

    async def _prepare_source_html(self, source_path: str) -> dict:
        """
        多帧合成 HTML 预处理（对标原版 prepareSourceHtml）：
        1. 读取源 HTML
        2. 检测 data-composition-src 属性
        3. 读取每个 composition 文件
        4. JSON 序列化为 window.__COMPOSITIONS__（转义 </）
        5. 注入 <head> script: __timelines + __COMPOSITIONS__
        6. 注入 composition player script（boot + mountOne + reexec + __hvPlayAll）
        7. 替换 __VIDEO_DURATION__ 和 __VIDEO_SRC__ 占位符
        8. 写入临时 .html 文件
        9. 返回 {load_path, cleanup_fn}
        """
        with open(source_path, "r", encoding="utf-8") as f:
            raw = f.read()

        # 检测 data-composition-src
        src_matches = re.findall(r'data-composition-src=["\']([^"\']+)["\']', raw)
        if not src_matches:
            return {"load_path": source_path}

        src_dir = os.path.dirname(source_path)
        comp_map: dict[str, str] = {}

        for rel in set(src_matches):
            comp_path = os.path.join(src_dir, rel)
            if os.path.exists(comp_path):
                with open(comp_path, "r", encoding="utf-8") as f:
                    comp_map[rel] = f.read()

        if not comp_map:
            return {"load_path": source_path}

        # 转义 </ 以安全嵌入 <script>
        safe_json = json.dumps(comp_map).replace("</", "<\\/").replace("<!--", "<\\!--")

        # 替换占位符
        out = raw.replace("__VIDEO_DURATION__", "15").replace(
            "__VIDEO_SRC__", "data:video/mp4;base64,"
        )

        # 注入 head script
        head_script = f"<script>window.__timelines=window.__timelines||{{}};window.__COMPOSITIONS__={safe_json};</script>"
        if re.search(r"<head[^>]*>", out, re.IGNORECASE):
            out = re.sub(
                r"<head[^>]*>",
                lambda m: f"{m.group(0)}\n{head_script}",
                out,
                count=1,
                flags=re.IGNORECASE,
            )
        else:
            out = f"{head_script}\n{out}"

        # 注入 composition player script
        player_script = """
<script>
(function () {
  function reexec(root) {
    root.querySelectorAll('script').forEach(function (old) {
      if (old.src) { old.parentNode.removeChild(old); return; }
      var s = document.createElement('script');
      s.textContent = '{\\n' + old.textContent + '\\n}';
      old.parentNode.replaceChild(s, old);
    });
  }
  function mountOne(host) {
    var src = host.getAttribute('data-composition-src');
    var text = (window.__COMPOSITIONS__ || {})[src];
    if (!text) return;
    var holder = document.createElement('div');
    holder.innerHTML = text;
    var tpl = holder.querySelector('template');
    host.appendChild(tpl ? tpl.content.cloneNode(true) : holder);
    reexec(host);
  }
  window.__hvPlayAll = function () {
    var tls = window.__timelines || {};
    Object.keys(tls).forEach(function (k) {
      var tl = tls[k];
      if (tl && typeof tl.play === 'function') tl.play(0);
    });
  };
  function boot() {
    window.__timelines = window.__timelines || {};
    Array.prototype.slice
      .call(document.querySelectorAll('[data-composition-src]'))
      .forEach(mountOne);
    setTimeout(function () { if (!window.__hvPlayed) window.__hvPlayAll(); }, 250);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else { boot(); }
})();
</script>"""

        if "</body>" in out:
            out = out.replace("</body>", f"{player_script}\n</body>")
        else:
            out += player_script

        # 写入临时文件
        load_path = os.path.join(src_dir, f".hv-render-{int(time.time() * 1000)}.html")
        with open(load_path, "w", encoding="utf-8") as f:
            f.write(out)

        async def cleanup():
            try:
                os.remove(load_path)
            except OSError:
                pass

        return {"load_path": load_path, "cleanup": cleanup}

    async def _wait_for_fonts(self, page) -> None:
        """
        等待 Web Fonts（对标原版 font wait 逻辑）：
        1. 等待所有 <link rel="stylesheet"> load/error
        2. fonts.forEach(face => face.load()) 强制下载
        3. await fonts.ready
        4. 2 rAF 确保布局稳定
        5. 8s 硬上限
        """
        await page.evaluate(
            """
            () => new Promise((resolve) => {
                const doc = document;
                const fonts = doc.fonts;
                if (!fonts || typeof fonts.ready?.then !== 'function') {
                    resolve();
                    return;
                }

                let settled = false;
                const finish = () => {
                    if (settled) return;
                    settled = true;
                    requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
                };
                const cap = setTimeout(finish, 8000);

                // 1. Wait for stylesheet <link>s to load
                const links = Array.from(
                    document.querySelectorAll('link[rel="stylesheet"]')
                );
                const linkDone = links.map((link) => {
                    try {
                        if (link.sheet && link.sheet.cssRules) return Promise.resolve();
                    } catch {}
                    return new Promise((r) => {
                        const done = () => r();
                        link.addEventListener('load', done, { once: true });
                        link.addEventListener('error', done, { once: true });
                        setTimeout(done, 6000);
                    });
                });

                Promise.all(linkDone)
                    .then(() => {
                        // 2. Force every registered face to download
                        const loads = [];
                        fonts.forEach((face) => {
                            try {
                                loads.push(face.load().catch(() => undefined));
                            } catch {}
                        });
                        return Promise.all(loads);
                    })
                    .then(() => fonts.ready)
                    .then(() => {
                        clearTimeout(cap);
                        finish();
                    })
                    .catch(() => {
                        clearTimeout(cap);
                        finish();
                    });
            })
        """
        ).catch(lambda: None)

    async def _probe_animation_duration(self, page) -> float:
        """
        探测动画时长（对标原版 animMs 探测）：
        CSS: 遍历所有元素 getComputedStyle，解析 animationDuration/animationDelay/animationIterationCount
        GSAP: globalTimeline.getChildren(true, true, true)，跳过 repeat()===-1
        返回 max(cssMs, gsapMs) / 1000 + 0.4，cap 30
        """
        anim_ms = await page.evaluate(
            """
            () => {
                let maxMs = 0;
                Array.from(document.querySelectorAll('*')).forEach((el) => {
                    const s = getComputedStyle(el);
                    const durs = (s.animationDuration || '').split(',');
                    const dels = (s.animationDelay || '').split(',');
                    const iters = (s.animationIterationCount || '').split(',');
                    durs.forEach((d, i) => {
                        if ((iters[i] || '').trim() === 'infinite') return;
                        maxMs = Math.max(maxMs, ((parseFloat(d) || 0) + (parseFloat(dels[i] || '0') || 0)) * 1000);
                    });
                });
                // GSAP: walk children, take longest finite tween
                const g = window.gsap;
                let gsapMs = 0;
                const children = g?.globalTimeline?.getChildren?.(true, true, true) ?? [];
                for (const c of children) {
                    const repeat = typeof c.repeat === 'function' ? c.repeat() : (c.vars?.repeat ?? 0);
                    if (repeat === -1) continue;
                    const td = typeof c.totalDuration === 'function' ? c.totalDuration() : 0;
                    if (Number.isFinite(td)) gsapMs = Math.max(gsapMs, td * 1000);
                }
                return Math.max(maxMs, gsapMs);
            }
        """
        )
        return anim_ms or 0

    async def _run_ffmpeg(self, args: list[str]) -> None:
        """
        执行 ffmpeg：
        - asyncio.create_subprocess_exec('ffmpeg', *args)
        - 收集 stderr
        - ENOENT → 友好提示 "brew install ffmpeg"
        - exit code != 0 → 抛出 HtmlVideoError('render-failed')
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg",
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()

            if proc.returncode != 0:
                stderr_text = stderr.decode("utf-8", errors="replace")[-2000:]
                raise HtmlVideoError(
                    code=ErrorCode.RENDER_FAILED,
                    message=f"ffmpeg exited {proc.returncode}: {stderr_text}",
                )
        except FileNotFoundError:
            raise HtmlVideoError(
                code=ErrorCode.ENGINE_NOT_INSTALLED,
                message="ffmpeg not found on PATH. Install with `brew install ffmpeg` (macOS) or `apt install ffmpeg` (Linux).",
            )

    async def concat_frames_ffmpeg(
        self,
        frame_mp4s: list[str],
        output_path: str,
        work_dir: str,
        reencode: bool = False,
        fps: int = 60,
    ) -> None:
        """
        多帧 MP4 合成（对标原版 concatFramesWithFfmpeg）：
        - 单引擎: concat demuxer + -c copy（快速，不重编码）
        - 混合引擎: concat filter + 重编码（避免 PTS 累积问题）
        """
        if not frame_mp4s:
            return

        if len(frame_mp4s) == 1:
            shutil.copy2(frame_mp4s[0], output_path)
            return

        if reencode:
            # 混合引擎：使用 concat filter 重编码
            inputs = []
            for mp4 in frame_mp4s:
                inputs.extend(["-i", mp4])

            # 构建 filter_complex
            n = len(frame_mp4s)
            filter_parts = []
            for i in range(n):
                filter_parts.append(f"[{i}:v:0]")
            filter_str = "".join(filter_parts) + f"concat=n={n}:v=1:a=0[outv]"

            args = [
                "-y",
                *inputs,
                "-filter_complex",
                filter_str,
                "-map",
                "[outv]",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-preset",
                "medium",
                "-crf",
                "20",
                "-movflags",
                "+faststart",
                output_path,
            ]
        else:
            # 单引擎：concat demuxer + -c copy
            concat_file = os.path.join(work_dir, "concat.txt")
            with open(concat_file, "w") as f:
                for mp4 in frame_mp4s:
                    f.write(f"file '{mp4}'\n")

            args = [
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                concat_file,
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                output_path,
            ]

        await self._run_ffmpeg(args)

    async def mux_audio_ffmpeg(
        self,
        video_path: str,
        output_path: str,
        music_path: Optional[str] = None,
        narration_path: Optional[str] = None,
        music_volume_db: float = -18,
        narration_volume_db: float = 0,
        fade_in_sec: float = 0,
        fade_out_sec: float = 0,
        video_duration_sec: Optional[float] = None,
    ) -> None:
        """
        音频混音（对标原版 muxAudioWithFfmpeg）：
        - 视频 stream copy（不重编码）
        - 音频编码 AAC 192k
        - music: volume + fade in/out
        - narration: volume
        - amix 混合
        - -shortest 对齐视频时长
        """
        if not music_path and not narration_path:
            return

        inputs = ["-i", video_path]
        filter_parts = []
        audio_inputs = []

        if music_path:
            inputs.extend(["-i", music_path])
            idx = len(audio_inputs) + 1
            audio_inputs.append(idx)
            vol_filter = f"[{idx}:a]volume={music_volume_db}dB"
            if fade_in_sec > 0:
                vol_filter += f",afade=t=in:st=0:d={fade_in_sec}"
            if fade_out_sec > 0 and video_duration_sec:
                vol_filter += f",afade=t=out:st={video_duration_sec - fade_out_sec}:d={fade_out_sec}"
            vol_filter += f"[music]"
            filter_parts.append(vol_filter)

        if narration_path:
            inputs.extend(["-i", narration_path])
            idx = len(audio_inputs) + 1
            audio_inputs.append(idx)
            filter_parts.append(f"[{idx}:a]volume={narration_volume_db}dB[narration]")

        if len(audio_inputs) > 1:
            # 混合多个音频
            mix_inputs = "[music][narration]" if music_path and narration_path else "[music]"
            filter_parts.append(f"{mix_inputs}amix=inputs={len(audio_inputs)}:duration=shortest[aout]")
            audio_map = "[aout]"
        elif music_path:
            audio_map = "[music]"
        else:
            audio_map = "[narration]"

        filter_str = ";".join(filter_parts)

        args = [
            "-y",
            *inputs,
            "-filter_complex",
            filter_str,
            "-map",
            "0:v",
            "-map",
            audio_map,
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            output_path,
        ]

        await self._run_ffmpeg(args)
