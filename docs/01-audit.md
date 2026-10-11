# 01 — Audit of the original project

State on 2026-10-11, commit `e29b51a` (local tree identical, nothing uncommitted).

## What existed

| File | What it did | Verdict |
|---|---|---|
| `bot_chat.py` | `pytchat` + Google Gemini (placeholder key), `spd-say` | replaced |
| `bot_chat1.py` | `pytchat` + Ollama `llama3` (hard-coded), `spd-say` | replaced |
| `bot_chat2.py` | `pytchat` + Ollama `qwen2.5:1.5b`, safety rules in the prompt | replaced; its rules live on as *forbidden topics* |
| `index.html`, `index1.html`, `1index.html` | Three.js r128 from a CDN, sphere characters, polls `chat_recente.txt`, speaks with `SpeechSynthesis` | replaced by the overlay |
| `teste 3d.html` | placeholder cube | removed (kept in `legacy/`) |
| `index.js` | Node.js Rumble chat poller with an **embedded API key** | key removed; kept in `legacy/` |
| `chat_recente.txt`, `comandos.txt` | runtime file and notes | runtime file deleted from git |

Everything was moved to `legacy/` with `git mv` (history preserved). Worth keeping: the idea of
a file/bridge to the overlay (now a WebSocket), the "deflect forbidden topics with humour" rule
and the short, informal Brazilian style.

## Problems found and fixed

| # | Problem | Severity | Fix |
|---|---|---|---|
| 1 | Rumble livestream API key committed in `index.js` (public repo) | **critical** | removed from code; reads `RUMBLE_API_URL`. **The key is still in git history: revoke it in the Rumble dashboard.** |
| 2 | `os.system(f"spd-say '{text}' &")` with chat/AI text | **critical** (command injection: `'; rm -rf ~ #`) | legacy: `subprocess.Popen([...])`; new code never uses a shell (tested) |
| 3 | Voice spoken twice: `spd-say` in Python **and** `SpeechSynthesis` in the page | high | single TTS path; overlay never synthesizes; audio played by exactly one sink (tested) |
| 4 | Full URL passed as `video_id` to `pytchat` | high | `extract_video_id()` for every common URL form (tested) |
| 5 | Duplicate filter compared only the last message text | medium | de-duplication by YouTube message id + per-user repeat filter |
| 6 | When the AI failed, the raw chat text was spoken | high (anyone could make the avatar say anything) | failures produce an error event, never speech (tested) |
| 7 | Chat text inserted into the prompt as `'...'` | medium (prompt injection) | delimited data block, escaping, explicit rules (tested) |
| 8 | `pytchat` unmaintained since 2021, not even installed | high | own reader on the pop-out endpoints, validated on a real live |
| 9 | Hard-coded models/URLs, no configuration | medium | persistent settings, profiles |
| 10 | Three.js r128 from a CDN, 4 s fixed "talking" timer | medium | Three.js 0.186.1 vendored; lip sync from the audio envelope |
| 11 | Polling a text file every 1.5 s, no reconnection | medium | WebSocket with snapshot + reconnect/backoff |
| 12 | Loops without cancellation or clean shutdown | medium | asyncio tasks with cancel; emergency stop |

## Found on the machine (not changed)

- The system `ollama` service runs with `OLLAMA_HOST=0.0.0.0`, so the Ollama API is reachable
  from the local network. If that is not intended, remove it from the service environment
  (`systemctl edit ollama`). ChatToon talks to `127.0.0.1` either way.
