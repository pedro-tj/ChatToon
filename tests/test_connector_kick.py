"""Kick connector: Pusher (unofficial) and official webhooks, against local fakes only."""

import asyncio
import base64
import json
import time
import uuid
from datetime import datetime, timezone

import aiohttp
import pytest
from aiohttp import web

from chattoon.core.config import PlatformApps, SourceConfig
from chattoon.core.credentials import CredentialStore
from chattoon.core.streams import kick
from chattoon.core.streams.base import ConnectorContext, FatalError, TransientError
from chattoon.core.streams.kick import KickConnector, clean_content, parse_time

pytest.importorskip("cryptography")
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import padding, rsa  # noqa: E402

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PEM = _KEY.public_key().public_bytes(serialization.Encoding.PEM,
                                      serialization.PublicFormat.SubjectPublicKeyInfo).decode()

_OLD_PEM = rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key().public_bytes(
    serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()

CHATROOM = 4242
BROADCASTERS = {"canal": 777, "outro": 888}


def chat_event(mid="m1", content="oi [emote:37226:KEKW] tudo bem?", badges=(), user_id=55, username="Ana"):
    return {"event": "App\\Events\\ChatMessageEvent", "channel": f"chatrooms.{CHATROOM}.v2", "data": json.dumps({
        "id": mid, "chatroom_id": CHATROOM, "content": content, "type": "message",
        "created_at": "2026-10-12T12:00:00+00:00", "metadata": {},
        "sender": {"id": user_id, "username": username, "slug": username.lower(),
                   "identity": {"color": "#fff", "badges": [{"type": b, "text": b, "count": 1} for b in badges]}}})}


class FakeKick:
    """kick.com channel endpoint + Pusher WebSocket + official API (token, channels, subscriptions)."""

    def __init__(self, channel="ok", script=(), pong=True, live=True):
        self.channel, self.script, self.pong, self.live = channel, list(script), pong, live
        self.subscribed = []
        self.pings = 0
        self.client_frames = []
        self.channel_hits = 0
        self.token_forms = []
        self.sub_bodies = []
        self.deleted = []
        self.key_hits = 0
        self.auth_headers = []

    async def channel_info(self, request):
        self.channel_hits += 1
        if self.channel == "blocked":
            return web.Response(status=403, text="<html>Just a moment...</html>", content_type="text/html")
        if self.channel == "missing":
            return web.json_response({"message": "Not found"}, status=404)
        slug = request.match_info["slug"]
        return web.json_response({"id": 9, "slug": slug, "chatroom": {"id": CHATROOM},
                                  "livestream": {"id": 1} if self.live else None, "user": {"username": "Canal"}})

    async def pusher(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await ws.send_json({"event": "pusher:connection_established",
                            "data": json.dumps({"socket_id": "1.2", "activity_timeout": 120})})
        async for msg in ws:
            frame = json.loads(msg.data)
            self.client_frames.append(frame)
            if frame["event"] == "pusher:subscribe":
                self.subscribed.append(frame["data"])
                await ws.send_json({"event": "pusher_internal:subscription_succeeded",
                                    "channel": frame["data"]["channel"], "data": "{}"})
                for item in self.script:
                    await ws.send_json(item)
            elif frame["event"] == "pusher:ping":
                self.pings += 1
                if self.pong:
                    await ws.send_json({"event": "pusher:pong", "data": "{}"})
        return ws

    async def token(self, request):
        form = await request.post()
        self.token_forms.append(dict(form))
        if form.get("client_secret") != "S3CR3T-VALUE":
            return web.json_response({"error": "invalid_client"}, status=401)
        return web.json_response({"access_token": "APP-TOKEN-XYZ", "expires_in": 3600, "token_type": "Bearer"})

    def _authorized(self, request):
        self.auth_headers.append(request.headers.get("Authorization"))
        return request.headers.get("Authorization") == "Bearer APP-TOKEN-XYZ"

    async def channels(self, request):
        if not self._authorized(request):
            return web.json_response({}, status=401)
        slug = request.query["slug"]
        if slug not in BROADCASTERS:
            return web.json_response({"data": []})
        return web.json_response({"data": [{"broadcaster_user_id": BROADCASTERS[slug], "slug": slug,
                                            "stream": {"is_live": self.live}}]})

    async def subscribe(self, request):
        if not self._authorized(request):
            return web.json_response({}, status=401)
        body = await request.json()
        self.sub_bodies.append(body)
        return web.json_response({"data": [{"name": e["name"], "version": 1, "subscription_id": f"sub-{e['name']}",
                                            "error": None} for e in body["events"]], "message": "OK"})

    async def unsubscribe(self, request):
        if not self._authorized(request):
            return web.json_response({}, status=401)
        self.deleted.extend(request.query.getall("id"))
        return web.Response(status=204)

    async def public_key(self, request):
        self.key_hits += 1
        return web.json_response({"data": {"public_key": _PEM}, "message": "OK"})


async def serve(fake):
    app = web.Application()
    app.router.add_get("/api/v2/channels/{slug}", fake.channel_info)
    app.router.add_get("/pusher", fake.pusher)
    app.router.add_post("/oauth/token", fake.token)
    app.router.add_get("/public/v1/channels", fake.channels)
    app.router.add_post("/public/v1/events/subscriptions", fake.subscribe)
    app.router.add_delete("/public/v1/events/subscriptions", fake.unsubscribe)
    app.router.add_get("/public/v1/public-key", fake.public_key)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    extra = {"kick_base": base, "kick_pusher_url": f"ws://127.0.0.1:{port}/pusher", "kick_id_base": base,
             "kick_api_base": base}
    return runner, extra


def make(extra, target="canal", options=None, app=False, port=0):
    store = CredentialStore()
    if app:
        store.set("kick/app", {"client_secret": "S3CR3T-VALUE"})
    ctx = ConnectorContext(credentials=store, apps=PlatformApps(kick_client_id="CID" if app else "",
                                                                kick_webhook_port=port), extra=extra)
    got, retracted, statuses = [], [], []
    conn = KickConnector(SourceConfig(platform="kick", target=target, options=dict(options or {})), got.append,
                         lambda s: statuses.append((s.state, s.code, s.detail)), ctx)
    conn.on_retract = lambda sid, mid, aid: retracted.append((mid, aid))
    return conn, got, retracted, statuses


async def until(predicate, timeout=1.5):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.01)


async def stop(task, conn):
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass
    await conn.close()


# -- pure helpers --------------------------------------------------------------------------

def test_bad_target_raises_value_error():
    for bad in ("", "https://example.com/canal", "a", "kick.com/categories", "nome com espaço"):
        with pytest.raises(ValueError):
            KickConnector(SourceConfig(platform="kick", target=bad), lambda m: None, lambda s: None)
    conn = KickConnector(SourceConfig(platform="kick", target="https://kick.com/Canal_X"), lambda m: None,
                         lambda s: None)
    assert conn.slug == "canal_x" and conn.support == "experimental" and conn.reconnect_when_ended


def test_clean_content_and_time():
    assert clean_content("oi [emote:37226:KEKW]  tudo[emote:1:x]bem [emoji:smile]") == "oi KEKW tudo x bem smile"
    assert parse_time("2026-10-12T12:00:00Z") == datetime(2026, 10, 12, 12, tzinfo=timezone.utc).timestamp()
    assert parse_time("2026-10-12T12:00:00.123456789Z") == pytest.approx(
        datetime(2026, 10, 12, 12, tzinfo=timezone.utc).timestamp() + 0.123456)
    assert parse_time("ontem") is None and parse_time("") is None


# -- chatroom id -----------------------------------------------------------------------------

def test_chatroom_resolution_manual_and_blocked():
    async def go():
        fake = FakeKick()
        runner, extra = await serve(fake)
        try:
            conn, *_ = make(extra)
            assert await conn._chatroom() == str(CHATROOM) and conn.display == "Canal"
            assert await conn._chatroom() == str(CHATROOM) and fake.channel_hits == 1  # cached
            await conn.close()

            fake.channel = "blocked"
            manual, *_ = make(extra, options={"chatroom_id": "999"})
            assert await manual._chatroom() == "999" and fake.channel_hits == 1  # no request at all
            await manual.close()

            blocked, *_ = make(extra)
            with pytest.raises(FatalError) as err:
                await blocked._chatroom()
            assert err.value.code == "blocked" and "Chatroom id" in str(err.value)
            await blocked.close()

            fake.channel = "missing"
            missing, *_ = make(extra)
            with pytest.raises(FatalError) as err:
                await missing._chatroom()
            assert err.value.code == "not-found"
            await missing.close()

            bad, *_ = make(extra, options={"chatroom_id": "12a"})
            with pytest.raises(FatalError) as err:
                await bad._chatroom()
            assert err.value.code == "invalid"
        finally:
            await runner.cleanup()

    asyncio.run(go())


def test_run_supervisor_stops_when_blocked():
    async def go():
        fake = FakeKick(channel="blocked")
        runner, extra = await serve(fake)
        try:
            conn, _, _, statuses = make(extra)
            await asyncio.wait_for(conn.run(), 2)
        finally:
            await runner.cleanup()
        return statuses

    state, code, detail = asyncio.run(go())[-1]
    assert (state, code) == ("error", "blocked") and "kick.com/api/v2/channels/canal" in detail


# -- Pusher ----------------------------------------------------------------------------------

def test_pusher_messages_badges_and_moderation():
    script = [
        chat_event("m1", badges=("moderator", "subscriber")),
        chat_event("m2", "[emote:1:PogU]", badges=("broadcaster", "verified"), user_id=1, username="Canal"),
        chat_event("m1"),  # duplicate
        {"event": "App\\Events\\MessageDeletedEvent", "data": json.dumps({"id": "x", "message": {"id": "m1"}})},
        {"event": "App\\Events\\UserBannedEvent", "data": json.dumps({"id": "y", "user": {"id": 55, "username": "Ana"}})},
        {"event": "App\\Events\\SubscriptionEvent", "data": json.dumps({"chatroom_id": CHATROOM, "username": "Bia",
                                                                        "months": 3})},
        {"event": "App\\Events\\GiftedSubscriptionsEvent", "data": json.dumps({
            "chatroom_id": CHATROOM, "gifted_usernames": ["a", "b"], "gifter_username": "Rico", "gifter_total": 2})},
        {"event": "App\\Events\\SomethingNew", "data": "{}"},
        {"event": "App\\Events\\StopStreamBroadcast", "data": "{}"},
    ]

    async def go():
        fake = FakeKick(script=script)
        runner, extra = await serve(fake)
        conn, got, retracted, statuses = make(extra, options={"mode": "pusher"})
        task = asyncio.create_task(conn.session())
        try:
            await until(lambda: len(got) >= 4 and len(retracted) >= 2)
        finally:
            await stop(task, conn)
            await runner.cleanup()
        return fake, conn, got, retracted, statuses

    fake, conn, got, retracted, statuses = asyncio.run(go())
    assert fake.subscribed == [{"auth": "", "channel": f"chatrooms.{CHATROOM}.v2"}]
    assert conn.mode_used == "pusher" and ("connected", "", "") in statuses and conn.status.channel == "Canal"
    first, second, sub, gift = got
    assert (first.id, first.author, first.author_id, first.text) == ("m1", "Ana", "55", "oi KEKW tudo bem?")
    assert first.is_moderator and first.is_member and not first.is_owner and not first.is_verified
    assert first.platform == "kick" and first.event_type == "message" and first.channel == "Canal"
    assert first.timestamp == datetime(2026, 10, 12, 12, tzinfo=timezone.utc).timestamp()
    assert second.text == "PogU" and second.is_owner and second.is_verified and not second.is_moderator
    assert (sub.author, sub.event_type, sub.superchat) == ("Bia", "subscription", "Sub (3 months)")
    assert (gift.author, gift.event_type, gift.superchat) == ("Rico", "subscription", "2 gifted subs")
    assert retracted == [("m1", ""), ("", "55")]


def test_pusher_ping_pong_and_missing_pong():
    async def go():
        fake = FakeKick(pong=True)
        runner, extra = await serve(fake)
        extra.update(kick_activity_timeout=0.1, kick_pong_timeout=0.2)
        conn, *_ = make(extra, options={"mode": "pusher"})
        task = asyncio.create_task(conn.session())
        try:
            await until(lambda: fake.pings >= 2)
            assert not task.done()  # pongs keep it alive
        finally:
            await stop(task, conn)

        fake.pong = False
        silent, *_ = make(extra, options={"mode": "pusher"})
        try:
            with pytest.raises(TransientError, match="keepalive"):
                await asyncio.wait_for(silent.session(), 2)
        finally:
            await silent.close()
            await runner.cleanup()

    asyncio.run(go())


def test_pusher_answers_server_ping_and_errors():
    async def go(error_code):
        fake = FakeKick(script=[{"event": "pusher:ping", "data": {}},
                                {"event": "pusher:error", "data": {"code": error_code, "message": "Over capacity"}}])
        runner, extra = await serve(fake)
        conn, *_ = make(extra, options={"mode": "pusher"})
        try:
            with pytest.raises((TransientError, FatalError)) as err:
                await asyncio.wait_for(conn.session(), 2)
        finally:
            await conn.close()
            await runner.cleanup()
        assert {"event": "pusher:pong", "data": {}} in fake.client_frames
        return err.value

    busy = asyncio.run(go(4100))
    assert isinstance(busy, TransientError) and busy.retry and "4100" in str(busy)
    refused = asyncio.run(go(4009))
    assert isinstance(refused, FatalError) and refused.code == "pusher-refused" and not refused.retry
    outdated = asyncio.run(go(4001))  # what the real server answers since kick.com retired its app key
    assert isinstance(outdated, FatalError) and outdated.code == "pusher-outdated" and not outdated.retry
    assert isinstance(asyncio.run(go(4201)), TransientError)


# -- webhooks --------------------------------------------------------------------------------

def sign(message_id, timestamp, body):
    return base64.b64encode(_KEY.sign(f"{message_id}.{timestamp}.".encode() + body, padding.PKCS1v15(),
                                      hashes.SHA256())).decode()


def now_rfc3339(offset=0.0):
    return datetime.fromtimestamp(time.time() + offset, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


async def deliver(http, port, kind, payload, message_id=None, timestamp=None, tamper=False, signature=None):
    message_id = message_id or uuid.uuid4().hex
    timestamp = timestamp or now_rfc3339()
    body = json.dumps(payload).encode()
    headers = {"Kick-Event-Message-Id": message_id, "Kick-Event-Subscription-Id": "sub-x",
               "Kick-Event-Signature": signature or sign(message_id, timestamp, body),
               "Kick-Event-Message-Timestamp": timestamp, "Kick-Event-Type": kind, "Kick-Event-Version": "1",
               "Content-Type": "application/json"}
    if tamper:
        body = body.replace(b"ola", b"OLA")
        assert b"OLA" in body
    async with http.post(f"http://127.0.0.1:{port}/kick/webhook", data=body, headers=headers) as resp:
        return resp.status


def chat_payload(mid, broadcaster=777, content="ola [emote:9:Kappa]", badges=()):
    return {"message_id": mid, "broadcaster": {"user_id": broadcaster, "username": "Canal", "channel_slug": "canal"},
            "sender": {"is_anonymous": False, "user_id": 55, "username": "Ana", "is_verified": True,
                       "channel_slug": "ana", "identity": {"username_color": "#f00", "badges": [
                           {"text": b, "type": b, "count": 1} for b in badges]}},
            "content": content, "emotes": [], "created_at": "2026-10-12T12:00:00Z"}


def test_webhook_end_to_end_signature_replay_and_cleanup():
    async def go():
        fake = FakeKick(live=False)
        runner, extra = await serve(fake)
        conn, got, retracted, statuses = make(extra, options={"mode": "auto"}, app=True)
        task = asyncio.create_task(conn.session())
        results = {}
        try:
            await until(lambda: conn.status.state == "connected")
            port = conn.webhook_port
            async with aiohttp.ClientSession() as http:
                results["valid"] = await deliver(http, port, "chat.message.sent",
                                                 chat_payload("c1", badges=("moderator", "og")), message_id="w1")
                receiver = kick._RECEIVERS[0]  # Kick rotated its key: the old one fails, refetched once
                receiver._key, receiver._key_at = kick.load_public_key(_OLD_PEM), receiver._key_at - 120
                results["rotated"] = await deliver(http, port, "chat.message.sent", chat_payload("c0"))
                results["dup"] = await deliver(http, port, "chat.message.sent", chat_payload("c1b"), message_id="w1")
                results["tampered"] = await deliver(http, port, "chat.message.sent", chat_payload("c2"), tamper=True)
                results["garbage"] = await deliver(http, port, "chat.message.sent", chat_payload("c3"),
                                                   signature="bm90IGEgc2lnbmF0dXJl")
                results["old"] = await deliver(http, port, "chat.message.sent", chat_payload("c4"),
                                               timestamp=now_rfc3339(-600))
                results["future"] = await deliver(http, port, "chat.message.sent", chat_payload("c5"),
                                                  timestamp=now_rfc3339(+300))
                results["kicks"] = await deliver(http, port, "kicks.gifted", {
                    "broadcaster": {"user_id": 777}, "sender": {"user_id": 66, "username": "Rico"},
                    "gift": {"amount": 100, "name": "Full Send", "type": "BASIC", "message": "valeu!"},
                    "created_at": "2026-10-12T12:00:00Z"}, message_id="w-kicks")
                results["sub"] = await deliver(http, port, "channel.subscription.new", {
                    "broadcaster": {"user_id": 777}, "subscriber": {"user_id": 67, "username": "Bia"},
                    "duration": 1}, message_id="w-sub")
                results["gifts"] = await deliver(http, port, "channel.subscription.gifts", {
                    "broadcaster": {"user_id": 777}, "gifter": {"is_anonymous": True, "user_id": None},
                    "giftees": [{"user_id": 1}, {"user_id": 2}, {"user_id": 3}]}, message_id="w-gifts")
                results["ban"] = await deliver(http, port, "moderation.banned", {
                    "broadcaster": {"user_id": 777}, "moderator": {"user_id": 1},
                    "banned_user": {"user_id": 55, "username": "Ana"}, "metadata": {"reason": "spam"}})
                results["other"] = await deliver(http, port, "chat.message.sent", chat_payload("c6", broadcaster=1))
                results["unknown"] = await deliver(http, port, "livestream.metadata.updated",
                                                   {"broadcaster": {"user_id": 777}})
                async with http.get(f"http://127.0.0.1:{port}/kick/webhook") as resp:
                    results["get"] = resp.status
                big = b"{" + b" " * (70 * 1024) + b"}"
                async with http.post(f"http://127.0.0.1:{port}/kick/webhook", data=big) as resp:
                    results["big"] = resp.status
        finally:
            await stop(task, conn)
        assert 0 not in kick._RECEIVERS  # the receiver is gone once the last source stops
        await runner.cleanup()
        return fake, conn, got, retracted, statuses, results

    fake, conn, got, retracted, statuses, results = asyncio.run(go())
    assert results == {"valid": 200, "rotated": 200, "dup": 200, "tampered": 401, "garbage": 401, "old": 400,
                       "future": 400, "kicks": 200, "sub": 200, "gifts": 200, "ban": 200, "other": 200,
                       "unknown": 200, "get": 405, "big": 413}
    assert conn.mode_used == "webhook"
    _, code, detail = [s for s in statuses if s[0] == "connected"][-1]
    assert code == "webhook" and f"127.0.0.1:{conn.webhook_port}/kick/webhook" in detail
    assert fake.token_forms == [{"grant_type": "client_credentials", "client_id": "CID",
                                 "client_secret": "S3CR3T-VALUE"}]
    assert fake.sub_bodies == [{"broadcaster_user_id": 777, "method": "webhook", "events": [
        {"name": n, "version": 1} for n in ("chat.message.sent", "channel.subscription.new",
                                            "channel.subscription.gifts", "kicks.gifted", "moderation.banned")]}]
    assert sorted(fake.deleted) == sorted(f"sub-{n}" for n in kick.WEBHOOK_EVENTS)  # close() cleaned up
    assert fake.key_hits == 2  # first use + rotation; forged requests afterwards are throttled
    chat, _rotated, kicks, sub, gifts = got  # c1b (duplicate id), c2..c5 (rejected), c6 (other channel) never arrive
    assert (chat.id, chat.author, chat.author_id, chat.text) == ("c1", "Ana", "55", "ola Kappa")
    assert chat.is_moderator and chat.is_member and chat.is_verified and not chat.is_owner
    assert (kicks.event_type, kicks.paid_kind, kicks.superchat, kicks.text, kicks.author) == (
        "gift", "kicks", "100 Kicks (Full Send)", "valeu!", "Rico")
    assert (sub.event_type, sub.superchat, sub.author, sub.id) == ("subscription", "Sub", "Bia", "w-sub")
    assert (gifts.author, gifts.author_id, gifts.superchat) == ("Anonymous", "", "3 gifted subs")
    assert retracted == [("", "55")]
    assert all("S3CR3T" not in d and "APP-TOKEN" not in d for _, _, d in statuses)


def test_webhook_receiver_shared_between_sources():
    async def go():
        fake = FakeKick()
        runner, extra = await serve(fake)
        one, got_one, *_ = make(extra, "canal", {"mode": "webhook"}, app=True)
        two, got_two, *_ = make(extra, "outro", {"mode": "webhook"}, app=True)
        tasks = [asyncio.create_task(one.session()), asyncio.create_task(two.session())]
        try:
            await until(lambda: one.status.state == two.status.state == "connected")
            assert one.webhook_port == two.webhook_port
            async with aiohttp.ClientSession() as http:
                assert await deliver(http, one.webhook_port, "chat.message.sent", chat_payload("a", 777)) == 200
                assert await deliver(http, one.webhook_port, "chat.message.sent", chat_payload("b", 888)) == 200
            await stop(tasks[0], one)
            async with aiohttp.ClientSession() as http:  # still served for the other source
                assert await deliver(http, two.webhook_port, "chat.message.sent", chat_payload("c", 888)) == 200
        finally:
            await stop(tasks[1], two)
            await runner.cleanup()
        return got_one, got_two

    got_one, got_two = asyncio.run(go())
    assert [m.id for m in got_one] == ["a"] and [m.id for m in got_two] == ["b", "c"]


def test_webhook_mode_without_app_is_unsupported_and_auto_falls_back():
    async def go():
        conn, *_ = make({}, options={"mode": "webhook"})
        with pytest.raises(kick.Unsupported) as err:
            await conn.session()
        auto, *_ = make({})
        mode = await auto._mode()
        with_app, *_ = make({}, app=True)
        return err.value.code, mode, await with_app._mode()

    assert asyncio.run(go()) == ("no-app", "pusher", "webhook")


# -- probe -----------------------------------------------------------------------------------

def test_probe_results():
    async def go():
        fake = FakeKick(live=True)
        runner, extra = await serve(fake)
        out = {}
        try:
            for name, kw in {"pusher": {}, "webhook": {"app": True}}.items():
                conn, *_ = make(extra, options={"mode": name}, **kw)
                out[name] = (await conn.probe()).to_dict()
                await conn.close()
            fake.live = False
            conn, *_ = make(extra, options={"mode": "pusher"})
            out["offline"] = (await conn.probe()).to_dict()
            await conn.close()
            conn, *_ = make(extra, target="ninguem", options={"mode": "webhook"}, app=True)
            out["webhook-missing"] = (await conn.probe()).to_dict()
            await conn.close()
            fake.channel = "blocked"
            conn, *_ = make(extra, options={"mode": "pusher"})
            out["blocked"] = (await conn.probe()).to_dict()
            await conn.close()
            conn, *_ = make(extra, options={"mode": "pusher", "chatroom_id": "123"})
            out["manual"] = (await conn.probe()).to_dict()
            await conn.close()
            fake.channel = "missing"
            conn, *_ = make(extra, options={"mode": "pusher"})
            out["missing"] = (await conn.probe()).to_dict()
            await conn.close()
            store = CredentialStore()
            store.set("kick/app", {"client_secret": "wrong-secret-value"})
            conn = KickConnector(SourceConfig(platform="kick", target="canal", options={"mode": "webhook"}),
                                 lambda m: None, lambda s: None,
                                 ConnectorContext(credentials=store, apps=PlatformApps(kick_client_id="CID"),
                                                  extra=extra))
            out["bad-secret"] = (await conn.probe()).to_dict()
            await conn.close()
        finally:
            await runner.cleanup()
        conn, *_ = make({"kick_base": "http://127.0.0.1:9"}, options={"mode": "pusher"})
        out["network"] = (await conn.probe()).to_dict()
        await conn.close()
        return out

    out = asyncio.run(go())
    assert out["pusher"] == {"ok": True, "code": "live", "detail": "", "channel": "Canal"}
    assert out["webhook"] == {"ok": True, "code": "live", "detail": "", "channel": "canal"}
    assert out["offline"]["ok"] and out["offline"]["code"] == "offline"
    assert not out["webhook-missing"]["ok"] and out["webhook-missing"]["code"] == "not-found"
    assert not out["blocked"]["ok"] and out["blocked"]["code"] == "blocked"
    assert out["manual"]["ok"] and out["manual"]["code"] == "ready"
    assert out["missing"]["code"] == "not-found"
    assert out["bad-secret"]["code"] == "auth-required" and "wrong-secret" not in out["bad-secret"]["detail"]
    assert out["network"] == {"ok": False, "code": "network", "detail": "ClientConnectorError", "channel": ""}
