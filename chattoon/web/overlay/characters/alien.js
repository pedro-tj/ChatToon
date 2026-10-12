// E.T.: big-headed, levitating alien with spring antennae and a glowing hover ring.
import * as THREE from "../../vendor/three/three.module.js";
import { Brow, Character, Eye, Mouth, Spring, damp, skin, wrapAngle } from "../rig.js";

export class Alien extends Character {
  constructor(options) {
    super(options);
    const q = this.quality;
    const seg = [20, 32, 48][q];
    const color = new THREE.Color(options.color || "#6fd65a");
    const skinMat = skin(color, { roughness: 0.35, clearcoat: 0.8, clearcoatRoughness: 0.25, sheen: 0.3 });
    const glow = new THREE.Color(0x5ef2ff);
    this.headHeight = 2.75;

    this.float = new THREE.Group(); // everything that levitates
    this.root.add(this.float);

    // --- body: silver suit, glowing emblem, arms ---------------------------
    const suit = new THREE.MeshPhysicalMaterial({ color: 0xd6dbe6, metalness: 0.85, roughness: 0.28, clearcoat: 1 });
    const torso = new THREE.Mesh(new THREE.CapsuleGeometry(0.3, 0.42, 6 + q * 2, seg), suit);
    torso.position.y = 0.95;
    torso.scale.set(1, 1, 0.85);
    this.float.add(torso);
    this.emblemMat = new THREE.MeshStandardMaterial({ color: 0x0b2730, emissive: glow, emissiveIntensity: 1.4 });
    const emblem = new THREE.Mesh(new THREE.CircleGeometry(0.085, 6), this.emblemMat);
    emblem.position.set(0, 0.06, 0.262);
    torso.add(emblem);
    const collar = new THREE.Mesh(new THREE.TorusGeometry(0.2, 0.045, 10, seg), suit);
    collar.rotation.x = Math.PI / 2;
    collar.position.y = 0.4;
    torso.add(collar);

    this.arms = [];
    for (const side of [-1, 1]) {
      const shoulder = new THREE.Group();
      shoulder.position.set(side * 0.33, 0.22, 0);
      torso.add(shoulder);
      const arm = new THREE.Mesh(new THREE.CapsuleGeometry(0.075, 0.38, 4, 12), suit);
      arm.position.y = -0.24;
      shoulder.add(arm);
      const hand = new THREE.Mesh(new THREE.SphereGeometry(0.1, 16, 12), skinMat);
      hand.position.y = -0.5;
      hand.scale.set(1, 1.1, 0.85);
      shoulder.add(hand);
      shoulder.rotation.z = side * 0.18;
      this.arms.push(shoulder);
    }

    // --- head: egg-shaped, wider at the top --------------------------------
    const head = new THREE.Group();
    head.position.y = 1.78;
    this.float.add(head);
    this.head = head;
    const hg = new THREE.SphereGeometry(0.6, seg + 8, seg);
    const hp = hg.attributes.position;
    const v = new THREE.Vector3();
    for (let i = 0; i < hp.count; i++) {
      v.fromBufferAttribute(hp, i);
      const widen = 1 + 0.18 * Math.max(0, v.y / 0.6);
      const chin = v.y < 0 ? 1 - 0.28 * Math.pow(-v.y / 0.6, 1.6) : 1;
      hp.setXYZ(i, v.x * widen * chin, v.y * 1.02, v.z * widen * chin * 0.95);
    }
    hg.computeVertexNormals();
    head.add(new THREE.Mesh(hg, skinMat));

    // --- antennae with glowing tips on springs -----------------------------
    this.antennae = [];
    this.tipMats = [];
    for (const side of [-1, 1]) {
      const pivot = new THREE.Group();
      pivot.position.set(side * 0.24, 0.5, -0.05);
      head.add(pivot);
      const curve = new THREE.CatmullRomCurve3([
        new THREE.Vector3(0, 0, 0), new THREE.Vector3(side * 0.06, 0.18, 0), new THREE.Vector3(side * 0.16, 0.34, 0.02),
      ]);
      pivot.add(new THREE.Mesh(new THREE.TubeGeometry(curve, 16, 0.022, 8), skinMat));
      const mat = new THREE.MeshStandardMaterial({ color: 0x103038, emissive: glow, emissiveIntensity: 1.6 });
      const tip = new THREE.Mesh(new THREE.SphereGeometry(0.06, 16, 12), mat);
      tip.position.set(side * 0.16, 0.36, 0.02);
      pivot.add(tip);
      this.tipMats.push(mat);
      this.antennae.push({ pivot, side, sx: new Spring(70, 6), sz: new Spring(70, 6) });
    }
    this.prevHead = new THREE.Vector3();
    this.tmp = new THREE.Vector3();

    this.setupFace(head, color);

    // --- hover ring and beam ------------------------------------------------
    this.ringMat = new THREE.MeshBasicMaterial({ color: glow, transparent: true, opacity: 0.85 });
    const ring = new THREE.Mesh(new THREE.TorusGeometry(0.42, 0.025, 8, seg + 16), this.ringMat);
    ring.rotation.x = Math.PI / 2;
    ring.position.y = 0.2;
    this.root.add(ring);
    this.ring = ring;
    const beam = new THREE.Mesh(new THREE.CylinderGeometry(0.3, 0.45, 0.55, seg, 1, true),
      new THREE.MeshBasicMaterial({ color: glow, transparent: true, opacity: 0.12, depthWrite: false,
        blending: THREE.AdditiveBlending, side: THREE.DoubleSide }));
    beam.position.y = 0.45;
    this.root.add(beam);
    this.beam = beam;

    this.bubbleAnchor = new THREE.Object3D();
    this.bubbleAnchor.position.set(0, 0.95, 0); // above the antennae
    head.add(this.bubbleAnchor);
    this.extent = { width: 1.4, height: 2.75 };
    this.director.register({
      scan: { duration: 3.2, weight: 1, cooldown: 14 },
      beep: { duration: 1.4, weight: 1.1, cooldown: 9, states: ["idle", "speaking"] },
      wave: { duration: 2.2, weight: 0.8, cooldown: 22 },
      orbit: { duration: 3.0, weight: 0.5, cooldown: 30, big: true },
      probe: { duration: 2.2, weight: 0.8, cooldown: 16 },
      point: { duration: 1.5, weight: 1.4, cooldown: 4, states: ["speaking"] },
    });
  }

  hear(text) {
    if (Character.mentionsTech(text)) this.director.play("beep");
    else this.director.play("probe");
  }

  setupFace(head, color) {
    const q = this.quality;
    const lid = color.clone().offsetHSL(0, -0.05, -0.08).getHex();
    for (const side of [-1, 1]) {
      const eye = new Eye({ radius: 0.2, iris: 0x2b1550, lid, irisSize: 0.74, pupilSize: 0.55, quality: q });
      eye.group.position.set(side * 0.22, 0.06, 0.45);
      eye.group.rotation.y = side * 0.22;
      head.add(eye.group);
      this.eyes.push(eye);
      const brow = new Brow({ side, color: color.clone().offsetHSL(0, 0, -0.28).getHex(), length: 0.17, quality: q });
      brow.place(side * 0.23, 0.33, 0.5);
      head.add(brow.mesh);
      this.brows.push(brow);
    }
    this.mouth = new Mouth({ width: 0.19, height: 0.14, lip: color.clone().offsetHSL(0, 0.05, -0.3).getHex(), quality: q });
    this.mouth.group.position.set(0, -0.26, 0.47);
    this.mouth.group.rotation.x = -0.3;
    head.add(this.mouth.group);
  }

  animate(dt, t, state) {
    const c = this.cur, d = this.director, a = d.amp;
    const act = this.actionCurve();
    const g = d.curve();
    const talking = c.speak;
    const still = d.state === "emergency";
    // levitation (the root rises; the overlay shrinks the contact shadow accordingly)
    let lift = Math.sin(t * 1.6) * 0.06 * (still ? 0.3 : 1) + d.breath * 0.01 - d.w.paused * 0.05;
    if (act.name === "surprised" || act.name === "celebrate") lift += (act.gentle ? 0.12 : 0.35) * act.s;
    if (g.name === "orbit") lift += 0.12 * g.s;
    this.root.position.y = damp(this.root.position.y, lift, 10, dt);
    const spin = (act.name === "celebrate" && !act.gentle ? act.p * Math.PI * 2 : 0) + (g.name === "orbit" ? g.p * Math.PI * 2 : 0);
    this.float.rotation.y = spin || damp(wrapAngle(this.float.rotation.y), Math.sin(t * 0.5) * 0.12 * a + d.head.x * 0.2, 4, dt);
    this.float.rotation.z = damp(this.float.rotation.z, act.name === "laugh" ? Math.sin(t * 30) * 0.05 * act.s
      : Math.sin(t * 0.8) * 0.03 * a + d.lean.x * 0.04, 12, dt);
    this.float.rotation.x = damp(this.float.rotation.x, d.lean.z * 0.05 + d.w.listening * 0.06 + (g.name === "probe" ? 0.12 * g.s : 0), 6, dt);
    let yaw = d.head.x * 0.5, roll = c.tilt * 1.1;
    if (g.name === "scan") yaw += Math.sin(g.p * Math.PI * 2) * 0.6 * g.s;
    if (g.name === "curious" || g.name === "probe") roll += 0.18 * g.s;
    this.head.rotation.y = damp(this.head.rotation.y, yaw, 6, dt);
    this.head.rotation.z = damp(this.head.rotation.z, roll, 8, dt);
    this.head.rotation.x = damp(this.head.rotation.x, -talking * 0.1 - d.head.y * 0.3 - d.beat * 0.07
      + (state.phase === "thinking" ? -0.15 : 0), 10, dt);
    this.head.scale.setScalar(1 + (act.name === "surprised" ? 0.06 * act.s : 0) + d.breath * 0.005);

    // arms: gestures while talking, up when celebrating, hand to chin when thinking
    this.arms.forEach((arm, i) => {
      const side = i === 0 ? -1 : 1;
      let z = side * (0.18 + talking * 0.25 * (0.5 + 0.5 * Math.sin(t * 5 + i * 2)) + d.beat * 0.2);
      let x = Math.sin(t * 1.3 + i) * 0.05 * a;
      if (!still) {
        if (g.name === "wave" && i === 1) { z = 2.6 + Math.sin(t * 10) * 0.35 * g.s; z = side * (0.18 + (z - 0.18) * g.s); }
        if (g.name === "point" && i === 1) { z = side * (0.18 + 1.1 * g.s); x = -0.9 * g.s; }
        if (act.name === "celebrate" || act.name === "surprised") z = side * (0.18 + 2.4 * act.s);
        if (state.phase === "thinking" && i === 1) { z = -0.9; x = -1.2; }
        if (act.name === "annoyed") { z = side * -0.5; x = -0.6; }
      }
      arm.rotation.z = damp(arm.rotation.z, z, 9, dt);
      arm.rotation.x = damp(arm.rotation.x, x, 9, dt);
    });

    // antennae lag behind head movement (springs) and one droops when confused
    this.head.getWorldPosition(this.tmp);
    const vx = (this.tmp.x - this.prevHead.x) / Math.max(dt, 1e-3);
    const vy = (this.tmp.y - this.prevHead.y) / Math.max(dt, 1e-3);
    this.prevHead.copy(this.tmp);
    for (const ant of this.antennae) {
      const droop = (state.phase === "thinking" || this.emotion === "confused") && ant.side < 0 ? 0.5 : 0;
      const wiggle = g.name === "beep" ? Math.sin(t * 24 + ant.side) * 0.25 * g.s : 0;
      ant.pivot.rotation.z = ant.sz.step(-vx * 0.15 + droop + Math.sin(t * 2 + ant.side) * 0.05 + wiggle, dt);
      ant.pivot.rotation.x = ant.sx.step(vy * 0.12 + (act.name === "surprised" ? -0.4 * act.s : 0) - d.w.listening * 0.2, dt);
    }
    // glow follows the voice (and beeps)
    const beep = g.name === "beep" ? Math.abs(Math.sin(g.p * Math.PI * 6)) * 2 * g.s : 0;
    const pulse = 1.2 + talking * 2.5 + Math.sin(t * 3) * 0.2 + beep + (g.name === "scan" ? g.s : 0);
    for (const m of this.tipMats) m.emissiveIntensity = pulse;
    this.emblemMat.emissiveIntensity = 1 + talking * 1.5 + beep * 0.5;
    this.ring.scale.setScalar(1 + Math.sin(t * 3) * 0.04 + (act.name ? 0.15 * act.s : 0));
    this.ringMat.opacity = 0.55 + 0.3 * Math.sin(t * 3);
    this.beam.material.opacity = 0.08 + talking * 0.1 + (g.name === "scan" ? 0.08 * g.s : 0);
  }
}
