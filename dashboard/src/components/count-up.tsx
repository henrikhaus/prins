import { useEffect, useRef, useState } from "react";

import { formatNumber } from "@/lib/format";

// Adapted from React Bits (CountUp), MIT + Commons Clause, copyright (c) 2026 David Haz.
// The first render is the real number, so it's right without JavaScript and for screen readers.
export function CountUp({ value, className = "" }: { value: number; className?: string }) {
  const [shown, setShown] = useState(value);
  const from = useRef(Math.round(value * 0.55));

  useEffect(() => {
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setShown(value);
      return;
    }
    const start = from.current;
    const began = performance.now();
    let frame = requestAnimationFrame(function step(now) {
      const t = Math.min(1, (now - began) / 900);
      const eased = 1 - (1 - t) ** 4;
      setShown(Math.round(start + (value - start) * eased));
      if (t < 1) frame = requestAnimationFrame(step);
      else from.current = value;
    });
    return () => cancelAnimationFrame(frame);
  }, [value]);

  return <span className={`tabular-nums ${className}`}>{formatNumber(shown)}</span>;
}
