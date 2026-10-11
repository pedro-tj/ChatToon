import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."

Page {
    id: page
    readonly property var cfg: backend.config
    readonly property var rt: backend.runtimeState
    property string urlError: ""

    title: qsTr("YouTube chat")
    subtitle: qsTr("Paste the link of your live stream. ChatToon reads the chat like the pop-out window does — no login needed.")

    Section {
        title: qsTr("Live stream")
        iconName: "chat"
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            AppTextField {
                id: url
                Layout.fillWidth: true
                iconName: "chat"
                text: cfg.chat.url
                placeholderText: "https://www.youtube.com/live/…"
                onTextChanged: page.urlError = backend.validateUrl(text)
                onEditingFinished: if (!page.urlError) backend.setConfig("chat.url", text)
                Accessible.name: qsTr("Live stream URL")
            }
            AppButton { iconName: "external"; tip: qsTr("Open in the browser"); enabled: url.text !== "" && !page.urlError; onClicked: backend.openUrl(url.text) }
        }
        Text { visible: page.urlError !== ""; text: page.urlError; color: Theme.danger; font.pixelSize: 12 }
        Text {
            Layout.fillWidth: true
            text: qsTr("Accepted: watch?v=…, /live/…, youtu.be/…, live_chat?v=… and the pop-out chat link.")
            color: Theme.textFaint; font.pixelSize: 11; wrapMode: Text.WordWrap
        }
        RowLayout {
            spacing: 8
            Rectangle { width: 8; height: 8; radius: 4; color: rt.chat === "connected" ? Theme.success : rt.chat === "error" ? Theme.danger : Theme.textFaint }
            Text {
                Layout.fillWidth: true
                text: (rt.chat === "connected" ? qsTr("Connected to the chat") : rt.chat === "error" ? qsTr("Chat unavailable")
                       : rt.chat === "reconnecting" ? qsTr("Reconnecting…") : rt.chat === "ended" ? qsTr("The live chat ended")
                       : qsTr("Connects when you press Start in Assisted or Automatic mode")) + (rt.chatDetail ? " — " + rt.chatDetail : "")
                color: Theme.textMuted; font.pixelSize: 12; wrapMode: Text.WordWrap
            }
        }
    }

    Section {
        title: qsTr("Which messages to answer")
        iconName: "users"
        description: qsTr("Busy chats send more than any avatar can answer. Choose how ChatToon picks.")
        AppCombo {
            Layout.preferredWidth: 360
            textRole: "t"; valueRole: "v"
            model: [
                { v: "smart", t: qsTr("Smart — mentions, questions and paid messages first") },
                { v: "all", t: qsTr("All — in arrival order, within the limits") },
                { v: "mentions", t: qsTr("Mentions — only when the avatar is called") },
                { v: "questions", t: qsTr("Questions first") },
                { v: "moderators", t: qsTr("Moderators first") },
                { v: "members", t: qsTr("Members first") },
                { v: "random", t: qsTr("Random") },
                { v: "manual", t: qsTr("Manual — you choose each message") },
            ]
            currentIndex: Math.max(0, indexOfValue(cfg.chat.selection))
            onActivated: backend.setConfig("chat.selection", currentValue)
        }
        SettingRow {
            label: qsTr("Wait before answering the same person again")
            NumberStepper { value: cfg.chat.user_cooldown; from: 0; to: 900; step: 10; suffix: " s"; onEdited: v => backend.setConfig("chat.user_cooldown", v) }
        }
        SettingRow {
            label: qsTr("Ignore messages older than")
            NumberStepper { value: cfg.chat.message_ttl; from: 15; to: 900; step: 15; suffix: " s"; onEdited: v => backend.setConfig("chat.message_ttl", v) }
        }
        SettingRow {
            label: qsTr("Queue size")
            NumberStepper { value: cfg.chat.max_queue; from: 5; to: 200; step: 5; onEdited: v => backend.setConfig("chat.max_queue", v) }
        }
        SettingRow {
            label: qsTr("Skip messages sent before connecting")
            AppSwitch { checked: cfg.chat.skip_backlog; onToggled: backend.setConfig("chat.skip_backlog", checked) }
        }
        SettingRow {
            label: qsTr("Ignore bot commands (messages starting with !)")
            AppSwitch { checked: cfg.chat.ignore_commands; onToggled: backend.setConfig("chat.ignore_commands", checked) }
        }
        SettingRow {
            label: qsTr("Super Chats jump the queue")
            AppSwitch { checked: cfg.chat.superchat_priority; onToggled: backend.setConfig("chat.superchat_priority", checked) }
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 6
            Text { text: qsTr("Blocked words (comma separated) — messages containing them are ignored"); color: Theme.text; font.pixelSize: 13 }
            AppTextField { Layout.fillWidth: true; text: cfg.chat.blocked_words; onEditingFinished: backend.setConfig("chat.blocked_words", text) }
        }
    }

    Section {
        title: qsTr("Incoming messages")
        iconName: "chat"
        description: qsTr("The latest messages and why some were skipped.")
        Repeater {
            model: backend.messages.slice(0, 14)
            RowLayout {
                required property var modelData
                Layout.fillWidth: true
                spacing: 8
                opacity: modelData.dropped ? 0.55 : 1
                Text {
                    Layout.fillWidth: true
                    text: "<b>" + modelData.author.replace(/</g, "&lt;") + "</b>  " + modelData.text.replace(/</g, "&lt;")
                    textFormat: Text.StyledText; color: Theme.text; font.pixelSize: 13; elide: Text.ElideRight
                }
                Chip { visible: !!modelData.dropped; text: modelData.dropped || ""; tone: Theme.textMuted }
            }
        }
        Text { visible: backend.messages.length === 0; text: qsTr("Nothing yet."); color: Theme.textFaint; font.pixelSize: 12 }
    }
}
