"""Conversation memory: who said what, so the avatar can follow up like a real co-host.

Three layers, cheapest first:

A. **Immediate** — the latest exchanges of the whole live (message + the line the avatar
   really spoke), in RAM. Gives the flow of the conversation and the "do not repeat
   yourself" list.
B. **Per viewer** — each viewer's own exchanges, the things they told about themselves
   ("I'm writing an app in Python"), and what they wrote recently even when it was not
   answered. Identity is ``platform:source:author id``: two "Rafael" on two platforms, or
   two viewers with the same name, never share memories.
C. **Long term** (optional, off by default) — the delivered exchanges and notes in a
   local SQLite database with full-text search (FTS5), kept for a configurable number of
   days, so a viewer who returns to the next live is remembered.

Only what was really said is kept: a suggestion that was never spoken, a reply cut by
the streamer and messages deleted by moderators are not memories. Instructions aimed at
the avatar ("save this as a rule") are never stored. E-mails, phone numbers, documents
and links are redacted, and sensitive subjects (health, religion, politics, passwords…)
stay in RAM for the current live only. Nothing here is sent anywhere.

Retrieval sends only a few relevant lines to the model, never the whole history: the
viewer's latest exchanges, older ones that share words with the new message, and their
notes, each with its age so old facts are not taken as current.
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from pathlib import Path

from .intent import fold
from .messages import ChatMessage, clean_text

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1
# platforms whose messages are typed by the streamer: remembered in RAM, never saved
LOCAL_PLATFORMS = ("demo", "manual", "test", "")

_STOP = frozenset("""
a o e os as um uma uns umas de do da dos das no na nos nas em por para pra pro com sem que se ja nao sim eu tu ele ela
voce vc voces nos eles elas me te lhe meu minha meus minhas seu sua seus suas teu tua isso esse essa este esta aquilo
aquele aquela ai la aqui ta to tou estou esta estao era foi ser sou e eh tem ter tenho mais menos muito muita bem mal
mas ou porque pq quando onde como qual quais quem quanto oi ola hoje agora entao tambem ate ne la so bom boa dia noite
tarde tux minhoca gata coruja cachorro et lembra lembrar lembro sabe acha voce? kkk kkkk haha rs the an and or of to in
on for with is are was were be been i you he she it we they my your his her its our their this that what which who
""".split())
_SYNONYMS = {"app": "aplic", "aplicativo": "aplic", "programa": "aplic", "software": "aplic", "projeto": "aplic",
             "pc": "comput", "computador": "comput", "notebook": "comput", "maquina": "comput", "laptop": "comput",
             "gato": "gat", "gata": "gat", "gatinho": "gat", "cachorro": "cachorr", "cachorra": "cachorr",
             "cao": "cachorr", "dog": "cachorr", "niver": "aniver", "aniversario": "aniver", "birthday": "aniver"}

# what is never written to disk (kept only for the current live, in RAM)
_SENSITIVE = re.compile(
    # whole words…
    r"\b(senha|password|cpf|rg|cnpj|endereco|address|hiv|aids|gay|lesbica|trans|sexo|sexual|pix|token|deus|igreja|"
    r"partido|lula|salario|divida|remedio|hospital|cancer|gravida)\b"
    # …and stems ("depressão", "religioso", "eleições", "diagnóstico")
    r"|\b(depress|ansiedad|ansios|diagnost|medicament|doenc|religi|eleic|elei[cç]|bolsonar|bissexu|homossexu|"
    r"cartao de credito|credit card|chave pix)")
_REDACT = (
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[e-mail]"),
    (re.compile(r"https?://\S+|www\.\S+"), "[link]"),
    (re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"), "[documento]"),
    (re.compile(r"\b(?:\d[ -]?){13,19}\b"), "[número]"),
    (re.compile(r"(?<!\w)\+?\(?\d{2,3}\)?[\s.-]?\d{4,5}[\s.-]?\d{4}\b"), "[telefone]"),
)
# first-person statements worth remembering ("estou desenvolvendo…", "meu gato se chama…")
_DISCLOSURE = re.compile(
    r"^(?:\W*(?:tux|minhoca|gata|coruja|cachorro|e\.?t\.?)\W+)?(?:hoje\s+)?(?:eu\s+)?"
    r"(?:estou|to|tou|tô|tenho|tive|moro|trabalho|estudo|uso|comprei|ganhei|consegui|terminei|instalei|fiz|sou|"
    r"vou|acabei|comecei|montei|troquei|meu|minha|meus|minhas|me chamo|faco|desenvolvo|programo|jogo|gosto|"
    r"hoje e meu|hoje e o meu|hoje e minha|i am|i'm|im|i have|i've|i live|i work|i study|i use|i bought|i got|"
    r"i finished|i installed|my|i'll|i will)\b")


def redact(text: str) -> str:
    for pattern, repl in _REDACT:
        text = pattern.sub(repl, text)
    return text


def sensitive(text: str) -> bool:
    return bool(_SENSITIVE.search(fold(text)))


def keywords(text: str) -> set[str]:
    """Content words, accent-folded and cut to a 5-letter stem ("desenvolvendo" ≈ "desenvolvimento")."""
    out = set()
    for word in re.findall(r"[a-z0-9+#]{2,}", fold(text)):
        if word in _STOP or word.isdigit() and len(word) < 3:
            continue
        if word in _SYNONYMS:
            out.add(_SYNONYMS[word])
        elif len(word) >= 3:
            out.add(word[:5] if len(word) > 5 else word.rstrip("s") or word)
    return out


def disclosures(text: str) -> list[str]:
    """Sentences where the viewer tells something about themselves."""
    out = []
    for sentence in re.split(r"(?<=[.!?;])\s+|\n+", text or ""):
        s = sentence.strip()
        if 6 <= len(s) <= 200 and "?" not in s and _DISCLOSURE.search(fold(s)):
            out.append(clean_text(s, 160))
    return out


def ago(seconds: float, pt: bool) -> str:
    """'há 5 min', 'ontem', 'há 3 dias' — memories always carry their age."""
    s = max(0.0, seconds)
    if s < 90:
        return "agora há pouco" if pt else "just now"
    if s < 3600:
        n = round(s / 60)
        return f"há {n} min" if pt else f"{n} min ago"
    if s < 86400:
        n = round(s / 3600)
        return (f"há {n} hora" + ("s" if n > 1 else "")) if pt else f"{n} hour{'s' if n > 1 else ''} ago"
    n = round(s / 86400)
    if n == 1:
        return "ontem" if pt else "yesterday"
    return f"há {n} dias" if pt else f"{n} days ago"


@dataclass
class Exchange:
    key: str  # viewer identity (ChatMessage.key)
    author: str
    platform: str
    source_id: str
    message_id: str
    author_ref: str  # author id (or folded name) inside the source: moderators remove by it
    message: str
    reply: str = ""  # what the avatar really said ("" = heard, not answered)
    emotion: str = ""
    at: float = field(default_factory=time.time)
    id: int = 0  # row id when saved
    saved: bool = False

    def to_dict(self) -> dict:
        return {"key": self.key, "author": self.author, "platform": self.platform, "sourceId": self.source_id,
                "message": self.message, "reply": self.reply, "emotion": self.emotion, "at": self.at,
                "saved": self.saved}


@dataclass
class Note:
    key: str
    author: str
    text: str
    at: float
    source_id: str = ""
    message_id: str = ""
    author_ref: str = ""
    kind: str = "said"  # said (the viewer's own words) | summary


@dataclass
class Recall:
    """What the memory found for one message (goes into the prompt and the interface)."""

    about: list[str] = field(default_factory=list)  # this viewer
    recent: list[str] = field(default_factory=list)  # the live around it
    used: int = 0  # how many memories reached the prompt
    known: bool = False  # the viewer talked to the avatar before
    returning: bool = False  # …in an earlier live (long-term memory)
    facts: list[str] = field(default_factory=list)  # the viewer's own words most related to the new message

    def text(self, author: str, platform_label: str, pt: bool) -> str:
        blocks = []
        if self.about:
            who = f"{author} ({platform_label})" if platform_label else author
            head = (f"O que você sabe de {who} — use só se ajudar a responder; pode estar desatualizado; "
                    "não repita isso mecanicamente:" if pt else
                    f"What you know about {who} — use only if it helps; it may be outdated; do not recite it:")
            blocks.append(head + "\n" + "\n".join(f"- {line}" for line in self.about))
        if self.recent:
            head = "Conversa recente na live (outras pessoas):" if pt else "Recent conversation (other viewers):"
            blocks.append(head + "\n" + "\n".join(f"- {line}" for line in self.recent))
        return "\n\n".join(blocks)


@dataclass
class _Viewer:
    key: str
    author: str
    platform: str
    exchanges: deque = field(default_factory=lambda: deque(maxlen=20))  # older ones live on disk (if saved)
    heard: deque = field(default_factory=lambda: deque(maxlen=6))  # (time, text, message_id) not answered (yet)
    notes: list[Note] = field(default_factory=list)
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    since_summary: int = 0


class Memory:
    """All three layers. Not thread-safe by itself: the engine uses it from its loop; the
    database is additionally guarded by a lock for the interface's read-only queries."""

    def __init__(self, path: Path | None = None, persist: bool = False, retention_days: int = 30,
                 enabled: bool = True, clock=time.time):
        self.path = path
        self.enabled = enabled
        self.persist = persist
        self.retention_days = retention_days
        self.clock = clock
        self.immediate: deque[Exchange] = deque(maxlen=40)
        self.viewers: OrderedDict[str, _Viewer] = OrderedDict()
        self._db: sqlite3.Connection | None = None
        self._fts = False
        self._lock = threading.RLock()
        self._last_purge = 0.0
        self.max_viewers = 2000  # least recently seen viewers leave RAM first (bounded for long lives)

    # -- configuration ---------------------------------------------------------

    def configure(self, enabled: bool, persist: bool, retention_days: int) -> None:
        self.enabled, self.retention_days = enabled, max(0, int(retention_days))
        if persist != self.persist:
            self.persist = persist
            if not persist:
                self.close()
        if self.persist:
            self._open()
            self.purge()

    def _open(self) -> sqlite3.Connection | None:
        if self._db is not None or not self.persist or self.path is None:
            return self._db
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fresh = not self.path.exists()
            db = sqlite3.connect(self.path, check_same_thread=False, timeout=2)
            if fresh:
                os.chmod(self.path, 0o600)  # public chat, but still nobody else's business
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=NORMAL")
            db.execute("PRAGMA foreign_keys=ON")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
                CREATE TABLE IF NOT EXISTS exchanges(
                    id INTEGER PRIMARY KEY, key TEXT NOT NULL, author TEXT NOT NULL, platform TEXT NOT NULL,
                    source_id TEXT NOT NULL, author_ref TEXT NOT NULL, message_id TEXT NOT NULL,
                    message TEXT NOT NULL, reply TEXT NOT NULL, emotion TEXT NOT NULL, at REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS exchanges_key ON exchanges(key, at);
                CREATE INDEX IF NOT EXISTS exchanges_at ON exchanges(at);
                CREATE INDEX IF NOT EXISTS exchanges_msg ON exchanges(source_id, message_id);
                CREATE TABLE IF NOT EXISTS notes(
                    id INTEGER PRIMARY KEY, key TEXT NOT NULL, author TEXT NOT NULL, text TEXT NOT NULL,
                    kind TEXT NOT NULL, source_id TEXT NOT NULL, author_ref TEXT NOT NULL,
                    message_id TEXT NOT NULL, at REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS notes_key ON notes(key, at);
            """)
            try:
                db.executescript("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS exchanges_fts USING fts5(
                        message, reply, content='exchanges', content_rowid='id',
                        tokenize='unicode61 remove_diacritics 2');
                    CREATE TRIGGER IF NOT EXISTS exchanges_ai AFTER INSERT ON exchanges BEGIN
                        INSERT INTO exchanges_fts(rowid, message, reply) VALUES (new.id, new.message, new.reply);
                    END;
                    CREATE TRIGGER IF NOT EXISTS exchanges_ad AFTER DELETE ON exchanges BEGIN
                        INSERT INTO exchanges_fts(exchanges_fts, rowid, message, reply)
                        VALUES ('delete', old.id, old.message, old.reply);
                    END;
                """)
                self._fts = True
            except sqlite3.OperationalError:  # SQLite built without FTS5: plain LIKE search
                self._fts = False
            db.execute("INSERT OR REPLACE INTO meta(k, v) VALUES ('schema', ?)", (str(SCHEMA_VERSION),))
            db.commit()
            self._db = db
        except (sqlite3.Error, OSError) as e:
            log.warning("memory database unavailable: %s", e)
            self._db = None
        return self._db

    def close(self) -> None:
        with self._lock:
            if self._db is not None:
                try:
                    self._db.close()
                except sqlite3.Error:
                    pass
                self._db = None

    # -- writing ---------------------------------------------------------------------

    def _viewer(self, msg: ChatMessage) -> _Viewer:
        v = self.viewers.get(msg.key)
        if v is None:
            v = _Viewer(msg.key, msg.author, msg.platform, first_seen=self.clock())
            self.viewers[msg.key] = v
            if len(self.viewers) > self.max_viewers:
                self.viewers.popitem(last=False)
        else:
            self.viewers.move_to_end(msg.key)
        v.author, v.last_seen = msg.author, self.clock()
        return v

    @staticmethod
    def _ref(msg: ChatMessage) -> str:
        return msg.author_id or msg.author.casefold()

    def heard(self, msg: ChatMessage, remember: bool = True) -> None:
        """A message arrived (answered or not): kept in RAM for this live only."""
        if not self.enabled or not remember or not msg.text.strip():
            return
        v = self._viewer(msg)
        v.heard.append((self.clock(), redact(clean_text(msg.text, 200)), msg.id))

    def record(self, msg: ChatMessage, reply: str, emotion: str = "", remember: bool = True) -> Exchange | None:
        """The avatar SPOKE ``reply`` to ``msg``: the only way something becomes a memory."""
        if msg is None:
            return None
        text = redact(clean_text(msg.text, 300))
        exchange = Exchange(msg.key, msg.author, msg.platform, msg.source_id, msg.id, self._ref(msg),
                            text if remember else "", redact(clean_text(reply, 400)), emotion, self.clock())
        self.immediate.append(exchange)
        if not self.enabled or not remember:
            return exchange
        v = self._viewer(msg)
        v.heard = deque(((t, h, i) for t, h, i in v.heard if i != msg.id), maxlen=v.heard.maxlen)
        v.exchanges.append(exchange)
        v.since_summary += 1
        new_notes = [Note(msg.key, msg.author, n, exchange.at, msg.source_id, msg.id, exchange.author_ref)
                     for n in disclosures(text)]
        v.notes.extend(new_notes)
        del v.notes[:-12]
        keep = msg.platform not in LOCAL_PLATFORMS and not sensitive(msg.text) and not sensitive(reply)
        if keep and self.persist:
            self._save(exchange, new_notes)
        return exchange

    def said(self, text: str, emotion: str = "") -> None:
        """A line the avatar said on its own (spontaneous, typed by the streamer): it only
        joins the "do not repeat yourself" list, it is nobody's memory."""
        if text.strip():
            self.immediate.append(Exchange("", "", "", "", "", "", "", clean_text(text, 400), emotion, self.clock()))

    def _save(self, exchange: Exchange, notes: list[Note]) -> None:
        with self._lock:
            db = self._open()
            if db is None:
                return
            try:
                cur = db.execute(
                    "INSERT INTO exchanges(key, author, platform, source_id, author_ref, message_id, message, reply,"
                    " emotion, at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (exchange.key, exchange.author, exchange.platform, exchange.source_id, exchange.author_ref,
                     exchange.message_id, exchange.message, exchange.reply, exchange.emotion, exchange.at))
                exchange.id, exchange.saved = cur.lastrowid, True
                db.executemany(
                    "INSERT INTO notes(key, author, text, kind, source_id, author_ref, message_id, at)"
                    " VALUES (?,?,?,?,?,?,?,?)",
                    [(n.key, n.author, n.text, n.kind, n.source_id, n.author_ref, n.message_id, n.at) for n in notes])
                db.commit()
            except sqlite3.Error as e:
                log.warning("could not save a memory: %s", e)
        if self.clock() - self._last_purge > 3600:
            self.purge()

    def set_summary(self, key: str, text: str) -> None:
        """Replace a viewer's summary (written by the model while the live is quiet)."""
        v = self.viewers.get(key)
        if v is None or not text.strip():
            return
        text = redact(clean_text(text, 300))
        v.notes = [n for n in v.notes if n.kind != "summary"]
        last = v.exchanges[-1] if v.exchanges else None
        note = Note(key, v.author, text, self.clock(), last.source_id if last else "", "",
                    last.author_ref if last else "", kind="summary")
        v.notes.append(note)
        v.since_summary = 0
        if self.persist and v.platform not in LOCAL_PLATFORMS and not sensitive(text):
            with self._lock:
                db = self._open()
                if db is not None:
                    try:
                        db.execute("DELETE FROM notes WHERE key=? AND kind='summary'", (key,))
                        db.execute("INSERT INTO notes(key, author, text, kind, source_id, author_ref, message_id, at)"
                                   " VALUES (?,?,?,?,?,?,?,?)", (key, v.author, text, "summary", note.source_id,
                                                                 note.author_ref, "", note.at))
                        db.commit()
                    except sqlite3.Error as e:
                        log.warning("could not save a summary: %s", e)

    def needs_summary(self, every: int = 6) -> _Viewer | None:
        """A viewer with enough new exchanges to be worth a fresh summary."""
        for v in reversed(self.viewers.values()):
            if v.since_summary >= every and v.platform not in LOCAL_PLATFORMS:
                return v
        return None

    # -- forgetting ------------------------------------------------------------------

    def forget_message(self, source_id: str, message_id: str) -> None:
        """A moderator deleted this message: it leaves every layer."""
        def keep(e) -> bool:
            return not (e.source_id == source_id and e.message_id == message_id)

        self.immediate = deque(filter(keep, self.immediate), maxlen=self.immediate.maxlen)
        for v in self.viewers.values():
            v.exchanges = deque(filter(keep, v.exchanges), maxlen=v.exchanges.maxlen)
            v.notes = [n for n in v.notes if keep(n)]
            v.heard = deque(((t, h, i) for t, h, i in v.heard if not (i == message_id)), maxlen=v.heard.maxlen)
        self._delete("source_id=? AND message_id=?", (source_id, message_id))

    def forget_author(self, source_id: str, author_ref: str) -> None:
        """A moderator removed every message of a viewer (ban, timeout, purge)."""
        gone = [k for k, v in self.viewers.items()
                if any(e.source_id == source_id and e.author_ref == author_ref for e in v.exchanges)
                or k.startswith(f"{v.platform}:{source_id}:") and k.endswith(f":{author_ref}")]
        for k in gone:
            self.viewers.pop(k, None)
        self.immediate = deque((e for e in self.immediate
                                if not (e.source_id == source_id and e.author_ref == author_ref)),
                               maxlen=self.immediate.maxlen)
        self._delete("source_id=? AND author_ref=?", (source_id, author_ref))

    def forget_viewer(self, key: str) -> None:
        """The streamer erased one viewer (Live chat › Memory)."""
        self.viewers.pop(key, None)
        self.immediate = deque((e for e in self.immediate if e.key != key), maxlen=self.immediate.maxlen)
        self._delete("key=?", (key,))

    def clear(self) -> None:
        """Erase everything: RAM and the database file's contents."""
        self.immediate.clear()
        self.viewers.clear()
        with self._lock:
            db = self._db or (self._open() if self.path and self.path.exists() and self.persist else None)
            if db is not None:
                try:
                    db.execute("DELETE FROM exchanges")
                    db.execute("DELETE FROM notes")
                    if self._fts:
                        db.execute("INSERT INTO exchanges_fts(exchanges_fts) VALUES ('rebuild')")
                    db.commit()
                    db.execute("VACUUM")
                except sqlite3.Error as e:
                    log.warning("could not clear the memory: %s", e)
        if not self.persist and self.path is not None and self.path.exists():
            self.close()
            for suffix in ("", "-wal", "-shm"):
                try:
                    Path(f"{self.path}{suffix}").unlink(missing_ok=True)
                except OSError:
                    pass

    def _delete(self, where: str, args: tuple) -> None:
        with self._lock:
            db = self._db if self._db is not None else (self._open() if self.persist else None)
            if db is None:
                return
            try:
                db.execute(f"DELETE FROM exchanges WHERE {where}", args)  # noqa: S608 - fixed clauses only
                db.execute(f"DELETE FROM notes WHERE {where}", args)  # noqa: S608
                db.commit()
            except sqlite3.Error as e:
                log.warning("could not delete memories: %s", e)

    def purge(self) -> int:
        """Drop what is older than the retention period (0 = keep until erased)."""
        self._last_purge = self.clock()
        if not self.retention_days:
            return 0
        limit = self.clock() - self.retention_days * 86400
        self.immediate = deque((e for e in self.immediate if e.at >= limit), maxlen=self.immediate.maxlen)
        for v in self.viewers.values():
            v.exchanges = deque((e for e in v.exchanges if e.at >= limit), maxlen=v.exchanges.maxlen)
            v.notes = [n for n in v.notes if n.at >= limit]
        with self._lock:
            db = self._db
            if db is None:
                return 0
            try:
                n = db.execute("DELETE FROM exchanges WHERE at < ?", (limit,)).rowcount
                db.execute("DELETE FROM notes WHERE at < ?", (limit,))
                db.commit()
                return n
            except sqlite3.Error:
                return 0

    # -- reading ---------------------------------------------------------------------

    def known(self, msg: ChatMessage) -> bool:
        v = self.viewers.get(msg.key)
        return bool(v and (v.exchanges or v.notes)) or bool(self._stored(msg.key, limit=1))

    def last_replies(self, n: int = 4, msg: ChatMessage | None = None) -> list[str]:
        """The avatar's latest lines (so it does not repeat itself). Lines said to someone
        else with the same name as ``msg``'s author are left out: they would carry that
        person's details into this viewer's reply."""
        name = fold(msg.author) if msg is not None else None
        lines = [e for e in self.immediate if e.reply and not (name is not None and e.key and e.key != msg.key
                                                                  and fold(e.author) == name)]
        return [e.reply for e in lines[-n:]]

    def last_emotions(self, n: int = 3) -> list[str]:
        return [e.emotion for e in list(self.immediate)[-n:] if e.emotion]

    def _stored(self, key: str, limit: int = 30) -> list[Exchange]:
        if not self.persist:
            return []
        with self._lock:
            db = self._open()
            if db is None:
                return []
            try:
                rows = db.execute("SELECT id, key, author, platform, source_id, message_id, author_ref, message,"
                                  " reply, emotion, at FROM exchanges WHERE key=? ORDER BY at DESC LIMIT ?",
                                  (key, limit)).fetchall()
            except sqlite3.Error:
                return []
        return [Exchange(r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10], id=r[0], saved=True)
                for r in rows]

    def _stored_notes(self, key: str, limit: int = 12) -> list[Note]:
        if not self.persist:
            return []
        with self._lock:
            db = self._open()
            if db is None:
                return []
            try:
                rows = db.execute("SELECT key, author, text, at, source_id, message_id, author_ref, kind FROM notes"
                                  " WHERE key=? ORDER BY at DESC LIMIT ?", (key, limit)).fetchall()
            except sqlite3.Error:
                return []
        return [Note(*r) for r in rows]

    def recall(self, msg: ChatMessage, language: str = "pt-BR", recall_intent: bool = False,
               budget: int = 900) -> Recall:
        """The few memories worth sending with ``msg`` (never the whole history)."""
        pt = language.lower().startswith("pt")
        out = Recall()
        if not self.enabled:
            return out
        now = self.clock()
        v = self.viewers.get(msg.key)
        exchanges = list(v.exchanges) if v else []
        notes = list(v.notes) if v else []
        session_ids = {e.id for e in exchanges if e.id}
        stored = [e for e in self._stored(msg.key) if e.id not in session_ids]
        stored_notes = self._stored_notes(msg.key) if not notes else []
        out.returning = bool(stored) and not exchanges
        out.known = bool(exchanges or stored or notes or stored_notes)
        words = keywords(msg.text)

        def relevance(text: str) -> float:
            k = keywords(text)
            return len(words & k) / (1 + len(words)) if words else 0.0

        picked: list[tuple[float, str]] = []  # (time, line)
        # the last two exchanges of this live always come (follow-ups: "and with QML?"), then
        # older ones that share words with the new message, best first
        recent = exchanges[-2:] if exchanges and now - exchanges[-1].at < 7200 else []
        pool = [e for e in exchanges if e not in recent] + stored
        scored = [(relevance(f"{e.message} {e.reply}"), e.at, e) for e in pool]
        chosen = recent + [e for score, _, e in sorted(scored, key=lambda s: s[:2], reverse=True) if score > 0][:3]
        if recall_intent and len(chosen) == len(recent):
            # "do you remember?" without shared words: the latest things they brought up
            chosen += sorted(pool, key=lambda e: e.at, reverse=True)[:2]
        for e in chosen:
            when = ago(now - e.at, pt)
            if pt:
                line = f'{when}, {e.author} disse: "{e.message}"' + (f' — você respondeu: "{e.reply}"' if e.reply else "")
            else:
                line = f'{when}, {e.author} said: "{e.message}"' + (f' — you replied: "{e.reply}"' if e.reply else "")
            picked.append((e.at, line))
        said = {e.message for e in chosen}
        for n in sorted(notes + stored_notes, key=lambda n: n.at, reverse=True)[:6]:
            if n.text in said or any(n.text in e.message for e in chosen):
                continue
            if n.kind == "summary":
                line = (f"resumo de conversas anteriores ({ago(now - n.at, pt)}): {n.text}" if pt
                        else f"summary of earlier talks ({ago(now - n.at, pt)}): {n.text}")
            else:
                line = (f'{ago(now - n.at, pt)}, {n.author} contou: "{n.text}"' if pt
                        else f'{ago(now - n.at, pt)}, {n.author} told you: "{n.text}"')
            picked.append((n.at, line))
        if v:
            for t, text, mid in list(v.heard)[-3:]:
                if mid != msg.id and now - t < 2700 and text not in said:
                    picked.append((t, (f'{ago(now - t, pt)}, {v.author} escreveu (sem resposta sua): "{text}"' if pt
                                       else f'{ago(now - t, pt)}, {v.author} wrote (you did not answer): "{text}"')))
        picked.sort()
        size = 0
        for _, line in reversed(picked):  # newest first within the budget
            line = line.replace("<<<", "‹‹‹").replace(">>>", "›››")
            if size + len(line) > budget:
                break
            out.about.insert(0, line)
            size += len(line)
        # the viewer's own statements closest to the new message (put right next to it in the
        # prompt: small models use what is near the question far better than a list above)
        own = [(relevance(e.message), e.at, e.message) for e in chosen if e.message] + \
              [(relevance(n.text) + 0.2, n.at, n.text) for n in notes + stored_notes if n.kind == "said"]
        related = [t for score, at, t in sorted(own, key=lambda x: x[:2], reverse=True) if score > 0]
        if (recall_intent or not related) and own:
            # "do you remember?": the latest things they told, too (a follow-up like "with Python
            # and QML" shares no word with "the app")
            related += [t for _, at, t in sorted(own, key=lambda x: x[1], reverse=True)
                        if now - at < 7200 and t not in related][:2]
        for text in related:
            if text not in out.facts and len(out.facts) < 3:
                out.facts.append(text.replace("<<<", "‹‹‹").replace(">>>", "›››"))
        # the flow of the live: what the others said a moment ago. Someone else with the same
        # name (another platform, another account) is left out: a small model would mix them up.
        same_name = fold(msg.author)
        for e in [e for e in self.immediate if e.key != msg.key and e.message and fold(e.author) != same_name
                  and now - e.at < 900][-3:]:
            line = (f'{e.author}: "{e.message}" → você: "{e.reply}"' if pt else f'{e.author}: "{e.message}" → you: "{e.reply}"')
            line = line.replace("<<<", "‹‹‹").replace(">>>", "›››")
            if e.message and e.reply and size + len(line) <= budget + 400:
                out.recent.append(line)
                size += len(line)
        out.used = len(out.about)
        return out

    # -- interface queries (read-only) -------------------------------------------------

    def participants(self, limit: int = 200) -> list[dict]:
        rows: dict[str, dict] = {}
        with self._lock:
            db = self._db if self.persist else None
            if db is None and self.persist:
                db = self._open()
            if db is not None:
                try:
                    for key, author, platform, count, last in db.execute(
                            "SELECT key, author, platform, COUNT(*), MAX(at) FROM exchanges GROUP BY key"
                            " ORDER BY MAX(at) DESC LIMIT ?", (limit,)):
                        rows[key] = {"key": key, "author": author, "platform": platform, "exchanges": count,
                                     "last": last, "notes": 0, "saved": True}
                except sqlite3.Error:
                    pass
        for key, v in self.viewers.items():
            row = rows.setdefault(key, {"key": key, "author": v.author, "platform": v.platform, "exchanges": 0,
                                        "last": v.last_seen, "notes": 0, "saved": False})
            session = [e for e in v.exchanges if not e.saved]
            row["exchanges"] += len(session)
            row["notes"] = len(v.notes)
            row["last"] = max(row["last"] or 0, v.last_seen)
            row["author"] = v.author
        return sorted(rows.values(), key=lambda r: r["last"] or 0, reverse=True)[:limit]

    def conversation(self, key: str, limit: int = 100) -> dict:
        v = self.viewers.get(key)
        session = list(v.exchanges) if v else []
        ids = {e.id for e in session if e.id}
        stored = [e for e in self._stored(key, limit) if e.id not in ids]
        exchanges = sorted(stored + session, key=lambda e: e.at)[-limit:]
        notes = (list(v.notes) if v else []) or self._stored_notes(key)
        return {"key": key, "exchanges": [e.to_dict() for e in exchanges],
                "notes": [{"text": n.text, "at": n.at, "kind": n.kind} for n in notes]}

    def search(self, query: str, limit: int = 60) -> list[dict]:
        words = [w for w in re.findall(r"\w+", fold(query)) if len(w) >= 2][:8]
        if not words:
            return []
        found: dict[tuple, dict] = {}
        for e in self.immediate:
            hay = fold(f"{e.author} {e.message} {e.reply}")
            if all(w in hay for w in words):
                found[(e.key, e.at)] = e.to_dict()
        for v in self.viewers.values():
            for e in v.exchanges:
                hay = fold(f"{e.author} {e.message} {e.reply}")
                if all(w in hay for w in words):
                    found[(e.key, e.at)] = e.to_dict()
        with self._lock:
            db = self._open() if self.persist else None
            if db is not None:
                try:
                    if self._fts:
                        match = " ".join(f'"{w}"*' for w in words)
                        rows = db.execute(
                            "SELECT e.key, e.author, e.platform, e.source_id, e.message, e.reply, e.emotion, e.at"
                            " FROM exchanges_fts f JOIN exchanges e ON e.id = f.rowid WHERE exchanges_fts MATCH ?"
                            " ORDER BY e.at DESC LIMIT ?", (match, limit)).fetchall()
                        rows += db.execute(
                            "SELECT key, author, platform, source_id, message, reply, emotion, at FROM exchanges"
                            " WHERE author LIKE ? ORDER BY at DESC LIMIT ?", (f"%{query.strip()}%", limit)).fetchall()
                    else:
                        like = f"%{query.strip()}%"
                        rows = db.execute(
                            "SELECT key, author, platform, source_id, message, reply, emotion, at FROM exchanges"
                            " WHERE message LIKE ? OR reply LIKE ? OR author LIKE ? ORDER BY at DESC LIMIT ?",
                            (like, like, like, limit)).fetchall()
                except sqlite3.Error:
                    rows = []
                for key, author, platform, source_id, message, reply, emotion, at in rows:
                    found[(key, at)] = {"key": key, "author": author, "platform": platform, "sourceId": source_id,
                                        "message": message, "reply": reply, "emotion": emotion, "at": at,
                                        "saved": True}
        return sorted(found.values(), key=lambda r: r["at"], reverse=True)[:limit]

    def stats(self) -> dict:
        saved = 0
        size = 0
        with self._lock:
            db = self._db
            if db is not None:
                try:
                    saved = db.execute("SELECT COUNT(*) FROM exchanges").fetchone()[0]
                except sqlite3.Error:
                    pass
        if self.path is not None and self.path.exists():
            size = sum(Path(f"{self.path}{s}").stat().st_size for s in ("", "-wal") if Path(f"{self.path}{s}").exists())
        return {"viewers": len(self.viewers), "session": sum(len(v.exchanges) for v in self.viewers.values()),
                "saved": saved, "bytes": size, "persist": self.persist, "enabled": self.enabled,
                "fts": self._fts, "retention": self.retention_days}
