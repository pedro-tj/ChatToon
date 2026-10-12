"""The unified chat feed: every platform's messages in one virtualized list.

Busy multistreams send hundreds of messages a minute, so the feed is a real Qt model
(not a JavaScript array rebuilt on every message): new messages arrive in batches with
one ``beginInsertRows`` each, the list keeps at most ``LIMIT`` rows, and a message's
state ("answering", "answered", "deleted"…) updates one row in place, found in O(1).
The QML ListView only creates delegates for the rows on screen.
"""

from __future__ import annotations

import time

from PySide6.QtCore import (Property, QAbstractListModel, QByteArray, QModelIndex, QObject, QSortFilterProxyModel, Qt,
                            Signal, Slot)

LIMIT = 2000

ROLES = ("uid", "platform", "sourceId", "channel", "author", "text", "time", "event", "moderator", "member", "owner",
         "verified", "paid", "question", "status", "reason", "reply")
_ROLE = {name: Qt.ItemDataRole.UserRole + 1 + i for i, name in enumerate(ROLES)}


def row_from_message(data: dict) -> dict:
    dropped = data.get("dropped") or ""
    return {
        "uid": data.get("id", ""), "platform": data.get("platform", ""), "sourceId": data.get("source_id", ""),
        "channel": data.get("channel", ""), "author": data.get("author", ""), "text": data.get("text", ""),
        "time": float(data.get("receivedAt") or time.time()), "event": data.get("event", "message"),
        "moderator": bool(data.get("moderator")), "member": bool(data.get("member")), "owner": bool(data.get("owner")),
        "verified": bool(data.get("verified")), "paid": data.get("superchat", ""), "question": bool(data.get("question")),
        "status": "dropped" if dropped else "queued", "reason": dropped, "reply": "",
    }


class ChatFeedModel(QAbstractListModel):
    countsChanged = Signal()

    def __init__(self, parent: QObject | None = None, limit: int = LIMIT):
        super().__init__(parent)
        self._rows: list[dict] = []
        self._first = 0  # sequence number of row 0
        self._seq: dict[str, int] = {}  # uid -> sequence number
        self._counts: dict[str, int] = {}
        self.limit = limit

    # -- Qt model -----------------------------------------------------------------

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802, B008
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        row = self._rows[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return row["text"]
        name = ROLES[role - Qt.ItemDataRole.UserRole - 1] if Qt.ItemDataRole.UserRole < role <= _ROLE[ROLES[-1]] else ""
        return row.get(name) if name else None

    def roleNames(self) -> dict:  # noqa: N802
        return {role: QByteArray(name.encode()) for name, role in _ROLE.items()}

    # -- updates --------------------------------------------------------------------

    def append(self, rows: list[dict]) -> None:
        if not rows:
            return
        start = len(self._rows)
        self.beginInsertRows(QModelIndex(), start, start + len(rows) - 1)
        for row in rows:
            self._seq[row["uid"]] = self._first + len(self._rows)
            self._rows.append(row)
            self._counts[row["platform"]] = self._counts.get(row["platform"], 0) + 1
        self.endInsertRows()
        overflow = len(self._rows) - self.limit
        if overflow > 0:
            self.beginRemoveRows(QModelIndex(), 0, overflow - 1)
            for row in self._rows[:overflow]:
                self._seq.pop(row["uid"], None)
                self._counts[row["platform"]] -= 1  # chips count what the list really holds
            del self._rows[:overflow]
            self._first += overflow
            self.endRemoveRows()
        self.countsChanged.emit()

    def update(self, uid: str, **changes) -> bool:
        seq = self._seq.get(uid)
        if seq is None:
            return False
        i = seq - self._first
        row = self._rows[i]
        if all(row.get(k) == v for k, v in changes.items()):
            return True
        row.update(changes)
        index = self.index(i, 0)
        self.dataChanged.emit(index, index, [_ROLE[k] for k in changes if k in _ROLE])
        return True

    def get(self, uid: str) -> dict | None:
        seq = self._seq.get(uid)
        return dict(self._rows[seq - self._first]) if seq is not None else None

    @Slot()
    def clear(self) -> None:
        self.beginResetModel()
        self._rows.clear()
        self._seq.clear()
        self._counts.clear()
        self._first = 0
        self.endResetModel()
        self.countsChanged.emit()

    counts = Property("QVariantMap", lambda self: dict(self._counts), notify=countsChanged)
    total = Property(int, lambda self: len(self._rows), notify=countsChanged)


class ChatFeedFilter(QSortFilterProxyModel):
    """Platform / source / text / skipped filters for the feed (all evaluated in C++ order)."""

    changed = Signal()

    def __init__(self, source: ChatFeedModel, parent: QObject | None = None):
        super().__init__(parent)
        self.setSourceModel(source)
        self._platform = ""
        self._source_id = ""
        self._search = ""
        self._hide_dropped = False

    def filterAcceptsRow(self, row: int, parent: QModelIndex) -> bool:  # noqa: N802
        model: ChatFeedModel = self.sourceModel()
        data = model._rows[row]
        if self._platform and data["platform"] != self._platform:
            return False
        if self._source_id and data["sourceId"] != self._source_id:
            return False
        if self._hide_dropped and data["status"] in ("dropped", "deleted", "skipped"):
            return False
        if self._search:
            haystack = f"{data['author']} {data['text']} {data['reply']}".casefold()
            return all(word in haystack for word in self._search.split())
        return True

    def _setter(name):  # noqa: N805 - property factory
        def setter(self, value) -> None:
            value = value.casefold().strip() if name == "_search" else value
            if getattr(self, name) != value:
                if hasattr(self, "beginFilterChange"):  # Qt 6.9+
                    self.beginFilterChange()
                    setattr(self, name, value)
                    self.endFilterChange(QSortFilterProxyModel.Direction.Rows)
                else:
                    setattr(self, name, value)
                    self.invalidateRowsFilter()
                self.changed.emit()
        return setter

    platform = Property(str, lambda self: self._platform, _setter("_platform"), notify=changed)
    sourceId = Property(str, lambda self: self._source_id, _setter("_source_id"), notify=changed)  # noqa: N815
    search = Property(str, lambda self: self._search, _setter("_search"), notify=changed)
    hideDropped = Property(bool, lambda self: self._hide_dropped, _setter("_hide_dropped"), notify=changed)  # noqa: N815
    del _setter
