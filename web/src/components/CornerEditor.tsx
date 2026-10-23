import { useRef } from "react";
import type { Point, Quad } from "../api";

interface Props {
  src: string;
  width: number;
  height: number;
  quad: Quad | null;
  onChange: (quad: Quad) => void;
  /** Called once a drag ends. */
  onCommit?: (quad: Quad) => void;
}

const LABELS = ["왼쪽 위", "오른쪽 위", "오른쪽 아래", "왼쪽 아래"];

/** Photo with the detected receipt outline and four draggable corner handles (image-pixel coordinates). */
export default function CornerEditor({ src, width, height, quad, onChange, onCommit }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const latest = useRef<Quad | null>(quad);
  latest.current = quad;

  function toImage(e: React.PointerEvent): Point {
    const r = box.current!.getBoundingClientRect();
    const x = ((e.clientX - r.left) / r.width) * width;
    const y = ((e.clientY - r.top) / r.height) * height;
    return [Math.min(width, Math.max(0, x)), Math.min(height, Math.max(0, y))];
  }

  function move(i: number, e: React.PointerEvent) {
    if (!quad || !e.currentTarget.hasPointerCapture(e.pointerId)) return;
    const next = [...quad] as Quad;
    next[i] = toImage(e);
    onChange(next);
  }

  function end(e: React.PointerEvent) {
    if (!e.currentTarget.hasPointerCapture(e.pointerId)) return;
    e.currentTarget.releasePointerCapture(e.pointerId);
    if (latest.current) onCommit?.(latest.current);
  }

  return (
    <div className="corner-editor" ref={box}>
      <img src={src} alt="선택한 영수증 미리보기" draggable={false} />
      {quad && (
        <>
          <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden>
            <polygon points={quad.map((p) => p.join(",")).join(" ")} vectorEffect="non-scaling-stroke" />
          </svg>
          {quad.map(([x, y], i) => (
            <span
              key={i}
              className="corner-handle"
              role="slider"
              aria-label={`${LABELS[i]} 모서리`}
              aria-valuetext={`${Math.round(x)}, ${Math.round(y)}`}
              style={{ left: `${(x / width) * 100}%`, top: `${(y / height) * 100}%` }}
              onPointerDown={(e) => {
                e.preventDefault();
                e.currentTarget.setPointerCapture(e.pointerId);
              }}
              onPointerMove={(e) => move(i, e)}
              onPointerUp={end}
              onPointerCancel={end}
            />
          ))}
        </>
      )}
    </div>
  );
}
