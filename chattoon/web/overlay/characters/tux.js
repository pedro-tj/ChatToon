// Tux-inspired penguin (original procedural model; Tux © Larry Ewing, created with The GIMP).
import * as THREE from "../../vendor/three/three.module.js";
import { Brow, Character, Eye, damp, skin } from "../rig.js";

// Two-part beak with the same interface as Mouth: the lower mandible is the jaw.
class Beak {
  constructor(color, quality) {
    const seg = [16, 24, 36][quality];
    const mat = new THREE.MeshPhysicalMaterial({ color, roughness: 0.32, clearcoat: 0.8, clearcoatRoughness: 0.2 });
    this.group = new THREE.Group();
    const half = (top) => {
      const g = new THREE.SphereGeometry(0.2, seg, seg / 2, 0, Math.PI * 2, top ? 0 : Math.PI / 2, Math.PI / 2);
      g.scale(1.25, top ? 0.42 : 0.3, 1);
      return g;
    };
    this.upper = new THREE.Mesh(half(true), mat);
    this.lowerPivot = new THREE.Group();
    this.lowerPivot.position.z = -0.12;
    this.lower = new THREE.Mesh(half(false), mat);
    this.lower.position.z = 0.12;
    this.lower.scale.set(0.92, 1, 0.94);
    this.lowerPivot.add(this.lower);
    const inside = new THREE.Mesh(new THREE.CircleGeometry(0.2, seg), new THREE.MeshBasicMaterial({ color: 0x5a1010, side: THREE.DoubleSide }));
    inside.rotation.x = -Math.PI / 2;
    inside.scale.set(1.15, 0.92, 1);
    this.lowerPivot.add(inside);
    inside.position.set(0, 0.001, 0.12);
    this.group.add(this.upper, this.lowerPivot);
  }

  set({ open, smile, frown, round }) {
    const jaw = Math.min(1, open + round * 0.5);
    this.lowerPivot.rotation.x = jaw * 0.55;
    this.upper.rotation.x = -jaw * 0.12;
    // a happy beak widens a little, an annoyed one narrows
    this.group.scale.set(1 + smile * 0.06 - frown * 0.04, 1, 1);
  }
}

export class Tux extends Character {
  constructor(options) {
    super(options);
    const q = this.quality;
    const seg = [24, 40, 56][q];
    const accent = new THREE.Color(options.color || "#ff8a00");
    const black = new THREE.MeshPhysicalMaterial({ color: 0x15161c, roughness: 0.35, clearcoat: 1, clearcoatRoughness: 0.18, sheen: 0.4, sheenColor: new THREE.Color(0x6a7590) });
    const white = skin(0xf6f4ef, { roughness: 0.55, sheen: 0.2 });
    this.headHeight = 2.6;

    this.body = new THREE.Group(); // waddles over the feet
    this.root.add(this.body);

    // --- egg body, belly and face mask -----------------------------------
    const egg = new THREE.SphereGeometry(0.72, seg, seg);
    const ep = egg.attributes.position;
    const v = new THREE.Vector3();
    for (let i = 0; i < ep.count; i++) {
      v.fromBufferAttribute(ep, i);
      const taper = v.y > 0 ? 1 - 0.22 * (v.y / 0.72) : 1 + 0.06 * (-v.y / 0.72);
      ep.setXYZ(i, v.x * taper, v.y * 1.3, v.z * taper * 0.92);
    }
    egg.computeVertexNormals();
    const torso = new THREE.Mesh(egg, black);
    torso.position.y = 1.0;
    this.body.add(torso);
    this.torso = torso;

    const belly = new THREE.Mesh(new THREE.SphereGeometry(0.62, seg, seg), white);
    belly.scale.set(0.95, 1.05, 0.62);
    belly.position.set(0, -0.2, 0.32);
    torso.add(belly);

    const head = new THREE.Group();
    head.position.y = 0.52;
    torso.add(head);
    this.head = head;
    const mask = new THREE.Mesh(new THREE.SphereGeometry(0.4, seg, seg), white);
    mask.scale.set(0.98, 0.72, 0.5);
    mask.position.set(0, -0.03, 0.38);
    head.add(mask);

    this.setupFace(head, accent);

    // --- flippers ----------------------------------------------------------
    this.flippers = [];
    for (const side of [-1, 1]) {
      const pivot = new THREE.Group();
      pivot.position.set(side * 0.6, 0.3, 0);
      torso.add(pivot);
      const g = new THREE.SphereGeometry(0.3, seg / 2, seg / 2);
      g.scale(0.32, 1.25, 0.6);
      g.translate(0, -0.32, 0);
      const flipper = new THREE.Mesh(g, black);
      pivot.add(flipper);
      pivot.rotation.z = side * 0.25;
      this.flippers.push(pivot);
    }

    // --- feet ---------------------------------------------------------------
    const footMat = new THREE.MeshPhysicalMaterial({ color: accent, roughness: 0.4, clearcoat: 0.6 });
    this.feet = [];
    for (const side of [-1, 1]) {
      const g = new THREE.SphereGeometry(0.2, seg / 2, seg / 3);
      g.scale(1.1, 0.35, 1.6);
      const foot = new THREE.Mesh(g, footMat);
      foot.position.set(side * 0.28, 0.06, 0.18);
      foot.rotation.y = side * -0.25;
      this.root.add(foot);
      this.feet.push(foot);
    }
  }

  setupFace(head, accent) {
    const q = this.quality;
    for (const side of [-1, 1]) {
      const eye = new Eye({ radius: 0.13, iris: 0x1b1b1b, lid: 0x15161c, irisSize: 0.75, pupilSize: 0.7, quality: q });
      eye.group.position.set(side * 0.15, 0.1, 0.5);
      eye.group.rotation.y = side * 0.2;
      eye.group.scale.set(0.9, 1.15, 0.9);
      head.add(eye.group);
      this.eyes.push(eye);
      const brow = new Brow({ side, color: 0x15161c, length: 0.12, thickness: 0.022, quality: q });
      brow.place(side * 0.16, 0.24, 0.55);
      head.add(brow.mesh);
      this.brows.push(brow);
    }
    this.mouth = new Beak(accent, q);
    this.mouth.group.position.set(0, -0.12, 0.6);
    head.add(this.mouth.group);
  }

  animate(dt, t, state) {
    const c = this.cur;
    const act = this.actionCurve();
    const talking = c.speak;
    const happy = this.emotion === "happy" || this.emotion === "celebrate";
    // waddle: rock side to side, more when happy
    const rock = Math.sin(t * (happy ? 6 : 2.2)) * (happy ? 0.1 : 0.035);
    this.body.rotation.z = damp(this.body.rotation.z, rock + (act.name === "laugh" ? Math.sin(t * 32) * 0.06 * act.s : 0), 12, dt);
    this.feet[0].position.y = 0.06 + Math.max(0, rock) * 0.6;
    this.feet[1].position.y = 0.06 + Math.max(0, -rock) * 0.6;
    let jump = 0;
    if (act.name === "celebrate") jump = Math.abs(Math.sin(act.p * Math.PI * 3)) * 0.35;
    if (act.name === "surprised") jump = act.s * 0.25;
    this.root.position.y = damp(this.root.position.y, jump, 18, dt);
    this.body.rotation.y = act.name === "celebrate" ? act.p * Math.PI * 2 : damp(this.body.rotation.y, Math.sin(t * 0.6) * 0.08, 4, dt);
    // breathing and head motion
    this.torso.scale.set(1 + Math.sin(t * 2) * 0.01, 1 + Math.sin(t * 2 + 1) * 0.012 + talking * 0.015, 1);
    this.head.rotation.z = damp(this.head.rotation.z, c.tilt * 0.9, 8, dt);
    this.head.rotation.x = damp(this.head.rotation.x, -talking * 0.1 + (act.name === "laugh" ? -0.25 * act.s : 0)
      + (state.phase === "thinking" ? -0.12 : 0), 10, dt);
    // flippers: flap when celebrating/surprised, gesture while talking, chin when thinking
    this.flippers.forEach((f, i) => {
      const side = i === 0 ? -1 : 1;
      let z = side * (0.25 + talking * 0.3 * (0.5 + 0.5 * Math.sin(t * 6 + i * 1.7)));
      let x = 0;
      if (act.name === "celebrate") z = side * (1.2 + Math.sin(t * 22) * 0.5);
      if (act.name === "surprised") z = side * (1.1 * act.s + 0.25);
      if (act.name === "annoyed") { z = side * -0.15; x = -0.4; }
      if (state.phase === "thinking" && i === 1) { z = -1.0; x = -1.0; }
      f.rotation.z = damp(f.rotation.z, z, 12, dt);
      f.rotation.x = damp(f.rotation.x, x, 10, dt);
    });
  }
}
