"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

/** Two resizable panes with a draggable divider (pointer + keyboard accessible). */
export function Split({
  a, b, direction = "horizontal", initial = 0.45, min = 0.2, max = 0.8, storageKey,
}: {
  a: ReactNode; b: ReactNode; direction?: "horizontal" | "vertical"; initial?: number; min?: number; max?: number; storageKey?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [ratio, setRatio] = useState(initial);
  const dragging = useRef(false);
  const horizontal = direction === "horizontal";

  useEffect(() => {
    if (!storageKey) return;
    try {
      const v = Number(localStorage.getItem(storageKey));
      if (v >= min && v <= max) setRatio(v);
    } catch { /* storage unavailable */ }
  }, [storageKey, min, max]);

  const commit = useCallback((v: number) => {
    const clamped = Math.min(max, Math.max(min, v));
    setRatio(clamped);
    if (storageKey) try { localStorage.setItem(storageKey, String(clamped)); } catch { /* ignore */ }
  }, [min, max, storageKey]);

  useEffect(() => {
    const move = (e: PointerEvent) => {
      if (!dragging.current || !ref.current) return;
      const r = ref.current.getBoundingClientRect();
      commit(horizontal ? (e.clientX - r.left) / r.width : (e.clientY - r.top) / r.height);
    };
    const up = () => { dragging.current = false; document.body.style.cursor = ""; document.body.style.userSelect = ""; };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    return () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
  }, [commit, horizontal]);

  return (
    <div ref={ref} className={`flex min-h-0 min-w-0 flex-1 ${horizontal ? "flex-row" : "flex-col"}`}>
      <div style={{ flexBasis: `${ratio * 100}%` }} className="flex min-h-0 min-w-0 shrink-0 grow-0 flex-col overflow-hidden">{a}</div>
      <div
        role="separator"
        aria-orientation={horizontal ? "vertical" : "horizontal"}
        aria-valuenow={Math.round(ratio * 100)}
        tabIndex={0}
        onKeyDown={(e) => {
          const step = e.shiftKey ? 0.1 : 0.02;
          if (e.key === (horizontal ? "ArrowLeft" : "ArrowUp")) commit(ratio - step);
          if (e.key === (horizontal ? "ArrowRight" : "ArrowDown")) commit(ratio + step);
        }}
        onPointerDown={(e) => {
          e.preventDefault();
          dragging.current = true;
          document.body.style.cursor = horizontal ? "col-resize" : "row-resize";
          document.body.style.userSelect = "none";
        }}
        className={`group relative shrink-0 bg-line outline-none transition-colors hover:bg-accent/50 focus-visible:bg-accent ${horizontal ? "w-px cursor-col-resize" : "h-px cursor-row-resize"}`}
      >
        <span className={`absolute ${horizontal ? "inset-y-0 -left-1.5 -right-1.5" : "inset-x-0 -top-1.5 -bottom-1.5"}`} />
      </div>
      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">{b}</div>
    </div>
  );
}
