import { useEffect, useRef } from "react";

import { NOTE_HEIGHT, NOTE_WIDTH } from "@/lib/schemas";

/** Draws a note exactly as it will print, pixel for pixel. */
export function NoteBitmap({
  bitmap,
  label,
  className = "",
}: {
  bitmap: string;
  label: string;
  className?: string;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const context = canvas.current?.getContext("2d");
    if (!context) return;
    const packed = Uint8Array.from(atob(bitmap), (char) => char.charCodeAt(0));
    const image = context.createImageData(NOTE_WIDTH, NOTE_HEIGHT);
    const rowBytes = Math.ceil(NOTE_WIDTH / 8);
    for (let y = 0; y < NOTE_HEIGHT; y++) {
      for (let x = 0; x < NOTE_WIDTH; x++) {
        const black = packed[y * rowBytes + (x >> 3)] & (0x80 >> (x & 7));
        const at = (y * NOTE_WIDTH + x) * 4;
        const value = black ? 17 : 255;
        image.data[at] = image.data[at + 1] = image.data[at + 2] = value;
        image.data[at + 3] = 255;
      }
    }
    context.putImageData(image, 0, 0);
  }, [bitmap]);

  return (
    <canvas
      ref={canvas}
      width={NOTE_WIDTH}
      height={NOTE_HEIGHT}
      role="img"
      aria-label={label}
      className={`block w-full [image-rendering:pixelated] ${className}`}
    />
  );
}
