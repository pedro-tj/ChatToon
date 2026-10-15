"""Emotions in the real overlay page: lead reactions, idle moods per species, reduce motion."""

import json

from .test_overlay_render import IDS, pytestmark, run_page  # noqa: F401 - pytestmark skips without a browser


def test_a_lead_reaction_comes_first_then_the_lines_emotion():
    async def check(page, url, _):
        await page.open(f"{url}?demo=tux&capture=1")
        await page.eval("chattoonCapture.advance(0.2)")
        speak = {"type": "speak", "kind": "reply", "id": "a", "text": "Aeee! Parabéns!", "emotion": "celebrate",
                 "intensity": 0.9, "lead": "surprised", "duration": 3, "envelope": [], "fps": 50}
        await page.eval(f"chattoonCapture.speak({json.dumps(speak)})")
        await page.eval("chattoonCapture.advance(0.3)")
        first = await page.eval("chattoonCapture.character().emotion")
        await page.eval("chattoonCapture.advance(1.0)")
        then = await page.eval("chattoonCapture.character().emotion")
        plain = dict(speak, id="b", lead="", emotion="happy")
        await page.eval(f"chattoonCapture.speak({json.dumps(plain)}); chattoonCapture.advance(0.2)")
        direct = await page.eval("chattoonCapture.character().emotion")
        return first, then, direct, page.errors

    first, then, direct, errors = run_page(check, timeout=120)
    assert (first, then, direct) == ("surprised", "celebrate", "happy") and errors == []


def test_every_species_persona_uses_its_own_gestures():
    async def check(page, url, _):
        out = {}
        for cid in IDS:
            await page.open(f"{url}?demo={cid}&capture=1")
            await page.eval("chattoonCapture.advance(0.1)")
            out[cid] = await page.eval("""(() => { const c = chattoonCapture.character();
                const names = c.gestureNames(); const p = c.persona;
                const used = [...Object.values(p.moodGestures), ...Object.values(p.speechGestures)];
                return { missing: used.filter(g => !names.includes(g)), moods: Object.keys(p.idleMoods) }; })()""")
        return out, page.errors

    out, errors = run_page(check, timeout=180)
    assert errors == []
    for cid, info in out.items():
        assert info["missing"] == [], cid
    assert out.get("cat", {}).get("moods") != out.get("dog", {}).get("moods")  # each species has its own temper


def test_idle_moods_follow_the_species_and_respect_reduce_motion():
    async def sample(page, url, cid, reduce, seconds):
        await page.open(f"{url}?demo={cid}&capture=1&idle=1&reduce={1 if reduce else 0}")
        seen = []
        for _ in range(int(seconds * 2)):
            await page.eval("chattoonCapture.advance(0.5)")
            emotion = await page.eval("chattoonCapture.character().emotion")
            if emotion != "neutral" and (not seen or seen[-1] != emotion):
                seen.append(emotion)
        moods = await page.eval("Object.keys(chattoonCapture.character().persona.idleMoods)")
        return seen, moods

    async def check(page, url, _):
        lively = await sample(page, url, "dog", False, 120)
        calm = await sample(page, url, "worm", True, 150)
        return lively, calm, page.errors

    (seen, moods), (calm_seen, _), errors = run_page(check, timeout=240)
    assert errors == []
    assert len(seen) >= 2 and set(seen) <= set(moods)  # it never looks frozen, and stays in character
    assert all(a != b for a, b in zip(seen, seen[1:]))  # no mood twice in a row
    assert set(calm_seen) <= {"happy", "thinking"}  # reduce motion: only soft faces
    assert len(calm_seen) <= len(seen)
