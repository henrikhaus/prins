import { Eraser, Pencil, Trash2 } from "lucide-react";
import { useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import type { PointerEvent, Ref } from "react";

import { Button } from "@/components/ui/button";
import { NOTE_HEIGHT, NOTE_WIDTH } from "@/lib/schemas";

export type DrawPadHandle = {
  /** Base64 of the 312x216 grid, or null if nothing has been drawn. */
  bitmap: () => string | null;
};

const ROW_BYTES = Math.ceil(NOTE_WIDTH / 8);

/** A pixel canvas the size of a note. There's no anti-aliasing: every pixel is black or white. */
export function DrawPad({ ref }: { ref: Ref<DrawPadHandle> }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const pixels = useRef(new Uint8Array(NOTE_WIDTH * NOTE_HEIGHT));
  const last = useRef<{ x: number; y: number } | null>(null);
  const [erasing, setErasing] = useState(false);

  const paint = useCallback((x: number, y: number, on: boolean) => {
    const context = canvas.current?.getContext("2d");
    if (!context) return;
    const size = on ? 3 : 8;
    context.fillStyle = on ? "#111" : "#fff";
    const left = Math.round(x - size / 2);
    const top = Math.round(y - size / 2);
    context.fillRect(left, top, size, size);
    for (let py = Math.max(0, top); py < Math.min(NOTE_HEIGHT, top + size); py++) {
      for (let px = Math.max(0, left); px < Math.min(NOTE_WIDTH, left + size); px++) {
        pixels.current[py * NOTE_WIDTH + px] = on ? 1 : 0;
      }
    }
  }, []);

  const clear = useCallback(() => {
    const context = canvas.current?.getContext("2d");
    if (!context) return;
    context.fillStyle = "#fff";
    context.fillRect(0, 0, NOTE_WIDTH, NOTE_HEIGHT);
    pixels.current.fill(0);
  }, []);

  useEffect(clear, [clear]);

  useImperativeHandle(ref, () => ({
    bitmap: () => {
      if (!pixels.current.some(Boolean)) return null;
      const packed = new Uint8Array(ROW_BYTES * NOTE_HEIGHT);
      pixels.current.forEach((on, index) => {
        if (on) {
          const x = index % NOTE_WIDTH;
          const y = Math.floor(index / NOTE_WIDTH);
          packed[y * ROW_BYTES + (x >> 3)] |= 0x80 >> (x & 7);
        }
      });
      return btoa(String.fromCharCode(...packed));
    },
  }));

  const toGrid = (event: PointerEvent<HTMLCanvasElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    return {
      x: ((event.clientX - box.left) / box.width) * NOTE_WIDTH,
      y: ((event.clientY - box.top) / box.height) * NOTE_HEIGHT,
    };
  };

  const stroke = (event: PointerEvent<HTMLCanvasElement>) => {
    const point = toGrid(event);
    const from = last.current ?? point;
    const steps = Math.max(1, Math.ceil(Math.hypot(point.x - from.x, point.y - from.y)));
    for (let i = 0; i <= steps; i++) {
      paint(
        from.x + ((point.x - from.x) * i) / steps,
        from.y + ((point.y - from.y) * i) / steps,
        !erasing,
      );
    }
    last.current = point;
  };

  return (
    <div className="flex flex-col gap-2">
      <canvas
        ref={canvas}
        width={NOTE_WIDTH}
        height={NOTE_HEIGHT}
        aria-label="Drawing area, the size of a note"
        className="block w-full touch-none rounded-[3px] border bg-white [image-rendering:pixelated]"
        onPointerDown={(event) => {
          event.currentTarget.setPointerCapture(event.pointerId);
          last.current = null;
          stroke(event);
        }}
        onPointerMove={(event) => {
          if (event.buttons) stroke(event);
        }}
        onPointerUp={() => {
          last.current = null;
        }}
      />
      <div className="flex gap-1">
        <Button
          type="button"
          variant={erasing ? "ghost" : "secondary"}
          size="sm"
          onClick={() => setErasing(false)}
        >
          <Pencil aria-hidden />
          Draw
        </Button>
        <Button
          type="button"
          variant={erasing ? "secondary" : "ghost"}
          size="sm"
          onClick={() => setErasing(true)}
        >
          <Eraser aria-hidden />
          Erase
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={clear}>
          <Trash2 aria-hidden />
          Clear
        </Button>
      </div>
    </div>
  );
}
