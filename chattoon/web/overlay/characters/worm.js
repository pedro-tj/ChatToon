// Minhoca: a skinned, segmented earthworm popping out of a dirt mound.
import * as THREE from "../../vendor/three/three.module.js";
import { Brow, Character, Eye, Mouth, damp, skin, smooth, wrapAngle } from "../rig.js";

const BONES = 7;
const HEIGHT = 1.55;

export class Worm extends Character {
  constructor(options) {
    super(options);
    const q = this.quality;
    const color = new THREE.Color(options.color || "#ff7eb6");
    const bodyMat = skin(color, { roughness: 0.4, sheen: 0.35, sheenColor: color.clone().offsetHSL(0, 0, 0.15), clearcoat: 0.5 });
    this.headHeight = HEIGHT + 0.85;

    // --- skeleton -------------------------------------------------------
    this.bones = [];
    let parent = null;
    for (let i = 0; i <= BONES; i++) {
      const bone = new THREE.Bone();
      bone.position.y = i === 0 ? 0 : HEIGHT / BONES;
      if (parent) parent.add(bone);
      this.bones.push(bone);
      parent = bone;
    }

    // --- body: ringed cylinder skinned to the bone chain -----------------
    const radial = [16, 28, 40][q];
    const rows = [30, 48, 72][q];
    const g = new THREE.CylinderGeometry(0.3, 0.34, HEIGHT, radial, rows, true);
    g.translate(0, HEIGHT / 2, 0);
    const pos = g.attributes.position;
    const skinIndex = [];
    const skinWeight = [];
    const v = new THREE.Vector3();
    for (let i = 0; i < pos.count; i++) {
      v.fromBufferAttribute(pos, i);
      const h = v.y / HEIGHT;
      // annuli (segments) + clitellum (the lighter band real worms have)
      let r = 1 + 0.045 * Math.pow(Math.abs(Math.sin(h * Math.PI * 11)), 0.6);
      const band = Math.exp(-Math.pow((h - 0.66) / 0.06, 2));
      r += band * 0.09;
      v.x *= r; v.z *= r;
      pos.setXYZ(i, v.x, v.y, v.z);
      const s = h * BONES;
      const idx = Math.min(BONES - 1, Math.floor(s));
      const w = s - idx;
      skinIndex.push(idx, idx + 1, 0, 0);
      skinWeight.push(1 - w, w, 0, 0);
    }
    g.computeVertexNormals();
    g.setAttribute("skinIndex", new THREE.Uint16BufferAttribute(skinIndex, 4));
    g.setAttribute("skinWeight", new THREE.Float32BufferAttribute(skinWeight, 4));
    const body = new THREE.SkinnedMesh(g, bodyMat);
    body.add(this.bones[0]);
    body.bind(new THREE.Skeleton(this.bones));
    body.castShadow = true;
    this.body = body;
    this.root.add(body);

    const bandMat = skin(color.clone().offsetHSL(0.01, -0.05, 0.12), { roughness: 0.5 });
    const clitellum = new THREE.Mesh(new THREE.TorusGeometry(0.335, 0.05, 10, radial), bandMat);
    clitellum.rotation.x = Math.PI / 2;
    clitellum.scale.z = 1.6;
    this.bones[Math.round(BONES * 0.66)].add(clitellum);
    clitellum.position.y = HEIGHT / BONES * (0.66 * BONES - Math.round(BONES * 0.66));

    // --- head (child of the top bone, so it follows the body) -------------
    const head = new THREE.Group();
    head.position.y = 0.32;
    this.bones[BONES].add(head);
    this.head = head;
    const skull = new THREE.Mesh(new THREE.SphereGeometry(0.46, radial + 8, radial), bodyMat);
    skull.scale.set(1, 0.96, 0.92);
    head.add(skull);

    this.setupFace(head, color);

    // --- dirt mound -------------------------------------------------------
    const dirt = new THREE.Group();
    const mound = new THREE.SphereGeometry(0.85, radial + 8, 12, 0, Math.PI * 2, 0, Math.PI / 2);
    const mp = mound.attributes.position;
    for (let i = 0; i < mp.count; i++) {
      v.fromBufferAttribute(mp, i);
      const n = 1 + 0.08 * Math.sin(v.x * 9) * Math.cos(v.z * 7) + 0.05 * Math.sin(v.x * 23 + v.z * 17);
      mp.setXYZ(i, v.x * n, v.y * 0.42 * n, v.z * n);
    }
    mound.computeVertexNormals();
    const dirtMat = new THREE.MeshStandardMaterial({ color: 0x6b4423, roughness: 1 });
    dirt.add(new THREE.Mesh(mound, dirtMat));
    const pebbleMat = new THREE.MeshStandardMaterial({ color: 0x8a7a66, roughness: 0.9 });
    for (let i = 0; i < [3, 6, 9][q]; i++) {
      const a = (i / 9) * Math.PI * 2 + 0.4;
      const pebble = new THREE.Mesh(new THREE.DodecahedronGeometry(0.05 + (i % 3) * 0.02, 0), pebbleMat);
      pebble.position.set(Math.cos(a) * 0.62, 0.12 + (i % 2) * 0.05, Math.sin(a) * 0.55);
      dirt.add(pebble);
    }
    dirt.position.y = -0.02;
    this.root.add(dirt);
    this.dirt = dirt;
    this.root.position.y = 0;

    this.bubbleAnchor = new THREE.Object3D();
    this.bubbleAnchor.position.set(0, 0.62, 0);
    head.add(this.bubbleAnchor);
    this.extent = { width: 1.7, height: 2.45 };
    this.director.register({
      stretch: { duration: 2.6, weight: 0.8, cooldown: 20 },
      wiggle: { duration: 2.0, weight: 1.1, cooldown: 10, states: ["idle", "speaking"] },
      peek: { duration: 3.0, weight: 0.5, cooldown: 35, big: true },
      headBob: { duration: 1.6, weight: 1, cooldown: 9 },
      dig: { duration: 2.2, weight: 0.5, cooldown: 28 },
      sassy: { duration: 1.4, weight: 1.4, cooldown: 4, states: ["speaking"] },
    });
    // mischievous: giggles to herself, peeks out of the dirt, sways with attitude
    this.setPersona({
      idleMoods: { laugh: 3, happy: 2, surprised: 1, thinking: 1, annoyed: 0.6 },
      moodGestures: { laugh: "wiggle", happy: "headBob", surprised: "peek", thinking: "lookAround", annoyed: "stretch" },
      speechGestures: { laugh: "sassy", annoyed: "sassy", happy: "wiggle", celebrate: "wiggle" },
    });
  }

  hear(text) {
    if (/\b(sono|dormir|cansad|pregui|sleep|tired)/i.test(text || "")) this.director.play("stretch");
    else if (Character.mentionsTech(text)) this.director.play("headBob");
  }

  setupFace(head, color) {
    const q = this.quality;
    const lid = color.clone().offsetHSL(0, 0, -0.04).getHex();
    for (const side of [-1, 1]) {
      const eye = new Eye({ radius: 0.16, iris: 0x3d2716, lid, quality: q });
      eye.group.position.set(side * 0.17, 0.1, 0.36);
      eye.group.rotation.y = side * 0.18;
      head.add(eye.group);
      this.eyes.push(eye);
      const brow = new Brow({ side, color: 0x5a1f3a, quality: q });
      brow.place(side * 0.18, 0.31, 0.39);
      head.add(brow.mesh);
      this.brows.push(brow);
      const cheek = new THREE.Mesh(new THREE.CircleGeometry(0.07, 20),
        new THREE.MeshBasicMaterial({ color: 0xff4f8b, transparent: true, opacity: 0.35, depthWrite: false }));
      cheek.position.set(side * 0.29, -0.08, 0.35);
      cheek.rotation.y = side * 0.65;
      head.add(cheek);
    }
    this.mouth = new Mouth({ width: 0.22, height: 0.15, lip: color.clone().offsetHSL(0, 0.1, -0.22).getHex(), quality: q });
    this.mouth.group.position.set(0, -0.06, 0.44);
    this.mouth.group.rotation.x = -0.32;
    head.add(this.mouth.group);
  }

  animate(dt, t, state) {
    const c = this.cur, d = this.director, a = d.amp;
    const act = this.actionCurve();
    const g = d.curve();
    const still = d.state === "emergency";
    const energy = (state.phase === "speaking" ? 1 : 0.55) * (still ? 0.15 : 1) * (0.6 + 0.4 * a);
    // S-shaped sway travelling up the body; the whole worm leans with the posture shift
    for (let i = 1; i <= BONES; i++) {
      const k = i / BONES;
      const wave = Math.sin(t * 1.6 - i * 0.55) * 0.06 * energy;
      const curl = 0.11 * Math.sin(i * 0.95 + 0.6);  // resting S-curve: worms are never straight
      let z = curl + wave + c.tilt * 0.06 * k + d.lean.x * 0.03 * a - d.head.x * 0.05 * k;
      let x = 0.035 + Math.sin(t * 1.1 - i * 0.4) * 0.03 * energy + c.speak * 0.035 * Math.sin(t * 7 + i)
        + d.lean.z * 0.03 + d.w.listening * 0.05 * k - d.beat * 0.04 * k;
      if (g.name === "wiggle") z += Math.sin(t * 9 - i * 0.9) * 0.09 * g.s;
      if (g.name === "stretch") x -= 0.05 * g.s;
      if (g.name === "sassy") z += Math.sin(g.p * Math.PI * 2) * 0.07 * g.s * k;
      if (act.name === "laugh") z += Math.sin(t * 34 + i) * 0.06 * act.s;
      if (act.name === "annoyed") x -= 0.09 * act.s;
      if (act.name === "confused") z += 0.06 * act.s * Math.sin(act.p * Math.PI * 2);
      if (state.phase === "thinking") z += 0.05 * k * d.w.thinking;
      this.bones[i].rotation.z = damp(this.bones[i].rotation.z, z, 10, dt);
      this.bones[i].rotation.x = damp(this.bones[i].rotation.x, x, 10, dt);
    }
    // breathing + stretch on surprise/celebration; peek = dive into the dirt and pop out
    let stretch = 1 + d.breath * 0.012 * a + c.speak * 0.03 - d.w.paused * 0.04
      + (act.name === "surprised" ? 0.18 * act.s : 0) + (act.name === "celebrate" ? 0.12 * act.s : 0)
      + (g.name === "stretch" ? 0.16 * g.s : 0);
    if (g.name === "peek") stretch -= 0.55 * smooth(0.1, 0.35, g.p) * (1 - smooth(0.6, 0.9, g.p));
    if (g.name === "dig") stretch -= 0.12 * Math.abs(Math.sin(g.p * Math.PI * 3)) * g.s;
    this.bones[0].scale.y = damp(this.bones[0].scale.y, stretch, 12, dt);
    this.head.scale.y = 1 / this.bones[0].scale.y; // the body stretches/retracts, the head keeps its shape
    const spin = act.name === "celebrate" && !act.gentle ? act.p * Math.PI * 2 : 0;
    this.bones[0].rotation.y = spin || damp(wrapAngle(this.bones[0].rotation.y), d.head.x * 0.25, 4, dt);
    let roll = c.tilt + Math.sin(t * 0.9) * 0.04 * a + d.head.x * -0.1;
    if (g.name === "headBob") roll += Math.sin(g.p * Math.PI * 4) * 0.12 * g.s;
    if (g.name === "curious" || d.w.listening > 0.4) roll += 0.15 * Math.max(g.name === "curious" ? g.s : 0, d.w.listening);
    this.head.rotation.z = damp(this.head.rotation.z, roll, 8, dt);
    this.head.rotation.y = damp(this.head.rotation.y, d.head.x * 0.4, 6, dt);
    this.head.rotation.x = damp(this.head.rotation.x, -c.speak * 0.12 - d.head.y * 0.25 - d.beat * 0.06
      + (state.phase === "thinking" ? -0.12 : 0), 10, dt);
    this.dirt.scale.y = 1 + (act.name === "celebrate" ? 0.08 * act.s : 0) + (g.name === "dig" ? 0.06 * g.s : 0);
  }
}
