"""Render the character card thumbnails from the real 3D models.

Run after changing a character (needs Chrome or Chromium):
    python tools/render_thumbnails.py            # all characters
    python tools/render_thumbnails.py tux cat    # some of them

Writes chattoon/gui/qml/assets/characters/<id>.png (transparent background).
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from headless import browser  # noqa: E402

from chattoon.core.characters import CHARACTERS  # noqa: E402
from chattoon.core.overlay_server import OverlayServer  # noqa: E402

OUT = ROOT / "chattoon" / "gui" / "qml" / "assets" / "characters"
SIZE = (300, 340)  # matches sourceSize in CharactersPage.qml


async def render(ids: list[str]) -> None:
    from PySide6.QtCore import QRect, Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter

    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841 - QImage scaling needs it
    server = OverlayServer("thumbs", 0)
    await server.start()
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        async with browser() as page:
            for cid in ids:
                await page.open(f"{server.url}?demo={cid}&capture=1&transparent=1&bubble=0&zoom=1.05", 720, 820,
                                transparent=True)
                await page.eval("chattoonCapture.advance(1.2)")  # settle into the idle pose
                img = QImage.fromData(await page.screenshot())
                box = _content_box(img)
                crop = img.copy(box)
                canvas = QImage(*SIZE, QImage.Format_ARGB32_Premultiplied)
                canvas.fill(Qt.transparent)
                scaled = crop.scaled(SIZE[0] - 16, SIZE[1] - 12, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                p = QPainter(canvas)
                p.drawImage((SIZE[0] - scaled.width()) // 2, SIZE[1] - scaled.height() - 4, scaled)
                p.end()
                canvas.save(str(OUT / f"{cid}.png"), "PNG")
                print(f"{cid}: {box.width()}x{box.height()} -> {OUT / (cid + '.png')}")
            if page.errors:
                print("JavaScript errors:", *page.errors, sep="\n  ")
    finally:
        await server.stop()


def _content_box(img):
    from PySide6.QtCore import QRect

    w, h = img.width(), img.height()
    xs, ys = [], []
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            if img.pixelColor(x, y).alpha() > 8:
                xs.append(x)
                ys.append(y)
    if not xs:
        return QRect(0, 0, w, h)
    pad = 6
    x0, x1, y0, y1 = max(0, min(xs) - pad), min(w, max(xs) + pad), max(0, min(ys) - pad), min(h, max(ys) + pad)
    return QRect(x0, y0, x1 - x0, y1 - y0)


if __name__ == "__main__":
    wanted = sys.argv[1:] or list(CHARACTERS)
    asyncio.run(render([c for c in wanted if c in CHARACTERS]))
