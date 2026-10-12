"""Twitch connector against local fakes of IRC, EventSub, Helix and the OAuth server."""

import asyncio
import json
import time

import aiohttp
from aiohttp import web

from chattoon.core.config import PlatformApps, SourceConfig
from chattoon.core.credentials import CredentialStore
from chattoon.core.streams.base import ConnectorContext
from chattoon.core.streams.twitch import CREDENTIAL, TwitchAuth, TwitchConnector, irc_message, parse_irc

from .test_engine import wait_for


def test_irc_parsing_and_message_mapping():
    line = ("@badge-info=subscriber/8;badges=moderator/1,subscriber/6;bits=100;color=#FF0000;display-name=Ana\\sL;"
            "id=abc-1;mod=1;subscriber=1;tmi-sent-ts=1700000000000;user-id=42 "
            ":ana!ana@ana.tmi.twitch.tv PRIVMSG #canal :\x01ACTION acena pro Tux\x01")
    tags, prefix, command, params, trailing = parse_irc(line)
    msg = irc_message(tags, prefix, trailing)
    assert (command, params) == ("PRIVMSG", ["#canal"])
    assert (msg.id, msg.author, msg.author_id, msg.text) == ("abc-1", "Ana L", "42", "acena pro Tux")
    assert msg.is_moderator and msg.is_member and not msg.is_owner
    assert (msg.superchat, msg.paid_kind, msg.event_type) == ("100 bits", "bits", "paid")
    assert msg.timestamp == 1700000000.0


async def start_server(app):
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    return runner, f"127.0.0.1:{site._server.sockets[0].getsockname()[1]}"


def connector(target, extra, store=None, mode="auto", client="cid"):
    got, statuses, retracted = [], [], []
    ctx = ConnectorContext(credentials=store or CredentialStore(), apps=PlatformApps(twitch_client_id=client),
                           extra=extra)
    c = TwitchConnector(SourceConfig(id="tw", platform="twitch", target=target, options={"mode": mode}),
                        got.append, lambda s: statuses.append((s.state, s.code, s.detail)), ctx)
    c.on_retract = lambda sid, mid, aid: retracted.append((mid, aid))
    return c, got, statuses, retracted


# -- anonymous IRC --------------------------------------------------------------------


def irc_app(pongs, channel_exists=True):
    async def ws(request):
        sock = web.WebSocketResponse()
        await sock.prepare(request)
        async for msg in sock:
            for line in msg.data.split("\r\n"):
                if line.startswith("JOIN") and channel_exists:
                    await sock.send_str("@room-id=99 :tmi.twitch.tv ROOMSTATE #canal\r\n")
                    await sock.send_str(
                        "@badges=broadcaster/1;display-name=Dono;id=m1;user-id=1;tmi-sent-ts=1 "
                        ":dono!dono@x PRIVMSG #canal :Bem-vindos!\r\n"
                        "@badges=;display-name=Bia;id=m2;user-id=2 :bia!bia@x PRIVMSG #canal :Tux, qual distro?\r\n"
                        "PING :tmi.twitch.tv\r\n")
                    await sock.send_str("@target-msg-id=m2 :tmi.twitch.tv CLEARMSG #canal :Tux, qual distro?\r\n"
                                        "@target-user-id=7 :tmi.twitch.tv CLEARCHAT #canal :spammer\r\n"
                                        "@msg-id=raid;display-name=Raider;id=r1;user-id=9;system-msg=9\\sraiders "
                                        ":tmi.twitch.tv USERNOTICE #canal\r\n")
                elif line.startswith("PONG"):
                    pongs.append(line)
        return sock

    app = web.Application()
    app.router.add_get("/irc", ws)
    return app


def test_anonymous_irc_reads_messages_events_and_moderation():
    async def go():
        pongs = []
        runner, host = await start_server(irc_app(pongs))
        c, got, statuses, retracted = connector("canal", {"twitch_irc_url": f"ws://{host}/irc"}, mode="anonymous")
        task = asyncio.create_task(c.run())
        await wait_for(lambda: len(got) == 3 and len(retracted) == 2 and pongs)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await runner.cleanup()
        return got, statuses, retracted, pongs

    got, statuses, retracted, pongs = asyncio.run(go())
    assert [m.text for m in got[:2]] == ["Bem-vindos!", "Tux, qual distro?"]
    assert got[0].is_owner and got[0].platform == "twitch" and got[0].source_id == "tw" and got[0].channel == "canal"
    assert got[2].event_type == "raid" and got[2].superchat == "9 raiders"
    assert retracted == [("m2", ""), ("", "7")]
    assert pongs == ["PONG :tmi.twitch.tv"]
    assert ("connected", "", "") in statuses and statuses[-1][0] == "stopped"


def test_irc_probe_detects_missing_channel():
    async def go():
        runner, host = await start_server(irc_app([], channel_exists=False))
        c, *_ = connector("naoexiste", {"twitch_irc_url": f"ws://{host}/irc", "probe_wait": 0.5}, mode="anonymous")
        c_ok, *_ = connector("canal", {"twitch_irc_url": f"ws://{host}/irc"}, mode="anonymous")
        start = time.monotonic()
        missing = await c.probe()
        await c.close()
        await runner.cleanup()
        runner, host = await start_server(irc_app([]))
        c_ok.irc_url = f"ws://{host}/irc"
        ok = await c_ok.probe()
        await c_ok.close()
        await runner.cleanup()
        return missing, ok, time.monotonic() - start

    missing, ok, _ = asyncio.run(go())
    assert (missing.ok, missing.code) == (False, "not-found")
    assert (ok.ok, ok.code, ok.channel) == (True, "ready", "canal")


# -- official EventSub ---------------------------------------------------------------------


class FakeTwitch:
    """Twitch id/API/EventSub in one local server."""

    def __init__(self):
        self.subscriptions, self.closed_first, self.validations, self.refreshes = [], False, 0, 0
        self.valid = {"tok1"}
        self.revoked = []
        self.device_polls = 0
        app = web.Application()
        app.router.add_get("/oauth2/validate", self.validate)
        app.router.add_post("/oauth2/token", self.token)
        app.router.add_post("/oauth2/device", self.device)
        app.router.add_post("/oauth2/revoke", self.revoke)
        app.router.add_get("/helix/users", self.users)
        app.router.add_post("/helix/eventsub/subscriptions", self.subscribe)
        app.router.add_get("/ws", self.ws_first)
        app.router.add_get("/ws2", self.ws_second)
        self.app = app

    async def validate(self, request):
        self.validations += 1
        token = request.headers.get("Authorization", "").removeprefix("OAuth ")
        if token not in self.valid:
            return web.json_response({"status": 401, "message": "invalid access token"}, status=401)
        return web.json_response({"client_id": "cid", "login": "streamer", "user_id": "500", "expires_in": 9000})

    async def token(self, request):
        form = await request.post()
        if form.get("grant_type") == "refresh_token":
            if form.get("refresh_token") != "ref1":
                return web.json_response({"status": 400, "message": "Invalid refresh token"}, status=400)
            self.refreshes += 1
            self.valid.add("tok2")
            return web.json_response({"access_token": "tok2", "refresh_token": "ref2", "expires_in": 9000})
        self.device_polls += 1
        if self.device_polls < 2:
            return web.json_response({"status": 400, "message": "authorization_pending"}, status=400)
        assert form["device_code"] == "dev-1" and form["client_id"] == "cid"
        return web.json_response({"access_token": "tok1", "refresh_token": "ref1", "expires_in": 9000})

    async def device(self, request):
        form = await request.post()
        assert form["scopes"] == "user:read:chat"
        return web.json_response({"device_code": "dev-1", "user_code": "ABCD-EFGH", "interval": 0.05,
                                  "verification_uri": "https://www.twitch.tv/activate?device-code=ABCD-EFGH",
                                  "expires_in": 1800})

    async def revoke(self, request):
        self.revoked.append(dict(await request.post()))
        return web.Response()

    async def users(self, request):
        assert request.headers["Client-Id"] == "cid"
        if request.query["login"] == "canal":
            return web.json_response({"data": [{"id": "77", "login": "canal", "display_name": "Canal"}]})
        return web.json_response({"data": []})

    async def subscribe(self, request):
        body = await request.json()
        assert body["condition"] == {"broadcaster_user_id": "77", "user_id": "500"}
        assert body["transport"] == {"method": "websocket", "session_id": "s1"}
        self.subscriptions.append(body["type"])
        return web.json_response({"data": [{"id": f"sub{len(self.subscriptions)}"}]}, status=202)

    @staticmethod
    def frame(kind, payload, sub=""):
        meta = {"message_id": str(time.time()), "message_type": kind, "message_timestamp": "x"}
        if sub:
            meta["subscription_type"] = sub
        return json.dumps({"metadata": meta, "payload": payload})

    def chat(self, mid, text, name="Ana", bits=None, badges=()):
        return self.frame("notification", {"subscription": {"type": "channel.chat.message"}, "event": {
            "broadcaster_user_name": "Canal", "message_id": mid, "chatter_user_id": "9", "chatter_user_name": name,
            "chatter_user_login": name.lower(), "message": {"text": text, "fragments": []},
            "badges": [{"set_id": b, "id": "1", "info": ""} for b in badges],
            "cheer": {"bits": bits} if bits else None}}, "channel.chat.message")

    async def ws_first(self, request):
        sock = web.WebSocketResponse()
        await sock.prepare(request)
        await sock.send_str(self.frame("session_welcome", {"session": {"id": "s1", "keepalive_timeout_seconds": 10}}))
        for _ in range(200):
            if len(self.subscriptions) >= 4:
                break
            await asyncio.sleep(0.01)
        await sock.send_str(self.chat("e1", "Oi Tux!", badges=("subscriber", "moderator")))
        await sock.send_str(self.chat("e2", "toma bits", bits=250))
        await sock.send_str(self.frame("session_keepalive", {}))
        await sock.send_str(self.frame("notification", {"subscription": {"type": "channel.chat.message_delete"},
                                                        "event": {"message_id": "e1"}}))
        host = request.host
        await sock.send_str(self.frame("session_reconnect", {"session": {
            "id": "s1", "reconnect_url": f"ws://{host}/ws2"}}))
        async for _ in sock:
            pass
        self.closed_first = True
        return sock

    async def ws_second(self, request):
        sock = web.WebSocketResponse()
        await sock.prepare(request)
        await sock.send_str(self.frame("session_welcome", {"session": {"id": "s1", "keepalive_timeout_seconds": 10}}))
        await sock.send_str(self.chat("e3", "depois do reconnect", name="Bia"))
        await sock.send_str(self.frame("notification", {"subscription": {"type": "channel.chat.notification"}, "event": {
            "message_id": "n1", "chatter_user_id": "3", "chatter_user_name": "Novo", "notice_type": "sub",
            "message": {"text": ""}, "badges": [], "system_message": "Novo se inscreveu no Tier 1"}}))
        await sock.send_str(self.frame("revocation", {"subscription": {"status": "authorization_revoked"}}))
        async for _ in sock:
            pass
        return sock


def eventsub_extra(host):
    return {"twitch_id_base": f"http://{host}", "twitch_api_base": f"http://{host}",
            "twitch_eventsub_url": f"ws://{host}/ws"}


def account(token="tok1", refresh="ref1", validated=0.0):
    return {"access_token": token, "refresh_token": refresh, "expires_at": time.time() + 9000, "login": "streamer",
            "user_id": "500", "client_id": "cid", "validated_at": validated}


def test_eventsub_reads_chat_follows_reconnect_and_stops_on_revocation():
    async def go():
        fake = FakeTwitch()
        runner, host = await start_server(fake.app)
        store = CredentialStore()
        store.set(CREDENTIAL, account())
        c, got, statuses, retracted = connector("canal", eventsub_extra(host), store)
        await asyncio.wait_for(c.run(), 10)  # returns: revocation -> auth_required
        await runner.cleanup()
        return fake, got, statuses, retracted, c

    fake, got, statuses, retracted, c = asyncio.run(go())
    assert c.mode_used == "account"
    assert sorted(fake.subscriptions) == sorted(["channel.chat.message", "channel.chat.notification",
                                                 "channel.chat.message_delete", "channel.chat.clear_user_messages"])
    assert len(fake.subscriptions) == 4  # not re-subscribed after session_reconnect
    assert [m.text for m in got] == ["Oi Tux!", "toma bits", "depois do reconnect", ""]
    assert got[0].is_member and got[0].is_moderator and got[0].channel == "Canal"
    assert (got[1].superchat, got[1].event_type) == ("250 bits", "paid")
    assert (got[3].event_type, got[3].superchat) == ("subscription", "Novo se inscreveu no Tier 1")
    assert retracted == [("e1", "")]
    assert fake.closed_first and fake.validations >= 1  # validated at start, as Twitch requires
    assert statuses[-1][0] == "auth_required"
    assert not any("tok1" in detail for _, _, detail in statuses)


def test_expired_token_is_refreshed_and_the_new_refresh_token_kept():
    async def go():
        fake = FakeTwitch()
        fake.valid = set()  # tok1 expired
        runner, host = await start_server(fake.app)
        store = CredentialStore()
        store.set(CREDENTIAL, account())
        async with aiohttp.ClientSession() as http:
            got = await TwitchAuth(store, "cid", f"http://{host}").ensure(http)
        await runner.cleanup()
        return got, store.get(CREDENTIAL), fake

    got, stored, fake = asyncio.run(go())
    assert got["access_token"] == "tok2" and stored["refresh_token"] == "ref2" and fake.refreshes == 1


def test_device_code_login_and_logout():
    async def go():
        fake = FakeTwitch()
        runner, host = await start_server(fake.app)
        store = CredentialStore()
        auth = TwitchAuth(store, "cid", f"http://{host}")
        async with aiohttp.ClientSession() as http:
            device = await auth.start(http)
            saved = await auth.finish(http, device, timeout=5)
            await auth.revoke(http)
        await runner.cleanup()
        return device, saved, store, fake

    device, saved, store, fake = asyncio.run(go())
    assert device["user_code"] == "ABCD-EFGH" and saved["login"] == "streamer" and saved["user_id"] == "500"
    assert store.get(CREDENTIAL) is None and fake.revoked == [{"client_id": "cid", "token": "tok1"}]


def test_account_mode_without_login_or_client_id_explains():
    async def go():
        c, _, statuses, _ = connector("canal", {}, mode="account")
        await c.run()
        c2, _, statuses2, _ = connector("canal", {}, mode="account", client="")
        await c2.run()
        return statuses[-1], statuses2[-1]

    no_login, no_client = asyncio.run(go())
    assert no_login[0] == "auth_required" and no_client[:2] == ("unsupported", "no-client-id")


def test_auto_mode_falls_back_to_anonymous_without_account():
    async def go():
        pongs = []
        runner, host = await start_server(irc_app(pongs))
        c, got, *_ = connector("canal", {"twitch_irc_url": f"ws://{host}/irc"}, mode="auto")
        task = asyncio.create_task(c.run())
        await wait_for(lambda: got)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await runner.cleanup()
        return c.mode_used

    assert asyncio.run(go()) == "anonymous"
