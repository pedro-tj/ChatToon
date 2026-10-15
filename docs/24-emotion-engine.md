# 24 — Emotions

The 3D rig already had eight expressions, body reactions per species, idle gestures and
lip sync from the real audio (docs 07 and 12). Nothing of that was rebuilt. What was
wrong was the data feeding it, and the avatar had no moods of its own when idle.

## Choosing the emotion (`chattoon/core/emotion.py`)

The model still picks an emotion with each reply (`neutral, happy, laugh, surprised,
confused, annoyed, celebrate, thinking` — unchanged identifiers). The controller:

1. **keeps it when it fits the message kind** from the classifier, else uses the
   kind's own emotion. Examples: sadness → never `laugh`/`annoyed`/`celebrate`;
   arithmetic and facts → `happy`/`neutral`/`thinking`; good news → `celebrate`/`happy`/
   `surprised`; a joke → `laugh`/`happy`; an order aimed at the avatar → `confused`/
   `annoyed`;
2. **avoids tics**: the same strong emotion three times in a row becomes `happy` or
   `neutral`, except for a joke after jokes or good news after good news;
3. **softens** objective answers (≤ 0.7) and replies to someone who is not well (≤ 0.5);
4. **adds a lead**: a quick first reaction played before the line's emotion. Today:
   `surprised` before good news ("consegui instalar o BigLinux!") and before problems
   told with emphasis ("travou pela décima vez").

No extra model call is involved. The few-shot examples now show varied emotions; before,
both examples said `laugh` and the memory turns said `neutral`.

Measured on the evaluation set: 2.2.2 gave `laugh` to 123 of 134 replies. The new
pipeline's distribution follows the messages (mostly `happy` for questions and
greetings, `laugh` for jokes, `celebrate` for good news, `confused` for unclear
messages). Criteria cases (greeting, good news, joke, sadness, unclear) pass 100 %
in most runs.

## In the overlay (`web/overlay/overlay.js`, `rig.js`)

* `speak` events may carry `lead`. The overlay plays `react(lead)`, then after 0.9 s
  applies the line's emotion (with its body reaction when strong). The switch happens in
  the frame loop and in capture mode, so tests and OBS behave the same. `stop` cancels
  a pending switch.
* `speak` events may carry `gesture` (spontaneous lines use the generic `lookAround`,
  `curious`, `glance`). Otherwise, 45 % of the time a line starts with **the species'
  own gesture for that emotion**.
* **Idle moods**: while really idle (not paused, not after an emergency stop, idle
  animation on), every 16–36 s (scaled by the gesture-frequency setting) the character
  drifts into a light mood for 1.6–3.2 s with a matching gesture. Moods are weighted per
  species and never repeat twice in a row.
* **Reduce motion**: idle moods are limited to `happy`/`thinking`, softer (0.3), 1.6×
  rarer and without gestures. Big gestures were already refused.

### Personality per species

| Character | Idle moods (weight) | Mood → gesture | Speech emotion → gesture |
|---|---|---|---|
| Tux | happy 3, thinking 2, laugh 1, surprised 0.6 | tipHat, adjustHat, bellyPat, lookAround | hatTouch, flap, explain |
| Minhoca | laugh 3, happy 2, surprised 1, thinking 1, annoyed 0.6 | wiggle, headBob, peek, lookAround, stretch | sassy, wiggle |
| E.T. | surprised 3, confused 2, thinking 2, happy 1 | scan, probe, beep, wave | point, beep, wave |
| Gata | happy 2, annoyed 2, thinking 1, surprised 0.8, laugh 0.4 | slowBlink, faceWash, curiousLook, earTwitch, smugLook | smugLook, explainPaw, tailWag, earFlick |
| Coruja | thinking 3, happy 2, surprised 1 | headTurn, hoot, surprisePuff | teach, nod, wingSweep, wingFlap |
| Cachorro | happy 4, celebrate 1, surprised 1, thinking 1 | tailWag, joy, headTilt, curiousSniff | wagBurst, nodAlong, pawTap |

The Minhoca giggles to herself; the Gata is rarely impressed and washes her face; the
Coruja is mostly pensive; the Cachorro is happy almost all the time.

## Verified

* `tests/test_overlay_emotions.py` (real page, headless Chromium, software WebGL):
  `surprised` then `celebrate` after 0.9 s; every persona gesture exists for all six
  species; over two simulated minutes the Cachorro shows ≥ 2 moods, all from its own
  table, never the same twice in a row; with reduce motion the Minhoca shows only
  `happy`/`thinking`.
* Screenshots of Tux, Cachorro and Gata during the lead and after the switch were
  inspected by eye: wide eyes and open mouth, then closed happy eyes, Tux's wings open.
* Rendering budget unchanged: `test_every_character_loads_animates_and_stays_within_budget`
  still passes (draw calls and triangles per character).
* Not verified: inside OBS Studio itself (the overlay is the same page OBS loads; OBS was
  not run during this work).
