# Development

## Run from the source tree

```bash
sudo pacman -S --needed pyside6 python-aiohttp qt6-declarative qt6-svg qt6-webengine python-pytest
python -m chattoon            # the app
python -m chattoon doctor     # Ollama, TTS BigLinux, audio, platforms
python -m chattoon ask "Quanto é 2+2?" --character tux
```

Code style: `ruff check chattoon tests` must be clean. Interface strings are English and go
through `qsTr()` (QML) or `self.tr()` (Python controllers); the core reports codes, not
sentences. Comments explain decisions and non-obvious behaviour, not what the next line does.

## Tests

```bash
python -m pytest -q              # ~550 tests, about 5 minutes
python -m pytest -q --run-live   # also the real Ollama, TTS BigLinux and Kokoro voices
CHATTOON_LIVE_URL=https://www.youtube.com/watch?v=… python -m pytest -q --run-live tests/test_youtube_chat.py
```

The suite never touches the real `~/.config` (isolated `XDG_*` dirs) or the keyring
(`CHATTOON_CREDENTIALS=memory`), and runs the GUI offscreen with software rendering.
`tests/test_overlay_render.py` and `test_overlay_emotions.py` open the real overlay in a
headless Chrome/Chromium when one is installed (skipped otherwise).

| Area | Files |
|---|---|
| Engine, selection, settings, reading | `test_engine.py`, `test_messages_config.py`, `test_reading.py`, `test_engine_intelligence.py` |
| Answers, intents, memory | `test_intelligence.py`, `test_intent.py`, `test_memory.py`, `test_ollama_brain.py`, `test_assistant.py` |
| Ollama management | `test_ollama_management.py` (fake API with namespaced, imported, vision, cloud, embedding and broken models; service states) |
| Voice | `test_tts_overlay.py`, `test_kokoro.py` (a fake `koko` run as a real subprocess), `test_tts_manager.py` |
| Overlay and network | `test_tts_overlay.py`, `test_overlay_network.py` (LAN listener on 127.0.0.2), `test_remote_privacy.py` (real local HTTPS with a throw-away CA) |
| Platforms | `test_streams_core.py`, `test_connector_*.py`, `test_youtube_chat.py`, `test_gui_multistream.py` |
| Interface | `test_gui.py`, `test_character_window.py` (every page loads without QML warnings, both modes) |
| System | `test_system_network.py` (commands are faked: nothing is installed) |
| Translations | `test_i18n.py` (complete catalogue, every `qsTr` in it, placeholders kept, `.qm` fresh, language choice) |
| Packaging | `test_packaging.py` (real wheel contents, PKGBUILD, desktop file, AppStream, Three.js checksums, no secrets) |

## Translations

```bash
python tools/update_translations.py
```

It runs `lupdate` over `chattoon/gui` (QML and every `gui/*.py`, listed one by one because
`lupdate` skips `.py` files when scanning a folder), fills the catalogue from
`tools/translations_pt_BR.py` and compiles `chattoon_pt_BR.qm`. It fails listing any string
without a translation. In Portuguese the character is always "personagem".

## Measuring

* Answer quality: `tools/eval_intelligence.py` (see [INTELLIGENCE.md](INTELLIGENCE.md)). Never
  tune on `holdout2`; report runs of shipped code only.
* Local layers: `tools/bench_intelligence.py`.
* Start-up, memory and CPU: run the app with an isolated `XDG_CONFIG_HOME`, connect to the main
  window's first `frameSwapped`, and sum `psutil` RSS/USS/CPU of the process and its
  QtWebEngine children after 15 s idle (numbers in [ARCHITECTURE.md](ARCHITECTURE.md)).
* `tools/headless.py` opens the overlay in a headless Chrome/Chromium in capture mode
  (`?capture=1`, deterministic animation steps), for the browser tests and
  `tools/render_thumbnails.py`, which renders the character portraits in
  `gui/qml/assets/characters/`.

## Packaging (Arch, Manjaro, BigLinux)

```bash
cd packaging/arch
makepkg -f                 # builds chattoon-<version>-1-any.pkg.tar from this checkout
namcap PKGBUILD chattoon-*-any.pkg.tar
sudo pacman -U chattoon-*-any.pkg.tar
```

The build compiles the translation with `lrelease`, builds the wheel with `python -m build`
(nothing is downloaded), installs it with `python -m installer`, and adds the desktop entry,
the icon, the AppStream metainfo, the README and the Three.js licence. Expected `namcap` notes:
"File referenced in $startdir" (the package is built from its own checkout), optional
dependencies detected as optional, and `qt6-svg`/`iproute2` "may not be needed" (used through
`QtSvg` and the `ip` command, which namcap cannot see).

A package can be checked without touching the system:

```bash
mkdir -p /tmp/root/db
fakeroot pacman -U --root /tmp/root --dbpath /tmp/root/db --nodeps --noscriptlet --disable-sandbox chattoon-*.pkg.tar
PYTHONPATH=/tmp/root/usr/lib/python3.14/site-packages python /tmp/root/usr/bin/chattoon --version
fakeroot pacman -R --root /tmp/root --dbpath /tmp/root/db --nodeps --noscriptlet --disable-sandbox chattoon
```

## Releasing

1. Bump the version in `pyproject.toml`, `chattoon/__init__.py`, `packaging/arch/PKGBUILD`
   (`pkgrel=1`), `data/chattoon.metainfo.xml` and the README title (`test_packaging` checks the
   first three and the metainfo).
2. Update `CHANGELOG.md`.
3. `python tools/update_translations.py`, `ruff check chattoon tests`, `python -m pytest -q`
   (and `--run-live` on a machine with Ollama and TTS BigLinux).
4. Build and check the package as above; open the installed app once.
