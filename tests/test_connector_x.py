"""X connector against a local fake of the X API v2 (no network)."""

import asyncio
import json
import logging
import time

import pytest
from aiohttp import web

from chattoon.core.config import SourceConfig
from chattoon.core.credentials import CredentialStore
from chattoon.core.streams.base import ConnectorContext, RateLimited
from chattoon.core.streams.x import XConnector

BEARER = "AAAAbearerSECRETtoken0009"
ROOT = "1840000000000000000"


def post(pid, author, text, created="2026-10-12T15:00:00.000Z"):
    return {"id": pid, "author_id": author, "text": text, "created_at": created, "conversation_id": ROOT,
            "edit_history_tweet_ids": [pid]}


USERS = [{"id": "1", "username": "canal_linux", "name": "Canal Linux", "verified": True},
         {"id": "2", "username": "bia", "name": "Bia", "verified": False},
         {"id": "3", "username": "caio", "name": "", "verified": True}]


class FakeX:
    def __init__(self):
        self.requests = []  # (path, query)
        self.posts = []
        self.fail = None  # (status, body, headers)
        self.remaining = 449
        self.reset = int(time.time()) + 900

    async def search(self, request):
        query = dict(request.query)
        self.requests.append((request.path, query))
        assert request.headers.get("Authorization") == f"Bearer {BEARER}"
        headers = {"x-rate-limit-limit": "450", "x-rate-limit-remaining": str(self.remaining),
                   "x-rate-limit-reset": str(self.reset)}
        if self.fail:
            status, body, extra = self.fail
            return web.json_response(body, status=status, headers={**headers, **extra})
        assert query["query"] == f"conversation_id:{ROOT}" and query["expansions"] == "author_id"
        since = int(query.get("since_id", 0))
        found = sorted((p for p in self.posts if int(p["id"]) > since), key=lambda p: int(p["id"]), reverse=True)
        found = found[:int(query["max_results"])]
        if not found:
            return web.json_response({"meta": {"result_count": 0}}, headers=headers)
        authors = {p["author_id"] for p in found}
        return web.json_response({
            "data": found, "includes": {"users": [u for u in USERS if u["id"] in authors]},
            "meta": {"newest_id": found[0]["id"], "oldest_id": found[-1]["id"], "result_count": len(found)}},
            headers=headers)

    async def lookup(self, request):
        self.requests.append((request.path, dict(request.query)))
        if self.fail:
            status, body, extra = self.fail
            return web.json_response(body, status=status, headers=extra)
        if request.match_info["id"] != ROOT:
            return web.json_response({"errors": [{"title": "Not Found Error", "detail": "Could not find tweet"}]})
        created = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
        return web.json_response({"data": {"id": ROOT, "text": "ao vivo!", "author_id": "1", "created_at": created},
                                  "includes": {"users": [USERS[0]]}})


async def serve(fake):
    app = web.Application()
    app.router.add_get("/2/tweets/search/recent", fake.search)
    app.router.add_get("/2/tweets/{id}", fake.lookup)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    return runner, f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}"


class Stop(Exception):
    pass


class Rig:
    def __init__(self, target, base, bearer=BEARER, options=None, skip_backlog=True, on_sleep=None, max_sleeps=10):
        store = CredentialStore()
        if bearer:
            store.set("x/bearer", {"bearer_token": bearer})
        self.got, self.statuses, self.sleeps = [], [], []
        self.on_sleep, self.max_sleeps = on_sleep, max_sleeps
        ctx = ConnectorContext(credentials=store, skip_backlog=skip_backlog,
                               extra={"x_api_base": base, "sleep": self.sleep})
        self.conn = XConnector(SourceConfig(platform="x", target=target, options=options or {}), self.got.append,
                               lambda s: self.statuses.append((s.state, s.code, s.detail)), ctx)

    async def sleep(self, seconds):
        self.sleeps.append(seconds)
        if self.on_sleep:
            self.on_sleep(len(self.sleeps))
        if len(self.sleeps) >= self.max_sleeps:
            raise Stop()
        await asyncio.sleep(0)

    async def run_until_stopped(self):
        try:
            await self.conn.run()
        except (asyncio.CancelledError, Stop):
            pass
        finally:
            await self.conn.close()


def scenario(fake, body):
    async def go():
        runner, base = await serve(fake)
        try:
            return await asyncio.wait_for(body(base), 5)
        finally:
            await runner.cleanup()

    return asyncio.run(go())


def searches(fake):
    return [q for p, q in fake.requests if p == "/2/tweets/search/recent"]


def test_replies_mapping_since_id_and_root_skipped():
    fake = FakeX()

    def on_sleep(n):
        if n == 1:
            fake.posts += [post(ROOT, "1", "Estou ao vivo!"), post("1840000000000000005", "2", "@canal_linux oi tux?"),
                           post("1840000000000000007", "1", "@bia valeu")]
        if n == 2:
            fake.posts.append(post("1840000000000000010", "3", "@canal_linux @bia que distro?"))

    async def body(base):
        rig = Rig(f"https://x.com/canal_linux/status/{ROOT}", base, on_sleep=on_sleep, max_sleeps=3)
        await rig.run_until_stopped()
        return rig

    rig = scenario(fake, body)
    assert [m.id for m in rig.got] == ["1840000000000000005", "1840000000000000007", "1840000000000000010"]
    bia, owner, caio = rig.got
    assert (bia.author, bia.author_id, bia.text, bia.is_verified) == ("Bia", "2", "oi tux?", False)
    assert owner.is_owner and owner.author == "Canal Linux" and owner.text == "valeu"
    assert caio.author == "caio" and caio.is_verified and caio.text == "que distro?"
    assert bia.timestamp == pytest.approx(1791817200.0)
    assert rig.conn.status.channel == "@canal_linux" and not rig.conn.reconnect_when_ended
    first, second, third = searches(fake)
    assert "start_time" in first and "since_id" not in first  # backlog never requested (nor billed)
    assert first["max_results"] == "100" and "verified" in first["user.fields"]
    assert "start_time" in second and "since_id" not in second  # nothing seen yet: still the same window
    assert third["since_id"] == "1840000000000000007"
    assert rig.sleeps[0] == 20.0 and rig.statuses[-1][0] == "connected"


def test_backlog_read_when_not_skipped():
    fake = FakeX()
    fake.posts = [post(ROOT, "1", "live!"), post("1840000000000000002", "2", "@canal_linux primeira")]

    async def body(base):
        rig = Rig(f"post:{ROOT}", base, skip_backlog=False, max_sleeps=1)
        await rig.run_until_stopped()
        return rig

    rig = scenario(fake, body)
    assert [m.text for m in rig.got] == ["primeira"]
    assert "start_time" not in searches(fake)[0] and rig.conn.since_id == "1840000000000000002"


def test_rate_limit_429_uses_reset_header():
    fake = FakeX()
    fake.fail = (429, {"title": "Too Many Requests"}, {})
    fake.remaining = 0
    fake.reset = int(time.time()) + 120

    async def body(base):
        rig = Rig(f"post:{ROOT}", base)
        with pytest.raises(RateLimited) as info:
            await rig.conn.session()
        await rig.conn.close()
        return info.value

    assert 100 <= scenario(fake, body).retry_after <= 121


def test_interval_follows_remaining_budget():
    async def body(base):
        rig = Rig(f"post:{ROOT}", base)
        conn = rig.conn
        conn.remaining, conn.reset_at = 1, time.time() + 100
        slow = conn.interval()
        conn.remaining, conn.reset_at = 400, time.time() + 600
        normal = conn.interval()
        return slow, normal

    slow, normal = scenario(FakeX(), body)
    assert 99 <= slow <= 101 and normal == 20.0


@pytest.mark.parametrize("value,expected", [("5", 15.0), ("1000", 300.0), ("45", 45.0), ("x", 20.0)])
def test_poll_option_is_clamped(value, expected):
    conn = XConnector(SourceConfig(platform="x", target=f"post:{ROOT}", options={"poll": value}),
                      lambda m: None, lambda s: None)
    assert conn.poll == expected


@pytest.mark.parametrize("status,body,state,code", [
    (401, {"title": "Unauthorized"}, "auth_required", "auth-required"),
    (403, {"reason": "client-not-enrolled", "title": "Client Forbidden"}, "unsupported", "plan-required"),
    (402, {"title": "CreditsDepleted"}, "unsupported", "plan-required"),
    (403, {"title": "Forbidden", "detail": "nope"}, "auth_required", "auth-required"),
])
def test_http_errors_stop_the_source(status, body, state, code):
    fake = FakeX()
    fake.fail = (status, body, {})

    async def go(base):
        rig = Rig(f"post:{ROOT}", base)
        await rig.run_until_stopped()
        probe = await rig.conn.probe()
        return rig, probe

    rig, probe = scenario(fake, go)
    assert rig.statuses[-1][:2] == (state, code)
    assert not probe.ok and probe.code == code


def test_broadcast_is_unsupported_without_crashing():
    async def body(base):
        rig = Rig("https://x.com/i/broadcasts/1ABCdefGHIjkl", base)
        await rig.run_until_stopped()
        return rig, await rig.conn.probe()

    fake = FakeX()
    rig, probe = scenario(fake, body)
    state, code, detail = rig.statuses[-1]
    assert (state, code) == ("unsupported", "no-api") and "no API" in detail
    assert not probe.ok and probe.code == "unsupported" and fake.requests == []


def test_missing_bearer_is_auth_required():
    async def body(base):
        rig = Rig(f"post:{ROOT}", base, bearer=None)
        await rig.run_until_stopped()
        return rig, await rig.conn.probe()

    fake = FakeX()
    rig, probe = scenario(fake, body)
    assert rig.statuses[-1][:2] == ("auth_required", "auth-required") and "Settings › Accounts" in rig.statuses[-1][2]
    assert probe.code == "auth-required" and fake.requests == []


def test_probe_reads_only_the_post():
    async def body(base):
        ok = await Rig(f"post:{ROOT}", base).conn.probe()
        missing = await Rig("post:1849999999999999999", base).conn.probe()
        return ok, missing

    fake = FakeX()
    ok, missing = scenario(fake, body)
    assert (ok.ok, ok.code, ok.channel) == (True, "ready", "@canal_linux")
    assert (missing.ok, missing.code) == (False, "not-found")
    assert searches(fake) == []


def test_rejects_bad_targets():
    for bad in ("", "https://x.com/canal_linux", "https://x.com/i/spaces/1abc", "post:abc"):
        with pytest.raises(ValueError):
            XConnector(SourceConfig(platform="x", target=bad), lambda m: None, lambda s: None)


def test_bearer_never_leaks(caplog):
    caplog.set_level(logging.DEBUG)
    texts = []

    async def body(base):
        for status, payload in ((401, {"detail": f"bad {BEARER}"}), (400, {"detail": f"odd {BEARER}"}),
                                (403, {"detail": f"forbidden {BEARER}"}), (503, {"detail": BEARER}),
                                (429, {"detail": BEARER})):
            fake.fail = (status, payload, {})
            rig = Rig(f"post:{ROOT}", base, max_sleeps=2)
            try:
                await rig.conn.session()
            except Exception as e:  # noqa: BLE001
                texts.append(str(e))
            await rig.run_until_stopped()
            texts.append(json.dumps(rig.statuses))
            texts.append(json.dumps((await rig.conn.probe()).to_dict()))

    fake = FakeX()
    scenario(fake, body)
    assert any("odd ***" in t for t in texts)
    assert BEARER not in "\n".join(texts) + caplog.text
