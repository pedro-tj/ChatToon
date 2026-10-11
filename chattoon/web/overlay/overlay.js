// ChatToon overlay: renders the avatar for OBS (Browser Source) and the app preview.
// The server only pushes events here; this page has no authority over the app.
import * as THREE from "../vendor/three/three.module.js";
import { RoomEnvironment } from "../vendor/three/RoomEnvironment.js";
import { Worm } from "./characters/worm.js";
import { Alien } from "./characters/alien.js";
import { Tux } from "./characters/tux.js";

const CHARACTERS = { worm: Worm, alien: Alien, tux: Tux };
const params = new URLSearchParams(location.search);
const role = params.get("role") === "preview" ? "preview" : "obs";
const demo = params.get("demo"); // standalone mode: ?demo=worm&emotion=happy&talk=1
if (role === "preview" || demo) document.body.classList.add("preview");
if (params.get("theme") === "light") document.body.classList.add("light");

const config = {
  character: demo || "worm", color: "", showBubble: params.get("bubble") !== "0", showAuthor: true,
  scale: 1, x: 0, y: -0.15, rotation: 0, light: 1, shadows: true, quality: params.get("quality") || "high",
  fps: 60, bubbleSeconds: 2.5, background: "transparent", zoom: Number(params.get("zoom") || 1),
};
const state = { phase: "idle", speech: null, connected: false };

// ---------------------------------------------------------------- renderer
const canvas = document.getElementById("stage");
let renderer, scene, camera, stage, character, shadow, keyLight, rimLight, hemi;

function createRenderer() {
  renderer?.dispose();
  const q = config.quality;
  renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: q !== "low", premultipliedAlpha: true,
    powerPreference: "high-performance", preserveDrawingBuffer: params.has("capture") });
  renderer.setClearColor(0x000000, 0);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 0.95;
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, q === "high" ? 2 : 1));
  resize();
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environmentIntensity = 0.75;
  pmrem.dispose();
}

function setupScene() {
  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(30, 1, 0.1, 100);
  hemi = new THREE.HemisphereLight(0xffffff, 0x3a3550, 0.4);
  keyLight = new THREE.DirectionalLight(0xfff4e6, 1.7);
  keyLight.position.set(2.5, 5, 4);
  rimLight = new THREE.DirectionalLight(0x8fd8ff, 1.2);
  rimLight.position.set(-3, 3, -4);
  scene.add(hemi, keyLight, rimLight);
  stage = new THREE.Group();
  scene.add(stage);
  // Soft contact shadow: a blurred blob is far cheaper than shadow maps.
  const c = document.createElement("canvas");
  c.width = c.height = 128;
  const g = c.getContext("2d");
  const grad = g.createRadialGradient(64, 64, 4, 64, 64, 64);
  grad.addColorStop(0, "rgba(0,0,0,0.55)");
  grad.addColorStop(1, "rgba(0,0,0,0)");
  g.fillStyle = grad;
  g.fillRect(0, 0, 128, 128);
  shadow = new THREE.Mesh(new THREE.PlaneGeometry(2.4, 2.4),
    new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(c), transparent: true, depthWrite: false }));
  shadow.rotation.x = -Math.PI / 2;
  shadow.position.y = 0.002;
  stage.add(shadow);
}

function resize() {
  const w = window.innerWidth, h = window.innerHeight;
  renderer.setSize(w, h, false);
  camera.aspect = w / Math.max(1, h);
  camera.updateProjectionMatrix();
}

function applyConfig(next) {
  const qualityChanged = next.quality && next.quality !== config.quality;
  const characterChanged = next.character && (next.character !== config.character || next.color !== config.color);
  Object.assign(config, next);
  if (qualityChanged) createRenderer();
  if (characterChanged || !character || qualityChanged) loadCharacter();
  stage.position.set(config.x * 2.4, config.y * 1.6, 0);
  stage.scale.setScalar(config.scale);
  stage.rotation.y = THREE.MathUtils.degToRad(config.rotation);
  const z = 6.6 / Math.max(0.3, config.zoom);
  camera.position.set(0, 1.45, z);
  camera.lookAt(0, 1.3, 0);
  hemi.intensity = 0.4 * config.light;
  keyLight.intensity = 1.7 * config.light;
  rimLight.intensity = 1.2 * config.light;
  shadow.visible = config.shadows;
  const bg = config.background;
  if (role === "obs" && !demo) document.body.style.background = bg === "green" ? "#00ff00" : (bg && bg !== "transparent" ? bg : "transparent");
}

function loadCharacter() {
  if (character) {
    stage.remove(character.root);
    character.dispose();
  }
  const Cls = CHARACTERS[config.character] || Worm;
  character = new Cls({ color: config.color || undefined, quality: config.quality });
  stage.add(character.root);
  rimLight.color.set(config.color || { worm: "#ff9ccd", alien: "#9dff8a", tux: "#ffd36b" }[config.character] || "#8fd8ff");
  document.documentElement.style.setProperty("--accent", config.color || { worm: "#e0559a", alien: "#3fae52", tux: "#e8a400" }[config.character]);
}

// ---------------------------------------------------------------- bubble
const bubble = document.getElementById("bubble");
const bubbleText = bubble.querySelector(".text");
const bubbleAuthor = bubble.querySelector(".author");
let bubbleHideAt = 0;

function showBubble(text, author) {
  if (!config.showBubble) return;
  bubbleAuthor.textContent = config.showAuthor && author ? author : "";
  bubbleText.textContent = "";
  const shown = document.createElement("span");
  const pending = document.createElement("span");
  pending.className = "pending";
  pending.textContent = text; // textContent: chat text is never parsed as HTML
  bubbleText.append(shown, pending);
  bubble.classList.add("show");
  bubbleHideAt = Infinity;
}

function revealBubble(fraction) {
  const [shown, pending] = bubbleText.children;
  if (!shown) return;
  const full = shown.textContent + pending.textContent;
  const n = Math.min(full.length, Math.ceil(full.length * Math.min(1, fraction * 1.15)));
  shown.textContent = full.slice(0, n);
  pending.textContent = full.slice(n);
}

function placeBubble() {
  if (!character || !bubble.classList.contains("show")) return;
  const anchor = new THREE.Vector3(0, character.headHeight, 0);
  character.root.localToWorld(anchor);
  anchor.project(camera);
  const w = window.innerWidth, h = window.innerHeight;
  let x = (anchor.x * 0.5 + 0.5) * w;
  let y = (-anchor.y * 0.5 + 0.5) * h - 10;
  const bw = bubble.offsetWidth, bh = bubble.offsetHeight;
  const cx = Math.min(w - bw / 2 - 12, Math.max(bw / 2 + 12, x));
  y = Math.max(bh + 12, y);
  bubble.style.left = `${cx}px`;
  bubble.style.top = `${y}px`;
  bubble.style.setProperty("--tail", `${Math.min(bw - 24, Math.max(24, bw / 2 + (x - cx)))}px`);
}

// ---------------------------------------------------------------- speech
let audioUnlockHint = false;

function startSpeech(msg) {
  stopSpeech(false);
  const speech = { id: msg.id, envelope: msg.envelope || [], fps: msg.fps || 50, duration: msg.duration || 2,
                   started: performance.now() / 1000, audio: null };
  state.speech = speech;
  state.phase = "speaking";
  character?.setEmotion(msg.emotion || "neutral", msg.intensity ?? 0.7, speech.duration + 2.5);
  showBubble(msg.text || "", msg.author || "");
  if (msg.audio) {
    const audio = new Audio(msg.audio);
    speech.audio = audio;
    audio.onended = () => send({ type: "ended", id: msg.id });
    audio.onerror = () => send({ type: "ended", id: msg.id });
    audio.play().catch(() => {
      // Browsers block autoplay without a click; OBS does not. Fall back to the clock.
      speech.audio = null;
      send({ type: "ended", id: msg.id });
      if (!audioUnlockHint) badge("Click the page to allow audio (not needed inside OBS)");
      audioUnlockHint = true;
    });
  }
}

function stopSpeech(hard) {
  const s = state.speech;
  if (s?.audio && hard) s.audio.pause();
  state.speech = null;
  bubbleHideAt = performance.now() / 1000 + (hard ? 0.2 : config.bubbleSeconds);
}

function speechTime(s) {
  if (s.audio && !s.audio.paused && s.audio.currentTime > 0) return s.audio.currentTime;
  return performance.now() / 1000 - s.started;
}

function mouthLevel(now) {
  const s = state.speech;
  if (!s) return 0;
  const t = speechTime(s);
  if (t > s.duration + 0.3) return 0;
  if (!s.envelope.length) { // no audio: plausible syllable rhythm
    return t < s.duration ? 0.45 + 0.4 * Math.abs(Math.sin(t * 13)) * (0.6 + 0.4 * Math.sin(t * 3.1)) : 0;
  }
  const f = t * s.fps;
  const i = Math.floor(f);
  const a = s.envelope[i] ?? 0, b = s.envelope[i + 1] ?? 0;
  return a + (b - a) * (f - i);
}

// ---------------------------------------------------------------- loop
const timer = new THREE.Timer();
let lastFrame = 0;

function frame(now) {
  requestAnimationFrame(frame);
  if (document.hidden) return; // OBS hides inactive sources: no work at all
  const minDelta = 1000 / Math.max(10, config.fps) - 1;
  if (now - lastFrame < minDelta) return;
  lastFrame = now;
  timer.update(now);
  const dt = Math.min(timer.getDelta(), 0.1);
  const seconds = performance.now() / 1000;
  const s = state.speech;
  if (s) revealBubble(speechTime(s) / Math.max(0.5, s.duration));
  if (!s && seconds > bubbleHideAt) {
    bubble.classList.remove("show");
    bubbleHideAt = Infinity;
  }
  const phase = s ? "speaking" : (state.phase === "speaking" ? "idle" : state.phase);
  character?.update(dt, seconds, { phase, mouth: mouthLevel(seconds) });
  if (character && shadow) {
    const lift = Math.max(0, character.root.position.y);
    shadow.scale.setScalar(1 - Math.min(0.5, lift * 0.4));
    shadow.material.opacity = 1 - Math.min(0.7, lift * 0.6);
  }
  renderer.render(scene, camera);
  placeBubble();
}

// ---------------------------------------------------------------- server link
let ws = null;
let retry = 0;

function send(data) {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(data));
}

function badge(text) {
  const el = document.getElementById("badge");
  el.textContent = text;
  el.hidden = !text || role === "obs" && !text.startsWith("Click");
}

function connect() {
  const url = new URL(`ws?role=${role}`, location.href);
  url.protocol = location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(url);
  ws.onopen = () => { retry = 0; state.connected = true; badge(""); };
  ws.onmessage = (ev) => {
    let msg;
    try { msg = JSON.parse(ev.data); } catch { return; }
    if (!msg || typeof msg !== "object") return;
    switch (msg.type) {
      case "config": applyConfig(msg); break;
      case "state": if (!state.speech) state.phase = msg.phase || "idle"; break;
      case "speak": startSpeech(msg); break;
      case "done": if (state.speech?.id === msg.id) stopSpeech(false); state.phase = "idle"; break;
      case "stop": stopSpeech(true); state.phase = "idle"; character?.setEmotion("neutral"); break;
      case "react": character?.react(msg.emotion); break;
    }
  };
  ws.onclose = () => {
    state.connected = false;
    if (role === "preview") badge("Connecting to ChatToon…");
    retry = Math.min(retry + 1, 6);
    setTimeout(connect, 500 * 2 ** retry); // backoff up to ~30 s
  };
}

// ---------------------------------------------------------------- demo (no server)
function runDemo() {
  const emotion = params.get("emotion") || "happy";
  const talk = params.get("talk") === "1";
  const cycle = ["happy", "laugh", "surprised", "confused", "annoyed", "celebrate", "thinking", "neutral"];
  let i = 0;
  const tick = () => {
    const e = emotion === "cycle" ? cycle[i++ % cycle.length] : emotion;
    if (e === "thinking") { state.phase = "thinking"; character.setEmotion("neutral"); }
    else {
      state.phase = "idle";
      if (talk) startSpeech({ id: "demo", text: params.get("text") || "", emotion: e, intensity: 0.9, duration: 2.6 });
      else character.setEmotion(e, 0.9, 999);
      if (["laugh", "surprised", "celebrate"].includes(e) && emotion === "cycle") character.react(e);
    }
  };
  tick();
  setInterval(tick, emotion === "cycle" ? 3200 : 4000);
}

window.addEventListener("resize", resize);
window.addEventListener("pointerdown", () => badge(""), { once: true });
setupScene();
createRenderer();
applyConfig({});
requestAnimationFrame(frame);
if (demo) runDemo(); else connect();
