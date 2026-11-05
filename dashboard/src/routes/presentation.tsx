import { createFileRoute } from "@tanstack/react-router";
import { ArrowLeft, ArrowRight, Cpu, Globe, Laptop, Maximize, Printer } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import type { CSSProperties, ReactNode } from "react";

import { Halftone } from "@/components/halftone";
import { NotePaper } from "@/components/note-paper";

// Public on purpose, like /demo: it only shows the concept model and made-up example notes.
export const Route = createFileRoute("/presentation")({
  head: () => ({
    meta: [{ title: "Prins" }, { name: "theme-color", content: "#241b16" }],
  }),
  component: Presentation,
});

const INK = "#241b16";
const BROWN = "#704a34";
const SAND = "#ecd3ad";
const CREAM = "#fff3df";

const SLIDES = [
  { background: INK, color: CREAM, render: () => <Title /> },
  { background: BROWN, color: CREAM, render: () => <WhatItDoes /> },
  { background: INK, color: CREAM, render: () => <HowItsMade /> },
  { background: SAND, color: INK, render: () => <UseCases /> },
  { background: BROWN, color: CREAM, render: () => <Demo /> },
];

/** Where the model sits on each slide, or null when it's out of sight. */
const MODEL: (string | null)[] = [
  "translate(23vw, 2vh) scale(1.08)",
  null,
  null,
  null,
  "translate(0, 15vh) scale(0.82)",
];

function Presentation() {
  const [index, setIndex] = useState(0);
  const slide = SLIDES[index];
  const model = MODEL[index];

  const go = useCallback((by: number) => {
    setIndex((current) => Math.min(SLIDES.length - 1, Math.max(0, current + by)));
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (["ArrowRight", "ArrowDown", "PageDown", " ", "Enter"].includes(event.key)) {
        event.preventDefault();
        go(1);
      } else if (["ArrowLeft", "ArrowUp", "PageUp"].includes(event.key)) {
        event.preventDefault();
        go(-1);
      } else if (event.key.toLowerCase() === "f") {
        void toggleFullscreen();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go]);

  return (
    <main
      className="fixed inset-0 cursor-default overflow-hidden select-none"
      style={{
        background: slide.background,
        color: slide.color,
        transition: "background .7s ease, color .4s ease",
      }}
      onClick={(event) => go(event.clientX < window.innerWidth * 0.25 ? -1 : 1)}
    >
      <Halftone
        fade="hole"
        alwaysDark
        pitch={11}
        opacity={0.04}
        className="absolute inset-0 size-full text-[#fff3df]"
      />

      <iframe
        src="/demo/product-3d.html?stage=1"
        title="3D model of the Prins device. Concept design."
        tabIndex={-1}
        className="pointer-events-none absolute inset-0 size-full border-0"
        style={{
          opacity: model ? 1 : 0,
          transform: model ?? "translate(0, 12vh) scale(0.9)",
          transition: "opacity .6s ease, transform 1s cubic-bezier(.16,1,.3,1)",
        }}
      />

      <div key={index} className="absolute inset-0 flex flex-col p-[6vmin]">
        {slide.render()}
      </div>

      <nav
        className="absolute inset-x-0 bottom-[3vmin] flex items-center justify-center gap-2"
        aria-label="Slides"
        onClick={(event) => event.stopPropagation()}
      >
        <NavButton label="Previous slide" onClick={() => go(-1)}>
          <ArrowLeft className="size-4" aria-hidden />
        </NavButton>
        {SLIDES.map((_, dot) => (
          <button
            key={dot}
            type="button"
            aria-label={`Slide ${dot + 1}`}
            aria-current={dot === index ? "step" : undefined}
            onClick={() => setIndex(dot)}
            className="h-1.5 cursor-pointer rounded-full bg-current transition-all duration-500"
            style={{ width: dot === index ? 28 : 6, opacity: dot === index ? 1 : 0.35 }}
          />
        ))}
        <NavButton label="Next slide" onClick={() => go(1)}>
          <ArrowRight className="size-4" aria-hidden />
        </NavButton>
        <NavButton label="Full screen" onClick={() => void toggleFullscreen()}>
          <Maximize className="size-4" aria-hidden />
        </NavButton>
      </nav>
    </main>
  );
}

function toggleFullscreen() {
  return document.fullscreenElement
    ? document.exitFullscreen()
    : document.documentElement.requestFullscreen();
}

function NavButton({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      className="flex size-8 cursor-pointer items-center justify-center rounded-full opacity-50 transition-opacity hover:opacity-100"
    >
      {children}
    </button>
  );
}

const delay = (i: number) => ({ "--i": i }) as CSSProperties;

function Title() {
  return (
    <div className="relative flex flex-1 flex-col justify-center gap-[4vmin] md:max-w-[48vw]">
      <h1 className="rise-in font-dot text-[clamp(5rem,19vmin,16rem)]" style={{ color: SAND }}>
        Prins
      </h1>
      <p
        className="rise-in text-[clamp(1.4rem,4.2vmin,3.25rem)] leading-[1.1] font-medium tracking-[-0.03em] text-balance"
        style={delay(3)}
      >
        Your inbox and your voice, turned into sticky notes you approve with a button.
      </p>
      <p className="rise-in absolute bottom-[5vmin] left-0 text-sm opacity-60" style={delay(6)}>
        Concept design
      </p>
    </div>
  );
}

const MESSAGES = [
  ["Weekly newsletter", false],
  ["Build passed on main", false],
  ["Lunch is at noon", true],
  ["Calendar update", false],
  ["Thanks, got it!", false],
  ["Out of office", false],
] as const;

function WhatItDoes() {
  return (
    <div className="flex flex-1 flex-col justify-center gap-[5vmin]">
      <div className="grid items-center gap-[4vmin] md:grid-cols-[1fr_auto_1.15fr]">
        <ul className="flex flex-col gap-[1.2vmin] text-[clamp(1rem,2.6vmin,2rem)] font-medium tracking-[-0.02em]">
          {MESSAGES.map(([text, keep], i) => (
            <li
              key={text}
              className="rise-in"
              style={{
                ...delay(i * 2),
                opacity: keep ? 1 : 0.5,
                color: keep ? SAND : undefined,
              }}
            >
              {text}
            </li>
          ))}
        </ul>
        <ArrowRight
          className="rise-in hidden size-[8vmin] stroke-1 md:block"
          style={{ ...delay(12), color: SAND }}
          aria-hidden
        />
        <div className="flex flex-col gap-[2.5vmin]">
          <NotePaper
            className="note-feed w-full"
            item={{
              source: "slack",
              sender: "Maria",
              title: "Lunch is at noon",
              detail: "Maria booked the table.",
              priority: "normal",
              due: "",
              bitmap: null,
            }}
          />
        </div>
      </div>
      <p
        className="rise-in text-center text-[clamp(1.5rem,5vmin,4rem)] leading-none font-medium tracking-[-0.03em]"
        style={delay(14)}
      >
        AI finds what matters. <span style={{ color: SAND }}>You press print.</span>
      </p>
    </div>
  );
}

const PARTS = [
  { icon: Cpu, name: "Atech ESP32-S3", role: "Screen and three keys" },
  { icon: Laptop, name: "Mac", role: "Python and Claude" },
  { icon: Printer, name: "M110", role: "Label printer" },
];

function Wire({ label, vertical = false }: { label: string; vertical?: boolean }) {
  return (
    <span
      className={`rise-in flex items-center justify-center ${vertical ? "h-[9vmin] flex-col" : "flex-col md:min-w-[10vmin]"}`}
      style={delay(5)}
    >
      <span
        className={vertical ? "h-full w-0.5" : "h-0.5 w-full max-md:h-[5vmin] max-md:w-0.5"}
        style={{
          backgroundImage: `repeating-linear-gradient(${vertical ? "180deg" : "90deg"}, ${SAND} 0 8px, transparent 8px 16px)`,
          backgroundSize: vertical ? "100% 32px" : "32px 100%",
          animation: `${vertical ? "wire-y" : "wire-x"} 1s linear infinite`,
        }}
      />
      <span
        className={`font-mono text-[clamp(0.7rem,1.5vmin,1.1rem)] opacity-70 ${vertical ? "absolute ml-[14vmin]" : "mt-2"}`}
      >
        {label}
      </span>
    </span>
  );
}

function Node({ part, i }: { part: (typeof PARTS)[number] | typeof WEB; i: number }) {
  return (
    <div
      className="rise-in flex w-[34vmin] flex-col items-center gap-[1.5vmin] text-center max-md:w-[60vmin]"
      style={delay(i * 3)}
    >
      <span
        className="flex size-[clamp(4rem,19vmin,13rem)] items-center justify-center rounded-[28%]"
        style={{ background: BROWN }}
      >
        <part.icon className="size-[46%] stroke-[1.25]" style={{ color: SAND }} aria-hidden />
      </span>
      <span>
        <span className="block text-[clamp(1rem,3vmin,2.25rem)] leading-tight font-medium tracking-[-0.02em]">
          {part.name}
        </span>
        <span className="block text-[clamp(0.8rem,2vmin,1.5rem)] opacity-70">{part.role}</span>
      </span>
    </div>
  );
}

const WEB = { icon: Globe, name: "Dashboard", role: "Queue, history, friends" };

function HowItsMade() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center">
      <div className="flex items-start justify-center gap-[2vmin] max-md:flex-col max-md:items-center">
        <Node part={PARTS[0]} i={0} />
        <div className="md:mt-[9vmin]">
          <Wire label="USB" />
        </div>
        <Node part={PARTS[1]} i={1} />
        <div className="md:mt-[9vmin]">
          <Wire label="Bluetooth" />
        </div>
        <Node part={PARTS[2]} i={2} />
      </div>
      <div className="relative">
        <Wire label="Sync" vertical />
      </div>
      <Node part={WEB} i={3} />
    </div>
  );
}

// Real output from the design engine: see demo/presentation_notes.py.
const NOTES = [
  { file: "reply", alt: "Reply to Northwind before their board meets", tilt: -1.5 },
  { file: "merged", alt: "An agent reports that pull request 512 merged", tilt: 1 },
  { file: "gym", alt: "Gym at 6 tomorrow, before work", tilt: -1 },
  { file: "anniversary", alt: "A happy anniversary postcard", tilt: 1.5 },
  { file: "ticket", alt: "A concert ticket for Rockefeller on 14 March", tilt: -1 },
  { file: "moon", alt: "To the moon, with a rocket", tilt: 1 },
];

function UseCases() {
  return (
    <div className="flex flex-1 items-center justify-center pb-[5vmin]">
      <div className="grid w-[min(100%,calc((100svh-24vmin)*2.166+6vmin))] grid-cols-2 gap-[3vmin] md:grid-cols-3">
        {NOTES.map((note, i) => (
          <div
            key={note.file}
            className="note-shadow note-feed [container-type:inline-size]"
            style={{ rotate: `${note.tilt}deg`, animationDelay: `${i * 90}ms` }}
          >
            <img
              src={`/presentation/${note.file}.png`}
              alt={note.alt}
              width={312}
              height={216}
              draggable={false}
              className="note-tear block h-auto w-full bg-[#fffefb] [image-rendering:pixelated]"
            />
          </div>
        ))}
      </div>
    </div>
  );
}

function Demo() {
  return (
    <div className="relative flex flex-1 flex-col items-center pt-[4vmin] text-center">
      <p className="rise-in font-dot text-[clamp(3.5rem,14vmin,11rem)]" style={{ color: SAND }}>
        Let's see it
      </p>
      <p className="rise-in absolute right-0 bottom-[5vmin] text-sm opacity-70" style={delay(4)}>
        Concept design
      </p>
    </div>
  );
}
