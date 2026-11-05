// The light in the room: a faint glow from above over a slow grainy ember, drawn on its own
// canvas behind the model. Adapted from React Bits (LightRays and Grainient), MIT + Commons
// Clause, copyright (c) 2026 David Haz. It's part of this page, not a component to redistribute.

const PULSES = 3;

const VERTEX = `#version 300 es
const vec2 corners[3] = vec2[3](vec2(-1.0, -1.0), vec2(3.0, -1.0), vec2(-1.0, 3.0));
void main() { gl_Position = vec4(corners[gl_VertexID], 0.0, 1.0); }`;

const FRAGMENT = `#version 300 es
precision highp float;
uniform vec2 uRes;
uniform float uTime;
uniform float uFrame;
uniform vec2 uSource;
uniform vec2 uAim;
uniform float uReach;
uniform vec3 uRayColor;
uniform float uEnergy;
uniform float uCool;
uniform float uRed;
uniform float uReveal;
uniform vec3 uPulses[${PULSES}];
out vec4 fragColor;

float hash(vec2 p) {
  vec3 q = fract(vec3(p.xyx) * 0.1031);
  q += dot(q, q.yzx + 33.33);
  return fract((q.x + q.y) * q.z);
}
vec2 hash2(vec2 p) {
  vec3 q = fract(vec3(p.xyx) * vec3(0.1031, 0.103, 0.0973));
  q += dot(q, q.yzx + 33.33);
  return fract((q.xx + q.yz) * q.zy) * 2.0 - 1.0;
}
float noise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  vec2 u = f * f * f * (f * (f * 6.0 - 15.0) + 10.0);
  return 0.5 + 0.5 * mix(
    mix(dot(hash2(i), f), dot(hash2(i + vec2(1.0, 0.0)), f - vec2(1.0, 0.0)), u.x),
    mix(dot(hash2(i + vec2(0.0, 1.0)), f - vec2(0.0, 1.0)), dot(hash2(i + vec2(1.0, 1.0)), f - vec2(1.0, 1.0)), u.x),
    u.y);
}
vec2 drift(vec2 p, float t) {
  vec2 a = vec2(noise(p * 0.85 + vec2(t * 0.11, t * 0.07)), noise(p * 0.85 + vec2(4.1, 1.7) - vec2(t * 0.08, t * 0.12)));
  vec2 b = vec2(noise(p * 1.55 + a * 1.8 + vec2(1.3, 7.1) + t * 0.05), noise(p * 1.55 + a * 1.8 + vec2(6.4, 2.2) - t * 0.06));
  return (a - 0.5) * 1.1 + (b - 0.5) * 0.55;
}

vec3 ember(float s) {
  vec3 c = mix(vec3(0.018, 0.014, 0.013), vec3(0.070, 0.026, 0.014), smoothstep(0.0, 0.30, s));
  c = mix(c, vec3(0.300, 0.105, 0.030), smoothstep(0.25, 0.62, s));
  c = mix(c, vec3(0.760, 0.310, 0.065), smoothstep(0.58, 0.90, s));
  return mix(c, vec3(1.000, 0.640, 0.300), smoothstep(0.86, 1.05, s));
}

void main() {
  float aspect = uRes.x / uRes.y;

  // Ember: a warped pool of heat low in the frame, behind the device.
  vec2 p = (gl_FragCoord.xy / uRes - vec2(0.5, 0.30)) * vec2(aspect, 1.0);
  vec2 w = p + drift(p * 1.15 + vec2(3.2, 8.4), uTime * 0.55) * 0.34;
  float heat = clamp(1.0 - length(w * vec2(min(1.0, 1.25 / aspect) * 1.0, 1.7)) / 0.86, 0.0, 1.0);
  vec3 glow = ember(heat * (0.62 + 0.22 * uEnergy) * smoothstep(0.0, 1.0, uReveal));
  glow = mix(glow, glow.bgr * vec3(0.55, 0.85, 1.25), uCool);
  glow = mix(glow, glow * vec3(1.15, 0.28, 0.22), uRed);

  // Rays: fan out from above the frame.
  vec2 delta = vec2(gl_FragCoord.x, uRes.y - gl_FragCoord.y) - uSource;
  float dist = length(delta);
  vec2 dir = delta / max(dist, 1e-4);
  float cosAngle = dot(dir, uAim);
  float depth = dist / uReach;
  float source = exp(-depth * depth * 9.0) * 0.9 + exp(-depth * 3.2) * 0.25;
  float halo = 0.1 * source * smoothstep(0.2, 0.9, cosAngle);
  float spread = pow(max(cosAngle, 0.0), 1.0 / 0.085);
  float envelope = spread * clamp(1.0 - depth / 1.5, 0.0, 1.0);

  float a = 0.75 + 0.15 * sin(cosAngle * 36.2214 * 1.6 + uTime * 0.42) + 0.2 * cos(-cosAngle * 21.11349 * 1.6 + uTime * 0.42);
  float b = 0.75 + 0.15 * sin(cosAngle * 22.3991 * 1.6 + uTime * 0.31) + 0.2 * cos(-cosAngle * 18.0234 * 1.6 + uTime * 0.31);
  float rays = envelope * (0.5 * clamp(a, 0.0, 1.0) + 0.4 * clamp(b, 0.0, 1.0));

  float around = atan(uAim.x * dir.y - uAim.y * dir.x, cosAngle);
  vec2 q = vec2(around * 2.2 + uTime * 0.035, depth * 2.6 - uTime * 0.11);
  float fog = 0.65 * noise(q * vec2(3.0, 1.0)) + 0.35 * noise(q * vec2(7.0, 2.3) + 4.1);
  rays = pow(rays, 1.25) * (0.1 + 1.25 * fog * fog);

  float boost = 0.0;
  for (int i = 0; i < ${PULSES}; i++) {
    if (uPulses[i].z <= 0.0) continue;
    float x = (depth - uPulses[i].x) / uPulses[i].y;
    boost += uPulses[i].z * exp(-x * x);
  }

  float light = (rays * (0.2 * uEnergy + boost * 0.4) + halo * uEnergy) * smoothstep(uReveal * 2.0 - 0.4, uReveal * 2.0 - 1.1, depth - 0.9) * uReveal;
  float level = light < 0.75 ? light : 0.75 + 0.25 * (1.0 - exp(-(light - 0.75) / 0.25));
  vec3 color = glow + uRayColor * level;

  vec2 v = gl_FragCoord.xy / uRes - 0.5;
  color *= 1.0 - dot(v, v) * 1.1;

  // Film grain, strongest in the midtones, so the long gradients never band.
  vec2 px = gl_FragCoord.xy + uFrame * vec2(17.0, 59.0);
  float luma = dot(color, vec3(0.2126, 0.7152, 0.0722));
  color += (hash(px) + hash(px + 7.13) - 1.0) * (0.011 + 0.07 * luma * (1.0 - luma));
  fragColor = vec4(clamp(color, 0.0, 1.0), 1.0);
}`;

function program(gl) {
  const compile = (type, source) => {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    return shader;
  };
  const p = gl.createProgram();
  gl.attachShader(p, compile(gl.VERTEX_SHADER, VERTEX));
  gl.attachShader(p, compile(gl.FRAGMENT_SHADER, FRAGMENT));
  gl.linkProgram(p);
  return gl.getProgramParameter(p, gl.LINK_STATUS) ? p : null;
}

const WARM = [1.0, 0.86, 0.68];
const COOL = [0.62, 0.78, 1.0];
const RED = [1.0, 0.42, 0.32];

export function startAtmosphere(canvas, { lowPower, reduceMotion }) {
  const state = { energy: 1, cool: 0, red: 0 };
  const target = { energy: 1, cool: 0, red: 0 };
  const api = {
    level: () => state.energy,
    cool: () => state.cool,
    red: () => state.red,
    set: (next) => Object.assign(target, next),
    pulse: () => {},
  };
  const gl = canvas.getContext('webgl2', { alpha: false, antialias: false });
  const prog = gl && program(gl);
  if (!prog) return api;

  gl.useProgram(prog);
  gl.bindVertexArray(gl.createVertexArray());
  const u = (name) => gl.getUniformLocation(prog, name);
  const loc = {
    res: u('uRes'), time: u('uTime'), frame: u('uFrame'), source: u('uSource'), aim: u('uAim'), reach: u('uReach'),
    color: u('uRayColor'), energy: u('uEnergy'), cool: u('uCool'), red: u('uRed'), reveal: u('uReveal'), pulses: u('uPulses'),
  };

  let scale = 1;
  const resize = () => {
    const w = Math.max(1, Math.round(window.innerWidth * scale));
    const h = Math.max(1, Math.round(window.innerHeight * scale));
    if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; gl.viewport(0, 0, w, h); }
  };
  // One pixel per CSS pixel: the light is soft, and the grain looks better a little coarse.
  scale = Math.min(window.devicePixelRatio || 1, 1);
  resize();
  window.addEventListener('resize', resize);

  const pointer = { x: 0.5, y: 0.75, tx: 0.5, ty: 0.75 };
  window.addEventListener('pointermove', (e) => {
    if (e.pointerType !== 'mouse') return;
    pointer.tx = e.clientX / window.innerWidth;
    pointer.ty = e.clientY / window.innerHeight;
  }, { passive: true });

  const pulses = [];
  api.pulse = (amount = 1) => {
    if (reduceMotion) return;
    if (pulses.length >= PULSES) pulses.shift();
    pulses.push({ age: 0, amount });
  };

  const started = performance.now();
  let minStep = lowPower ? 1 / 31 : 1 / 61;
  const pulseData = new Float32Array(PULSES * 3);
  let last = started;
  let seconds = 0;
  let frameNo = 0;
  let slow = 0;

  function draw(now) {
    requestAnimationFrame(draw);
    const dt = (now - last) / 1000;
    if (dt < minStep) return;
    last = now;
    const step = Math.min(dt, 0.1);
    // Counted in steps, so a page still busy loading doesn't skip the fade-up.
    seconds += step;
    const ease = 1 - Math.exp(-step * 4.5);
    state.energy += (target.energy - state.energy) * ease;
    state.cool += (target.cool - state.cool) * ease;
    state.red += (target.red - state.red) * ease;
    pointer.x += (pointer.tx - pointer.x) * (1 - Math.exp(-step * 2.2));
    pointer.y += (pointer.ty - pointer.y) * (1 - Math.exp(-step * 2.2));

    // A machine that can't keep up gets a softer, slower background rather than a stuttering page.
    // The first seconds don't count: loading and the opening shot keep the page busy.
    if (seconds > 5) slow = dt > 0.05 ? slow + 1 : Math.max(0, slow - 1);
    if (slow > 8) {
      slow = 0;
      if (scale > 0.5) { scale = 0.5; resize(); } else minStep = 1 / 15;
    }

    const w = canvas.width, h = canvas.height;
    const reveal = reduceMotion ? 1 : Math.min(1, seconds / 2.2);
    const easedReveal = 1 - (1 - reveal) ** 3;
    const sourceX = w * (0.5 + (pointer.x - 0.5) * 0.08);
    const sourceY = -h * 0.2;
    const aimX = (pointer.x - 0.5) * w * 0.34;
    const aimY = h * 1.1;
    const aimLen = Math.hypot(aimX, aimY);

    pulseData.fill(0);
    for (let i = pulses.length - 1; i >= 0; i--) {
      pulses[i].age += step;
      if (pulses[i].age > 1.5) pulses.splice(i, 1);
    }
    pulses.forEach((p, i) => {
      const t = p.age / 1.5;
      pulseData[i * 3] = t * 1.5;
      pulseData[i * 3 + 1] = 0.18 + t * 0.34;
      pulseData[i * 3 + 2] = p.amount * 1.9 * (1 - t) ** 1.5;
    });

    const c = (i) => WARM[i] * (1 - state.cool) * (1 - state.red) + COOL[i] * state.cool + RED[i] * state.red * (1 - state.cool);
    gl.uniform2f(loc.res, w, h);
    gl.uniform1f(loc.time, reduceMotion ? 14 : seconds);
    gl.uniform1f(loc.frame, reduceMotion ? 1 : frameNo++ % 240);
    gl.uniform2f(loc.source, sourceX, sourceY);
    gl.uniform2f(loc.aim, aimX / aimLen, aimY / aimLen);
    gl.uniform1f(loc.reach, Math.max(h * 1.25, w * 0.62));
    gl.uniform3f(loc.color, c(0), c(1), c(2));
    gl.uniform1f(loc.energy, state.energy);
    gl.uniform1f(loc.cool, state.cool);
    gl.uniform1f(loc.red, state.red);
    gl.uniform1f(loc.reveal, easedReveal);
    gl.uniform3fv(loc.pulses, pulseData);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }
  requestAnimationFrame(draw);
  return api;
}
