import React, { useEffect, useRef, useState } from 'react';
import { Stage, Layer, Line } from 'react-konva';
import type Konva from 'konva';

export type MaskTool = 'brush' | 'eraser';

interface StrokeLine {
  tool: MaskTool;
  size: number;
  points: number[];
}

export interface InpaintMaskStageProps {
  width: number;
  height: number;
  tool: MaskTool;
  brushSize: number;
  clearSignal: number;
  undoSignal: number;
  onExportReady?: (exporter: () => string | null) => void;
}

/**
 * 基于 Konva (`react-konva`) 的局部精修涂抹蒙版层：
 * - 支持画笔涂抹与橡皮擦（destination-out）
 * - 支持按笔触撤销与一键清空
 * - 支持通过 Konva Stage.toDataURL() 导出透明 PNG 蒙版供后端局部重绘接口使用
 */
export const InpaintMaskStage: React.FC<InpaintMaskStageProps> = ({
  width,
  height,
  tool,
  brushSize,
  clearSignal,
  undoSignal,
  onExportReady,
}) => {
  const [lines, setLines] = useState<StrokeLine[]>([]);
  const isDrawingRef = useRef(false);
  const stageRef = useRef<Konva.Stage | null>(null);

  useEffect(() => {
    setLines([]);
  }, [clearSignal]);

  useEffect(() => {
    if (undoSignal > 0) {
      setLines((prev) => prev.slice(0, -1));
    }
  }, [undoSignal]);

  useEffect(() => {
    onExportReady?.(() => stageRef.current?.toDataURL({ pixelRatio: 1 }) ?? null);
  }, [onExportReady]);

  const handlePointerDown = (e: Konva.KonvaEventObject<MouseEvent | TouchEvent>) => {
    isDrawingRef.current = true;
    const pos = e.target.getStage()?.getPointerPosition();
    if (!pos) return;
    setLines((prev) => [...prev, { tool, size: brushSize, points: [pos.x, pos.y] }]);
  };

  const handlePointerMove = (e: Konva.KonvaEventObject<MouseEvent | TouchEvent>) => {
    if (!isDrawingRef.current) return;
    const pos = e.target.getStage()?.getPointerPosition();
    if (!pos) return;
    setLines((prev) => {
      if (prev.length === 0) return prev;
      const next = prev.slice();
      const last = next[next.length - 1];
      next[next.length - 1] = {
        ...last,
        points: last.points.concat([pos.x, pos.y]),
      };
      return next;
    });
  };

  const handlePointerUp = () => {
    isDrawingRef.current = false;
  };

  return (
    <div className="absolute inset-0 z-20 cursor-crosshair">
      <Stage
        ref={stageRef}
        width={Math.max(1, width)}
        height={Math.max(1, height)}
        onMouseDown={handlePointerDown}
        onMouseMove={handlePointerMove}
        onMouseUp={handlePointerUp}
        onMouseLeave={handlePointerUp}
        onTouchStart={handlePointerDown}
        onTouchMove={handlePointerMove}
        onTouchEnd={handlePointerUp}
      >
        <Layer>
          {lines.map((line, idx) => (
            <Line
              key={idx}
              points={line.points}
              stroke="#6366f1"
              opacity={0.55}
              strokeWidth={line.size}
              tension={0.45}
              lineCap="round"
              lineJoin="round"
              globalCompositeOperation={
                line.tool === 'eraser' ? 'destination-out' : 'source-over'
              }
            />
          ))}
        </Layer>
      </Stage>
    </div>
  );
};
