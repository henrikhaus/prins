import { useEffect, useRef } from "react";

// A slow halftone wave: one bit per dot, like the printer. Adapted from React Bits (PatternWaves),
// MIT + Commons Clause, copyright (c) 2026 David Haz. Part of this site, not for redistribution.

const VERTEX = `#version 300 es
const vec2 corners[3] = vec2[3](vec2(-1.0, -1.0), vec2(3.0, -1.0), vec2(-1.0, 3.0));
void main() { gl_Position = vec4(corners[gl_VertexID], 0.0, 1.0); }`;

// One texel per dot, so all the expensive noise runs on a tiny texture.
const FIELD = `#version 300 es
precision highp float;
precision highp int;
uniform vec2 uCells;
uniform float uTime;
uniform vec3 uLight;
uniform vec2 uPointer;
uniform float uPointerOn;
uniform float uInk;
out vec4 fragColor;

uvec3 scramble(uvec3 v) {
  v = v * 1664525u + 1013904223u;
  v.x += v.y * v.z; v.y += v.z * v.x; v.z += v.x * v.y;
  v ^= v >> 16u;
  v.x += v.y * v.z; v.y += v.z * v.x; v.z += v.x * v.y;
  return v;
}
vec3 lattice(vec3 c) { return vec3(scramble(uvec3(ivec3(c) + 4096)) & 65535u) / 32767.5 - 1.0; }
float noise(vec3 p) {
  vec3 i = floor(p), f = p - i;
  vec3 u = f * f * f * (f * (f * 6.0 - 15.0) + 10.0);
  return mix(
    mix(mix(dot(lattice(i), f), dot(lattice(i + vec3(1, 0, 0)), f - vec3(1, 0, 0)), u.x),
        mix(dot(lattice(i + vec3(0, 1, 0)), f - vec3(0, 1, 0)), dot(lattice(i + vec3(1, 1, 0)), f - vec3(1, 1, 0)), u.x), u.y),
    mix(mix(dot(lattice(i + vec3(0, 0, 1)), f - vec3(0, 0, 1)), dot(lattice(i + vec3(1, 0, 1)), f - vec3(1, 0, 1)), u.x),
        mix(dot(lattice(i + vec3(0, 1, 1)), f - vec3(0, 1, 1)), dot(lattice(i + vec3(1, 1, 1)), f - vec3(1, 1, 1)), u.x), u.y),
    u.z);
}
float surface(vec2 p, float t) {
  vec2 heading = vec2(0.72, 0.69);
  vec2 side = vec2(-heading.y, heading.x);
  float u = dot(p, heading), v = dot(p, side);
  float bend = noise(vec3(v * 0.85, u * 0.3, t * 0.05)) * 1.7 + 0.4 * sin(v * 1.6 + t * 0.2);
  float phase = u * 5.5 + bend - t * 0.45;
  float swell = 0.6 + 0.4 * noise(vec3(u * 0.55 + 3.0, v * 0.45, t * 0.04));
  float h = (sin(phase) + 0.32 * sin(2.0 * phase + 1.3)) * swell;
  vec2 d = p - uPointer;
  return h + uPointerOn * 1.1 * exp(-dot(d, d) * 26.0);
}
void main() {
  float unit = min(uCells.x, uCells.y);
  vec2 p = (gl_FragCoord.xy - 0.5 * uCells) / unit;
  float e = 1.0 / unit;
  float h = surface(p, uTime);
  vec2 g = vec2(surface(p + vec2(e, 0.0), uTime) - surface(p - vec2(e, 0.0), uTime),
                surface(p + vec2(0.0, e), uTime) - surface(p - vec2(0.0, e), uTime)) / (2.0 * e);
  vec3 n = normalize(vec3(-g * 0.11, 1.0));
  float diffuse = clamp(dot(n, uLight), 0.0, 1.0);
  float spec = pow(clamp(dot(n, normalize(uLight + vec3(0, 0, 1))), 0.0, 1.0), 120.0);
  float hollow = 0.7 + 0.3 * clamp(h * 0.5 + 0.5, 0.0, 1.0);
  float tone = clamp(diffuse * hollow * 0.78 + spec, 0.0, 1.0);
  tone = clamp((tone - 0.42) * 2.4 + 0.42, 0.0, 1.0);
  float level = uInk > 0.5 ? pow(clamp(1.0 - tone / 0.5, 0.0, 1.0), 1.6) : pow(tone, 2.0);
  fragColor = vec4(level, 0.0, 0.0, 1.0);
}`;

const DOTS = `#version 300 es
precision highp float;
uniform sampler2D uField;
uniform vec2 uSize;
uniform float uPitch;
uniform vec3 uColor;
uniform float uOpacity;
uniform int uFade;
uniform float uAppear;
out vec4 fragColor;
void main() {
  vec2 cell = floor(gl_FragCoord.xy / uPitch);
  vec2 local = (fract(gl_FragCoord.xy / uPitch) - 0.5) * uPitch;
  float level = texelFetch(uField, ivec2(cell), 0).r;
  vec2 uv = gl_FragCoord.xy / uSize;
  vec2 c = uv * 2.0 - 1.0;
  float fade = 1.0;
  if (uFade == 1) fade = 1.0 - smoothstep(0.35, 1.05, length(c));
  if (uFade == 2) fade = smoothstep(0.25, 0.95, length(c * vec2(1.0, 1.2)));
  if (uFade == 3) fade = smoothstep(0.0, 0.45, uv.y) * smoothstep(0.0, 0.3, 1.0 - uv.y);
  if (uFade == 4) fade = smoothstep(0.42, 0.95, uv.y);
  float appear = smoothstep(0.0, 0.35, uAppear * 1.4 - uv.y * 0.9 - 0.05);
  float radius = 0.5 * uPitch * 0.94 * sqrt(clamp(level * fade * appear, 0.0, 1.0));
  float dot = 1.0 - smoothstep(radius - 0.75, radius + 0.75, length(local));
  float a = radius < 0.3 ? 0.0 : dot * uOpacity;
  fragColor = vec4(uColor * a, a);
}`;

function program(gl: WebGL2RenderingContext, fragment: string) {
  const make = (type: number, source: string) => {
    const shader = gl.createShader(type);
    if (!shader) return null;
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    return shader;
  };
  const vs = make(gl.VERTEX_SHADER, VERTEX);
  const fs = make(gl.FRAGMENT_SHADER, fragment);
  const linked = gl.createProgram();
  if (!vs || !fs || !linked) return null;
  gl.attachShader(linked, vs);
  gl.attachShader(linked, fs);
  gl.linkProgram(linked);
  return gl.getProgramParameter(linked, gl.LINK_STATUS) ? linked : null;
}

const FADES = { edges: 1, hole: 2, band: 3, top: 4, none: 0 } as const;

/** Browsers report CSS colours in several formats, so let a 2D canvas turn it into plain RGB. */
function inkFrom(element: Element) {
  const context = document.createElement("canvas").getContext("2d");
  if (!context) return [0.04, 0.04, 0.04];
  context.fillStyle = getComputedStyle(element).color;
  context.fillRect(0, 0, 1, 1);
  const { data } = context.getImageData(0, 0, 1, 1);
  return [data[0] / 255, data[1] / 255, data[2] / 255];
}

/**
 * Takes its dot colour from CSS `color` and adapts to the theme. The page is complete without it:
 * no WebGL2 means no decoration, nothing else changes.
 */
export function Halftone({
  className = "",
  pitch = 9,
  opacity = 1,
  darkOpacity = opacity,
  fade = "edges",
  interactive = false,
  alwaysDark = false,
}: {
  className?: string;
  pitch?: number;
  opacity?: number;
  darkOpacity?: number;
  fade?: keyof typeof FADES;
  interactive?: boolean;
  alwaysDark?: boolean;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const gl = canvas.getContext("webgl2", {
      alpha: true,
      antialias: false,
      premultipliedAlpha: true,
    });
    if (!gl) return;
    const field = program(gl, FIELD);
    const dots = program(gl, DOTS);
    if (!field || !dots) return;

    gl.bindVertexArray(gl.createVertexArray());
    const texture = gl.createTexture();
    const framebuffer = gl.createFramebuffer();
    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const uf = (name: string) => gl.getUniformLocation(field, name);
    const ud = (name: string) => gl.getUniformLocation(dots, name);
    const uniforms = {
      cells: uf("uCells"),
      time: uf("uTime"),
      light: uf("uLight"),
      pointer: uf("uPointer"),
      pointerOn: uf("uPointerOn"),
      ink: uf("uInk"),
      field: ud("uField"),
      size: ud("uSize"),
      pitch: ud("uPitch"),
      color: ud("uColor"),
      opacity: ud("uOpacity"),
      fade: ud("uFade"),
      appear: ud("uAppear"),
    };

    // On a panel that's always dark, the wave lights up instead of inking in.
    const forceDark = canvas.dataset.dark === "true";
    let ink = inkFrom(canvas);
    let cols = 1;
    let rows = 1;
    let devicePitch = pitch;
    const resize = () => {
      const box = canvas.getBoundingClientRect();
      const ratio = Math.min(devicePixelRatio || 1, 2);
      canvas.width = Math.max(1, Math.round(box.width * ratio));
      canvas.height = Math.max(1, Math.round(box.height * ratio));
      devicePitch = pitch * ratio;
      cols = Math.ceil(canvas.width / devicePitch) + 1;
      rows = Math.ceil(canvas.height / devicePitch) + 1;
      gl.bindTexture(gl.TEXTURE_2D, texture);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, cols, rows, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
      gl.bindFramebuffer(gl.FRAMEBUFFER, framebuffer);
      gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, texture, 0);
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    };

    const pointer = { x: 0, y: 0, tx: 0, ty: 0, on: 0, target: 0 };
    const onMove = (event: PointerEvent) => {
      if (event.pointerType !== "mouse") return;
      const box = canvas.getBoundingClientRect();
      const unit = Math.min(box.width, box.height);
      pointer.tx = (event.clientX - box.left - box.width / 2) / unit;
      pointer.ty = (box.height / 2 - (event.clientY - box.top)) / unit;
      pointer.target = 1;
    };
    if (interactive) window.addEventListener("pointermove", onMove, { passive: true });

    const started = performance.now();
    let last = 0;
    let frame = 0;
    let visible = true;

    const draw = (now: number) => {
      const seconds = (now - started) / 1000;
      const dark = document.documentElement.classList.contains("dark") || forceDark;
      const color = ink;
      pointer.x += (pointer.tx - pointer.x) * 0.1;
      pointer.y += (pointer.ty - pointer.y) * 0.1;
      pointer.on += (pointer.target - pointer.on) * 0.06;

      gl.bindFramebuffer(gl.FRAMEBUFFER, framebuffer);
      gl.viewport(0, 0, cols, rows);
      gl.useProgram(field);
      gl.uniform2f(uniforms.cells, cols, rows);
      gl.uniform1f(uniforms.time, reduced ? 9 : seconds * 0.8 + 20);
      gl.uniform3f(uniforms.light, -0.42, 0.56, 0.71);
      gl.uniform2f(uniforms.pointer, pointer.x, pointer.y);
      gl.uniform1f(uniforms.pointerOn, pointer.on);
      gl.uniform1f(uniforms.ink, dark ? 0 : 1);
      gl.drawArrays(gl.TRIANGLES, 0, 3);

      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.useProgram(dots);
      gl.bindTexture(gl.TEXTURE_2D, texture);
      gl.uniform1i(uniforms.field, 0);
      gl.uniform2f(uniforms.size, canvas.width, canvas.height);
      gl.uniform1f(uniforms.pitch, devicePitch);
      gl.uniform3f(uniforms.color, color[0], color[1], color[2]);
      gl.uniform1f(uniforms.opacity, dark ? darkOpacity : opacity);
      gl.uniform1i(uniforms.fade, FADES[fade]);
      gl.uniform1f(uniforms.appear, reduced ? 1 : Math.min(1, seconds / 1.6));
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    };

    const loop = (now: number) => {
      frame = requestAnimationFrame(loop);
      if (!visible || document.hidden || now - last < 33) return;
      last = now;
      draw(now);
    };

    resize();
    const sizes = new ResizeObserver(() => {
      resize();
      if (reduced) draw(performance.now());
    });
    sizes.observe(canvas);
    const seen = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
    });
    seen.observe(canvas);
    const theme = new MutationObserver(() => {
      ink = inkFrom(canvas);
      if (reduced) draw(performance.now());
    });
    theme.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    if (reduced) draw(performance.now());
    else frame = requestAnimationFrame(loop);

    return () => {
      cancelAnimationFrame(frame);
      sizes.disconnect();
      seen.disconnect();
      theme.disconnect();
      window.removeEventListener("pointermove", onMove);
      gl.getExtension("WEBGL_lose_context")?.loseContext();
    };
  }, [pitch, opacity, darkOpacity, fade, interactive]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden
      data-dark={alwaysDark}
      className={`pointer-events-none block ${className}`}
    />
  );
}
