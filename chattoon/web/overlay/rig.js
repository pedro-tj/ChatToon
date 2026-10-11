// Shared rig for the procedural characters: eyes with lids, brows, a morph-target
// mouth, emotion presets with smooth interpolation, blinking, gaze and reactions.
import * as THREE from "../vendor/three/three.module.js";

export const EMOTIONS = ["neutral", "happy", "laugh", "surprised", "confused", "annoyed", "celebrate", "thinking"];

// Expression targets. Values are blended (damped) every frame, never snapped.
const EXPRESSIONS = {
  neutral:   { smile: 0.25, frown: 0, open: 0, round: 0, browY: 0, browTilt: 0, browAsym: 0, lidUp: 0.12, lidLow: 0.05, wide: 0, tilt: 0 },
  happy:     { smile: 0.95, browY: 0.035, lidLow: 0.35, tilt: 0.05 },
  laugh:     { smile: 1, open: 0.45, lidUp: 0.04, lidLow: 0.74, browY: 0.05, tilt: 0.08 },
  surprised: { smile: 0, round: 0.85, open: 0.45, browY: 0.09, lidUp: 0, lidLow: 0, wide: 1 },
  confused:  { smile: 0, frown: 0.25, browAsym: 1, tilt: 0.22, lidUp: 0.2 },
  annoyed:   { smile: 0, frown: 0.75, browY: -0.03, browTilt: -1, lidUp: 0.42, lidLow: 0.15 },
  celebrate: { smile: 1, open: 0.35, browY: 0.07, lidLow: 0.3, wide: 0.3 },
  thinking:  { smile: 0.05, frown: 0.12, browAsym: 0.6, lidUp: 0.28, tilt: -0.12 },
};

export function expression(name) {
  return { ...EXPRESSIONS.neutral, ...(EXPRESSIONS[name] || {}) };
}

export const damp = (current, target, lambda, dt) => THREE.MathUtils.lerp(current, target, 1 - Math.exp(-lambda * dt));

export function skin(color, extra = {}) {
  return new THREE.MeshPhysicalMaterial({
    color, roughness: 0.48, metalness: 0, clearcoat: 0.35, clearcoatRoughness: 0.45,
    sheen: 0.6, sheenRoughness: 0.5, sheenColor: new THREE.Color(0xffffff), ...extra,
  });
}

// Spherical cap facing +Z (iris, pupil). Angle in radians from the centre.
function cap(radius, angle, segments = 32) {
  const g = new THREE.SphereGeometry(radius, segments, 12, 0, Math.PI * 2, 0, angle);
  g.rotateX(Math.PI / 2);
  return g;
}

export class Eye {
  constructor({ radius = 0.16, iris = 0x4a3020, lid = 0xff9ac6, irisSize = 0.62, pupilSize = 0.42, quality = 2 } = {}) {
    const seg = [16, 24, 40][quality];
    this.radius = radius;
    this.group = new THREE.Group();
    this.ball = new THREE.Group();
    this.group.add(this.ball);
    const sclera = new THREE.Mesh(new THREE.SphereGeometry(radius, seg, seg * 0.75),
      new THREE.MeshPhysicalMaterial({ color: 0xffffff, roughness: 0.12, clearcoat: 1, clearcoatRoughness: 0.05 }));
    const irisMesh = new THREE.Mesh(cap(radius * 1.004, irisSize * 0.75, seg),
      new THREE.MeshPhysicalMaterial({ color: iris, roughness: 0.3, clearcoat: 1 }));
    const pupil = new THREE.Mesh(cap(radius * 1.008, pupilSize * 0.75 * irisSize, seg),
      new THREE.MeshBasicMaterial({ color: 0x050505 }));
    this.ball.add(sclera, irisMesh, pupil);
    this.pupil = pupil;
    // Highlights stay fixed while the ball rotates: reads as a light reflection.
    const shine = new THREE.Mesh(new THREE.SphereGeometry(radius * 0.16, 12, 8), new THREE.MeshBasicMaterial({ color: 0xffffff }));
    shine.position.set(radius * 0.32, radius * 0.38, radius * 0.86);
    const shine2 = shine.clone();
    shine2.scale.setScalar(0.45);
    shine2.position.set(-radius * 0.22, -radius * 0.25, radius * 0.95);
    this.group.add(shine, shine2);
    this.shines = [shine, shine2];
    const lidMat = skin(lid, { side: THREE.DoubleSide });
    this.upper = new THREE.Mesh(new THREE.SphereGeometry(radius * 1.07, seg, seg / 2, 0, Math.PI * 2, 0, Math.PI / 2), lidMat);
    this.lower = new THREE.Mesh(new THREE.SphereGeometry(radius * 1.065, seg, seg / 2, 0, Math.PI * 2, Math.PI / 2, Math.PI / 2), lidMat);
    this.group.add(this.upper, this.lower);
  }

  // closure: 0 = wide open, 1 = shut. tilt: radians, angry/sad slant of the upper lid.
  setLids(upper, lower, tilt = 0) {
    this.upper.rotation.set(THREE.MathUtils.lerp(-1.25, 1.62, upper), 0, tilt);
    this.lower.rotation.set(THREE.MathUtils.lerp(1.15, -0.25, lower), 0, 0);
    const visible = upper < 0.9;
    for (const s of this.shines) s.visible = visible;
  }

  look(x, y) {
    this.ball.rotation.set(-y * 0.45, x * 0.55, 0);
  }
}

export class Brow {
  constructor({ length = 0.16, thickness = 0.026, color = 0x3a1e12, side = 1, quality = 2 } = {}) {
    const g = new THREE.CapsuleGeometry(thickness, length, 4 + quality * 2, 8 + quality * 4);
    g.rotateZ(Math.PI / 2);
    this.mesh = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color, roughness: 0.8 }));
    this.side = side; // -1 left, 1 right (character's point of view mirrored on screen)
    this.base = new THREE.Vector3();
  }

  place(x, y, z) {
    this.base.set(x, y, z);
    this.mesh.position.copy(this.base);
  }

  // tilt > 0: inner end up (worried); tilt < 0: inner end down (angry)
  set(y, tilt) {
    this.mesh.position.y = this.base.y + y;
    this.mesh.rotation.z = -this.side * tilt * 0.35;
  }
}

// Mouth: a dark disc with absolute morph targets (open, smile, frown, round) plus a lip
// rim (same morphs, slightly larger), a tongue and teeth that appear as it opens.
export class Mouth {
  constructor({ width = 0.3, height = 0.22, lip = 0xc2477a, quality = 2 } = {}) {
    const seg = [24, 36, 56][quality];
    this.group = new THREE.Group();
    const shapes = {
      base: (x, y) => [x * width, y * height * 0.06 + x * x * height * 0.14],
      open: (x, y) => [x * width * 0.88, y * height * 0.85 + x * x * height * 0.08 - height * 0.22],
      smile: (x, y) => [x * width * 1.18, y * height * 0.07 + x * x * height * 0.62 - height * 0.12],
      frown: (x, y) => [x * width * 0.82, y * height * 0.06 - x * x * height * 0.55 + height * 0.12],
      round: (x, y) => [x * width * 0.42, y * height * 0.62 - height * 0.12],
    };
    const make = (scale, color, z, order) => {
      const g = new THREE.CircleGeometry(1, seg);
      const pos = g.attributes.position;
      const unit = [];
      for (let i = 0; i < pos.count; i++) unit.push([pos.getX(i), pos.getY(i)]);
      const build = (fn) => {
        const arr = new Float32Array(pos.count * 3);
        unit.forEach(([x, y], i) => {
          const [px, py] = fn(x, y);
          arr[i * 3] = px * scale; arr[i * 3 + 1] = py * scale + (scale - 1) * -0.01; arr[i * 3 + 2] = 0;
        });
        return new THREE.Float32BufferAttribute(arr, 3);
      };
      g.setAttribute("position", build(shapes.base));
      g.morphAttributes.position = ["open", "smile", "frown", "round"].map((k) => build(shapes[k]));
      const m = new THREE.Mesh(g, new THREE.MeshBasicMaterial({ color, polygonOffset: true, polygonOffsetFactor: -2 - order }));
      m.position.z = z;
      m.renderOrder = order;
      this.group.add(m);
      return m;
    };
    this.lip = make(1.14, lip, 0, 1);
    this.inner = make(1.0, 0x3a0612, 0.003, 2);
    this.tongue = new THREE.Mesh(new THREE.CircleGeometry(1, 24), new THREE.MeshBasicMaterial({ color: 0xff6f8e }));
    this.tongue.position.set(0, -height * 0.42, 0.005);
    this.tongue.renderOrder = 3;
    // upper teeth: a rounded strip that hugs the top lip as the mouth opens
    const tw = width * 0.9, th = height * 0.17;
    const teethShape = new THREE.Shape();
    teethShape.moveTo(-tw / 2, 0);
    teethShape.lineTo(tw / 2, 0);
    teethShape.lineTo(tw / 2, -th * 0.6);
    teethShape.quadraticCurveTo(tw / 2, -th, tw / 2 - th * 0.4, -th);
    teethShape.lineTo(-tw / 2 + th * 0.4, -th);
    teethShape.quadraticCurveTo(-tw / 2, -th, -tw / 2, -th * 0.6);
    teethShape.closePath();
    this.teeth = new THREE.Mesh(new THREE.ShapeGeometry(teethShape, 6), new THREE.MeshBasicMaterial({ color: 0xfdfbf6 }));
    this.teeth.position.z = 0.006;
    this.teeth.renderOrder = 3;
    this.group.add(this.tongue, this.teeth);
    this.size = { width, height };
  }

  set({ open, smile, frown, round }) {
    const w = [open, smile, frown, round];
    for (const m of [this.lip, this.inner]) w.forEach((v, i) => (m.morphTargetInfluences[i] = v));
    const o = Math.max(0, open + round * 0.6);
    this.tongue.scale.set(this.size.width * 0.42 * (1 - round * 0.4), this.size.height * 0.36 * Math.min(1, o * 1.4), 1);
    this.tongue.position.y = -this.size.height * (0.28 + 0.45 * Math.min(1, o));
    this.tongue.visible = o > 0.12;
    const lift = Math.min(1, o);
    this.teeth.scale.set(1 - round * 0.5, Math.min(1, o * 1.8), 1);
    // follow the morphed top edge: closed ≈ 0.06h, open ≈ 0.63h - 0.22h, smile lifts the corners
    this.teeth.position.y = this.size.height * (0.06 + 0.36 * lift - 0.12 * smile * (1 - lift) - 0.03);
    this.teeth.visible = o > 0.15;
  }
}

// Base class: subclasses build the body and call setupFace(); this class drives expressions.
export class Character {
  constructor(options = {}) {
    this.options = options;
    this.quality = { low: 0, medium: 1, high: 2 }[options.quality] ?? 2;
    this.root = new THREE.Group();
    this.eyes = [];
    this.brows = [];
    this.mouth = null;
    this.expr = expression("neutral");
    this.cur = { ...this.expr, speak: 0 };
    this.emotion = "neutral";
    this.emotionUntil = 0;
    this.gaze = { x: 0, y: 0, tx: 0, ty: 0, next: 0 };
    this.blink = { next: 1.5, t: -1, double: false };
    this.action = null; // one-shot reaction {name, t, duration}
    this.headHeight = 2.0; // world height of the speech bubble anchor
  }

  setEmotion(name, intensity = 0.7, seconds = 4) {
    if (!EMOTIONS.includes(name)) name = "neutral";
    this.emotion = name;
    this.intensity = Math.max(0.2, Math.min(1, intensity));
    this.emotionUntil = performance.now() / 1000 + seconds;
  }

  react(name) {
    this.setEmotion(name, 1, 3);
    const duration = { laugh: 1.6, surprised: 0.9, celebrate: 1.8, annoyed: 1.0, confused: 1.2, happy: 0.9 }[name] || 0.8;
    this.action = { name, t: 0, duration };
  }

  // Shared per-frame logic. state: { phase, mouth (0..1 lip-sync level), time }
  update(dt, t, state) {
    if (this.emotion !== "neutral" && t > this.emotionUntil && state.phase !== "speaking") this.emotion = "neutral";
    const mood = state.phase === "thinking" && this.emotion === "neutral" ? "thinking" : this.emotion;
    const target = expression(mood);
    const k = mood === "neutral" ? 1 : (this.intensity ?? 0.7);
    for (const key of Object.keys(target)) {
      const neutral = EXPRESSIONS.neutral[key] ?? 0;
      const goal = neutral + (target[key] - neutral) * k;
      this.cur[key] = damp(this.cur[key], goal, 7, dt);
    }
    // Lip sync: the loudness envelope opens the jaw; quick attack, slower release.
    const speak = state.phase === "speaking" ? state.mouth : 0;
    this.cur.speak = damp(this.cur.speak, speak, speak > this.cur.speak ? 28 : 14, dt);

    if (this.action) {
      this.action.t += dt;
      if (this.action.t > this.action.duration) this.action = null;
    }
    this.updateBlink(dt, t, mood);
    this.updateGaze(dt, t, state.phase, mood);
    this.applyFace(t);
    this.animate(dt, t, state);
  }

  updateBlink(dt, t, mood) {
    const b = this.blink;
    b.next -= dt;
    if (b.t < 0 && b.next <= 0) {
      b.t = 0;
      b.double = Math.random() < 0.2;
      b.next = 2 + Math.random() * 4.5;
    }
    if (b.t >= 0) {
      b.t += dt;
      const length = b.double ? 0.42 : 0.18;
      if (b.t > length) b.t = -1;
    }
  }

  blinkAmount() {
    const b = this.blink;
    if (b.t < 0) return 0;
    const phase = b.double ? (b.t % 0.21) / 0.21 : b.t / 0.18;
    return Math.sin(Math.min(1, phase) * Math.PI);
  }

  updateGaze(dt, t, phase, mood) {
    const g = this.gaze;
    if (t > g.next) {
      if (mood === "thinking") { g.tx = -0.55 + Math.random() * 0.2; g.ty = 0.55; g.next = t + 1.2 + Math.random(); }
      else if (phase === "speaking") { g.tx = (Math.random() - 0.5) * 0.25; g.ty = (Math.random() - 0.5) * 0.15; g.next = t + 0.6 + Math.random() * 1.2; }
      else { g.tx = (Math.random() - 0.5) * 0.9; g.ty = (Math.random() - 0.5) * 0.5; g.next = t + 0.8 + Math.random() * 2.5; }
    }
    // saccades are fast
    g.x = damp(g.x, g.tx, 18, dt);
    g.y = damp(g.y, g.ty, 18, dt);
  }

  applyFace(t) {
    const c = this.cur;
    const blink = this.blinkAmount();
    const wide = c.wide;
    this.eyes.forEach((eye, i) => {
      const upper = Math.min(1, Math.max(c.lidUp * (1 - wide), blink));
      const lower = Math.min(1, c.lidLow * (1 - wide) + blink * 0.15);
      const side = i === 0 ? -1 : 1;
      eye.setLids(upper, lower, -side * c.browTilt * 0.18);
      eye.look(this.gaze.x, this.gaze.y);
      eye.group.scale.setScalar(1 + wide * 0.12);
    });
    this.brows.forEach((brow, i) => {
      const asym = i === 0 ? c.browAsym * 0.05 : -c.browAsym * 0.02;
      brow.set(c.browY + asym + c.speak * 0.012 * Math.sin(t * 9), c.browTilt + (i === 0 ? c.browAsym * 0.6 : -c.browAsym * 0.3));
    });
    if (this.mouth) {
      const talk = c.speak;
      this.mouth.set({
        open: Math.min(1, c.open * (1 - talk * 0.5) + talk * 0.95),
        smile: c.smile * (1 - talk * 0.35),
        frown: c.frown * (1 - talk * 0.4),
        round: Math.min(1, c.round + talk * 0.25 * (0.5 + 0.5 * Math.sin(t * 11))),
      });
    }
  }

  // Helpers for subclasses
  actionCurve() {
    if (!this.action) return { name: "", p: 0, s: 0 };
    const p = this.action.t / this.action.duration;
    return { name: this.action.name, p, s: Math.sin(p * Math.PI) };
  }

  animate() {}

  dispose() {
    this.root.traverse((o) => {
      if (o.geometry) o.geometry.dispose();
      if (o.material) (Array.isArray(o.material) ? o.material : [o.material]).forEach((m) => m.dispose());
    });
  }
}
