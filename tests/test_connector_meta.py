"""Facebook and Instagram connectors against a local fake of the Graph API (no network)."""

import asyncio
import json
import logging

import pytest
from aiohttp import web

from chattoon.core.config import SourceConfig
from chattoon.core.credentials import CredentialStore
from chattoon.core.streams.base import ConnectorContext, NotLive, RateLimited
from chattoon.core.streams.meta import FacebookConnector, InstagramConnector, parse_time, usage

USER_TOKEN = "EAAuserSECRETtoken0001"
PAGE_TOKEN = "EAApageSECRETtoken0002"
OTHER_PAGE_TOKEN = "EAAotherSECRETtoken0003"
T0 = 1791800000  # comment times (unix)


def gtime(ts):
    from datetime import datetime, timezone

    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+0000")


def fb_comment(cid, ts, name="Bia", uid="501", text=None):
    return {"id": cid, "message": text if text is not None else f"msg {cid}", "created_time": gtime(ts),
            "from": {"id": uid, "name": name}}


def ig_comment(cid, ts, user="leo", uid="601"):
    return {"id": cid, "text": f"ig {cid}", "username": user, "timestamp": gtime(ts), "from": {"id": uid, "username": user}}


class FakeGraph:
    """Just enough Graph API: tokens decide who ``/me`` is, like the real one."""

    def __init__(self):
        self.requests = []  # (path, query dict, token)
        self.live = True
        self.video_status = "LIVE"
        self.comments = []
        self.ig_live = True
        self.ig_comments = []
        self.headers = {}
        self.errors = {}  # path -> (http status, error dict)

    def error(self, status, code, message="boom", **extra):
        return web.json_response({"error": {"message": message, "type": "OAuthException", "code": code, **extra}},
                                 status=status, headers=self.headers)

    async def handle(self, request):
        path = request.path.strip("/")
        token = request.headers.get("Authorization", "").removeprefix("Bearer ")
        query = dict(request.query)
        self.requests.append((path, query, token))
        assert "access_token" not in query
        if path in self.errors:
            status, err = self.errors[path]
            return self.error(status, **err)
        if token not in (USER_TOKEN, PAGE_TOKEN, OTHER_PAGE_TOKEN):
            return self.error(400, 190, "Invalid OAuth access token.")
        body = self.route(path, query, token)
        if isinstance(body, web.Response):
            return body
        return web.json_response(body, headers=self.headers)

    def route(self, path, query, token):
        fields = query.get("fields", "")
        if path == "me":
            if token == USER_TOKEN:
                if "instagram_business_account" in fields:
                    return self.error(400, 100, "Tried accessing nonexisting field (instagram_business_account)")
                return {"id": "100", "name": "Ana Streamer"}
            body = {"id": "200", "name": "Canal Linux"}
            if "instagram_business_account" in fields:
                body["instagram_business_account"] = {"id": "300", "username": "canal.linux"}
            return body
        if path == "me/accounts":
            if token != USER_TOKEN:
                return self.error(400, 100, "(#100) Tried accessing nonexisting field (accounts) on node type (Page)")
            return {"data": [
                {"id": "200", "name": "Canal Linux", "username": "canallinux", "access_token": PAGE_TOKEN,
                 "instagram_business_account": {"id": "300", "username": "canal.linux"}},
                {"id": "201", "name": "Outra Página", "access_token": OTHER_PAGE_TOKEN}]}
        if path == "200/live_videos":
            assert query["broadcast_status"] == '["LIVE"]'
            return {"data": [{"id": "900", "status": "LIVE", "title": "ao vivo"}] if self.live else []}
        if path in ("900/comments", "5551234567/comments"):
            since = int(query.get("since", 0))
            items = sorted((c for c in self.comments if parse_time(c["created_time"]) >= since),
                           key=lambda c: c["created_time"], reverse=True)
            if token == USER_TOKEN:  # like Meta: with a user token only the user's own name comes back
                items = [{k: v for k, v in c.items() if k != "from"} for c in items]
            return {"data": items}
        if path == "900":
            return {"id": "900", "status": self.video_status}
        if path == "5551234567":
            if fields == "from{id,name}":
                return {"id": "5551234567", "from": {"id": "200", "name": "Canal Linux"}}
            return {"id": "5551234567", "live_status": self.video_status}
        if path == "canal-linux-oficial":  # a Page looked up by its username
            return {"id": "200"}
        if path == "300/live_media":
            return {"data": [{"id": "777", "media_type": "BROADCAST", "media_product_type": "LIVE"}]
                    if self.ig_live else []}
        if path == "777/comments":
            assert query["limit"] == "50"
            newest = sorted(self.ig_comments, key=lambda c: c["timestamp"], reverse=True)
            return {"data": newest[:50]}
        return self.error(400, 100, f"Unsupported get request. Object with ID '{path}' does not exist")


async def serve(fake):
    app = web.Application()
    app.router.add_get("/{tail:.*}", fake.handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    return runner, f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}"


class Stop(Exception):
    pass


class Rig:
    """A connector wired to the fake server, a fake sleep and collectors."""

    def __init__(self, cls, target, base, cred=None, options=None, skip_backlog=True, on_sleep=None, max_sleeps=20):
        store = CredentialStore()
        if cred is not None:
            store.set("meta/token", cred)
        self.got, self.statuses, self.sleeps = [], [], []
        self.on_sleep, self.max_sleeps = on_sleep, max_sleeps
        ctx = ConnectorContext(credentials=store, skip_backlog=skip_backlog,
                               extra={"graph_base": base, "sleep": self.sleep, "wait_poll": 30})
        platform = "facebook" if cls is FacebookConnector else "instagram"
        self.conn = cls(SourceConfig(platform=platform, target=target, options=options or {}), self.got.append,
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


def comment_requests(fake, path="900/comments"):
    return [(q, t) for p, q, t in fake.requests if p == path]


# -- Facebook ---------------------------------------------------------------------------------

def test_fb_user_token_picks_page_token_skips_backlog_and_follows_since():
    fake = FakeGraph()
    fake.comments = [fb_comment("c1", T0), fb_comment("c2", T0 + 5)]

    def on_sleep(n):
        if n == 1:
            fake.comments += [fb_comment("c3", T0 + 10, "Caio", "502"), fb_comment("c4", T0 + 12, "Canal Linux", "200")]
        if n == 2:
            fake.comments.append(fb_comment("c5", T0 + 20, "Duda", "503"))
        if n == 3:
            fake.video_status = "LIVE_STOPPED"

    async def body(base):
        rig = Rig(FacebookConnector, "https://www.facebook.com/canallinux", base, {"access_token": USER_TOKEN},
                  options={"poll": "10"}, on_sleep=on_sleep)
        await rig.conn.session()  # returns when the live ends
        await rig.conn.close()
        return rig

    rig = scenario(fake, body)
    assert [m.id for m in rig.got] == ["c3", "c4", "c5"]  # c1/c2 were backlog
    assert [m.author for m in rig.got] == ["Caio", "Canal Linux", "Duda"]
    assert rig.got[1].is_owner and not rig.got[0].is_owner and rig.got[0].author_id == "502"
    assert rig.got[0].timestamp == T0 + 10 and rig.got[0].text == "msg c3"
    assert rig.conn.status.channel == "Canal Linux" and rig.conn.reconnect_when_ended
    reads = comment_requests(fake)
    assert all(t == PAGE_TOKEN for _, t in reads)  # names need the Page token
    first = reads[0][0]
    assert first["filter"] == "stream" and first["order"] == "reverse_chronological"
    assert first["live_filter"] == "no_filter" and "from{id,name}" in first["fields"] and "since" not in first
    assert reads[1][0]["since"] == str(T0 + 5) and reads[2][0]["since"] == str(T0 + 12)
    assert rig.sleeps == [10.0, 10.0, 10.0]
    assert [p for p, _, _ in fake.requests][:3] == ["me", "me/accounts", "200/live_videos"]


def test_fb_page_token_direct_without_backlog_skip():
    fake = FakeGraph()
    fake.comments = [fb_comment("c1", T0)]

    async def body(base):
        rig = Rig(FacebookConnector, "canal-linux-oficial", base, {"access_token": PAGE_TOKEN, "kind": "page"},
                  skip_backlog=False, max_sleeps=1)
        with pytest.raises(Stop):
            await rig.conn.session()
        await rig.conn.close()
        wrong = Rig(FacebookConnector, "otherpage", base, {"access_token": PAGE_TOKEN, "kind": "page"})
        await wrong.run_until_stopped()
        return rig, wrong

    rig, wrong = scenario(fake, body)
    assert [m.id for m in rig.got] == ["c1"]
    paths = [p for p, _, _ in fake.requests]
    assert "me/accounts" not in paths and "canal-linux-oficial" in paths  # username checked with the Page token
    assert rig.sleeps == [5.0]
    assert wrong.statuses[-1][0] == "auth_required" and "belongs to the Page 'Canal Linux'" in wrong.statuses[-1][2]


def test_fb_page_token_without_kind_is_detected():
    fake = FakeGraph()

    async def body(base):
        rig = Rig(FacebookConnector, "200", base, {"access_token": PAGE_TOKEN}, max_sleeps=1)
        with pytest.raises(Stop):
            await rig.conn.session()
        await rig.conn.close()
        return rig

    rig = scenario(fake, body)
    assert rig.conn.status.state == "connected" and rig.conn.status.channel == "Canal Linux"
    assert all(t == PAGE_TOKEN for _, t in comment_requests(fake))


@pytest.mark.parametrize("header,value,expected", [
    ("X-Business-Use-Case-Usage", {"200": [{"type": "pages", "call_count": 80, "total_cputime": 10,
                                            "total_time": 12, "estimated_time_to_regain_access": 0}]}, 15.0),
    ("X-App-Usage", {"call_count": 95, "total_cputime": 1, "total_time": 1}, 30.0),
    ("X-App-Usage", {"call_count": 40, "total_cputime": 1, "total_time": 1}, 5.0),
])
def test_fb_usage_headers_slow_down(header, value, expected):
    fake = FakeGraph()
    fake.headers = {header: json.dumps(value)}

    async def body(base):
        rig = Rig(FacebookConnector, "canallinux", base, {"access_token": USER_TOKEN}, max_sleeps=2)
        with pytest.raises(Stop):
            await rig.conn.session()
        await rig.conn.close()
        return rig

    assert scenario(fake, body).sleeps == [expected, expected]


def test_usage_parser_and_regain_time():
    headers = {"X-Business-Use-Case-Usage": json.dumps(
        {"1": [{"type": "pages", "call_count": 100, "total_time": 20, "estimated_time_to_regain_access": 7}]}),
        "X-App-Usage": "not json"}
    assert usage(headers) == (100.0, 7.0)
    assert usage({}) == (0.0, 0.0)


def test_fb_invalid_token_stops_with_auth_required():
    fake = FakeGraph()
    fake.errors["me"] = (400, {"code": 190, "message": "Error validating access token: Session has expired"})

    async def body(base):
        rig = Rig(FacebookConnector, "canallinux", base, {"access_token": USER_TOKEN})
        await rig.run_until_stopped()
        return rig

    rig = scenario(fake, body)
    state, code, detail = rig.statuses[-1]
    assert (state, code) == ("auth_required", "auth-required") and "Settings" in detail


def test_fb_permission_error_names_the_permission():
    fake = FakeGraph()
    fake.errors["900/comments"] = (403, {"code": 10, "message": "(#10) Application does not have permission"})

    async def body(base):
        rig = Rig(FacebookConnector, "canallinux", base, {"access_token": USER_TOKEN})
        await rig.run_until_stopped()
        return rig

    state, code, detail = scenario(fake, body).statuses[-1]
    assert state == "auth_required" and "pages_read_engagement" in detail


def test_fb_missing_credential():
    async def body(base):
        rig = Rig(FacebookConnector, "canallinux", base, None)
        await rig.run_until_stopped()
        probe = await rig.conn.probe()
        return rig, probe

    rig, probe = scenario(FakeGraph(), body)
    assert rig.statuses[-1][:2] == ("auth_required", "auth-required") and "Settings › Accounts" in rig.statuses[-1][2]
    assert not probe.ok and probe.code == "auth-required"


def test_fb_throttled_becomes_rate_limited_with_meta_wait():
    fake = FakeGraph()
    fake.errors["200/live_videos"] = (400, {"code": 32, "message": "Page request limit reached"})
    fake.headers = {"X-Business-Use-Case-Usage": json.dumps(
        {"200": [{"type": "pages", "call_count": 100, "estimated_time_to_regain_access": 4}]})}

    async def body(base):
        rig = Rig(FacebookConnector, "canallinux", base, {"access_token": USER_TOKEN})
        with pytest.raises(RateLimited) as info:
            await rig.conn.session()
        await rig.conn.close()
        return info.value

    assert scenario(fake, body).retry_after == 240.0


def test_fb_not_live_waits():
    fake = FakeGraph()
    fake.live = False

    async def body(base):
        rig = Rig(FacebookConnector, "canallinux", base, {"access_token": USER_TOKEN}, max_sleeps=1)
        await rig.run_until_stopped()
        probe = await rig.conn.probe()
        return rig, probe

    rig, probe = scenario(fake, body)
    assert rig.statuses[-1][:2] == ("waiting", "not-live") and rig.sleeps == [30]
    assert probe.ok and probe.code == "offline" and probe.channel == "Canal Linux"


def test_fb_video_target_reads_that_video_and_ends():
    fake = FakeGraph()
    fake.comments = [fb_comment("v1", T0)]

    def on_sleep(n):
        if n == 1:
            fake.comments.append(fb_comment("v2", T0 + 3))
        if n == 3:
            fake.video_status = "VOD"

    async def body(base):
        rig = Rig(FacebookConnector, "https://www.facebook.com/canallinux/videos/5551234567/", base,
                  {"access_token": USER_TOKEN}, options={"poll": "10"}, on_sleep=on_sleep)
        await rig.run_until_stopped()
        return rig

    rig = scenario(fake, body)
    assert [m.id for m in rig.got] == ["v2"]
    assert not rig.conn.reconnect_when_ended and rig.statuses[-1][0] == "ended"
    assert all(t == PAGE_TOKEN for _, t in comment_requests(fake, "5551234567/comments"))  # owner's Page token
    assert "200/live_videos" not in [p for p, _, _ in fake.requests]  # no discovery for a pasted video


def test_fb_personal_profile_and_unmanaged_page_are_explained():
    async def body(base):
        mine = Rig(FacebookConnector, "ana.streamer", base, {"access_token": USER_TOKEN})
        await mine.run_until_stopped()
        other = Rig(FacebookConnector, "otherpage", base, {"access_token": USER_TOKEN})
        await other.run_until_stopped()
        return mine, other

    mine, other = scenario(FakeGraph(), body)
    assert mine.statuses[-1][0] == "unsupported" and "personal profile" in mine.statuses[-1][2]
    assert other.statuses[-1][0] == "unsupported" and "Canal Linux" in other.statuses[-1][2]


def test_fb_probe_live_and_not_found():
    fake = FakeGraph()

    async def body(base):
        ok = await Rig(FacebookConnector, "canallinux", base, {"access_token": USER_TOKEN}).conn.probe()
        gone = await Rig(FacebookConnector, "video:5550000000", base, {"access_token": PAGE_TOKEN,
                                                                       "kind": "page"}).conn.probe()
        return ok, gone

    ok, gone = scenario(fake, body)
    assert (ok.ok, ok.code, ok.channel) == (True, "live", "Canal Linux")
    assert (gone.ok, gone.code) == (False, "not-found")


def test_fb_rejects_bad_targets():
    for bad in ("", "https://fb.watch/abc", "https://example.com/page", "has space"):
        with pytest.raises(ValueError):
            FacebookConnector(SourceConfig(platform="facebook", target=bad), lambda m: None, lambda s: None)


# -- Instagram --------------------------------------------------------------------------------

def test_ig_account_live_comments_cap_and_dedup():
    fake = FakeGraph()
    fake.ig_comments = [ig_comment(f"old{i}", T0 + i) for i in range(60)]

    def on_sleep(n):
        if n == 1:
            fake.ig_comments += [ig_comment("n1", T0 + 100, "mia", "602"), ig_comment("n2", T0 + 101, "canal.linux", "300")]
        if n == 3:
            fake.ig_comments += [ig_comment(f"burst{i:02d}", T0 + 200 + i) for i in range(55)]

    async def body(base):
        rig = Rig(InstagramConnector, "https://www.instagram.com/Canal.Linux/", base, {"access_token": USER_TOKEN},
                  on_sleep=on_sleep, max_sleeps=4)
        with pytest.raises(Stop):
            await rig.conn.session()
        await rig.conn.close()
        return rig

    rig = scenario(fake, body)
    ids = [m.id for m in rig.got]
    assert ids[:2] == ["n1", "n2"]  # the 50 visible old comments were backlog; poll 3 repeated nothing
    assert rig.got[0].author == "mia" and rig.got[0].author_id == "602" and rig.got[1].is_owner
    assert ids[2:] == [f"burst{i:02d}" for i in range(5, 55)]  # only the newest 50 are visible
    assert len(ids) == len(set(ids))
    assert rig.conn.status.channel == "@canal.linux"
    assert rig.sleeps == [6.0, 6.0, 6.0, 3.0]  # a full page of new comments: look again sooner
    paths = [p for p, _, _ in fake.requests]
    assert paths[:3] == ["me/accounts", "300/live_media", "777/comments"]


def test_ig_page_token_and_live_end():
    fake = FakeGraph()

    def on_sleep(n):
        if n == 3:
            fake.ig_live = False

    async def body(base):
        rig = Rig(InstagramConnector, "@canal.linux", base, {"access_token": PAGE_TOKEN, "kind": "page"},
                  options={"poll": "10"}, on_sleep=on_sleep)
        await rig.conn.session()  # returns: the live is over
        await rig.conn.close()
        return rig

    rig = scenario(fake, body)
    assert rig.conn.reconnect_when_ended and rig.sleeps == [10.0, 10.0, 10.0]
    assert "me/accounts" not in [p for p, _, _ in fake.requests]


def test_ig_no_live_waits_and_unlinked_account_is_explained():
    fake = FakeGraph()
    fake.ig_live = False

    async def body(base):
        rig = Rig(InstagramConnector, "@canal.linux", base, {"access_token": USER_TOKEN}, max_sleeps=1)
        await rig.run_until_stopped()
        with pytest.raises(NotLive):
            await rig.conn.session()
        probe = await rig.conn.probe()
        other = Rig(InstagramConnector, "@someone", base, {"access_token": USER_TOKEN})
        await other.run_until_stopped()
        return rig, probe, other

    rig, probe, other = scenario(fake, body)
    assert rig.statuses[-1][:2] == ("waiting", "not-live")
    assert probe.ok and probe.code == "offline" and probe.channel == "@canal.linux"
    assert other.statuses[-1][0] == "unsupported" and "professional" in other.statuses[-1][2]


# -- secrets ------------------------------------------------------------------------------------

def test_tokens_never_leak_to_status_errors_or_logs(caplog):
    caplog.set_level(logging.DEBUG)
    leaks = []

    async def body(base):
        rigs = []
        for path, status, err in (("me", 400, {"code": 190, "message": f"bad token {USER_TOKEN}"}),
                                  ("900/comments", 400, {"code": 200, "message": f"perm {PAGE_TOKEN}"}),
                                  ("200/live_videos", 400, {"code": 4, "message": "app limit"}),
                                  ("900/comments", 400, {"code": 9999, "message": f"weird {PAGE_TOKEN}"}),
                                  ("900/comments", 500, {"code": 1, "message": "unknown"})):
            fake.errors = {path: (status, err)}
            rig = Rig(FacebookConnector, "canallinux", base, {"access_token": USER_TOKEN}, max_sleeps=2)
            try:
                await rig.conn.session()
            except Exception as e:  # noqa: BLE001
                leaks.append(str(e))
            await rig.run_until_stopped()
            leaks.append(json.dumps(rig.statuses))
            leaks.append(json.dumps((await rig.conn.probe()).to_dict()))
            rigs.append(rig)
        return rigs

    fake = FakeGraph()
    rigs = scenario(fake, body)
    assert any("weird ***" in text for text in leaks)  # Meta's own message is kept, scrubbed
    text = "\n".join(leaks) + caplog.text
    for token in (USER_TOKEN, PAGE_TOKEN, OTHER_PAGE_TOKEN):
        assert token not in text
    assert len(rigs) == 5
