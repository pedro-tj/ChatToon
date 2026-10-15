// Tux-inspired penguin in a top hat (original procedural model; Tux © Larry Ewing,
// created with The GIMP). Modelled after the round vinyl-toy look of the reference:
// one soft body with the head built in, a heart-shaped white face flowing into the
// belly, small glossy eyes, a chubby beak and a black top hat with a coloured band.
import * as THREE from "../../vendor/three/three.module.js";
import { BeadEye, Brow, Character, Spring, clamp01, damp, smooth, wrapAngle } from "../rig.js";
import {
  boneChain, frontUV, latheBody, markedMaterial, markingTexture, profile, radiusAt, sdCircle, sdEllipse,
  skinByHeight, smin, topHat,
} from "./shapes.js";

const BLACK = 0x17181d;
const WHITE = 0xf7f5f0;
const ORANGE = 0xff8c00;
const DEPTH = 0.84;
const HEAD_Y = 1.05; // head bone height: everything above bends with the head

// Two-part beak with the same interface as Mouth: the lower mandible is the jaw.
class Beak {
  constructor(quality) {
    const seg = [14, 20, 30][quality];
    const top = new THREE.MeshPhysicalMaterial({ color: 0xff9800, roughness: 0.42, clearcoat: 0.45, clearcoatRoughness: 0.35 });
    const bottom = new THREE.MeshPhysicalMaterial({ color: 0xe46a00, roughness: 0.45, clearcoat: 0.35, clearcoatRoughness: 0.4 });
    this.group = new THREE.Group();
    // upper mandible: a soft rounded wedge, wide at the base and blunt at the tip
    const ug = new THREE.SphereGeometry(1, seg, seg / 2, 0, Math.PI * 2, 0, Math.PI * 0.62);
    const up = ug.attributes.position;
    for (let i = 0; i < up.count; i++) {
      const x = up.getX(i), y = up.getY(i), z = up.getZ(i);
      const forward = (z + 1) / 2; // 0 back .. 1 tip
      const taper = 1 - forward * forward * 0.45;
      up.setXYZ(i, x * 0.14 * taper, (y - 0.3) * 0.105 * taper - forward * forward * 0.025, z * 0.135 + 0.03);
    }
    ug.computeVertexNormals();
    this.upper = new THREE.Mesh(ug, top);
    this.lowerPivot = new THREE.Group();
    this.lowerPivot.position.set(0, -0.012, -0.06);
    const lg = new THREE.SphereGeometry(1, seg, seg / 2, 0, Math.PI * 2, Math.PI * 0.5, Math.PI * 0.5);
    const lp = lg.attributes.position;
    for (let i = 0; i < lp.count; i++) {
      const x = lp.getX(i), y = lp.getY(i), z = lp.getZ(i);
      const forward = (z + 1) / 2;
      const taper = 1 - forward * forward * 0.4;
      lp.setXYZ(i, x * 0.115 * taper, y * 0.06 * taper, z * 0.11 + 0.075);
    }
    lg.computeVertexNormals();
    this.lower = new THREE.Mesh(lg, bottom);
    this.lowerPivot.add(this.lower);
    const inside = new THREE.Mesh(new THREE.CircleGeometry(1, seg),
      new THREE.MeshBasicMaterial({ color: 0x6a1420, side: THREE.DoubleSide }));
    inside.rotation.x = -Math.PI / 2;
    inside.scale.set(0.11, 0.085, 1);
    inside.position.set(0, 0.002, 0.065);
    this.lowerPivot.add(inside);
    const tongue = new THREE.Mesh(new THREE.SphereGeometry(1, 12, 8), new THREE.MeshBasicMaterial({ color: 0xff7d95 }));
    tongue.scale.set(0.055, 0.015, 0.045);
    tongue.position.set(0, 0.004, 0.07);
    this.lowerPivot.add(tongue);
    this.group.add(this.upper, this.lowerPivot);
  }

  set({ open, smile, frown, round }) {
    const jaw = Math.min(1, open + round * 0.5);
    this.lowerPivot.rotation.x = jaw * 0.62;
    this.upper.rotation.x = -jaw * 0.1;
    this.group.scale.set(1 + smile * 0.07 - frown * 0.05, 1 + round * 0.05, 1);
  }
}

// Rounded webbed foot with three toes (extruded outline with a soft bevel).
function footGeometry(quality) {
  const s = new THREE.Shape();
  s.moveTo(-0.11, -0.05);
  s.bezierCurveTo(-0.17, 0.05, -0.2, 0.17, -0.15, 0.23);
  s.bezierCurveTo(-0.12, 0.27, -0.08, 0.25, -0.065, 0.22);
  s.bezierCurveTo(-0.05, 0.29, 0.05, 0.29, 0.065, 0.22);
  s.bezierCurveTo(0.08, 0.25, 0.12, 0.27, 0.15, 0.23);
  s.bezierCurveTo(0.2, 0.17, 0.17, 0.05, 0.11, -0.05);
  s.bezierCurveTo(0.07, -0.1, -0.07, -0.1, -0.11, -0.05);
  const g = new THREE.ExtrudeGeometry(s, { depth: 0.04, bevelEnabled: true, bevelThickness: 0.035, bevelSize: 0.03,
    bevelSegments: [2, 3, 5][quality], curveSegments: [6, 10, 16][quality] });
  g.rotateX(-Math.PI / 2);
  g.translate(0, 0.035, 0);
  g.computeVertexNormals();
  return g;
}

export class Tux extends Character {
  constructor(options) {
    super(options);
    const q = this.quality;
    const seg = [28, 44, 64][q];
    const band = new THREE.Color(options.color || "#ffb000");
    this.headHeight = 2.45;
    this.extent = { width: 1.6, height: 2.45 };

    this.body = new THREE.Group(); // waddles, jumps and spins over the feet
    this.root.add(this.body);

    // --- one soft body, the head built in (as in the reference) --------------
    const pts = profile([[0.0, 0.1], [0.36, 0.115], [0.55, 0.2], [0.635, 0.36], [0.655, 0.52], [0.64, 0.7],
      [0.6, 0.88], [0.56, 1.04], [0.54, 1.18], [0.525, 1.32], [0.49, 1.47], [0.41, 1.6], [0.27, 1.7], [0.0, 1.745]], 64);
    this.pts = pts;
    const bodyGeo = latheBody(pts, { segments: seg, depth: DEPTH });
    const box = frontUV(bodyGeo, { x0: -0.7, x1: 0.7, y0: 0.05, y1: 1.8, fade: [0.08, 0.32] });
    // White face (two lobes around the eyes, dipping between them) blending into the belly.
    const face = (x, y) => {
      const lobes = Math.min(sdCircle(x, y, -0.19, 1.29, 0.22), sdCircle(x, y, 0.19, 1.29, 0.22));
      const cheeks = sdEllipse(x, y, 0, 1.1, 0.37, 0.24);
      const belly = sdEllipse(x, y, 0, 0.6, 0.555, 0.58);
      return smin(smin(lobes, cheeks, 0.16), belly, 0.22);
    };
    const map = markingTexture(box, BLACK, [{ color: WHITE, sdf: face }], { size: [256, 512, 512][q], soft: 0.006,
      key: `tux-face-${q}` });
    const skinMat = markedMaterial(map, BLACK, { roughness: 0.55, clearcoat: 0.3, clearcoatRoughness: 0.42,
      sheen: 0.12, sheenRoughness: 0.7, sheenColor: new THREE.Color(0x4a5066), envMapIntensity: 0.6 });
    this.bones = boneChain([0, 0.6, HEAD_Y]);
    skinByHeight(bodyGeo, [
      (y) => 1 - smooth(0.25, 0.8, y),
      (y) => smooth(0.25, 0.8, y) * (1 - smooth(0.92, 1.32, y)),
      (y) => smooth(0.25, 0.8, y) * smooth(0.92, 1.32, y),
    ]);
    const skinned = new THREE.SkinnedMesh(bodyGeo, skinMat);
    skinned.add(this.bones[0]);
    skinned.bind(new THREE.Skeleton(this.bones));
    skinned.frustumCulled = false; // the bones move it; the bind-pose bounds would cull it wrongly
    this.body.add(skinned);
    this.skinned = skinned;
    const [hips, chest, head] = this.bones;
    this.hips = hips; this.chest = chest; this.head = head;

    // --- face -------------------------------------------------------------------
    this.setupFace(head, q);

    // --- top hat, on a spring so it lags a little behind the head ------------------
    this.hatPivot = new THREE.Group();
    this.hatPivot.position.set(0.03, 1.66 - HEAD_Y, -0.02);
    head.add(this.hatPivot);
    this.hat = topHat({ band, quality: q });
    this.hat.scale.setScalar(0.92);
    this.hatPivot.add(this.hat);
    this.hatBase = { x: -0.1, z: -0.16 }; // a dapper tilt, back and to the side
    this.hatSpring = { x: new Spring(90, 9), z: new Spring(90, 9), y: new Spring(120, 11) };
    this.prevHead = new THREE.Vector3();
    this.headVel = new THREE.Vector3();
    this.tmp = new THREE.Vector3();

    this.bubbleAnchor = new THREE.Object3D();
    this.bubbleAnchor.position.set(0, 0.5, 0); // above the hat
    this.hatPivot.add(this.bubbleAnchor);

    // --- flippers: shoulder + elbow ---------------------------------------------
    const black = new THREE.MeshPhysicalMaterial({ color: BLACK, roughness: 0.55, clearcoat: 0.3, clearcoatRoughness: 0.42,
      sheen: 0.12, sheenRoughness: 0.7, sheenColor: new THREE.Color(0x4a5066), envMapIntensity: 0.6 });
    this.flippers = [];
    for (const side of [-1, 1]) {
      const shoulder = new THREE.Group();
      const sy = 1.0, r = radiusAt(pts, sy);
      shoulder.position.set(side * (r - 0.05), sy - 0.6, 0.0);
      chest.add(shoulder);
      // a flat paddle, thick at the root and thinner towards the rounded tip
      const upper = new THREE.SphereGeometry(1, seg / 2, seg / 3);
      upper.scale(0.085, 0.3, 0.17);
      upper.translate(0, -0.22, 0);
      shoulder.add(new THREE.Mesh(upper, black));
      const elbow = new THREE.Group();
      elbow.position.y = -0.42;
      shoulder.add(elbow);
      const lower = new THREE.SphereGeometry(1, seg / 2, seg / 3);
      lower.scale(0.07, 0.22, 0.145);
      lower.translate(0, -0.12, 0);
      elbow.add(new THREE.Mesh(lower, black));
      this.flippers.push({ shoulder, elbow, side, });
    }

    // --- feet ---------------------------------------------------------------------
    const footMat = new THREE.MeshPhysicalMaterial({ color: ORANGE, roughness: 0.42, clearcoat: 0.5, clearcoatRoughness: 0.3 });
    const fg = footGeometry(q);
    this.feet = [];
    for (const side of [-1, 1]) {
      const foot = new THREE.Mesh(fg, footMat);
      foot.position.set(side * 0.27, 0, 0.16);
      foot.rotation.y = side * 0.28;
      foot.scale.setScalar(1.15);
      this.root.add(foot);
      this.feet.push(foot);
    }

    // --- species gestures -----------------------------------------------------------
    this.director.register({
      tipHat: { duration: 2.8, weight: 1, cooldown: 24 },
      adjustHat: { duration: 1.6, weight: 0.9, cooldown: 14 },
      flap: { duration: 1.2, weight: 1, cooldown: 9, states: ["idle", "speaking"] },
      waddle: { duration: 3.2, weight: 0.9, cooldown: 18 },
      bow: { duration: 2.6, weight: 0.5, cooldown: 32 },
      stretch: { duration: 2.4, weight: 0.5, cooldown: 30 },
      bellyPat: { duration: 1.8, weight: 0.6, cooldown: 20 },
      explain: { duration: 1.5, weight: 1.6, cooldown: 3, states: ["speaking"] },
      hatTouch: { duration: 1.4, weight: 0.4, cooldown: 18, states: ["speaking"] },
    });
    // a gentleman: content and pensive; tips the hat, never rolls on the floor
    this.setPersona({
      idleMoods: { happy: 3, thinking: 2, laugh: 1, surprised: 0.6 },
      moodGestures: { happy: "tipHat", thinking: "adjustHat", laugh: "bellyPat", surprised: "lookAround" },
      speechGestures: { happy: "hatTouch", celebrate: "flap", thinking: "explain", surprised: "flap", laugh: "bellyPat" },
    });
  }

  hear(text) {
    if (/\bwindows\b/i.test(text || "")) { this.setEmotion("annoyed", 0.5, 2.5); this.director.play("adjustHat"); }
    else if (Character.mentionsTech(text)) this.director.play("flap");
  }

  setupFace(head, q) {
    const surface = (x, y) => DEPTH * Math.sqrt(Math.max(0, radiusAt(this.pts, y) ** 2 - x * x));
    for (const side of [-1, 1]) {
      const ex = side * 0.175, ey = 1.29;
      const eye = new BeadEye({ radius: 0.068, lid: WHITE, depth: 0.55, quality: q });
      eye.group.position.set(ex, ey - HEAD_Y, surface(ex, ey) - 0.012);
      eye.group.rotation.set(-0.08, side * 0.32, 0);
      eye.group.scale.set(1, 1.42, 1);
      head.add(eye.group);
      this.eyes.push(eye);
      // brows only show up for big expressions (the reference face has none)
      const brow = new Brow({ side, color: BLACK, length: 0.085, thickness: 0.017, quality: q });
      brow.place(side * 0.175, 1.405 - HEAD_Y, surface(side * 0.175, 1.38) + 0.02);
      brow.mesh.rotation.y = side * 0.3;
      head.add(brow.mesh);
      this.brows.push(brow);
      const blush = new THREE.Mesh(new THREE.CircleGeometry(0.055, 20),
        new THREE.MeshBasicMaterial({ color: 0xff8fa8, transparent: true, opacity: 0, depthWrite: false }));
      blush.position.set(side * 0.29, 1.15 - HEAD_Y, surface(side * 0.29, 1.15) + 0.004);
      blush.rotation.y = side * 0.55;
      blush.scale.y = 0.7;
      head.add(blush);
      (this.blush ??= []).push(blush);
    }
    this.mouth = new Beak(q);
    this.mouth.group.position.set(0, 1.175 - HEAD_Y, surface(0, 1.175) - 0.005);
    this.mouth.group.rotation.x = 0.12;
    head.add(this.mouth.group);
  }

  applyFace(t) {
    super.applyFace(t);
    const c = this.cur;
    // only strong expressions (surprise, annoyance, confusion) pop the brows out
    const vis = clamp01((Math.abs(c.browY) - 0.045) * 22 + (Math.abs(c.browTilt) - 0.2) * 1.2 + (c.browAsym - 0.2) * 1.2 + c.wide);
    for (const b of this.brows) { b.mesh.visible = vis > 0.05; b.mesh.scale.setScalar(0.4 + vis * 0.6); }
    const glow = clamp01((c.smile - 0.4) * 1.6) * 0.55;
    for (const b of this.blush) b.material.opacity = glow;
  }

  animate(dt, t, state) {
    const c = this.cur, d = this.director, w = d.w, a = d.amp;
    const act = this.actionCurve();
    const g = d.curve();
    const talking = c.speak;
    const happy = this.emotion === "happy" || this.emotion === "celebrate";
    const still = d.state === "emergency";

    // waddle: gentle rock always, real stepping during the waddle gesture or when happy
    const stepping = g.name === "waddle" ? g.s : happy ? 0.5 : 0;
    const rockSpeed = 2.0 + stepping * 4.5;
    const rock = still ? 0 : Math.sin(t * rockSpeed) * (0.025 * a + stepping * 0.09);
    let jump = 0, spin = 0, squash = 0;
    if (act.name === "celebrate") {
      const hops = act.gentle ? 1 : 2;
      jump = Math.abs(Math.sin(act.p * Math.PI * hops)) * (act.gentle ? 0.12 : 0.32);
      spin = act.gentle ? 0 : smooth(0.15, 0.85, act.p) * Math.PI * 2;
    }
    if (act.name === "surprised") { jump = act.s * (act.gentle ? 0.08 : 0.22); squash = -act.s * 0.06; }
    if (act.name === "happy") jump = Math.abs(Math.sin(act.p * Math.PI * 2)) * 0.07;
    if (g.name === "stretch") squash = -g.s * 0.07;
    if (act.name === "laugh") squash = Math.sin(t * 28) * 0.025 * act.s;
    squash += d.breath * 0.008 * a + talking * 0.012;

    this.root.position.y = damp(this.root.position.y, jump, 16, dt);
    this.body.rotation.y = spin || damp(wrapAngle(this.body.rotation.y), d.head.x * 0.15, 4, dt);
    this.body.rotation.z = damp(this.body.rotation.z, rock + d.lean.x * 0.05 * a, 10, dt);
    this.hips.scale.set(1 - squash * 0.5, 1 + squash, 1 - squash * 0.5);
    this.feet[0].position.y = damp(this.feet[0].position.y, Math.max(0, rock) * (0.5 + stepping * 1.4), 18, dt);
    this.feet[1].position.y = damp(this.feet[1].position.y, Math.max(0, -rock) * (0.5 + stepping * 1.4), 18, dt);
    if (act.name === "annoyed") this.feet[1].position.y = Math.abs(Math.sin(t * 14)) * 0.05 * act.s; // foot tap

    // chest: lean in to listen, bow, breathe
    let chestX = d.lean.z * 0.06 * a + w.listening * 0.08 - w.paused * 0.04;
    if (g.name === "bow") chestX += g.s * 0.45;
    if (act.name === "laugh") chestX -= 0.18 * act.s;
    this.chest.rotation.x = damp(this.chest.rotation.x, chestX, 6, dt);
    this.chest.rotation.z = damp(this.chest.rotation.z, d.lean.x * 0.03, 4, dt);
    const breathe = 1 + d.breath * 0.012 * a;
    this.chest.scale.set(breathe, 1, breathe);

    // head: looks where the director looks, tilts with emotion and curiosity, nods on beats
    let yaw = d.head.x * 0.55, pitch = -d.head.y * 0.3 - talking * 0.06 - d.beat * 0.07, roll = c.tilt * 0.8;
    if (g.name === "curious" || w.listening > 0.5) roll += 0.16 * Math.max(g.name === "curious" ? g.s : 0, w.listening);
    if (state.phase === "thinking") { roll -= 0.08; pitch -= 0.06; }
    if (g.name === "bow") pitch += g.s * 0.25;
    if (g.name === "tipHat") pitch += g.s * 0.12;
    if (act.name === "confused") roll += 0.2 * act.s;
    if (act.name === "laugh") pitch -= 0.15 * act.s;
    this.head.rotation.y = damp(this.head.rotation.y, yaw, 7, dt);
    this.head.rotation.x = damp(this.head.rotation.x, pitch, 9, dt);
    this.head.rotation.z = damp(this.head.rotation.z, roll, 7, dt);

    this.animateFlippers(dt, t, state, g, act, talking, still);
    this.animateHat(dt, g, act);
  }

  // Flipper pose: z = shoulder roll (+ raises outward), x = shoulder pitch (- forward),
  // ez = elbow curl (+ keeps turning the same way as z), ex = elbow fold (- forward).
  animateFlippers(dt, t, state, g, act, talking, still) {
    const d = this.director;
    const mix = (p, q, k) => { for (const key in q) p[key] = THREE.MathUtils.lerp(p[key], q[key], k); };
    this.flippers.forEach((f, i) => {
      const right = f.side > 0;
      const p = { z: 0.42 + d.breath * 0.02, x: 0, ez: 0.08, ex: 0 };
      if (!still) {
        p.z += talking * 0.22 * (0.5 + 0.5 * Math.sin(t * 6 + i * 1.7)) + d.beat * 0.25;
        if (g.name === "flap") p.z += Math.abs(Math.sin(g.p * Math.PI * 4)) * 0.6 * g.s;
        if (g.name === "waddle") p.z += 0.25 * g.s;
        if (g.name === "stretch") mix(p, { z: 1.6, x: 0, ez: -0.2, ex: 0 }, g.s);
        if (right) {
          if (g.name === "explain") mix(p, { z: 0.9, x: -0.7, ez: 0.25, ex: -0.5 }, g.s);
          if (g.name === "bellyPat") mix(p, { z: -0.05, x: -0.75, ez: -0.65, ex: -0.55 + Math.sin(t * 16) * 0.15 }, g.s);
          if (g.name === "bow") mix(p, { z: -0.1, x: -0.95, ez: -0.9, ex: -0.75 }, g.s);
          const toHat = Math.max(g.name === "tipHat" ? smooth(0, 0.3, g.p) * (1 - smooth(0.75, 1, g.p)) : 0,
            g.name === "adjustHat" || g.name === "hatTouch" ? g.s : 0);
          if (toHat) mix(p, { z: 2.75, x: -0.25, ez: 0.55, ex: -0.2 }, toHat);
          if (state.phase === "thinking") mix(p, { z: -0.35, x: -2.0, ez: -0.75, ex: -0.6 }, d.w.thinking); // flipper to the beak
          if (act.name === "confused") mix(p, { z: 2.6, x: -0.3, ez: 0.6 + Math.sin(t * 18) * 0.2, ex: -0.2 }, act.s);
        }
        if (act.name === "celebrate") mix(p, { z: 2.4 + Math.sin(t * 20 + i) * 0.35, x: 0, ez: 0.1, ex: 0 }, act.s);
        if (act.name === "surprised") mix(p, { z: 1.6, x: -0.2, ez: 0.2, ex: 0 }, act.s);
        if (act.name === "laugh") mix(p, { z: 0.0, x: -0.6, ez: -0.7, ex: -0.6 }, act.s); // hold the belly
        if (act.name === "annoyed") mix(p, { z: 0.75, x: 0.15, ez: -1.6, ex: -0.2 }, act.s); // hands on hips
      }
      f.shoulder.rotation.z = damp(f.shoulder.rotation.z, f.side * p.z, 10, dt);
      f.shoulder.rotation.x = damp(f.shoulder.rotation.x, p.x, 9, dt);
      f.elbow.rotation.z = damp(f.elbow.rotation.z, f.side * p.ez, 10, dt);
      f.elbow.rotation.x = damp(f.elbow.rotation.x, p.ex, 10, dt);
    });
  }

  animateHat(dt, g, act) {
    // greeting: lift and tilt the hat; surprise pops it up; it always lags a bit (spring)
    let lift = 0, tiltZ = 0, tiltX = 0;
    if (g.name === "tipHat") {
      const k = smooth(0.25, 0.45, g.p) * (1 - smooth(0.62, 0.85, g.p));
      lift = 0.2 * k; tiltZ = 0.35 * k; tiltX = 0.3 * k;
    }
    if (g.name === "adjustHat") { tiltZ = Math.sin(g.p * Math.PI * 2) * 0.12 * g.s; lift = 0.03 * g.s; }
    if (act.name === "surprised") lift = 0.22 * act.s;
    if (act.name === "celebrate") lift = 0.06 * act.s;
    if (act.name === "confused") tiltZ = -0.1 * act.s;
    this.head.getWorldPosition(this.tmp);
    const v = this.tmp.clone().sub(this.prevHead).divideScalar(Math.max(dt, 1e-3));
    this.prevHead.copy(this.tmp);
    this.headVel.lerp(v, 0.5);
    const hx = this.hatSpring.x.step(this.hatBase.x + tiltX - this.headVel.z * 0.02, dt);
    const hz = this.hatSpring.z.step(this.hatBase.z + tiltZ + this.headVel.x * 0.05, dt);
    const hy = this.hatSpring.y.step(lift + Math.max(0, -this.headVel.y) * 0.01, dt);
    this.hatPivot.rotation.set(hx, 0, hz);
    this.hatPivot.position.y = 1.66 - HEAD_Y + hy;
  }
}
