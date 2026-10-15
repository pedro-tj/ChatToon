import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."

// Every platform's chat in one virtualized list. Not a ScrollView page: the ListView
// owns the scrolling, so thousands of messages cost only the rows on screen.
Item {
    id: page
    readonly property var cfg: backend.config
    readonly property var st: backend.stats
    readonly property var feed: backend.feed
    readonly property var counts: backend.feedModel.counts
    readonly property var memView: backend.memoryView
    readonly property var memStats: backend.memory.stats || ({})
    property bool follow: true
    property bool showMemory: false
    onShowMemoryChanged: if (showMemory) backend.refreshMemory()

    function time(t) { return new Date(t * 1000).toLocaleTimeString(Qt.locale(), "HH:mm:ss") }
    function stateInfo(s) {
        return ({
            queued: { icon: "clock", text: qsTr("In the queue"), tone: Theme.textMuted },
            answering: { icon: "mic", text: qsTr("Answering now"), tone: Theme.accent },
            suggested: { icon: "sparkles", text: qsTr("Suggestion ready"), tone: Theme.accent2 },
            answered: { icon: "check", text: qsTr("Answered"), tone: Theme.success },
            skipped: { icon: "x", text: qsTr("Skipped"), tone: Theme.textMuted },
            failed: { icon: "alert", text: qsTr("Not answered"), tone: Theme.warning },
            interrupted: { icon: "stop", text: qsTr("Interrupted"), tone: Theme.warning },
            dropped: { icon: "minus", text: qsTr("Not queued"), tone: Theme.textMuted },
            deleted: { icon: "trash", text: qsTr("Removed by a moderator"), tone: Theme.danger }
        })[s] || { icon: "info", text: s, tone: Theme.textMuted }
    }
    function reasonText(r) {
        return ({
            "empty": qsTr("no words"), "command": qsTr("bot command"), "blocked word": qsTr("blocked word"),
            "duplicate": qsTr("duplicate"), "repeated": qsTr("repeated"), "no mention": qsTr("no mention"),
            "queue full": qsTr("queue full"), "expired": qsTr("too old"), "not running": qsTr("not live"),
            "event": qsTr("event")
        })[r] || r
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 14

        // ------------------------------------------------------------ title
        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: 4
            spacing: 12
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2
                RowLayout {
                    spacing: 10
                    Text { text: qsTr("Live chat"); color: Theme.text; font.pixelSize: 24; font.weight: Font.Bold; Accessible.role: Accessible.Heading }
                    Rectangle {
                        visible: win.running
                        width: liveRow.implicitWidth + 16; height: 22; radius: 11
                        color: Theme.tint(Theme.danger, 0.14)
                        RowLayout {
                            id: liveRow
                            anchors.centerIn: parent
                            spacing: 5
                            Rectangle {
                                width: 7; height: 7; radius: 4; color: Theme.danger
                                SequentialAnimation on opacity {
                                    running: win.running && !cfg.animation.reduce_motion; loops: Animation.Infinite
                                    NumberAnimation { to: 0.3; duration: 700 }
                                    NumberAnimation { to: 1; duration: 700 }
                                }
                            }
                            Text { text: qsTr("LIVE"); color: Theme.danger; font.pixelSize: 11; font.weight: Font.Bold; font.letterSpacing: 1 }
                        }
                    }
                }
                Text {
                    Layout.fillWidth: true
                    text: qsTr("Every platform in one place. Answer a message now or skip it — the avatar still speaks one at a time.")
                    color: Theme.textMuted; font.pixelSize: 13; wrapMode: Text.WordWrap
                }
            }
            AppButton {
                iconName: "arrowDown"
                text: page.follow ? qsTr("Following") : qsTr("Follow new messages")
                variant: page.follow ? "secondary" : "primary"
                onClicked: { page.follow = true; list.positionViewAtEnd() }
            }
            AppButton {
                iconName: "users"
                text: qsTr("Memory")
                variant: page.showMemory ? "primary" : "secondary"
                tip: qsTr("What the avatar remembers about each viewer")
                onClicked: page.showMemory = !page.showMemory
            }
            AppButton { iconName: "trash"; tip: qsTr("Clear the list (the queue is kept)"); Accessible.name: qsTr("Clear the list"); onClicked: backend.clearFeed() }
        }

        // ------------------------------------------------------------ filters
        RowLayout {
            Layout.fillWidth: true
            spacing: 10
            AppTextField {
                id: search
                Layout.preferredWidth: 280
                implicitHeight: 38
                iconName: "search"
                placeholderText: qsTr("Search name or message…")
                onTextChanged: page.feed.search = text
                Accessible.name: qsTr("Search the chat")
            }
            Flow {
                Layout.fillWidth: true
                spacing: 6
                FilterChip { platform: ""; label: qsTr("All"); count: backend.feedModel.total }
                Repeater {
                    model: backend.platforms.filter(p => (page.counts[p.id] || 0) > 0 || backend.sources.some(s => s.platform === p.id))
                    FilterChip {
                        required property var modelData
                        platform: modelData.id
                        label: modelData.label
                        count: page.counts[modelData.id] || 0
                    }
                }
            }
            AppCheck {
                text: qsTr("Hide skipped")
                checked: page.feed.hideDropped
                onToggled: page.feed.hideDropped = checked
            }
        }

        // ------------------------------------------------------------ list (+ memory panel)
        RowLayout {
        Layout.fillWidth: true
        Layout.fillHeight: true
        spacing: 14
        GlassCard {
            Layout.fillWidth: true
            Layout.fillHeight: true

            ListView {
                id: list
                anchors { fill: parent; margins: 6 }
                clip: true
                model: page.feed
                spacing: 2
                reuseItems: true
                boundsBehavior: Flickable.StopAtBounds
                keyNavigationEnabled: true
                activeFocusOnTab: true
                highlightFollowsCurrentItem: false
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                Accessible.role: Accessible.List
                Accessible.name: qsTr("Messages from every platform")

                onCountChanged: if (page.follow) Qt.callLater(positionViewAtEnd)
                onMovementStarted: page.follow = false
                onAtYEndChanged: if (atYEnd && moving) page.follow = true

                delegate: Rectangle {
                    id: row
                    required property int index
                    required property string uid
                    required property string platform
                    required property string author
                    required property string text
                    required property real time
                    required property string event
                    required property bool moderator
                    required property bool member
                    required property bool owner
                    required property bool verified
                    required property string paid
                    required property bool question
                    required property string status
                    required property string reason
                    required property string reply
                    required property int memory
                    readonly property var info: win.platformInfo[platform] || ({ color: Theme.textFaint, label: platform })
                    readonly property var si: page.stateInfo(status)
                    readonly property bool active: status === "answering"
                    readonly property bool faded: status === "dropped" || status === "skipped" || status === "deleted"

                    width: ListView.view.width
                    implicitHeight: col.implicitHeight + 16
                    radius: Theme.radiusSmall
                    color: active ? Theme.tint(Theme.accent, Theme.dark ? 0.16 : 0.1)
                         : hover.hovered || ListView.isCurrentItem ? Theme.hover : "transparent"
                    border.width: active ? 1 : 0
                    border.color: Theme.tint(Theme.accent, 0.5)
                    Accessible.role: Accessible.ListItem
                    Accessible.name: info.label + ", " + author + ": " + text + ". " + si.text

                    HoverHandler { id: hover }

                    Rectangle {  // platform stripe
                        width: 3; radius: 2
                        anchors { left: parent.left; top: parent.top; bottom: parent.bottom; margins: 6 }
                        color: row.info.color
                    }

                    ColumnLayout {
                        id: col
                        anchors { left: parent.left; right: parent.right; top: parent.top; leftMargin: 16; rightMargin: 10; topMargin: 8 }
                        spacing: 3
                        opacity: row.faded ? 0.55 : 1

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 6
                            PlatformBadge { platform: row.platform; size: 18 }
                            Text {
                                text: row.author
                                textFormat: Text.PlainText
                                color: Theme.text; font.pixelSize: 13; font.weight: Font.DemiBold
                                Layout.maximumWidth: row.width * 0.35; elide: Text.ElideRight
                            }
                            Chip { visible: row.owner; text: qsTr("host"); tone: Theme.accent2; implicitHeight: 18 }
                            Chip { visible: row.moderator && !row.owner; text: qsTr("mod"); tone: Theme.accent; implicitHeight: 18 }
                            Chip { visible: row.member; text: qsTr("member"); tone: Theme.success; implicitHeight: 18 }
                            Chip { visible: row.paid !== ""; text: row.paid; iconName: row.event === "gift" ? "gift" : "star"; tone: Theme.warning; implicitHeight: 18 }
                            Chip { visible: row.question; text: "?"; tone: Theme.accent2; implicitHeight: 18 }
                            Item { Layout.fillWidth: true }
                            // state: icon + words, never colour alone
                            RowLayout {
                                spacing: 4
                                visible: row.status !== "queued" || hover.hovered
                                Icon { name: row.si.icon; size: 12; color: row.si.tone }
                                Text {
                                    text: row.si.text + (row.reason ? " · " + page.reasonText(row.reason) : "")
                                    color: row.si.tone; font.pixelSize: 11
                                }
                            }
                            Text { text: page.time(row.time); color: Theme.textFaint; font.family: Theme.mono; font.pixelSize: 11 }
                        }
                        Text {
                            Layout.fillWidth: true
                            visible: text !== ""
                            text: row.text
                            textFormat: Text.PlainText  // viewer text is never interpreted as markup
                            color: Theme.text; font.pixelSize: 14; wrapMode: Text.Wrap
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            visible: row.reply !== ""
                            spacing: 6
                            Icon { name: "quote"; size: 13; color: Theme.accent; Layout.alignment: Qt.AlignTop }
                            Text {
                                Layout.fillWidth: true
                                text: row.reply
                                textFormat: Text.PlainText
                                color: row.status === "interrupted" ? Theme.textMuted : Theme.accent
                                font.pixelSize: 13; font.italic: true; wrapMode: Text.Wrap
                                font.strikeout: row.status === "interrupted"
                            }
                            Chip {
                                visible: row.memory > 0
                                Layout.alignment: Qt.AlignTop
                                text: qsTr("remembered")
                                iconName: "users"; tone: Theme.accent2
                                ToolTip.visible: memHover.hovered
                                ToolTip.text: qsTr("This reply used %1 memory item(s) about this viewer").arg(row.memory)
                                HoverHandler { id: memHover }
                            }
                        }
                    }

                    // actions (hover or keyboard focus)
                    Row {
                        anchors { right: parent.right; bottom: parent.bottom; margins: 6 }
                        spacing: 4
                        visible: (hover.hovered || row.ListView.isCurrentItem) && ["queued", "dropped", "failed", "suggested", "interrupted"].indexOf(row.status) >= 0
                        AppButton { compact: true; variant: "primary"; iconName: "play"; text: qsTr("Answer now"); onClicked: backend.approve(row.uid) }
                        AppButton { compact: true; iconName: "x"; tip: qsTr("Skip"); Accessible.name: qsTr("Skip"); visible: row.status !== "dropped"; onClicked: backend.reject(row.uid) }
                    }
                    TapHandler { onTapped: row.ListView.view.currentIndex = row.index }
                    Keys.onReturnPressed: if (["queued", "dropped", "failed", "suggested", "interrupted"].indexOf(status) >= 0) backend.approve(uid)
                }

            }
            EmptyState {
                anchors.centerIn: parent
                visible: list.count === 0
                iconName: "chat"
                title: backend.feedModel.total ? qsTr("Nothing matches the filter") : qsTr("No messages yet")
                message: backend.feedModel.total ? "" : backend.sources.length === 0
                         ? qsTr("Add your streaming platforms, then press Start in Assisted or Automatic mode.")
                         : win.running ? qsTr("Messages from every connected platform will appear here.")
                         : qsTr("Press Start to connect your platforms.")
                AppButton { visible: backend.sources.length === 0; variant: "primary"; iconName: "plus"; text: qsTr("Add platform"); onClicked: win.go("platforms") }
            }
        }

        MemoryPanel {
            visible: page.showMemory
            Layout.preferredWidth: 380
            Layout.fillHeight: true
        }
        }

        // ------------------------------------------------------------ totals
        RowLayout {
            Layout.fillWidth: true
            spacing: 18
            Repeater {
                model: [
                    { l: qsTr("Received"), v: page.st.received || 0 },
                    { l: qsTr("Replies"), v: page.st.answered || 0 },
                    { l: qsTr("In the queue"), v: (backend.queue.pending || []).length },
                    { l: qsTr("Platforms connected"), v: backend.connectedPlatforms.length },
                ]
                RowLayout {
                    required property var modelData
                    spacing: 6
                    Text { text: modelData.v; color: Theme.text; font.family: Theme.mono; font.pixelSize: 15; font.weight: Font.Bold }
                    Text { text: modelData.l; color: Theme.textFaint; font.pixelSize: 12 }
                }
            }
            Item { Layout.fillWidth: true }
            Text {
                visible: cfg.chat.selection === "manual"
                text: qsTr("Manual mode: only the messages you pick are answered.")
                color: Theme.accent; font.pixelSize: 12
            }
        }
    }

    component FilterChip: Rectangle {
        id: chip
        property string platform
        property string label
        property int count
        readonly property bool selected: page.feed.platform === platform
        implicitHeight: 32
        implicitWidth: chipRow.implicitWidth + 20
        radius: 16
        color: selected ? Theme.tint(Theme.accent, Theme.dark ? 0.22 : 0.14) : chipHover.hovered ? Theme.hover : Theme.field
        border.width: selected || activeFocus ? 2 : 1
        border.color: selected || activeFocus ? Theme.accent : Theme.border
        activeFocusOnTab: true
        Accessible.role: Accessible.RadioButton
        Accessible.name: label + " (" + count + ")"
        Accessible.checked: selected
        Keys.onSpacePressed: page.feed.platform = platform
        RowLayout {
            id: chipRow
            anchors.centerIn: parent
            spacing: 6
            PlatformBadge { visible: chip.platform !== ""; platform: chip.platform; size: 16 }
            Text { text: chip.label; color: chip.selected ? Theme.accent : Theme.text; font.pixelSize: 12; font.weight: chip.selected ? Font.DemiBold : Font.Normal }
            Text { text: chip.count; color: Theme.textFaint; font.family: Theme.mono; font.pixelSize: 11 }
        }
        HoverHandler { id: chipHover; cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: page.feed.platform = chip.platform }
    }

    // ---------------------------------------------------------------- memory panel
    component MemoryPanel: GlassCard {
        id: panel
        function time(t) {
            const d = new Date(t * 1000)
            return d.toDateString() === new Date().toDateString() ? d.toLocaleTimeString(Qt.locale(), "HH:mm")
                                                                   : d.toLocaleDateString(Qt.locale(), Locale.ShortFormat)
        }
        Timer { id: searchDelay; interval: 300; onTriggered: backend.searchMemory(memSearch.text) }

        ColumnLayout {
            anchors { fill: parent; margins: 14 }
            spacing: 10
            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                AppButton {
                    visible: page.memView.mode !== ""
                    compact: true; variant: "ghost"; iconName: "arrowDown"; rotation: 90
                    tip: qsTr("Back to everyone"); Accessible.name: tip
                    onClicked: { memSearch.text = ""; backend.searchMemory("") }
                }
                Text { Layout.fillWidth: true; text: qsTr("Conversation memory"); color: Theme.text; font.pixelSize: 15; font.weight: Font.DemiBold }
                AppButton { compact: true; variant: "ghost"; iconName: "x"; tip: qsTr("Close"); Accessible.name: tip; onClicked: page.showMemory = false }
            }
            Text {
                Layout.fillWidth: true
                text: !(cfg.memory || {}).enabled ? qsTr("Memory is off (AI page).")
                      : qsTr("%1 viewer(s) in this live · %2 saved exchange(s)").arg(page.memStats.viewers || 0).arg(page.memStats.saved || 0)
                      + ((cfg.memory || {}).persist ? "" : " · " + qsTr("not saved between lives"))
                color: Theme.textMuted; font.pixelSize: 12; wrapMode: Text.WordWrap
            }
            AppTextField {
                id: memSearch
                Layout.fillWidth: true
                implicitHeight: 36
                iconName: "search"
                placeholderText: qsTr("Search what was said…")
                onTextChanged: searchDelay.restart()
                Accessible.name: qsTr("Search the memory")
            }

            // one viewer: notes, then the conversation
            ColumnLayout {
                id: viewerBox
                Layout.fillWidth: true
                visible: page.memView.mode === "viewer"
                spacing: 6
                readonly property var who: (backend.memory.participants || []).find(p => p.key === page.memView.key) || ({})
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 6
                    PlatformBadge { platform: viewerBox.who.platform || ""; size: 18; visible: (viewerBox.who.platform || "") !== "" }
                    Text { Layout.fillWidth: true; text: viewerBox.who.author || ""; textFormat: Text.PlainText; color: Theme.text; font.pixelSize: 14; font.weight: Font.DemiBold; elide: Text.ElideRight }
                    AppButton { compact: true; variant: "danger"; iconName: "trash"; text: qsTr("Forget"); onClicked: forgetDialog.open() }
                }
                Flow {
                    Layout.fillWidth: true
                    spacing: 4
                    visible: (page.memView.notes || []).length > 0
                    Repeater {
                        model: page.memView.notes || []
                        Chip {
                            required property var modelData
                            text: modelData.text.length > 60 ? modelData.text.slice(0, 58) + "…" : modelData.text
                            iconName: modelData.kind === "summary" ? "book" : "quote"
                            tone: modelData.kind === "summary" ? Theme.accent : Theme.accent2
                        }
                    }
                }
            }

            ListView {
                id: memList
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                spacing: 4
                reuseItems: true
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                model: page.memView.mode !== "" ? (page.memView.items || []) : (backend.memory.participants || [])
                Accessible.role: Accessible.List
                Accessible.name: qsTr("Remembered viewers")

                delegate: Rectangle {
                    id: item
                    required property var modelData
                    readonly property bool person: page.memView.mode === ""
                    width: ListView.view.width
                    implicitHeight: itemCol.implicitHeight + 14
                    radius: Theme.radiusSmall
                    color: itemHover.hovered ? Theme.hover : "transparent"
                    HoverHandler { id: itemHover; cursorShape: item.person || page.memView.mode === "search" ? Qt.PointingHandCursor : Qt.ArrowCursor }
                    TapHandler { onTapped: if (item.person || page.memView.mode === "search") backend.openConversation(item.modelData.key) }
                    Accessible.role: Accessible.ListItem
                    Accessible.name: item.person ? (modelData.author + ", " + qsTr("%n exchange(s)", "", modelData.exchanges || 0))
                                                 : (modelData.author + ": " + modelData.message)
                    ColumnLayout {
                        id: itemCol
                        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 7 }
                        spacing: 3
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 6
                            PlatformBadge { platform: item.modelData.platform || ""; size: 16; visible: (item.modelData.platform || "") !== "" && (win.platformInfo[item.modelData.platform] !== undefined) }
                            Text { Layout.fillWidth: true; text: item.modelData.author || ""; textFormat: Text.PlainText; color: Theme.text; font.pixelSize: 13; font.weight: Font.DemiBold; elide: Text.ElideRight }
                            Chip { visible: !!item.modelData.saved; text: qsTr("saved"); iconName: "lock"; tone: Theme.textMuted }
                            Text { text: panel.time(item.modelData.at || item.modelData.last || 0); color: Theme.textFaint; font.family: Theme.mono; font.pixelSize: 11 }
                        }
                        Text {
                            Layout.fillWidth: true
                            visible: item.person
                            text: qsTr("%n exchange(s)", "", item.modelData.exchanges || 0) + ((item.modelData.notes || 0) > 0 ? " · " + qsTr("%n note(s)", "", item.modelData.notes) : "")
                            color: Theme.textMuted; font.pixelSize: 12
                        }
                        Text {
                            Layout.fillWidth: true
                            visible: !item.person && (item.modelData.message || "") !== ""
                            text: item.modelData.message || ""
                            textFormat: Text.PlainText; color: Theme.text; font.pixelSize: 13; wrapMode: Text.Wrap
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            visible: !item.person && (item.modelData.reply || "") !== ""
                            spacing: 6
                            Icon { name: "quote"; size: 12; color: Theme.accent; Layout.alignment: Qt.AlignTop }
                            Text { Layout.fillWidth: true; text: item.modelData.reply || ""; textFormat: Text.PlainText; color: Theme.accent; font.pixelSize: 12; font.italic: true; wrapMode: Text.Wrap }
                        }
                    }
                }
                Text {
                    anchors.centerIn: parent
                    width: parent.width - 20
                    visible: memList.count === 0
                    horizontalAlignment: Text.AlignHCenter
                    text: page.memView.mode === "search" ? qsTr("Nothing found.")
                        : qsTr("No memories yet. They appear after the avatar really answers someone.")
                    color: Theme.textFaint; font.pixelSize: 12; wrapMode: Text.WordWrap
                }
            }
            AppButton {
                Layout.fillWidth: true
                compact: true; variant: "danger"; iconName: "trash"; text: qsTr("Erase all memories…")
                onClicked: eraseAll.open()
            }
        }

        Dialog {
            id: forgetDialog
            parent: Overlay.overlay
            anchors.centerIn: parent
            modal: true
            title: qsTr("Forget this viewer?")
            standardButtons: Dialog.Cancel | Dialog.Yes
            onAccepted: backend.forgetViewer(page.memView.key)
            Text { width: 340; text: qsTr("Everything the avatar remembers about this person is erased, in RAM and on disk."); color: Theme.text; wrapMode: Text.WordWrap }
            background: Rectangle { radius: Theme.radius; color: Theme.surfaceStrong; border.width: 1; border.color: Theme.borderStrong }
        }
        Dialog {
            id: eraseAll
            parent: Overlay.overlay
            anchors.centerIn: parent
            modal: true
            title: qsTr("Erase all memories?")
            standardButtons: Dialog.Cancel | Dialog.Yes
            onAccepted: backend.clearMemory()
            Text { width: 360; text: qsTr("The avatar forgets every viewer, in RAM and on disk. This cannot be undone."); color: Theme.text; wrapMode: Text.WordWrap }
            background: Rectangle { radius: Theme.radius; color: Theme.surfaceStrong; border.width: 1; border.color: Theme.borderStrong }
        }
    }
}
