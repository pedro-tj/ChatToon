// Gata — orange cartoon cat (original procedural model). Premium vinyl-toy look after the
// reference: a big round head with enormous glossy amber eyes, tall triangular ears with
// rosy insides, a small pink nose over a "ω" mouth, thin whiskers, a small sitting body
// with round toe paws and a long striped tail that moves on a chain of springs.
import * as THREE from "../../vendor/three/three.module.js";
import { Character, Spring, clamp01, damp, smooth } from "../rig.js";
import { boneChain, latheBody, profile, skinByHeight } from "./shapes.js";

const FUR = 0xf07812;
const HEAD_PIVOT = 0.15; // head pivot above the neck bone (world ≈ 1.15)
const HEAD_UP = 0.4; // head centre above the pivot (world ≈ 1.55)
const TAIL_BONES = 10;
const TAIL_LEN = 1.24;
const L1 = 0.272, L2 = 0.246; // front leg: upper / lower

const lerp = THREE.MathUtils.lerp;
const bump = (p, a, b) => smooth(a, a + (b - a) * 0.35, p) * (1 - smooth(b - (b - a) * 0.35, b, p));

// ------------------------------------------------------------------ helpers
// Paint a texture from a function of (u, v) → linear colour (procedural, no images).
function paint(w, h, fn) {
  const c = document.createElement("canvas");
  c.width = w; c.height = h;
  const g = c.getContext("2d");
  const img = g.createImageData(w, h);
  const col = new THREE.Color();
  for (let py = 0; py < h; py++) {
    const v = 1 - (py + 0.5) / h;
    for (let px = 0; px < w; px++) {
      fn((px + 0.5) / w, v, col);
      const o = (py * w + px) * 4;
      img.data[o] = Math.round(Math.pow(clamp01(col.r), 1 / 2.2) * 255);
      img.data[o + 1] = Math.round(Math.pow(clamp01(col.g), 1 / 2.2) * 255);
      img.data[o + 2] = Math.round(Math.pow(clamp01(col.b), 1 / 2.2) * 255);
      img.data[o + 3] = 255;
    }
  }
  g.putImageData(img, 0, 0);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  return tex;
}

const mixc = (col, other, a) => {
  if (a <= 0) return;
  col.r += (other.r - col.r) * a; col.g += (other.g - col.g) * a; col.b += (other.b - col.b) * a;
};

// Distance to a tapered segment (capsule whose radius goes ra → rb), 2D.
function sdTaper(px, py, ax, ay, bx, by, ra, rb) {
  const dx = bx - ax, dy = by - ay;
  const t = clamp01(((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy));
  return Math.hypot(px - ax - dx * t, py - ay - dy * t) - lerp(ra, rb, t);
}

// Concatenate indexed geometries (position + normal) into one.
function merge(geos) {
  let nv = 0, ni = 0;
  for (const g of geos) { nv += g.attributes.position.count; ni += g.index.count; }
  const pos = new Float32Array(nv * 3), nor = new Float32Array(nv * 3), idx = new Uint32Array(ni);
  let vo = 0, io = 0;
  for (const g of geos) {
    pos.set(g.attributes.position.array, vo * 3);
    nor.set(g.attributes.normal.array, vo * 3);
    const src = g.index.array;
    for (let i = 0; i < src.length; i++) idx[io + i] = src[i] + vo;
    vo += g.attributes.position.count; io += src.length;
    g.dispose();
  }
  const out = new THREE.BufferGeometry();
  out.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  out.setAttribute("normal", new THREE.BufferAttribute(nor, 3));
  out.setIndex(new THREE.BufferAttribute(idx, 1));
  return out;
}

// Average the normals of coincident vertices (UV seams, poles): no visible seam lines.
function weldNormals(g) {
  const pos = g.attributes.position, nor = g.attributes.normal;
  const map = new Map();
  const key = (i) => `${Math.round(pos.getX(i) * 1e4)},${Math.round(pos.getY(i) * 1e4)},${Math.round(pos.getZ(i) * 1e4)}`;
  for (let i = 0; i < pos.count; i++) {
    const k = key(i);
    if (!map.has(k)) map.set(k, []);
    map.get(k).push(i);
  }
  const n = new THREE.Vector3(), m = new THREE.Vector3();
  for (const list of map.values()) {
    if (list.length < 2) continue;
    n.set(0, 0, 0);
    for (const i of list) n.add(m.fromBufferAttribute(nor, i));
    n.normalize();
    for (const i of list) nor.setXYZ(i, n.x, n.y, n.z);
  }
}

// ------------------------------------------------------------------ head shape
// Unit sphere → cartoon cat head: wide cheeks, softly flattened crown, a hint of muzzle.
function headShape(x, y, z, out) {
  const cheek = Math.exp(-(((y + 0.4) / 0.48) ** 2));
  const top = Math.max(0, y);
  let Y = y * 0.575;
  if (y > 0) Y *= 1 - 0.07 * y * y;
  if (y < -0.5) Y += (y + 0.5) * -0.22 * 0.575; // broad, softly flattened jaw
  const front = Math.max(0, z);
  const muzzle = front ** 3 * Math.exp(-(((y + 0.5) / 0.22) ** 2)) * Math.exp(-((x / 0.32) ** 2));
  const brow = front ** 2 * Math.exp(-(((y - 0.05) / 0.3) ** 2));
  const sx = 0.61 * (1 + 0.14 * cheek + 0.16 * top * (1 - top));
  out.set(x * sx, Y, z * 0.56 * (1 + 0.05 * cheek) + muzzle * 0.05 - brow * 0.015);
  return out;
}

// Height map of the face (z of the head surface at x, y, head-local) for placing features.
class FaceSurface {
  constructor(n = 112) {
    this.n = n; this.x0 = -0.75; this.x1 = 0.75; this.y0 = -0.65; this.y1 = 0.65;
    const z = new Float32Array(n * n).fill(-1);
    const p = new THREE.Vector3();
    const S = 520;
    for (let i = 0; i <= S; i++) {
      const lat = -Math.PI / 2 + Math.PI * i / S;
      for (let j = 0; j <= S; j++) {
        const lon = -Math.PI / 2 + Math.PI * j / S;
        headShape(Math.sin(lon) * Math.cos(lat), Math.sin(lat), Math.cos(lon) * Math.cos(lat), p);
        const gx = Math.round((p.x - this.x0) / (this.x1 - this.x0) * (n - 1));
        const gy = Math.round((p.y - this.y0) / (this.y1 - this.y0) * (n - 1));
        if (gx < 0 || gy < 0 || gx >= n || gy >= n) continue;
        const k = gy * n + gx;
        if (p.z > z[k]) z[k] = p.z;
      }
    }
    this.data = z;
  }

  z(x, y) {
    const n = this.n;
    const fx = clamp01((x - this.x0) / (this.x1 - this.x0)) * (n - 1);
    const fy = clamp01((y - this.y0) / (this.y1 - this.y0)) * (n - 1);
    const ix = Math.min(n - 2, Math.floor(fx)), iy = Math.min(n - 2, Math.floor(fy));
    const tx = fx - ix, ty = fy - iy, d = this.data;
    const a = d[iy * n + ix], b = d[iy * n + ix + 1], c = d[(iy + 1) * n + ix], e = d[(iy + 1) * n + ix + 1];
    return lerp(lerp(a, b, tx), lerp(c, e, tx), ty);
  }
}

// ------------------------------------------------------------------ eyes
// Iris + pupil are painted in the eyeball's shader, so the pupil can dilate or narrow to
// a slit (cats!) without extra meshes. Shared uniforms: both eyes react together.
function eyeMaterial(uniforms) {
  const m = new THREE.MeshPhysicalMaterial({ color: 0xffffff, roughness: 0.16, clearcoat: 1, clearcoatRoughness: 0.03 });
  m.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, uniforms);
    shader.vertexShader = shader.vertexShader
      .replace("#include <common>", "#include <common>\nvarying vec3 vEyeP;")
      .replace("#include <begin_vertex>", "#include <begin_vertex>\nvEyeP = position;");
    shader.fragmentShader = shader.fragmentShader
      .replace("#include <common>", `#include <common>
varying vec3 vEyeP;
uniform float pupilR; uniform vec2 pupilShape; uniform float irisR;
uniform vec3 irisInner; uniform vec3 irisOuter; uniform vec3 irisRing; uniform vec3 irisLight; uniform vec3 sclera;`)
      .replace("#include <color_fragment>", `#include <color_fragment>
{
  vec3 e = normalize(vEyeP);
  vec2 p = e.xy;
  float r = e.z > 0.0 ? length(p) : 2.0;
  float aa = fwidth(r) * 1.3 + 0.003;
  float irisM = 1.0 - smoothstep(irisR - aa, irisR + aa, r);
  float t = r / irisR;
  vec3 col = mix(irisInner, irisOuter, smoothstep(0.25, 0.95, t));
  float low = smoothstep(0.15, -0.85, p.y / irisR);
  col = mix(col, irisLight, low * 0.75 * (1.0 - smoothstep(0.7, 1.0, t)));
  col = mix(col, irisRing, smoothstep(0.8, 1.0, t));
  float ang = atan(p.y, p.x);
  col *= 0.9 + 0.1 * sin(ang * 21.0 + sin(ang * 5.0) * 2.0) * smoothstep(0.3, 0.7, t);
  float pr = length(vec2(p.x / pupilShape.x, p.y / pupilShape.y));
  float pupilM = 1.0 - smoothstep(pupilR - aa * 1.4, pupilR + aa * 1.4, pr);
  vec3 sc = sclera;
  diffuseColor.rgb = mix(sc, col, irisM);
  diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.018, 0.009, 0.006), pupilM);
}`);
  };
  m.customProgramCacheKey = () => "cat-eye";
  return m;
}

function lashGeometry(r, q) {
  const arc = Math.PI * 1.08;
  const t = new THREE.TorusGeometry(r, r * 0.034, [5, 6, 8][q], [16, 24, 36][q], arc);
  t.scale(1, 1, 1.6); // flatter band, thicker in depth
  t.rotateZ(Math.PI / 2 - arc / 2);
  t.rotateX(Math.PI / 2); // into the lid rim plane (xz), centred on +z
  // outer flick (+x side; mirrored for the other eye)
  const a = Math.PI / 2 + 0.12; // angle from +z towards +x
  const cone = new THREE.ConeGeometry(r * 0.05, r * 0.36, [5, 6, 8][q], 1);
  cone.translate(0, r * 0.18, 0);
  const dir = new THREE.Vector3(Math.cos(a) * 0.45 + Math.sin(a) * 0.75, 0.45, -Math.sin(a) * 0.45 + Math.cos(a) * 0.75).normalize();
  cone.applyQuaternion(new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir));
  cone.translate(Math.sin(a) * r * 0.98, 0, Math.cos(a) * r * 0.98);
  // two finer lashes just inside the corner
  const extra = [0.78, 0.98].map((b, k) => {
    const c = new THREE.ConeGeometry(r * 0.03, r * (0.22 - k * 0.04), [4, 5, 6][q], 1);
    c.translate(0, r * 0.1, 0);
    const d = new THREE.Vector3(Math.sin(b) * 0.8, 0.6, Math.cos(b) * 0.8).normalize();
    c.applyQuaternion(new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), d));
    c.translate(Math.sin(b) * r, 0, Math.cos(b) * r);
    return c;
  });
  return merge([t, cone, ...extra]);
}

class CatEye {
  constructor({ radius, mat, lidMat, lashMat, lashGeo, shineMat, side, quality }) {
    const seg = [18, 28, 44][quality];
    this.radius = radius;
    this.group = new THREE.Group();
    this.ball = new THREE.Group();
    this.group.add(this.ball);
    this.ball.add(new THREE.Mesh(new THREE.SphereGeometry(radius, seg, Math.round(seg * 0.75)), mat));
    const shine = new THREE.Mesh(new THREE.SphereGeometry(radius * 0.17, 12, 8), shineMat);
    shine.scale.set(1, 1.25, 0.35);
    shine.position.set(radius * 0.34, radius * 0.36, radius * 0.86);
    const shine2 = new THREE.Mesh(shine.geometry, shineMat);
    shine2.scale.set(0.42, 0.42, 0.2);
    shine2.position.set(-radius * 0.3, -radius * 0.38, radius * 0.86);
    this.group.add(shine, shine2);
    this.shines = [shine, shine2];
    this.upper = new THREE.Mesh(new THREE.SphereGeometry(radius * 1.035, seg, seg / 2, 0, Math.PI * 2, 0, Math.PI / 2), lidMat);
    this.lower = new THREE.Mesh(new THREE.SphereGeometry(radius * 1.03, seg, seg / 2, 0, Math.PI * 2, Math.PI / 2, Math.PI / 2), lidMat);
    const lash = new THREE.Mesh(lashGeo, lashMat);
    lash.scale.x = side;
    this.upper.add(lash);
    this.group.add(this.upper, this.lower);
    this.force = 0; // extra closure from gestures (slow blink, grooming)
    this.squint = 0; // extra lower lid
    this.extraTilt = 0;
    this.gy = 0;
  }

  setLids(upper, lower, tilt = 0) {
    // the upper lid follows the gaze a little: looking up lifts it, looking down lowers it
    let u = clamp01(Math.max(upper - this.gy * 0.28, this.force)), l = clamp01(lower + this.squint);
    // a big cheek squeeze (laughing) shuts the eyes into a soft closed line instead of
    // pushing a flat lower lid over the iris
    u = Math.max(u, smooth(0.5, 0.72, l));
    // the lids meet below the centre: a closed eye reads as a curved lash line "‿"
    const meet = 0.46;
    l = Math.max(Math.min(l, meet), smooth(0.55, 1, u) * meet);
    this.upper.rotation.set(lerp(-1.12, 0.58, Math.pow(u, 0.8)), 0, (tilt + this.extraTilt) * (1 - u * 0.7));
    this.lower.rotation.set(lerp(1.22, -0.18, l), 0, 0);
    this.shines[0].visible = u < 0.4;
    this.shines[1].visible = u < 0.85 && l < 0.5;
  }

  look(x, y) { this.gy = y; this.ball.rotation.set(-y * 0.38, x * 0.5, 0); }
}

// ------------------------------------------------------------------ mouth
// Cat "ω" mouth drawn on the face surface: a philtrum line from the nose splitting into
// two arcs; opening reveals a dark mouth with a tongue below the arcs. Vertices are
// recomputed every frame (a few dozen) and projected on the curved face.
class CatMouth {
  constructor(surface, cx, cy, quality, colors) {
    this.s = surface; this.cx = cx; this.cy = cy; this.z0 = surface.z(cx, cy);
    const N = [8, 11, 15][quality];
    this.n = 2 * N + 1;
    this.nt = N + 1; // tongue samples
    this.group = new THREE.Group();
    this.group.position.set(cx, cy, this.z0);
    const n = this.n;
    this.ux = new Float32Array(n); this.uy = new Float32Array(n);
    this.bx = new Float32Array(n); this.by = new Float32Array(n);
    this.px = new Float32Array([0, 0, 0]); this.py = new Float32Array([0.06, 0.03, 0]);
    const strip = (count) => {
      const idx = [];
      for (let k = 0; k < count - 1; k++) { const a = k * 2; idx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2); }
      return idx;
    };
    const mk = (verts, idx, color, order) => {
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(verts * 3), 3));
      g.setIndex(idx);
      const m = new THREE.Mesh(g, new THREE.MeshBasicMaterial({ color, polygonOffset: true, polygonOffsetFactor: -1 - order, polygonOffsetUnits: -4 - order * 2 }));
      m.renderOrder = order;
      m.frustumCulled = false;
      this.group.add(m);
      return m;
    };
    // lines: philtrum (3 pts) + upper arcs (n) + lower lip (n)
    const lineIdx = [];
    const offs = [0, 3, 3 + n];
    const cnts = [3, n, n];
    offs.forEach((o, i) => strip(cnts[i]).forEach((v) => lineIdx.push(v + o * 2)));
    this.lines = mk((3 + 2 * n) * 2, lineIdx, colors.line, 3);
    this.inner = mk(n * 2, strip(n), colors.inner, 1);
    this.tongue = mk(this.nt * 2, strip(this.nt), colors.tongue, 2);
    // 3D tongue for grooming licks
    this.lickTongue = new THREE.Mesh(new THREE.SphereGeometry(1, 14, 10),
      new THREE.MeshPhysicalMaterial({ color: colors.tongue, roughness: 0.35, clearcoat: 0.6 }));
    this.lickTongue.visible = false;
    this.group.add(this.lickTongue);
    this.meow = 0; this.lick = 0;
    this.open = 0;
  }

  _ribbon(arr, vo, xs, ys, count, th, off) {
    for (let k = 0; k < count; k++) {
      const a = Math.max(0, k - 1), b = Math.min(count - 1, k + 1);
      let tx = xs[b] - xs[a], ty = ys[b] - ys[a];
      const l = Math.hypot(tx, ty) || 1;
      tx /= l; ty /= l;
      const nx = -ty * th * 0.5, ny = tx * th * 0.5;
      for (let s = 0; s < 2; s++) {
        const sg = s ? -1 : 1;
        const x = xs[k] + nx * sg, y = ys[k] + ny * sg;
        const i = (vo + k * 2 + s) * 3;
        arr[i] = x; arr[i + 1] = y; arr[i + 2] = this.s.z(this.cx + x, this.cy + y) - this.z0 + off;
      }
    }
  }

  set({ open, smile, frown, round }) {
    const meow = this.meow, lick = this.lick;
    open = Math.max(open, meow * 0.85, lick * 0.32);
    round = Math.max(round * 0.7, meow * 0.55);
    smile = smile * (1 - meow);
    this.open = open;
    const n = this.n, N = (n - 1) / 2;
    const W = 0.092 * (1 + 0.24 * smile - 0.28 * round - 0.08 * frown + 0.06 * open);
    const h = 0.026 * (0.55 + 0.6 * smile) * (1 - 0.35 * round) - 0.042 * frown;
    const corner = 0.012 * smile - 0.016 * frown + 0.008 * meow;
    const depth = open * 0.12 * (1 + 0.3 * round);
    const pw = 0.6 + 1.2 * (1 - round); // bottom curve: rounder when "O"
    for (let k = 0; k < n; k++) {
      const s = (k - N) / N, a = Math.abs(s);
      const x = s * W;
      const y = -h * Math.sin(Math.PI * a) + corner * a * a + open * 0.008 * (1 - a * a);
      this.ux[k] = x; this.uy[k] = y;
      this.bx[k] = x * (1 - 0.12 * open);
      this.by[k] = y - depth * Math.pow(Math.max(0, 1 - a * a), 1 / pw);
    }
    const lp = this.lines.geometry.attributes.position;
    this.py[2] = this.uy[N];
    this._ribbon(lp.array, 0, this.px, this.py, 3, 0.0085, 0.006);
    this._ribbon(lp.array, 3 * 2, this.ux, this.uy, n, 0.0092, 0.006);
    // lower lip line only while open
    const lt = 0.0065 * smooth(0.02, 0.12, open);
    this._ribbon(lp.array, (3 + n) * 2, this.bx, this.by, n, lt, 0.006);
    lp.needsUpdate = true;
    const ip = this.inner.geometry.attributes.position.array;
    for (let k = 0; k < n; k++) {
      const i = k * 6;
      ip[i] = this.ux[k]; ip[i + 1] = this.uy[k]; ip[i + 2] = this.s.z(this.cx + ip[i], this.cy + ip[i + 1]) - this.z0 + 0.004;
      ip[i + 3] = this.bx[k]; ip[i + 4] = this.by[k]; ip[i + 5] = this.s.z(this.cx + ip[i + 3], this.cy + ip[i + 4]) - this.z0 + 0.004;
    }
    this.inner.geometry.attributes.position.needsUpdate = true;
    this.inner.visible = open > 0.015;
    // tongue: a pink mound resting on the bottom of the open mouth
    const tH = Math.min(depth * 0.45, 0.04);
    const tp = this.tongue.geometry.attributes.position.array;
    const nt = this.nt;
    for (let k = 0; k < nt; k++) {
      const s = (k / (nt - 1) * 2 - 1) * 0.62;
      const kk = Math.round((s + 1) / 2 * (n - 1));
      const x = this.bx[kk] * 0.92, yb = this.by[kk] + 0.002;
      const yt = Math.min(this.uy[kk] - 0.006, yb + tH * Math.sqrt(Math.max(0, 1 - (s / 0.62) ** 2)));
      const i = k * 6;
      tp[i] = x; tp[i + 1] = yt; tp[i + 2] = this.s.z(this.cx + x, this.cy + yt) - this.z0 + 0.005;
      tp[i + 3] = x; tp[i + 4] = yb; tp[i + 5] = this.s.z(this.cx + x, this.cy + yb) - this.z0 + 0.005;
    }
    this.tongue.geometry.attributes.position.needsUpdate = true;
    this.tongue.visible = open > 0.12;
    // grooming lick: a little 3D tongue slides out
    this.lickTongue.visible = lick > 0.03;
    if (this.lickTongue.visible) {
      this.lickTongue.scale.set(0.032, 0.022 + lick * 0.012, 0.03);
      this.lickTongue.position.set(0, this.uy[N] - 0.03 - lick * 0.028, 0.01 + lick * 0.03);
    }
  }
}

// ------------------------------------------------------------------ parts
function earGeometry(q, fur, inner) {
  const seg = [16, 24, 36][q], rows = [8, 12, 18][q];
  const W = 0.29, D = 0.11, H = 0.45;
  const pos = [], col = [], idx = [];
  const c = new THREE.Color();
  for (let j = 0; j <= rows; j++) {
    const v = j / rows;
    const w = W * Math.pow(1 - v, 0.82) * (1 + 0.12 * Math.sin(Math.PI * v));
    const d = D * Math.pow(1 - v, 0.9) + 0.004;
    for (let i = 0; i <= seg; i++) {
      const u = i / seg * Math.PI * 2;
      const cu = Math.cos(u), su = Math.sin(u);
      const x = w * su;
      const z = cu > 0 ? d * (0.35 * cu - 0.62 * cu * cu) + d * 0.1 : d * cu * 1.05 + d * 0.1 * (1 + cu);
      pos.push(x, v * H, z);
      const pink = smooth(0.3, 0.6, cu) * smooth(0.04, 0.16, v) * (1 - smooth(0.74, 0.92, v));
      c.copy(fur);
      mixc(c, inner, pink);
      col.push(c.r, c.g, c.b);
    }
  }
  for (let j = 0; j < rows; j++) {
    for (let i = 0; i < seg; i++) {
      const a = j * (seg + 1) + i, b = a + seg + 1;
      idx.push(a, b, a + 1, b, b + 1, a + 1);
    }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute("color", new THREE.Float32BufferAttribute(col, 3));
  g.setIndex(idx);
  g.computeVertexNormals();
  weldNormals(g);
  return g;
}

// Tapered limb along -y from 0 to -len, rounded at both ends (radius rTop → rBot).
function limbGeometry(rTop, rBot, len, seg, q, rows = 4) {
  const pts = [];
  const n = [6, 8, 10][q];
  for (let i = 0; i <= n; i++) { const a = (i / n) * Math.PI / 2; pts.push([rBot * Math.sin(a), -len - rBot * Math.cos(a)]); }
  for (let i = 1; i < rows; i++) { const t = i / rows; pts.push([lerp(rBot, rTop, Math.pow(t, 1.6)), -len + len * t]); }
  for (let i = 0; i <= n; i++) { const a = Math.PI / 2 - (i / n) * Math.PI / 2; pts.push([rTop * Math.sin(a), rTop * Math.cos(a)]); }
  const g = new THREE.LatheGeometry(pts.map(([r, y]) => new THREE.Vector2(Math.max(0, r), y)), seg);
  g.computeVertexNormals();
  weldNormals(g);
  return g;
}

// Round paw with three toe bumps at the front and a flat sole.
function pawGeometry(q, sx, sy, sz) {
  const seg = [14, 20, 30][q];
  const flat = (g, k) => {
    const p = g.attributes.position;
    for (let i = 0; i < p.count; i++) {
      let y = p.getY(i);
      if (y < -0.45 * k) y = -0.45 * k + (y + 0.45 * k) * 0.35;
      p.setY(i, y);
    }
  };
  // palm: a soft flattened dome
  const palm = new THREE.SphereGeometry(1, seg, Math.round(seg * 0.7));
  flat(palm, 1);
  palm.scale(sx, sy, sz * 0.9);
  palm.translate(0, 0, -sz * 0.08);
  // three round toes along the front, slightly overlapping: the creases read as toes
  const toes = [-1, 0, 1].map((k) => {
    const t = new THREE.SphereGeometry(1, Math.round(seg * 0.6), Math.round(seg * 0.45));
    flat(t, 1);
    t.scale(sx * 0.4, sy * 0.78, sz * 0.38);
    t.translate(k * sx * 0.58, -sy * 0.2, sz * (0.58 - Math.abs(k) * 0.1));
    return t;
  });
  const g = merge([palm, ...toes]);
  g.computeVertexNormals();
  weldNormals(g);
  return g;
}

// ------------------------------------------------------------------ the cat
export class Cat extends Character {
  constructor(options) {
    super(options);
    const q = this.quality;
    const seg = [26, 40, 60][q];
    this.headHeight = 2.4;
    this.extent = { width: 1.55, height: 2.35 };

    const fur = new THREE.Color(options.color || FUR);
    const hsl = {};
    fur.getHSL(hsl);
    const dark = new THREE.Color().setHSL(hsl.h - 0.012, Math.min(1, hsl.s * 1.05), hsl.l * 0.62);
    const cream = fur.clone().lerp(new THREE.Color(0xffc887), 0.5);
    const light = fur.clone().lerp(new THREE.Color(0xffb560), 0.3);
    this.colors = { fur, dark, cream };
    const furParams = { roughness: 0.56, metalness: 0, clearcoat: 0.22, clearcoatRoughness: 0.5,
      sheen: 0.4, sheenRoughness: 0.45, sheenColor: new THREE.Color(0xffa050), envMapIntensity: 0.75 };
    const furMat = new THREE.MeshPhysicalMaterial({ color: fur, ...furParams });
    this.furMat = furMat;

    this.body = new THREE.Group();
    this.body.scale.setScalar(1.08);
    this.root.add(this.body);

    // --- body: a small sitting pear, skinned to hips → chest → neck -------------------
    const pts = profile([[0.0, 0.0], [0.24, 0.012], [0.34, 0.065], [0.375, 0.17], [0.37, 0.3], [0.345, 0.43],
      [0.325, 0.56], [0.315, 0.7], [0.295, 0.81], [0.255, 0.9], [0.15, 0.98], [0.0, 1.01]].map(([r, y]) => [r, y * 0.8]), 56);
    this.pts = pts;
    const bodyGeo = latheBody(pts, { segments: seg, depth: 0.8, front: 0.95 });
    const bodyMap = paint([128, 256, 512][q], [128, 256, 512][q], (u, v, col) => {
      const lon = (u - 0.5) * Math.PI * 2;
      const y = pts[Math.round(v * (pts.length - 1))].y / 0.72;
      col.copy(fur);
      // cream chest/belly, soft edges
      const chest = Math.hypot(lon / 0.62, (y - 0.62) / 0.42);
      mixc(col, cream, (1 - smooth(0.55, 1.05, chest)) * 0.85);
      // subtle tabby bands on the back
      const back = smooth(1.6, 2.6, Math.abs(lon));
      const band = Math.abs(((y * 6.5) % 1) - 0.5) < 0.13 ? 1 : 0;
      mixc(col, dark, back * band * 0.35 * smooth(0.25, 0.4, y) * (1 - smooth(0.85, 0.95, y)));
    });
    const bodyMat = new THREE.MeshPhysicalMaterial({ map: bodyMap, ...furParams });
    this.bones = boneChain([0, 0.36, 0.72]);
    skinByHeight(bodyGeo, [
      (y) => 1 - smooth(0.14, 0.5, y),
      (y) => smooth(0.14, 0.5, y) * (1 - smooth(0.59, 0.74, y)),
      (y) => smooth(0.14, 0.5, y) * smooth(0.59, 0.74, y),
    ]);
    const skinned = new THREE.SkinnedMesh(bodyGeo, bodyMat);
    skinned.add(this.bones[0]);
    skinned.bind(new THREE.Skeleton(this.bones));
    skinned.frustumCulled = false;
    this.body.add(skinned);
    const [hips, chest, neck] = this.bones;
    this.hips = hips; this.chest = chest; this.neck = neck;

    // haunches + hind paws (on the hips: they stay planted)
    const haunchGeo = new THREE.SphereGeometry(1, seg / 2, Math.round(seg * 0.4));
    const hindPawGeo = pawGeometry(q, 0.105, 0.072, 0.15);
    for (const side of [-1, 1]) {
      const h = new THREE.Mesh(haunchGeo, furMat);
      h.scale.set(0.19, 0.19, 0.29);
      h.position.set(side * 0.26, 0.17, -0.03);
      h.rotation.set(-0.25, 0, side * 0.12);
      hips.add(h);
      const hp = new THREE.Mesh(hindPawGeo, furMat);
      hp.position.set(side * 0.3, 0.05, 0.17);
      hp.rotation.y = side * 0.18;
      hips.add(hp);
    }

    // --- head ------------------------------------------------------------------------
    this.headPivot = new THREE.Group();
    this.headPivot.position.set(0, HEAD_PIVOT, 0.04);
    neck.add(this.headPivot);
    const hseg = [32, 48, 72][q];
    const headGeo = new THREE.SphereGeometry(1, hseg, Math.round(hseg * 0.75), Math.PI * 1.5);
    const hp = headGeo.attributes.position;
    const tmp = new THREE.Vector3();
    for (let i = 0; i < hp.count; i++) {
      headShape(hp.getX(i), hp.getY(i), hp.getZ(i), tmp);
      hp.setXYZ(i, tmp.x, tmp.y, tmp.z);
    }
    headGeo.computeVertexNormals();
    weldNormals(headGeo);
    const headMap = paint([256, 512, 1024][q], [128, 256, 512][q], (u, v, col) => {
      const lon = (u - 0.5) * Math.PI * 2, lat = (v - 0.5) * Math.PI;
      col.copy(fur);
      const X = lon * Math.cos(lat), Y = lat;
      // light muzzle and chin
      const muz = Math.hypot(X / 0.42, (Y + 0.72) / 0.36);
      mixc(col, light, (1 - smooth(0.5, 1.1, muz)) * 0.9);
      mixc(col, cream, (1 - smooth(0.35, 0.95, Math.hypot(X / 0.3, (Y + 0.95) / 0.3))) * 0.6);
      // three forehead stripes, thick at the crown and tapering down
      let d = sdTaper(X, Y, 0, 1.15, 0, 0.62, 0.05, 0.016);
      d = Math.min(d, sdTaper(X, Y, -0.2, 1.05, -0.13, 0.66, 0.042, 0.013));
      d = Math.min(d, sdTaper(X, Y, 0.2, 1.05, 0.13, 0.66, 0.042, 0.013));
      // two short cheek stripes on each side
      for (const s of [-1, 1]) {
        d = Math.min(d, sdTaper(X, Y, s * 1.5, -0.1, s * 1.18, -0.16, 0.035, 0.01));
        d = Math.min(d, sdTaper(X, Y, s * 1.5, -0.3, s * 1.2, -0.3, 0.03, 0.009));
      }
      mixc(col, dark, (1 - smooth(-0.012, 0.012, d)) * 0.62);
    });
    const headMat = new THREE.MeshPhysicalMaterial({ map: headMap, ...furParams });
    this.headMesh = new THREE.Mesh(headGeo, headMat);
    this.headMesh.position.y = HEAD_UP;
    this.headPivot.add(this.headMesh);
    const head = this.headMesh;
    this.surface = new FaceSurface([80, 96, 112][q]);

    this.setupFace(head, q, fur);

    // ears: pivot at the base, sprung
    const earGeo = earGeometry(q, fur, new THREE.Color(0xc0141a));
    const earMat = new THREE.MeshPhysicalMaterial({ vertexColors: true, ...furParams, sheen: 0.15, side: THREE.DoubleSide });
    this.ears = [];
    for (const side of [-1, 1]) {
      const base = new THREE.Group();
      base.position.set(side * 0.37, 0.33, -0.03);
      base.rotation.set(-0.12, side * -0.22, side * -0.4);
      head.add(base);
      const joint = new THREE.Group();
      base.add(joint);
      const ear = new THREE.Mesh(earGeo, earMat);
      joint.add(ear);
      this.ears.push({ side, joint, fold: new Spring(110, 10), flat: new Spring(110, 10), turn: new Spring(90, 9) });
    }

    this.bubbleAnchor = new THREE.Object3D();
    this.bubbleAnchor.position.set(0, 0.86, 0);
    head.add(this.bubbleAnchor);

    // --- front legs (two-bone IK: paws stay planted, or reach for the face) ------------
    // one smooth tube per leg, skinned to shoulder → elbow bones: it bends without a seam
    const legGeo = limbGeometry(0.13, 0.088, L1 + L2, seg / 2, q, [10, 14, 18][q]);
    skinByHeight(legGeo, [
      (y) => smooth(-L1 - 0.07, -L1 + 0.07, y),
      (y) => 1 - smooth(-L1 - 0.07, -L1 + 0.07, y),
    ]);
    const pawGeo = pawGeometry(q, 0.122, 0.08, 0.15);
    const padMat = new THREE.MeshPhysicalMaterial({ color: 0xf28d98, roughness: 0.45, clearcoat: 0.4 });
    const padGeo = merge([
      (() => { const g = new THREE.SphereGeometry(0.05, 12, 8); g.scale(1, 0.25, 0.85); g.translate(0, 0, -0.015); return g; })(),
      ...[-1, 0, 1].map((k) => { const g = new THREE.SphereGeometry(0.02, 10, 6); g.scale(1, 0.3, 1.1); g.translate(k * 0.037, 0, 0.055 - Math.abs(k) * 0.012); return g; }),
    ]);
    this.legs = [];
    for (const side of [-1, 1]) {
      const legMesh = new THREE.SkinnedMesh(legGeo, furMat);
      legMesh.position.set(side * 0.155, 0.22, 0.18);
      legMesh.frustumCulled = false;
      chest.add(legMesh);
      const shoulder = new THREE.Bone();
      shoulder.rotation.order = "ZYX";
      legMesh.add(shoulder);
      const elbow = new THREE.Bone();
      elbow.position.y = -L1;
      shoulder.add(elbow);
      const wrist = new THREE.Bone();
      wrist.position.y = -L2;
      elbow.add(wrist);
      legMesh.bind(new THREE.Skeleton([shoulder, elbow]));
      const paw = new THREE.Mesh(pawGeo, furMat);
      paw.position.set(0, -0.035, 0.035);
      wrist.add(paw);
      const pad = new THREE.Mesh(padGeo, padMat);
      pad.position.set(0, -0.047, 0.0);
      paw.add(pad);
      this.legs.push({ side, base: legMesh.position, shoulder, elbow, wrist, target: new THREE.Vector3(), pitch: 0 });
    }

    // --- tail: a skinned tube on a chain of bones, every joint on its own spring --------
    const tailPts = profile([[0.0, -0.08], [0.055, -0.07], [0.078, 0.0], [0.072, 0.3], [0.066, 0.6], [0.062, 0.9],
      [0.054, 1.0], [0.034, 1.05], [0.0, 1.075]].map(([r, y]) => [r, y * TAIL_LEN / 1.075]), 40);
    const tailGeo = new THREE.LatheGeometry(tailPts, [10, 14, 20][q]);
    const tailMap = paint(32, [128, 256, 256][q], (u, v, col) => {
      col.copy(fur);
      const y = tailPts[Math.round(v * (tailPts.length - 1))].y / TAIL_LEN;
      const b = Math.abs(((y - 0.18) * 7.2) % 1 - 0.5);
      if (y > 0.2) mixc(col, dark, (1 - smooth(0.12, 0.2, b)) * 0.55);
    });
    const tailMat = new THREE.MeshPhysicalMaterial({ map: tailMap, ...furParams });
    const step = TAIL_LEN / TAIL_BONES;
    const heights = Array.from({ length: TAIL_BONES }, (_, i) => i * step);
    this.tailBones = boneChain(heights);
    skinByHeight(tailGeo, heights.map((h, i) => (y) => {
      if (i === 0 && y <= h) return 1;
      if (i === TAIL_BONES - 1 && y >= h) return 1;
      return Math.max(0, 1 - Math.abs(y - h) / step);
    }));
    const tail = new THREE.SkinnedMesh(tailGeo, tailMat);
    tail.position.set(-0.14, 0.15, -0.3);
    hips.add(tail);
    tail.add(this.tailBones[0]);
    tail.bind(new THREE.Skeleton(this.tailBones));
    tail.frustumCulled = false;
    this.tail = tail;
    this.tailRest = this.tailBones.map((_, i) => (i === 0 ? 0 : -[0, 0.02, 0.1, 0.24, 0.34, 0.38, 0.38, 0.34, 0.3, 0.24][i]));
    this.tailSprings = this.tailBones.map((_, i) => ({ z: new Spring(70 - i * 3, 8), x: new Spring(70 - i * 3, 8) }));

    // --- runtime state ----------------------------------------------------------------
    this.pupil = { r: 0.56, slit: 1 };
    this.perk = 0; // ears perk up after hearing something interesting
    this.perkUntil = -1;
    this.prevHead = new THREE.Vector3();
    this.headVel = new THREE.Vector3();
    this.v1 = new THREE.Vector3(); this.v2 = new THREE.Vector3(); this.v3 = new THREE.Vector3();
    this.pose = { yaw: 0, pitch: 0, roll: 0 };

    this.director.register({
      tailWag: { duration: 2.6, weight: 1.3, cooldown: 9, states: ["idle", "speaking"] },
      earTwitch: { duration: 0.9, weight: 1.5, cooldown: 5, states: ["idle", "speaking", "listening"] },
      slowBlink: { duration: 2.0, weight: 1, cooldown: 14 },
      headTilt: { duration: 2.2, weight: 1.1, cooldown: 10, states: ["idle", "listening"] },
      curiousLook: { duration: 2.8, weight: 0.9, cooldown: 16 },
      silentMeow: { duration: 1.5, weight: 0.6, cooldown: 22 },
      pawRaise: { duration: 2.4, weight: 0.7, cooldown: 18 },
      faceWash: { duration: 5.0, weight: 0.45, cooldown: 40 },
      smugLook: { duration: 2.6, weight: 0.6, cooldown: 24, states: ["idle", "speaking"] },
      explainPaw: { duration: 1.7, weight: 1.6, cooldown: 4, states: ["speaking"] },
      earFlick: { duration: 0.8, weight: 1.2, cooldown: 3, states: ["speaking"] },
    });
  }

  setupFace(head, q, fur) {
    const S = this.surface;
    const eyeR = 0.218;
    this.eyeUniforms = {
      pupilR: { value: 0.55 }, pupilShape: { value: new THREE.Vector2(1, 1) }, irisR: { value: 0.82 },
      irisInner: { value: new THREE.Color(0x7a3610) }, irisOuter: { value: new THREE.Color(0xb0621e) },
      irisRing: { value: new THREE.Color(0x3a1806) }, irisLight: { value: new THREE.Color(0xe39a3e) },
      sclera: { value: new THREE.Color(0xf6eee4) },
    };
    const eyeMat = eyeMaterial(this.eyeUniforms);
    const lidMat = new THREE.MeshPhysicalMaterial({ color: fur, roughness: 0.56, clearcoat: 0.22, clearcoatRoughness: 0.5,
      sheen: 0.4, sheenRoughness: 0.45, sheenColor: new THREE.Color(0xffa050), envMapIntensity: 0.75, side: THREE.DoubleSide });
    const lashMat = new THREE.MeshStandardMaterial({ color: 0x2a1408, roughness: 0.5 });
    const shineMat = new THREE.MeshBasicMaterial({ color: 0xffffff });
    const lashGeo = lashGeometry(eyeR * 1.035, q);
    for (const side of [-1, 1]) {
      const ex = side * 0.295, ey = 0.0;
      const eye = new CatEye({ radius: eyeR, mat: eyeMat, lidMat, lashMat, lashGeo, shineMat, side, quality: q });
      eye.group.position.set(ex, ey, S.z(ex, ey) - eyeR * 0.4);
      eye.group.rotation.set(-0.06, side * 0.36, 0);
      eye.group.scale.set(1, 1.1, 0.5);
      head.add(eye.group);
      this.eyes.push(eye);
      const blush = new THREE.Mesh(this.surfaceDisc(side * 0.4, -0.24, 0.075, 0.045, 20, 0.004),
        new THREE.MeshBasicMaterial({ color: 0xff7c8c, transparent: true, opacity: 0, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -4 }));
      head.add(blush);
      (this.blush ??= []).push(blush);
    }
    // nose: a soft rounded triangle, wider on top
    const ng = new THREE.SphereGeometry(1, 20, 14);
    const np = ng.attributes.position;
    for (let i = 0; i < np.count; i++) {
      const x = np.getX(i), y = np.getY(i), z = np.getZ(i);
      const w = 0.5 + 0.5 * (y + 1) / 2;
      np.setXYZ(i, x * 0.085 * w * 1.15, y * 0.05 - (1 - Math.abs(x)) * 0.006, z * 0.046);
    }
    ng.computeVertexNormals();
    this.nose = new THREE.Mesh(ng, new THREE.MeshPhysicalMaterial({ color: 0xf0857f, roughness: 0.32, clearcoat: 0.8, clearcoatRoughness: 0.2 }));
    const nyy = -0.215;
    this.nose.position.set(0, nyy, S.z(0, nyy) + 0.006);
    this.nose.rotation.x = -0.25;
    head.add(this.nose);
    // mouth
    this.mouth = new CatMouth(S, 0, -0.3, q, { line: 0x4a2010, inner: 0x5a1220, tongue: 0xf0707f });
    head.add(this.mouth.group);
    // whiskers: one shared geometry (three per side), mirrored for the left
    const wg = [];
    for (const [dy, ang, len] of [[0.018, 0.16, 0.36], [0, 0.0, 0.4], [-0.02, -0.15, 0.36]]) {
      const end = new THREE.Vector3(len, dy + Math.sin(ang) * len - 0.02, -0.16);
      const curve = new THREE.QuadraticBezierCurve3(new THREE.Vector3(0, dy, 0),
        new THREE.Vector3(len * 0.5, dy + Math.sin(ang) * len * 0.5 + 0.01, -0.04), end);
      const tg = new THREE.TubeGeometry(curve, [6, 8, 12][q], 0.0042, [3, 4, 5][q], false);
      // taper towards the tip
      const p = tg.attributes.position;
      const pt = new THREE.Vector3();
      for (let i = 0; i < p.count; i++) {
        const t = clamp01(p.getX(i) / len);
        curve.getPoint(t, pt);
        p.setXYZ(i, pt.x + (p.getX(i) - pt.x) * (1 - t * 0.6), pt.y + (p.getY(i) - pt.y) * (1 - t * 0.6), pt.z + (p.getZ(i) - pt.z) * (1 - t * 0.6));
      }
      wg.push(tg);
    }
    const whiskerGeo = merge(wg);
    const whiskerMat = new THREE.MeshStandardMaterial({ color: 0x7a3a14, roughness: 0.6 });
    this.whiskers = [];
    for (const side of [-1, 1]) {
      const w = new THREE.Mesh(whiskerGeo, whiskerMat);
      const wx = side * 0.2, wy = -0.26;
      w.position.set(wx, wy, S.z(wx, wy) - 0.006);
      w.scale.x = side;
      w.rotation.y = 0;
      head.add(w);
      this.whiskers.push(w);
    }
    // markers on the face for the paw IK (grooming, thinking)
    const marker = (x, y, out) => { const o = new THREE.Object3D(); o.position.set(x, y, S.z(x, y) + out); head.add(o); return o; };
    this.marks = { mouth: marker(0.04, -0.34, 0.1), cheek: marker(0.36, -0.2, 0.08), brow: marker(0.38, 0.18, 0.06), chin: marker(0.06, -0.47, 0.1) };
  }

  // Thin disc lying on the face surface (blush).
  surfaceDisc(cx, cy, rx, ry, segs, off) {
    const S = this.surface;
    const pos = [cx, cy, S.z(cx, cy) + off];
    const idx = [];
    for (let i = 0; i <= segs; i++) {
      const a = i / segs * Math.PI * 2, x = cx + Math.cos(a) * rx, y = cy + Math.sin(a) * ry;
      pos.push(x, y, S.z(x, y) + off);
      if (i > 0) idx.push(0, i, i + 1);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    g.setIndex(idx);
    return g;
  }

  update(dt, t, state) {
    this.dt = dt;
    super.update(dt, t, state);
  }

  hear(text) {
    if (Character.mentionsTech(text)) {
      this.perkUntil = (this.now ?? 0) + 3.5;
      this.director.play("curiousLook", true);
    } else if (text) {
      this.director.play("earTwitch", true);
    }
  }

  applyFace(t) {
    const d = this.director, g = d.curve(), c = this.cur;
    let force = 0, squint = 0, tiltA = 0;
    if (g.name === "slowBlink") {
      // the affectionate cat blink: slow close, a held beat, slow open
      force = smooth(0.05, 0.4, g.p) * (1 - smooth(0.62, 0.95, g.p));
    }
    if (g.name === "smugLook") { force = 0.5 * g.s; squint = 0.12 * g.s; tiltA = 0.12 * g.s; }
    if (g.name === "faceWash") { force = 0.55 * g.s; squint = 0.2 * g.s; }
    if (g.name === "silentMeow") squint = 0.3 * bumpS(g.p, 0.15, 0.8);
    if (d.state === "paused") force = Math.max(force, 0.25 * d.w.paused);
    for (let i = 0; i < this.eyes.length; i++) {
      const eye = this.eyes[i];
      eye.force = force;
      eye.squint = squint;
      eye.extraTilt = tiltA * (i === 0 ? 1 : -1);
    }
    this.mouth.meow = g.name === "silentMeow" ? bumpS(g.p, 0.15, 0.8) : 0;
    this.mouth.lick = g.name === "faceWash" ? this.lickAmount(g.p) : 0;
    super.applyFace(t);
    // pupils: wide when curious/surprised/listening, narrow slit when annoyed
    const curious = (g.name === "curiousLook" ? g.s : 0) + (this.now < this.perkUntil ? 0.6 : 0);
    let pr = 0.56 + c.wide * 0.16 + curious * 0.14 + d.w.listening * 0.06 + d.w.paused * -0.04;
    let slit = 1;
    if (this.emotion === "annoyed") { pr -= 0.08; slit = 0.5; }
    if (this.emotion === "laugh" || this.emotion === "happy") pr += 0.04;
    const fdt = this.dt ?? 1 / 60;
    this.pupil.r = damp(this.pupil.r, Math.min(0.78, pr), 5, fdt);
    this.pupil.slit = damp(this.pupil.slit, slit, 5, fdt);
    this.eyeUniforms.pupilR.value = this.pupil.r;
    this.eyeUniforms.pupilShape.value.set(this.pupil.slit, 1);
    const glow = clamp01((c.smile - 0.45) * 1.8) * 0.5;
    for (const b of this.blush) b.material.opacity = glow;
  }

  lickAmount(p) {
    // faceWash timeline: 0–0.14 paw to mouth, 0.14–0.42 licks, 0.42–0.86 wipes, then down
    if (p < 0.14 || p > 0.44) return 0;
    const k = (p - 0.14) / 0.28;
    return Math.pow(Math.abs(Math.sin(k * Math.PI * 3)), 0.6) * smooth(0, 0.1, k) * (1 - smooth(0.9, 1, k));
  }

  animate(dt, t, state) {
    const c = this.cur, d = this.director, w = d.w, a = d.amp;
    const act = this.actionCurve();
    const g = d.curve();
    const talking = c.speak;
    const still = d.state === "emergency";
    const side = d.gesture ? (d.gesture.side ??= d.rng() < 0.5 ? -1 : 1) : 1;
    const calm = still ? 0.15 : 1;

    // --- whole body: hops, squash, breathing --------------------------------------------
    let jump = 0, squash = 0, spin = 0;
    if (act.name === "celebrate") {
      jump = Math.abs(Math.sin(act.p * Math.PI * (act.gentle ? 1 : 2))) * (act.gentle ? 0.08 : 0.26);
      spin = act.gentle ? 0 : smooth(0.5, 0.95, act.p) * Math.PI * 2;
    }
    if (act.name === "surprised") { jump = act.s * (act.gentle ? 0.05 : 0.17); squash = -act.s * 0.05; }
    if (act.name === "happy") jump = Math.abs(Math.sin(act.p * Math.PI * 2)) * 0.05;
    if (act.name === "laugh") squash = Math.sin(t * 26) * 0.022 * act.s;
    squash += d.breath * 0.008 * a * calm + talking * 0.01;
    this.root.position.y = damp(this.root.position.y, jump, 16, dt);
    if (spin) this.body.rotation.y = spin;
    else {
      const ry = this.body.rotation.y;
      this.body.rotation.y = damp(Math.atan2(Math.sin(ry), Math.cos(ry)), d.head.x * 0.12 * calm, 4, dt);
    }
    this.body.rotation.z = damp(this.body.rotation.z, d.lean.x * 0.035 * a * calm, 4, dt);
    this.hips.scale.set(1 - squash * 0.5, 1 + squash, 1 - squash * 0.5);

    // chest: lean in to listen/peek, breathe, rock with laughter
    let chestX = d.lean.z * 0.05 * a + w.listening * 0.07 - w.paused * 0.03 + w.reading * 0.04;
    let chestZ = d.lean.x * 0.03;
    if (g.name === "curiousLook") { chestX += 0.12 * g.s; chestZ += 0.08 * side * g.s; }
    if (g.name === "pawRaise") chestZ -= 0.05 * g.s;
    if (g.name === "faceWash") chestX += 0.06 * g.s;
    if (act.name === "laugh") chestX -= 0.12 * act.s;
    this.chest.rotation.x = damp(this.chest.rotation.x, chestX * calm, 6, dt);
    this.chest.rotation.z = damp(this.chest.rotation.z, chestZ * calm, 5, dt);
    const breathe = 1 + d.breath * 0.014 * a * calm;
    this.chest.scale.set(breathe, 1, breathe);

    // --- head ------------------------------------------------------------------------
    const P = this.pose;
    let yaw = d.head.x * 0.55, pitch = -d.head.y * 0.3 - d.beat * 0.06 - talking * 0.03, roll = c.tilt * 0.8;
    if (w.listening > 0.01) roll += 0.12 * w.listening;
    if (state.phase === "thinking") { roll -= 0.12; pitch -= 0.08; }
    if (g.name === "headTilt") roll += side * 0.34 * g.s;
    if (g.name === "curiousLook") { yaw += side * 0.22 * g.s; roll -= side * 0.18 * g.s; pitch += 0.05 * g.s; }
    if (g.name === "silentMeow") pitch -= 0.16 * bumpS(g.p, 0.1, 0.85);
    if (g.name === "slowBlink") { pitch += 0.07 * g.s; roll += 0.06 * g.s; }
    if (g.name === "smugLook") { pitch -= 0.1 * g.s; roll += side * 0.1 * g.s; yaw += side * 0.1 * g.s; }
    if (g.name === "faceWash") {
      const lickNod = this.lickAmount(g.p);
      const wipe = bumpS(g.p, 0.42, 0.88);
      pitch += 0.14 * g.s + lickNod * 0.08 + wipe * Math.sin(g.p * Math.PI * 9) * 0.05;
      roll += 0.22 * wipe;
      yaw -= 0.12 * wipe;
    }
    if (g.name === "explainPaw") roll += 0.06 * g.s;
    if (act.name === "confused") roll += 0.3 * act.s;
    if (act.name === "laugh") pitch -= 0.18 * act.s + Math.sin(t * 22) * 0.03 * act.s;
    if (act.name === "annoyed") { yaw -= 0.25 * act.s; pitch -= 0.08 * act.s; }
    if (act.name === "surprised") pitch -= 0.08 * act.s;
    if (d.state === "paused") pitch += 0.08 * w.paused;
    P.yaw = damp(P.yaw, yaw * calm, 7, dt);
    P.pitch = damp(P.pitch, pitch * calm, 8, dt);
    P.roll = damp(P.roll, roll * calm, 7, dt);
    this.neck.rotation.set(P.pitch * 0.3, P.yaw * 0.3, P.roll * 0.2);
    this.headPivot.rotation.set(P.pitch * 0.7, P.yaw * 0.7, P.roll * 0.8);

    this.root.updateMatrixWorld(true);
    this.headMesh.getWorldPosition(this.v1);
    this.headVel.copy(this.v1).sub(this.prevHead).divideScalar(Math.max(dt, 1e-3));
    this.prevHead.copy(this.v1);

    this.animateEars(dt, t, g, act, side, still);
    this.animateTail(dt, t, g, act, still);
    this.animateLegs(dt, t, g, act, state, side, still);

    // whiskers twitch with the voice and when curious
    const wt = (Math.sin(t * 13) * talking * 0.04 + (g.name === "curiousLook" ? 0.08 * g.s : 0) + (act.name === "surprised" ? 0.12 * act.s : 0)) * calm;
    this.whiskers[0].rotation.z = -wt;
    this.whiskers[1].rotation.z = wt;
  }

  animateEars(dt, t, g, act, side, still) {
    const c = this.cur, d = this.director, w = d.w;
    const perk = Math.max(this.now < this.perkUntil ? 1 : 0, w.listening, c.wide);
    for (let i = 0; i < this.ears.length; i++) {
      const ear = this.ears[i], s = ear.side;
      let fold = -0.12 * perk, flat = 0.06 - 0.1 * perk, turn = -0.1 * perk;
      if (this.emotion === "annoyed") { flat += 0.75; fold += 0.35; }
      if (this.emotion === "laugh") { fold += 0.2; flat += 0.15; }
      if (this.emotion === "confused") { if (s < 0) { flat += 0.45; fold += 0.15; } else fold -= 0.12; }
      if (this.emotion === "happy" || this.emotion === "celebrate") fold -= 0.06;
      flat += w.paused * 0.3; fold += w.paused * 0.1;
      if (d.state === "thinking" && s > 0) turn += 0.5 * w.thinking;
      if (w.reading > 0.01) fold -= 0.08 * w.reading;
      if (g.name === "silentMeow") { fold += 0.35 * g.s; flat += 0.2 * g.s; }
      if (g.name === "headTilt" && s === side) { turn += 0.3 * g.s; flat += 0.15 * g.s; }
      if (g.name === "curiousLook") { fold -= 0.18 * g.s; turn -= 0.15 * g.s; }
      if (g.name === "smugLook") { flat += 0.18 * g.s; turn += 0.15 * g.s; }
      if (g.name === "faceWash") flat += 0.2 * g.s;
      const twitch = (g.name === "earTwitch" || g.name === "earFlick") && s === side;
      if (twitch) {
        const k = Math.max(bump(g.p, 0.05, 0.35), g.name === "earTwitch" ? bump(g.p, 0.45, 0.75) : 0);
        fold += 0.45 * k; turn += 0.5 * k; flat += 0.2 * k;
      }
      if (act.name === "surprised") { fold -= 0.25 * act.s; flat -= 0.12 * act.s; }
      if (still) { fold *= 0.3; flat = 0.06; turn *= 0.3; }
      // inertia: the head's motion swings the ears
      const kick = Math.min(dt, 0.05) * 1.6;
      ear.fold.v += (this.headVel.y * 1.4 - this.headVel.z * 0.7) * kick;
      ear.flat.v += this.headVel.x * s * 1.2 * kick;
      const fx = ear.fold.step(fold, dt), fz = ear.flat.step(flat, dt), fy = ear.turn.step(turn, dt);
      ear.joint.rotation.set(-fx, s * fy, -s * fz);
    }
  }

  animateTail(dt, t, g, act, still) {
    const d = this.director, w = d.w, n = TAIL_BONES;
    let amp = 0.07, freq = 1.1, ampX = 0.06, lift = 0, curl = 0, tipFlick = 0;
    if (g.name === "tailWag") { amp += 0.26 * g.s; freq += 0.9 * g.s; ampX += 0.12 * g.s; }
    if (this.emotion === "annoyed") tipFlick = 0.4;
    if (this.emotion === "happy" || this.emotion === "celebrate") { lift = 0.35; amp += 0.04; }
    if (this.emotion === "surprised") { lift = 0.5; amp *= 0.4; }
    if (this.emotion === "confused") curl = 0.25;
    if (d.state === "thinking") { tipFlick = Math.max(tipFlick, 0.15); }
    if (d.state === "speaking") amp += 0.04 + d.beat * 0.1;
    if (act.name === "laugh") { amp += 0.15 * act.s; freq += 3 * act.s; }
    amp *= d.amp; ampX *= d.amp;
    const pw = w.paused;
    curl += pw * 0.15; amp *= 1 - pw * 0.6; freq *= 1 - pw * 0.4;
    if (still) { amp = 0.015; ampX = 0.01; freq = 0.6; lift = 0; curl = 0; tipFlick = 0; }
    this.tailPhase = (this.tailPhase ?? 0) + dt * freq * Math.PI * 2;
    const ph = this.tailPhase;
    for (let i = 0; i < n; i++) {
      const b = this.tailBones[i], sp = this.tailSprings[i];
      const k = i / (n - 1);
      let tz = this.tailRest[i] + amp * Math.sin(ph - i * 0.55) * (0.35 + k) - curl * k * 0.35;
      let tx = ampX * Math.sin(ph * 0.7 - i * 0.4) * (0.3 + k);
      if (i >= n - 4) tz += tipFlick * Math.sin(t * 11 - i) * 0.6;
      if (i === 0) { tz = 1.72 - lift * 0.9 + amp * 0.7 * Math.sin(ph + 0.6); tx = 0.32 + tx * 0.5; }
      else if (i < 4) tz -= lift * 0.12;
      b.rotation.z = sp.z.step(tz, dt);
      b.rotation.x = i === 0 ? 0 : sp.x.step(tx, dt);
      if (i === 0) b.rotation.y = sp.x.step(tx, dt);
    }
  }

  // Two-bone IK in the leg plane. target: wrist position in chest space; pitch: paw angle.
  solveLeg(leg, target, pitch) {
    const T = this.v3.copy(target).sub(leg.base);
    let phi = Math.abs(T.y) > 1e-4 ? Math.atan(-T.x / T.y) : 0;
    phi = THREE.MathUtils.clamp(phi, -1.0, 1.0);
    const yp = -T.x * Math.sin(phi) + T.y * Math.cos(phi);
    const D = THREE.MathUtils.clamp(Math.hypot(yp, T.z), 0.08, L1 + L2 - 0.002);
    const thT = Math.atan2(-T.z, -yp);
    const gam = Math.acos(THREE.MathUtils.clamp((L1 * L1 + D * D - L2 * L2) / (2 * L1 * D), -1, 1));
    const del = Math.acos(THREE.MathUtils.clamp((L1 * L1 + L2 * L2 - D * D) / (2 * L1 * L2), -1, 1));
    const al = thT + gam, be = -(Math.PI - del);
    leg.shoulder.rotation.set(al, 0, phi);
    leg.elbow.rotation.x = be;
    leg.wrist.rotation.x = pitch - (al + be) - (this.chest.rotation.x + this.hips.rotation.x);
  }

  // Blend the wrist target (world space, in this.v1) towards a point near a face marker.
  _reach(obj, dx, dy, dz, weight, pawPitch) {
    if (weight <= 0.001) return;
    const m = this.v2;
    obj.getWorldPosition(m);
    m.x += dx; m.y += dy; m.z += dz;
    this.v1.lerp(m, weight);
    this._pitch = lerp(this._pitch, pawPitch, weight);
  }

  // Blend the wrist target towards a point relative to the resting paw (body space).
  _lift(s, dx, dy, dz, weight, pawPitch) {
    if (weight <= 0.001) return;
    const m = this.v2.set(s * 0.165 + dx * s, 0.086 + dy, 0.32 + dz);
    this.body.localToWorld(m);
    this.v1.lerp(m, weight);
    this._pitch = lerp(this._pitch, pawPitch, weight);
  }

  animateLegs(dt, t, g, act, state, side, still) {
    const d = this.director;
    const v = this.v1;
    const thinkW = d.state === "thinking" ? d.w.thinking : 0;
    for (let li = 0; li < this.legs.length; li++) {
      const leg = this.legs[li], s = leg.side;
      // rest: paw planted on the ground (body space → world → chest space)
      v.set(s * 0.165, 0.086, 0.32);
      this.body.localToWorld(v);
      this._pitch = 0;
      if (!still) {
        const main = s > 0; // the visible right-hand paw (screen right) does the solo gestures
        if (main) {
          if (g.name === "pawRaise") this._lift(s, 0.03, 0.6 + Math.sin(g.t * 7) * 0.03 * g.s, 0.2, g.s, -1.45 + Math.sin(g.t * 7) * 0.3);
          if (g.name === "explainPaw") this._lift(s, 0.0, 0.28 + Math.sin(g.t * 6) * 0.05, 0.12, g.s, -0.9);
          if (g.name === "faceWash") {
            const toMouth = smooth(0.02, 0.14, g.p) * (1 - smooth(0.4, 0.5, g.p));
            const wipe = bumpS(g.p, 0.42, 0.9);
            this._reach(this.marks.mouth, 0.02, -0.03, 0.02, toMouth, -2.0);
            if (wipe > 0) {
              // strokes from the cheek up over the eye towards the ear
              const cyc = 0.5 - 0.5 * Math.cos((g.p - 0.42) / 0.46 * Math.PI * 6);
              const m = this.v2, b = this.v3;
              this.marks.cheek.getWorldPosition(m);
              this.marks.brow.getWorldPosition(b);
              m.lerp(b, cyc);
              m.z += 0.04;
              v.lerp(m, wipe);
              this._pitch = lerp(this._pitch, -2.1, wipe);
            }
          }
          if (thinkW > 0.01) this._reach(this.marks.chin, -0.02, -0.02, 0.05, thinkW * 0.95, -1.9);
        }
        if (act.name === "celebrate") this._lift(s, 0.04, 0.5, 0.15, act.s, -1.3);
        if (act.name === "surprised") this._lift(s, 0.03, 0.2, 0.08, act.s * 0.7, -0.8);
        if (act.name === "laugh" && main) this._reach(this.marks.mouth, 0.02, -0.06, 0.06, act.s * 0.8, -1.9);
      }
      this.chest.worldToLocal(v);
      if (!leg.ready) { leg.target.copy(v); leg.ready = true; }
      leg.target.lerp(v, 1 - Math.exp(-14 * dt));
      leg.pitch = damp(leg.pitch, this._pitch, 12, dt);
      this.solveLeg(leg, leg.target, leg.pitch);
    }
  }
}

function bumpS(p, a, b) { return smooth(a, a + (b - a) * 0.3, p) * (1 - smooth(b - (b - a) * 0.3, b, p)); }
