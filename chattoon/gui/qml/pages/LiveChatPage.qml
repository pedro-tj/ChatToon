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
    property bool follow: true

    function time(t) { return new Date(t * 1000).toLocaleTimeString(Qt.locale(), "HH:mm:ss") }
    function stateInfo(s) {
        return ({
            queued: { icon: "clock", text: qsTr("In the queue"), tone: Theme.textMuted },
            answering: { icon: "mic", text: qsTr("Answering now"), tone: Theme.accent },
            suggested: { icon: "sparkles", text: qsTr("Suggestion ready"), tone: Theme.accent2 },
            answered: { icon: "check", text: qsTr("Answered"), tone: Theme.success },
            skipped: { icon: "x", text: qsTr("Skipped"), tone: Theme.textMuted },
            failed: { icon: "alert", text: qsTr("Not answered"), tone: Theme.warning },
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

        // ------------------------------------------------------------ list
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
                                color: Theme.accent; font.pixelSize: 13; font.italic: true; wrapMode: Text.Wrap
                            }
                        }
                    }

                    // actions (hover or keyboard focus)
                    Row {
                        anchors { right: parent.right; bottom: parent.bottom; margins: 6 }
                        spacing: 4
                        visible: (hover.hovered || row.ListView.isCurrentItem) && ["queued", "dropped", "failed", "suggested"].indexOf(row.status) >= 0
                        AppButton { compact: true; variant: "primary"; iconName: "play"; text: qsTr("Answer now"); onClicked: backend.approve(row.uid) }
                        AppButton { compact: true; iconName: "x"; tip: qsTr("Skip"); Accessible.name: qsTr("Skip"); visible: row.status !== "dropped"; onClicked: backend.reject(row.uid) }
                    }
                    TapHandler { onTapped: row.ListView.view.currentIndex = row.index }
                    Keys.onReturnPressed: if (["queued", "dropped", "failed", "suggested"].indexOf(status) >= 0) backend.approve(uid)
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
}
