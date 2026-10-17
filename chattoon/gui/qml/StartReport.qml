import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

// What the character really does in this session — shown when Start is pressed, and from
// the Dashboard (docs/35-startup-report.md). Red items stop the start; yellow ones are optional.
Popup {
    id: root
    readonly property var r: backend.sessionReport.report
    readonly property var ch: r.character || ({})
    readonly property var ai: r.ai || ({})
    readonly property var voice: r.voice || ({})
    readonly property var plat: r.platforms || ({})
    readonly property var disp: r.display || ({})
    readonly property bool checking: r.state === "checking"

    parent: Overlay.overlay
    anchors.centerIn: parent
    modal: true
    focus: true
    width: Math.min(820, (parent ? parent.width : 820) - 48)
    height: Math.min(implicitHeight, (parent ? parent.height : 760) - 48)
    padding: 24
    Overlay.modal: Rectangle { color: Qt.rgba(0, 0, 0, 0.5) }
    background: Rectangle { radius: Theme.radius + 4; color: Theme.surfaceStrong; border.color: Theme.border }

    Connections {
        target: backend.sessionReport
        function onOpenRequested() { root.open() }
    }

    function fix(page) { root.close(); win.go(page) }
    function tone(status) { return status === "ok" ? "ok" : status === "error" ? "error" : status === "warn" ? "warn" : status === "off" ? "idle" : "busy" }
    function headline() {
        if (checking) return qsTr("Checking everything…")
        if (r.state === "running") return qsTr("%1 is live!").arg(ch.name || "")
        if (r.state === "checked") return qsTr("%1 is ready").arg(ch.name || "")
        if (r.state === "blocked") return qsTr("Almost there!")
        return ch.name || ""
    }
    function aiText() {
        const m = ai.model || ""
        switch (ai.code) {
        case "ready": return ai.responded === true ? qsTr("%1 answered in %2 s").arg(m).arg(Number(ai.seconds || 0).toFixed(1))
                           : ai.responded === null || ai.responded === undefined ? qsTr("%1 — checking that it answers…").arg(m) : m
        case "ollama-not-installed": return qsTr("Ollama is not installed.")
        case "ollama-stopped": return qsTr("Ollama is installed but stopped.")
        case "ollama-remote-down": return qsTr("The Ollama server on the other computer does not answer.")
        case "ollama-unreachable": return qsTr("Ollama does not answer.")
        case "no-model": case "no-chat-model": return qsTr("Choose or install an AI model.")
        case "model-missing": return qsTr("The model %1 is no longer installed.").arg(m)
        case "model-incompatible": return qsTr("The model %1 cannot answer the chat.").arg(m)
        case "model-failed": return qsTr("The model %1 did not load.").arg(m)
        }
        return ai.code || ""
    }
    function voiceText() {
        const engines = { rhvoice: "RHVoice", "espeak-ng": "espeak-ng", piper: "Piper", kokoro: "Kokoro" }
        switch (voice.code) {
        case "ready": return (engines[voice.engine] || voice.engine) + " — " + voice.voice
                           + (voice.verified === true ? "  ✓ " + qsTr("ready to speak") : voice.verified === null || voice.verified === undefined ? "  · " + qsTr("testing…") : "")
        case "muted": return qsTr("Voice off — replies only in the speech bubble.")
        case "tts-missing": return qsTr("The voice is not ready yet.")
        case "no-voice": return qsTr("There is no voice in the reply language yet.")
        case "voice-failed": return qsTr("The voice failed the test.")
        }
        return voice.code || ""
    }
    function platformText() {
        if (plat.code === "demo") return qsTr("Demo mode — type to the character on the Dashboard.")
        if (plat.code === "no-platform") return qsTr("Connect a platform to receive messages.")
        return (plat.items || []).map(i => (win.platformInfo[i.platform] || {}).label || i.platform).join(", ")
    }
    function modeText(m) { return ({ demo: qsTr("Demo"), assisted: qsTr("Assisted — you approve each reply"), auto: qsTr("Automatic") })[m] || m || "" }
    function displayText() {
        const parts = []
        if (disp.mode !== "window") parts.push(disp.obs > 0 ? qsTr("OBS: %n source(s) connected", "", disp.obs) : qsTr("OBS has not opened the overlay yet"))
        if (disp.mode !== "obs") parts.push(disp.window ? qsTr("window on the desktop") : qsTr("the desktop window is closed"))
        if (disp.lan) parts.push(qsTr("local network on"))
        if (disp.remote) parts.push(qsTr("internet address set"))
        return parts.join(" · ")
    }
    function interactionText(id) {
        return ({ answer: qsTr("Answer the chat"), read_name: qsTr("Read who sent the message"), read_message: qsTr("Read the message aloud"),
                  emotions: qsTr("React with emotions"), animations: qsTr("Idle animations"), spontaneous: qsTr("Speak on its own"),
                  curiosities: qsTr("Tell curiosities"), memory: qsTr("Remember the conversation"), platforms: qsTr("Talk with the connected platforms"),
                  context: qsTr("Use the stream context"), voice: qsTr("Speak with a voice") })[id] || id
    }

    contentItem: ScrollView {
        id: scroller
        clip: true
        contentWidth: availableWidth
        implicitHeight: body.implicitHeight
        ColumnLayout {
            id: body
            width: scroller.availableWidth
            spacing: 16

            RowLayout {
                Layout.fillWidth: true
                spacing: 16
                Image {
                    Layout.preferredWidth: 84; Layout.preferredHeight: 96
                    source: root.ch.id ? "assets/characters/" + root.ch.id + ".png" : ""
                    sourceSize: Qt.size(168, 192)
                    fillMode: Image.PreserveAspectFit
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 6
                    Text { text: root.headline(); color: Theme.text; font.pixelSize: 24; font.weight: Font.Bold; Accessible.role: Accessible.Heading }
                    RowLayout {
                        spacing: 8
                        StateChip {
                            text: root.checking ? qsTr("Checking…") : root.r.state === "running" ? qsTr("Live") : root.r.state === "checked" ? qsTr("Ready")
                                : qsTr("Could not start")
                            tone: root.checking ? "busy" : root.r.ok ? "ok" : "error"
                        }
                        Chip { visible: !!root.ch.preset; text: qsTr("Personality: %1").arg(Status.preset(root.ch.preset)); tone: Theme.accent }
                        Chip { visible: !!root.plat.mode; text: root.modeText(root.plat.mode); tone: Theme.textMuted }
                    }
                    Text {
                        Layout.fillWidth: true
                        visible: root.r.state === "blocked"
                        text: qsTr("Fix what is red below and try again. Yellow items are optional.")
                        color: Theme.textMuted; font.pixelSize: 13; wrapMode: Text.WordWrap
                    }
                }
            }
            BusyDots { visible: root.checking; Layout.alignment: Qt.AlignHCenter }

            // the four areas
            GridLayout {
                Layout.fillWidth: true
                visible: !root.checking
                columns: width < 600 ? 1 : 2
                columnSpacing: 12
                rowSpacing: 12
                Repeater {
                    model: [
                        { icon: "bot", title: qsTr("Artificial intelligence"), status: root.ai.status, text: root.aiText(), page: "ai", fix: qsTr("Set up AI") },
                        { icon: "volume", title: qsTr("Voice"), status: root.voice.status, text: root.voiceText(), page: "voice", fix: qsTr("Set up voice") },
                        { icon: "layers", title: qsTr("Platforms"), status: root.plat.status, text: root.platformText(), page: "platforms", fix: qsTr("Set up platform") },
                        { icon: "monitor", title: qsTr("Where it appears"), status: root.disp.status, text: root.displayText(), page: "display", fix: qsTr("Where to show") },
                    ]
                    GlassCard {
                        required property var modelData
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignTop
                        implicitHeight: areaCol.implicitHeight + 24
                        border.color: modelData.status === "error" ? Theme.tint(Theme.danger, 0.6) : Theme.border
                        ColumnLayout {
                            id: areaCol
                            anchors { left: parent.left; right: parent.right; top: parent.top; margins: 12 }
                            spacing: 6
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                Icon { name: modelData.icon; size: 18; color: Theme.accent }
                                Text { Layout.fillWidth: true; text: modelData.title; color: Theme.text; font.pixelSize: 14; font.weight: Font.DemiBold }
                                StateChip {
                                    text: modelData.status === "ok" ? qsTr("OK") : modelData.status === "error" ? qsTr("Required") : modelData.status === "off" ? qsTr("Off") : qsTr("Optional")
                                    tone: root.tone(modelData.status)
                                }
                            }
                            Text { Layout.fillWidth: true; text: modelData.text; color: Theme.textMuted; font.pixelSize: 12; wrapMode: Text.WordWrap }
                            AppButton {
                                visible: modelData.status === "error" || modelData.status === "warn"
                                compact: true; variant: modelData.status === "error" ? "primary" : "secondary"; iconName: "wand"; text: modelData.fix
                                onClicked: root.fix(modelData.page)
                            }
                        }
                    }
                }
            }

            // what it will do
            GlassCard {
                Layout.fillWidth: true
                visible: !root.checking && (root.r.interactions || []).length > 0
                implicitHeight: interCol.implicitHeight + 24
                ColumnLayout {
                    id: interCol
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 12 }
                    spacing: 8
                    Text { text: qsTr("What %1 will do").arg(root.ch.name || ""); color: Theme.text; font.pixelSize: 14; font.weight: Font.DemiBold }
                    GridLayout {
                        Layout.fillWidth: true
                        columns: width < 520 ? 1 : 2
                        columnSpacing: 16
                        rowSpacing: 4
                        Repeater {
                            model: root.r.interactions || []
                            RowLayout {
                                required property var modelData
                                spacing: 8
                                Icon { name: modelData.on ? "check" : "minus"; size: 15; color: modelData.on ? Theme.success : Theme.textFaint }
                                Text {
                                    Layout.fillWidth: true
                                    text: root.interactionText(modelData.id) + (modelData.id === "memory" && modelData.detail === "persist" ? " " + qsTr("(also between lives)") : "")
                                    color: modelData.on ? Theme.text : Theme.textFaint; font.pixelSize: 13
                                    Accessible.name: text + ": " + (modelData.on ? qsTr("on") : qsTr("off"))
                                }
                            }
                        }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                AppButton {
                    visible: root.r.state === "running" || root.r.state === "checked"
                    iconName: "chat"; text: qsTr("Test the character")
                    onClicked: backend.testReply(qsTr("Hi! Are you ready for the live?"), qsTr("Test"))
                }
                Item { Layout.fillWidth: true }
                AppButton { text: qsTr("Close"); onClicked: root.close() }
                AppButton {
                    visible: root.r.state === "blocked"
                    variant: "primary"; iconName: "refresh"; text: qsTr("Try again")
                    onClicked: root.r.start ? backend.start() : backend.sessionReport.check()
                }
            }
        }
    }
}
