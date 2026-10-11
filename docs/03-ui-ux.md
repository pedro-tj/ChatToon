# 03 — Interface and experience

## Principles

1. **Live first.** The Dashboard answers "is everything working?" at a glance: avatar preview
   with its current phase, status cards for Ollama, voice, chat and OBS (each card opens its
   page), live counters and every live control. The Start/Pause button and the emergency
   button also stay in the sidebar on every page.
2. **Safe state is obvious.** The emergency stop paints a red banner across the window until
   Start is pressed again.
3. **No dead ends.** Every problem shows its fix in place: the command to start Ollama, the
   package to install, a download button for a missing model, why a chat message was skipped.
4. **Try before going live.** Demo mode, "Make it say", reactions and voice preview work
   without YouTube.
5. **Settings explain themselves.** Every option has a one-line effect description.

## Pages

Dashboard · Characters (animated gallery, colour, catchphrases) · Personality (presets, nine
dials, length, pause between replies, own instructions) · Artificial intelligence (Ollama
status/host, model, downloads, generation parameters, reply language) · YouTube chat (link,
selection mode, limits, filters, incoming messages) · Voice (TTS status, voice per character,
speed, pitch, volume, output) · Stream context · OBS Studio (URL, steps, appearance with live
preview) · History (export/clear) · Settings (theme, language, profiles, privacy, diagnostics).
A four-step first-run assistant checks services and picks a character.

## Visual system (`gui/qml/Theme.qml`)

- Dark, light or system theme (`Qt.styleHints.colorScheme`, follows Plasma).
- Violet → pink accent gradient, translucent cards, 150/220 ms transitions with
  `cubic-bezier(0.4, 0, 0.2, 1)`.
- Icons are SVG paths coloured in Python (`gui/icons.py`) so they stay legible in both themes.
- **Contrast is tested**: every text colour ≥ 4.5:1 (WCAG AA) on background, sidebar and cards,
  and the text on primary buttons ≥ 4.5:1 on both gradient ends (`tests/test_gui.py`).

## Accessibility and keyboard

Accessible names on fields and icon buttons, visible focus rings, keyboard-navigable sidebar,
shortcuts (`Ctrl+Space`, `Ctrl+.`, `Ctrl+M`, `Ctrl+Shift+X`/`Pause`, `Ctrl+1…9`), scalable layout
from 1020×660, HiDPI-aware icons (rendered at 2× of their logical size).

## Languages

Interface strings are English (`qsTr`); `chattoon/i18n/chattoon_pt_BR.ts` holds the complete
Brazilian Portuguese translation. Interface language (Settings), reply language (AI page) and
voice language (Voice page) are independent. Update with `python tools/update_translations.py`
— tests fail if a string is untranslated or the `.qm` is stale.
