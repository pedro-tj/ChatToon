import asyncio
import json

import pytest
from aiohttp import web

from chattoon.core.youtube_chat import ChatError, LiveChatClient, extract_video_id, parse_actions, parse_page

VID = "AbCdEfGhIjK"


@pytest.mark.parametrize("url", [
    f"https://www.youtube.com/watch?v={VID}",
    f"https://www.youtube.com/watch?feature=share&v={VID}&t=10",
    f"https://www.youtube.com/live/{VID}?si=x",
    f"https://youtu.be/{VID}",
    f"https://www.youtube.com/live_chat?v={VID}",
    f"https://www.youtube.com/live_chat?is_popout=1&v={VID}",
    f"m.youtube.com/watch?v={VID}",
    f"https://studio.youtube.com/video/{VID}/livestreaming",
    VID,
])
def test_extract_video_id(url):
    assert extract_video_id(url) == VID


@pytest.mark.parametrize("bad", ["", "https://example.com/watch?v=AbCdEfGhIjK", "https://youtube.com/@canal",
                                 "https://youtu.be/curto", "javascript:alert(1)"])
def test_extract_video_id_rejects(bad):
    with pytest.raises(ValueError):
        extract_video_id(bad)


def text_item(mid, author, text, badges=(), usec="1791705780363732", channel="UCx"):
    return {"addChatItemAction": {"item": {"liveChatTextMessageRenderer": {
        "id": mid, "authorName": {"simpleText": "@" + author}, "authorExternalChannelId": channel,
        "timestampUsec": usec, "message": {"runs": [{"text": text},
                                                    {"emoji": {"emojiId": "😂", "shortcuts": [":joy:"]}},
                                                    {"emoji": {"emojiId": "UC/x", "isCustomEmoji": True}}]},
        "authorBadges": list(badges)}}}}


MOD = {"liveChatAuthorBadgeRenderer": {"icon": {"iconType": "MODERATOR"}, "tooltip": "Moderador"}}
MEMBER = {"liveChatAuthorBadgeRenderer": {"customThumbnail": {"thumbnails": []}, "tooltip": "Membro (2 meses)"}}


def test_parse_actions_fields():
    actions = [
        text_item("a1", "ana", "oi minhoca", [MOD]),
        text_item("a2", "bia", "sou membro", [MEMBER]),
        {"addChatItemAction": {"item": {"liveChatPaidMessageRenderer": {
            "id": "p1", "authorName": {"simpleText": "@rico"}, "timestampUsec": "1",
            "purchaseAmountText": {"simpleText": "R$ 20,00"}, "message": {"runs": [{"text": "valeu"}]}}}}},
        {"addChatItemAction": {"item": {"liveChatPlaceholderItemRenderer": {"id": "x"}}}},
        {"addChatItemAction": {"item": {"liveChatViewerEngagementMessageRenderer": {"id": "sys"}}}},
        {"markChatItemAsDeletedAction": {}},
    ]
    msgs = parse_actions(actions)
    assert [m.id for m in msgs] == ["a1", "a2", "p1"]
    assert msgs[0].author == "ana" and msgs[0].text == "oi minhoca😂" and msgs[0].is_moderator
    assert msgs[1].is_member and not msgs[1].is_moderator
    assert msgs[2].superchat == "R$ 20,00"
    assert abs(msgs[0].timestamp - 1791705780.363732) < 1e-6


def page(actions=(), cont="C1", disabled=False):
    contents = ({"messageRenderer": {"text": {"runs": [{"text": "O chat está desativado."}]}}} if disabled else
                {"liveChatRenderer": {"continuations": [{"invalidationContinuationData": {
                    "continuation": cont, "timeoutMs": 1000}}], "actions": list(actions)}})
    return ('<script>ytcfg.set({"INNERTUBE_API_KEY":"KEY","INNERTUBE_CONTEXT":{"client":{"clientName":"WEB",'
            '"clientVersion":"2"}},"INNERTUBE_CONTEXT_CLIENT_NAME":1})</script>'
            f'<script>window["ytInitialData"] = {json.dumps({"contents": contents})};</script>')


def test_parse_page_errors():
    with pytest.raises(ChatError, match="desativado"):
        parse_page(page(disabled=True))
    with pytest.raises(ChatError):
        parse_page("<html>nada</html>")
    cfg, backlog, cont, timeout = parse_page(page([text_item("b1", "x", "velha")]))
    assert cfg["key"] == "KEY" and cont == "C1" and timeout == 1000 and backlog[0].id == "b1"


class FakeYouTube:
    """Pop-out page + get_live_chat with scripted responses."""

    def __init__(self, polls, fail_first_page=0):
        self.polls = list(polls)
        self.fail_first_page = fail_first_page
        self.page_hits = 0
        self.bodies = []

    async def live_chat(self, request):
        self.page_hits += 1
        if self.page_hits <= self.fail_first_page:
            return web.Response(status=503)
        assert request.query["v"] == VID
        return web.Response(text=page([text_item("old", "x", "backlog")]), content_type="text/html")

    async def get_live_chat(self, request):
        self.bodies.append(await request.json())
        assert request.query["key"] == "KEY"
        if not self.polls:
            return web.json_response({"responseContext": {}})  # ended
        actions = self.polls.pop(0)
        return web.json_response({"continuationContents": {"liveChatContinuation": {
            "continuations": [{"timedContinuationData": {"continuation": "C2", "timeoutMs": 10}}],
            "actions": actions}}})


async def serve(fake):
    app = web.Application()
    app.router.add_get("/live_chat", fake.live_chat)
    app.router.add_post("/youtubei/v1/live_chat/get_live_chat", fake.get_live_chat)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    return runner, f"http://127.0.0.1:{port}"


def test_client_reads_dedups_skips_backlog_and_ends(monkeypatch):
    async def go():
        fake = FakeYouTube([[text_item("n1", "a", "primeira")],
                            [text_item("n1", "a", "primeira"), text_item("n2", "b", "segunda")]],
                           fail_first_page=1)
        runner, base = await serve(fake)
        monkeypatch.setattr("chattoon.core.youtube_chat.asyncio.sleep", fast_sleep)
        got, statuses = [], []
        client = LiveChatClient(f"https://youtu.be/{VID}", got.append, statuses.append, base_url=base)
        await asyncio.wait_for(client.run(), 5)
        await runner.cleanup()
        return fake, got, statuses, client

    fake, got, statuses, client = asyncio.run(go())
    assert [m.id for m in got] == ["n1", "n2"]  # backlog skipped, duplicate n1 dropped
    states = [s.state for s in statuses]
    assert states[0] == "connecting" and "reconnecting" in states and states[-1] == "ended"
    assert client.failures == 1
    assert fake.bodies[1]["continuation"] == "C2" and fake.bodies[0]["context"]["client"]["clientName"] == "WEB"


_real_sleep = asyncio.sleep


async def fast_sleep(_seconds):
    await _real_sleep(0)


def test_client_disabled_chat_raises():
    async def go():
        async def disabled(request):
            return web.Response(text=page(disabled=True), content_type="text/html")
        app = web.Application()
        app.router.add_get("/live_chat", disabled)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        base = f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}"
        statuses = []
        try:
            with pytest.raises(ChatError):
                await LiveChatClient(VID, lambda m: None, statuses.append, base_url=base).run()
        finally:
            await runner.cleanup()
        return statuses

    statuses = asyncio.run(go())
    assert statuses[-1].state == "error" and "desativado" in statuses[-1].detail


def test_client_cancel_is_clean(monkeypatch):
    async def go():
        fake = FakeYouTube([[]] * 1000)
        runner, base = await serve(fake)
        statuses = []
        task = asyncio.create_task(LiveChatClient(VID, lambda m: None, statuses.append, base_url=base).run())
        await _real_sleep(0.3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await runner.cleanup()
        return statuses

    assert asyncio.run(go())[-1].state == "stopped"


@pytest.mark.live
def test_real_live_chat_if_url_given():
    import os

    url = os.environ.get("CHATTOON_LIVE_URL")
    if not url:
        pytest.skip("set CHATTOON_LIVE_URL to a live stream with chat")

    async def go():
        got = []
        client = LiveChatClient(url, got.append, skip_backlog=False)
        task = asyncio.create_task(client.run())
        await asyncio.sleep(25)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return got

    got = asyncio.run(go())
    assert got and all(m.id and m.author for m in got)
    assert len({m.id for m in got}) == len(got)
