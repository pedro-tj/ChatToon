"""TikTok connector against a fake TikTokLive module (no network, no library needed)."""

import asyncio
import importlib.util
import inspect
from types import SimpleNamespace

import pytest

from chattoon.core.config import SourceConfig
from chattoon.core.streams import tiktok
from chattoon.core.streams.base import (ConnectorContext, NotLive, RateLimited, TransientError,
                                        Unsupported)
from chattoon.core.streams.tiktok import TikTokConnector

from .conftest import run

KEY = "euler-secret-key-123456"


# -- fake TikTokLive -------------------------------------------------------------------

class FakeEvent:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class GiftEvent(FakeEvent):
    @property
    def streaking(self):  # same rule as TikTokLive: streakable (type 1) and not repeat_end
        return self.gift is not None and self.gift.type == 1 and not self.repeat_end


def _events():
    names = ("ConnectEvent", "DisconnectEvent", "LiveEndEvent", "LivePauseEvent", "CommentEvent", "FollowEvent",
             "SubNotifyEvent", "ShareEvent", "LikeEvent")
    ns = SimpleNamespace(**{n: type(n, (FakeEvent,), {}) for n in names})
    ns.GiftEvent = GiftEvent
    return ns


class TikTokLiveError(RuntimeError):
    pass


class UserOfflineError(TikTokLiveError):
    pass


class UserNotFoundError(TikTokLiveError):
    pass


class AgeRestrictedError(TikTokLiveError):
    pass


class SignAPIError(TikTokLiveError):
    pass


class SignatureRateLimitError(SignAPIError):
    def __init__(self, message="", retry_after=None):
        super().__init__(message)
        if retry_after is not None:
            self.retry_after = retry_after


class WebcastBlockedError(TikTokLiveError):
    pass


class FakeWeb:
    def __init__(self, lib):
        self.lib, self.closed = lib, 0

    async def close(self):
        self.closed += 1
        if self.lib.web_close_error:
            raise RuntimeError("web close failed")


class FakeClient:
    def __init__(self, lib, unique_id, web_kwargs=None):
        self.lib, self.unique_id, self.web_kwargs = lib, unique_id, web_kwargs
        self.web = FakeWeb(lib)
        self.listeners: dict[type, list] = {}
        self.start_kwargs = None
        self.disconnects = 0
        self._stop = asyncio.Event()
        self.task = None
        lib.clients.append(self)

    async def is_live(self):
        if self.lib.is_live_error:
            raise self.lib.is_live_error
        return self.lib.live

    def add_listener(self, event, f):
        self.listeners.setdefault(event, []).append(f)

    def on(self, event, f=None):
        if f is None:
            return lambda g: self.add_listener(event, g) or g
        self.add_listener(event, f)

    def fire(self, event):
        for f in self.listeners.get(type(event), []):
            f(event)

    async def start(self, **kw):
        self.start_kwargs = kw
        if self.lib.start_error:
            raise self.lib.start_error
        self.task = asyncio.ensure_future(self._loop())
        return self.task

    async def _loop(self):
        self.fire(self.lib.events.ConnectEvent(unique_id=self.unique_id, room_id=1))
        for item in self.lib.script:
            await asyncio.sleep(0)
            if isinstance(item, BaseException):
                raise item
            self.fire(item)
        if not self.lib.ends_by_itself:
            await self._stop.wait()  # like a live websocket: runs until disconnect()
        self.fire(self.lib.events.DisconnectEvent())

    async def disconnect(self):
        self.disconnects += 1
        self._stop.set()
        if self.lib.disconnect_error:
            raise RuntimeError("disconnect failed")
        if self.task is not None:
            await self.task


def fake_module(**kw):
    lib = SimpleNamespace(events=_events(), clients=[], live=True, is_live_error=None, start_error=None,
                          script=[], ends_by_itself=False, disconnect_error=False, web_close_error=False,
                          TikTokLiveError=TikTokLiveError, UserOfflineError=UserOfflineError,
                          UserNotFoundError=UserNotFoundError, AgeRestrictedError=AgeRestrictedError,
                          SignAPIError=SignAPIError, SignatureRateLimitError=SignatureRateLimitError,
                          WebcastBlockedError=WebcastBlockedError)
    lib.__dict__.update(kw)
    lib.TikTokLiveClient = lambda unique_id, web_kwargs=None: FakeClient(lib, unique_id, web_kwargs)
    return lib


class Store:
    def __init__(self, data=None):
        self.data = data or {}

    def get(self, key):
        return self.data.get(key)


class StopLoop(Exception):
    pass


def make(lib, target="https://www.tiktok.com/@Ana.Live/live", credentials=None, **extra):
    messages, states = [], []
    ctx = ConnectorContext(credentials=credentials, extra={"tiktok_module": lib, **extra})
    source = SourceConfig(id="tt-1", platform="tiktok", target=target)

    def on_status(status):
        states.append((status.state, status.code, status.detail))

    return TikTokConnector(source, messages.append, on_status, ctx), messages, states


async def _stop_sleep(delay):
    raise StopLoop


def supervise(connector):
    """Run the supervisor until it stops by itself or sleeps once (then StopLoop)."""
    async def go():
        try:
            await connector.run()
        except StopLoop:
            pass
    run(go())


def user(uid=7, unique_id="ana", nickname="Ana", **kw):
    return SimpleNamespace(id=uid, unique_id=unique_id, nickname=nickname, is_moderator=False, verified=False, **kw)


def comment(lib, text="oi tudo bem?", msg_id=101, **identity):
    ident = {"is_moderator_of_anchor": False, "is_subscriber_of_anchor": False, "is_anchor": False, **identity}
    return lib.events.CommentEvent(content=text, comment=text, user=user(),
                                   user_identity=SimpleNamespace(**ident),
                                   common=SimpleNamespace(msg_id=msg_id, create_time=1_760_000_000_000))


def gift(lib, repeat_count, repeat_end, gift_type=1, msg_id=500, name="Rosa"):
    return lib.events.GiftEvent(gift=SimpleNamespace(name=name, diamond_count=1, type=gift_type),
                                repeat_count=repeat_count, repeat_end=repeat_end, user=user(), user_identity=None,
                                common=SimpleNamespace(msg_id=msg_id, create_time=0))


# -- tests --------------------------------------------------------------------------

def test_target_is_normalised_and_bad_target_rejected():
    connector, _, _ = make(fake_module())
    assert connector.user == "@ana.live"
    assert connector.reconnect_when_ended and connector.support == "experimental"
    with pytest.raises(ValueError):
        make(fake_module(), target="https://vm.tiktok.com/ZMabc/")
    with pytest.raises(ValueError):
        make(fake_module(), target="not a user!")


def test_comment_mapping_flags_and_live_end():
    lib = fake_module()
    lib.script = [comment(lib, msg_id=101),
                  comment(lib, "sou mod", msg_id=102, is_moderator_of_anchor=True, is_subscriber_of_anchor=True),
                  comment(lib, "eu sou o dono", msg_id=103, is_anchor=True),
                  comment(lib, "repetida", msg_id=101),  # same id: delivered once
                  comment(lib, "   ", msg_id=104),  # empty: ignored
                  lib.events.LikeEvent(user=user()), lib.events.ShareEvent(user=user()),
                  lib.events.LiveEndEvent()]
    connector, messages, states = make(lib)
    run(connector.session())  # LiveEndEvent: the session returns normally
    assert ("connected", "", "") in states and connector.status.channel == "@ana.live"
    assert [m.text for m in messages] == ["oi tudo bem?", "sou mod", "eu sou o dono"]
    first, mod, owner = messages
    assert first.id == "101" and first.author == "Ana" and first.author_id == "7"
    assert first.event_type == "message" and first.platform == "tiktok" and first.source_id == "tt-1"
    assert first.channel == "@ana.live" and first.timestamp == 1_760_000_000
    assert not (first.is_moderator or first.is_member or first.is_owner)
    assert mod.is_moderator and mod.is_member and not mod.is_owner
    assert owner.is_owner
    client = lib.clients[0]
    assert client.unique_id == "@ana.live" and client.web_kwargs is None  # no key: library defaults
    assert client.start_kwargs == {"process_connect_events": False, "fetch_live_check": False,
                                   "fetch_gift_info": False}
    assert client.disconnects == 1 and client.web.closed == 1 and connector._client is None


def test_comment_without_msg_id_gets_stable_id_and_fallback_author():
    lib = fake_module()
    connector, messages, _ = make(lib)
    event = comment(lib, msg_id=0)
    event.user = SimpleNamespace(id=0, unique_id="sem_nome", nickname="", is_moderator=True)
    connector._on_comment(event)
    connector._seen.clear()
    connector._on_comment(event)
    assert len(messages) == 2 and messages[0].id == messages[1].id and messages[0].id.startswith("message:h")
    assert messages[0].author == "sem_nome" and messages[0].author_id == "sem_nome" and messages[0].is_moderator


def test_gift_streak_emits_only_the_final_event():
    lib = fake_module()
    lib.script = [gift(lib, 1, 0, msg_id=501), gift(lib, 3, 0, msg_id=502), gift(lib, 5, 1, msg_id=503),
                  gift(lib, 1, 0, gift_type=2, msg_id=504, name="Universo"), lib.events.LiveEndEvent()]
    connector, messages, _ = make(lib)
    run(connector.session())
    assert [(m.superchat, m.event_type, m.paid_kind, m.text) for m in messages] == [
        ("Rosa ×5", "gift", "gift", ""), ("Universo", "gift", "gift", "")]
    assert messages[0].id == "gift:503" and messages[0].is_paid


def test_follow_and_subscription_events():
    lib = fake_module()
    lib.script = [lib.events.FollowEvent(user=user(), common=SimpleNamespace(msg_id=900, create_time=0)),
                  lib.events.SubNotifyEvent(user=user(), common=SimpleNamespace(msg_id=901, create_time=0)),
                  lib.events.DisconnectEvent()]
    lib.ends_by_itself = True  # the websocket dropped: no disconnect() call needed
    connector, messages, _ = make(lib)
    run(connector.session())
    assert [(m.event_type, m.text, m.id) for m in messages] == [("follow", "", "follow:900"),
                                                                ("subscription", "", "subscription:901")]


def test_handler_errors_never_reach_the_library():
    lib = fake_module()
    connector, _, _ = make(lib)

    def boom(msg):
        raise RuntimeError("consumer failed")

    connector._on_message = boom
    connector._guard(connector._on_comment)(comment(lib))  # must not raise
    connector._guard(connector._on_gift)(object())  # odd payload: must not raise


def test_offline_waits_for_the_next_live():
    lib = fake_module(live=False)
    connector, _, states = make(lib, sleep=_stop_sleep)
    supervise(connector)
    assert states[-1][:2] == ("waiting", "not-live")
    assert lib.clients[0].start_kwargs is None and lib.clients[0].web.closed == 1


def test_live_end_goes_back_to_waiting():
    lib = fake_module()
    lib.script = [comment(lib), lib.events.LiveEndEvent()]
    connector, messages, states = make(lib, sleep=_stop_sleep)
    supervise(connector)
    assert len(messages) == 1 and states[-1][0] == "waiting"


def test_user_offline_error_from_start_is_not_live():
    lib = fake_module(start_error=UserOfflineError("TikTokLive v7.0.1 -> offline"))
    connector, _, _ = make(lib)
    with pytest.raises(NotLive):
        run(connector.session())


def test_user_not_found_and_age_restricted_stop_the_source():
    lib = fake_module(is_live_error=UserNotFoundError("nope"))
    connector, _, states = make(lib, sleep=_stop_sleep)
    supervise(connector)
    assert states[-1][:2] == ("error", "not-found")
    lib = fake_module(start_error=AgeRestrictedError())
    connector, _, states = make(lib, sleep=_stop_sleep)
    supervise(connector)
    assert states[-1][:2] == ("error", "age-restricted")


def test_rate_limit_waits_what_euler_stream_asked():
    lib = fake_module(start_error=SignatureRateLimitError("slow down", retry_after=120))
    connector, _, _ = make(lib)
    with pytest.raises(RateLimited) as info:
        run(connector.session())
    assert info.value.retry_after == 120
    lib = fake_module(start_error=SignatureRateLimitError("slow down"))  # no header: five minutes
    connector, _, states = make(lib, sleep=_stop_sleep)
    supervise(connector)
    assert states[-1][:2] == ("reconnecting", "rate-limited") and connector.status.retry_in == 300


def test_sign_errors_blocks_and_task_failures_are_transient():
    for error, code in ((SignAPIError("[SIGN_NOT_200] boom"), "sign-server"),
                        (WebcastBlockedError("blocked"), "blocked"), (TikTokLiveError("captcha"), "network"),
                        (ConnectionResetError("reset"), "network")):
        lib = fake_module(start_error=error)
        connector, _, _ = make(lib)
        with pytest.raises(TransientError) as info:
            run(connector.session())
        assert info.value.code == code
    lib = fake_module()
    lib.script = [comment(lib), WebcastBlockedError("dropped")]  # the websocket task itself fails
    connector, messages, _ = make(lib)
    with pytest.raises(TransientError):
        run(connector.session())
    assert len(messages) == 1 and lib.clients[0].web.closed == 1


def test_missing_library_is_unsupported(monkeypatch):
    def missing(name):
        raise ImportError(f"No module named {name!r}")

    monkeypatch.setattr(tiktok, "_import", missing)
    connector, _, states = make(None, sleep=_stop_sleep)  # no fake: the real import is attempted
    supervise(connector)
    assert states[-1][:2] == ("unsupported", "missing-dependency")
    assert "chattoon extras install tiktok" in states[-1][2]
    result = run(connector.probe())
    assert (result.ok, result.code) == (False, "unsupported") and "extras install tiktok" in result.detail
    with pytest.raises(Unsupported):
        tiktok.load_library()


def test_close_never_raises():
    lib = fake_module(disconnect_error=True, web_close_error=True)
    connector, _, _ = make(lib)
    connector._client = lib.TikTokLiveClient("@ana")
    run(connector.close())
    assert connector._client is None and lib.clients[0].web.closed == 1
    run(connector.close())  # nothing to close: fine
    lib = fake_module(disconnect_error=True)
    lib.script = [lib.events.LiveEndEvent()]
    connector, _, _ = make(lib)
    run(connector.session())  # a failing disconnect does not turn a normal end into an error


def test_cancelling_a_session_disconnects():
    lib = fake_module()

    async def go():
        connector, _, _ = make(lib)
        task = asyncio.ensure_future(connector.session())
        for _ in range(5):
            await asyncio.sleep(0)
        assert connector.status.state == "connected"
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    run(go())
    assert lib.clients[0].disconnects == 1 and lib.clients[0].web.closed == 1


def test_euler_key_is_applied_but_never_shown():
    lib = fake_module(start_error=SignAPIError(f"rejected X-Api-Key {KEY}"))
    store = Store({"tiktok/sign": {"api_key": KEY}})
    connector, _, states = make(lib, credentials=store, sleep=_stop_sleep)
    supervise(connector)
    assert lib.clients[0].web_kwargs == {"signer_kwargs": {"sign_api_key": KEY}}
    assert states[-1][:2] == ("reconnecting", "sign-server")
    assert all(KEY not in detail for _, _, detail in states) and "***" in states[-1][2]
    assert KEY not in repr(connector.status.to_dict())


def test_broken_keyring_means_no_key():
    class Broken:
        def get(self, key):
            raise OSError("keyring locked")

    lib = fake_module(live=False)
    connector, _, _ = make(lib, credentials=Broken())
    with pytest.raises(NotLive):
        run(connector.session())
    assert lib.clients[0].web_kwargs is None


def test_probe_paths():
    lib = fake_module()
    connector, _, _ = make(lib)
    result = run(connector.probe())
    assert (result.ok, result.code, result.channel) == (True, "live", "@ana.live")
    assert lib.clients[-1].web.closed == 1 and lib.clients[-1].start_kwargs is None  # never connects
    lib.live = False
    assert run(connector.probe()).code == "offline"
    for error, code in ((UserOfflineError(), "offline"), (UserNotFoundError("x"), "not-found"),
                        (AgeRestrictedError(), "age-restricted"),
                        (SignatureRateLimitError("slow", retry_after=10), "rate-limited"),
                        (TikTokLiveError("captcha"), "network"), (OSError("down"), "network")):
        lib.is_live_error = error
        result = run(connector.probe())
        assert (result.ok, result.code) == (False, code)


def test_unknown_event_classes_are_skipped():
    lib = fake_module()
    del lib.events.SubNotifyEvent  # an older/newer library without this event
    lib.script = [comment(lib), lib.events.LiveEndEvent()]
    connector, messages, _ = make(lib)
    run(connector.session())
    assert len(messages) == 1


# -- the real library (only when installed; never touches the network) -------------------

@pytest.mark.skipif(importlib.util.find_spec("TikTokLive") is None, reason="TikTokLive is not installed")
def test_real_library_shapes():
    import dataclasses

    from TikTokLive.proto.custom_proto import ExtendedGift, ExtendedUser
    from TikTokLiveProto.v3.webcast.model.data import UserIdentity
    from TikTokLiveProto.v3.webcast.shared.message import CommonMessageData

    lib = tiktok.load_library()
    for name in tiktok._ERRORS:
        assert isinstance(getattr(lib, name), type), name
    assert issubclass(lib.SignatureRateLimitError, lib.SignAPIError)
    for name in ("ConnectEvent", "DisconnectEvent", "LiveEndEvent", "CommentEvent", "GiftEvent", "FollowEvent",
                 "SubNotifyEvent"):
        assert isinstance(getattr(lib.events, name), type), name
    client_cls = lib.TikTokLiveClient
    start = inspect.signature(client_cls.start).parameters
    assert {"process_connect_events", "fetch_live_check", "fetch_gift_info"} <= set(start)
    assert "web_kwargs" in inspect.signature(client_cls.__init__).parameters
    for name in ("is_live", "start", "disconnect", "add_listener", "web"):
        assert hasattr(client_cls, name), name
    assert {"msg_id", "create_time"} <= {f.name for f in dataclasses.fields(CommonMessageData)}
    assert {"is_moderator_of_anchor", "is_subscriber_of_anchor", "is_anchor"} <= {
        f.name for f in dataclasses.fields(UserIdentity)}
    assert isinstance(lib.events.GiftEvent.streaking, property)

    # adapter against real event objects
    connector, messages, _ = make(lib)
    event = lib.events.CommentEvent(
        content="olá", common=CommonMessageData(msg_id=42, create_time=1_760_000_000_000),
        user=ExtendedUser(id=9, nickname="Bia", display_id="bia"),
        user_identity=UserIdentity(is_moderator_of_anchor=True, is_subscriber_of_anchor=True))
    connector._on_comment(event)
    assert (messages[0].id, messages[0].author, messages[0].author_id, messages[0].text) == ("42", "Bia", "9", "olá")
    assert messages[0].is_moderator and messages[0].is_member and not messages[0].is_owner
    rose = ExtendedGift(name="Rose", type=1, diamond_count=1)
    connector._on_gift(lib.events.GiftEvent(gift=rose, repeat_count=3, repeat_end=0,
                                            common=CommonMessageData(msg_id=43)))
    connector._on_gift(lib.events.GiftEvent(gift=rose, repeat_count=4, repeat_end=1, user=ExtendedUser(id=9),
                                            common=CommonMessageData(msg_id=44)))
    assert [m.superchat for m in messages[1:]] == ["Rose ×4"]

    # per-client sign key and TLS verification on the Euler Stream client (no request is made)
    async def build():
        client = connector._new_client(lib, KEY)
        sdk = client.web.signer.sdk_client
        try:
            assert client.web.signer.sign_api_key == KEY and sdk._verify_ssl is True
        finally:
            await connector._shutdown(client)

    run(build())
