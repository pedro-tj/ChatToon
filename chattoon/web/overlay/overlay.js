// ChatToon overlay: renders the avatar for OBS (Browser Source) and the app preview.
// The server only pushes events here; this page has no authority over the app.
import * as THREE from "../vendor/three/three.module.js";
import { RoomEnvironment } from "../vendor/three/RoomEnvironment.js";
import { Worm } from "./characters/worm.js";
import { Alien } from "./characters/alien.js";
import { Tux } from "./characters/tux.js";
import { Cat } from "./characters/cat.js";
import { Owl } from "./characters/owl.js";
import { Dog } from "./characters/dog.js";

const CHARACTERS = { worm: Worm, alien: Alien, tux: Tux, cat: Cat, owl: Owl, dog: Dog };
const params = new URLSearchParams(location.search);
// preview: the app's dashboard · desktop: the character window on the desktop · obs: OBS
const role = ["preview", "desktop"].includes(params.get("role")) ? params.get("role") : "obs";
// OBS (and other obs-browser hosts) inject window.obsstudio; a plain browser tab shows the same
// overlay but joins as "browser", so opening the link to check it never takes the voice from OBS
const socketRole = role === "obs" && !window.obsstudio && params.get("role") !== "obs" ? "browser" : role;
// the desktop window frames the character itself (frameDesktop), whatever OBS uses
const DESKTOP = { x: 0, y: 0, scale: 1, rotation: 0, zoom: 1, background: "transparent" };
// share of the window height the whole character uses; the space above is for the bubble
const DESKTOP_FILL = 0.6, DESKTOP_BOTTOM = 0.035, DESKTOP_WIDTH = 0.8;
const demo = params.get("demo"); // standalone mode: ?demo=worm&emotion=happy&talk=1
if ((role === "preview" || demo) && !params.has("transparent")) document.body.classList.add("preview");
if (params.get("theme") === "light") document.body.classList.add("light");
if (role === "desktop") document.body.classList.add("desktop");

const config = {
  character: demo || "worm", color: params.get("color") || "", showBubble: params.get("bubble") !== "0", showAuthor: true,
  scale: 1, x: 0, y: -0.15, rotation: Number(params.get("rot") || 0), light: 1, shadows: true, quality: params.get("quality") || "high",
  fps: Number(params.get("fps") || 60), bubbleSeconds: 2.5, background: "transparent", zoom: Number(params.get("zoom") || 1),
  idle: params.get("idle") !== "0", intensity: params.get("intensity") || "normal",
  frequency: params.get("frequency") || "normal", reduceMotion: params.get("reduce") === "1", language: "pt-BR",
  showPlatform: true,
};
// phase: what the avatar is doing (idle/listening/reading/thinking/speaking); app: running/paused/stopped/emergency
// next: the line's own emotion, applied when a short lead reaction ends (surprised → celebrate)
const state = { phase: "idle", app: "stopped", speech: null, connected: false, next: null };
const EMOTIONS = ["neutral", "happy", "laugh", "surprised", "confused", "annoyed", "celebrate", "thinking"];
const LEAD_SECONDS = 0.9;
const capture = params.has("capture");
let captureClock = performance.now() / 1000;
const clock = () => (capture ? captureClock : performance.now() / 1000);

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
  if (role === "desktop") frameDesktop();
}

// Desktop window: every species has its own size (the dog's head is huge, the worm is tall),
// so the camera is fitted to the character's real bounding box: whole body in the lower part
// of the window, feet just above the bottom edge, free space above the head for the bubble.
let desktopBox = null;

function measureCharacter() {
  if (!character) return;
  desktopBox = new THREE.Box3().setFromObject(character.root, true);
  if (desktopBox.isEmpty()) desktopBox = null;
}

function frameDesktop() {
  if (!camera || !desktopBox) return;
  const tan = Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
  const size = desktopBox.getSize(new THREE.Vector3());
  const height = size.y * 1.08; // jumps, ears and hats move a little above the rest pose
  const width = Math.max(size.x, size.z * 0.6) * 1.15; // arms and wings open sideways
  const byHeight = height / (DESKTOP_FILL * 2 * tan);
  const byWidth = width / (DESKTOP_WIDTH * 2 * tan * Math.max(0.2, camera.aspect));
  const distance = Math.max(byHeight, byWidth) + size.z / 2;
  const visible = 2 * (distance - size.z / 2) * tan;
  const centerY = desktopBox.min.y - DESKTOP_BOTTOM * visible + visible / 2;
  const centerX = (desktopBox.min.x + desktopBox.max.x) / 2;
  camera.position.set(centerX, centerY, distance);
  camera.lookAt(centerX, centerY, 0);
}

function applyConfig(next) {
  const qualityChanged = next.quality && next.quality !== config.quality;
  const characterChanged = next.character && (next.character !== config.character || next.color !== config.color);
  Object.assign(config, next);
  if (role === "desktop") Object.assign(config, DESKTOP, { showBubble: params.get("bubble") !== "0" });
  if (qualityChanged) createRenderer();
  if (characterChanged || !character || qualityChanged) loadCharacter();
  character?.configure(animationConfig());
  stage.position.set(config.x * 2.4, config.y * 1.6, 0);
  stage.scale.setScalar(config.scale);
  stage.rotation.y = THREE.MathUtils.degToRad(config.rotation);
  if (role === "desktop") {
    frameDesktop();
  } else {
    const z = 6.6 / Math.max(0.3, config.zoom);
    camera.position.set(0, 1.45, z);
    camera.lookAt(0, 1.3, 0);
  }
  hemi.intensity = 0.4 * config.light;
  keyLight.intensity = 1.7 * config.light;
  rimLight.intensity = 1.2 * config.light;
  shadow.visible = config.shadows;
  const bg = config.background;
  if (role === "obs" && !demo) document.body.style.background = bg === "green" ? "#00ff00" : (bg && bg !== "transparent" ? bg : "transparent");
}

let loadToken = 0;

function loadCharacter() {
  const token = ++loadToken;
  const id = config.character;
  const Cls = CHARACTERS[id] || Worm;
  const next = new Cls({ color: config.color || undefined, quality: config.quality });
  next.configure(animationConfig());
  const swap = () => {
    if (token !== loadToken) { next.dispose(); return; } // a newer switch won
    if (character) {
      stage.remove(character.root);
      character.dispose();
    }
    character = next;
    stage.add(character.root);
    if (role === "desktop") { measureCharacter(); frameDesktop(); }
    rimLight.color.set(config.color || RIM[id] || "#8fd8ff");
    document.documentElement.style.setProperty("--accent", config.color || ACCENT[id] || "#7c5cff");
  };
  if (!character || capture) { swap(); return; }
  // Switching during a live: compile the new character's shaders while the current one
  // keeps animating, then swap — no frozen frame on stream.
  let done = false;
  const finish = () => { if (!done) { done = true; swap(); } };
  renderer.compileAsync(next.root, camera, scene).then(finish, finish);
  setTimeout(finish, 4000); // never wait forever (e.g. a lost GPU context)
}

const RIM = { worm: "#ff9ccd", alien: "#9dff8a", tux: "#ffd36b", cat: "#ffc07a", owl: "#e27bff", dog: "#ffd2a1" };
const ACCENT = { worm: "#e0559a", alien: "#3fae52", tux: "#e8a400", cat: "#e8781c", owl: "#7650e0", dog: "#b06a2a" };

function animationConfig() {
  return { idle: config.idle !== false, intensity: config.intensity, frequency: config.frequency,
           reduceMotion: !!config.reduceMotion };
}

// ---------------------------------------------------------------- bubble
// Two looks: the viewer's message being read ("viewer") and the avatar's reply. A new
// line swaps the content with a short cross-fade instead of hiding the bubble.
const bubble = document.getElementById("bubble");
const bubbleText = bubble.querySelector(".text");
const bubbleAuthor = bubble.querySelector(".author");
const bubbleLabel = bubble.querySelector(".label");
const bubblePlatform = bubble.querySelector(".platform");
let bubbleHideAt = 0;
let swapTimer = 0;
const LABELS = {
  pt: { said: "no chat", asked: "pergunta", superchat: "Super Chat" },
  en: { said: "in chat", asked: "question", superchat: "Super Chat" },
};

function labels() { return LABELS[(config.language || "pt").toLowerCase().startsWith("pt") ? "pt" : "en"]; }

// Super Chats say so; Bits, Kicks and gifts show their own label ("100 bits", "Rosa ×5")
function paidLabel(extra) {
  const superchat = !extra.paidKind || extra.paidKind === "superchat" || extra.paidKind === "supersticker";
  return superchat ? `${labels().superchat} ${extra.superchat}` : extra.superchat;
}

// "Twitch • Ana": where the message came from, in the platform's colour (text, never only colour)
function fillPlatform(kind, extra) {
  const show = kind === "reading" && config.showPlatform !== false && extra.platformLabel;
  bubblePlatform.textContent = show ? String(extra.platformLabel).slice(0, 20) : "";
  const color = /^#[0-9a-f]{6}$/i.test(extra.platformColor || "") ? extra.platformColor : "#5b5670";
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(color.slice(i, i + 2), 16) / 255);
  bubblePlatform.style.setProperty("--platform", color);
  bubblePlatform.classList.toggle("light", 0.299 * r + 0.587 * g + 0.114 * b > 0.6);
  return !!show;
}

function fillBubble(text, author, kind, extra = {}) {
  bubble.classList.toggle("viewer", kind === "reading");
  bubble.classList.remove("waiting");
  const tagged = fillPlatform(kind, extra);
  bubbleAuthor.textContent = (kind === "reading" || config.showAuthor) && author ? author : "";
  bubbleLabel.textContent = kind === "reading"
    ? (extra.superchat ? paidLabel(extra) : extra.question ? labels().asked : tagged ? "" : labels().said) : "";
  bubbleText.textContent = "";
  const shown = document.createElement("span");
  const pending = document.createElement("span");
  pending.className = "pending";
  pending.textContent = text; // textContent: chat text is never parsed as HTML
  bubbleText.append(shown, pending);
  if (extra.reveal === false) revealBubble(1);
}

function showBubble(text, author, kind = "reply", extra = {}) {
  if (!config.showBubble) return;
  clearTimeout(swapTimer);
  bubbleHideAt = Infinity;
  if (bubble.classList.contains("show") && !capture) {
    bubble.classList.add("swap"); // fade the old line out, then the new one in
    swapTimer = setTimeout(() => { fillBubble(text, author, kind, extra); bubble.classList.remove("swap"); }, 150);
  } else {
    fillBubble(text, author, kind, extra);
    bubble.classList.add("show");
  }
}

function hideBubble() {
  bubble.classList.remove("show", "waiting");
  bubbleHideAt = Infinity;
}

function revealBubble(fraction) {
  const [shown, pending] = bubbleText.children;
  if (!shown || bubble.classList.contains("swap")) return;
  const full = shown.textContent + pending.textContent;
  const n = Math.min(full.length, Math.ceil(full.length * Math.min(1, fraction * 1.15)));
  shown.textContent = full.slice(0, n);
  pending.textContent = full.slice(n);
}

const _anchor = new THREE.Vector3();
const _side = new THREE.Vector3();
let bubbleAbove = true;

function placeBubble() {
  if (!character || !bubble.classList.contains("show")) return;
  const w = window.innerWidth, h = window.innerHeight;
  const toScreen = (v) => ({ x: (v.x * 0.5 + 0.5) * w, y: (-v.y * 0.5 + 0.5) * h });
  // the anchor rides on the head: the bubble follows hats, ears and jumps, never covering the face
  if (character.bubbleAnchor) character.bubbleAnchor.getWorldPosition(_anchor);
  else character.root.localToWorld(_anchor.set(0, character.headHeight, 0));
  _side.copy(_anchor);
  _side.x += 0.85 * stage.scale.x;
  _side.y -= 0.55 * stage.scale.y;
  _anchor.project(camera);
  _side.project(camera);
  const head = toScreen(_anchor), side = toScreen(_side);
  const bw = bubble.offsetWidth, bh = bubble.offsetHeight, gap = 18, margin = 12;
  // hysteresis: a head bobbing near the limit must not flip the bubble back and forth
  const roomAbove = head.y - gap - bh - margin;
  bubbleAbove = role === "desktop" || (bubbleAbove ? roomAbove >= -6 : roomAbove >= 18);
  bubble.classList.remove("side-left", "side-right");
  if (bubbleAbove) {
    // above the head (preferred)
    const cx = Math.min(w - bw / 2 - margin, Math.max(bw / 2 + margin, head.x));
    bubble.style.left = `${cx}px`;
    // the desktop window is narrow: a long line may cover the forehead, never leave the window
    bubble.style.top = `${role === "desktop" ? Math.max(bh + margin, head.y - gap) : head.y - gap}px`;
    bubble.style.setProperty("--tail", `${Math.min(bw - 24, Math.max(24, bw / 2 + (head.x - cx)))}px`);
    return;
  }
  // not enough room above: beside the head, never covering the character
  const halfWidth = Math.max(40, side.x - head.x);
  const rightRoom = w - (head.x + halfWidth + gap) - margin;
  const leftRoom = head.x - halfWidth - gap - margin;
  const wasRight = bubble.dataset.side !== "left";
  const placeRight = rightRoom >= bw ? (wasRight || leftRoom < bw) : rightRoom >= leftRoom;
  bubble.dataset.side = placeRight ? "right" : "left";
  const left = placeRight ? head.x + halfWidth + gap : head.x - halfWidth - gap - bw;
  const top = Math.min(h - bh - margin, Math.max(margin, side.y - bh / 2));
  bubble.classList.add(placeRight ? "side-right" : "side-left");
  bubble.style.left = `${Math.max(margin, left)}px`;
  bubble.style.top = `${top}px`;
  bubble.style.setProperty("--tail", `${Math.min(bh - 24, Math.max(24, side.y - top))}px`);
}

// ---------------------------------------------------------------- speech
let audioUnlockHint = false;

function startSpeech(msg) {
  const kind = msg.kind === "reading" ? "reading" : "reply";
  const group = msg.group || msg.id;
  // the next segment of the same line: same bubble, same emotion — only audio and timing change
  const continuing = msg.continue && state.speech?.group === group;
  if (!continuing) stopSpeech(false);
  else if (state.speech.audio) state.speech.audio.onended = state.speech.audio.onerror = null;
  const speech = { id: msg.id, group, kind, envelope: msg.envelope || [], fps: msg.fps || 50, duration: msg.duration || 2,
                   started: clock(), audio: null, simulate: !!msg.simulate, progress: msg.progress || [0, 1] };
  state.speech = speech;
  state.phase = kind === "reading" ? "reading" : "speaking";
  if (continuing) { playAudio(msg, speech); return; }
  if (kind === "reading" && msg.superchat) character?.react("celebrate"); // a Super Chat deserves a party
  if (kind === "reply") {
    const emotion = EMOTIONS.includes(msg.emotion) ? msg.emotion : "neutral";
    const lead = EMOTIONS.includes(msg.lead) && msg.lead !== emotion ? msg.lead : "";
    state.next = null;
    if (lead) {
      // a quick first reaction (surprise at good news), then the line's own emotion
      character?.react(lead);
      state.next = { emotion, intensity: msg.intensity ?? 0.7, at: clock() + LEAD_SECONDS, seconds: speech.duration + 2.5 };
    } else {
      applyEmotion(emotion, msg.intensity ?? 0.7, speech.duration + 2.5);
    }
    // the species' own gesture for this kind of line (asked for, or one that fits the emotion)
    if (typeof msg.gesture === "string" && msg.gesture) character?.director.play(msg.gesture, false);
    else if (emotion !== "neutral" && Math.random() < 0.45) character?.speechGesture(emotion);
  }
  showBubble(msg.text || "", msg.author || "", kind, { reveal: msg.reveal, question: msg.question, superchat: msg.superchat,
                                                       paidKind: msg.paidKind, platformLabel: msg.platformLabel,
                                                       platformColor: msg.platformColor });
  playAudio(msg, speech);
}

function applyEmotion(emotion, intensity, seconds) {
  character?.setEmotion(emotion, intensity, seconds);
  // strong emotions get a short body reaction at the start of the line
  if (["laugh", "surprised", "celebrate"].includes(emotion) && intensity >= 0.75) character?.react(emotion);
}

// the emotion that follows a lead reaction, once its moment came (frame loop and capture mode)
function settleEmotion(now) {
  const n = state.next;
  if (n && now >= n.at) {
    state.next = null;
    applyEmotion(n.emotion, n.intensity, Math.max(1, n.seconds - LEAD_SECONDS));
  }
}

function playAudio(msg, speech) {
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
  if (hard) { clearTimeout(swapTimer); bubbleHideAt = clock() + 0.2; return; }
  // after the viewer's message the bubble stays while the reply is being prepared
  if (s?.kind === "reading") { bubbleHideAt = Infinity; bubble.classList.add("waiting"); }
  else bubbleHideAt = clock() + config.bubbleSeconds;
}

// how much of the whole line has been said (segments carry their share of the text)
function lineProgress(s) {
  const [a, b] = s.progress;
  return a + (b - a) * Math.min(1, speechTime(s) / Math.max(0.3, s.duration));
}

function speechTime(s) {
  if (s.audio && !s.audio.paused && s.audio.currentTime > 0) return s.audio.currentTime;
  return clock() - s.started;
}

function mouthLevel() {
  const s = state.speech;
  if (!s) return 0;
  const t = speechTime(s);
  if (t > s.duration + 0.3) return 0;
  if (!s.envelope.length) {
    // No real audio: the mouth stays closed. Only the demo page simulates a syllable rhythm.
    if (!s.simulate) return 0;
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
  if (!capture && now - lastFrame < minDelta) return;
  lastFrame = now;
  timer.update(now);
  // capture mode (screenshots/tests): fixed steps, so animation time is deterministic
  const dt = capture ? 1 / 60 : Math.min(timer.getDelta(), 0.1);
  if (capture) captureClock += dt;
  const seconds = clock();
  settleEmotion(seconds);
  const s = state.speech;
  if (s) revealBubble(lineProgress(s));
  if (!s && seconds > bubbleHideAt) hideBubble();
  const phase = s ? (s.kind === "reading" ? "reading" : "speaking")
    : (state.phase === "speaking" || state.phase === "reading" ? "idle" : state.phase);
  character?.update(dt, seconds, { phase, app: state.app, mouth: mouthLevel() });
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

let lastHeard = "";

function onState(msg) {
  if (msg.state) state.app = msg.state;
  // a message was picked: let the character react to what it says (once per message)
  if (msg.message && msg.message !== lastHeard && (msg.phase === "listening" || msg.phase === "thinking")) {
    lastHeard = msg.message;
    character?.hear(msg.message);
  }
  if (state.speech) return;
  const before = state.phase;
  state.phase = msg.phase || "idle";
  // the viewer's message stays up while the avatar thinks; it goes if no reply comes
  if (state.phase === "idle" && before !== "idle" && bubble.classList.contains("viewer") && bubbleHideAt === Infinity)
    bubbleHideAt = clock() + 0.8;
}

function connect() {
  const url = new URL(`ws?role=${socketRole}`, location.href);
  url.protocol = location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(url);
  ws.onopen = () => { retry = 0; state.connected = true; badge(""); };
  ws.onmessage = (ev) => {
    let msg;
    try { msg = JSON.parse(ev.data); } catch { return; }
    if (!msg || typeof msg !== "object") return;
    switch (msg.type) {
      case "config": applyConfig(msg); break;
      case "state": onState(msg); break;
      case "speak": startSpeech(msg); break;
      case "done":
        if (state.speech && (state.speech.group === msg.id || state.speech.id === msg.id)) stopSpeech(false);
        if (msg.kind !== "reading") state.phase = "idle";
        break;
      case "stop": stopSpeech(true); state.next = null; state.phase = "idle"; character?.setEmotion("neutral"); break;
      case "react": character?.react(msg.emotion); break;
      case "gesture": if (typeof msg.name === "string") character?.gesture(msg.name); break;
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
// Standalone page for the character cards and the enlarged preview. Lip movement here is
// simulated (there is no audio) — the app labels these previews as animation demos.
function runDemo() {
  const emotion = params.get("emotion") || "idle";
  const talk = params.get("talk") === "1";
  const cycle = ["happy", "laugh", "surprised", "confused", "annoyed", "celebrate", "thinking", "neutral"];
  state.app = "running";
  let i = 0;
  const tick = () => {
    const e = emotion === "cycle" ? cycle[i++ % cycle.length] : emotion;
    if (e === "idle") return;
    if (e === "thinking") { state.phase = "thinking"; character.setEmotion("neutral"); setTimeout(() => { state.phase = "idle"; }, 2400); }
    else {
      state.phase = "idle";
      if (talk) startSpeech({ id: "demo", text: params.get("text") || "", emotion: e, intensity: 0.9, duration: 2.6, simulate: true });
      else character.setEmotion(e, 0.9, 999);
      if (["laugh", "surprised", "celebrate"].includes(e) && emotion === "cycle") character.react(e);
    }
  };
  tick();
  if (emotion !== "idle") setInterval(tick, emotion === "cycle" ? 3200 : 4000);
  const gesture = params.get("gesture");
  if (gesture) { const play = () => (character.gesture(gesture) || character.react(gesture)); setTimeout(play, 300); setInterval(play, 4500); }
  // used by the enlarged preview in the app (local page, no server, no authority)
  window.chattoonDemo = {
    emotion: (name) => { character.setEmotion(name, 0.9, 4); if (["laugh", "surprised", "celebrate", "annoyed", "confused", "happy"].includes(name)) character.react(name); },
    gesture: (name) => character.gesture(name),
    talk: (text, seconds = 3) => startSpeech({ id: `demo${Date.now()}`, text, emotion: "happy", intensity: 0.6, duration: seconds, simulate: true }),
    read: (author, text, seconds = 2.5) => startSpeech({ id: `demo${Date.now()}`, kind: "reading", author, text, duration: seconds, simulate: true }),
    phase: (name) => { state.phase = name; },
    configure: (cfg) => applyConfig(cfg),
    gestures: () => character.gestureNames(),
    hear: (text) => character.hear(text),
  };
}

// capture mode (screenshots and rendering tests): step the animation by exact amounts
if (capture) {
  document.body.classList.add("capture"); // no CSS transitions: what is measured is the final layout
  window.chattoonCapture = {
    advance(seconds) {
      for (let i = 0, n = Math.round(seconds * 60); i < n; i++) {
        captureClock += 1 / 60;
        settleEmotion(captureClock);
        const s = state.speech;
        if (s) revealBubble(lineProgress(s));
        if (!s && captureClock > bubbleHideAt) hideBubble();
        const phase = s ? (s.kind === "reading" ? "reading" : "speaking") : state.phase;
        character?.update(1 / 60, captureClock, { phase, app: state.app, mouth: mouthLevel() });
      }
      renderer.render(scene, camera);
      placeBubble();
      return window.chattoonDiagnostics();
    },
    state: (phase, app) => { state.phase = phase; if (app) state.app = app; },
    hear: (text) => character.hear(text),
    speak: (msg) => startSpeech(msg),
    done: () => stopSpeech(false),
    config: (cfg) => applyConfig(cfg),
    bubble: () => (bubble.classList.contains("show")
      ? { ...bubble.getBoundingClientRect().toJSON(), viewer: bubble.classList.contains("viewer"),
          waiting: bubble.classList.contains("waiting"), text: bubbleText.textContent, author: bubbleAuthor.textContent,
          platform: bubblePlatform.textContent, label: bubbleLabel.textContent }
      : null),
    headScreen: () => {
      const v = new THREE.Vector3();
      if (character.bubbleAnchor) character.bubbleAnchor.getWorldPosition(v);
      else character.root.localToWorld(v.set(0, character.headHeight, 0));
      v.project(camera);
      return { x: (v.x * 0.5 + 0.5) * window.innerWidth, y: (-v.y * 0.5 + 0.5) * window.innerHeight };
    },
    character: () => character,
  };
}

// read-only diagnostics (used by the soak test; exposes no control)
window.chattoonDiagnostics = () => ({
  geometries: renderer.info.memory.geometries, textures: renderer.info.memory.textures,
  heap: performance.memory ? performance.memory.usedJSHeapSize : null, character: config.character,
  state: character?.director.state, gesture: character?.director.gesture?.name || "", phase: state.phase,
  calls: renderer.info.render.calls, triangles: renderer.info.render.triangles,
});

window.addEventListener("resize", resize);
window.addEventListener("pointerdown", () => badge(""), { once: true });
setupScene();
createRenderer();
applyConfig({});
requestAnimationFrame(frame);
if (demo) runDemo(); else connect();
