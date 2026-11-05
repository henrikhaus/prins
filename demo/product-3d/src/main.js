// Prins concept model. All dimensions are millimetres; the GLB export wraps
// the model in a 0.001 scale so viewers see it at true size.
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFExporter } from 'three/addons/exporters/GLTFExporter.js';
import { Reflector } from 'three/addons/objects/Reflector.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { startAtmosphere } from './atmosphere.js';

const FONT = 'Archivo, "Helvetica Neue", Helvetica, Arial, sans-serif';

/* ------------------------------------------------------------------ */
/* Design parameters                                                   */
/* ------------------------------------------------------------------ */
const W = 94;         // body width
const R = 8;          // side edge softness
const BASE = 3;       // body floats this far above the desk on its foot
const PLATE = { w: 58, h: 47, r: 4.5 };
const ACTIVE = { w: 49, h: 36.75, up: 2.9 };  // 320x240 panel, shifted up to leave a chin
const KEY = { w: 21.8, h: 19, r: 6.5, gap: 3.4, proud: 4.6, travel: 2.6 };
const NOTE = { w: 58, h: 56, tilt: THREE.MathUtils.degToRad(15) };
const ROLL = { z: -13.5, y: 55, r: 13.2 };

const PALETTE = {
  body: 0xe6e2d8,
  band: 0x26262a,
  bandMetal: 0,
  bandRough: 0.42,
  metal: 0xdcd6c8,
  rubber: 0x1b1a1a,
  interior: 0x0b0a0a,
  glass: 0x040405,
  blue: '#2457d6',
  green: '#11985a',
  red: '#e2402a',
  shadow: new THREE.Color(0.012, 0.008, 0.006),
};

const ACCENT = {
  SLACK: 'rgb(190,130,255)',
  EMAIL: 'rgb(90,170,255)',
  VOICE: 'rgb(255,170,60)',
  AGENT: 'rgb(80,220,140)',
};

const SEED_CARDS = [
  { src: 'SLACK', from: 'Maria', task: 'Send Fennick the revised freight quote', detail: 'They want it before Friday’s call.' },
  { src: 'EMAIL', from: 'Tomas', task: 'Approve the Alder & Rowe invoice', detail: 'Second reminder, due this week.' },
  { src: 'AGENT', from: 'Inbox', task: 'Renew the Pinegate Studio contract', detail: 'Terms unchanged, needs your sign-off.' },
  { src: 'SLACK', from: 'Jonas', task: 'Book the Thursday design review', detail: 'Priya and Sam are free after lunch.' },
  { src: 'EMAIL', from: 'Aisha', task: 'Answer Marlow Kettle about delivery', detail: 'They asked for a date on the spring order.' },
];
const FIRST_NOTE = { src: 'EMAIL', from: 'Elena', task: 'Call Halvorsen Tile back today', detail: 'She has a question about the sample order.' };
const VOICE_CARDS = [
  { src: 'VOICE', from: 'You', task: 'Call Sam about the Pinegate kickoff', detail: 'Dictated just now.' },
  { src: 'VOICE', from: 'You', task: 'Order name badges for the offsite', detail: 'Dictated just now.' },
  { src: 'VOICE', from: 'You', task: 'Move Monday’s check-in to the morning', detail: 'Dictated just now.' },
];

/* ------------------------------------------------------------------ */
/* Small geometry toolkit                                              */
/* ------------------------------------------------------------------ */
const v2 = (x, y) => new THREE.Vector2(x, y);
const lerp2 = (a, b, t) => a.clone().lerp(b, t);

// Quintic corner: three collinear control points each end give zero curvature
// where it meets a straight, so highlights flow through (curvature continuity).
function quinticCorner(S, C, E, n) {
  const P = [S, lerp2(S, C, 0.34), lerp2(S, C, 0.68), lerp2(E, C, 0.68), lerp2(E, C, 0.34), E];
  const B = (t) => {
    const u = 1 - t;
    return [u ** 5, 5 * t * u ** 4, 10 * t * t * u ** 3, 10 * t ** 3 * u * u, 5 * t ** 4 * u, t ** 5];
  };
  const out = [];
  for (let i = 0; i <= n; i++) {
    const t = i / n;
    const b = B(t);
    const p = v2(0, 0);
    P.forEach((c, j) => p.addScaledVector(c, b[j]));
    // derivative
    const u = 1 - t;
    const d = [u ** 4, 4 * t * u ** 3, 6 * t * t * u * u, 4 * t ** 3 * u, t ** 4];
    const tan = v2(0, 0);
    for (let j = 0; j < 5; j++) tan.addScaledVector(P[j + 1].clone().sub(P[j]), d[j]);
    if (tan.lengthSq() < 1e-9) tan.copy(E).sub(S);
    out.push({ p, t: tan.normalize() });
  }
  return out;
}

// Closed 2D loop from sharp vertices and per-corner tangent lengths.
function roundedLoop(verts, cornerN = 12) {
  const n = verts.length;
  const out = [];
  for (let i = 0; i < n; i++) {
    const prev = verts[(i + n - 1) % n], cur = verts[i], next = verts[(i + 1) % n];
    const C = v2(cur[0], cur[1]);
    const dIn = C.clone().sub(v2(prev[0], prev[1])).normalize();
    const dOut = v2(next[0], next[1]).sub(C).normalize();
    const S = C.clone().addScaledVector(dIn, -cur[2]);
    const E = C.clone().addScaledVector(dOut, cur[2]);
    quinticCorner(S, C, E, cornerN).forEach((s) => out.push({ ...s, corner: i }));
  }
  return out;
}

function squircle(w, h, r, cornerN = 10) {
  const x = w / 2, y = h / 2;
  // tangent length ~1.1r keeps the visual radius about r for the quintic corner
  const L = Math.min(r * 1.1, x, y);
  const pts = roundedLoop([[-x, -y, L], [x, -y, L], [x, y, L], [-x, y, L]], cornerN).map((s) => s.p);
  return cleanLoop(pts);
}
function pill(w, h, cornerN = 12) { return squircle(w, h, h / 2 / 1.1, cornerN); }
function circleLoop(r, n = 72) {
  const out = [];
  for (let i = 0; i < n; i++) out.push(v2(Math.cos((i / n) * Math.PI * 2) * r, Math.sin((i / n) * Math.PI * 2) * r));
  return out;
}
function cleanLoop(pts) {
  const out = [];
  pts.forEach((p) => { if (!out.length || out[out.length - 1].distanceTo(p) > 1e-4) out.push(p); });
  if (out[0].distanceTo(out[out.length - 1]) < 1e-4) out.pop();
  if (THREE.ShapeUtils.isClockWise(out)) out.reverse();
  return out;
}
function loopNormals(loop) {
  const n = loop.length;
  return loop.map((p, i) => {
    const d = loop[(i + 1) % n].clone().sub(loop[(i + n - 1) % n]).normalize();
    return v2(d.y, -d.x); // outward for CCW
  });
}
function offsetLoop(loop, d) {
  const nrm = loopNormals(loop);
  return loop.map((p, i) => p.clone().addScaledVector(nrm[i], d));
}

class MeshData {
  constructor() { this.p = []; this.n = []; this.uv = []; this.c = []; this.i = []; }
  vert(x, y, z, nx, ny, nz, u = 0, v = 0, c = 1) {
    this.p.push(x, y, z); this.n.push(nx, ny, nz); this.uv.push(u, v); this.c.push(c, c, c);
    return this.p.length / 3 - 1;
  }
  tri(a, b, c) { this.i.push(a, b, c); }
  quad(a, b, c, d) { this.i.push(a, b, c, a, c, d); }
  build() {
    // Wind every triangle to agree with its authored normals.
    for (let t = 0; t < this.i.length; t += 3) {
      const [a, b, c] = [this.i[t], this.i[t + 1], this.i[t + 2]];
      const A = new THREE.Vector3().fromArray(this.p, a * 3);
      const B = new THREE.Vector3().fromArray(this.p, b * 3);
      const C = new THREE.Vector3().fromArray(this.p, c * 3);
      const fn = B.sub(A).cross(C.sub(A));
      const nn = new THREE.Vector3().fromArray(this.n, a * 3)
        .add(new THREE.Vector3().fromArray(this.n, b * 3))
        .add(new THREE.Vector3().fromArray(this.n, c * 3));
      if (fn.dot(nn) < 0) { this.i[t + 1] = c; this.i[t + 2] = b; }
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(this.p, 3));
    g.setAttribute('normal', new THREE.Float32BufferAttribute(this.n, 3));
    g.setAttribute('uv', new THREE.Float32BufferAttribute(this.uv, 2));
    g.setAttribute('color', new THREE.Float32BufferAttribute(this.c, 3));
    g.setIndex(this.i);
    return g;
  }
}

// Flat face with holes, in local XY at z = h.
function flatFace(md, outer, holes, h, nz = 1, uvScale = 1 / 100) {
  const tris = THREE.ShapeUtils.triangulateShape(outer, holes);
  const all = [...outer, ...holes.flat()];
  const idx = all.map((p) => md.vert(p.x, p.y, h, 0, 0, nz, p.x * uvScale, p.y * uvScale));
  tris.forEach((t) => md.tri(idx[t[0]], idx[t[1]], idx[t[2]]));
}

// Ring strip helper: rings = [{loop, z, n2d, nz}] all same vertex count.
function ringStrip(md, rings) {
  const m = rings[0].loop.length;
  const ids = rings.map((r) => r.loop.map((p, i) => md.vert(
    p.x, p.y, r.z,
    r.nr[i].x, r.nr[i].y, r.nz,
    p.x / 100, p.y / 100, r.c ?? 1,
  )));
  for (let k = 0; k < rings.length - 1; k++) {
    for (let i = 0; i < m; i++) {
      const j = (i + 1) % m;
      md.quad(ids[k][i], ids[k][j], ids[k + 1][j], ids[k + 1][i]);
    }
  }
}

// Rounded-edge plate with optional holes; z from 0 to h.
function plateGeometry(outer, holes = [], h = 1, bevel = 0.3, steps = 5) {
  const md = new MeshData();
  const nO = loopNormals(outer);
  const rings = [{ loop: outer, z: 0, nr: nO, nz: 0 }];
  for (let k = 0; k <= steps; k++) {
    const a = (k / steps) * Math.PI / 2;
    const c = Math.cos(a), s = Math.sin(a);
    rings.push({
      loop: offsetLoop(outer, -bevel * (1 - c)),
      z: h - bevel + bevel * s,
      nr: nO.map((d) => d.clone().multiplyScalar(c)), nz: s,
    });
  }
  ringStrip(md, rings);
  const inner = holes.map((hole) => {
    const nH = loopNormals(hole);
    const hr = [];
    for (let k = steps; k >= 0; k--) {
      const a = (k / steps) * Math.PI / 2;
      const c = Math.cos(a), s = Math.sin(a);
      hr.push({
        loop: offsetLoop(hole, bevel * (1 - c)),
        z: h - bevel + bevel * s,
        nr: nH.map((d) => d.clone().multiplyScalar(-c)), nz: s,
      });
    }
    hr.push({ loop: hole, z: 0, nr: nH.map((d) => d.clone().multiplyScalar(-1)), nz: 0 });
    ringStrip(md, hr);
    return offsetLoop(hole, bevel);
  });
  flatFace(md, offsetLoop(outer, -bevel), inner, h);
  return md.build();
}

// Well sunk into a surface: soft moulded lip, wall fading dark, floor optional.
function wellGeometry(hole, depth, lip = 0.45, floor = true) {
  const md = new MeshData();
  const nH = loopNormals(hole);
  const rings = [];
  const steps = 4;
  for (let k = 0; k <= steps; k++) {
    const a = (k / steps) * Math.PI / 2;
    rings.push({
      loop: offsetLoop(hole, -lip * Math.sin(a)),
      z: -lip * (1 - Math.cos(a)),
      nr: nH.map((d) => d.clone().multiplyScalar(-Math.sin(a))), nz: Math.cos(a),
      c: 1,
    });
  }
  const wall = offsetLoop(hole, -lip);
  const nWall = nH.map((d) => d.clone().multiplyScalar(-1));
  rings.push({ loop: wall, z: -lip - 0.6, nr: nWall, nz: 0, c: 0.55 });
  rings.push({ loop: wall, z: -depth * 0.45, nr: nWall, nz: 0, c: 0.12 });
  rings.push({ loop: wall, z: -depth, nr: nWall, nz: 0, c: 0.04 });
  ringStrip(md, rings);
  if (floor) {
    const tris = THREE.ShapeUtils.triangulateShape(wall, []);
    const ids = wall.map((p) => md.vert(p.x, p.y, -depth, 0, 0, 1, 0, 0, 0.03));
    tris.forEach((t) => md.tri(ids[t[0]], ids[t[1]], ids[t[2]]));
  }
  return md.build();
}

// Sculpted keycap: drafted skirt, soft shoulder, dished top. Planar UVs carry the legend.
function keycapGeometry(w, h, r, proud, skirt = 6, dish = 1.2, shoulder = 1.9) {
  const md = new MeshData();
  const base = squircle(w, h, r, 16);
  const m = base.length;
  const draft = 0.5;
  const ax = w / 2 - draft - shoulder, ay = h / 2 - draft - shoulder;
  // One smooth saucer over the whole top, so no creases follow the mesh rings.
  const sag = (x, y) => {
    const qx = Math.min(1, Math.abs(x / ax)), qy = Math.min(1, Math.abs(y / ay));
    return dish * (1 - qx * qx) * (1 - qy * qy);
  };
  const rings = [];
  rings.push({ loop: offsetLoop(base, 0), z: -skirt, top: false });
  rings.push({ loop: offsetLoop(base, -draft * 0.45), z: 0.2, top: false });
  const steps = 10;
  for (let k = 0; k <= steps; k++) {
    const a = (k / steps) * Math.PI / 2;
    rings.push({ loop: offsetLoop(base, -(draft + shoulder * (1 - Math.cos(a)))), z: proud - shoulder + shoulder * Math.sin(a), top: k === steps });
  }
  const edge = offsetLoop(base, -(draft + shoulder));
  const topSteps = 22;
  for (let k = 1; k <= topSteps; k++) {
    const q = 1 - k / topSteps;
    rings.push({ loop: edge.map((p) => p.clone().multiplyScalar(Math.max(q, 0.002))), z: proud, top: true });
  }
  const ids = rings.map((ring) => ring.loop.map((p) => {
    const z = ring.top ? ring.z - sag(p.x, p.y) : ring.z;
    return md.vert(p.x, p.y, z, 0, 0, 1, p.x / w + 0.5, p.y / h + 0.5);
  }));
  for (let k = 0; k < rings.length - 1; k++) {
    for (let i = 0; i < m; i++) {
      const j = (i + 1) % m;
      md.i.push(ids[k][i], ids[k][j], ids[k + 1][j], ids[k][i], ids[k + 1][j], ids[k + 1][i]);
    }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(md.p, 3));
  g.setAttribute('uv', new THREE.Float32BufferAttribute(md.uv, 2));
  g.setIndex(md.i);
  g.computeVertexNormals();
  // Replace ring-biased normals on the top with the exact surface normal.
  const nrm = g.attributes.normal, pos = g.attributes.position;
  const e = 0.01;
  const shoulderTop = 2 + steps;
  for (let k = shoulderTop + 1; k < rings.length; k++) {
    rings[k].loop.forEach((p, i) => {
      const id = ids[k][i];
      const dx = (sag(p.x + e, p.y) - sag(p.x - e, p.y)) / (2 * e);
      const dy = (sag(p.x, p.y + e) - sag(p.x, p.y - e)) / (2 * e);
      const n = new THREE.Vector3(dx, dy, 1).normalize();
      nrm.setXYZ(id, n.x, n.y, n.z);
    });
  }
  return g;
}

/* ------------------------------------------------------------------ */
/* The body                                                            */
/* ------------------------------------------------------------------ */
// Side profile in (z, y), clockwise: rear, top, screen face, key shelf, nose, underside.
const YT = BASE + 92;
const ZJ = 21;      // junction of screen face and key shelf
const YJ = BASE + 31;
const ZT = ZJ - (YT - YJ) * Math.tan(NOTE.tilt);
const PROFILE = [
  [-36, BASE, 12.5],        // rear bottom
  [-38, YT, 17],            // rear top: big soft shoulder holding the roll
  [ZT, YT, 10.5],           // top front
  [ZJ, YJ, 4],              // face/shelf junction (concave)
  [55, BASE + 22, 10.5],    // shelf front
  [52, BASE, 11.5],         // nose bottom
];
const SEG_NAMES = ['rear', 'top', 'face', 'shelf', 'front', 'bottom'];

function buildProfileRows() {
  const raw = roundedLoop(PROFILE, 22);
  const rows = raw.map((s) => ({
    z: s.p.x, y: s.p.y,
    tz: s.t.x, ty: s.t.y,
    nz: -s.t.y, ny: s.t.x,   // outward for clockwise traversal
    corner: s.corner,
  }));
  let arc = 0;
  rows.forEach((r, i) => {
    if (i) arc += Math.hypot(r.z - rows[i - 1].z, r.y - rows[i - 1].y);
    r.s = arc;
  });
  return rows;
}

const GROOVE = { gap: 0.55, edge: 0.22, depth: 1.5 };

// The body is two soft cheeks clamping one continuous band that runs right round the profile.
function buildBody() {
  const rows = buildProfileRows();
  const N = rows.length;
  const Nb = 12;
  const bev = quinticCorner(v2(0, R), v2(0, 0), v2(R, 0), Nb).map(({ p, t }) => ({
    a: p.x, b: p.y, ws: -t.y, wp: t.x,
  }));
  bev[0].a = 0; bev[0].b = R; bev[0].ws = 1; bev[0].wp = 0;
  bev[Nb].a = R; bev[Nb].b = 0; bev[Nb].ws = 0; bev[Nb].wp = 1;

  const hw = W / 2 - R;
  const hwBand = hw - GROOVE.gap - GROOVE.edge;
  const cheeks = new MeshData();
  const band = new MeshData();
  const groove = new MeshData();

  const cheekIds = { [-1]: [], [1]: [] };
  const bandIds = [];
  const grooveIds = [];
  rows.forEach((r) => {
    const at = (b) => [r.y - r.ny * b, r.z - r.nz * b];
    [-1, 1].forEach((sgn) => {
      const line = [];
      bev.forEach((b) => {
        const [y, z] = at(b.b);
        line.push(cheeks.vert(sgn * (W / 2 - b.a), y, z, sgn * b.ws, r.ny * b.wp, r.nz * b.wp, (W / 2 - b.a) / 100, r.s / 100));
      });
      // Soft edge rolling into the groove, then the groove wall fading dark.
      const e = 0.2;
      let [y, z] = at(e * 0.3);
      const k = Math.SQRT1_2;
      line.push(cheeks.vert(sgn * (hw - e * 0.3), y, z, -sgn * k, r.ny * k, r.nz * k, hw / 100, r.s / 100));
      [y, z] = at(e);
      line.push(cheeks.vert(sgn * (hw - e), y, z, -sgn, 0, 0, hw / 100, r.s / 100, 0.75));
      [y, z] = at(GROOVE.depth);
      line.push(cheeks.vert(sgn * (hw - e), y, z, -sgn, 0, 0, hw / 100, r.s / 100, 0.04));
      cheekIds[sgn].push(line);
    });
    // Band: top surface with its own small rolled edges and walls.
    const bl = [];
    const e = GROOVE.edge;
    const k = Math.SQRT1_2;
    let [y, z] = at(GROOVE.depth);
    bl.push(band.vert(-(hwBand + e), y, z, -1, 0, 0, 0, r.s / 100, 0.05));
    [y, z] = at(e);
    bl.push(band.vert(-(hwBand + e), y, z, -1, 0, 0, 0, r.s / 100, 0.8));
    [y, z] = at(e * 0.3);
    bl.push(band.vert(-(hwBand + e * 0.7), y, z, -k, r.ny * k, r.nz * k, 0, r.s / 100));
    [y, z] = at(0);
    bl.push(band.vert(-hwBand, y, z, 0, r.ny, r.nz, -hwBand / 100, r.s / 100));
    bl.push(band.vert(hwBand, y, z, 0, r.ny, r.nz, hwBand / 100, r.s / 100));
    [y, z] = at(e * 0.3);
    bl.push(band.vert(hwBand + e * 0.7, y, z, k, r.ny * k, r.nz * k, 0, r.s / 100));
    [y, z] = at(e);
    bl.push(band.vert(hwBand + e, y, z, 1, 0, 0, 0, r.s / 100, 0.8));
    [y, z] = at(GROOVE.depth);
    bl.push(band.vert(hwBand + e, y, z, 1, 0, 0, 0, r.s / 100, 0.05));
    bandIds.push(bl);
    // Groove floor
    [y, z] = at(GROOVE.depth);
    grooveIds.push([groove.vert(-hw, y, z, 0, r.ny, r.nz), groove.vert(hw, y, z, 0, r.ny, r.nz)]);
  });

  const frames = {};
  const patchSegs = new Set(['top', 'face', 'shelf']);
  for (let i = 0; i < N; i++) {
    const j = (i + 1) % N;
    const a = rows[i], b = rows[j];
    const straight = a.corner !== b.corner;
    const seg = straight ? SEG_NAMES[a.corner] : null;
    const isPatch = straight && patchSegs.has(seg);
    [-1, 1].forEach((sgn) => {
      const A = cheekIds[sgn][i], B = cheekIds[sgn][j];
      for (let c = 0; c < A.length - 1; c++) cheeks.quad(A[c], A[c + 1], B[c + 1], B[c]);
    });
    const A = bandIds[i], Bb = bandIds[j];
    for (let c = 0; c < A.length - 1; c++) {
      if (c === 3 && isPatch) continue;
      band.quad(A[c], A[c + 1], Bb[c + 1], Bb[c]);
    }
    groove.quad(grooveIds[i][0], grooveIds[i][1], grooveIds[j][1], grooveIds[j][0]);
    if (straight) {
      const u = new THREE.Vector3(1, 0, 0);
      const tan = new THREE.Vector3(0, b.y - a.y, b.z - a.z);
      const len = tan.length();
      const vv = tan.clone().normalize().negate();
      const nn = u.clone().cross(vv);
      const o = new THREE.Vector3(0, (a.y + b.y) / 2, (a.z + b.z) / 2);
      const m = new THREE.Matrix4().makeBasis(u, vv, nn).setPosition(o);
      frames[seg] = { o, u, v: vv, n: nn, len, m };
    }
  }

  // Side caps: flat, one with the roll window cut out.
  const capLoop = cleanLoop(rows.map((r) => v2(r.z - r.nz * R, r.y - r.ny * R)));
  const win = circleLoop(ROLL.r + 0.8, 72).map((p) => v2(p.x + ROLL.z, p.y + ROLL.y));
  [[-1, []], [1, [win]]].forEach(([sgn, holes]) => {
    const tris = THREE.ShapeUtils.triangulateShape(capLoop, holes);
    const all = [...capLoop, ...holes.flat()];
    const ids = all.map((p) => cheeks.vert(sgn * W / 2, p.y, p.x, sgn, 0, 0, p.x / 100, p.y / 100));
    tris.forEach((t) => cheeks.tri(ids[t[0]], ids[t[1]], ids[t[2]]));
  });

  return { cheeks, band, groove, frames, rows, hwBand };
}

function patchInto(md, frame, holes, hw) {
  const hl = frame.len / 2;
  const outer = cleanLoop([v2(-hw, -hl), v2(hw, -hl), v2(hw, hl), v2(-hw, hl)]);
  const tris = THREE.ShapeUtils.triangulateShape(outer, holes);
  const all = [...outer, ...holes.flat()];
  const ids = all.map((p) => {
    const w = frame.o.clone().addScaledVector(frame.u, p.x).addScaledVector(frame.v, p.y);
    return md.vert(w.x, w.y, w.z, frame.n.x, frame.n.y, frame.n.z, p.x / 100, p.y / 100);
  });
  tris.forEach((t) => md.tri(ids[t[0]], ids[t[1]], ids[t[2]]));
}

/* ------------------------------------------------------------------ */
/* Canvas art                                                          */
/* ------------------------------------------------------------------ */
function canvasOf(w, h) { const c = document.createElement('canvas'); c.width = w; c.height = h; return c; }
function roundRectPath(ctx, x, y, w, h, r) { ctx.beginPath(); ctx.roundRect(x, y, w, h, r); }

function wrapLines(ctx, text, maxW) {
  const words = text.split(' ');
  const lines = [];
  let line = '';
  words.forEach((w) => {
    const t = line ? `${line} ${w}` : w;
    if (ctx.measureText(t).width > maxW && line) { lines.push(line); line = w; } else line = t;
  });
  if (line) lines.push(line);
  return lines;
}
function fitted(ctx, text, maxW) {
  if (ctx.measureText(text).width <= maxW) return text;
  let t = text;
  while (t.length > 1 && ctx.measureText(`${t}…`).width > maxW) t = t.slice(0, -1);
  return `${t}…`;
}

class Screen {
  constructor(scale) {
    this.S = scale;
    this.canvas = canvasOf(320 * scale, 240 * scale);
    this.ctx = this.canvas.getContext('2d');
    this.tex = new THREE.CanvasTexture(this.canvas);
    this.tex.colorSpace = THREE.SRGBColorSpace;
    this.tex.anisotropy = 16;
    this.tex.name = 'screen';
  }
  begin() {
    const { ctx, S } = this;
    ctx.setTransform(S, 0, 0, S, 0, 0);
    ctx.globalAlpha = 1;
    ctx.fillStyle = '#0a0a0c';
    ctx.fillRect(0, 0, 320, 240);
  }
  end() { this.tex.needsUpdate = true; }

  card(card, n, slide = 0, alpha = 1) {
    const { ctx } = this;
    ctx.save();
    ctx.translate(slide, 0);
    ctx.globalAlpha = alpha;
    const accent = ACCENT[card.src];
    ctx.fillStyle = accent;
    ctx.fillRect(0, 0, 320, 42);
    ctx.fillStyle = '#0a0a0c';
    ctx.textBaseline = 'middle';
    ctx.textAlign = 'left';
    ctx.font = `700 21px ${FONT}`;
    const label = `${card.src} - ${card.from}`;
    ctx.fillText(fitted(ctx, label, 244), 12, 22);
    const txt = String(n);
    ctx.font = `800 18px ${FONT}`;
    const bw = Math.max(32, ctx.measureText(txt).width + 18);
    ctx.fillStyle = '#0a0a0c';
    roundRectPath(ctx, 320 - bw - 8, 7, bw, 28, 14);
    ctx.fill();
    ctx.fillStyle = '#ffffff';
    ctx.textAlign = 'center';
    ctx.fillText(txt, 320 - bw / 2 - 8, 22);

    // Task, large and bold, shrinks only if it would need more than three lines.
    ctx.textAlign = 'left';
    ctx.textBaseline = 'alphabetic';
    let size = 35, lines;
    do {
      ctx.font = `800 ${size}px ${FONT}`;
      lines = wrapLines(ctx, card.task, 298);
      if (lines.length <= 3) break;
      size -= 2;
    } while (size > 22);
    const lh = size * 1.06;
    ctx.fillStyle = '#ffffff';
    const top = 56 + size * 0.86;
    lines.forEach((l, i) => ctx.fillText(l, 11, top + i * lh));

    ctx.font = `500 15.5px ${FONT}`;
    ctx.fillStyle = '#b4b4bc';
    ctx.fillText(fitted(ctx, card.detail, 298), 12, 190);

    ctx.fillStyle = 'rgba(255,255,255,0.14)';
    ctx.fillRect(0, 205, 320, 1);
    ctx.textBaseline = 'middle';
    ctx.font = `700 15px ${FONT}`;
    let x = 12;
    const seg = (t, c) => { ctx.fillStyle = c; ctx.fillText(t, x, 223); x += ctx.measureText(t).width; };
    seg('Green', '#50dc8c'); seg(': print', '#d8d8de');
    x += 28;
    seg('Red', '#ff6a5a'); seg(': dismiss', '#d8d8de');
    ctx.restore();
  }

  listening(levels) {
    const { ctx } = this;
    ctx.fillStyle = 'rgb(255,90,90)';
    ctx.fillRect(0, 0, 320, 240);
    ctx.fillStyle = '#0a0a0c';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'alphabetic';
    ctx.font = `800 44px ${FONT}`;
    ctx.fillText('Listening', 160, 96);
    const n = levels.length, bw = 12, gap = 8;
    const total = n * bw + (n - 1) * gap;
    levels.forEach((l, i) => {
      const h = 8 + l * 70;
      roundRectPath(ctx, 160 - total / 2 + i * (bw + gap), 164 - h / 2, bw, h, 6);
      ctx.fill();
    });
  }

  printing(p, time) {
    const { ctx } = this;
    ctx.fillStyle = 'rgb(80,220,140)';
    ctx.fillRect(0, 0, 320, 240);
    ctx.fillStyle = '#0a0a0c';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'alphabetic';
    ctx.font = `800 44px ${FONT}`;
    ctx.fillText('Printing', 160, 112);
    roundRectPath(ctx, 60, 142, 200, 12, 6);
    ctx.fillStyle = 'rgba(10,10,12,0.22)';
    ctx.fill();
    roundRectPath(ctx, 60, 142, Math.max(12, 200 * p), 12, 6);
    ctx.fillStyle = '#0a0a0c';
    ctx.fill();
  }

  thinking(time) {
    const { ctx } = this;
    ctx.fillStyle = '#0a0a0c';
    ctx.fillRect(0, 0, 320, 240);
    ctx.fillStyle = '#ffffff';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'alphabetic';
    ctx.font = `800 40px ${FONT}`;
    ctx.fillText('Thinking', 160, 112);
    for (let i = 0; i < 3; i++) {
      const a = 0.25 + 0.75 * Math.max(0, Math.sin(time * 6 - i * 0.9));
      ctx.globalAlpha = a;
      ctx.fillStyle = ACCENT.VOICE;
      ctx.beginPath();
      ctx.arc(160 + (i - 1) * 26, 148, 7.5, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  empty() {
    const { ctx } = this;
    ctx.fillStyle = '#ffffff';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'alphabetic';
    ctx.font = `800 42px ${FONT}`;
    ctx.fillText('All clear', 160, 112);
    ctx.font = `500 16px ${FONT}`;
    ctx.fillStyle = '#b4b4bc';
    ctx.fillText('Hold blue to add a note', 160, 144);
  }
}

// Sticky note artwork. Bottom edge is the torn serration.
const NOTE_PX = { w: 696, h: Math.round(696 * NOTE.h / NOTE.w) };
function drawNote(ctx, card) {
  const { w, h } = NOTE_PX;
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, w, h);
  ctx.beginPath();
  ctx.moveTo(0, 0); ctx.lineTo(w, 0); ctx.lineTo(w, h - 16);
  const teeth = 40, tw = w / teeth;
  for (let i = teeth; i > 0; i--) {
    ctx.lineTo((i - 0.5) * tw, h - 1);
    ctx.lineTo((i - 1) * tw, h - 16);
  }
  ctx.closePath();
  ctx.fillStyle = '#ffffff';
  ctx.fill();
  ctx.save();
  ctx.clip();
  const m = 50;
  ctx.fillStyle = '#111111';
  ctx.textAlign = 'left';
  ctx.textBaseline = 'alphabetic';
  ctx.font = `700 38px ${FONT}`;
  ctx.fillText(`${card.src} - ${card.from}`, m, 88);
  ctx.fillRect(m, 110, w - m * 2, 5);
  let size = 76, lines;
  do {
    ctx.font = `800 ${size}px ${FONT}`;
    lines = wrapLines(ctx, card.task, w - m * 2);
    if (lines.length <= 4) break;
    size -= 4;
  } while (size > 44);
  const lh = size * 1.08;
  lines.forEach((l, i) => ctx.fillText(l, m, 118 + size * 0.98 + i * lh));
  const y = 118 + size * 0.98 + lines.length * lh;
  ctx.font = `500 38px ${FONT}`;
  wrapLines(ctx, card.detail, w - m * 2).slice(0, 2).forEach((l, i) => ctx.fillText(l, m, y + 10 + i * 46));
  ctx.restore();
}
function drawNoteBack(ctx) {
  const { w, h } = NOTE_PX;
  ctx.clearRect(0, 0, w, h);
  ctx.beginPath();
  ctx.moveTo(0, 0); ctx.lineTo(w, 0); ctx.lineTo(w, h - 16);
  const teeth = 40, tw = w / teeth;
  for (let i = teeth; i > 0; i--) { ctx.lineTo((i - 0.5) * tw, h - 1); ctx.lineTo((i - 1) * tw, h - 16); }
  ctx.closePath();
  ctx.fillStyle = '#f3f1ea';
  ctx.fill();
  // The adhesive band: slightly different sheen along the top.
  ctx.save();
  ctx.clip();
  ctx.fillStyle = 'rgba(160,150,120,0.14)';
  ctx.fillRect(0, 0, w, 96);
  ctx.restore();
}

function keyLegend(kind, base) {
  const px = 384;
  const c = canvasOf(px, Math.round(px * KEY.h / KEY.w));
  const ctx = c.getContext('2d');
  ctx.fillStyle = base;
  ctx.fillRect(0, 0, c.width, c.height);
  ctx.translate(c.width / 2, c.height / 2);
  const s = c.height / 142;
  ctx.scale(s, s);
  ctx.strokeStyle = ctx.fillStyle = 'rgba(255,255,255,0.97)';
  ctx.lineCap = ctx.lineJoin = 'round';
  ctx.lineWidth = 6.2;
  if (kind === 'mic') {
    roundRectPath(ctx, -8.5, -27, 17, 34, 8.5);
    ctx.fill();
    ctx.beginPath();
    ctx.arc(0, -3, 17, 0.05, Math.PI - 0.05);
    ctx.moveTo(0, 14); ctx.lineTo(0, 26);
    ctx.moveTo(-11, 27); ctx.lineTo(11, 27);
    ctx.stroke();
  } else if (kind === 'print') {
    ctx.beginPath();
    ctx.moveTo(0, 13); ctx.lineTo(0, -24);
    ctx.moveTo(-15, -9); ctx.lineTo(0, -24); ctx.lineTo(15, -9);
    ctx.moveTo(-23, 26); ctx.lineTo(23, 26);
    ctx.stroke();
  } else {
    ctx.beginPath();
    ctx.moveTo(-18, -18); ctx.lineTo(18, 18);
    ctx.moveTo(18, -18); ctx.lineTo(-18, 18);
    ctx.stroke();
  }
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 8;
  t.name = `key-${kind}`;
  return t;
}

function rollEndTexture() {
  const px = 512;
  const c = canvasOf(px, px);
  const ctx = c.getContext('2d');
  const r = px / 2;
  ctx.translate(r, r);
  ctx.fillStyle = '#b9b6ae';
  ctx.beginPath(); ctx.arc(0, 0, r, 0, Math.PI * 2); ctx.fill();
  // Wound paper: hairline rings that wander slightly, so rotation reads.
  for (let i = 0; i < 90; i++) {
    const q = 0.3 + (i / 90) * 0.7;
    ctx.strokeStyle = i % 2 ? 'rgba(255,255,255,0.28)' : 'rgba(60,55,45,0.18)';
    ctx.lineWidth = 1.1;
    ctx.beginPath();
    ctx.ellipse(1.6 * Math.sin(i), 1.6 * Math.cos(i * 1.3), q * r, q * r, 0, 0, Math.PI * 2);
    ctx.stroke();
  }
  // Core
  ctx.fillStyle = '#8c7f68';
  ctx.beginPath(); ctx.arc(0, 0, r * 0.3, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = '#1a1817';
  ctx.beginPath(); ctx.arc(0, 0, r * 0.22, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = PALETTE.green;
  ctx.beginPath(); ctx.arc(r * 0.13, 0, r * 0.035, 0, Math.PI * 2); ctx.fill();
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 8;
  t.name = 'roll-end';
  return t;
}

function wordmarkTexture(fg) {
  const c = canvasOf(512, 128);
  const ctx = c.getContext('2d');
  ctx.fillStyle = fg;
  ctx.font = `700 76px ${FONT}`;
  ctx.textBaseline = 'middle';
  ctx.textAlign = 'center';
  ctx.fillText('prins', 256, 68);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 8;
  t.name = 'wordmark';
  return t;
}

/* ------------------------------------------------------------------ */
/* Assemble the product                                                */
/* ------------------------------------------------------------------ */
function buildProduct(screen) {
  const product = new THREE.Group();
  product.name = 'Prins';

  const mats = {
    body: new THREE.MeshPhysicalMaterial({ name: 'Body shell', color: PALETTE.body, roughness: 0.46, sheen: 0.2, sheenRoughness: 0.6, sheenColor: 0xfff8ee, specularIntensity: 0.9, dithering: true, vertexColors: true }),
    wall: new THREE.MeshStandardMaterial({ name: 'Moulded wall', color: PALETTE.band, roughness: 0.7, vertexColors: true }),
    band: new THREE.MeshPhysicalMaterial({ name: 'Band', color: PALETTE.band, metalness: PALETTE.bandMetal, roughness: PALETTE.bandRough, vertexColors: true, dithering: true, specularIntensity: 1 }),
    metal: new THREE.MeshPhysicalMaterial({ name: 'Anodised aluminium', color: PALETTE.metal, metalness: 1, roughness: 0.34, dithering: true }),
    teeth: new THREE.MeshStandardMaterial({ name: 'Tear bar', color: 0xe4ddce, metalness: 1, roughness: 0.25, flatShading: true }),
    rubber: new THREE.MeshStandardMaterial({ name: 'Rubber foot', color: PALETTE.rubber, roughness: 0.82 }),
    interior: new THREE.MeshStandardMaterial({ name: 'Interior', color: PALETTE.interior, roughness: 0.9, envMapIntensity: 0.25 }),
    glassPlate: new THREE.MeshPhysicalMaterial({ name: 'Cover glass', color: PALETTE.glass, roughness: 0.08, clearcoat: 0.5, clearcoatRoughness: 0.05, specularIntensity: 0.8, envMapIntensity: 0.25 }),
    screen: new THREE.MeshPhysicalMaterial({ name: 'Display', color: PALETTE.glass, roughness: 0.08, clearcoat: 0.5, clearcoatRoughness: 0.05, specularIntensity: 0.8, envMapIntensity: 0.25, emissive: 0xffffff, emissiveMap: screen.tex, emissiveIntensity: 1 }),
    roll: new THREE.MeshStandardMaterial({ name: 'Paper roll end', map: rollEndTexture(), roughness: 0.85, envMapIntensity: 0.8 }),
    windowGlass: new THREE.MeshPhysicalMaterial({ name: 'Roll window', color: 0x000000, roughness: 0.04, clearcoat: 1, clearcoatRoughness: 0.03, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false }),
    led: new THREE.MeshStandardMaterial({ name: 'Status light', color: 0x151515, emissive: 0x000000, roughness: 0.3 }),
    port: new THREE.MeshStandardMaterial({ name: 'Port', color: 0x0b0b0b, roughness: 0.5 }),
  };

  const { cheeks, band, groove, frames, hwBand } = buildBody();
  const hw = hwBand;
  const md = band;
  // Key wells
  const keyXs = [-(KEY.w + KEY.gap), 0, KEY.w + KEY.gap];
  const keyHole = squircle(KEY.w + 1.3, KEY.h + 1.3, KEY.r + 0.65, 14);
  const keyHoles = keyXs.map((x) => keyHole.map((p) => v2(p.x + x, p.y)));
  patchInto(md, frames.shelf, keyHoles, hw);
  // Display opening
  const plateHole = squircle(PLATE.w + 0.8, PLATE.h + 0.8, PLATE.r + 0.4, 12);
  patchInto(md, frames.face, [plateHole], hw);
  // Printer deck opening
  const deck = { w: 74.5, h: 13.5 };
  const deckHole = pill(deck.w + 0.7, deck.h + 0.7, 14);
  patchInto(md, frames.top, [deckHole], hw);

  const bodyMesh = new THREE.Mesh(cheeks.build(), mats.body);
  bodyMesh.name = 'Cheeks';
  bodyMesh.castShadow = bodyMesh.receiveShadow = true;
  product.add(bodyMesh);
  const bandMesh = new THREE.Mesh(band.build(), mats.band);
  bandMesh.name = 'Band';
  bandMesh.castShadow = bandMesh.receiveShadow = true;
  product.add(bandMesh);
  const grooveMesh = new THREE.Mesh(groove.build(), mats.interior);
  grooveMesh.name = 'Shut line';
  grooveMesh.userData.noBake = true;
  product.add(grooveMesh);

  const attach = (frame, name) => {
    const g = new THREE.Group();
    g.name = name;
    g.applyMatrix4(frame.m);
    product.add(g);
    return g;
  };

  /* --- display ------------------------------------------------------- */
  const face = attach(frames.face, 'Display assembly');
  const plateWell = new THREE.Mesh(wellGeometry(plateHole, 3.2, 0.35), mats.wall);
  face.add(plateWell);
  const glass = new THREE.Mesh(plateGeometry(squircle(PLATE.w, PLATE.h, PLATE.r, 12), [], 2.8, 0.42), mats.glassPlate);
  glass.position.z = -2.65;
  glass.name = 'Cover glass';
  glass.castShadow = true;
  glass.receiveShadow = true;
  face.add(glass);
  const screenMesh = new THREE.Mesh(new THREE.PlaneGeometry(ACTIVE.w, ACTIVE.h), mats.screen);
  screenMesh.position.set(0, ACTIVE.up, 0.17);
  screenMesh.name = 'Display';
  face.add(screenMesh);
  // Printed chin: a small wordmark and a status pinlight.
  const chinY = -PLATE.h / 2 + 3.9;
  const mark = new THREE.Mesh(new THREE.PlaneGeometry(12, 3), new THREE.MeshStandardMaterial({
    name: 'Wordmark', map: wordmarkTexture('#9a968e'), transparent: true, roughness: 0.2, metalness: 0, emissive: 0x3a3936, depthWrite: false,
  }));
  mark.material.emissiveMap = mark.material.map;
  mark.position.set(-ACTIVE.w / 2 + 6, chinY, 0.17);
  mark.userData.noBake = true;
  face.add(mark);
  const led = new THREE.Mesh(new THREE.CircleGeometry(0.62, 24), mats.led);
  led.position.set(ACTIVE.w / 2 - 0.9, chinY, 0.17);
  led.userData.noBake = true;
  face.add(led);

  /* --- printer deck -------------------------------------------------- */
  const top = attach(frames.top, 'Printer deck');
  top.add(new THREE.Mesh(wellGeometry(deckHole, 7, 0.35), mats.wall));
  const slot = { w: 62.5, h: 3.1 };
  const slotZ = 0.6; // local s: towards the rear of the deck plate
  const slotLoop = pill(slot.w, slot.h, 8).map((p) => v2(p.x, p.y + slotZ));
  const plate = new THREE.Mesh(plateGeometry(pill(deck.w, deck.h, 14), [slotLoop], 1.9, 0.38), mats.metal);
  plate.position.z = -0.9;
  plate.name = 'Deck plate';
  plate.castShadow = plate.receiveShadow = true;
  top.add(plate);
  const slotWell = new THREE.Mesh(new THREE.PlaneGeometry(slot.w + 4, slot.h + 4), mats.interior);
  slotWell.position.set(0, slotZ, -6.5);
  top.add(slotWell);
  // Tear bar: real serrations, standing in front of the paper path.
  const teethShape = new THREE.Shape();
  const barW = 60, barH = 1.0, pitch = 1.5, toothH = 1.15;
  teethShape.moveTo(-barW / 2, -1.2);
  teethShape.lineTo(barW / 2, -1.2);
  teethShape.lineTo(barW / 2, barH);
  const nTeeth = Math.round(barW / pitch);
  for (let i = 0; i < nTeeth; i++) {
    const x = barW / 2 - (i + 0.5) * (barW / nTeeth);
    teethShape.lineTo(x, barH + toothH);
    teethShape.lineTo(barW / 2 - (i + 1) * (barW / nTeeth), barH);
  }
  teethShape.closePath();
  const teethGeo = new THREE.ExtrudeGeometry(teethShape, { depth: 0.5, bevelEnabled: false });
  const bar = new THREE.Mesh(teethGeo, mats.teeth);
  bar.name = 'Tear bar';
  // Stand it up (shape Y -> deck normal, leaning back with the paper)
  bar.rotation.x = Math.PI / 2 + NOTE.tilt * -1;
  bar.position.set(0, slotZ - slot.h / 2 + 0.5, 1.0);
  bar.castShadow = true;
  top.add(bar);

  /* --- keys ---------------------------------------------------------- */
  const shelf = attach(frames.shelf, 'Keys');
  const keyDefs = [
    { name: 'blue', kind: 'mic', color: PALETTE.blue },
    { name: 'green', kind: 'print', color: PALETTE.green },
    { name: 'red', kind: 'x', color: PALETTE.red },
  ];
  const capGeo = keycapGeometry(KEY.w, KEY.h, KEY.r, KEY.proud);
  const wellGeo = wellGeometry(keyHole, 8, 0.45);
  const keys = {};
  keyDefs.forEach((def, i) => {
    const well = new THREE.Mesh(wellGeo, mats.wall);
    well.position.x = keyXs[i];
    shelf.add(well);
    const mat = new THREE.MeshPhysicalMaterial({
      name: `Key ${def.name}`, map: keyLegend(def.kind, def.color), roughness: 0.34,
      clearcoat: 0.55, clearcoatRoughness: 0.28, specularIntensity: 0.9,
      emissive: new THREE.Color(def.color), emissiveIntensity: 0,
    });
    const cap = new THREE.Mesh(capGeo, mat);
    cap.name = `Key ${def.name}`;
    cap.position.x = keyXs[i];
    cap.castShadow = cap.receiveShadow = true;
    shelf.add(cap);
    const proxy = new THREE.Mesh(new THREE.BoxGeometry(KEY.w + 3.5, KEY.h + 5, 14), new THREE.MeshBasicMaterial({ visible: false }));
    proxy.position.set(keyXs[i], 0, 5);
    proxy.userData.key = def.name;
    proxy.userData.noExport = true;
    proxy.userData.noBake = true;
    shelf.add(proxy);
    keys[def.name] = { cap, proxy, value: 0, vel: 0, target: 0, mat, rest: 0 };
  });

  /* --- roll window --------------------------------------------------- */
  const win = new THREE.Group();
  win.name = 'Roll window';
  win.position.set(W / 2, ROLL.y, ROLL.z);
  win.rotation.y = Math.PI / 2; // local +z -> world +x
  product.add(win);
  const ringPts = [
    [ROLL.r - 0.5, -3], [ROLL.r - 0.5, 0.25], [ROLL.r - 0.25, 0.62], [ROLL.r + 0.4, 0.82],
    [ROLL.r + 1.25, 0.72], [ROLL.r + 1.75, 0.3], [ROLL.r + 1.9, -0.4], [ROLL.r + 1.9, -2],
  ].reverse().map(([r, z]) => v2(r, z));
  const ringCurve = new THREE.SplineCurve(ringPts).getPoints(40);
  const ring = new THREE.Mesh(new THREE.LatheGeometry(ringCurve, 96), mats.metal);
  ring.rotation.x = Math.PI / 2;
  ring.name = 'Window trim';
  ring.castShadow = ring.receiveShadow = true;
  win.add(ring);
  const bore = new THREE.Mesh(new THREE.CylinderGeometry(ROLL.r + 0.8, ROLL.r + 0.8, 10, 72, 1, true), mats.interior);
  bore.material.side = THREE.DoubleSide;
  bore.rotation.x = Math.PI / 2;
  bore.position.z = -5;
  bore.userData.noBake = true;
  win.add(bore);
  const rollEnd = new THREE.Mesh(new THREE.CircleGeometry(ROLL.r + 0.8, 72), mats.roll);
  rollEnd.position.z = -4.5;
  rollEnd.name = 'Paper roll';
  win.add(rollEnd);
  const dome = new THREE.Mesh(new THREE.SphereGeometry(ROLL.r * 4, 48, 8, 0, Math.PI * 2, 0, Math.asin((ROLL.r - 0.3) / (ROLL.r * 4))), mats.windowGlass);
  dome.rotation.x = Math.PI / 2;
  dome.position.z = 0.32 - ROLL.r * 4 * Math.cos(Math.asin((ROLL.r - 0.3) / (ROLL.r * 4)));
  dome.name = 'Window glass';
  dome.userData.noBake = true;
  dome.renderOrder = 2;
  win.add(dome);

  /* --- foot and rear port -------------------------------------------- */
  const footLoop = squircle(W - 18, 70, 16, 12);
  const foot = new THREE.Mesh(plateGeometry(footLoop, [], BASE + 3, 0.5), mats.rubber);
  foot.rotation.x = -Math.PI / 2;
  foot.position.set(0, 0, 8);
  foot.name = 'Foot';
  foot.castShadow = true;
  product.add(foot);

  const rear = attach(frames.rear, 'Rear');
  const portPlate = new THREE.Mesh(plateGeometry(pill(11.2, 4.6, 8), [], 0.12, 0.06), mats.metal);
  portPlate.position.set(0, frames.rear.len / 2 - 6, 0.0);
  rear.add(portPlate);
  const port = new THREE.Mesh(plateGeometry(pill(9.2, 3.2, 8), [], 0.04, 0.02), mats.port);
  port.position.set(0, frames.rear.len / 2 - 6, 0.12);
  rear.add(port);
  const rearMark = new THREE.Mesh(new THREE.PlaneGeometry(14, 3.5), new THREE.MeshStandardMaterial({
    name: 'Wordmark rear', map: wordmarkTexture('#a9a59c'), transparent: true, roughness: 0.4, depthWrite: false,
  }));
  rearMark.position.set(0, frames.rear.len / 2 - 13, 0.03);
  rearMark.rotation.z = Math.PI;
  rearMark.userData.noBake = true;
  rear.add(rearMark);

  // Slot point on the deck, for the paper path (world space).
  const slotPoint = frames.top.o.clone()
    .addScaledVector(frames.top.v, slotZ + 0.2)
    .addScaledVector(frames.top.n, 0.4);

  return { product, keys, mats, rollEnd, led, slotPoint, frames, bodyMesh, bandMesh };
}

/* ------------------------------------------------------------------ */
/* A sticky note: bendable strip with separate front/back materials     */
/* ------------------------------------------------------------------ */
const NOTE_ROWS = 30;
const noteOfMesh = new WeakMap();
class Note {
  constructor(paperMat) {
    this.canvas = canvasOf(NOTE_PX.w, NOTE_PX.h);
    this.ctx = this.canvas.getContext('2d');
    this.tex = new THREE.CanvasTexture(this.canvas);
    this.tex.colorSpace = THREE.SRGBColorSpace;
    this.tex.anisotropy = 16;
    this.tex.name = 'note';

    const v = (NOTE_ROWS + 1) * 2;
    const pos = new Float32Array(v * 2 * 3);
    const nrm = new Float32Array(v * 2 * 3);
    const uv = new Float32Array(v * 2 * 2);
    const idxF = [], idxB = [];
    for (let i = 0; i <= NOTE_ROWS; i++) {
      const t = i / NOTE_ROWS;
      [0, 1].forEach((c) => {
        const a = i * 2 + c;
        uv[a * 2] = c; uv[a * 2 + 1] = t;
        uv[(a + v) * 2] = 1 - c; uv[(a + v) * 2 + 1] = t;
      });
      if (i < NOTE_ROWS) {
        const a = i * 2, b = a + 1, c = a + 2, d = a + 3;
        idxF.push(a, b, d, a, d, c);
        idxB.push(a + v, d + v, b + v, a + v, c + v, d + v);
      }
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    g.setAttribute('normal', new THREE.BufferAttribute(nrm, 3));
    g.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
    g.setIndex([...idxF, ...idxB]);
    g.addGroup(0, idxF.length, 0);
    g.addGroup(idxF.length, idxB.length, 1);
    g.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, NOTE.h / 2, 0), NOTE.h * 1.25);
    g.boundingBox = new THREE.Box3(new THREE.Vector3(-NOTE.w, -NOTE.h, -NOTE.h), new THREE.Vector3(NOTE.w, NOTE.h * 1.5, NOTE.h));
    this.geo = g;
    this.front = new THREE.MeshStandardMaterial({ name: 'Note front', map: this.tex, roughness: 0.8, alphaTest: 0.5, envMapIntensity: 1.45, emissive: 0xfff6e8, emissiveMap: this.tex, emissiveIntensity: 0.3 });
    this.mesh = new THREE.Mesh(g, [this.front, paperMat]);
    this.mesh.name = 'Sticky note';
    this.mesh.castShadow = true;
    this.mesh.frustumCulled = false;
    this.mesh.visible = false;
    noteOfMesh.set(this.mesh, this);
    this.setShape(NOTE.h, 1);
  }
  setCard(card) {
    this.card = card;
    drawNote(this.ctx, card);
    this.tex.needsUpdate = true;
  }
  // emerged: millimetres out of the slot. curl: 0 flat, 1 relaxed curve towards the viewer.
  setShape(emerged, curl) {
    const h = NOTE.h, w2 = NOTE.w / 2;
    const pos = this.geo.attributes.position, nrm = this.geo.attributes.normal;
    const v = (NOTE_ROWS + 1) * 2;
    let y = 0, z = 0;
    const dl = h / NOTE_ROWS;
    const hidden = h - emerged;
    // Walk from the slot upward so the free end does the bending.
    const coords = [];
    for (let i = 0; i <= NOTE_ROWS; i++) {
      const l = i * dl - hidden; // distance beyond the slot along the paper
      const q = Math.max(0, l) / NOTE.h;
      const ang = curl * 0.6 * q * q;
      if (i > 0) {
        const lm = (i - 0.5) * dl - hidden;
        const qm = Math.max(0, lm) / NOTE.h;
        const am = curl * 0.6 * qm * qm;
        y += Math.cos(am) * dl;
        z += Math.sin(am) * dl;
      }
      coords.push({ y, z, ang });
    }
    const offY = hidden > 0 ? coords.reduce((best, c, i) => (i * dl - hidden <= 0 ? c.y : best), 0) : 0;
    const offZ = hidden > 0 ? coords.reduce((best, c, i) => (i * dl - hidden <= 0 ? c.z : best), 0) : 0;
    for (let i = 0; i <= NOTE_ROWS; i++) {
      const c = coords[i];
      const l = i * dl - hidden;
      const yy = hidden > 0 ? c.y - offY + Math.min(0, l) * 0 : c.y;
      const zz = hidden > 0 ? c.z - offZ : c.z;
      const ny = -Math.sin(c.ang), nz = Math.cos(c.ang);
      [-1, 1].forEach((sx, k) => {
        const a = i * 2 + k;
        pos.setXYZ(a, sx * w2, yy, zz); nrm.setXYZ(a, 0, ny, nz);
        pos.setXYZ(a + v, sx * w2, yy, zz); nrm.setXYZ(a + v, 0, -ny, -nz);
      });
    }
    pos.needsUpdate = nrm.needsUpdate = true;
  }
}

/* ------------------------------------------------------------------ */
/* Studio light as an in-code environment (no external HDRIs)           */
/* ------------------------------------------------------------------ */
function buildEnvironment(renderer) {
  const env = new THREE.Scene();
  const panel = (w, h, pos, look, intensity, tint = 0xffffff) => {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({
      color: new THREE.Color(tint).multiplyScalar(intensity), side: THREE.DoubleSide,
    }));
    m.position.set(...pos);
    m.lookAt(...look);
    env.add(m);
  };
  const shell = new THREE.Mesh(new THREE.SphereGeometry(30, 32, 16), new THREE.ShaderMaterial({
    side: THREE.BackSide,
    vertexShader: 'varying vec3 d; void main(){ d = normalize(position); gl_Position = projectionMatrix*modelViewMatrix*vec4(position,1.); }',
    fragmentShader: `varying vec3 d; void main(){
      float h = d.y*.5+.5;
      vec3 low = vec3(.20,.185,.17);   // bounce off the sweep
      vec3 mid = vec3(.20,.195,.19);
      vec3 up  = vec3(.34,.34,.34);
      vec3 c = mix(low, mid, smoothstep(.15,.5,h));
      c = mix(c, up, smoothstep(.5,1.,h));
      gl_FragColor = vec4(c,1.);
    }`,
  }));
  env.add(shell);
  panel(24, 16, [-4, 22, 5], [0, 0, 0], 4.2, 0xfffaf2);       // big overhead softbox
  panel(8, 26, [-22, 8, 12], [0, 2, 0], 5.5, 0xfff6ea);       // tall key strip, camera left
  panel(4, 24, [23, 7, 2], [0, 2, 0], 4.6, 0xf2f6ff);         // rim strip, camera right: edge line on the side
  panel(18, 2.0, [0, 1.2, 25], [0, 2, 0], 1.3, 0xffffff);     // low front strip: a line along the nose
  panel(32, 18, [6, 10, -22], [0, 2, 0], 3.2, 0xffffff);      // back wall
  const pmrem = new THREE.PMREMGenerator(renderer);
  const rt = pmrem.fromScene(env, 0.012, 0.1, 100);
  pmrem.dispose();
  return rt.texture;
}

/* ------------------------------------------------------------------ */
/* Floor shadow by real area-light accumulation                         */
/* ------------------------------------------------------------------ */
const FLOOR_EXTENT = 620;
const KEY_DIR = new THREE.Vector3(-0.56, 1, 0.5).normalize();

function buildAccumMaterial() {
  return new THREE.ShaderMaterial({
    uniforms: { uL: { value: new THREE.Vector3(0, 1, 0) }, uE: { value: FLOOR_EXTENT }, uW: { value: 0 } },
    vertexShader: `uniform vec3 uL; uniform float uE;
      void main(){ vec4 w = modelMatrix*vec4(position,1.);
        vec2 p = w.xz - uL.xz*(w.y/uL.y);
        gl_Position = vec4(p/uE, 0., 1.); }`,
    fragmentShader: 'uniform float uW; void main(){ gl_FragColor = vec4(uW); }',
    side: THREE.DoubleSide,
    blending: THREE.CustomBlending,
    blendEquation: THREE.AddEquation,
    blendSrc: THREE.OneFactor, blendDst: THREE.OneFactor,
    blendSrcAlpha: THREE.OneFactor, blendDstAlpha: THREE.OneFactor,
    depthTest: true, depthWrite: true, depthFunc: THREE.LessDepth,
    transparent: true, toneMapped: false,
  });
}

function hammersleySamples(n) {
  const out = [];
  for (let i = 0; i < n; i++) {
    let bits = i, rad = 0, f = 0.5;
    while (bits) { rad += f * (bits & 1); bits >>= 1; f *= 0.5; }
    out.push([(i + 0.5) / n, rad]);
  }
  return out;
}

function lightSamples(nKey, nDome) {
  const list = [];
  const tmp = new THREE.Vector3();
  const axisA = new THREE.Vector3().crossVectors(KEY_DIR, new THREE.Vector3(0, 0, 1)).normalize();
  const axisB = new THREE.Vector3().crossVectors(KEY_DIR, axisA).normalize();
  hammersleySamples(nKey).forEach(([u, v]) => {
    const r = Math.sqrt(u) * 0.42, a = v * Math.PI * 2;
    tmp.copy(KEY_DIR).addScaledVector(axisA, Math.cos(a) * r).addScaledVector(axisB, Math.sin(a) * r);
    list.push({ dir: tmp.clone().normalize(), w: 0.6 / nKey });
  });
  hammersleySamples(nDome).forEach(([u, v]) => {
    const y = 0.55 + 0.45 * Math.sqrt(1 - u), rr = Math.sqrt(1 - y * y), a = v * Math.PI * 2;
    list.push({ dir: new THREE.Vector3(Math.cos(a) * rr, y, Math.sin(a) * rr), w: 0.4 / nDome });
  });
  return list;
}

class FloorShadow {
  constructor(renderer, scene, opts) {
    this.renderer = renderer;
    this.scene = scene;
    const type = renderer.extensions.has('EXT_color_buffer_float') ? THREE.HalfFloatType : THREE.UnsignedByteType;
    const mk = (size) => new THREE.WebGLRenderTarget(size, size, { type, format: THREE.RGBAFormat, depthBuffer: true, generateMipmaps: false, minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter });
    this.baseRT = mk(opts.baseSize);
    this.dynRT = mk(opts.dynSize);
    this.mat = buildAccumMaterial();
    this.baseSamples = lightSamples(opts.nKey, opts.nDome);
    this.dynSamples = lightSamples(opts.dynKey, opts.dynDome);
    this.cam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
    this.tmpBase = mk(opts.baseSize);
    this.tmpDyn = mk(opts.dynSize);
    this.blurMat = new THREE.ShaderMaterial({
      uniforms: { t: { value: null }, d: { value: new THREE.Vector2() } },
      vertexShader: 'varying vec2 u; void main(){ u = uv; gl_Position = vec4(position.xy,0.,1.); }',
      fragmentShader: `uniform sampler2D t; uniform vec2 d; varying vec2 u;
        void main(){ vec4 c = texture2D(t,u)*.2270270;
          c += (texture2D(t,u+d*1.3846)+texture2D(t,u-d*1.3846))*.3162162;
          c += (texture2D(t,u+d*3.2308)+texture2D(t,u-d*3.2308))*.0702703;
          gl_FragColor = c; }`,
      depthTest: false, depthWrite: false, toneMapped: false,
    });
    this.quadScene = new THREE.Scene();
    this.quadScene.add(new THREE.Mesh(new THREE.PlaneGeometry(2, 2), this.blurMat));
    this.quadScene.children[0].frustumCulled = false;
    const floorGeo = new THREE.PlaneGeometry(FLOOR_EXTENT * 2, FLOOR_EXTENT * 2);
    floorGeo.rotateX(-Math.PI / 2);
    this.floorMat = new THREE.ShaderMaterial({
      uniforms: {
        tBase: { value: this.baseRT.texture }, tDyn: { value: this.dynRT.texture },
        uE: { value: FLOOR_EXTENT }, uColor: { value: PALETTE.shadow }, uK: { value: 0.86 },
      },
      vertexShader: 'varying vec2 vP; void main(){ vec4 w = modelMatrix*vec4(position,1.); vP = w.xz; gl_Position = projectionMatrix*viewMatrix*w; }',
      fragmentShader: `uniform sampler2D tBase, tDyn; uniform float uE, uK; uniform vec3 uColor; varying vec2 vP;
        void main(){
          vec2 uv = vP/uE*.5+.5;
          float a = texture2D(tBase, uv).r;
          float b = texture2D(tDyn, uv).r;
          float m = 1. - (1.-clamp(a,0.,1.))*(1.-clamp(b,0.,1.));
          float edge = smoothstep(1., .82, max(abs(vP.x),abs(vP.y))/uE);
          float n = fract(52.9829189*fract(dot(gl_FragCoord.xy, vec2(.06711056,.00583715))));
          gl_FragColor = vec4(uColor, m*uK*edge + (n-.5)/255.);
          #include <colorspace_fragment>
        }`,
      transparent: true, depthWrite: false, toneMapped: false,
    });
    this.floor = new THREE.Mesh(floorGeo, this.floorMat);
    this.floor.name = 'Floor shadow';
    this.floor.renderOrder = -1;
    this.floor.position.y = -0.02;
    scene.add(this.floor);
  }
  accumulate(rt, samples, roots) {
    const r = this.renderer;
    const prevColor = r.getClearColor(new THREE.Color());
    const prevAlpha = r.getClearAlpha();
    const prevBg = this.scene.background;
    const prevOverride = this.scene.overrideMaterial;
    const prevAuto = r.autoClear;
    const prevShadow = r.shadowMap.autoUpdate;
    const prevNeeds = r.shadowMap.needsUpdate;
    r.shadowMap.autoUpdate = false;
    r.shadowMap.needsUpdate = false;
    this.scene.background = null;
    this.scene.overrideMaterial = this.mat;
    r.autoClear = false;
    const hidden = [];
    this.scene.children.forEach((c) => { if (c.visible && !roots.includes(c) && c.isObject3D && !c.isLight) { c.visible = false; hidden.push(c); } });
    r.setRenderTarget(rt);
    r.setClearColor(0x000000, 0);
    r.clear(true, true, true);
    this.floor.visible = false;
    samples.forEach((s) => {
      this.mat.uniforms.uL.value.copy(s.dir);
      this.mat.uniforms.uW.value = s.w;
      r.clearDepth();
      r.render(this.scene, this.cam);
    });
    this.floor.visible = true;
    this.scene.overrideMaterial = null;
    // Two blur iterations melt any remaining sample edges into a true soft penumbra.
    const tmp = rt === this.baseRT ? this.tmpBase : this.tmpDyn;
    const px = 1 / rt.width;
    const spread = rt === this.baseRT ? 1.25 : 1.1;
    for (let it = 0; it < 2; it++) {
      this.blurMat.uniforms.t.value = rt.texture;
      this.blurMat.uniforms.d.value.set(px * spread, 0);
      r.setRenderTarget(tmp);
      r.render(this.quadScene, this.cam);
      this.blurMat.uniforms.t.value = tmp.texture;
      this.blurMat.uniforms.d.value.set(0, px * spread);
      r.setRenderTarget(rt);
      r.render(this.quadScene, this.cam);
    }
    r.setRenderTarget(null);
    hidden.forEach((c) => { c.visible = true; });
    this.scene.overrideMaterial = prevOverride;
    this.scene.background = prevBg;
    r.autoClear = prevAuto;
    r.setClearColor(prevColor, prevAlpha);
    r.shadowMap.autoUpdate = prevShadow;
    r.shadowMap.needsUpdate = prevNeeds;
  }
}

/* ------------------------------------------------------------------ */
/* The floor: a pool of light and a soft mirror of the device            */
/* ------------------------------------------------------------------ */
// Both are premultiplied with alpha covering the brightest channel, so browsers composite them
// the same way: a canvas pixel brighter than its alpha is undefined in WebGL.
function buildLightPool() {
  const geo = new THREE.CircleGeometry(520, 64);
  geo.rotateX(-Math.PI / 2);
  const mat = new THREE.ShaderMaterial({
    uniforms: { uColor: { value: new THREE.Color(1, 0.5, 0.2) }, uLevel: { value: 1 } },
    vertexShader: 'varying vec2 vP; void main(){ vec4 w = modelMatrix*vec4(position,1.); vP = w.xz; gl_Position = projectionMatrix*viewMatrix*w; }',
    fragmentShader: `uniform vec3 uColor; uniform float uLevel; varying vec2 vP;
      void main(){
        float r = length(vP - vec2(0.,14.))/520.;
        float g = exp(-r*r*16.)*.36 + exp(-r*r*70.)*.44;
        float n = fract(52.9829189*fract(dot(gl_FragCoord.xy, vec2(.06711056,.00583715))));
        vec3 c = max(uColor*g*uLevel + (n-.5)/255., 0.);
        gl_FragColor = vec4(c, max(c.r, max(c.g, c.b)));
      }`,
    transparent: true, depthWrite: false, toneMapped: false, premultipliedAlpha: true,
  });
  const mesh = new THREE.Mesh(geo, mat);
  mesh.name = 'Light pool';
  mesh.position.y = -0.06;
  mesh.renderOrder = -3;
  return mesh;
}

function buildMirror(size) {
  const geo = new THREE.CircleGeometry(380, 48);
  const mirror = new Reflector(geo, {
    textureWidth: size,
    textureHeight: size,
    clipBias: 0.001,
    shader: {
      name: 'SoftMirror',
      uniforms: { color: { value: null }, tDiffuse: { value: null }, textureMatrix: { value: null } },
      vertexShader: `uniform mat4 textureMatrix; varying vec4 vUv; varying vec2 vP;
        void main(){ vUv = textureMatrix*vec4(position,1.); vec4 w = modelMatrix*vec4(position,1.); vP = w.xz; gl_Position = projectionMatrix*viewMatrix*w; }`,
      // Bright highlights are clamped first, or the blur turns them into sparkling dots.
      fragmentShader: `uniform sampler2D tDiffuse; varying vec4 vUv; varying vec2 vP;
        vec4 at(vec2 uv){ return min(texture2D(tDiffuse,uv), vec4(1.)); }
        void main(){
          vec2 uv = vUv.xy/vUv.w;
          vec2 d = vec2(.0026,.0052);
          vec4 c = at(uv)*.28;
          c += (at(uv+d)+at(uv-d)+at(uv+vec2(d.x,-d.y))+at(uv+vec2(-d.x,d.y)))*.13;
          c += (at(uv+d*vec2(2.4,0.))+at(uv-d*vec2(2.4,0.))+at(uv+d*vec2(0.,2.4))+at(uv-d*vec2(0.,2.4)))*.05;
          float r = length(vP - vec2(0.,10.));
          float k = smoothstep(165.,35.,r)*.2;
          gl_FragColor = c*k;
          #include <tonemapping_fragment>
          #include <colorspace_fragment>
          gl_FragColor.a = max(gl_FragColor.a, max(gl_FragColor.r, max(gl_FragColor.g, gl_FragColor.b)));
        }`,
    },
  });
  mirror.name = 'Floor mirror';
  mirror.rotation.x = -Math.PI / 2;
  mirror.position.y = -0.04;
  mirror.renderOrder = -2;
  mirror.material.transparent = true;
  mirror.material.depthWrite = false;
  mirror.material.premultipliedAlpha = true;
  return mirror;
}

/* ------------------------------------------------------------------ */
/* Main                                                                */
/* ------------------------------------------------------------------ */
async function main() {
  const canvas = document.getElementById('stage');
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: 'high-performance' });
  } catch (err) {
    document.body.classList.add('no-webgl');
    document.getElementById('nogl-img').src = 'stills/hero.png';
    return;
  }
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const narrow = Math.min(window.innerWidth, window.innerHeight) < 600;
  const coarse = window.matchMedia('(pointer: coarse)').matches;
  const lowPower = narrow || coarse;
  const atmosphere = startAtmosphere(document.getElementById('atmos'), { lowPower, reduceMotion });
  document.querySelectorAll('[data-words]').forEach((el) => {
    const label = el.textContent;
    el.setAttribute('aria-label', label);
    el.innerHTML = label.split(' ').map((w, i) => `<span aria-hidden="true" style="--i:${i}">${w}</span>`).join(' ');
  });
  try {
    await Promise.all(['400 16px Archivo', '500 16px Archivo', '700 16px Archivo', '800 16px Archivo'].map((f) => document.fonts.load(f)));
  } catch (err) { /* system font fallback is fine */ }

  renderer.setClearColor(0x000000, 0);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, lowPower ? 2 : 2));
  renderer.toneMapping = THREE.NeutralToneMapping;
  renderer.toneMappingExposure = 1.0;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;
  renderer.shadowMap.autoUpdate = false;
  renderer.shadowMap.needsUpdate = true;

  const scene = new THREE.Scene();
  scene.environment = buildEnvironment(renderer);
  scene.environmentIntensity = 0.62;

  const camera = new THREE.PerspectiveCamera(22, 1, 40, 6000);
  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.dampingFactor = 0.07;
  controls.enablePan = false;
  controls.minPolarAngle = THREE.MathUtils.degToRad(28);
  controls.maxPolarAngle = THREE.MathUtils.degToRad(88);
  controls.rotateSpeed = 0.75;
  controls.zoomSpeed = 0.7;

  const key = new THREE.DirectionalLight(0xfff1e0, 1.25);
  key.position.copy(KEY_DIR).multiplyScalar(600);
  key.target.position.set(0, 40, 0);
  key.castShadow = true;
  key.shadow.mapSize.setScalar(lowPower ? 2048 : 4096);
  const sc = key.shadow.camera;
  sc.left = -170; sc.right = 170; sc.top = 170; sc.bottom = -170; sc.near = 200; sc.far = 1100;
  key.shadow.radius = lowPower ? 3 : 5;
  key.shadow.bias = -0.0004;
  key.shadow.normalBias = 0.5;
  scene.add(key, key.target);
  // Close soft fills give the big flat faces a gradient instead of a single flat tone.
  const fillR = new THREE.PointLight(0xfff4e6, 52000, 0, 2);
  fillR.position.set(210, 40, 70);
  const fillF = new THREE.PointLight(0xffffff, 26000, 0, 2);
  fillF.position.set(-60, 170, 190);
  const fillB = new THREE.PointLight(0xffffff, 42000, 0, 2);
  fillB.position.set(70, 150, -210);
  // The shaft of light from above: picks out the top of the device and the note.
  const shaft = new THREE.PointLight(0xffe2bd, 150000, 0, 2);
  shaft.position.set(0, 330, -40);
  const rimL = new THREE.PointLight(0xffb27a, 62000, 0, 2);
  rimL.position.set(-250, 90, -120);
  scene.add(fillR, fillF, fillB, shaft, rimL);

  const screen = new Screen(lowPower ? 2.5 : 4);
  const built = buildProduct(screen);
  const { product, keys, mats, rollEnd, led, slotPoint } = built;
  scene.add(product);

  const notesGroup = new THREE.Group();
  notesGroup.name = 'Notes';
  scene.add(notesGroup);

  // Shared back of the paper
  const backCanvas = canvasOf(NOTE_PX.w, NOTE_PX.h);
  drawNoteBack(backCanvas.getContext('2d'));
  const backTex = new THREE.CanvasTexture(backCanvas);
  backTex.colorSpace = THREE.SRGBColorSpace;
  backTex.name = 'note-back';
  const paperBack = new THREE.MeshStandardMaterial({ name: 'Note back', map: backTex, roughness: 0.85, alphaTest: 0.5 });

  const pool = [];
  for (let i = 0; i < 6; i++) {
    const n = new Note(paperBack);
    notesGroup.add(n.mesh);
    pool.push(n);
  }

  /* --- floor shadow bake --------------------------------------------- */
  const floorShadow = new FloorShadow(renderer, scene, lowPower
    ? { baseSize: 768, dynSize: 384, nKey: 40, nDome: 56, dynKey: 16, dynDome: 16 }
    : { baseSize: 1536, dynSize: 768, nKey: 128, nDome: 192, dynKey: 40, dynDome: 40 });
  // Hide what should not contribute to the device shadow.
  const noBakeList = [];
  product.traverse((o) => { if (o.isMesh && (o.userData.noBake || o.material?.transparent)) { noBakeList.push([o, o.visible]); o.visible = false; } });
  product.traverse((o) => { if (o.isMesh) o.frustumCulled = false; });
  floorShadow.accumulate(floorShadow.baseRT, floorShadow.baseSamples, [product]);
  noBakeList.forEach(([o, vis]) => { o.visible = vis; });
  product.traverse((o) => { if (o.isMesh) o.frustumCulled = true; });

  floorShadow.floorMat.uniforms.uK.value = 0.78;
  const lightPool = buildLightPool();
  const mirror = buildMirror(lowPower ? 640 : 1280);
  scene.add(lightPool, mirror);

  /* --- framing and resize -------------------------------------------- */
  const HERO = { az: THREE.MathUtils.degToRad(27), pol: THREE.MathUtils.degToRad(74) };
  const target = new THREE.Vector3(0, 70, 8);

  function framedDistance(aspect) {
    const t = Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
    const needV = aspect < 1.25 ? 320 : 248;   // room for the words below
    const needH = aspect < 0.8 ? 168 : 196;
    return Math.max(needV / (2 * t), needH / (2 * t * aspect));
  }
  function setCam(az, pol, dist) {
    camera.position.set(
      target.x + dist * Math.sin(pol) * Math.sin(az),
      target.y + dist * Math.cos(pol),
      target.z + dist * Math.sin(pol) * Math.cos(az),
    );
    camera.lookAt(target);
  }

  const pixelCapNow = () => Math.min(window.devicePixelRatio || 1, 2, pixelCap);
  let distance = 700;
  let fitDist = 700;
  let touched = false;
  let lastSize = '';
  function resize() {
    const w = window.innerWidth, h = window.innerHeight;
    const sizeKey = `${w}x${h}`;
    if (sizeKey === lastSize) return;
    lastSize = sizeKey;
    renderer.setPixelRatio(pixelCapNow());
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    const fit = framedDistance(w / h);
    const prevFit = fitDist;
    const prevTarget = controls.target.clone();
    controls.minDistance = fit * 0.32;
    controls.maxDistance = fit * 1.45;
    target.y = w / h < 1.25 ? 62 : 68;
    fitDist = fit;
    controls.target.copy(target);
    if (!touched) {
      distance = fit;
      const curAz = idle.az;
      setCam(curAz, idle.pol, distance);
    } else {
      // Keep the viewer's angle and relative zoom, so turning a phone never crops the product.
      const off = camera.position.clone().sub(prevTarget);
      off.multiplyScalar(fit / prevFit);
      off.setLength(Math.min(Math.max(off.length(), controls.minDistance), controls.maxDistance));
      camera.position.copy(controls.target).add(off);
    }
    controls.update();
    renderer.shadowMap.needsUpdate = true;
    dirty = 3;
  }

  /* --- interaction state --------------------------------------------- */
  const idle = { on: true, az: HERO.az, pol: HERO.pol, t: 0, base: HERO.az, lastTouch: performance.now() };
  let dirty = 3;
  if (reduceMotion) idle.on = false;
  const intro = { t: 0, dur: 2.4, on: !reduceMotion };

  let dynShadowDirty = false;
  const app = {
    mode: 'card', // card | printing | listening | thinking | clearing | empty
    queue: SEED_CARDS.map((c) => ({ ...c })),
    voiceIdx: 0,
    time: 0,
    modeStart: 0,
    prevCard: null,
    prevN: 0,
    levels: new Array(9).fill(0.1),
    feed: null,
    slotNote: null,
    desk: [],
    flying: [],
    pending: null,
    refillAt: 0,
    rollSpeed: 0,
    torn: 0,
  };

  const setLed = (color, intensity) => {
    led.material.emissive.set(color);
    led.material.emissiveIntensity = intensity;
  };

  function freeNote() {
    const n = pool.find((p) => p !== app.slotNote && !app.desk.includes(p) && !app.flying.some((f) => f.note === p));
    if (n) return n;
    // Recycle the oldest note on the desk.
    const old = app.desk.shift();
    old.mesh.visible = false;
    app.desk.forEach((d, i) => { d.mesh.position.y = 0.08 + i * 0.1; });
    dynShadowDirty = true;
    return old;
  }

  function placeInSlot(note, emerged, curl) {
    note.mesh.visible = true;
    note.mesh.position.copy(slotPoint);
    note.mesh.rotation.set(-NOTE.tilt, 0, 0);
    note.setShape(emerged, curl);
    note.emerged = emerged;
    note.curl = curl;
  }

  // Torn notes form a loose stack on the desk: beside the device on wide views, in front on tall ones.
  function deskSpot(i) {
    const wide = camera.aspect >= 1.25;
    const baseX = wide ? -112 : 16, baseZ = wide ? 92 : 118;
    const jx = [0, -5, 6, -3, 4], jz = [0, 3, -4, 5, -2];
    const yaw = [0.16, 0.02, 0.24, 0.07, 0.19];
    const k = (app.torn++) % 5;
    return {
      pos: new THREE.Vector3(baseX + jx[k], 0.08 + i * 0.1, baseZ + jz[k]),
      quat: new THREE.Quaternion().setFromEuler(new THREE.Euler(-Math.PI / 2, yaw[k], 0, 'YXZ')),
    };
  }

  function tearOff(note) {
    if (!note || app.slotNote !== note) return;
    app.slotNote = null;
    atmosphere.pulse(0.45);
    // Keep the paper's pose; lift it clear of the teeth, then let it drift down.
    note.setShape(NOTE.h, note.curl);
    const spot = deskSpot(app.desk.length + app.flying.length);
    app.flying.push({
      note, t: 0, dur: 0.95,
      fromPos: note.mesh.position.clone(), fromQuat: note.mesh.quaternion.clone(),
      toPos: spot.pos, toQuat: spot.quat, curl0: note.curl,
    });
  }

  function enterMode(mode) {
    app.mode = mode;
    app.modeStart = app.time;
    dirty = 3;
  }

  function current() { return app.queue[0]; }

  function pressGreen() {
    if (app.mode !== 'card' || !current()) return;
    const card = app.queue.shift();
    if (app.slotNote) tearOff(app.slotNote);
    const note = freeNote();
    note.setCard(card);
    app.feed = { note, t: -0.15 - (app.flying.length ? 0.25 : 0), dur: 2.3 };
    placeInSlot(note, 0, 0.2);
    note.mesh.visible = false;
    app.slotNote = note;
    enterMode('printing');
    setLed('rgb(80,220,140)', 3);
    atmosphere.pulse(1);
  }

  function pressRed() {
    if (app.mode !== 'card' || !current()) return;
    app.prevCard = current();
    app.prevN = app.queue.length;
    app.queue.shift();
    enterMode('clearing');
    atmosphere.pulse(0.3);
  }

  function blueDown() {
    if (app.mode !== 'card' && app.mode !== 'empty') return;
    app.blueHeldSince = app.time;
    enterMode('listening');
    setLed('rgb(255,90,90)', 3.5);
    keys.blue.mat.emissiveIntensity = 0.35;
  }
  function blueUp() {
    if (app.mode !== 'listening') return;
    // Even a quick tap shows the listening page long enough to read.
    const wait = Math.max(0, 0.45 - (app.time - app.blueHeldSince));
    app.pending = { at: app.time + wait, fn: () => {
      keys.blue.mat.emissiveIntensity = 0;
      setLed('#000000', 0);
      enterMode('thinking');
      app.pending = { at: app.time + 1.25, fn: () => {
        const card = { ...VOICE_CARDS[app.voiceIdx % VOICE_CARDS.length] };
        app.voiceIdx++;
        app.queue.unshift(card);
        enterMode('card');
      } };
    } };
  }

  function keyDown(name) {
    keys[name].target = 1;
    keys[name].downAt = app.time;
    if (name === 'blue') blueDown();
    if (name === 'green') pressGreen();
    if (name === 'red') pressRed();
    dirty = 3;
  }
  function keyUp(name) {
    const k = keys[name];
    // A click still reads as a full press: hold the travel for a beat.
    const held = app.time - (k.downAt ?? 0);
    k.releaseAt = app.time + Math.max(0, 0.14 - held);
    k.releasing = true;
    if (name === 'blue') blueUp();
    dirty = 3;
  }

  /* --- screen drawing ------------------------------------------------ */
  function drawScreen() {
    screen.begin();
    const t = app.time - app.modeStart;
    switch (app.mode) {
      case 'card':
        if (current()) {
          const intro = Math.min(1, t / 0.24);
          const e = 1 - (1 - intro) ** 3;
          screen.card(current(), app.queue.length, (1 - e) * 26, e);
        } else {
          enterMode('empty');
          screen.empty();
        }
        break;
      case 'clearing': {
        const out = Math.min(1, t / 0.26);
        const e = out * out;
        screen.card(app.prevCard, app.prevN, -e * 340, 1 - e * 0.6);
        if (out >= 1) {
          enterMode('card');
        }
        break;
      }
      case 'printing': {
        const p = app.feed ? Math.min(1, Math.max(0, app.feed.t / app.feed.dur)) : 1;
        screen.printing(p, app.time);
        break;
      }
      case 'listening': screen.listening(app.levels); break;
      case 'thinking': screen.thinking(app.time); break;
      case 'empty': screen.empty(); break;
      default: break;
    }
    screen.end();
  }

  /* --- first impression: one note already sitting in the slot -------- */
  {
    const n = pool[0];
    n.setCard(FIRST_NOTE);
    if (reduceMotion) {
      placeInSlot(n, NOTE.h - 1.5, 1);
    } else {
      // The opening shot: the first note prints as the device comes out of the dark.
      placeInSlot(n, 0, 0.2);
      n.mesh.visible = false;
      app.feed = { note: n, t: -0.9, dur: 1.9, quiet: true };
      app.rollSpeed = 0;
    }
    app.slotNote = n;
  }
  floorShadow.accumulate(floorShadow.dynRT, floorShadow.dynSamples, [notesGroup]);
  drawScreen();

  /* --- pointer handling ---------------------------------------------- */
  const raycaster = new THREE.Raycaster();
  const ndc = new THREE.Vector2();
  const proxies = Object.values(keys).map((k) => k.proxy);
  function pick(ev) {
    const r = canvas.getBoundingClientRect();
    ndc.set(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
    raycaster.setFromCamera(ndc, camera);
    const occluders = [built.bodyMesh, built.bandMesh];
    const slotMesh = app.slotNote && app.slotNote.mesh.visible && app.mode !== 'printing' ? [app.slotNote.mesh] : [];
    const hits = raycaster.intersectObjects([...proxies, ...slotMesh, ...occluders], false);
    if (!hits.length) return null;
    const first = hits[0].object;
    if (first.userData.key) return { key: first.userData.key };
    if (noteOfMesh.has(first)) return { note: noteOfMesh.get(first) };
    return null;
  }

  const activePointers = new Map();
  function markTouched() {
    touched = true;
    idle.on = false;
    idle.lastTouch = performance.now();
  }

  // Capture phase so it runs before OrbitControls and can claim the gesture.
  canvas.addEventListener('pointerdown', (ev) => {
    markTouched();
    const hit = pick(ev);
    if (hit?.key) {
      controls.enabled = false;
      activePointers.set(ev.pointerId, hit.key);
      try { canvas.setPointerCapture(ev.pointerId); } catch (e) { /* synthetic */ }
      keyDown(hit.key);
      ev.preventDefault();
      ev.stopPropagation();
    } else if (hit?.note) {
      tearOff(hit.note);
      dirty = 3;
    }
  }, { capture: true });

  const release = (ev) => {
    const name = activePointers.get(ev.pointerId);
    if (name) {
      activePointers.delete(ev.pointerId);
      keyUp(name);
      if (!activePointers.size) controls.enabled = true;
    }
  };
  window.addEventListener('pointerup', release);
  window.addEventListener('pointercancel', release);
  canvas.addEventListener('lostpointercapture', release);
  window.addEventListener('blur', () => { [...activePointers.keys()].forEach((id) => release({ pointerId: id })); });
  canvas.addEventListener('contextmenu', (e) => e.preventDefault());

  // Hover affordance on mouse devices.
  let hoverKey = null;
  canvas.addEventListener('pointermove', (ev) => {
    if (ev.pointerType !== 'mouse' || ev.buttons) return;
    const hit = pick(ev);
    const next = hit ? (hit.key || 'note') : null;
    if (next !== hoverKey) {
      hoverKey = next;
      canvas.style.cursor = next ? 'pointer' : '';
    }
  });
  controls.addEventListener('start', markTouched);
  controls.addEventListener('change', () => { dirty = Math.max(dirty, 1); });

  // Keyboard and assistive tech drive the same keys through real buttons.
  document.querySelectorAll('[data-key]').forEach((b) => {
    const name = b.dataset.key;
    const down = () => { markTouched(); if (!keys[name].kbd) { keys[name].kbd = true; keyDown(name); } };
    const up = () => { if (keys[name].kbd) { keys[name].kbd = false; keyUp(name); } };
    b.addEventListener('keydown', (e) => { if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); down(); } });
    b.addEventListener('keyup', up);
    b.addEventListener('blur', up);
    b.addEventListener('click', (e) => { if (e.detail !== 0 || keys[name].kbd) return; down(); setTimeout(up, 120); });
  });

  /* --- frame loop ---------------------------------------------------- */
  let lastT = performance.now();
  let renderedLastFrame = false;
  let pixelCap = Math.min(window.devicePixelRatio || 1, 2);
  const perf = { sum: 0, n: 0 };
  const anyAnimating = () => app.mode !== 'card' && app.mode !== 'empty'
    || app.feed || app.flying.length || app.pending || app.time - app.modeStart < 0.3
    || Object.values(keys).some((k) => k.target || Math.abs(k.value) > 0.001 || Math.abs(k.vel) > 0.01);

  let frozen = false; // stills mode pauses the loop

  function tick(dt) {
    app.time += dt;

    if (app.pending && app.time >= app.pending.at) {
      const fn = app.pending.fn;
      app.pending = null;
      fn();
    }

    // Keys: quick down, slightly springy up.
    Object.values(keys).forEach((k) => {
      if (k.releasing && app.time >= k.releaseAt) { k.target = 0; k.releasing = false; }
      const stiff = k.target ? 2600 : 300;
      const damp = k.target ? 80 : 22;
      // Fixed sub-steps keep the spring stable at any frame rate, and the key can
      // never leave its travel range: it bottoms out and tops out like the real part.
      const steps = Math.max(1, Math.ceil(dt * 480));
      const h = dt / steps;
      for (let s = 0; s < steps; s++) {
        k.vel += ((k.target - k.value) * stiff - k.vel * damp) * h;
        k.value += k.vel * h;
        if (k.value > 1) { k.value = 1; k.vel = 0; }
        if (k.value < -0.06) { k.value = -0.06; k.vel = 0; }
      }
      k.cap.position.z = -k.value * KEY.travel;
    });

    // Paper feed
    if (app.feed) {
      const f = app.feed;
      f.t += dt;
      if (f.t > 0) {
        const note = f.note;
        note.mesh.visible = true;
        const p = Math.min(1, f.t / f.dur);
        const ease = p; // the head feeds at constant speed
        const stutter = Math.sin(f.t * 60) * 0.06 * (1 - p);
        const emerged = Math.max(0, ease * (NOTE.h - 1.5) + stutter);
        const curl = Math.min(1, emerged / NOTE.h) ** 1.2;
        note.setShape(emerged, curl);
        note.emerged = emerged;
        note.curl = curl;
        app.rollSpeed = 2.4;
        dynShadowDirty = true;
        if (p >= 1) {
          app.feed = null;
          app.rollSpeed = 0;
          setLed('#000000', 0);
          if (!f.quiet) enterMode('card');
        }
      }
    }
    rollEnd.rotation.z -= app.rollSpeed * dt;

    // Notes in flight down to the desk
    for (let i = app.flying.length - 1; i >= 0; i--) {
      const f = app.flying[i];
      f.t += dt;
      const p = Math.min(1, f.t / f.dur);
      const e = p < 0.5 ? 2 * p * p : 1 - (-2 * p + 2) ** 2 / 2;
      const m = f.note.mesh;
      m.position.lerpVectors(f.fromPos, f.toPos, e);
      // lift clear of the deck before descending
      m.position.y += Math.sin(Math.min(1, p * 1.15) * Math.PI) * 26;
      m.position.z += Math.sin(p * Math.PI) * 6;
      m.quaternion.slerpQuaternions(f.fromQuat, f.toQuat, e);
      f.note.setShape(NOTE.h, f.curl0 * (1 - e));
      dynShadowDirty = true;
      if (p >= 1) {
        f.note.curl = 0;
        app.desk.push(f.note);
        app.flying.splice(i, 1);
      }
    }

    // Queue empty: more mail arrives after a beat, so a demo never dead-ends.
    if (app.mode === 'empty') {
      if (!app.refillAt) app.refillAt = app.time + 7;
      if (app.time > app.refillAt) {
        app.refillAt = 0;
        app.queue = SEED_CARDS.map((c) => ({ ...c }));
        enterMode('card');
      }
    } else app.refillAt = 0;

    // Fake audio levels: a voice-like envelope, not a sine wave.
    if (app.mode === 'listening') {
      const tt = app.time;
      const env = 0.45 + 0.55 * Math.abs(Math.sin(tt * 2.1) * Math.sin(tt * 0.73 + 1.2));
      app.levels = app.levels.map((v, i) => {
        const centre = 1 - Math.abs(i - 4) / 5;
        const n = Math.abs(Math.sin(tt * (5 + i * 1.7) + i * 2.4));
        const tgt = env * (0.3 + 0.7 * n) * (0.45 + 0.55 * centre);
        return v + (tgt - v) * Math.min(1, dt * 18);
      });
      led.material.emissiveIntensity = 2.6 + Math.sin(tt * 7) * 0.9;
      keys.blue.mat.emissiveIntensity = 0.28 + env * 0.12;
    }
  }

  function frame() {
    requestAnimationFrame(frame);
    if (frozen) return;
    const nowT = performance.now();
    const rawDt = (nowT - lastT) / 1000;
    const dt = Math.min(rawDt, 0.2); // animations keep real time on a slow machine
    lastT = nowT;

    // Sustained slow frames: step resolution down rather than let the demo stutter.
    // Moving paper redraws its soft shadow, so it's slow on purpose and doesn't count.
    if (renderedLastFrame && rawDt < 1 && !intro.on && !app.feed && !app.flying.length) {
      perf.sum += rawDt;
      perf.n++;
      if (perf.n >= 12) {
        if (perf.sum / perf.n > 0.055) {
          // Slow machine: the reflection goes first, since it draws the whole model a second time.
          if (mirror.visible) mirror.visible = false;
          else if (pixelCap > 0.75) {
            pixelCap = Math.max(0.75, pixelCap - 0.5);
            renderer.setPixelRatio(pixelCap);
          }
          dirty = Math.max(dirty, 2);
        }
        perf.sum = 0;
        perf.n = 0;
      }
    }
    renderedLastFrame = false;

    tick(dt);

    // The room answers the device: warm surge on print, cold while it listens, a red dip on dismiss.
    const voice = app.mode === 'listening' ? app.levels.reduce((a, b) => a + b, 0) / app.levels.length : 0;
    atmosphere.set({
      energy: app.mode === 'printing' ? 1.32 : app.mode === 'listening' ? 0.82 + voice * 1.15 : app.mode === 'thinking' ? 1.08 : app.mode === 'clearing' ? 0.72 : app.mode === 'empty' ? 0.66 : 1,
      cool: app.mode === 'listening' || app.mode === 'thinking' ? 1 : 0,
      red: app.mode === 'clearing' ? 1 : 0,
    });
    const poolLevel = atmosphere.level() * (1 - atmosphere.red() * 0.45);
    const poolUniforms = lightPool.material.uniforms;
    poolUniforms.uColor.value.setRGB(1 - atmosphere.cool() * 0.6, 0.5 + atmosphere.cool() * 0.24 - atmosphere.red() * 0.3, 0.2 + atmosphere.cool() * 0.8 - atmosphere.red() * 0.04);
    if (Math.abs(poolUniforms.uLevel.value - poolLevel) > 0.002 || atmosphere.cool() > 0.002 || atmosphere.red() > 0.002) dirty = Math.max(dirty, 1);
    poolUniforms.uLevel.value = poolLevel;

    // Opening shot and idle: a slow sway around the hero angle, keeping the display in view.
    if (!touched && idle.on) {
      idle.t += dt;
      let az = idle.base + Math.sin(idle.t * 0.13) * THREE.MathUtils.degToRad(22);
      idle.az = az;
      let dist = distance, pol = idle.pol;
      if (intro.on) {
        intro.t = Math.min(intro.dur, intro.t + dt);
        const e = 1 - (1 - intro.t / intro.dur) ** 4;
        az -= (1 - e) * THREE.MathUtils.degToRad(46);
        pol += (1 - e) * THREE.MathUtils.degToRad(7);
        dist *= 1 + (1 - e) * 0.42;
        if (intro.t >= intro.dur) intro.on = false;
      }
      setCam(az, pol, dist);
      dirty = Math.max(dirty, 1);
    }
    if (touched && performance.now() - idle.lastTouch > 60000 && !reduceMotion) {
      // Left alone for a while: pick the sway back up from wherever the viewer stopped.
      const off = camera.position.clone().sub(controls.target);
      const sph = new THREE.Spherical().setFromVector3(off);
      idle.base = sph.theta; idle.pol = sph.phi; distance = sph.radius;
      idle.t = 0; idle.on = true; touched = false;
    }

    controls.update();

    document.body.classList.toggle('zoomed', camera.position.distanceTo(controls.target) < fitDist * 0.78);
    const animating = anyAnimating();
    if (animating) { drawScreen(); dirty = Math.max(dirty, 1); }
    const dynShadowWasDirty = dynShadowDirty;
    if (dynShadowDirty) {
      floorShadow.accumulate(floorShadow.dynRT, floorShadow.dynSamples, [notesGroup]);
      dynShadowDirty = false;
      dirty = Math.max(dirty, 1);
    }
    if (dirty > 0) {
      // Shadows only change when a key or a note moves, not when the camera does.
      if (animating || dynShadowWasDirty) renderer.shadowMap.needsUpdate = true;
      renderer.render(scene, camera);
      renderedLastFrame = true;
      dirty--;
    }
  }

  window.addEventListener('resize', resize);
  window.addEventListener('orientationchange', resize);
  resize();
  document.body.classList.add('ready');
  requestAnimationFrame(frame);

  /* --- tooling hooks: stills and GLB export ---------------------------- */
  function advance(seconds, step = 1 / 60) {
    for (let t = 0; t < seconds; t += step) tick(step);
    drawScreen();
    floorShadow.accumulate(floorShadow.dynRT, floorShadow.dynSamples, [notesGroup]);
    dirty = 3;
  }

  // Accumulates many jittered frames: true anti-aliasing, a soft key light, optional lens blur.
  async function renderStill(o) {
    frozen = true;
    const w = o.w, h = o.h;
    const samples = o.samples ?? 96;
    renderer.setPixelRatio(1);
    renderer.setSize(w, h, false);
    const cam = camera.clone();
    cam.fov = o.fov ?? camera.fov;
    cam.aspect = w / h;
    cam.near = 40; cam.far = 6000;
    const az = THREE.MathUtils.degToRad(o.az), pol = THREE.MathUtils.degToRad(90 - o.el);
    const tgt = new THREE.Vector3(...(o.target ?? [0, 62, 4]));
    const camPos = new THREE.Vector3(
      tgt.x + o.dist * Math.sin(pol) * Math.sin(az),
      tgt.y + o.dist * Math.cos(pol),
      tgt.z + o.dist * Math.sin(pol) * Math.cos(az),
    );
    const gl = renderer.getContext();
    const acc = new Float32Array(w * h * 3);
    const px = new Uint8Array(w * h * 4);
    const lut = new Float32Array(256);
    for (let i = 0; i < 256; i++) { const c = i / 255; lut[i] = c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; }

    const focus = o.focusDist ?? o.dist;
    const aperture = o.aperture ?? 0;
    const keyBase = key.position.clone();
    const hs = hammersleySamples(samples);
    const axisA = new THREE.Vector3().crossVectors(KEY_DIR, new THREE.Vector3(0, 0, 1)).normalize();
    const axisB = new THREE.Vector3().crossVectors(KEY_DIR, axisA).normalize();
    for (let s = 0; s < samples; s++) {
      const [u, v] = hs[s];
      const r = Math.sqrt(u), a = v * Math.PI * 2 * 7.3;
      // light: walk over the softbox area
      key.position.copy(keyBase)
        .addScaledVector(axisA, Math.cos(a) * r * 130)
        .addScaledVector(axisB, Math.sin(a) * r * 130);
      // lens
      const lr = Math.sqrt(((s * 0.618034) % 1)) * aperture;
      const la = ((s * 0.754877) % 1) * Math.PI * 2;
      const dx = Math.cos(la) * lr, dy = Math.sin(la) * lr;
      cam.position.copy(camPos);
      cam.up.set(0, 1, 0);
      cam.lookAt(tgt);
      cam.updateMatrixWorld();
      const right = new THREE.Vector3().setFromMatrixColumn(cam.matrixWorld, 0);
      const upv = new THREE.Vector3().setFromMatrixColumn(cam.matrixWorld, 1);
      cam.position.addScaledVector(right, dx).addScaledVector(upv, dy);
      cam.updateMatrixWorld();
      cam.updateProjectionMatrix();
      const P = cam.projectionMatrix.elements;
      const jx = ((s * 0.5698403) % 1 - 0.5) * 2 / w;
      const jy = ((s * 0.8191725) % 1 - 0.5) * 2 / h;
      P[8] = -P[0] * dx / focus + jx;
      P[9] = -P[5] * dy / focus + jy;
      cam.projectionMatrixInverse.copy(cam.projectionMatrix).invert();
      renderer.shadowMap.needsUpdate = true;
      renderer.render(scene, cam);
      gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, px);
      for (let i = 0, j = 0; i < px.length; i += 4, j += 3) {
        acc[j] += lut[px[i]]; acc[j + 1] += lut[px[i + 1]]; acc[j + 2] += lut[px[i + 2]];
      }
      if (s % 8 === 7) await new Promise((res) => setTimeout(res, 0));
    }
    key.position.copy(keyBase);
    const out = canvasOf(w, h);
    const ctx = out.getContext('2d');
    const img = ctx.createImageData(w, h);
    const enc = (x) => {
      const c = x <= 0.0031308 ? x * 12.92 : 1.055 * x ** (1 / 2.4) - 0.055;
      return Math.max(0, Math.min(255, c * 255 + (Math.random() - 0.5)));
    };
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const src = (y * w + x) * 3;
        const dst = ((h - 1 - y) * w + x) * 4;
        img.data[dst] = enc(acc[src] / samples);
        img.data[dst + 1] = enc(acc[src + 1] / samples);
        img.data[dst + 2] = enc(acc[src + 2] / samples);
        img.data[dst + 3] = 255;
      }
    }
    ctx.putImageData(img, 0, 0);
    const url = out.toDataURL('image/png');
    return url;
  }

  function resumeFromStill() {
    frozen = false;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    lastSize = '';
    resize();
  }

  async function exportGLB() {
    // Clean, viewer-friendly snapshot of the device with a note in the slot.
    const root = new THREE.Group();
    root.name = 'Prins';
    root.scale.setScalar(0.001);
    const clone = product.clone(true);
    const drop = [];
    clone.traverse((o) => { if (o.userData?.noExport) drop.push(o); });
    drop.forEach((o) => o.parent.remove(o));
    clone.traverse((o) => {
      if (o.isMesh && o.material === mats.windowGlass) {
        o.material = new THREE.MeshPhysicalMaterial({ name: 'Roll window', color: 0x111111, roughness: 0.05, transparent: true, opacity: 0.16 });
      }
    });
    root.add(clone);
    if (app.slotNote && app.slotNote.mesh.visible) root.add(app.slotNote.mesh.clone());
    const exporter = new GLTFExporter();
    const buf = await new Promise((res, rej) => exporter.parse(root, res, rej, { binary: true, maxTextureSize: 2048 }));
    let bin = '';
    const bytes = new Uint8Array(buf);
    for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    return btoa(bin);
  }

  function keyScreenPos(name) {
    const p = new THREE.Vector3();
    keys[name].cap.getWorldPosition(p);
    p.addScaledVector(built.frames.shelf.n, KEY.proud);
    p.project(camera);
    return { x: (p.x * 0.5 + 0.5) * window.innerWidth, y: (-p.y * 0.5 + 0.5) * window.innerHeight };
  }
  function noteScreenPos() {
    if (!app.slotNote) return null;
    const p = app.slotNote.mesh.localToWorld(new THREE.Vector3(0, NOTE.h * 0.5, 0)).project(camera);
    return { x: (p.x * 0.5 + 0.5) * window.innerWidth, y: (-p.y * 0.5 + 0.5) * window.innerHeight };
  }

  window.__prins = {
    built, mats, THREE,
    app, keys, renderer, scene, camera, controls, screen, product, advance, renderStill, resumeFromStill, exportGLB,
    keyScreenPos, noteScreenPos, keyDown, keyUp, markTouched,
    freeze: (v) => { frozen = v; },
    badge: () => app.queue.length,
    setView: (azDeg, elDeg, dist) => {
      markTouched();
      setCam(THREE.MathUtils.degToRad(azDeg), THREE.MathUtils.degToRad(90 - elDeg), dist);
      controls.update();
      dirty = 3;
    },
    render: () => { renderer.render(scene, camera); },
    distance: () => camera.position.distanceTo(controls.target),
    info: () => ({ calls: renderer.info.render.calls, tris: renderer.info.render.triangles }),
    screenPNG: () => screen.canvas.toDataURL('image/png'),
  };
}

main();
