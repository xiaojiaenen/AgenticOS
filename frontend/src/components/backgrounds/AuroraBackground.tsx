import { useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/utils';

/**
 * AuroraBackground — 首页 / 登录 / 注册共用的极光雾背景。
 *
 * 设计约束（DESIGN）：
 *  - 低饱和 indigo 渐变雾，整体透明度 < 8%，速度极慢，无粒子 / 无视差；
 *  - `prefers-reduced-motion: reduce` 时只渲染单帧（完全静止）；
 *  - WebGL 不可用（getContext 失败 / 老设备）时降级为 CSS 静态径向渐变；
 *  - 仅允许在 Home / Login / Signup 三处使用，禁止 admin 与 chat 页面。
 */

const VERTEX_SHADER = /* glsl */ `
attribute vec2 uv;
attribute vec2 position;
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = vec4(position, 0.0, 1.0);
}
`;

const FRAGMENT_SHADER = /* glsl */ `
precision mediump float;
varying vec2 vUv;
uniform float uTime;

void main() {
  vec2 uv = vUv;
  // 极慢的时间因子（约 0.03x），保证"雾"的漂移几乎不可察觉
  float t = uTime * 0.03;

  // 两个缓慢漂移的柔和光团（低饱和 indigo 系）
  vec2 p1 = vec2(0.28 + 0.10 * sin(t), 0.72 + 0.08 * cos(t * 0.8));
  vec2 p2 = vec2(0.76 + 0.08 * cos(t * 0.7), 0.30 + 0.10 * sin(t * 0.9));

  float d1 = smoothstep(0.95, 0.0, distance(uv, p1));
  float d2 = smoothstep(0.85, 0.0, distance(uv, p2));

  // #4f46e5 (indigo-600) 与 #818cf8 (indigo-400)，去饱和处理
  vec3 indigo = vec3(0.33, 0.31, 0.78);
  vec3 soft = vec3(0.55, 0.52, 0.86);

  vec3 color = indigo * d1 * 0.55 + soft * d2 * 0.40;
  // 透明度硬上限 8%，满足"透明度 <8%"要求
  float alpha = min(d1 * 0.055 + d2 * 0.045, 0.08);

  gl_FragColor = vec4(color, alpha);
}
`;

/** WebGL 不可用时的 CSS 静态降级（纯径向渐变，无动画） */
function AuroraFallback({ className }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn('pointer-events-none inset-0 z-0', className)}
      style={{
        background:
          'radial-gradient(ellipse 60% 50% at 28% 25%, rgba(79, 70, 229, 0.06), transparent 70%),' +
          'radial-gradient(ellipse 50% 45% at 75% 70%, rgba(129, 140, 248, 0.05), transparent 70%)',
      }}
    />
  );
}

export function AuroraBackground({ className }: { className?: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [webglFailed, setWebglFailed] = useState(false);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let disposed = false;
    let rafId = 0;
    let resizeObserver: ResizeObserver | null = null;

    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    try {
      // WebGL 能力探测：getContext 失败（老设备 / 被禁用）直接走 CSS 降级
      const probe = document.createElement('canvas');
      const gl = probe.getContext('webgl') || probe.getContext('experimental-webgl');
      if (!gl) {
        setWebglFailed(true);
        return;
      }

      void (async () => {
        try {
          const { Renderer, Program, Mesh, Triangle } = await import('ogl');
          if (disposed || !containerRef.current) return;

          const renderer = new Renderer({
            alpha: true,
            antialias: false,
            depth: false,
            stencil: false,
            dpr: Math.min(window.devicePixelRatio || 1, 2),
          });
          const glCtx = renderer.gl;
          glCtx.clearColor(0, 0, 0, 0);

          const geometry = new Triangle(glCtx);
          const program = new Program(glCtx, {
            vertex: VERTEX_SHADER,
            fragment: FRAGMENT_SHADER,
            uniforms: {
              uTime: { value: reducedMotion ? 12 : 0 },
            },
          });
          const mesh = new Mesh(glCtx, { geometry, program });

          const resize = () => {
            const el = containerRef.current;
            if (!el) return;
            renderer.setSize(el.clientWidth, el.clientHeight);
          };
          resize();
          if (typeof ResizeObserver !== 'undefined') {
            resizeObserver = new ResizeObserver(resize);
            resizeObserver.observe(containerRef.current);
          }

          containerRef.current.appendChild(glCtx.canvas);
          glCtx.canvas.style.width = '100%';
          glCtx.canvas.style.height = '100%';
          glCtx.canvas.style.display = 'block';

          const startTime = performance.now();
          const renderFrame = () => {
            if (disposed) return;
            program.uniforms.uTime.value = (performance.now() - startTime) / 1000;
            renderer.render({ scene: mesh });
          };

          if (reducedMotion) {
            // 静态：只渲染一帧
            renderFrame();
          } else {
            const loop = () => {
              if (disposed) return;
              renderFrame();
              rafId = requestAnimationFrame(loop);
            };
            rafId = requestAnimationFrame(loop);
          }
        } catch {
          // ogl 初始化失败（编译错误 / 上下文丢失等）→ CSS 降级
          if (!disposed) setWebglFailed(true);
        }
      })();

      return () => {
        disposed = true;
        if (rafId) cancelAnimationFrame(rafId);
        resizeObserver?.disconnect();
        const canvas = container.querySelector('canvas');
        canvas?.remove();
      };
    } catch {
      setWebglFailed(true);
      return;
    }
  }, []);

  if (webglFailed) {
    return <AuroraFallback className={className} />;
  }

  return (
    <div
      ref={containerRef}
      aria-hidden="true"
      className={cn('pointer-events-none inset-0 z-0 overflow-hidden', className)}
    />
  );
}
