"""The real overlay page in a headless browser (software WebGL): characters, transparency,
speech bubble, idle motion and GPU resource release.

Runs when Chrome/Chromium is installed (CHATTOON_BROWSER picks one); skipped otherwise.
"""

import asyncio
import hashlib
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from headless import browser, find_browser  # noqa: E402

from chattoon.core.characters import CHARACTERS  # noqa: E402
from chattoon.core.overlay_server import OverlayServer  # noqa: E402

pytestmark = pytest.mark.skipif(find_browser() is None, reason="needs Chrome or Chromium")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
IDS = [c for c in os.environ.get("CHATTOON_TEST_CHARACTERS", ",".join(CHARACTERS)).split(",") if c in CHARACTERS]


def run_page(check, timeout=240):
    """Start the real overlay server and a browser, run ``check(page, url)``."""
    async def go():
        server = OverlayServer("render", 0)
        await server.start()
        try:
            async with browser() as page:
                return await check(page, server.url, server)
        finally:
            await server.stop()
    return asyncio.run(asyncio.wait_for(go(), timeout))


def image(png):
    from PySide6.QtGui import QGuiApplication, QImage

    QGuiApplication.instance() or QGuiApplication([])
    return QImage.fromData(png)


def test_every_character_loads_animates_and_stays_within_budget():
    async def check(page, url, _):
        out = {}
        for cid in IDS:
            for quality in ("high", "low"):
                await page.open(f"{url}?demo={cid}&capture=1&quality={quality}")
                await page.eval("chattoonCapture.advance(0.5)")
                gestures = await page.eval("chattoonCapture.character().gestureNames()")
                for g in gestures:  # every gesture runs without errors
                    await page.eval(f"chattoonCapture.character().gesture('{g}'); chattoonCapture.advance(0.4)")
                for r in ("laugh", "surprised", "celebrate", "annoyed", "confused", "happy"):
                    await page.eval(f"chattoonCapture.character().react('{r}'); chattoonCapture.advance(0.3)")
                out[cid, quality] = await page.eval("chattoonCapture.advance(2)")
        return out, page.errors

    out, errors = run_page(check)
    assert errors == []
    for (cid, quality), diag in out.items():
        assert diag["character"] == cid
        limit_calls, limit_tris = (90, 120_000) if quality == "high" else (90, 60_000)
        assert diag["calls"] <= limit_calls, (cid, quality, diag)
        assert diag["triangles"] <= limit_tris, (cid, quality, diag)


def test_obs_overlay_stays_transparent_while_moving_and_supports_chroma_key():
    async def check(page, url, server):
        results = {}
        await page.open(f"{url}?capture=1", 640, 720, transparent=True)
        for cid in IDS:
            await server.broadcast({"type": "config", "character": cid, "background": "transparent", "showBubble": True,
                                    "quality": "medium", "fps": 60, "scale": 1, "x": 0, "y": -0.15, "zoom": 1}, keep=True)
            await page.eval(f"chattoonCapture.advance(0.2); chattoonCapture.character() && 1")
            shots = []
            for action in ("", "react('celebrate')", "react('surprised')", "gesture(chattoonCapture.character().gestureNames()[4])"):
                if action:
                    await page.eval(f"chattoonCapture.character().{action}")
                await page.eval("chattoonCapture.advance(0.45)")
                shots.append(await page.screenshot())
            results[cid] = shots
        await server.broadcast({"type": "config", "character": "tux", "background": "green", "quality": "medium"}, keep=True)
        await page.eval("chattoonCapture.advance(0.3)")
        green = await page.screenshot()
        return results, green, page.errors

    results, green, errors = run_page(check)
    assert errors == []
    for cid, shots in results.items():
        for png in shots:
            img = image(png)
            w, h = img.width(), img.height()
            corners = [img.pixelColor(x, y).alpha() for x, y in ((3, 3), (w - 4, 3), (3, h - 4), (w - 4, h - 4))]
            assert corners == [0, 0, 0, 0], cid  # never a white/checkered/opaque background
            opaque = sum(img.pixelColor(x, y).alpha() > 200 for y in range(0, h, 8) for x in range(0, w, 8))
            assert 0.02 < opaque / ((w // 8) * (h // 8)) < 0.6, cid  # the character is there, and only it
            top = [img.pixelColor(x, 0).alpha() for x in range(0, w, 4)]
            assert max(top) == 0, cid  # nothing (hat, ears, wings) is cut at the top edge
    g = image(green).pixelColor(3, 3)
    assert (g.red(), g.green(), g.blue()) == (0, 255, 0)


def test_reading_bubble_then_reply_never_covers_the_face():
    async def check(page, url, _):
        out = {}
        for cid in IDS:
            await page.open(f"{url}?demo={cid}&capture=1", 1280, 720)
            await page.eval("chattoonCapture.advance(0.3)")
            await page.eval("chattoonCapture.speak({id: 'r1', kind: 'reading', author: 'Carlos', text: 'Boa noite! "
                            "Qual distribuição Linux vocês recomendam?', duration: 2, envelope: [0.2, 0.8, 0.5, 0.9], fps: 50})")
            await page.eval("chattoonCapture.advance(1.0)")
            reading = await page.eval("chattoonCapture.bubble()")
            head = await page.eval("chattoonCapture.headScreen()")
            await page.eval("chattoonCapture.done(); chattoonCapture.state('thinking'); chattoonCapture.advance(0.6)")
            waiting = await page.eval("chattoonCapture.bubble()")
            await page.eval("chattoonCapture.speak({id: 'r2', kind: 'reply', author: 'Carlos', text: 'Carlos, essa é fácil!', "
                            "duration: 1.5, envelope: [0.3, 0.9, 0.4], fps: 50, emotion: 'happy', intensity: 0.6})")
            await page.eval("chattoonCapture.advance(0.8)")
            reply = await page.eval("chattoonCapture.bubble()")
            out[cid] = (reading, head, waiting, reply)
        return out, page.errors

    out, errors = run_page(check)
    assert errors == []
    for cid, (reading, head, waiting, reply) in out.items():
        assert reading and reading["viewer"] and reading["author"] == "Carlos" and "Linux" in reading["text"], cid
        assert waiting and waiting["viewer"] and waiting["waiting"], cid  # stays while the reply is prepared
        assert reply and not reply["viewer"] and reply["text"].startswith("Carlos, essa"), cid  # swapped, not stacked
        beside = reading["left"] >= head["x"] + 20 or reading["right"] <= head["x"] - 20
        assert reading["bottom"] <= head["y"] + 4 or beside, (cid, reading, head)  # above the head, or beside it


def test_switching_characters_releases_gpu_resources():
    async def check(page, url, _):
        await page.open(f"{url}?demo=worm&capture=1&quality=medium")
        rounds = []
        for _ in range(4):
            counts = {}
            for cid in IDS:
                await page.eval(f"chattoonCapture.config({{character: '{cid}'}})")
                d = await page.eval("chattoonCapture.advance(0.1)")
                counts[cid] = (d["geometries"], d["textures"])
            rounds.append(counts)
        return rounds, page.errors

    rounds, errors = run_page(check)
    assert errors == []
    assert rounds[1] == rounds[2] == rounds[3]  # no growth after the first round (shared assets are created once)


def test_idle_character_keeps_moving_and_reduced_motion_skips_big_gestures():
    async def check(page, url, _):
        out = {}
        for cid in IDS:
            await page.open(f"{url}?demo={cid}&capture=1&quality=low", 400, 480)
            frames = []
            for _ in range(3):
                await page.eval("chattoonCapture.advance(1.3)")
                frames.append(hashlib.sha1(await page.screenshot()).hexdigest())
            big = await page.eval("Object.entries(chattoonCapture.character().director.gestures)"
                                  ".filter(([, d]) => d.big).map(([n]) => n)")
            await page.eval("chattoonCapture.config({reduceMotion: true})")
            allowed = await page.eval(f"{big!r}.map(n => chattoonCapture.character().director.play(n, false))")
            out[cid] = (len(set(frames)), allowed)
        return out, page.errors

    out, errors = run_page(check)
    assert errors == []
    for cid, (distinct, allowed) in out.items():
        assert distinct == 3, cid  # breathing, gaze and gestures: never a frozen avatar
        assert not any(allowed), cid


def test_mouth_moves_only_with_real_audio():
    async def check(page, url, _):
        await page.open(f"{url}?demo=tux&capture=1")
        await page.eval("chattoonCapture.speak({id: 'a', kind: 'reply', text: 'sem áudio', duration: 2, envelope: [], fps: 50})")
        await page.eval("chattoonCapture.advance(0.8)")
        silent = await page.eval("chattoonCapture.character().cur.speak")
        await page.eval("chattoonCapture.speak({id: 'b', kind: 'reply', text: 'com áudio', duration: 2, "
                        "envelope: Array(100).fill(0.9), fps: 50})")
        await page.eval("chattoonCapture.advance(0.5)")
        voiced = await page.eval("chattoonCapture.character().cur.speak")
        return silent, voiced

    silent, voiced = run_page(check)
    assert silent == 0 and voiced > 0.6
