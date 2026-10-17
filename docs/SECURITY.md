# Security and privacy

ChatToon reads text written by strangers on the internet and shows itself on live streams.
Both shape every rule below. To report a vulnerability, open a private security advisory at
<https://github.com/ruscher/ChatToon/security/advisories> (or an issue without details).

## Viewer messages are data, never commands

| Rule | How | Tests |
|---|---|---|
| Nothing from the chat is executed | no shell anywhere (`os.system`/`shell=True` are banned by a test); voice text goes through stdin | `test_no_secrets_or_shell_in_code`, `test_text_goes_through_stdin_not_shell` |
| Viewers cannot change the rules | delimited, neutralised data block; rules forbid following embedded instructions; replies validated; leaks of the rules are never spoken | `test_messages_wrap_untrusted_text`, `test_a_prompt_leak_is_never_spoken`, eval injection 10/10 |
| Model output is never executed | text plus an emotion from a fixed list | `test_parse_cleans_reply` |
| No raw chat spoken on failures | an AI failure is an error event, never an echo | `test_ai_failure_never_speaks_raw_chat` |
| No HTML injection | overlay uses `textContent`; QML shows `Text.PlainText` and escapes `<` before StyledText; platform colours must match `^#[0-9a-f]{6}$` | overlay render tests |
| Limits | 300 characters per message, 4 KB WebSocket frames, 64 KB requests, timeouts on every network call | — |
| Pasted links are only parsed | `streams/urls.py` never fetches; connectors talk to fixed hosts only (no SSRF) | `test_streams_core` |

Content safety: forbidden topics (default: partisan politics, religion, sexual content) are
in the prompt and checked again on the reply; blocked words drop messages before the AI sees
them; teasing is bounded (no humiliation, prejudice, harsh profanity or personal attacks).

## Local services

* The overlay listens on `127.0.0.1` behind a random path token (`/o/<token>/`), checks the
  `Host` header (anti DNS rebinding), sends CSP `default-src 'self'`, `no-store`, `nosniff`,
  `no-referrer`, and ignores every WebSocket message except `ended` from the audio sink. Static
  files are served without symlinks or directory listings.
* **Local network mode** (off by default, asks for consent): one extra listener on one private
  IPv4 of this computer — never `0.0.0.0` — that only answers callers of the same subnet with
  that exact `Host`. The firewall is changed only after consent, through `pkexec`, with a rule
  limited to that subnet.
* **Internet**: only through an HTTPS reverse proxy (or a tunnel) the person sets up; ChatToon
  accepts that one host name. Never forward the overlay port or Ollama's 11434.
* **New secret address** rotates the token and restarts the server: every old link stops
  working.
* The Kick webhook receiver binds `127.0.0.1` and checks size, timestamp window and the RSA
  signature before parsing.
* An `ollama serve` started by ChatToon always listens on `127.0.0.1` only; a remote Ollama is
  used through its API and never controlled.

## Commands and privileges

ChatToon runs as the user. Changes to the system happen only after a confirmation dialog that
lists what will be done, and the administrator password is asked by polkit:

* packages: `pkexec env LC_ALL=C pacman -S --noconfirm --needed -- <names>` — never `-Sy`
  (a partial upgrade), names validated by a strict pattern and limited to an allow-list (Ollama:
  `ollama` and its acceleration add-ons; voice engines: the packages TTS BigLinux names, AUR only
  through its own helper, as the user);
* services: `systemctl [--user] start|stop|restart|enable|disable ollama.service` (systemd asks
  polkit itself);
* firewall: the exact `ufw`/`firewall-cmd` rule shown to the person.

Every subprocess uses a fixed argv list. The KWin script for the character window is generated
with JSON-quoted values and loaded with the user's rights; the D-Bus method it calls back only
accepts well-formed numbers.

## Secrets and privacy

* Logins use official flows or tokens the streamer pastes (never passwords) and live in the
  Secret Service (KWallet, GNOME Keyring); without a keyring, in a 0600 file the interface marks
  as unencrypted. Settings and exported profiles never contain them (`SECRET_KEY` filter on
  source options, `export_profile()` filters again; tests check both).
* `REDACTOR` masks every stored secret, the overlay token, the public IP (once looked up) and
  token-like patterns in every log line. Log lines never include the overlay address.
* **On screen** (the app is often shown on stream): the token inside any overlay address and
  the public IP are always masked; the **Live privacy mode** (on by default) also masks local
  addresses, domains, IPs in errors and the Twitch login. Revealing one value is deliberate,
  warns that viewers will see it, and lasts 15 seconds. Copy buttons copy the real value and
  say it contains a secret code. Every toast goes through `core.privacy.scrub()`.
* The public IP is looked up only after consent (`api.ipify.org`, the dialog says so), kept in
  memory only, never saved or logged.
* Files: settings, backups, credentials, memories and logs 0600; the voice workspace 0700 and
  removed on exit.
* No telemetry. External connections: the configured platforms (and Euler Stream for TikTok),
  the configured Ollama, and — only when the person acts — the package repositories,
  `registry.ollama.ai` (model sizes and downloads), Hugging Face (Kokoro voices, through TTS
  BigLinux), `api.ipify.org` and the person's own domain.

## Third-party code

* Three.js 0.186.1 (MIT) is vendored in `chattoon/web/vendor/three` with `SHA256SUMS`, checked
  by `test_vendored_three_is_intact_and_licensed`; its licence is installed with the package.
* TikTokLive is never bundled; it is installed only on request into a private venv.
* An early prototype exposed a Rumble API key (still in the Git history: it must be revoked in
  the Rumble dashboard). A test scans every tracked file for it and for key-shaped strings.
