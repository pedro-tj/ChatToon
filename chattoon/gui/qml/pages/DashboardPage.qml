import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."

Page {
    id: page
    readonly property var cfg: backend.config
    readonly property var rt: backend.runtimeState
    readonly property var svc: backend.services
    readonly property var st: backend.stats
    readonly property var current: backend.characters.find(c => c.id === cfg.character) || {}

    title: qsTr("Dashboard")
    subtitle: qsTr("Everything that matters during the live stream, in one place.")

    function chatValue() {
        const map = { connected: qsTr("Connected"), connecting: qsTr("Connecting…"), reconnecting: qsTr("Reconnecting…"),
                      ended: qsTr("Chat ended"), error: qsTr("Unavailable"), stopped: qsTr("Not connected") }
        return cfg.mode === "demo" ? qsTr("Demo mode (no YouTube)") : (map[rt.chat] || qsTr("Not connected"))
    }
    function phaseLabel(p) {
        return { idle: qsTr("Waiting for messages"), listening: qsTr("Paying attention"), reading: qsTr("Reading the message"),
                 thinking: qsTr("Thinking…"), speaking: qsTr("Speaking") }[p] || p
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: 16

        // ---------------------------------------------------------------- preview
        Preview {
            Layout.fillWidth: true
            Layout.preferredWidth: 3
            Layout.preferredHeight: 470
            url: rt.overlayUrl
            Rectangle {
                anchors { left: parent.left; top: parent.top; margins: 14 }
                width: chipRow.implicitWidth + 20; height: 30; radius: 15
                color: Qt.rgba(0, 0, 0, 0.45)
                RowLayout {
                    id: chipRow
                    anchors.centerIn: parent
                    spacing: 8
                    Rectangle { width: 8; height: 8; radius: 4; color: page.current.color || Theme.accent }
                    Text { text: (page.current.name || "") + " · " + page.phaseLabel(rt.phase); color: "white"; font.pixelSize: 12; font.weight: Font.DemiBold }
                }
            }
        }

        // ---------------------------------------------------------------- status
        ColumnLayout {
            Layout.fillWidth: true
            Layout.preferredWidth: 2
            Layout.alignment: Qt.AlignTop
            spacing: 10

            StatusCard {
                iconName: "bot"
                title: qsTr("Ollama (AI)")
                status: svc.ollama.ok === true ? (cfg.ai.model ? "ok" : "warn") : svc.ollama.ok === false ? "error" : "busy"
                value: svc.ollama.ok === false ? qsTr("Not running") : cfg.ai.model || qsTr("Choose a model")
                detail: svc.ollama.ok === false ? svc.ollama.error || "" : qsTr("Version %1").arg(svc.ollama.version || "?")
                onClicked: win.currentPage = 3
            }
            StatusCard {
                iconName: "volume"
                title: qsTr("Voice (TTS BigLinux)")
                status: !cfg.voice.enabled ? "warn" : svc.tts.ok === true ? "ok" : svc.tts.ok === false ? "error" : "busy"
                value: !cfg.voice.enabled ? qsTr("Muted") : svc.tts.ok === false ? qsTr("Unavailable")
                     : cfg.voice.audio_output === "overlay" ? qsTr("Plays in OBS") : qsTr("Plays on this computer")
                detail: svc.tts.ok === false ? svc.tts.error || "" : ""
                onClicked: win.currentPage = 5
            }
            StatusCard {
                iconName: "chat"
                title: qsTr("Live chat")
                status: cfg.mode === "demo" ? "ok" : rt.chat === "connected" ? "ok" : rt.chat === "error" ? "error"
                      : (rt.chat === "connecting" || rt.chat === "reconnecting") ? "busy" : "idle"
                value: page.chatValue()
                detail: rt.chatDetail || ""
                onClicked: win.currentPage = 4
            }
            StatusCard {
                iconName: "broadcast"
                title: qsTr("OBS overlay")
                status: rt.obs > 0 ? "ok" : "idle"
                value: rt.obs > 0 ? qsTr("%n source(s) connected", "", rt.obs) : qsTr("Not added to OBS yet")
                onClicked: win.currentPage = 7
            }
            GridLayout {
                Layout.fillWidth: true
                columns: 3
                columnSpacing: 10
                rowSpacing: 10
                Repeater {
                    model: [
                        { label: qsTr("Messages"), value: st.received || 0 },
                        { label: qsTr("Replies"), value: st.answered || 0 },
                        { label: qsTr("Avg. reply"), value: (st.avg_generation || 0).toFixed(1) + " s" },
                    ]
                    GlassCard {
                        required property var modelData
                        Layout.fillWidth: true
                        implicitHeight: 64
                        ColumnLayout {
                            anchors.centerIn: parent
                            spacing: 0
                            Text { Layout.alignment: Qt.AlignHCenter; text: modelData.value; color: Theme.text; font.pixelSize: 20; font.weight: Font.Bold; font.family: Theme.mono }
                            Text { Layout.alignment: Qt.AlignHCenter; text: modelData.label; color: Theme.textFaint; font.pixelSize: 11 }
                        }
                    }
                }
            }
        }
    }

    // ------------------------------------------------------------------- controls
    Section {
        title: qsTr("Live controls")
        iconName: "zap"
        description: qsTr("Demo works without YouTube. Assisted shows suggestions for you to approve. Automatic answers on its own.")

        RowLayout {
            Layout.fillWidth: true
            spacing: 10
            Segmented {
                model: [{ value: "demo", label: qsTr("Demo") }, { value: "assisted", label: qsTr("Assisted") },
                        { value: "auto", label: qsTr("Automatic") }]
                current: cfg.mode
                onActivated: v => backend.setConfig("mode", v)
            }
            Item { Layout.fillWidth: true }
            AppButton { variant: "primary"; iconName: win.running ? "pause" : "play"
                        text: win.running ? qsTr("Pause") : win.paused ? qsTr("Resume") : qsTr("Start"); onClicked: win.toggleRun() }
            AppButton { iconName: "stop"; text: qsTr("Stop"); enabled: rt.state !== "stopped"; onClicked: backend.stop() }
            AppButton { iconName: "skip"; text: qsTr("Interrupt"); tip: qsTr("Cancel the current answer and voice (Ctrl+.)"); onClicked: backend.interrupt() }
            AppButton { iconName: cfg.voice.enabled ? "volume" : "mute"; tip: qsTr("Mute or unmute the voice (Ctrl+M)")
                        Accessible.name: qsTr("Mute voice"); onClicked: backend.setConfig("voice.enabled", !cfg.voice.enabled) }
            AppButton { variant: "danger"; iconName: "emergency"; text: qsTr("Emergency"); onClicked: backend.emergencyStop() }
        }
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: 16

        // ---------------------------------------------------------------- try it
        Section {
            Layout.alignment: Qt.AlignTop
            Layout.preferredWidth: 1
            title: qsTr("Talk to the avatar")
            iconName: "send"
            description: qsTr("Type as if you were a viewer. In demo mode this is the chat.")

            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                AppTextField { id: author; Layout.preferredWidth: 130; placeholderText: qsTr("Name"); text: qsTr("Viewer") }
                AppTextField {
                    id: message
                    Layout.fillWidth: true
                    iconName: "chat"
                    placeholderText: qsTr("Good morning! I just got here!")
                    onAccepted: send.clicked()
                }
                AppButton {
                    id: send
                    variant: "primary"
                    iconName: "send"
                    tip: qsTr("Send as a chat message")
                    Accessible.name: qsTr("Send")
                    onClicked: {
                        if (!win.running && cfg.mode === "demo") backend.start()
                        if (cfg.mode === "demo") backend.submitMessage(message.text, author.text)
                        else backend.testReply(message.text, author.text)
                        message.text = ""
                    }
                }
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                AppTextField { id: phrase; Layout.fillWidth: true; iconName: "mic"; placeholderText: qsTr("Make it say exactly this…"); onAccepted: sayBtn.clicked() }
                AppButton { id: sayBtn; iconName: "volume"; text: qsTr("Say"); onClicked: { backend.say(phrase.text, "happy"); phrase.text = "" } }
            }
            Flow {
                Layout.fillWidth: true
                spacing: 6
                Repeater {
                    model: [{ e: "happy", l: qsTr("Happy") }, { e: "laugh", l: qsTr("Laugh") }, { e: "surprised", l: qsTr("Surprise") },
                            { e: "confused", l: qsTr("Confused") }, { e: "annoyed", l: qsTr("Annoyed") }, { e: "celebrate", l: qsTr("Celebrate") }]
                    AppButton {
                        required property var modelData
                        compact: true
                        text: modelData.l
                        onClicked: backend.react(modelData.e)
                    }
                }
            }
        }

        // ---------------------------------------------------------------- queue
        Section {
            Layout.alignment: Qt.AlignTop
            Layout.preferredWidth: 1
            title: qsTr("Up next")
            iconName: "users"
            description: (backend.queue.suggestions || []).length ? qsTr("Approve a suggestion to make the avatar say it.")
                                                                 : qsTr("Messages chosen by the selection mode, best first.")
            actions: AppButton { compact: true; variant: "ghost"; iconName: "trash"; tip: qsTr("Clear the queue"); onClicked: backend.clearQueue() }

            Repeater {
                model: backend.queue.suggestions || []
                GlassCard {
                    required property var modelData
                    Layout.fillWidth: true
                    implicitHeight: sugCol.implicitHeight + 20
                    border.color: Theme.tint(Theme.accent, 0.5)
                    ColumnLayout {
                        id: sugCol
                        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 10 }
                        spacing: 4
                        Text { Layout.fillWidth: true; text: modelData.author + ": " + modelData.message; color: Theme.textFaint; font.pixelSize: 11; elide: Text.ElideRight }
                        RowLayout {
                            Layout.fillWidth: true
                            visible: !!modelData.reading
                            spacing: 6
                            Icon { name: "quote"; size: 12; color: Theme.textFaint }
                            Text { Layout.fillWidth: true; text: qsTr("Reads first: %1").arg(modelData.reading || ""); color: Theme.textFaint; font.pixelSize: 11; font.italic: true; elide: Text.ElideRight }
                        }
                        Text { Layout.fillWidth: true; text: modelData.text; color: Theme.text; font.pixelSize: 13; wrapMode: Text.WordWrap }
                        RowLayout {
                            Item { Layout.fillWidth: true }
                            AppButton { compact: true; variant: "ghost"; iconName: "x"; text: qsTr("Discard"); onClicked: backend.reject(modelData.id) }
                            AppButton { compact: true; variant: "primary"; iconName: "check"; text: qsTr("Say it"); onClicked: backend.approve(modelData.id) }
                        }
                    }
                }
            }
            Repeater {
                model: (backend.queue.pending || []).slice(0, 6)
                RowLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    spacing: 8
                    Chip { visible: modelData.superchat !== ""; text: modelData.superchat; tone: Theme.warning }
                    Chip { visible: modelData.moderator; text: qsTr("mod"); tone: Theme.accent }
                    Chip { visible: modelData.question; text: "?"; tone: Theme.accent2 }
                    Text {
                        Layout.fillWidth: true
                        text: "<b>" + modelData.author.replace(/</g, "&lt;") + "</b> " + modelData.text.replace(/</g, "&lt;")
                        textFormat: Text.StyledText
                        color: Theme.text
                        font.pixelSize: 13
                        elide: Text.ElideRight
                    }
                    AppButton { compact: true; variant: "ghost"; iconName: "play"; tip: qsTr("Answer this now"); onClicked: backend.approve(modelData.id) }
                    AppButton { compact: true; variant: "ghost"; iconName: "x"; tip: qsTr("Skip"); onClicked: backend.reject(modelData.id) }
                }
            }
            Text {
                visible: !(backend.queue.pending || []).length && !(backend.queue.suggestions || []).length
                text: win.running ? qsTr("Waiting for messages…") : qsTr("Press Start to begin.")
                color: Theme.textFaint
                font.pixelSize: 12
            }
        }
    }

    Section {
        title: qsTr("Recent replies")
        iconName: "history"
        visible: backend.history.length > 0
        Repeater {
            model: backend.history.slice(0, 4)
            ColumnLayout {
                required property var modelData
                Layout.fillWidth: true
                spacing: 2
                Text {
                    Layout.fillWidth: true
                    visible: modelData.author !== ""
                    text: modelData.author + ": " + modelData.message
                    color: Theme.textFaint; font.pixelSize: 11; elide: Text.ElideRight
                }
                Text { Layout.fillWidth: true; text: modelData.reply; color: Theme.text; font.pixelSize: 13; wrapMode: Text.WordWrap }
            }
        }
    }
}
