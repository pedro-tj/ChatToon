// Coruja — a wise purple cartoon owl perched on a twig (original procedural model).
// Vinyl-toy look after the reference: a big round head with pointed ear tufts, huge
// amber eyes set in raised rims, a small hooked beak, a round body with a row of chest
// spots, wings folded on the sides (shoulder + feather fan, they open and flap) and
// toes gripping a 3D branch. The branch and the feet stay put; the body moves above.
import * as THREE from "../../vendor/three/three.module.js";
import { Character, Spring, clamp01, damp, skin, smooth } from "../rig.js";
import {
  boneChain, frontUV, latheBody, markedMaterial, markingTexture, profile, radiusAt, sdCircle, sdEllipse, skinByHeight, smin,
} from "./shapes.js";

const DEPTH = 0.88; // body cross-section (z / x)
const BODY_Z = -0.02;
const PIVOT_Y = 0.36; // the body rocks/bobs around this point, level with the feet
const NECK_Y = 1.2; // head bone (world height at rest)
const CHEST_Y = 0.72;
const BRANCH_R = 0.068;
const FEET_X = 0.17;
const TAU = Math.PI * 2;

// ------------------------------------------------------------------ small helpers
// Merge indexed/non-indexed geometries that share the same attributes.
function merge(geos) {
  const parts = geos.map((g) => (g.index ? g : g.toNonIndexed()));
  const names = Object.keys(parts[0].attributes);
  const out = new THREE.BufferGeometry();
  let total = 0;
  for (const g of parts) total += g.attributes.position.count;
  for (const n of names) {
    const size = parts[0].attributes[n].itemSize;
    const arr = new Float32Array(total * size);
    let o = 0;
    for (const g of parts) { arr.set(g.attributes[n].array, o); o += g.attributes[n].count * size; }
    out.setAttribute(n, new THREE.BufferAttribute(arr, size));
  }
  if (parts.every((g) => g.index)) {
    const idx = [];
    let base = 0;
    for (const g of parts) { for (const i of g.index.array) idx.push(i + base); base += g.attributes.position.count; }
    out.setIndex(idx);
  }
  parts.forEach((g, i) => { if (g !== geos[i]) g.dispose(); });
  out.computeBoundingSphere();
  return out;
}

function paint(geo, color) {
  const n = geo.attributes.position.count, arr = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) { arr[i * 3] = color.r; arr[i * 3 + 1] = color.g; arr[i * 3 + 2] = color.b; }
  geo.setAttribute("color", new THREE.BufferAttribute(arr, 3));
  return geo;
}

// Spherical cap facing +Z (iris, pupil).
function cap(radius, angle, segments) {
  const g = new THREE.SphereGeometry(radius, segments, Math.max(6, segments / 3), 0, TAU, 0, angle);
  g.rotateX(Math.PI / 2);
  return g;
}

// Radial iris gradient (sphere-cap UV v runs from the pupil to the rim) with fine streaks.
function irisTexture(inner, mid, outer) {
  const c = document.createElement("canvas");
  c.width = 64; c.height = 64;
  const g = c.getContext("2d");
  const img = g.createImageData(64, 64);
  const A = new THREE.Color(inner), B = new THREE.Color(mid), C = new THREE.Color(outer), tmp = new THREE.Color();
  for (let y = 0; y < 64; y++) {
    const f = y / 63; // 0 = centre (pupil), 1 = rim
    if (f < 0.55) tmp.copy(A).lerp(B, smooth(0.2, 0.55, f));
    else tmp.copy(B).lerp(C, smooth(0.62, 0.97, f));
    for (let x = 0; x < 64; x++) {
      const u = x / 64;
      const streak = 0.92 + 0.08 * Math.sin(u * TAU * 23 + Math.sin(u * TAU * 5) * 2) * smooth(0.25, 0.6, f) * (1 - smooth(0.85, 1, f));
      const o = (y * 64 + x) * 4;
      img.data[o] = Math.min(255, Math.round(Math.pow(tmp.r * streak, 1 / 2.2) * 255));
      img.data[o + 1] = Math.min(255, Math.round(Math.pow(tmp.g * streak, 1 / 2.2) * 255));
      img.data[o + 2] = Math.min(255, Math.round(Math.pow(tmp.b * streak, 1 / 2.2) * 255));
      img.data[o + 3] = 255;
    }
  }
  g.putImageData(img, 0, 0);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

// Blend a wing pose towards a target (k = weight 0..1); no allocations per frame.
function set(P, raise, pitch, twist, elbow, spread, k, yaw = 0) {
  P.yaw += (yaw - P.yaw) * k;
  P.raise += (raise - P.raise) * k; P.pitch += (pitch - P.pitch) * k; P.twist += (twist - P.twist) * k;
  P.elbow += (elbow - P.elbow) * k; P.spread += (spread - P.spread) * k;
}

// ------------------------------------------------------------------ eye
// Big owl eye: cream sclera ring, amber gradient iris, a pupil that dilates, fixed glossy
// highlights and heavy lids in the facial-disc colour (same interface as rig.Eye).
class OwlEye {
  constructor({ radius, lid, iris, arcColor, quality }) {
    const seg = [16, 26, 40][quality];
    this.radius = radius;
    this.group = new THREE.Group();
    this.ball = new THREE.Group();
    this.group.add(this.ball);
    const sclera = new THREE.Mesh(new THREE.SphereGeometry(radius, seg, Math.round(seg * 0.75)),
      new THREE.MeshPhysicalMaterial({ color: 0xfff0c4, roughness: 0.14, clearcoat: 1, clearcoatRoughness: 0.05 }));
    const irisMesh = new THREE.Mesh(cap(radius * 1.004, 0.9, seg),
      new THREE.MeshPhysicalMaterial({ map: iris, roughness: 0.22, clearcoat: 1, clearcoatRoughness: 0.04 }));
    this.pupil = new THREE.Mesh(cap(radius * 1.012, 0.42, seg),
      new THREE.MeshPhysicalMaterial({ color: 0x0b0710, roughness: 0.1, clearcoat: 1 }));
    this.ball.add(sclera, irisMesh, this.pupil);
    const shineMat = new THREE.MeshBasicMaterial({ color: 0xffffff });
    const shine = new THREE.Mesh(new THREE.SphereGeometry(radius * 0.2, 14, 10), shineMat);
    shine.scale.set(1, 0.8, 0.35);
    shine.position.set(-radius * 0.34, radius * 0.38, radius * 0.86);
    // low quality: one highlight (an empty placeholder keeps setLids simple)
    const shine2 = quality > 0 ? new THREE.Mesh(new THREE.SphereGeometry(radius * 0.08, 10, 8), shineMat) : new THREE.Object3D();
    shine2.scale.set(1, 1, 0.4);
    shine2.position.set(radius * 0.3, -radius * 0.32, radius * 0.9);
    this.group.add(shine, shine2);
    this.shines = [shine, shine2];
    const lidMat = skin(lid, { side: THREE.DoubleSide, roughness: 0.5, clearcoat: 0.3, sheen: 0.4 });
    this.upper = new THREE.Mesh(new THREE.SphereGeometry(radius * 1.07, seg, seg / 2, 0, TAU, 0, Math.PI / 2), lidMat);
    this.lower = new THREE.Mesh(new THREE.SphereGeometry(radius * 1.065, seg, seg / 2, 0, TAU, Math.PI / 2, Math.PI / 2), lidMat);
    this.group.add(this.upper, this.lower);
    // laughing: closed lids with a happy "∩" crease instead of a half-covered eye
    this.arc = new THREE.Mesh(new THREE.TorusGeometry(radius * 0.55, radius * 0.09, 8, [12, 18, 24][quality], Math.PI),
      new THREE.MeshPhysicalMaterial({ color: arcColor, roughness: 0.4, clearcoat: 0.6 }));
    this.arc.position.set(0, -radius * 0.18, radius * 1.02);
    this.arc.scale.set(1, 0.8, 0.5);
    this.arc.visible = false;
    this.group.add(this.arc);
  }

  setLids(upper, lower, tilt = 0) {
    const happy = lower > 0.5 && upper < 0.85;
    this.arc.visible = happy;
    if (happy) { upper = 1; lower = 0.3; tilt = 0; }
    this.upper.rotation.set(THREE.MathUtils.lerp(-1.3, 1.62, upper), 0, tilt);
    this.lower.rotation.set(THREE.MathUtils.lerp(1.2, -0.22, lower), 0, 0);
    this.shines[0].visible = upper < 0.42;
    this.shines[1].visible = lower < 0.62 && upper < 0.85;
  }

  look(x, y) { this.ball.rotation.set(-y * 0.4, x * 0.5, 0); }

  // s < 1 contracts (surprise), > 1 dilates (delight). z compensation keeps the cap on the iris.
  setPupil(s) {
    const sin2 = 0.166; // sin²(0.42)
    const kz = Math.sqrt(Math.max(1, (0.985 - s * s * sin2) / (1 - sin2)));
    this.pupil.scale.set(s, s, kz);
  }
}

// ------------------------------------------------------------------ beak
// Small hooked beak, two mandibles (same interface as Mouth). Built along +Z, tilted down.
class OwlBeak {
  constructor(quality) {
    const seg = [12, 18, 26][quality];
    const topMat = new THREE.MeshPhysicalMaterial({ color: 0xff8d1f, roughness: 0.36, clearcoat: 0.6, clearcoatRoughness: 0.25 });
    const lowMat = new THREE.MeshPhysicalMaterial({ color: 0xdf6410, roughness: 0.4, clearcoat: 0.45, clearcoatRoughness: 0.3 });
    this.group = new THREE.Group();
    this.tilt = 0.45;
    this.size = 1;
    const mandible = (w, h, len, hook) => {
      const g = new THREE.SphereGeometry(1, seg, seg);
      g.rotateX(Math.PI / 2); // poles on ±Z
      const p = g.attributes.position;
      for (let i = 0; i < p.count; i++) {
        const x = p.getX(i), y = p.getY(i), z = p.getZ(i);
        const u = (z + 1) / 2; // 0 back … 1 tip
        const taper = 1 - u * 0.35;
        p.setXYZ(i, x * w * taper, y * h * taper - hook * u * u * u, Math.pow(u, 0.85) * len - len * 0.25);
      }
      g.computeVertexNormals();
      return g;
    };
    this.upper = new THREE.Mesh(mandible(0.08, 0.062, 0.19, 0.08), topMat);
    this.lowerPivot = new THREE.Group();
    this.lowerPivot.position.set(0, -0.03, -0.035);
    this.lower = new THREE.Mesh(mandible(0.058, 0.034, 0.19, 0.03), lowMat);
    this.lower.position.set(0, -0.012, 0.0);
    this.lowerPivot.add(this.lower);
    this.inside = new THREE.Mesh(new THREE.SphereGeometry(1, 12, 8), new THREE.MeshBasicMaterial({ color: 0x4a0f22 }));
    this.inside.scale.set(0.055, 0.04, 0.085);
    this.inside.position.set(0, -0.035, 0.0);
    // tongue/mouth lining on top of the lower mandible: shows as the beak opens
    this.tongue = new THREE.Mesh(new THREE.SphereGeometry(1, 12, 8), new THREE.MeshBasicMaterial({ color: 0x8a2238 }));
    this.tongue.scale.set(0.042, 0.016, 0.075);
    this.tongue.position.set(0, 0.012, 0.035);
    this.lowerPivot.add(this.tongue);
    this.group.add(this.upper, this.lowerPivot, this.inside);
  }

  set({ open, smile, frown, round }) {
    const jaw = Math.min(1, open * 0.9 + round * 0.55);
    this.lowerPivot.rotation.x = jaw * 0.85;
    this.upper.rotation.x = -jaw * 0.3;
    this.group.rotation.x = this.tilt - jaw * 0.3; // the beak lifts as it opens: the gap faces the viewer
    const k = this.size;
    this.group.scale.set(k * (1 + smile * 0.05 - frown * 0.04 + round * 0.06), k, k);
  }
}

// ------------------------------------------------------------------ the owl
export class Owl extends Character {
  constructor(options) {
    super(options);
    const q = this.quality;
    const seg = [26, 42, 60][q];
    this.headHeight = 2.42;
    this.extent = { width: 1.65, height: 2.35 };

    // palette: everything derives from the main colour (the app can override it)
    const base = new THREE.Color(options.color || "#3a1cb0");
    const hsl = {};
    base.getHSL(hsl);
    const shade = (dh, ds, dl) => new THREE.Color().setHSL((hsl.h + dh + 1) % 1, clamp01(hsl.s + ds), clamp01(hsl.l + dl));
    const C = this.colors = {
      plumage: base.clone(),
      back: shade(0.03, 0.0, -0.02), // sides and back drift towards violet-magenta
      belly: shade(-0.04, -0.2, -0.03),
      face: shade(-0.025, -0.1, 0.02),
      disc: shade(-0.035, -0.12, 0.07),
      wing: shade(0.028, 0.02, -0.04),
      feather: shade(0.02, 0.02, -0.12),
      tip: shade(0.06, 0.04, -0.03),
      spot: shade(0.0, -0.08, 0.1),
      feet: shade(-0.03, -0.05, -0.12),
    };
    const plush = (color, extra = {}) => new THREE.MeshPhysicalMaterial({ color, roughness: 0.5, clearcoat: 0.32,
      clearcoatRoughness: 0.42, sheen: 0.55, sheenRoughness: 0.42, sheenColor: new THREE.Color(0xff8ce8), ...extra });
    this.plush = plush;

    this.buildBranchAndFeet(q, C);

    // --- one soft body with the head built in, skinned to hips/chest/head bones --
    // (the neck twists smoothly when the owl turns its head far to the side)
    this.body = new THREE.Group(); // rocks and bobs above the feet
    this.body.position.set(0, PIVOT_Y, BODY_Z);
    this.root.add(this.body);
    const pts = profile([[0, 0.08], [0.32, 0.1], [0.54, 0.2], [0.68, 0.38], [0.725, 0.58], [0.7, 0.8], [0.62, 1.0],
      [0.565, 1.16], [0.59, 1.34], [0.625, 1.54], [0.61, 1.72], [0.52, 1.88], [0.33, 1.98], [0, 2.01]], 72);
    this.pts = pts;
    const bodyGeo = latheBody(pts, { segments: seg, depth: DEPTH });
    // flatten the lower front a little so the branch passes in front of the belly
    {
      const p = bodyGeo.attributes.position, nr = bodyGeo.attributes.normal;
      for (let i = 0; i < p.count; i++) {
        const z = p.getZ(i);
        if (z <= 0) continue;
        const f = this.frontSquash(p.getY(i));
        p.setZ(i, z * f);
        const nz = nr.getZ(i) / f, nx = nr.getX(i), ny = nr.getY(i), l = Math.hypot(nx, ny, nz);
        nr.setXYZ(i, nx / l, ny / l, nz / l);
      }
    }
    const box = frontUV(bodyGeo, { x0: -0.7, x1: 0.7, y0: 0.05, y1: 2.05, fade: [0.0, 0.42] });
    this.EYE = { x: 0.282, y: 1.635, r: 0.215 };
    const E = this.EYE;
    const face = (x, y) => smin(smin(sdCircle(x, y, -E.x, E.y, 0.28), sdCircle(x, y, E.x, E.y, 0.28), 0.12),
      sdEllipse(x, y, 0, 1.46, 0.16, 0.12), 0.12);
    // belly: three nested ellipses fake a soft gradient into the plumage
    const bellyLayer = (k, rx, ry) => ({ color: C.plumage.clone().lerp(C.belly, k), sdf: (x, y) => sdEllipse(x, y, 0, 0.56, rx, ry) });
    const map = markingTexture(box, C.plumage, [bellyLayer(0.35, 0.6, 0.62), bellyLayer(0.7, 0.53, 0.55), bellyLayer(1, 0.46, 0.48),
      { color: C.face, sdf: face }],
      { size: [256, 512, 1024][q], soft: 0.05 });
    // the belly blends very softly into the plumage (wide anti-alias band)
    const bodyMat = markedMaterial(map, C.back, { roughness: 0.5, clearcoat: 0.32, clearcoatRoughness: 0.42,
      sheen: 0.55, sheenRoughness: 0.42, sheenColor: new THREE.Color(0xff8ce8) });
    bodyGeo.translate(0, -PIVOT_Y, 0);
    this.bones = boneChain([0, CHEST_Y - PIVOT_Y, NECK_Y - PIVOT_Y]);
    const Y = (fn) => (y) => fn(y + PIVOT_Y);
    skinByHeight(bodyGeo, [
      Y((y) => 1 - smooth(0.32, 0.72, y)),
      Y((y) => smooth(0.32, 0.72, y) * (1 - smooth(1.13, 1.37, y))),
      Y((y) => smooth(0.32, 0.72, y) * smooth(1.13, 1.37, y)),
    ]);
    const skinned = new THREE.SkinnedMesh(bodyGeo, bodyMat);
    skinned.add(this.bones[0]);
    skinned.bind(new THREE.Skeleton(this.bones));
    skinned.frustumCulled = false;
    this.body.add(skinned);
    this.skinned = skinned;
    const [hips, chest, head] = this.bones;
    this.hips = hips; this.chest = chest; this.head = head;
    this.headGroup = head;
    this.surf = (x, y) => DEPTH * (this.frontSquash(y)) * Math.sqrt(Math.max(0, radiusAt(pts, y) ** 2 - x * x));

    // tail: a short feather fan behind the branch (mostly hidden: skipped on low quality)
    if (q > 0) {
      const tailGeo = new THREE.SphereGeometry(1, seg / 2, seg / 3);
      tailGeo.scale(0.19, 0.2, 0.05);
      tailGeo.translate(0, -0.16, 0);
      const tail = new THREE.Mesh(tailGeo, plush(C.feather));
      tail.position.set(0, 0.3 - PIVOT_Y, -0.5);
      tail.rotation.x = -0.75;
      hips.add(tail);
    }

    // chest spots (one instanced draw), on the chest bone
    const spotGeo = new THREE.SphereGeometry(0.068, [10, 14, 20][q], [6, 10, 14][q]);
    spotGeo.scale(1, 1, 0.45);
    const spots = new THREE.InstancedMesh(spotGeo, plush(C.spot, { sheen: 0.3, clearcoat: 0.45 }), 5);
    const m4 = new THREE.Matrix4(), qn = new THREE.Quaternion(), pos = new THREE.Vector3(), nrm = new THREE.Vector3(), one = new THREE.Vector3(1, 1, 1);
    for (let i = 0; i < 5; i++) {
      const x = (i - 2) * 0.155, y = 0.98 - Math.abs(i - 2) * 0.012;
      const z = this.surf(x, y);
      pos.set(x, y - CHEST_Y, z - 0.01);
      nrm.set(x / DEPTH / DEPTH, 0.22, z).normalize();
      qn.setFromUnitVectors(new THREE.Vector3(0, 0, 1), nrm);
      spots.setMatrixAt(i, m4.compose(pos, qn, one));
    }
    chest.add(spots);

    // --- wings: shoulder → (mirror) → coverts + elbow → primary fan --------------
    this.buildWings(q, C, plush);

    // ear tufts on springs, rooted in the top corners of the head
    const tuftGeo = new THREE.LatheGeometry(profile([[0, -0.14], [0.21, -0.12], [0.225, 0.0], [0.18, 0.16], [0.105, 0.32], [0.04, 0.44], [0, 0.48]], 20), [10, 16, 22][q]);
    const tp = tuftGeo.attributes.position;
    for (let i = 0; i < tp.count; i++) {
      const y = tp.getY(i), k = clamp01(y / 0.48);
      tp.setZ(i, tp.getZ(i) * 0.6 - k * k * 0.07);
      tp.setX(i, tp.getX(i) + k * k * 0.15);
    }
    tuftGeo.computeVertexNormals();
    const tuftMat = plush(C.plumage);
    this.tufts = [];
    for (const side of [-1, 1]) {
      const pivot = new THREE.Group();
      pivot.position.set(side * 0.4, 1.8 - NECK_Y, -0.03);
      const holder = new THREE.Group();
      holder.scale.x = side;
      holder.add(new THREE.Mesh(tuftGeo, tuftMat));
      pivot.add(holder);
      head.add(pivot);
      const spring = new Spring(70, 6);
      spring.x = -side * 0.36;
      pivot.rotation.z = spring.x;
      this.tufts.push({ pivot, side, spring, base: spring.x });
    }

    this.setupFace(q, C, plush);

    this.bubbleAnchor = new THREE.Object3D();
    this.bubbleAnchor.position.set(0, 2.38 - NECK_Y, 0);
    head.add(this.bubbleAnchor);

    // scratch values for animate (no allocations per frame)
    this.tmpV = new THREE.Vector3();
    this.prevHead = new THREE.Vector3();
    this.headVel = new THREE.Vector3();
    this.wingPose = [0, 1].map(() => ({ raise: 0, pitch: 0, twist: 0, elbow: 0, spread: 0, yaw: 0 }));
    this.turnSide = 1;

    // --- species gestures -------------------------------------------------------
    this.director.register({
      headTurn: { duration: 3.4, weight: 1.3, cooldown: 14, rise: 0.25, fall: 0.3 },
      wingOpen: { duration: 2.6, weight: 0.8, cooldown: 20 },
      wingFlap: { duration: 1.4, weight: 0.8, cooldown: 14, states: ["idle", "speaking"], big: true },
      sway: { duration: 3.0, weight: 1, cooldown: 12 },
      ruffle: { duration: 2.2, weight: 0.8, cooldown: 22 },
      lookAround: { duration: 3.8, weight: 1.1, cooldown: 14 },
      hoot: { duration: 1.8, weight: 0.7, cooldown: 20 },
      surprisePuff: { duration: 1.5, weight: 0.4, cooldown: 26, states: ["idle", "listening", "reading"] },
      techExcited: { duration: 2.4, weight: 0, cooldown: 4, states: ["idle", "listening", "reading", "thinking", "speaking"] },
      // talk gestures
      teach: { duration: 2.0, weight: 1.6, cooldown: 4, states: ["speaking"] },
      explain: { duration: 1.6, weight: 1.2, cooldown: 3, states: ["speaking"] },
      nod: { duration: 1.2, weight: 1, cooldown: 3, states: ["speaking"] },
      wingSweep: { duration: 1.8, weight: 0.7, cooldown: 6, states: ["speaking"] },
    });
  }

  // depth factor of the body's front by height (flatter belly bottom behind the branch)
  frontSquash(y) { return 1 - 0.2 * (1 - smooth(0.12, 0.64, y)); }

  hear(text) {
    if (Character.mentionsTech(text)) {
      this.director.play("techExcited", true);
      this.setEmotion("happy", 0.85, 3);
    } else if (/\b(coruja|owl|corujinha|hoo+t?|uhu+)\b/i.test(text || "")) {
      this.director.play("hoot", true);
    }
  }

  // ---------------------------------------------------------------- branch + feet
  buildBranchAndFeet(q, C) {
    const bark = new THREE.Color(0x7a5e62), barkDark = new THREE.Color(0x4c3740), barkLight = new THREE.Color(0x9a8084);
    const curve = new THREE.CatmullRomCurve3([
      new THREE.Vector3(-1.0, 0.2, 0.56), new THREE.Vector3(-0.55, 0.255, 0.51), new THREE.Vector3(0, 0.27, 0.5),
      new THREE.Vector3(0.5, 0.29, 0.5), new THREE.Vector3(0.98, 0.37, 0.55)]);
    this.branchCurve = curve;
    const tube = (path, radius, tseg, rseg, r0, r1, seed) => {
      const g = new THREE.TubeGeometry(path, tseg, radius, rseg, false);
      const p = g.attributes.position;
      const col = new Float32Array(p.count * 3);
      const P = new THREE.Vector3(), V = new THREE.Vector3(), tmp = new THREE.Color();
      for (let i = 0; i <= tseg; i++) {
        const u = i / tseg;
        path.getPointAt(u, P);
        let k = THREE.MathUtils.lerp(r0, r1, u);
        const end = Math.min(u, 1 - u) * path.getLength();
        if (end < radius * 0.9) k *= Math.sqrt(Math.max(0.02, 1 - ((radius * 0.9 - end) / (radius * 0.9)) ** 2));
        for (let j = 0; j <= rseg; j++) {
          const n = i * (rseg + 1) + j;
          V.fromBufferAttribute(p, n).sub(P);
          const a = j / rseg;
          const ridge = 1 + 0.06 * Math.sin(a * TAU * 7 + Math.sin(u * 19 + seed) * 1.5);
          V.multiplyScalar(k * ridge);
          p.setXYZ(n, P.x + V.x, P.y + V.y, P.z + V.z);
          const s = 0.5 + 0.5 * Math.sin(a * TAU * 7 + Math.sin(u * 19 + seed) * 1.5);
          tmp.copy(barkDark).lerp(bark, 0.35 + 0.65 * s);
          if (Math.sin(u * 37 + seed * 3) > 0.93) tmp.lerp(barkLight, 0.5); // little knots
          col[n * 3] = tmp.r; col[n * 3 + 1] = tmp.g; col[n * 3 + 2] = tmp.b;
        }
      }
      g.setAttribute("color", new THREE.BufferAttribute(col, 3));
      g.computeVertexNormals();
      return g;
    };
    const twig = new THREE.CatmullRomCurve3([
      new THREE.Vector3(-0.58, 0.25, 0.51), new THREE.Vector3(-0.72, 0.17, 0.57), new THREE.Vector3(-0.86, 0.13, 0.63)]);
    const twig2 = new THREE.CatmullRomCurve3([
      new THREE.Vector3(0.62, 0.3, 0.5), new THREE.Vector3(0.74, 0.4, 0.47), new THREE.Vector3(0.8, 0.47, 0.45)]);
    const rs = [8, 10, 14][q];
    const branchGeo = merge([
      tube(curve, BRANCH_R, [40, 60, 90][q], rs, 1.1, 0.75, 0),
      tube(twig, 0.032, [8, 12, 16][q], rs - 2, 1, 0.55, 2),
      tube(twig2, 0.025, [6, 10, 14][q], rs - 2, 1, 0.5, 5),
    ]);
    const branch = new THREE.Mesh(branchGeo, new THREE.MeshPhysicalMaterial({ vertexColors: true, roughness: 0.82, clearcoat: 0.08, sheen: 0.2, sheenColor: new THREE.Color(0xb59a8a) }));
    this.root.add(branch);
    this.branch = branch;

    // feet: three toes over the front, one behind, wrapping the branch; dark claws
    const toeR = 0.041, R = BRANCH_R + toeR * 0.8;
    const claw = new THREE.Color(0x2a2030);
    const toe = (fx, cy, cz, xoff, splay, a0, a1) => {
      const len = R * Math.abs(a1 - a0);
      const g = new THREE.CapsuleGeometry(toeR, Math.max(0.01, len - toeR * 2), [3, 4, 6][q], [6, 8, 12][q]);
      const p = g.attributes.position;
      const total = len, back = a1 < a0;
      const col = new Float32Array(p.count * 3), tmp = new THREE.Color();
      for (let i = 0; i < p.count; i++) {
        let x = p.getX(i);
        const y = p.getY(i), z = p.getZ(i);
        if (!back) x = -x; // keeps the winding (and normals) outward after the bend
        const s = clamp01((y + total / 2) / total);
        const a = a0 + s * (a1 - a0);
        const taper = 1 - 0.38 * s * s;
        const dr = z * taper;
        p.setXYZ(i, fx + xoff + x * taper + splay * s, cy + (R + dr) * Math.cos(a), cz + (R + dr) * Math.sin(a));
        tmp.copy(C.feet).lerp(claw, smooth(0.78, 0.9, s));
        col[i * 3] = tmp.r; col[i * 3 + 1] = tmp.g; col[i * 3 + 2] = tmp.b;
      }
      g.setAttribute("color", new THREE.BufferAttribute(col, 3));
      g.computeVertexNormals();
      return g;
    };
    const parts = [];
    const pt = new THREE.Vector3();
    this.feetAt = [];
    for (const side of [-1, 1]) {
      const fx = side * FEET_X;
      // centre of the branch under this foot
      let best = 0, bd = 1e9;
      for (let i = 0; i <= 200; i++) { curve.getPointAt(i / 200, pt); const dd = Math.abs(pt.x - fx); if (dd < bd) { bd = dd; best = i / 200; } }
      curve.getPointAt(best, pt);
      const cy = pt.y, cz = pt.z;
      this.feetAt.push({ x: fx, y: cy, z: cz });
      for (const k of [-1, 0, 1]) parts.push(toe(fx, cy, cz, k * 0.058, k * 0.03, -0.3, 2.0 - Math.abs(k) * 0.15));
      parts.push(toe(fx, cy, cz, 0, 0, 0.2, -1.55));
      const ankle = new THREE.SphereGeometry(0.07, [8, 12, 16][q], [6, 8, 12][q]);
      ankle.scale(1.15, 0.75, 1.0);
      ankle.translate(fx, cy + BRANCH_R + 0.022, cz - 0.004);
      parts.push(paint(ankle, C.feet));
    }
    const feet = new THREE.Mesh(merge(parts), new THREE.MeshPhysicalMaterial({ vertexColors: true, roughness: 0.4, clearcoat: 0.5, clearcoatRoughness: 0.3 }));
    this.root.add(feet);
    this.feet = feet;

    // feathered legs: stretch between the ankles and the body when it bobs
    const legParts = [];
    for (const f of this.feetAt) {
      const lg = new THREE.SphereGeometry(0.085, [10, 14, 18][q], [8, 10, 14][q]);
      lg.scale(1, 1.25, 0.95);
      lg.translate(f.x, 0.085, 0);
      legParts.push(lg);
    }
    const legs = new THREE.Mesh(merge(legParts), new THREE.MeshPhysicalMaterial({ color: C.belly, roughness: 0.55, clearcoat: 0.2,
      sheen: 0.7, sheenRoughness: 0.4, sheenColor: new THREE.Color(0xd9c8ff) }));
    legs.position.set(0, this.feetAt[0].y + BRANCH_R + 0.0, this.feetAt[0].z - 0.1);
    this.root.add(legs);
    this.legs = legs;
  }

  // ---------------------------------------------------------------- wings
  buildWings(q, C, plush) {
    const pts = this.pts;
    const surfX = (y, z) => {
      const r = radiusAt(pts, y);
      if (r <= 0) return 0;
      const k = (z - BODY_Z) / (r * DEPTH * (z > BODY_Z ? this.frontSquash(y) : 1));
      return r * Math.sqrt(Math.max(0, 1 - k * k));
    };
    const SY = 1.12, SZ = 0.0;
    const SX = surfX(SY, SZ) - 0.035;
    const L = 0.92, W = 0.34, T = 0.09, GAP = 0.012;
    // folded wing (right side; the left one is mirrored): flat inside, domed outside,
    // hugging the body, a teardrop whose tip points down and back
    const ws = [16, 24, 34][q];
    const wingGeo = new THREE.SphereGeometry(1, ws, ws);
    const wp = wingGeo.attributes.position;
    for (let i = 0; i < wp.count; i++) {
      const ux = wp.getX(i), uy = wp.getY(i), uz = wp.getZ(i);
      const v = (1 - uy) / 2;
      const ly = 0.09 - L * Math.pow(v, 1.1);
      const lz = uz * W * (1.12 - 0.62 * v) - 0.02 - 0.13 * v * v;
      const e = Math.abs(ux) ** 0.9;
      const sx = surfX(SY + ly, SZ + lz);
      const lx = sx - SX + GAP + T * (Math.sign(ux) * e + e) * (1 - 0.3 * v) + 0.11 * Math.pow(v, 1.6);
      wp.setXYZ(i, lx, ly, lz);
    }
    wingGeo.computeVertexNormals();
    const wingMat = plush(C.wing, { sheenColor: new THREE.Color(0xe0a8ff) });
    // primary feathers: one shared blade
    const fs = [8, 12, 16][q];
    const featherGeo = new THREE.SphereGeometry(1, fs, fs);
    featherGeo.scale(0.032, 0.2, 0.062);
    const fp = featherGeo.attributes.position;
    for (let i = 0; i < fp.count; i++) { // slightly pointed tip
      const y = fp.getY(i);
      if (y < 0) { const k = -y / 0.2; fp.setX(i, fp.getX(i) * (1 - 0.35 * k * k)); fp.setZ(i, fp.getZ(i) * (1 - 0.4 * k * k)); }
    }
    featherGeo.translate(0, -0.19, 0);
    featherGeo.computeVertexNormals();
    const featherMats = [plush(C.feather), plush(C.tip, { sheenColor: new THREE.Color(0xffc8ff) })];
    this.wings = [];
    for (const side of [-1, 1]) {
      const swing = new THREE.Group(); // yaw: swings the whole wing forward/inward
      swing.position.set(side * SX, SY - CHEST_Y, SZ - BODY_Z);
      this.chest.add(swing);
      const shoulder = new THREE.Group();
      shoulder.rotation.order = "ZXY";
      swing.add(shoulder);
      const mirror = new THREE.Group();
      mirror.scale.x = side;
      shoulder.add(mirror);
      const wing = new THREE.Mesh(wingGeo, wingMat);
      mirror.add(wing);
      const elbow = new THREE.Group();
      const ey = -0.36, ez = -0.06;
      elbow.position.set(surfX(SY + ey, SZ + ez) - SX + 0.012, ey, ez);
      mirror.add(elbow);
      const feathers = [];
      for (let i = 0; i < (q > 0 ? 4 : 3); i++) {
        const f = new THREE.Mesh(featherGeo, featherMats[i % 2 ? 1 : 0]);
        f.position.set(0.004 * i, 0, -0.02 * i);
        elbow.add(f);
        feathers.push(f);
      }
      this.wings.push({ swing, shoulder, mirror, wing, elbow, feathers, side });
    }
    this.wingSurfX = surfX;
  }

  // ---------------------------------------------------------------- face
  setupFace(q, C, plush) {
    const head = this.headGroup;
    const E = this.EYE;
    this.blush = [];
    const iris = irisTexture(0xffd23c, 0xf6900f, 0x9a3a05);
    const rimMat = plush(C.disc, { clearcoat: 0.45, sheen: 0.35 });
    const rimGeo = new THREE.TorusGeometry(E.r * 1.05, 0.05, [8, 12, 16][q], [24, 36, 52][q]);
    rimGeo.scale(1, 1, 0.75);
    for (const side of [-1, 1]) {
      const ex = side * E.x, ey = E.y, ez = this.surf(ex, ey);
      const sock = new THREE.Group();
      sock.position.set(ex, ey - NECK_Y, ez);
      sock.rotation.set(-0.06, side * 0.32, 0);
      head.add(sock);
      const rim = new THREE.Mesh(rimGeo, rimMat);
      rim.position.z = -0.034;
      sock.add(rim);
      const eye = new OwlEye({ radius: E.r, lid: C.disc, iris, arcColor: C.feather.clone().multiplyScalar(0.55), quality: q });
      eye.group.position.z = -0.13;
      sock.add(eye.group);
      this.eyes.push(eye);
      if (q === 0) continue; // no blush on low quality
      const blush = new THREE.Mesh(new THREE.CircleGeometry(0.05, 20),
        new THREE.MeshBasicMaterial({ color: 0xff8fc8, transparent: true, opacity: 0, depthWrite: false }));
      const bx = side * 0.44, by = 1.43;
      blush.position.set(bx, by - NECK_Y, this.surf(bx, by) + 0.004);
      blush.rotation.y = side * 0.62;
      blush.scale.y = 0.65;
      head.add(blush);
      this.blush.push(blush);
    }
    this.mouth = new OwlBeak(q);
    this.mouth.group.position.set(0, 1.49 - NECK_Y, this.surf(0, 1.49) - 0.005);
    this.mouth.tilt = 0.45;
    this.mouth.size = 1.25;
    head.add(this.mouth.group);
  }

  applyFace(t) {
    const c = this.cur, d = this.director, g = d.curve();
    // gesture-driven expression extras (added and removed around the base pass)
    let wide = 0, round = 0, smile = 0;
    if (g.name === "hoot") round = smooth(0.15, 0.3, g.p) * (1 - smooth(0.75, 0.92, g.p)) * (0.75 + 0.25 * Math.sin(g.p * TAU * 2));
    if (g.name === "surprisePuff") wide = g.s;
    if (g.name === "techExcited") { wide = g.s * 0.9; smile = g.s * 0.6; }
    c.wide += wide; c.round += round; c.smile += smile;
    super.applyFace(t);
    c.wide -= wide; c.round -= round; c.smile -= smile;
    // pupils: big and soft when delighted, small when startled
    const pupil = 1 + clamp01(c.smile - 0.5) * 0.25 - (c.wide + wide) * 0.22 + this.director.w.paused * 0.1;
    for (const e of this.eyes) e.setPupil(Math.max(0.72, pupil));
    const glow = clamp01((c.smile + smile - 0.4) * 1.6) * 0.5;
    for (const b of this.blush) b.material.opacity = glow;
  }

  // ---------------------------------------------------------------- animation
  animate(dt, t, state) {
    const c = this.cur, d = this.director, w = d.w, a = d.amp;
    const act = this.actionCurve();
    const g = d.curve();
    const talk = c.speak;
    const still = d.state === "emergency";
    const gentle = act.gentle || d.cfg.reduceMotion;

    // ---- body: rocks on the branch, leans, bobs, puffs up
    let roll = still ? 0 : Math.sin(t * 1.05) * 0.014 * a;
    let lean = d.lean.z * 0.05 * a + w.listening * 0.07 - w.paused * 0.02 + w.reading * 0.03;
    let lift = 0, puff = w.paused * 0.035, stretch = 0, yaw = d.head.x * 0.08;
    if (!still) {
      roll += d.lean.x * 0.035 * a;
      if (g.name === "sway") roll += Math.sin(g.p * TAU * 2) * 0.13 * g.s * a;
      if (g.name === "ruffle") {
        puff += smooth(0.05, 0.3, g.p) * (1 - smooth(0.55, 0.85, g.p)) * 0.09;
        roll += Math.sin(t * 40) * 0.025 * smooth(0.3, 0.4, g.p) * (1 - smooth(0.6, 0.7, g.p));
      }
      if (g.name === "hoot") { const h = smooth(0.15, 0.35, g.p) * (1 - smooth(0.7, 0.9, g.p)); puff += h * 0.08; lean -= h * 0.05; }
      if (g.name === "surprisePuff") { stretch += g.s * 0.05; puff += g.s * 0.03; lean -= g.s * 0.04; }
      if (g.name === "techExcited") { lift += Math.abs(Math.sin(g.p * Math.PI * 3)) * 0.06 * g.s * a; stretch += 0.03 * g.s; }
      if (g.name === "wingFlap") lift += Math.abs(Math.sin(g.p * Math.PI * 6)) * 0.025 * g.s;
      if (act.name === "laugh") { roll += Math.sin(t * 22) * 0.03 * act.s; lean -= 0.1 * act.s; }
      if (act.name === "surprised") { stretch += 0.08 * act.s; puff += 0.05 * act.s; lean -= 0.06 * act.s; }
      if (act.name === "celebrate") lift += Math.abs(Math.sin(act.p * Math.PI * (gentle ? 2 : 3))) * (gentle ? 0.035 : 0.11);
      if (act.name === "happy") lift += Math.abs(Math.sin(act.p * Math.PI * 2)) * 0.05;
      if (act.name === "annoyed") { yaw -= 0.25 * act.s; lean -= 0.04 * act.s; }
      if (act.name === "confused") roll += 0.05 * act.s;
    }
    const squash = c.speak * 0.012 + d.breath * 0.008 * a;
    this.body.position.y = damp(this.body.position.y, PIVOT_Y + lift, 16, dt);
    this.body.rotation.z = damp(this.body.rotation.z, roll, 9, dt);
    this.body.rotation.x = damp(this.body.rotation.x, lean, 6, dt);
    this.body.rotation.y = damp(this.body.rotation.y, yaw, 4, dt);
    const sx = 1 + puff + d.breath * 0.01 * a - stretch * 0.35;
    this.body.scale.set(sx, 1 + stretch + squash - puff * 0.3, sx);
    this.legs.scale.y = 1 + (this.body.position.y - PIVOT_Y) / 0.12;

    // ---- head: turns far, tilts with curiosity, bobs on speech beats
    let hy = d.head.x * 0.75, hp = -d.head.y * 0.32 - d.beat * 0.08 - talk * 0.04, hr = c.tilt * 0.6;
    if (!still) {
      if (g.name === "headTurn") {
        this.turnSide = d.gesture.side ??= Math.random() < 0.5 ? -1 : 1;
        const k = smooth(0.08, 0.4, g.p) * (1 - smooth(0.62, 0.95, g.p));
        hy += this.turnSide * 1.5 * k;
        hr += this.turnSide * 0.12 * Math.sin(g.p * Math.PI);
      }
      if (g.name === "lookAround") hy += Math.sin(g.p * TAU) * 0.8 * g.s;
      if (g.name === "curious" || w.listening > 0.4) hr += 0.22 * Math.max(g.name === "curious" ? g.s : 0, w.listening);
      if (g.name === "nod") hp += Math.sin(g.p * Math.PI * 4) * 0.1 * g.s;
      if (g.name === "teach") { hr -= 0.12 * g.s; hp += 0.06 * g.s; }
      if (g.name === "hoot") hp -= Math.sin(g.p * Math.PI) * 0.12 * g.s;
      if (g.name === "techExcited") hr += Math.sin(g.p * TAU * 2) * 0.12 * g.s;
      if (g.name === "ruffle") hr += Math.sin(t * 40) * 0.03 * smooth(0.3, 0.4, g.p) * (1 - smooth(0.6, 0.7, g.p));
      if (state.phase === "thinking") { hr -= 0.14 * w.thinking; hp -= 0.08 * w.thinking; }
      if (act.name === "confused") hr += 0.2 * act.s;
      if (act.name === "laugh") hp -= 0.18 * act.s;
      if (act.name === "annoyed") hy += 0.35 * act.s;
      hp += w.paused * 0.12;
    }
    this.head.rotation.y = damp(this.head.rotation.y, hy, 7, dt);
    this.head.rotation.x = damp(this.head.rotation.x, hp, 9, dt);
    this.head.rotation.z = damp(this.head.rotation.z, hr, 8, dt);

    // ---- ear tufts: perk up with surprise/excitement, droop when annoyed or sleepy
    this.headGroup.getWorldPosition(this.tmpV);
    if (!this.headSeen) { this.prevHead.copy(this.tmpV); this.headSeen = true; }
    this.headVel.subVectors(this.tmpV, this.prevHead).divideScalar(Math.max(dt, 1e-3)).clampLength(0, 4);
    this.prevHead.copy(this.tmpV);
    let perk = c.wide * 0.3 + (g.name === "surprisePuff" ? g.s * 0.35 : 0) + (g.name === "techExcited" ? g.s * 0.35 : 0) + w.listening * 0.08;
    perk -= clamp01(-c.browTilt) * 0.3 + w.paused * 0.25 + c.frown * 0.1;
    for (const tf of this.tufts) {
      const target = tf.base + tf.side * (perk * 0.6) - tf.side * this.headVel.x * 0.02 + Math.sin(t * 2.1 + tf.side) * 0.015;
      tf.pivot.rotation.z = tf.spring.step(target, dt);
      tf.pivot.rotation.x = damp(tf.pivot.rotation.x, -perk * 0.25 + this.headVel.y * 0.01, 10, dt);
      tf.pivot.scale.y = damp(tf.pivot.scale.y, 1 + Math.max(0, perk) * 0.15, 10, dt);
    }

    this.animateWings(dt, t, state, g, act, talk, still, gentle);
  }

  // Wing pose: raise (out to the side), pitch (- forward), twist (turns the inner face
  // to the front, for open wings), elbow (fan extends), spread (primaries fan out).
  animateWings(dt, t, state, g, act, talk, still, gentle) {
    const d = this.director;
    for (let i = 0; i < 2; i++) {
      const W = this.wings[i], P = this.wingPose[i];
      const teacher = i === 1;
      P.raise = 0.02 + d.breath * 0.012; P.pitch = 0; P.twist = 0; P.elbow = 0; P.spread = 0; P.yaw = 0;
      if (!still) {
        P.raise += talk * 0.12 * (0.5 + 0.5 * Math.sin(t * 5.5 + i * 1.9)) + d.beat * 0.18;
        if (g.name === "wingOpen") { const k = smooth(0.1, 0.4, g.p) * (1 - smooth(0.65, 0.95, g.p)); set(P, 1.25, -0.1, 1.2, 0.5, 1, k); }
        if (g.name === "wingFlap") {
          const f = 0.5 + 0.5 * Math.sin(g.p * TAU * 4 - Math.PI / 2);
          set(P, 0.25 + f * 0.75, -0.1, 0.5 + f * 0.5, 0.2 + f * 0.3, f, g.s);
        }
        if (g.name === "techExcited") {
          const f = 0.5 + 0.5 * Math.sin(g.t * 22);
          set(P, 0.55 + f * 0.6, -0.15, 0.7 + f * 0.4, 0.3, 0.6 + f * 0.4, g.s);
        }
        if (g.name === "ruffle") set(P, 0.18 + Math.sin(t * 40 + i) * 0.04, 0, 0.1, 0.1, 0.5, smooth(0.05, 0.3, g.p) * (1 - smooth(0.55, 0.85, g.p)));
        if (g.name === "hoot") set(P, 0.12, 0, 0, 0, 0.2, g.s);
        if (g.name === "explain") set(P, 0.5, -0.45, 0.9, 0.3, 0.5, g.s);
        if (g.name === "wingSweep") set(P, 0.35 + (teacher ? 0.4 : 0) * Math.sin(g.p * Math.PI), -0.5, 0.7, 0.3, 0.6, g.s * (teacher ? 1 : 0.4));
        if (teacher) {
          if (g.name === "teach") set(P, 2.15 + Math.sin(g.t * 7) * 0.08 * g.s, -0.45, 0.4, 0.9, 0.05, g.s, -0.15);
          if (state.phase === "thinking") set(P, 0.3, -1.9, 0.3, 0.9, 0.05, d.w.thinking, -0.7);
          if (act.name === "confused") set(P, 2.2, -0.35, 0.6, 0.4 + Math.sin(t * 16) * 0.15, 0.2, act.s);
          if (act.name === "annoyed") set(P, 0.35 + Math.abs(Math.sin(t * 12)) * 0.15, -0.2, 0.3, 0.2, 0.3, act.s);
        }
        if (act.name === "celebrate") {
          const f = 0.5 + 0.5 * Math.sin(t * (gentle ? 10 : 18) + i * 0.3);
          set(P, 1.15 + f * (gentle ? 0.15 : 0.4), -0.1, 1.15, 0.5, 0.7 + f * 0.3, act.s);
        }
        if (act.name === "surprised") set(P, 0.75, -0.15, 0.6, 0.3, 0.8, act.s);
        if (act.name === "happy") { const f = 0.5 + 0.5 * Math.sin(t * 16); set(P, 0.3 + f * 0.35, -0.1, 0.4, 0.2, 0.5, act.s); }
        if (act.name === "laugh") set(P, 0.1, -0.6 + Math.sin(t * 22) * 0.06, 0.1, 0.2, 0.2, act.s, -0.35);
      }
      W.swing.rotation.y = damp(W.swing.rotation.y, W.side * P.yaw, 10, dt);
      W.shoulder.rotation.z = damp(W.shoulder.rotation.z, W.side * P.raise, 12, dt);
      W.shoulder.rotation.x = damp(W.shoulder.rotation.x, P.pitch, 10, dt);
      W.shoulder.rotation.y = damp(W.shoulder.rotation.y, W.side * P.twist, 10, dt);
      W.elbow.rotation.x = damp(W.elbow.rotation.x, -P.elbow * 0.5, 10, dt);
      for (let k = 0; k < W.feathers.length; k++) {
        const f = W.feathers[k];
        const target = 0.12 + k * (0.1 + P.spread * 0.28);
        f.rotation.x = damp(f.rotation.x, target, 12, dt);
        f.rotation.z = damp(f.rotation.z, -0.04 * k * (1 - P.spread), 12, dt);
      }
    }
  }
}
