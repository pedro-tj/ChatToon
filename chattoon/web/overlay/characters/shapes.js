// Procedural building blocks shared by the characters: lathe bodies with elliptical
// cross-sections, markings painted from signed-distance shapes (smooth, seamless — no
// decals floating over the body), spine skinning and a few reusable props.
import * as THREE from "../../vendor/three/three.module.js";

// Sample a smooth profile (radius, height) through control points.
export function profile(points, samples = 48) {
  const curve = new THREE.SplineCurve(points.map(([r, y]) => new THREE.Vector2(r, y)));
  return curve.getPoints(samples).map((p) => new THREE.Vector2(Math.max(0, p.x), p.y));
}

// Radius of a sampled profile at height y (linear between samples).
export function radiusAt(points, y) {
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1], b = points[i];
    if ((y >= a.y && y <= b.y) || (y <= a.y && y >= b.y)) {
      const t = b.y === a.y ? 0 : (y - a.y) / (b.y - a.y);
      return a.x + (b.x - a.x) * t;
    }
  }
  return 0;
}

// Lathe around Y with depth scaled by `depth` (elliptical sections). The seam faces back
// and normals are transformed properly, so the surface stays perfectly smooth.
export function latheBody(points, { segments = 48, depth = 0.85, front = 1 } = {}) {
  const g = new THREE.LatheGeometry(points, segments, Math.PI, Math.PI * 2);
  const pos = g.attributes.position, nor = g.attributes.normal;
  const n = new THREE.Vector3();
  for (let i = 0; i < pos.count; i++) {
    const z = pos.getZ(i);
    pos.setZ(i, z * depth * (z > 0 ? front : 1));
    n.fromBufferAttribute(nor, i);
    n.z /= depth * (z > 0 ? front : 1);
    n.normalize();
    nor.setXYZ(i, n.x, n.y, n.z);
  }
  g.computeBoundingSphere();
  return g;
}

// Front-projected UVs (x, y → u, v) plus a vertex-colour "frontness" that fades the
// painted markings to the base colour on the back. Returns the box used.
export function frontUV(geometry, box) {
  const pos = geometry.attributes.position;
  const uv = new Float32Array(pos.count * 2);
  const col = new Float32Array(pos.count * 3);
  const { x0, x1, y0, y1, fade = [0.0, 0.35] } = box;
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i), y = pos.getY(i), z = pos.getZ(i);
    uv[i * 2] = (x - x0) / (x1 - x0);
    uv[i * 2 + 1] = (y - y0) / (y1 - y0);
    const r = Math.max(1e-3, Math.hypot(x, z));
    const f = THREE.MathUtils.smoothstep(z / r, fade[0], fade[1]);
    col[i * 3] = col[i * 3 + 1] = col[i * 3 + 2] = f;
  }
  geometry.setAttribute("uv", new THREE.BufferAttribute(uv, 2));
  geometry.setAttribute("frontness", new THREE.BufferAttribute(col, 3));
  return box;
}

// Smooth minimum of signed distances (blends shapes like clay).
export const smin = (a, b, k) => {
  const h = Math.max(k - Math.abs(a - b), 0) / k;
  return Math.min(a, b) - h * h * k * 0.25;
};
export const sdCircle = (x, y, cx, cy, r) => Math.hypot(x - cx, y - cy) - r;
export const sdEllipse = (x, y, cx, cy, rx, ry) => {
  const dx = (x - cx) / rx, dy = (y - cy) / ry;
  return (Math.hypot(dx, dy) - 1) * Math.min(rx, ry);
};

// Painted canvases are kept per `key`: switching back to a character reuses them instead
// of evaluating the shapes again (the GPU texture itself is still freed on dispose).
const paintedCanvases = new Map();

// Paint a two-colour (or more) marking texture: layers = [{ color, sdf(x, y) }] drawn
// in order over `base`; edges are anti-aliased with `soft` world units. Pass a `key` that
// identifies the result (character, colours, size) to cache the painting.
export function markingTexture(box, base, layers, { size = 512, soft = 0.012, key = "" } = {}) {
  const cached = key && paintedCanvases.get(key);
  if (cached) return canvasTexture(cached);
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const g = c.getContext("2d");
  const img = g.createImageData(size, size);
  const baseC = new THREE.Color(base);
  const cols = layers.map((l) => new THREE.Color(l.color));
  const { x0, x1, y0, y1 } = box;
  for (let py = 0; py < size; py++) {
    const y = y1 - (py + 0.5) / size * (y1 - y0);
    for (let px = 0; px < size; px++) {
      const x = x0 + (px + 0.5) / size * (x1 - x0);
      let r = baseC.r, gg = baseC.g, b = baseC.b;
      for (let i = 0; i < layers.length; i++) {
        const d = layers[i].sdf(x, y);
        const a = 1 - THREE.MathUtils.smoothstep(d, -soft, soft);
        if (a > 0) {
          r += (cols[i].r - r) * a; gg += (cols[i].g - gg) * a; b += (cols[i].b - b) * a;
        }
      }
      const o = (py * size + px) * 4;
      img.data[o] = Math.round(Math.pow(r, 1 / 2.2) * 255);
      img.data[o + 1] = Math.round(Math.pow(gg, 1 / 2.2) * 255);
      img.data[o + 2] = Math.round(Math.pow(b, 1 / 2.2) * 255);
      img.data[o + 3] = 255;
    }
  }
  g.putImageData(img, 0, 0);
  if (key) paintedCanvases.set(key, c);
  return canvasTexture(c);
}

function canvasTexture(canvas) {
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  return tex;
}

// Material that shows the marking texture on the front and `back` on the rest, using
// the "frontness" attribute written by frontUV().
export function markedMaterial(map, back, params = {}) {
  const m = new THREE.MeshPhysicalMaterial({ map, roughness: 0.5, ...params });
  const backColor = new THREE.Color(back);
  m.onBeforeCompile = (shader) => {
    shader.uniforms.backColor = { value: backColor };
    shader.vertexShader = shader.vertexShader
      .replace("#include <common>", "#include <common>\nattribute vec3 frontness;\nvarying float vFront;")
      .replace("#include <begin_vertex>", "#include <begin_vertex>\nvFront = frontness.x;");
    shader.fragmentShader = shader.fragmentShader
      .replace("#include <common>", "#include <common>\nuniform vec3 backColor;\nvarying float vFront;")
      .replace("#include <map_fragment>",
        "#include <map_fragment>\ndiffuseColor.rgb = mix(backColor, diffuseColor.rgb, vFront);");
  };
  m.customProgramCacheKey = () => "marked";
  return m;
}

// Skin a geometry to a vertical chain of bones by height: weights[i](y) must sum to 1.
export function skinByHeight(geometry, weightFns) {
  const pos = geometry.attributes.position;
  const idx = [], wts = [];
  for (let i = 0; i < pos.count; i++) {
    const y = pos.getY(i);
    const w = weightFns.map((f) => Math.max(0, f(y)));
    const order = w.map((v, j) => [v, j]).sort((a, b) => b[0] - a[0]).slice(0, 4);
    const sum = order.reduce((s, [v]) => s + v, 0) || 1;
    for (let k = 0; k < 4; k++) {
      idx.push(order[k] ? order[k][1] : 0);
      wts.push(order[k] ? order[k][0] / sum : 0);
    }
  }
  geometry.setAttribute("skinIndex", new THREE.Uint16BufferAttribute(idx, 4));
  geometry.setAttribute("skinWeight", new THREE.Float32BufferAttribute(wts, 4));
}

export function boneChain(heights) {
  const bones = [];
  let prevY = 0;
  heights.forEach((y, i) => {
    const b = new THREE.Bone();
    b.position.y = i === 0 ? y : y - prevY;
    if (i > 0) bones[i - 1].add(b);
    bones.push(b);
    prevY = y;
  });
  return bones;
}

// Classic top hat: slightly flared crown, curled brim, band and a small bow.
export function topHat({ band = 0xffcc33, quality = 2 } = {}) {
  const seg = [24, 36, 56][quality];
  const group = new THREE.Group();
  const felt = new THREE.MeshPhysicalMaterial({ color: 0x121216, roughness: 0.55, clearcoat: 0.25, clearcoatRoughness: 0.5,
    sheen: 0.6, sheenRoughness: 0.4, sheenColor: new THREE.Color(0x3c4054), envMapIntensity: 0.55 });
  const crown = new THREE.LatheGeometry(profile([[0.0, 0.47], [0.2, 0.468], [0.285, 0.455], [0.297, 0.43],
    [0.288, 0.3], [0.268, 0.15], [0.262, 0.02], [0.262, 0.0]], 28), seg);
  const crownMesh = new THREE.Mesh(crown, felt);
  group.add(crownMesh);
  // brim: a flat ring whose sides curl up and whose front/back dip a little
  const brim = new THREE.LatheGeometry(profile([[0.24, 0.012], [0.33, 0.006], [0.42, 0.012], [0.452, 0.03],
    [0.445, 0.045], [0.41, 0.03], [0.33, 0.03], [0.24, 0.035]], 24), seg);
  const bp = brim.attributes.position;
  for (let i = 0; i < bp.count; i++) {
    const x = bp.getX(i), z = bp.getZ(i);
    const r = Math.hypot(x, z) || 1;
    const side = Math.abs(x) / r; // 1 at the sides
    const reach = THREE.MathUtils.smoothstep(r, 0.28, 0.45);
    bp.setY(i, bp.getY(i) + reach * (side * side * 0.085 - (1 - side * side) * 0.012));
    bp.setZ(i, z * 0.88);
  }
  brim.computeVertexNormals();
  group.add(new THREE.Mesh(brim, felt));
  const bandMat = new THREE.MeshPhysicalMaterial({ color: band, roughness: 0.4, clearcoat: 0.3, clearcoatRoughness: 0.4,
    sheen: 0.4, sheenColor: new THREE.Color(band), envMapIntensity: 0.5 });
  const bandMesh = new THREE.Mesh(new THREE.CylinderGeometry(0.268, 0.266, 0.085, seg, 1, true), bandMat);
  bandMesh.position.y = 0.085;
  group.add(bandMesh);
  const bow = new THREE.Group();
  const knot = new THREE.Mesh(new THREE.SphereGeometry(0.035, 12, 8), bandMat);
  knot.scale.set(0.8, 1, 0.6);
  bow.add(knot);
  for (const s of [-1, 1]) {
    const loop = new THREE.Mesh(new THREE.SphereGeometry(0.05, 12, 8), bandMat);
    loop.scale.set(1.25, 0.65, 0.4);
    loop.position.set(0, 0, s * 0.045);
    loop.rotation.x = s * 0.25;
    bow.add(loop);
  }
  bow.position.set(-0.27, 0.088, 0);
  group.add(bow);
  crownMesh.scale.z = 0.92;
  bandMesh.scale.z = 0.92;
  group.userData.bandMaterial = bandMat;
  return group;
}
