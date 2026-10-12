# 17 — Multistream interface

## Navigation

The "YouTube chat" page became **Streaming platforms**, and a new **Live chat** page sits
right after it. Characters keeps index 1, which shortcuts and tests rely on. Pages are
reached by name (`win.go("platforms")`) instead of hard-coded indices. The menu shows a
**!** badge on Streaming platforms while an enabled source needs attention (login
required, error).

## Streaming platforms (`pages/PlatformsPage.qml`)

1. **Your sources.** One card per source with:
   - the platform badge (brand colour plus a short name; no trademarked logos are bundled);
   - the name and target;
   - a state pill (icon, word and tone);
   - live counters (messages, per minute, answered);
   - an enable switch;
   - **Connect / Reconnect / Disconnect** (while live), **Test** (probe, result in a
     tooltip and a toast), **Edit**, and **Remove** (asks a second click within 3 s).

   When something needs the streamer, a line explains it in plain words and says where to
   fix it. With no sources, an empty state offers one-click buttons per platform.
2. **Attention between platforms.** The selection mode, sharing between platforms, paid
   priority, events without text, cooldown (noting that "ana" differs per platform), TTL,
   queue size, backlog, commands, reading, favourite viewers and blocked words. In
   *Custom priority* mode each card shows a 1–5× stepper.
3. **Accounts.**
   - It says where logins are stored (keyring, or a private file).
   - Twitch: Client ID, **Connect account**, then the Device Code panel (large code, copy,
     open twitch.tv/activate, cancel).
   - Kick: Client ID, secret, webhook port, with the local-only explanation.
   - TikTok: install command (copy button) and an optional Euler key, with the third-party
     disclosure.
   - Meta: token, with step-by-step guidance.
   - X: bearer token, with a cost warning.
   - Secret fields are password fields: "Saved — type to replace", plus delete.
4. **What each platform allows.** The honest support sheet: level chip plus one sentence
   per platform.

## Add / edit source (`SourceDialog.qml`)

1. **Pick a platform** from keyboard-focusable tiles (Space/Enter). Each shows its support
   level and a one-line note.
2. **Paste a link.** Pasting a link from another platform switches the tile by itself.
   - Recognition shows "Recognised: Twitch · canal_linux".
   - Problems are named precisely: short link, not supported, wrong platform, already in
     the list.
3. **Platform options.** Twitch: Automatic / Account / Guest. Kick: Automatic / Public chat
   / Official webhook, plus the chatroom number.
4. **Test connection** runs a probe that reads nothing and reports in words: "Live now",
   "Not live right now", "Login required"…
5. **Add / Save.** Enter submits and Esc closes.

## Live chat (`pages/LiveChatPage.qml`)

- **Header:** a "LIVE" pill, which stops pulsing when reduced motion is on, plus
  "Following / Follow new messages" and Clear.
- **Filters:** search (name, message, reply), platform chips with counts, "Hide skipped".
- **List:** a virtualized `ListView` over a Qt model.
  - Each row: platform stripe and badge, author with host/mod/member/paid/question chips,
    time, the message as **plain text** (`Text.PlainText`: viewer text is never
    interpreted), and the avatar's reply under it.
  - States: in the queue, answering now, suggestion ready, answered, skipped, not queued
    (with the reason), removed by a moderator. Each state has an icon and words.
  - Hovering or focusing a row shows **Answer now** / **Skip**; Enter answers the focused
    row.
- **Follow mode:** scrolling up pauses auto-follow; reaching the end resumes it.
- **Footer:** received, replies, in the queue, platforms connected, plus a manual-mode
  notice.

## Dashboard

- The "Live chat" card shows "2 of 5 connected". Its tooltip lists each source and its
  state.
- A **Platforms** strip of small cards shows the state pill, messages per minute and
  replies per source.
- Queue rows carry the platform badge.

## Voice, OBS and Settings

- **Voice › Message reading:** "Say which platform the message came from": Never /
  Multistream (default) / Always, with an example.
- **OBS:** "Show the platform of the message" toggles the bubble pill.
- **Settings › Diagnostics** lists the login storage, TikTok support and each source with
  its state and reason. The privacy list mentions logins.

## Accessibility

- States are never told by colour alone: every state pill and feed row has an icon and
  words.
- Tiles, filter chips and the list are keyboard reachable, with `Accessible.role` and
  names.
- Focus rings come from the existing components.
- The new text tokens are the existing theme colours, already checked for WCAG AA by
  `test_theme_text_contrast`.
- Badges choose dark or white ink by luminance; Kick's green gets dark ink.
- Reduced motion also stops the LIVE pulse.

## Internationalisation

Every new string is English inside `qsTr()` / `self.tr()`.
`tools/translations_pt_BR.py` adds the full Brazilian Portuguese set, including plural
forms, and `tools/update_translations.py` regenerates and compiles the catalogue.
`test_i18n` fails if any string is untranslated or missing.

Screenshots: `docs/screenshots/platforms-pt-dark.png`, `live-chat-pt-dark.png`,
`live-chat-en-light.png`, `add-platform-pt-dark.png`, `dashboard-multistream-pt-dark.png`.
