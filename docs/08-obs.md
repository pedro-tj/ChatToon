# 08 — OBS Studio

## Adding the avatar

1. In ChatToon open **OBS Studio** and click **Copy**. The address looks like
   `http://127.0.0.1:8765/o/<secret>/` (port changes automatically if 8765 is busy).
2. In OBS: **Sources → + → Browser**, paste the URL, width **1920**, height **1080**.
3. Leave *Shutdown source when not visible* **off**.
4. Audio:
   - **This computer** (default): the app plays the voice; capture it with Desktop Audio or an
     application audio capture of ChatToon.
   - **Inside OBS**: enable *Control audio via OBS* on the source; the voice is part of the
     source (stream + monitoring). If no OBS source is connected the app plays it instead.
5. Position and resize the source; the background is transparent (or choose *Green (chroma
   key)* and add a Chroma Key filter).

The app must be running for the overlay to work. The OBS card on the Dashboard counts the
connected sources.

## Overlay settings

Size, horizontal/vertical position, rotation, camera zoom, lighting, speech bubble, viewer
name, soft shadow, background, quality (low/medium/high) and FPS limit (30/60). Changes are
pushed instantly to every open overlay; late joiners receive the current configuration.

## Protocol (server → overlay only)

`config`, `state` (state + phase), `speak` (id, text, author, emotion, intensity, duration,
envelope, fps, audio URL only for the audio sink), `done`, `stop`, `react`. The overlay may
send only `ended` (audio finished; accepted from the audio sink) — anything else is ignored.

## Not done

Automatic source creation through obs-websocket was not implemented in this version.
