# 07 — Avatars (`chattoon/web/overlay`)

All three characters are **procedural**: built in code with Three.js primitives, deformed
geometry and PBR materials. No external models, no licences to track, nothing downloaded at
runtime.

## Shared rig (`rig.js`)

- **Eyes**: glossy sclera, iris and pupil as spherical caps, fixed highlights, upper and lower
  lids (hemispheres) that blink (single/double, 2–6.5 s), squint and tilt; saccadic gaze.
- **Brows**: capsules with height, tilt and asymmetry.
- **Mouth**: disc with **morph targets** (open, smile, frown, round "O"), a lip rim with the
  same morphs, tongue and an upper-teeth strip that follow the opening.
- **Expressions**: neutral, happy, laugh, surprised, confused, annoyed, celebrate, thinking —
  target values damped every frame (smooth transitions, never snapping), scaled by intensity.
- **Reactions**: one-shot actions (jump, spin, shake, stretch) for laugh, surprise,
  celebration, annoyance and confusion.
- **Lip sync**: the envelope of the real audio drives the jaw (fast attack, slower release);
  with audio in OBS the page uses `audio.currentTime`, otherwise the event clock. Without audio
  (voice muted) a syllable rhythm is used.

## Characters

| | Construction | Specials |
|---|---|---|
| **Minhoca** | `SkinnedMesh` cylinder with segment rings and clitellum, 7-bone chain, head on the top bone, dirt mound | travelling S-wave, stretch on surprise, spin on celebration |
| **E.T.** | egg head (wider at the top), silver suit with glowing emblem, arms | levitation, spring-physics antennae that lag behind the head, glow that pulses with the voice, hover ring and beam |
| **Tux** | egg body with belly and face mask, two-part beak (lower mandible = jaw), flippers, feet | waddle, jumps and flapping on celebration, flipper to beak when thinking |

## Rendering and performance

ACES tone mapping, sRGB output, room environment (PMREM) for reflections, key/rim/hemisphere
lights, soft contact shadow (blurred texture instead of shadow maps). Quality presets change
geometry segments, antialiasing and pixel ratio; FPS limit 30/60; nothing is rendered while the
page is hidden (OBS inactive sources).

## Memory (measured)

400 speeches and 57 character switches in QtWebEngine: geometries constant, JS heap constant
(Chromium reports it in coarse steps). The same run **found a leak** — the worm's skeleton
bone texture was not freed on switch (+1 GPU texture per switch); fixed by disposing
`skeleton` in `Character.dispose()`. After the fix textures return to their baseline (worm 6,
E.T. 5, Tux 3).
