# 07 — Avatars (`chattoon/web/overlay`)

All six characters are **procedural**: built in code with Three.js geometry, deformed
surfaces, skinning and PBR materials. No external models, no images used as characters, no
licences to track, nothing downloaded at runtime. The reference pictures used for Tux, Gata,
Coruja and Cachorro only guided proportions, colours and finish.

## Building blocks

### `rig.js` — face, expressions and behaviour

- **Eyes**: `Eye` (glossy sclera, iris and pupil caps, fixed highlights, lids that blink,
  squint and tilt) and `BeadEye` (toy-like glossy bead, no visible lids at rest, lids only to
  blink/squint, "^ ^" arcs for laughs, highlights that hide under a lid).
- **Brows** (`Brow`), **mouth** (`Mouth`: disc with morph targets open/smile/frown/round, lip
  rim, tongue and teeth). Characters may bring their own mouth (beaks, muzzles) with the same
  `set({open, smile, frown, round, talk})` interface.
- **Expressions**: neutral, happy, laugh, surprised, confused, annoyed, celebrate, thinking —
  damped every frame, scaled by intensity; one-shot **reactions** for the same emotions
  (`gentle` versions with reduced motion).
- **Lip sync**: the loudness envelope of the real audio drives the jaw (fast attack, slower
  release); with audio in OBS the page uses `audio.currentTime`, otherwise the event clock.
  **Without real audio the mouth stays closed**; only the standalone demo page simulates a
  syllable rhythm, and the app labels it as an animation demo.
- **`Director`** — the behaviour layer described in
  [12-character-tts-upgrade.md §3.4](12-character-tts-upgrade.md): a state machine (idle,
  listening, reading, thinking, speaking, reacting, celebrating, paused, emergency) with
  blended weights, head/eye coordination, posture shifts, breathing, speech beats,
  micro-expressions and weighted random gestures with cooldowns, configurable intensity,
  frequency and reduced motion. Everything is time-based (no frame-rate dependency).
- `Spring` (sub-stepped) for secondary motion: hats, ears, tails, antennae, wings.
- `hear(text)`: the character can react to the words of the message being answered.

### `characters/shapes.js` — procedural helpers

`latheBody` (elliptical lathe with a smooth back seam), `frontUV` + `markingTexture` +
`markedMaterial` (patches painted from signed-distance shapes onto the body itself — belly,
face masks, coat patches — anti-aliased, no decals, cached per key), `skinByHeight` +
`boneChain` (spine skinning), `topHat`.

## Characters

| | Construction | Gestures (idle / talking) |
|---|---|---|
| **Minhoca** | `SkinnedMesh` ringed body with clitellum, 7-bone chain, head on the top bone, dirt mound | stretch, wiggle, peek (retracts into the dirt), headBob, dig / sassy |
| **E.T.** | egg head, silver suit with glowing emblem, arms, spring antennae, hover ring and beam | scan, beep, wave, orbit, probe / point |
| **Tux** | one skinned lathe body with the head built in (hips/chest/head bones), seamless heart-shaped white face flowing into the belly, bead eyes, two-part beak, two-joint flippers, webbed feet, **top hat** with a coloured band on a spring | tipHat (greets the audience lifting the hat), adjustHat, flap, waddle, bow, stretch, bellyPat / explain, hatTouch |
| **Gata** | see the table in §Results of 12-character-tts-upgrade.md | tailWag, earTwitch, slowBlink, headTilt, curiousLook, silentMeow, pawRaise, faceWash |
| **Coruja** | ″ | headTurn, wingOpen, wingFlap, sway, ruffle, hoot, surprisePuff, techExcited |
| **Cachorro** | ″ | tailWag, earFlop, headTilt, pant, tongueOut, hop, pawRaise, joy, curiousSniff |

Every character also uses the generic gestures (glance, look around, weight shift, curious
tilt), all reactions and the state poses (listening leans in, reading sweeps the eyes along
the bubble, thinking looks up and touches the chin/beak, paused relaxes, emergency stays
still). The speech bubble follows a `bubbleAnchor` on each head (above the hat, ears or
tufts).

## Rendering and performance

ACES tone mapping, sRGB output, room environment (PMREM) for reflections, key/rim/hemisphere
lights, soft contact shadow (blurred texture instead of shadow maps). Quality presets change
geometry segments, texture sizes, antialiasing and pixel ratio; FPS limit 30/60; nothing is
rendered while the page is hidden (OBS inactive sources).

Switching character during a live compiles the new character's shaders in the background
(`renderer.compileAsync`) while the current one keeps animating, then swaps — no frozen frame.
Painted marking textures are cached, so switching back does not repaint them.

Budgets checked by `tests/test_overlay_render.py` (software WebGL): ≤ 90 draw calls and
≤ 120 k triangles at high quality, ≤ 60 k at low; GPU geometries/textures return to the same
counts after repeated switches through all six characters.

Card thumbnails in the app are rendered from these models by `tools/render_thumbnails.py`
(headless Chrome/Chromium); re-run it after changing a character.
