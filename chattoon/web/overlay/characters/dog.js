// Cachorro: a cheerful white-and-brown cartoon puppy (beagle / jack-russell look),
// sitting like a vinyl toy. Round head built from a smooth signed-distance blend (skull,
// full cheeks, soft muzzle) with seamless painted patches, big glossy eyes, floppy ears
// and a tail on spring-driven bones, an open smiling mouth with a pink tongue, round paws.
import * as THREE from "../../vendor/three/three.module.js";
import { Character, Eye, Spring, clamp01, damp, smooth } from "../rig.js";
import { boneChain, frontUV, latheBody, markedMaterial, markingTexture, profile, skinByHeight, smin } from "./shapes.js";

const WHITE = 0xf3efe8;
const BROWN = 0x88450a;
const BROW = 0x3a2114;
const S = 1.28; // the model is built in "reference units" and scaled up to the stage
const NECK_Y = 0.8; // head bone height (body units)
const HEAD = new THREE.Vector3(0, 1.2, 0.06); // head centre (body units)
const MOUTH_Y = -0.218; // head-local height of the upper lip line
const NOSE_Y = -0.075;
const JAW = 0.065; // how far the chin drops with the jaw

const ell = (x, y, z, cx, cy, cz, rx, ry, rz) => {
  const dx = (x - cx) / rx, dy = (y - cy) / ry, dz = (z - cz) / rz;
  return (Math.sqrt(dx * dx + dy * dy + dz * dz) - 1) * Math.min(rx, ry, rz);
};

// Head (head-local): round skull, full cheeks, a small soft muzzle — one smooth surface.
function headSDF(x, y, z) {
  let d = ell(x, y, z, 0, 0.0, 0, 0.5, 0.47, 0.46);
  d = smin(d, ell(x, y, z, 0, -0.15, 0.07, 0.49, 0.32, 0.4), 0.14);
  d = smin(d, ell(x, y, z, 0, -0.19, 0.41, 0.26, 0.185, 0.25), 0.08);
  // puffy cheeks either side of the muzzle
  d = smin(d, Math.min(ell(x, y, z, -0.19, -0.2, 0.27, 0.19, 0.17, 0.2), ell(x, y, z, 0.19, -0.2, 0.27, 0.19, 0.17, 0.2)), 0.09);
  return d;
}

// White areas of the head coat (negative inside): muzzle, cheeks, chin and the blaze.
function whiteSDF(x, y, z) {
  let d = Math.max(ell(x, y, z, 0.015, -0.3, 0.25, 0.43, 0.25, 0.52), -z - 0.06);
  const wB = (0.07 + 0.065 * smooth(0.12, 0.46, y) + 0.03 * smooth(0.0, -0.15, y)) * smooth(-0.3, 0.04, z) - 0.004;
  const blaze = Math.abs(x - 0.012) - wB;
  d = smin(d, blaze, 0.08);
  d = Math.min(d, Math.max(y + 0.38, 0.08 - z));
  return d;
}

// Chin weight for the jaw morph: everything below the upper lip, front half, fading out.
const jawW = (y, z) => smooth(MOUTH_Y + 0.008, MOUTH_Y - 0.06, y) * (1 - smooth(MOUTH_Y - 0.13, MOUTH_Y - 0.32, y)) * smooth(0.0, 0.28, z);

// Surface queries on the head: radial projection, normals and a front height field
// (z of the face at x, y) used to lay the mouth, nose and brows on the muzzle.
class HeadSurface {
  constructor() {
    this.x0 = -0.4; this.x1 = 0.4; this.y0 = -0.52; this.y1 = 0.36; this.n = 96;
    this.grid = new Float32Array(this.n * this.n);
    for (let j = 0; j < this.n; j++) {
      for (let i = 0; i < this.n; i++) {
        const x = this.x0 + (this.x1 - this.x0) * i / (this.n - 1), y = this.y0 + (this.y1 - this.y0) * j / (this.n - 1);
        this.grid[j * this.n + i] = this.rayZ(x, y);
      }
    }
  }

  rayZ(x, y) {
    let z = 0.9;
    for (; z > -0.3; z -= 0.01) if (headSDF(x, y, z) < 0) break;
    let hi = z + 0.01, lo = z;
    for (let k = 0; k < 18; k++) { const m = (hi + lo) / 2; if (headSDF(x, y, m) < 0) lo = m; else hi = m; }
    return (hi + lo) / 2;
  }

  radial(dx, dy, dz) {
    let lo = 0.02, hi = 1.0;
    for (let k = 0; k < 26; k++) { const m = (hi + lo) / 2; if (headSDF(dx * m, dy * m, dz * m) < 0) lo = m; else hi = m; }
    return (hi + lo) / 2;
  }

  normal(x, y, z, out) {
    const h = 0.002;
    out.set(headSDF(x + h, y, z) - headSDF(x - h, y, z), headSDF(x, y + h, z) - headSDF(x, y - h, z), headSDF(x, y, z + h) - headSDF(x, y, z - h));
    return out.normalize();
  }

  z(x, y) {
    const n = this.n;
    const fx = THREE.MathUtils.clamp((x - this.x0) / (this.x1 - this.x0) * (n - 1), 0, n - 1.001);
    const fy = THREE.MathUtils.clamp((y - this.y0) / (this.y1 - this.y0) * (n - 1), 0, n - 1.001);
    const i = Math.floor(fx), j = Math.floor(fy), tx = fx - i, ty = fy - j;
    const g = this.grid;
    const a = g[j * n + i] + (g[j * n + i + 1] - g[j * n + i]) * tx;
    const b = g[(j + 1) * n + i] + (g[(j + 1) * n + i + 1] - g[(j + 1) * n + i]) * tx;
    return a + (b - a) * ty;
  }

  // face height with the chin dropped by `jaw` (inverse of the jaw morph)
  zJaw(x, y, jaw) {
    if (jaw < 1e-3) return this.z(x, y);
    let yb = y;
    for (let k = 0; k < 3; k++) yb = y + JAW * jaw * jawW(yb, this.z(x, yb));
    const zb = this.z(x, yb);
    return zb - JAW * 0.25 * jaw * jawW(yb, zb);
  }
}

// Smooth normals across the duplicated seam / pole vertices of a deformed sphere.
function weldNormals(g) {
  g.computeVertexNormals();
  const pos = g.attributes.position, nor = g.attributes.normal;
  const groups = new Map();
  for (let i = 0; i < pos.count; i++) {
    const key = `${Math.round(pos.getX(i) * 1e4)},${Math.round(pos.getY(i) * 1e4)},${Math.round(pos.getZ(i) * 1e4)}`;
    let e = groups.get(key);
    if (!e) groups.set(key, (e = { x: 0, y: 0, z: 0, ids: [] }));
    e.x += nor.getX(i); e.y += nor.getY(i); e.z += nor.getZ(i); e.ids.push(i);
  }
  for (const e of groups.values()) {
    if (e.ids.length < 2) continue;
    const l = Math.hypot(e.x, e.y, e.z) || 1;
    for (const i of e.ids) nor.setXYZ(i, e.x / l, e.y / l, e.z / l);
  }
  return g;
}

// Round paw: a soft flattened dome with toe grooves pressed into the front.
function pawGeometry(q, rx, ry, rz, grooves) {
  const g = new THREE.SphereGeometry(1, [20, 32, 48][q], [12, 20, 30][q], -Math.PI / 2);
  const p = g.attributes.position;
  for (let i = 0; i < p.count; i++) {
    let x = p.getX(i), y = p.getY(i), z = p.getZ(i);
    let k = 1;
    for (const gx of grooves) k -= 0.085 * Math.exp(-(((x - gx) / 0.075) ** 2)) * smooth(0.15, 0.65, z) * smooth(-0.35, 0.15, y);
    x *= k; y *= k; z *= k;
    p.setXYZ(i, x * rx, (y > 0 ? y * ry : y * ry * 0.55), z * rz);
  }
  return weldNormals(g);
}

// Floppy ear hanging along -Y: thick at the root, wide rounded flap, cupped towards the head.
function earGeometry(q, side, L) {
  const g = new THREE.SphereGeometry(1, [16, 24, 36][q], [20, 30, 44][q], Math.PI);
  const p = g.attributes.position;
  for (let i = 0; i < p.count; i++) {
    const x = p.getX(i), y = p.getY(i), z = p.getZ(i);
    const t = (1 - y) / 2; // 0 root .. 1 tip
    const wide = 0.27 * (0.55 + 0.45 * smooth(0.0, 0.55, t));
    const thick = 0.068 * (1 - 0.45 * t);
    const zz = z * wide;
    const cup = -0.07 * (zz / 0.27) ** 2; // edges curl towards the head
    const bulge = 0.035 * Math.sin(Math.PI * t);
    p.setXYZ(i, side * (x * thick + cup + bulge), -t * L, zz);
  }
  return weldNormals(g);
}

// Tail along +Y with a rounded tip.
function tailGeometry(q) {
  const pts = profile([[0.001, -0.06], [0.05, -0.05], [0.062, 0.0], [0.058, 0.12], [0.05, 0.24], [0.04, 0.34], [0.03, 0.41], [0.016, 0.45], [0.001, 0.462]], [16, 24, 32][q]);
  return new THREE.LatheGeometry(pts, [10, 14, 20][q]);
}

// Muzzle mouth: a lip line / open mouth shape laid on the face (it follows the muzzle and
// the dropping chin), a dark rim, a maroon inside and a 3D tongue. Same interface as Mouth.
class DogMouth {
  constructor(surf, q, tongueColor) {
    this.surf = surf;
    this.C = [17, 25, 33][q];
    this.R = 5;
    this.group = new THREE.Group();
    this.rim = this.sheet(0x2e0a10, 1, null);
    this.inner = this.sheet(0x7d1d2b, 2, [0x3a0710, 0x6a1524, 0x8f2a38]);
    const tg = new THREE.SphereGeometry(1, [14, 20, 28][q], [10, 14, 20][q]);
    const tp = tg.attributes.position;
    for (let i = 0; i < tp.count; i++) {
      const x = tp.getX(i), y = tp.getY(i), z = tp.getZ(i);
      const t = (1 - y) / 2;
      const groove = z > 0 ? 0.35 * Math.exp(-((x / 0.22) ** 2)) * smooth(0.1, 0.5, t) : 0;
      tp.setXYZ(i, x * 0.075 * (0.82 + 0.18 * t), -t * 0.13, z * 0.03 * (1 - groove));
    }
    weldNormals(tg);
    this.tongue = new THREE.Mesh(tg, new THREE.MeshPhysicalMaterial({ color: tongueColor, roughness: 0.38, clearcoat: 0.7, clearcoatRoughness: 0.22, sheen: 0.3, sheenColor: new THREE.Color(0xffc0cc) }));
    this.tongue.renderOrder = 3;
    this.group.add(this.tongue);
    this.p = { open: 0, smile: 0, frown: 0, round: 0, talk: 0 };
    this.jaw = 0;
    this.tmp = new THREE.Vector3();
  }

  sheet(color, order, rowColors) {
    const C = this.C, R = this.R;
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(C * R * 3), 3).setUsage(THREE.DynamicDrawUsage));
    if (rowColors) {
      const col = new Float32Array(C * R * 3), cs = rowColors.map((c) => new THREE.Color(c));
      for (let j = 0; j < C; j++) for (let i = 0; i < R; i++) {
        const f = i / (R - 1) * (cs.length - 1), a = Math.floor(Math.min(f, cs.length - 1.001)), t = f - a;
        const c = cs[a].clone().lerp(cs[a + 1], t);
        col.set([c.r, c.g, c.b], (j * R + i) * 3);
      }
      g.setAttribute("color", new THREE.BufferAttribute(col, 3));
    }
    const idx = [];
    for (let j = 0; j < C - 1; j++) for (let i = 0; i < R - 1; i++) {
      const a = j * R + i, b = (j + 1) * R + i;
      idx.push(a, b, a + 1, a + 1, b, b + 1);
    }
    g.setIndex(idx);
    const m = new THREE.Mesh(g, new THREE.MeshBasicMaterial({ color: rowColors ? 0xffffff : color, vertexColors: !!rowColors,
      side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -1 - order, polygonOffsetUnits: -2 - order * 2 }));
    m.renderOrder = order;
    m.frustumCulled = false;
    this.group.add(m);
    return m;
  }

  set({ open, smile, frown, round, talk }) {
    const p = this.p;
    p.open = open; p.smile = smile; p.frown = frown; p.round = round; p.talk = talk;
  }

  fill(mesh, hw, th, low, lift, eps) {
    const arr = mesh.geometry.attributes.position.array, C = this.C, R = this.R;
    let k = 0;
    for (let j = 0; j < C; j++) {
      const u = -Math.cos(Math.PI * j / (C - 1));
      const x = hw * u, s = Math.sqrt(Math.max(0, 1 - u * u));
      const top = MOUTH_Y + lift * u * u;
      const y0 = top + th * s, y1 = top - low * s;
      for (let i = 0; i < R; i++) {
        const y = y0 + (y1 - y0) * i / (R - 1);
        arr[k++] = x; arr[k++] = y; arr[k++] = this.surf.zJaw(x, y, this.jaw) + eps;
      }
    }
    mesh.geometry.attributes.position.needsUpdate = true;
  }

  // ex: { open, smile, tongue (hang out 0..1), blep (0..1), wag (tongue side wiggle) }
  update(ex, t) {
    const p = this.p;
    const open = clamp01(p.open + ex.open), round = clamp01(p.round);
    const smile = clamp01(p.smile + ex.smile), frown = clamp01(p.frown);
    const o = clamp01(open + round * 0.35);
    this.jaw = o;
    const hw = 0.136 + smile * 0.04 + o * 0.014 - frown * 0.025 - round * 0.07;
    const lift = (smile * 0.06 - frown * 0.06) * (1 - round * 0.85);
    const low = 0.004 + o * 0.19;
    const th = 0.003 + round * o * 0.075;
    this.fill(this.rim, hw + 0.008, th + 0.005, low + 0.006, lift, 0.004);
    this.inner.visible = o > 0.05;
    if (this.inner.visible) this.fill(this.inner, hw - 0.004, Math.max(0.001, th - 0.003), Math.max(0.002, low - 0.008), lift, 0.0075);

    // tongue: rests in the lower jaw when open, hangs out when panting, peeks out for a blep
    const show = smooth(0.1, 0.3, o);
    const blep = ex.blep * (1 - show);
    const vis = Math.max(show, blep);
    const tg = this.tongue;
    tg.visible = vis > 0.02;
    if (!tg.visible) return;
    const yR = THREE.MathUtils.lerp(MOUTH_Y - 0.006, MOUTH_Y - low * 0.3, show);
    const len = THREE.MathUtils.lerp(0.085 * blep, low * 0.8 + ex.tongue * 0.13, show);
    const x = blep * 0.035 * (1 - show) + ex.wag * Math.sin(t * 7) * 0.012 * show;
    const z1 = this.surf.zJaw(x, yR, this.jaw), z2 = this.surf.zJaw(x, yR - 0.06, this.jaw);
    tg.position.set(x, yR, z1 + 0.006);
    tg.rotation.set(Math.atan2(z1 - z2, 0.06) - ex.tongue * 0.45 - blep * 0.35, 0, x * 2);
    const wide = Math.min(1.15, (hw * 0.74) / 0.075);
    tg.scale.set(THREE.MathUtils.lerp(0.85, wide, show), Math.max(0.05, len / 0.13), 1);
  }
}

// Curved brow laid on the head: a thin tapered arc. Same interface as rig.Brow.
class ArcBrow {
  constructor(surf, side, q, mat) {
    this.side = side;
    const cx = side * 0.255, cy = 0.262;
    const pts = [];
    for (let i = 0; i <= 8; i++) {
      const s = i / 8 * 2 - 1;
      const x = cx + s * 0.085, y = cy + 0.03 * (1 - s * s) - side * s * 0.018;
      pts.push(new THREE.Vector3(x, y, surf.z(x, y) + 0.004));
    }
    const curve = new THREE.CatmullRomCurve3(pts);
    const N = [10, 16, 24][q], rad = [5, 6, 8][q];
    const g = new THREE.TubeGeometry(curve, N, 0.0125, rad, false);
    const p = g.attributes.position, c = new THREE.Vector3(), v = new THREE.Vector3();
    for (let i = 0; i < p.count; i++) {
      const seg = Math.floor(i / (rad + 1)), f = Math.pow(Math.sin(Math.PI * (0.06 + 0.88 * seg / N)), 0.6);
      curve.getPointAt(seg / N, c);
      v.fromBufferAttribute(p, i).sub(c).multiplyScalar(f).add(c);
      p.setXYZ(i, v.x, v.y, v.z);
    }
    g.computeVertexNormals();
    this.center = new THREE.Vector3(cx, cy + 0.015, surf.z(cx, cy + 0.015));
    g.translate(-this.center.x, -this.center.y, -this.center.z);
    this.mesh = new THREE.Mesh(g, mat);
    this.mesh.position.copy(this.center);
  }

  set(y, tilt) {
    this.mesh.position.y = this.center.y + y;
    this.mesh.rotation.z = -this.side * tilt * 0.3;
  }
}

export class Dog extends Character {
  constructor(options) {
    super(options);
    const q = this.quality;
    this.brown = new THREE.Color(options.color || BROWN);
    this.headHeight = 2.25;
    this.extent = { width: 1.75, height: 2.15 };
    const fur = (color, extra = {}) => new THREE.MeshPhysicalMaterial({ color, roughness: 0.5, metalness: 0, clearcoat: 0.3,
      clearcoatRoughness: 0.42, sheen: 0.25, sheenRoughness: 0.55, sheenColor: new THREE.Color(0xffe6cc), ...extra });
    this.fur = fur;
    this.whiteMat = fur(WHITE);
    this.brownMat = fur(this.brown);

    this.body = new THREE.Group(); // hops, wiggles and spins
    this.body.scale.setScalar(S);
    this.root.add(this.body);
    this.surf = new HeadSurface();

    this.buildTorso(q);
    this.buildHead(q);
    this.buildLegs(q);
    this.buildTail(q);
    this.buildEars(q);
    this.setupFace(q);

    this.bubbleAnchor = new THREE.Object3D();
    this.bubbleAnchor.position.set(0, 0.66, 0);
    this.headGroup.add(this.bubbleAnchor);

    this.director.register({
      tailWag: { duration: 2.4, weight: 1.4, cooldown: 7, states: ["idle", "listening"] },
      earFlop: { duration: 1.8, weight: 1, cooldown: 10 },
      headTilt: { duration: 2.4, weight: 1.3, cooldown: 8, states: ["idle", "listening"] },
      pant: { duration: 3.2, weight: 0.9, cooldown: 14 },
      tongueOut: { duration: 2.2, weight: 0.6, cooldown: 18 },
      hop: { duration: 1.3, weight: 0.5, cooldown: 20, big: true },
      pawRaise: { duration: 2.6, weight: 0.6, cooldown: 18 },
      joy: { duration: 2.2, weight: 0.5, cooldown: 22 },
      curiousSniff: { duration: 2.6, weight: 0.8, cooldown: 14 },
      nodAlong: { duration: 1.4, weight: 1.6, cooldown: 3, states: ["speaking"] },
      pawTap: { duration: 1.3, weight: 1, cooldown: 6, states: ["speaking"] },
      wagBurst: { duration: 1.5, weight: 1.2, cooldown: 5, states: ["speaking"] },
    });
    // pure joy: happy almost all the time, curious sniffs, little celebrations
    this.setPersona({
      idleMoods: { happy: 4, celebrate: 1, surprised: 1, thinking: 1 },
      moodGestures: { happy: "tailWag", celebrate: "joy", surprised: "headTilt", thinking: "curiousSniff" },
      speechGestures: { happy: "wagBurst", laugh: "wagBurst", celebrate: "wagBurst", thinking: "nodAlong",
                        surprised: "pawTap" },
    });

    // animation state (preallocated: nothing is created per frame)
    this.excite = 0;
    this.grin = 0.3;
    this.wagPhase = 0;
    this.wagAmp = 0.12;
    this.wagFreq = 4;
    this.mouthEx = { open: 0, smile: 0, tongue: 0, blep: 0, wag: 0 };
    this.tmpV = new THREE.Vector3();
    this.tmpN = new THREE.Vector3();
    this.tmpQ = new THREE.Quaternion();
    this.root.updateMatrixWorld(true);
    for (const e of this.ears) e.root.getWorldPosition(e.prev);
  }

  // --- body: one soft sitting torso (chest, belly and rump), skinned to hips/chest/neck --
  buildTorso(q) {
    const seg = [32, 48, 64][q];
    const pts = profile([[0.0, 0.0], [0.26, 0.008], [0.35, 0.05], [0.375, 0.15], [0.365, 0.3], [0.33, 0.46], [0.285, 0.62],
      [0.268, 0.76], [0.232, 0.88], [0.13, 0.975], [0.0, 1.0]], [32, 48, 64][q]);
    const geo = latheBody(pts, { segments: seg, depth: 1.1, front: 0.84 });
    const box = frontUV(geo, { x0: -0.4, x1: 0.4, y0: 0, y1: 1.0, fade: [-0.32, -0.08] });
    // sitting posture: the rump sits further back than the chest (shear z by height)
    const pos = geo.attributes.position, nor = geo.attributes.normal;
    const zc = (y) => -0.1 + 0.12 * smooth(0, 0.9, y);
    // …and the chest swells forward over the tops of the front legs
    const fb = (y) => 1 + 0.2 * Math.exp(-(((y - 0.62) / 0.17) ** 2)) - 0.32 * Math.exp(-(((y - 0.12) / 0.22) ** 2));
    for (let i = 0; i < pos.count; i++) {
      const y = pos.getY(i), z0 = pos.getZ(i);
      let ny0 = nor.getY(i), nz0 = nor.getZ(i);
      if (z0 > 0) {
        const f = fb(y), df = (fb(y + 0.005) - fb(y - 0.005)) / 0.01;
        ny0 -= (z0 * df / f) * nz0;
        nz0 /= f;
        pos.setZ(i, z0 * f);
      }
      pos.setZ(i, pos.getZ(i) + zc(y));
      const dz = (zc(y + 0.005) - zc(y - 0.005)) / 0.01;
      const nx = nor.getX(i), ny = ny0 - dz * nz0, nz = nz0;
      const l = Math.hypot(nx, ny, nz);
      nor.setXYZ(i, nx / l, ny / l, nz / l);
    }
    const map = markingTexture(box, WHITE, [], { size: 16 });
    const mat = markedMaterial(map, this.brown, { roughness: 0.5, clearcoat: 0.3, clearcoatRoughness: 0.42,
      sheen: 0.25, sheenRoughness: 0.55, sheenColor: new THREE.Color(0xffe6cc) });
    this.bones = boneChain([0, 0.42, NECK_Y]);
    skinByHeight(geo, [
      (y) => 1 - smooth(0.15, 0.6, y),
      (y) => smooth(0.15, 0.6, y) * (1 - smooth(0.66, 0.9, y)),
      (y) => smooth(0.15, 0.6, y) * smooth(0.66, 0.9, y),
    ]);
    const skinned = new THREE.SkinnedMesh(geo, mat);
    skinned.add(this.bones[0]);
    this.body.add(skinned);
    this.body.updateMatrixWorld(true);
    skinned.bind(new THREE.Skeleton(this.bones));
    skinned.frustumCulled = false;
    [this.hips, this.chest, this.neck] = this.bones;
  }

  // --- head: SDF surface on a sphere, painted with the equirectangular coat pattern ------
  buildHead(q) {
    const surf = this.surf;
    const ws = [48, 72, 104][q], hs = [32, 48, 72][q];
    const g = new THREE.SphereGeometry(1, ws, hs, -Math.PI / 2);
    const pos = g.attributes.position, nor = g.attributes.normal;
    const jaw = new Float32Array(pos.count * 3);
    const d = new THREE.Vector3(), n = new THREE.Vector3();
    for (let i = 0; i < pos.count; i++) {
      d.fromBufferAttribute(pos, i).normalize();
      const r = surf.radial(d.x, d.y, d.z);
      const x = d.x * r, y = d.y * r, z = d.z * r;
      pos.setXYZ(i, x, y, z);
      surf.normal(x, y, z, n);
      nor.setXYZ(i, n.x, n.y, n.z);
      const w = jawW(y, z);
      jaw[i * 3 + 1] = -JAW * w;
      jaw[i * 3 + 2] = -JAW * 0.25 * w;
    }
    g.morphAttributes.position = [new THREE.Float32BufferAttribute(jaw, 3)];
    g.morphTargetsRelative = true;
    g.computeBoundingSphere();
    // coat pattern painted in the sphere's UV space from 3D shapes: seamless, crisp edges
    const LU = 96, LV = 48, lut = new Float32Array((LU + 1) * (LV + 1));
    const dirOf = (u, v, out) => {
      const th = Math.PI * (1 - v), ph = -Math.PI / 2 + 2 * Math.PI * u;
      return out.set(-Math.cos(ph) * Math.sin(th), Math.cos(th), Math.sin(ph) * Math.sin(th));
    };
    for (let j = 0; j <= LV; j++) for (let i = 0; i <= LU; i++) {
      dirOf(i / LU, j / LV, d);
      lut[j * (LU + 1) + i] = surf.radial(d.x, d.y, d.z);
    }
    const rAt = (u, v) => {
      const fx = Math.min(LU - 0.001, Math.max(0, u * LU)), fy = Math.min(LV - 0.001, Math.max(0, v * LV));
      const i = Math.floor(fx), j = Math.floor(fy), tx = fx - i, ty = fy - j, W = LU + 1;
      const a = lut[j * W + i] + (lut[j * W + i + 1] - lut[j * W + i]) * tx;
      const b = lut[(j + 1) * W + i] + (lut[(j + 1) * W + i + 1] - lut[(j + 1) * W + i]) * tx;
      return a + (b - a) * ty;
    };
    const white = (u, v) => {
      dirOf(u, v, d);
      const r = rAt(u, v);
      return whiteSDF(d.x * r, d.y * r, d.z * r);
    };
    const map = markingTexture({ x0: 0, x1: 1, y0: 0, y1: 1 }, this.brown, [{ color: WHITE, sdf: white }],
      { size: [256, 512, 1024][q], soft: [0.0025, 0.0018, 0.0012][q] });
    map.wrapS = THREE.RepeatWrapping;
    this.headMat = this.fur(0xffffff, { map });
    this.headMesh = new THREE.Mesh(g, this.headMat);
    this.headMesh.morphTargetInfluences = [0];
    this.headGroup = new THREE.Group();
    this.headGroup.position.set(HEAD.x, HEAD.y - NECK_Y, HEAD.z);
    this.headGroup.scale.setScalar(1.06);
    this.headGroup.add(this.headMesh);
    this.neck.add(this.headGroup);
  }

  // --- legs: front legs (shoulder, elbow, wrist) with round paws; haunches and hind feet --
  buildLegs(q) {
    const cs = [8, 12, 16][q], rs = [12, 18, 28][q];
    const upper = new THREE.CapsuleGeometry(0.13, 0.3, cs, rs);
    upper.translate(0, -0.17, 0);
    const fore = new THREE.CapsuleGeometry(0.128, 0.1, cs, rs);
    fore.translate(0, -0.065, 0);
    const paw = pawGeometry(q, 0.158, 0.09, 0.165, [-0.34, 0.0, 0.34]);
    paw.translate(0, 0, 0.05);
    this.legs = [];
    for (const side of [-1, 1]) {
      const shoulder = new THREE.Group();
      shoulder.position.set(side * 0.16, 0.6, 0.06);
      shoulder.rotation.z = side * 0.04;
      this.body.add(shoulder);
      shoulder.add(new THREE.Mesh(upper, this.whiteMat));
      const elbow = new THREE.Group();
      elbow.position.y = -0.34;
      shoulder.add(elbow);
      elbow.add(new THREE.Mesh(fore, this.whiteMat));
      const wrist = new THREE.Group();
      wrist.position.y = -0.21;
      elbow.add(wrist);
      const p = new THREE.Mesh(paw, this.whiteMat);
      p.rotation.y = side * 0.08;
      wrist.add(p);
      this.legs.push({ side, shoulder, elbow, wrist });
    }
    // haunches (brown) with the white hind feet peeking out in front
    const thigh = new THREE.SphereGeometry(1, [20, 28, 40][q], [14, 20, 28][q]);
    thigh.scale(0.14, 0.2, 0.25);
    const hind = pawGeometry(q, 0.105, 0.08, 0.15, [-0.3, 0.3]);
    for (const side of [-1, 1]) {
      const t = new THREE.Mesh(thigh, this.brownMat);
      t.position.set(side * 0.31, 0.2, -0.13);
      t.rotation.set(0.35, side * 0.12, side * 0.12);
      this.body.add(t);
      const f = new THREE.Mesh(hind, this.whiteMat);
      f.position.set(side * 0.36, 0.06, 0.04);
      f.rotation.y = side * 0.32;
      this.body.add(f);
    }
  }

  // --- tail: white, upright, five bones driven by springs ----------------------------
  buildTail(q) {
    const geo = tailGeometry(q);
    const H = [0, 0.1, 0.2, 0.3, 0.38];
    skinByHeight(geo, H.map((h, i) => (y) => {
      if (i === 0 && y <= h) return 1;
      if (i === H.length - 1 && y >= h) return 1;
      const span = i === 0 ? H[1] - H[0] : H[i] - H[i - 1];
      return Math.max(0, 1 - Math.abs(y - h) / span);
    }));
    this.tailBones = boneChain(H);
    const mesh = new THREE.SkinnedMesh(geo, this.whiteMat);
    mesh.position.set(0, 0.2, -0.43);
    mesh.add(this.tailBones[0]);
    this.hips.add(mesh);
    this.body.updateMatrixWorld(true);
    mesh.bind(new THREE.Skeleton(this.tailBones));
    mesh.frustumCulled = false;
    this.tailSprings = H.map(() => new Spring(420, 22));
    this.tailLift = new Spring(90, 11);
  }

  // --- ears: floppy brown flaps on three bones each, swinging on springs ---------------
  buildEars(q) {
    const L = 0.8;
    this.ears = [];
    for (const side of [-1, 1]) {
      const geo = earGeometry(q, side, L);
      skinByHeight(geo, [
        (y) => 1 - smooth(-0.06, -0.26, y),
        (y) => smooth(-0.06, -0.26, y) * (1 - smooth(-0.3, -0.52, y)),
        (y) => smooth(-0.06, -0.26, y) * smooth(-0.3, -0.52, y),
      ]);
      const bones = boneChain([0, -0.2, -0.42]);
      const mesh = new THREE.SkinnedMesh(geo, this.brownMat);
      mesh.position.set(side * 0.3, 0.41, -0.04);
      mesh.rotation.y = -side * 0.55;
      mesh.add(bones[0]);
      this.headGroup.add(mesh);
      this.body.updateMatrixWorld(true);
      mesh.bind(new THREE.Skeleton(bones));
      mesh.frustumCulled = false;
      this.ears.push({ side, mesh, root: bones[0], mid: bones[1], tip: bones[2],
        z: new Spring(110, 9), x: new Spring(110, 9), m: new Spring(140, 8), t: new Spring(160, 8),
        prev: new THREE.Vector3(), vel: new THREE.Vector3() });
    }
  }

  setupFace(q) {
    const surf = this.surf, h = this.headGroup, n = this.tmpN || new THREE.Vector3();
    const lashMat = new THREE.MeshStandardMaterial({ color: 0x24130b, roughness: 0.6 });
    const lashGeo = new THREE.TorusGeometry(0.142 * 1.07, 0.0075, 6, [16, 24, 32][q], Math.PI);
    lashGeo.rotateX(Math.PI / 2);
    for (const side of [-1, 1]) {
      const ex = side * 0.258, ey = 0.05, r = 0.142;
      const ez = surf.z(ex, ey);
      surf.normal(ex, ey, ez, n);
      const eye = new Eye({ radius: r, iris: 0x2a170e, lid: this.brown, irisSize: 1.22, pupilSize: 0.72, quality: q });
      eye.group.position.set(ex - n.x * r * 0.42, ey - n.y * r * 0.42, ez - n.z * r * 0.42);
      eye.group.rotation.set(-0.06, side * 0.2, 0);
      eye.group.scale.set(1, 1.1, 0.62);
      eye.shines[0].scale.setScalar(1.15);
      eye.shines[1].scale.setScalar(1.1);
      for (const sh of eye.shines) sh.material.toneMapped = false; // crisp white reflections
      Object.assign(eye.upper.material, { sheen: 0.1, clearcoat: 0.15, roughness: 0.55 });
      eye.upper.material.color.multiplyScalar(0.92);
      // lash line on the lid rims: a closed or squinting eye reads as a soft line
      const lash = new THREE.Mesh(lashGeo, lashMat);
      eye.upper.add(lash);
      const lowLash = new THREE.Mesh(lashGeo, lashMat);
      lowLash.scale.set(1, 0.6, 1);
      if (q > 0) eye.lower.add(lowLash); // low quality: fewer draw calls
      h.add(eye.group);
      this.eyes.push(eye);
    }
    const browMat = new THREE.MeshStandardMaterial({ color: BROW, roughness: 0.7 });
    for (const side of [-1, 1]) {
      const b = new ArcBrow(surf, side, q, browMat);
      h.add(b.mesh);
      this.brows.push(b);
    }
    // nose: broad rounded inverted triangle, glossy almost-black
    const ng = new THREE.SphereGeometry(1, [20, 28, 40][q], [14, 20, 28][q]);
    const np = ng.attributes.position;
    for (let i = 0; i < np.count; i++) {
      const x = np.getX(i), y = np.getY(i), z = np.getZ(i);
      const taper = y < 0 ? 1 - 0.42 * (-y) ** 1.2 : 1 - 0.08 * y;
      np.setXYZ(i, x * 0.142 * taper, y * 0.088 + (y > 0 ? -0.013 * x * x : 0), z * 0.098);
    }
    weldNormals(ng);
    this.nose = new THREE.Mesh(ng, new THREE.MeshPhysicalMaterial({ color: 0x18151a, roughness: 0.26, clearcoat: 1, clearcoatRoughness: 0.08, envMapIntensity: 1.2 }));
    this.noseBase = new THREE.Vector3(0, NOSE_Y, surf.z(0, NOSE_Y) - 0.012);
    this.nose.position.copy(this.noseBase);
    this.nose.rotation.x = -0.28;
    h.add(this.nose);
    // philtrum: a short line from the nose down to the lip
    const pts = [];
    for (let i = 0; i <= 6; i++) { const y = NOSE_Y - 0.06 + (MOUTH_Y + 0.004 - NOSE_Y + 0.06) * i / 6; pts.push(new THREE.Vector3(0, y, surf.z(0, y) + 0.002)); }
    const phil = new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 8, 0.0075, 6, false),
      new THREE.MeshBasicMaterial({ color: 0x2e0a10 }));
    h.add(phil);
    this.mouth = new DogMouth(surf, q, 0xdc4f6b);
    h.add(this.mouth.group);
  }

  applyFace(t) {
    super.applyFace(t);
    // highlights go before the lid edge reaches them (they sit in front of the iris)
    const c = this.cur, blink = this.blinkAmount(), wide = c.wide;
    const upper = Math.max(c.lidUp * (1 - wide), blink), lower = c.lidLow * (1 - wide) + blink * 0.15;
    for (const e of this.eyes) {
      e.shines[0].visible = upper < 0.34;
      e.shines[1].visible = upper < 0.62 && lower < 0.5;
    }
  }

  hear(text) {
    if (Character.mentionsTech(text)) {
      // Linux, computers, code: the puppy can't contain itself
      this.excite = 2.6;
      this.setEmotion("happy", 0.95, 3.5);
      this.director.play("joy");
    } else if (Math.random() < 0.35) this.director.play("headTilt");
  }

  animate(dt, t, state) {
    const c = this.cur, d = this.director, w = d.w, a = d.amp;
    const g = d.curve(), act = this.actionCurve();
    const still = d.state === "emergency";
    const talk = c.speak;
    const emo = this.emotion;
    this.excite = Math.max(0, this.excite - dt);
    const ex = clamp01(this.excite);
    const glad = (emo === "happy" || emo === "celebrate" || emo === "laugh") ? (this.intensity ?? 0.7) : 0;
    const cross = emo === "annoyed" ? 1 : 0;
    const side = (this.director.gesture && (this.director.gesture.side ??= Math.random() < 0.5 ? -1 : 1)) || 1;

    // ---- whole body: hops, spins, wiggles -------------------------------------------
    let jump = 0, spin = 0, squash = 0, wiggle = 0;
    if (!still) {
      if (g.name === "hop") jump = Math.abs(Math.sin(g.p * Math.PI * 2)) * 0.2 * Math.min(1, g.s * 2);
      if (act.name === "celebrate") {
        if (act.gentle) jump = Math.abs(Math.sin(act.p * Math.PI * 2)) * 0.06;
        else { jump = Math.abs(Math.sin(act.p * Math.PI * 3)) * 0.22; spin = smooth(0.1, 0.85, act.p) * Math.PI * 2; }
      }
      if (act.name === "surprised") { jump = act.s * (act.gentle ? 0.05 : 0.16); squash = -act.s * 0.05; }
      if (act.name === "happy") jump = Math.abs(Math.sin(act.p * Math.PI * 2)) * 0.06;
      if (g.name === "joy") { jump = Math.abs(Math.sin(g.p * Math.PI * 4)) * 0.05 * g.s; wiggle = Math.sin(t * 13) * 0.09 * g.s; }
      if (act.name === "laugh") { squash = Math.sin(t * 26) * 0.03 * act.s; wiggle += Math.sin(t * 9) * 0.04 * act.s; }
      wiggle += Math.sin(t * 11) * 0.035 * ex;
    }
    squash += d.breath * 0.006 * a;
    const air = Math.min(1, jump * 6);
    this.root.position.y = damp(this.root.position.y, jump, 18, dt);
    if (!spin && this.body.rotation.y > Math.PI) this.body.rotation.y -= Math.PI * 2; // finished a spin: no rewind
    this.body.rotation.y = spin || damp(this.body.rotation.y, d.head.x * 0.12 + wiggle * 0.6, 6, dt);
    this.body.rotation.z = damp(this.body.rotation.z, d.lean.x * 0.035 * a + wiggle, 10, dt);
    this.hips.scale.set(1 - squash * 0.5, 1 + squash, 1 - squash * 0.5);

    // ---- chest: lean in, sniff, laugh back, breathe (quick panting when excited) --------
    const pant = still ? 0 : Math.max(G2(g, "pant"), glad * 0.35 * w.idle, ex * 0.6, A2(act, "celebrate") * 0.4);
    let chestX = d.lean.z * 0.05 * a + w.listening * 0.06 - w.paused * 0.03 + G2(g, "curiousSniff") * 0.2 - A2(act, "laugh") * 0.1 - G2(g, "pawRaise") * 0.05;
    this.chest.rotation.x = damp(this.chest.rotation.x, chestX, 6, dt);
    this.chest.rotation.z = damp(this.chest.rotation.z, d.lean.x * 0.03 + wiggle * 0.4, 5, dt);
    const breathe = 1 + d.breath * 0.012 * a + pant * Math.sin(t * 15) * 0.014;
    this.chest.scale.set(breathe, 1, breathe);

    // ---- head ---------------------------------------------------------------------
    let yaw = d.head.x * 0.6, pitch = -d.head.y * 0.32 + d.beat * 0.08 - talk * 0.03, roll = c.tilt * 0.9;
    if (!still) {
      roll += G2(g, "headTilt") * 0.42 * side + w.listening * 0.12 + w.thinking * 0.22 + A2(act, "confused") * 0.3;
      pitch += G2(g, "curiousSniff") * 0.16 + w.paused * 0.16 + w.reading * 0.07 + w.listening * 0.04 - A2(act, "surprised") * 0.12;
      pitch += Math.sin(g.p * Math.PI * 4) * 0.09 * G2(g, "nodAlong") + pant * Math.sin(t * 15) * 0.012;
      yaw += Math.sin(t * 2.2) * 0.12 * G2(g, "curiousSniff") + cross * 0.22 * A2(act, "annoyed");
      if (act.name === "laugh") { pitch -= 0.16 * act.s; roll += Math.sin(t * 20) * 0.04 * act.s; }
      if (g.name === "joy") roll += Math.sin(t * 12) * 0.12 * g.s;
      if (g.name === "tongueOut") roll += 0.12 * g.s * side;
      roll += 0.08 * G2(g, "pawRaise");
    }
    this.neck.rotation.y = damp(this.neck.rotation.y, yaw, 7, dt);
    this.neck.rotation.x = damp(this.neck.rotation.x, pitch, 9, dt);
    this.neck.rotation.z = damp(this.neck.rotation.z, roll, 7, dt);

    // nose twitch while sniffing
    const sniff = G2(g, "curiousSniff");
    const tw = sniff * (0.5 + 0.5 * Math.sin(t * 34)) * (Math.sin(t * 5) > -0.3 ? 1 : 0);
    this.nose.position.y = this.noseBase.y + tw * 0.008;
    this.nose.scale.set(1 + tw * 0.06, 1 - tw * 0.04, 1);

    this.animateLegs(dt, t, g, act, still, air, side);
    this.animateTail(dt, t, g, act, still, glad, cross, ex);
    this.animateEars(dt, t, g, act, still, glad, cross, ex);

    // ---- mouth extras: the open friendly grin of the reference, panting, the blep ------
    const friendly = (emo === "neutral" || glad > 0) && d.state !== "thinking" && !still ? 1 : 0;
    const stateK = w.idle + w.listening * 0.6 + w.reacting + w.celebrating + w.speaking * 0.25 + w.reading * 0.15;
    const resting = Math.sin(t * 0.21) * Math.sin(t * 0.33) > 0.3 && glad === 0 ? 0.25 : 1; // now and then a closed smile
    this.grin = damp(this.grin, (0.46 + glad * 0.16) * friendly * Math.min(1, stateK) * resting, 4, dt);
    const m = this.mouthEx;
    m.open = this.grin + pant * (0.22 + Math.sin(t * 15) * 0.07) + G2(g, "joy") * 0.2 + A2(act, "laugh") * Math.abs(Math.sin(t * 13)) * 0.15;
    m.smile = this.grin * 0.4 + G2(g, "joy") * 0.3;
    m.tongue = Math.max(G2(g, "pant"), pant * 0.5, G2(g, "joy") * 0.5);
    m.blep = G2(g, "tongueOut");
    m.wag = pant;
    if (g.name === "tongueOut") m.open *= 1 - g.s;
    this.mouth.update(m, t);
    this.headMesh.morphTargetInfluences[0] = this.mouth.jaw;
  }

  animateLegs(dt, t, g, act, still, air, side) {
    const d = this.director;
    for (const leg of this.legs) {
      let sx = -0.15, el = 0, wr = 0.15;
      if (!still) {
        const lead = leg.side === 1; // the paw that gives "five"
        if (g.name === "pawRaise" && lead) {
          const k = g.s;
          sx = -0.15 - 1.45 * k + Math.sin(t * 9) * 0.07 * smooth(0.35, 0.5, g.p) * k;
          el = -0.45 * k; wr = 0.15 + 0.2 * k;
        }
        if (g.name === "pawTap" && leg.side === side) { sx -= 0.5 * g.s; el = 0.75 * g.s; wr += 0.2 * g.s; }
        if (d.state === "thinking" && lead) { sx -= 0.5 * d.w.thinking; el = 1.0 * d.w.thinking; wr += 0.45 * d.w.thinking; }
        if (act.name === "annoyed" && !lead) sx -= 0.3 * Math.abs(Math.sin(t * 12)) * act.s;
        if (act.name === "celebrate" || g.name === "joy") sx -= Math.abs(Math.sin(t * 9 + leg.side)) * 0.18 * Math.max(act.name === "celebrate" ? act.s : 0, g.name === "joy" ? g.s : 0);
        sx -= air * 0.25;
        el += air * 0.35;
        sx -= d.beat * 0.12 * (leg.side === side ? 1 : 0);
      }
      leg.shoulder.rotation.x = damp(leg.shoulder.rotation.x, sx, 10, dt);
      leg.elbow.rotation.x = damp(leg.elbow.rotation.x, el, 10, dt);
      leg.wrist.rotation.x = damp(leg.wrist.rotation.x, wr, 10, dt);
    }
  }

  animateTail(dt, t, g, act, still, glad, cross, ex) {
    const d = this.director, w = d.w;
    // wag amplitude / speed: gentle sway at rest, fast when happy, barely moving when cross
    let amp = 0.14, freq = 4.5;
    const fast = Math.max(glad * 0.9, G2(g, "tailWag"), G2(g, "joy"), G2(g, "wagBurst") * 0.85, A2(act, "celebrate"), A2(act, "laugh") * 0.8, A2(act, "happy"), ex);
    amp += fast * 0.3;
    freq += fast * 13;
    if (cross) { amp = 0.04; freq = 2.2; }
    amp *= 1 - w.paused * 0.8;
    freq *= 1 - w.paused * 0.6;
    amp += w.listening * 0.06;
    if (still) { amp = 0.02; freq = 1.5; }
    this.wagAmp = damp(this.wagAmp, amp * Math.min(1.3, d.amp), 5, dt);
    this.wagFreq = damp(this.wagFreq, freq, 4, dt);
    this.wagPhase += dt * this.wagFreq;
    // carriage: proud and upright when happy, low when annoyed or sleepy
    const lift = this.tailLift.step(-0.4 + glad * 0.14 + A2(act, "surprised") * 0.25 - cross * 0.85 - w.paused * 0.55 + this.root.position.y * 1.2, dt);
    const curl = 0.2 + glad * 0.06 - cross * 0.36 - w.paused * 0.12;
    for (let i = 0; i < this.tailBones.length; i++) {
      const b = this.tailBones[i];
      const wag = this.wagAmp * Math.sin(this.wagPhase - i * 0.55) * (i === 0 ? 1 : 0.5);
      b.rotation.z = this.tailSprings[i].step(wag, dt);
      b.rotation.x = i === 0 ? lift : curl;
    }
  }

  animateEars(dt, t, g, act, still, glad, cross, ex) {
    const d = this.director, w = d.w;
    let perk = w.listening * 0.55 + A2(act, "surprised") + glad * 0.18 + ex * 0.45 + G2(g, "curiousSniff") * 0.3;
    if (g.name === "earFlop") perk += (g.p < 0.4 ? smooth(0, 0.14, g.p) : 0) * 0.9;
    const droop = cross * 0.8 + w.paused * 0.6 + w.emergency * 0.15;
    const sideUp = (A2(act, "confused") + w.thinking * 0.7 + G2(g, "headTilt") * 0.6);
    const tilt = (this.director.gesture && this.director.gesture.side) || 1;
    this.headGroup.getWorldQuaternion(this.tmpQ).invert(); // velocities in head space
    for (const e of this.ears) {
      // inertia: the flaps lag behind the head (velocity of the ear root, world space)
      e.root.getWorldPosition(this.tmpV);
      const inv = 1 / Math.max(dt, 1e-3);
      e.vel.set((this.tmpV.x - e.prev.x) * inv, (this.tmpV.y - e.prev.y) * inv, (this.tmpV.z - e.prev.z) * inv);
      e.prev.copy(this.tmpV);
      e.vel.applyQuaternion(this.tmpQ).clampLength(0, 5);
      const up = e.side === tilt ? sideUp : -sideUp * 0.3;
      const zT = 1.0 + Math.min(1, perk) * 0.3 - droop * 0.32 + up * 0.35 - e.side * e.vel.x * 0.12 - e.vel.y * 0.16;
      const xT = droop * 0.35 - perk * 0.12 + e.vel.z * 0.1;
      const z = e.z.step(still ? 0.98 : zT, dt);
      const x = e.x.step(still ? 0 : xT, dt);
      const m = e.m.step(-0.55 + Math.min(1, perk) * 0.22 - e.z.v * 0.05, dt);
      const tp = e.t.step(-0.12 - e.m.v * 0.05, dt);
      e.root.rotation.set(x, 0, e.side * z);
      e.mid.rotation.set(0, 0, e.side * m);
      e.tip.rotation.set(0, 0, e.side * tp);
    }
  }
}

const G2 = (g, name) => (g.name === name ? g.s : 0);
const A2 = (act, name) => (act.name === name ? act.s : 0);
