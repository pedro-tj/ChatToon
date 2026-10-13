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
     Without that option OBS plays the voice straight to the speakers of the OBS computer,
     outside the mix. Only real OBS Browser Sources (detected by `window.obsstudio`) receive the
     audio: the link opened in a normal browser tab only shows the avatar (add `?role=obs` to
     force it).
5. Position and resize the source; the background is transparent (or choose *Green (chroma
   key)* and add a Chroma Key filter).

The app must be running for the overlay to work. The OBS card on the Dashboard counts the
connected sources.

## OBS on another computer (HTTPS)

ChatToon never listens on the network: the overlay stays on `127.0.0.1`. To open it from
another computer (or from anywhere), run an HTTPS reverse proxy on the ChatToon computer and
tell ChatToon its public address. Step-by-step guide in Portuguese, from a free domain to the
router: [21 — Seu próprio domínio para o overlay](21-dominio-proprio.md).

1. Point a domain to your public IP and forward a TCP port on the router to this computer
   (e.g. **8443**; it is also one of the ports Cloudflare's proxy accepts).
2. Caddy example (`/etc/caddy/conf.d/chattoon.caddy`, then `sudo systemctl reload caddy`):

   ```
   example.org:8443 {
   	reverse_proxy 127.0.0.1:8765
   }
   ```

   Caddy gets the certificate and forwards WebSockets on its own; keep the original `Host`
   header (Caddy's default). The overlay port must match: if 8765 was busy ChatToon picked the
   next one, shown in the local address.
3. In ChatToon: **OBS Studio → Access from another computer**, type `https://example.org:8443`.
   The public overlay link appears below it, ready to copy.

Only `https://` addresses are accepted. Requests for that host (and loopback names) are
served; any other `Host` still gets **403 forbidden**. The page's CSP allows the WebSocket
only on that `wss://` origin. Anyone with the link sees the avatar and hears its voice:
treat it like a password.

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
