// Shared rig for the procedural characters: eyes with lids, brows, a morph-target
// mouth, emotion presets with smooth interpolation, blinking, gaze and reactions —
// plus the Director, the behaviour layer that keeps every avatar alive (state machine,
// idle motion, random gestures, head/eye coordination, speech beats).
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
export const clamp01 = (v) => Math.max(0, Math.min(1, v));
// angle in (-π, π]: after a full spin the body eases back the short way, never rewinds
export const wrapAngle = (a) => a - Math.PI * 2 * Math.round(a / (Math.PI * 2));
export const smooth = (a, b, x) => { const t = clamp01((x - a) / (b - a)); return t * t * (3 - 2 * t); };
// 0 → 1 → 0 over p in [0, 1] with eased shoulders (a gesture's weight over its lifetime)
export const bell = (p, rise = 0.25, fall = 0.3) => smooth(0, rise, p) * (1 - smooth(1 - fall, 1, p));

// Critically damped-ish spring: secondary motion (tails, ears, antennae, hats).
export class Spring {
  constructor(stiffness = 60, damping = 7) { this.x = 0; this.v = 0; this.k = stiffness; this.d = damping; }
  step(target, dt) {
    // sub-steps keep it stable at 30 fps and after a slow frame
    const n = Math.max(1, Math.ceil(dt / 0.012));
    const h = dt / n;
    for (let i = 0; i < n; i++) {
      const a = (target - this.x) * this.k - this.v * this.d;
      this.v += a * h;
      this.x += this.v * h;
    }
    return this.x;
  }
}

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

// Small glossy bead eye (Tux, Owl pupils…): no white, gaze moves the bead inside its socket.
export class BeadEye {
  constructor({ radius = 0.07, color = 0x101014, lid = 0xffffff, depth = 0.55, quality = 2 } = {}) {
    const seg = [12, 18, 28][quality];
    this.radius = radius;
    this.group = new THREE.Group();
    this.ball = new THREE.Group();
    this.group.add(this.ball);
    const bead = new THREE.Mesh(new THREE.SphereGeometry(radius, seg, seg * 0.75),
      new THREE.MeshPhysicalMaterial({ color, roughness: 0.18, clearcoat: 1, clearcoatRoughness: 0.08 }));
    bead.scale.z = depth;
    this.ball.add(bead);
    const shine = new THREE.Mesh(new THREE.SphereGeometry(radius * 0.26, 10, 8), new THREE.MeshBasicMaterial({ color: 0xffffff }));
    shine.position.set(radius * 0.3, radius * 0.38, radius * depth * 0.92);
    const shine2 = new THREE.Mesh(new THREE.SphereGeometry(radius * 0.12, 8, 6), new THREE.MeshBasicMaterial({ color: 0xffffff }));
    shine2.position.set(-radius * 0.28, -radius * 0.3, radius * depth * 0.9);
    this.group.add(shine, shine2);
    this.shines = [shine, shine2];
    const lidMat = new THREE.MeshStandardMaterial({ color: lid, roughness: 0.6, side: THREE.DoubleSide });
    const lidGeo = (top) => {
      const g = new THREE.SphereGeometry(radius * 1.07, seg, seg / 2, 0, Math.PI * 2, top ? 0 : Math.PI / 2, Math.PI / 2);
      g.scale(1, 1, depth * 1.12); // hugs the bead: a closing lid blends into the face, no rim
      return g;
    };
    this.upper = new THREE.Mesh(lidGeo(true), lidMat);
    this.lower = new THREE.Mesh(lidGeo(false), lidMat);
    this.group.add(this.upper, this.lower);
    // happy closed eyes: a cartoon "∩" arc replaces the bead when the cheeks push up
    const arc = new THREE.TorusGeometry(radius * 0.78, radius * 0.2, 8, [12, 18, 24][quality], Math.PI);
    this.arc = new THREE.Mesh(arc, new THREE.MeshPhysicalMaterial({ color, roughness: 0.3, clearcoat: 0.8 }));
    this.arc.position.set(0, -radius * 0.25, radius * depth * 0.55);
    this.arc.scale.set(1, 0.85, 0.6);
    this.arc.visible = false;
    this.group.add(this.arc);
  }

  // Bead eyes have no visible lids at rest (like a toy): the relaxed "neutral" lid values
  // map to fully open, and lids only appear to blink, squint or smile with the eyes.
  setLids(upper, lower, tilt = 0) {
    const u = clamp01((upper - 0.15) / 0.85), l = clamp01((lower - 0.08) / 0.92);
    const happy = l > 0.55 && u < 0.9; // laughing: show the arc instead of a half-covered bead
    this.arc.visible = happy;
    this.ball.visible = !happy;
    this.upper.visible = !happy && u > 0.02;
    this.lower.visible = !happy && l > 0.02;
    this.upper.rotation.set(THREE.MathUtils.lerp(-1.3, 1.6, u), 0, tilt);
    this.lower.rotation.set(THREE.MathUtils.lerp(1.2, -0.2, l), 0, 0);
    // highlights disappear under a lid instead of floating over it
    this.shines[0].visible = !happy && u < 0.3 && l < 0.85;
    this.shines[1].visible = !happy && l < 0.3 && u < 0.85;
  }

  look(x, y) {
    this.ball.position.set(x * this.radius * 0.28, y * this.radius * 0.22, 0);
  }
}

// ---------------------------------------------------------------------- Director
//
// One behaviour layer for every avatar. It never touches meshes: it produces smooth
// values (state weights, where to look, posture, breathing, the current gesture, speech
// beats) that each character maps onto its own anatomy. Everything is time based
// (dt in seconds, exponential damping), so 30 and 60 fps look the same.

export const STATES = ["idle", "listening", "reading", "thinking", "speaking", "reacting", "celebrating", "paused", "emergency"];
const INTENSITY = { subtle: 0.55, normal: 1, lively: 1.45 };
const FREQUENCY = { low: 1.8, normal: 1, high: 0.55 };

// Generic gestures every character understands (through look/lean); species add their own.
const BASE_GESTURES = {
  glance: { duration: 1.6, weight: 2, cooldown: 4 },
  lookAround: { duration: 3.6, weight: 1.2, cooldown: 14 },
  shift: { duration: 2.4, weight: 1.4, cooldown: 8 },
  curious: { duration: 2.2, weight: 0.8, cooldown: 16 },
};

export class Director {
  constructor(rng = Math.random) {
    this.rng = rng;
    this.cfg = { idle: true, intensity: "normal", frequency: "normal", reduceMotion: false };
    this.state = "idle";
    this.since = 0; // seconds in the current state
    this.w = Object.fromEntries(STATES.map((s) => [s, s === "idle" ? 1 : 0]));
    this.gestures = { ...BASE_GESTURES };
    this.gesture = null; // { name, t, duration, def }
    this.cooldowns = {};
    this.recent = [];
    this.nextGesture = 2.5 + rng() * 3;
    this.target = { x: 0, y: 0 }; // where the avatar wants to look (-1..1)
    this.eyes = { x: 0, y: 0 }; // eyes lead…
    this.head = { x: 0, y: 0 }; // …the head follows
    this.nextLook = 0.5;
    this.lean = { x: 0, z: 0, tx: 0, tz: 0, next: 3 };
    this.breath = 0; // -1..1
    this.breathPhase = rng() * 6;
    this.beat = 0; // decaying impulse on speech onsets (nods, hand beats)
    this.prevSpeak = 0;
    this.micro = { smile: 0, brow: 0, ts: 0, tb: 0, next: 6 };
    this.blinkRequest = false;
    this.scan = 0; // reading: eyes sweep the line
  }

  configure(cfg = {}) {
    for (const k of ["idle", "intensity", "frequency", "reduceMotion"]) if (cfg[k] !== undefined) this.cfg[k] = cfg[k];
  }

  get amp() { return (this.cfg.reduceMotion ? 0.45 : 1) * (INTENSITY[this.cfg.intensity] ?? 1); }
  get pace() { return (this.cfg.reduceMotion ? 1.6 : 1) * (FREQUENCY[this.cfg.frequency] ?? 1); }
  get still() { return this.state === "emergency"; }

  register(defs) { Object.assign(this.gestures, defs); }

  setState(name) {
    if (name === this.state) return;
    this.state = name;
    this.since = 0;
    // a random gesture that does not belong to the new state fades out early; one that was
    // asked for (preview button, a reaction to the message) plays to the end
    if (this.gesture && !this.gesture.forced && !(this.gesture.def.states || ["idle"]).includes(name)) this.gesture.cut = true;
    this.nextLook = 0;
  }

  // Start a gesture now (preview buttons, reactions to emotions). Returns false if unknown.
  play(name, force = true) {
    const def = this.gestures[name];
    if (!def || (def.big && this.cfg.reduceMotion && !force)) return false;
    this.gesture = { name, t: 0, duration: def.duration, def, cut: false, forced: force };
    this.cooldowns[name] = (def.cooldown ?? 8) * this.pace;
    this.recent = [name, ...this.recent].slice(0, 3);
    return true;
  }

  // Current gesture as { name, p (0..1 progress), s (eased weight), t (seconds) }
  curve() {
    const g = this.gesture;
    if (!g) return { name: "", p: 0, s: 0, t: 0 };
    const p = clamp01(g.t / g.duration);
    return { name: g.name, p, s: bell(p, g.def.rise ?? 0.2, g.def.fall ?? 0.28) * (g.fade ?? 1), t: g.t };
  }

  is(name) { return this.gesture?.name === name; }

  _pick() {
    const allowed = Object.entries(this.gestures).filter(([name, def]) =>
      (def.states || ["idle"]).includes(this.state) && !(this.cooldowns[name] > 0) &&
      !(def.big && this.cfg.reduceMotion) && name !== this.recent[0]);
    const total = allowed.reduce((sum, [, d]) => sum + (d.weight ?? 1), 0);
    if (!total) return null;
    let r = this.rng() * total;
    for (const [name, d] of allowed) { r -= d.weight ?? 1; if (r <= 0) return name; }
    return allowed[allowed.length - 1][0];
  }

  update(dt, t, speak = 0) {
    const rng = this.rng;
    this.since += dt;
    for (const s of STATES) this.w[s] = damp(this.w[s], s === this.state ? 1 : 0, 4.5, dt);
    for (const k in this.cooldowns) this.cooldowns[k] -= dt;

    // breathing: slower when paused, faster when excited or talking
    const rate = { paused: 0.17, emergency: 0.2, speaking: 0.36, celebrating: 0.55, reacting: 0.45 }[this.state] ?? 0.25;
    this.breathPhase += dt * rate * Math.PI * 2;
    this.breath = Math.sin(this.breathPhase);

    // speech beats: a quick rise of the voice envelope makes a nod/gesture impulse
    if (speak - this.prevSpeak > 0.28 && speak > 0.45) this.beat = 1;
    this.prevSpeak = damp(this.prevSpeak, speak, 10, dt);
    this.beat = Math.max(0, this.beat - dt * 3.2);

    // gestures: idle life (and talk gestures while speaking)
    const g = this.gesture;
    if (g) {
      g.t += dt * (g.cut ? 2.5 : 1);
      if (g.cut) g.fade = Math.max(0, (g.fade ?? 1) - dt * 3);
      if (g.t >= g.duration || g.fade === 0) this.gesture = null;
    } else if (!this.still && this.cfg.idle && this.state !== "paused") {
      this.nextGesture -= dt;
      if (this.nextGesture <= 0) {
        const name = this._pick();
        if (name) this.play(name, false);
        const base = this.state === "speaking" ? 2.5 + rng() * 3 : 3.5 + rng() * 5.5;
        this.nextGesture = base * this.pace;
      }
    }

    this._updateLook(dt, t);
    this._updateLean(dt);
    this._updateMicro(dt);
  }

  _updateLook(dt, t) {
    const rng = this.rng, a = this.cfg.idle ? Math.min(1.2, this.amp) : 0.35;
    this.nextLook -= dt;
    const tg = this.target;
    const curve = this.curve();
    switch (this.state) {
      case "listening": tg.x = 0.05 * Math.sin(t * 0.7); tg.y = 0.08; break;
      case "reading": {
        // eyes sweep along the bubble like reading a line, then jump back
        this.scan = (this.scan + dt * 0.75) % 1;
        tg.x = -0.35 + this.scan * 0.7; tg.y = 0.42;
        break;
      }
      case "thinking": if (this.nextLook <= 0) { tg.x = -0.5 + rng() * 0.2; tg.y = 0.5 + rng() * 0.1; this.nextLook = 1.4 + rng(); } break;
      case "emergency": tg.x = 0; tg.y = 0; break;
      case "paused": if (this.nextLook <= 0) { tg.x = (rng() - 0.5) * 0.4; tg.y = -0.25; this.nextLook = 3 + rng() * 3; } break;
      case "speaking":
        if (this.nextLook <= 0) {
          const away = rng() < 0.18; // now and then a short glance away, like people do
          tg.x = away ? (rng() < 0.5 ? -1 : 1) * (0.3 + rng() * 0.2) : (rng() - 0.5) * 0.18;
          tg.y = away ? (rng() - 0.3) * 0.25 : (rng() - 0.5) * 0.1;
          this.nextLook = away ? 0.5 + rng() * 0.4 : 0.9 + rng() * 1.6;
        }
        break;
      default:
        if (this.nextLook <= 0) {
          const nx = (rng() - 0.5) * 1.1 * a, ny = (rng() - 0.45) * 0.55 * a;
          if (Math.hypot(nx - tg.x, ny - tg.y) > 0.5 && rng() < 0.45) this.blinkRequest = true; // blink on big shifts
          tg.x = nx; tg.y = ny;
          this.nextLook = (0.9 + rng() * 2.6) * this.pace;
        }
    }
    // generic gestures steer the look
    let gx = 0, gy = 0;
    if (curve.name === "glance") gx = (this.gesture.side ??= rng() < 0.5 ? -1 : 1) * 0.8 * curve.s;
    if (curve.name === "lookAround") { gx = Math.sin(curve.p * Math.PI * 2) * 0.9 * curve.s; gy = 0.1 * curve.s; }
    if (curve.name === "curious") gy = 0.15 * curve.s;
    const ex = THREE.MathUtils.clamp(tg.x + gx, -1, 1), ey = THREE.MathUtils.clamp(tg.y + gy, -1, 1);
    const eyeSpeed = this.state === "reading" ? 9 : 18;
    this.eyes.x = damp(this.eyes.x, ex, eyeSpeed, dt);
    this.eyes.y = damp(this.eyes.y, ey, eyeSpeed, dt);
    const follow = this.state === "reading" ? 0.25 : 0.6; // the head turns less than the eyes
    const headSpeed = this.cfg.reduceMotion ? 1.8 : 3.2;
    this.head.x = damp(this.head.x, ex * follow, headSpeed, dt);
    this.head.y = damp(this.head.y, ey * follow, headSpeed, dt);
  }

  _updateLean(dt) {
    const l = this.lean, rng = this.rng;
    l.next -= dt;
    if (l.next <= 0 && (this.state === "idle" || this.state === "speaking")) {
      l.tx = (rng() - 0.5) * 2 * this.amp;
      l.tz = (rng() - 0.5) * 0.6 * this.amp;
      l.next = (4 + rng() * 6) * this.pace;
    }
    let tx = l.tx, tz = l.tz;
    if (this.state === "listening") { tx = 0; tz = 0.8; } // leans in to listen
    if (this.state === "paused" || this.state === "emergency") { tx = 0; tz = 0; }
    const c = this.curve();
    if (c.name === "shift") tx += (this.gesture.side ??= rng() < 0.5 ? -1 : 1) * 0.9 * c.s;
    if (!this.cfg.idle && this.state === "idle") { tx *= 0.3; tz *= 0.3; }
    l.x = damp(l.x, tx, 1.6, dt);
    l.z = damp(l.z, tz, 1.6, dt);
  }

  _updateMicro(dt) {
    const m = this.micro, rng = this.rng;
    m.next -= dt;
    if (m.next <= 0 && this.state === "idle" && this.cfg.idle) {
      const r = rng();
      m.ts = r < 0.4 ? 0.35 + rng() * 0.3 : 0; // a little smile…
      m.tb = r > 0.7 ? 0.5 + rng() * 0.5 : 0; // …or a brow raise
      m.next = (5 + rng() * 7) * this.pace;
      m.until = 1.2 + rng() * 1.5;
    }
    if (m.until !== undefined) { m.until -= dt; if (m.until <= 0) { m.ts = 0; m.tb = 0; m.until = undefined; } }
    if (this.state !== "idle") { m.ts = 0; m.tb = 0; }
    m.smile = damp(m.smile, m.ts, 3, dt);
    m.brow = damp(m.brow, m.tb, 4, dt);
  }
}

// ---------------------------------------------------------------------- Character
// Base class: subclasses build the body and call setupFace(); this class drives
// expressions, lip sync, blinking and gaze, and owns a Director for the rest.
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
    this.gaze = { x: 0, y: 0 };
    this.blink = { next: 1.5, t: -1, double: false, slow: false };
    this.action = null; // one-shot reaction {name, t, duration}
    this.headHeight = 2.0; // world height of the speech bubble anchor (fallback)
    this.bubbleAnchor = null; // Object3D on the head: the bubble follows the animation
    this.director = new Director();
    this.extent = { width: 1.6, height: 2.2 }; // rough size, for framing and the bubble
    // Who this character is, physically: which moods it drifts into when nobody talks (with
    // weights) and which of its own gestures go with a mood or with an emotion while it
    // speaks. Each species sets its own (see setPersona in characters/*.js).
    this.persona = { idleMoods: { happy: 2, thinking: 1 }, moodGestures: {}, speechGestures: {} };
    this.mood = { next: 10 + Math.random() * 8, last: "", active: false };
  }

  setPersona(persona) { this.persona = { ...this.persona, ...persona }; }

  // Idle life beyond gestures: now and then a light, short mood (a smile, a pensive look, a
  // little surprise) with a matching gesture — weighted per species, never twice in a row,
  // subtle and rarer with "reduce motion", and only while really idle.
  updateMood(t, state) {
    const d = this.director, m = this.mood;
    const free = d.cfg.idle && d.state === "idle" && state.app !== "emergency" && state.app !== "paused";
    if (!free) { m.next = Math.max(m.next, t + 6 * d.pace); m.active = false; return; }
    if (t < m.next || this.emotion !== "neutral" || this.action) return;
    const calm = d.cfg.reduceMotion;
    const options = Object.entries(this.persona.idleMoods || {})
      .filter(([name, w]) => w > 0 && EMOTIONS.includes(name) && name !== m.last && (!calm || ["happy", "thinking"].includes(name)));
    const total = options.reduce((sum, [, w]) => sum + w, 0);
    if (!total) { m.next = t + 20; return; }
    let r = d.rng() * total, mood = options[0][0];
    for (const [name, w] of options) { r -= w; if (r <= 0) { mood = name; break; } }
    const strength = { subtle: 0.75, normal: 1, lively: 1.2 }[d.cfg.intensity] ?? 1;
    this.setEmotion(mood, (calm ? 0.3 : 0.38 + d.rng() * 0.22) * strength, 1.6 + d.rng() * 1.6);
    const gesture = (this.persona.moodGestures || {})[mood];
    if (gesture && !calm && !d.gesture) d.play(gesture, false);
    m.last = mood;
    m.active = true;
    m.next = t + (16 + d.rng() * 20) * d.pace * (calm ? 1.6 : 1);
  }

  // A gesture of this species that goes with the emotion of a line it starts to say.
  speechGesture(emotion) {
    const name = (this.persona.speechGestures || {})[emotion];
    return name && this.director.gestures[name] ? this.director.play(name, false) : false;
  }

  configure(cfg) { this.director.configure(cfg); }

  setEmotion(name, intensity = 0.7, seconds = 4) {
    if (!EMOTIONS.includes(name)) name = "neutral";
    this.emotion = name;
    this.intensity = Math.max(0.2, Math.min(1, intensity));
    this.emotionUntil = (this.now ?? performance.now() / 1000) + seconds;
  }

  react(name) {
    this.setEmotion(name, 1, 3);
    const big = this.director.cfg.reduceMotion;
    const duration = { laugh: 1.6, surprised: 0.9, celebrate: big ? 1.2 : 1.8, annoyed: 1.0, confused: 1.2, happy: 0.9 }[name] || 0.8;
    this.action = { name, t: 0, duration, gentle: big };
  }

  // A gesture by name (species gestures or the generic ones). Used by the preview.
  gesture(name) { return this.director.play(name, true); }

  // Called with the viewer's message when the avatar starts paying attention to it.
  // Characters override it to react to words (the owl perks up at "Linux"…).
  hear(text) {}

  static mentionsTech(text) {
    return /\b(linux|kernel|biglinux|tux|kde|plasma|gnome|ubuntu|arch|manjaro|debian|fedora|pacman|terminal|bash|python|c\+\+|rust|programa|program|c[oó]digo|code|software livre|open ?source|github|git|servidor|server|cpu|gpu|placa de v[ií]deo|computador|computer|pc|tecnologia|tech|ia\b|ai\b)/i.test(text || "");
  }

  gestureNames() { return Object.keys(this.director.gestures); }

  resolveState(state) {
    if (state.app === "emergency") return "emergency";
    if (this.action) return this.action.name === "celebrate" ? "celebrating" : "reacting";
    if (state.app === "paused" && state.phase === "idle") return "paused";
    return { listening: "listening", reading: "reading", thinking: "thinking", speaking: "speaking" }[state.phase] || "idle";
  }

  // Shared per-frame logic. state: { phase, app, mouth (0..1 lip-sync level) }
  update(dt, t, state) {
    this.now = t;
    const d = this.director;
    const talking = state.phase === "speaking" || state.phase === "reading";
    if (this.emotion !== "neutral" && t > this.emotionUntil && !talking) this.emotion = "neutral";
    if (state.app === "emergency" && this.emotion !== "neutral") this.emotion = "neutral";
    const mood = state.phase === "thinking" && this.emotion === "neutral" ? "thinking" : this.emotion;
    const target = expression(mood);
    const k = mood === "neutral" ? 1 : (this.intensity ?? 0.7);
    for (const key of Object.keys(target)) {
      const neutral = EXPRESSIONS.neutral[key] ?? 0;
      let goal = neutral + (target[key] - neutral) * k;
      if (key === "smile") goal += d.micro.smile * 0.5;
      if (key === "browY") goal += d.micro.brow * 0.03 + d.w.listening * 0.025;
      if (key === "lidUp") goal = goal * (1 - d.w.listening * 0.6) + d.w.paused * 0.35;
      this.cur[key] = damp(this.cur[key], goal, 7, dt);
    }
    // Lip sync: the loudness envelope opens the jaw; quick attack, slower release.
    const speak = talking ? state.mouth : 0;
    this.cur.speak = damp(this.cur.speak, speak, speak > this.cur.speak ? 28 : 14, dt);

    if (this.action) {
      this.action.t += dt;
      if (this.action.t > this.action.duration) this.action = null;
    }
    d.setState(this.resolveState(state));
    this.updateMood(t, state);
    d.update(dt, t, this.cur.speak);
    this.updateBlink(dt);
    this.gaze.x = d.eyes.x;
    this.gaze.y = d.eyes.y;
    this.applyFace(t);
    this.animate(dt, t, state);
  }

  updateBlink(dt) {
    const b = this.blink, d = this.director;
    b.next -= dt;
    const want = d.blinkRequest || (b.next <= 0);
    if (b.t < 0 && want && !d.still) {
      b.t = 0;
      b.double = Math.random() < 0.18;
      b.slow = d.state === "paused" || (d.state === "idle" && Math.random() < 0.12); // lazy, slow blinks
      b.next = (d.state === "speaking" ? 1.8 : 2.2) + Math.random() * 4.5;
    }
    d.blinkRequest = false;
    if (b.t >= 0) {
      b.t += dt;
      if (b.t > this.blinkLength()) b.t = -1;
    }
  }

  blinkLength() { return this.blink.double ? 0.42 : this.blink.slow ? 0.5 : 0.18; }

  blinkAmount() {
    const b = this.blink;
    if (b.t < 0) return 0;
    if (b.double) return Math.sin(Math.min(1, (b.t % 0.21) / 0.21) * Math.PI);
    if (b.slow) return Math.min(1, Math.sin(Math.min(1, b.t / 0.5) * Math.PI) * 1.25);
    return Math.sin(Math.min(1, b.t / 0.18) * Math.PI);
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
      if (eye.group.userData.baseScale === undefined) eye.group.userData.baseScale = eye.group.scale.clone();
      eye.group.scale.copy(eye.group.userData.baseScale).multiplyScalar(1 + wide * 0.12);
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
        talk,
      });
    }
  }

  // Helpers for subclasses
  actionCurve() {
    if (!this.action) return { name: "", p: 0, s: 0 };
    const p = this.action.t / this.action.duration;
    return { name: this.action.name, p, s: Math.sin(p * Math.PI), gentle: !!this.action.gentle };
  }

  animate() {}

  dispose() {
    this.root.traverse((o) => {
      if (o.isSkinnedMesh) o.skeleton.dispose(); // frees the bone-matrix DataTexture
      if (o.geometry) o.geometry.dispose();
      if (o.material) {
        (Array.isArray(o.material) ? o.material : [o.material]).forEach((m) => {
          for (const key of ["map", "alphaMap", "roughnessMap", "normalMap", "emissiveMap"]) m[key]?.dispose();
          m.dispose();
        });
      }
    });
  }
}
