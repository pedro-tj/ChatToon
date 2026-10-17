import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

// The four voice engines of TTS BigLinux, each with its real state and the one action that
// moves it forward: install the engine, download a voice, test it.
ColumnLayout {
    id: root
    property bool compact: false
    readonly property var tts: backend.services.tts || ({})
    readonly property var states: tts.states || ({})
    readonly property var vc: backend.voiceCenter
    readonly property var inst: vc.install
    readonly property string activeEngine: activeBackend
    property string activeBackend: ""
    property string pendingEngine: ""
    readonly property string lang: backend.config.ai.reply_language.toLowerCase().split("-")[0]

    spacing: 12
    Layout.fillWidth: true

    function stateText(s) {
        return ({ not_installed: qsTr("Not installed"), needs_voice: qsTr("Needs a voice"), ready: qsTr("Ready to use"),
                  error: qsTr("Error"), unavailable: qsTr("Needs TTS BigLinux") })[s] || qsTr("Checking…")
    }
    function stateTone(s) { return s === "ready" ? "ok" : s === "needs_voice" ? "warn" : s === "error" ? "error" : s ? "idle" : "busy" }
    function blurb(e) {
        return ({ piper: qsTr("Natural neural voices that answer quickly."),
                  kokoro: qsTr("The most natural voices; they take a little longer to create."),
                  rhvoice: qsTr("Light and clear voices, like Letícia in Portuguese."),
                  "espeak-ng": qsTr("Robotic but tiny and fast, in many languages.") })[e] || ""
    }
    function sampleVoice(engine) {
        const voices = (root.tts.voices || []).filter(v => v.backend === engine)
        return voices.find(v => v.language.toLowerCase().startsWith(root.lang)) || voices[0] || null
    }
    function sourceText(src) { return ({ installed: qsTr("already installed"), repo: qsTr("from your repositories"), aur: qsTr("from the AUR (built on this computer)") })[src] || qsTr("not found") }

    Connections {
        target: root.vc
        function onPlanChanged() {
            const plan = root.vc.plan
            if (!root.pendingEngine || plan.loading || plan.engine !== root.pendingEngine) return
            const engine = root.pendingEngine
            root.pendingEngine = ""
            const items = plan.items || []
            const todo = items.filter(i => i.source === "repo" || i.source === "aur")
            const missing = items.filter(i => !i.source)
            if (missing.length) {
                win.ask({ title: qsTr("Not available"), icon: "alert", confirm: qsTr("OK"),
                          message: qsTr("These packages were not found in your repositories: %1. Update the system and try again.")
                                   .arg(missing.map(i => i.wanted).join(", ")) }, null)
                return
            }
            if (!todo.length) { root.vc.refresh(); return }
            win.ask({ title: engine === "tts-biglinux" ? qsTr("Install TTS BigLinux?") : qsTr("Install %1?").arg(root.states[engine] ? root.states[engine].label : engine),
                      icon: "download", confirm: qsTr("Install"),
                      message: qsTr("These packages will be installed. Your administrator password will be asked."),
                      details: todo.map(i => i.name + (i.size ? "  (" + i.size + ")" : "") + " — " + root.sourceText(i.source)) },
                    () => root.vc.installEngine(engine))
        }
    }

    // TTS BigLinux itself is missing
    Rectangle {
        Layout.fillWidth: true
        visible: root.tts.ok === false
        implicitHeight: missCol.implicitHeight + 24
        radius: Theme.radiusSmall
        color: Theme.tint(Theme.warning, 0.1)
        border.color: Theme.tint(Theme.warning, 0.4)
        ColumnLayout {
            id: missCol
            anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; margins: 12 }
            spacing: 8
            Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Theme.text; font.pixelSize: 13
                   text: qsTr("The voice comes from TTS BigLinux, which is not installed. Without it the character only writes in the speech bubble.") }
            AppButton {
                variant: "primary"; iconName: "download"; text: qsTr("Install TTS BigLinux")
                enabled: !root.inst.running
                onClicked: { root.pendingEngine = "tts-biglinux"; root.vc.loadPlan("tts-biglinux") }
            }
        }
    }

    GridLayout {
        Layout.fillWidth: true
        columns: root.compact ? 2 : Math.max(1, Math.min(4, Math.floor(width / 250)))
        columnSpacing: 10
        rowSpacing: 10
        Repeater {
            model: ["piper", "kokoro", "rhvoice", "espeak-ng"]
            Rectangle {
                id: card
                required property string modelData
                readonly property var info: root.states[modelData] || ({})
                readonly property bool inUse: root.activeEngine === modelData
                readonly property bool installing: root.inst.running && root.inst.engine === modelData
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                implicitHeight: engCol.implicitHeight + 24
                radius: Theme.radiusSmall
                color: inUse ? Theme.tint(Theme.success, Theme.dark ? 0.1 : 0.07) : Theme.field
                border.width: inUse ? 2 : 1
                border.color: inUse ? Theme.success : Theme.border
                ColumnLayout {
                    id: engCol
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 12 }
                    spacing: 6
                    RowLayout {
                        Layout.fillWidth: true
                        Text { Layout.fillWidth: true; text: card.info.label || card.modelData; color: Theme.text; font.pixelSize: 15; font.weight: Font.DemiBold }
                        Icon { visible: card.inUse; name: "checkCircle"; size: 18; color: Theme.success }
                    }
                    StateChip { text: card.inUse ? qsTr("In use") : root.stateText(card.info.state); tone: card.inUse ? "ok" : root.stateTone(card.info.state) }
                    Text { Layout.fillWidth: true; visible: !root.compact; text: root.blurb(card.modelData); color: Theme.textMuted; font.pixelSize: 12; wrapMode: Text.WordWrap }
                    Text {
                        Layout.fillWidth: true
                        visible: (card.info.voices || 0) > 0
                        text: qsTr("%n voice(s)", "", card.info.voices || 0) + " · " + qsTr("%1 in the reply language").arg(card.info.inLanguage || 0)
                        color: Theme.textFaint; font.pixelSize: 11
                    }
                    ProgressGlow { Layout.fillWidth: true; visible: card.installing; implicitHeight: 5; value: -1 }
                    Flow {
                        Layout.fillWidth: true
                        spacing: 6
                        visible: !card.installing
                        AppButton {
                            visible: card.info.state === "not_installed"
                            compact: true; variant: "primary"; iconName: "download"; text: qsTr("Install engine")
                            enabled: !root.inst.running
                            onClicked: { root.pendingEngine = card.modelData; root.vc.loadPlan(card.modelData) }
                        }
                        AppButton {
                            visible: card.info.state === "needs_voice"
                            compact: true; variant: "primary"; iconName: "download"; text: qsTr("Download voice")
                            enabled: !root.inst.running
                            onClicked: {
                                if (card.modelData === "kokoro") kokoroDialog.open()
                                else if (card.info.voicePackage) { root.pendingEngine = card.modelData; root.vc.loadPlan(card.modelData) }
                                else root.vc.openTtsBigLinux()
                            }
                        }
                        AppButton {
                            visible: card.info.state === "ready"
                            compact: true; iconName: "play"; text: qsTr("Test voice")
                            enabled: root.sampleVoice(card.modelData) !== null
                            onClicked: backend.previewVoice(root.sampleVoice(card.modelData).id)
                        }
                        AppButton {
                            visible: card.modelData === "kokoro" && card.info.state === "ready" && !root.compact
                            compact: true; variant: "ghost"; iconName: "plus"; text: qsTr("More voices")
                            onClicked: kokoroDialog.open()
                        }
                    }
                }
            }
        }
    }
    Text {
        Layout.fillWidth: true
        visible: !!(root.inst.result && root.inst.result.ok === false)
        text: (root.inst.result || {}).message || qsTr("The installation failed.")
        color: Theme.danger; font.pixelSize: 12; wrapMode: Text.WordWrap
    }
    RowLayout {
        Layout.fillWidth: true
        visible: root.vc.hasTtsApp && !root.compact
        Text { Layout.fillWidth: true; text: qsTr("Every RHVoice and Piper voice, history and shortcuts are in the TTS BigLinux app."); color: Theme.textFaint; font.pixelSize: 12; wrapMode: Text.WordWrap }
        AppButton { compact: true; variant: "ghost"; iconName: "external"; text: qsTr("Manage voices in TTS BigLinux"); onClicked: root.vc.openTtsBigLinux() }
    }

    // Kokoro voices: downloaded by TTS BigLinux into your voices.bin
    Popup {
        id: kokoroDialog
        parent: Overlay.overlay
        anchors.centerIn: parent
        modal: true
        width: Math.min(560, (parent ? parent.width : 560) - 48)
        height: Math.min(560, (parent ? parent.height : 560) - 80)
        padding: 20
        onOpened: root.vc.loadKokoro()
        Overlay.modal: Rectangle { color: Qt.rgba(0, 0, 0, 0.5) }
        background: Rectangle { radius: Theme.radius; color: Theme.surfaceStrong; border.color: Theme.border }
        contentItem: ColumnLayout {
            spacing: 10
            RowLayout {
                Text { Layout.fillWidth: true; text: qsTr("Kokoro voices"); color: Theme.text; font.pixelSize: 17; font.weight: Font.DemiBold }
                AppButton { compact: true; variant: "ghost"; iconName: "x"; Accessible.name: qsTr("Close"); onClicked: kokoroDialog.close() }
            }
            Text { Layout.fillWidth: true; text: qsTr("Each voice is a small download from Hugging Face, made by TTS BigLinux."); color: Theme.textMuted; font.pixelSize: 12; wrapMode: Text.WordWrap }
            ListView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                spacing: 4
                model: root.vc.kokoro.slice().sort((a, b) => (b.language.toLowerCase().startsWith(root.lang)) - (a.language.toLowerCase().startsWith(root.lang)) || a.name.localeCompare(b.name))
                ScrollBar.vertical: ScrollBar {}
                delegate: RowLayout {
                    required property var modelData
                    width: ListView.view.width - 12
                    spacing: 8
                    Text { Layout.preferredWidth: 140; text: modelData.name; color: Theme.text; font.pixelSize: 13; elide: Text.ElideRight }
                    Text { Layout.fillWidth: true; text: modelData.language + (modelData.gender ? " · " + modelData.gender : ""); color: Theme.textFaint; font.pixelSize: 12; elide: Text.ElideRight }
                    StateChip { visible: modelData.installed; text: qsTr("Installed"); tone: "ok" }
                    AppButton {
                        visible: !modelData.installed && !(root.vc.download.voice === modelData.id && root.vc.download.state === "downloading")
                        compact: true; iconName: "download"; text: qsTr("Download")
                        enabled: root.vc.download.state !== "downloading"
                        onClicked: root.vc.downloadKokoro(modelData.id)
                    }
                    ProgressGlow {
                        visible: root.vc.download.voice === modelData.id && root.vc.download.state === "downloading"
                        Layout.preferredWidth: 80; implicitHeight: 5; value: root.vc.download.progress
                    }
                    AppButton {
                        visible: root.vc.download.voice === modelData.id && root.vc.download.state === "downloading"
                        compact: true; variant: "ghost"; iconName: "x"; Accessible.name: qsTr("Cancel"); onClicked: root.vc.cancelDownload()
                    }
                }
            }
            Text { visible: root.vc.download.state === "error"; Layout.fillWidth: true; text: root.vc.download.error || ""; color: Theme.danger; font.pixelSize: 12; wrapMode: Text.WordWrap }
        }
    }
}
