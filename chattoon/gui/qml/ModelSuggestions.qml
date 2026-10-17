import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

// Models worth downloading. Each card says clearly whether it still needs a download,
// is installed, or is the one in use; a download shows real progress and can be cancelled.
ColumnLayout {
    id: root
    property bool compact: false
    property int limit: 99
    readonly property var center: backend.aiCenter
    readonly property var pull: center.pull
    readonly property var installed: (backend.services.ollama || {}).models || []
    readonly property bool online: (backend.services.ollama || {}).ok === true
    readonly property string selected: backend.config.ai.model
    property string pendingModel: ""

    spacing: 10
    Layout.fillWidth: true

    function fitText(fit) {
        return ({ good: qsTr("Fits your graphics card"), ok: qsTr("Runs on the processor (slower)"),
                  heavy: qsTr("Heavy for this computer") })[fit] || ""
    }
    function fitTone(fit) { return fit === "good" ? Theme.success : fit === "ok" ? Theme.accent : Theme.warning }
    function tierText(t) {
        return ({ tiny: qsTr("Very light"), light: qsTr("Light"), balanced: qsTr("Balanced"), strong: qsTr("More knowledge") })[t] || ""
    }
    function askDownload(name) {
        root.pendingModel = name
        root.center.downloadSize(name)
    }

    Connections {
        target: root.center
        function onSizeReady(model, bytes) {
            if (model !== root.pendingModel) return
            root.pendingModel = ""
            win.ask({ title: qsTr("Download %1?").arg(model), icon: "download", confirm: qsTr("Download and install"),
                      message: (bytes > 0 ? qsTr("Download size: %1.").arg(Status.size(bytes)) + " " : "")
                               + qsTr("Ollama downloads it from its official library (registry.ollama.ai). You can keep using ChatToon meanwhile.") },
                    () => root.center.pullModel(model))
        }
    }

    Text {
        visible: !root.online
        Layout.fillWidth: true
        text: qsTr("Start Ollama to download models.")
        color: Theme.textFaint; font.pixelSize: 12
    }

    GridLayout {
        Layout.fillWidth: true
        columns: root.compact ? 1 : Math.max(1, Math.floor(width / 300))
        columnSpacing: 10
        rowSpacing: 10
        Repeater {
            model: root.center.suggestions.slice(0, root.limit)
            Rectangle {
                id: card
                required property var modelData
                readonly property bool isInstalled: root.installed.indexOf(modelData.name) >= 0
                readonly property bool inUse: isInstalled && root.selected === modelData.name
                readonly property bool downloading: root.pull.model === modelData.name && root.pull.state === "downloading"
                Layout.fillWidth: true
                implicitHeight: sugCol.implicitHeight + 24
                radius: Theme.radiusSmall
                color: inUse ? Theme.tint(Theme.success, Theme.dark ? 0.1 : 0.07) : Theme.field
                border.width: inUse ? 2 : 1
                border.color: inUse ? Theme.success : Theme.border

                ColumnLayout {
                    id: sugCol
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 12 }
                    spacing: 6
                    RowLayout {
                        Layout.fillWidth: true
                        Text { Layout.fillWidth: true; text: card.modelData.name; color: Theme.text; font.family: Theme.mono; font.pixelSize: 14; font.weight: Font.DemiBold }
                        Chip { text: root.tierText(card.modelData.tier); tone: Theme.textMuted }
                    }
                    Text {
                        Layout.fillWidth: true; wrapMode: Text.WordWrap
                        color: Theme.textMuted; font.pixelSize: 12
                        text: qsTr("≈ %1 download").arg(Status.size(card.modelData.bytes)) + "  ·  " + qsTr("%1 parameters").arg(card.modelData.params)
                              + "  ·  " + card.modelData.languages
                    }
                    Flow {
                        Layout.fillWidth: true
                        spacing: 4
                        Repeater {
                            model: card.modelData.features
                            Chip { required property string modelData; text: Status.capability(modelData); tone: Theme.accent }
                        }
                        Chip { visible: root.fitText(card.modelData.fit) !== ""; text: root.fitText(card.modelData.fit); tone: root.fitTone(card.modelData.fit)
                               tip: qsTr("An estimate from your memory and graphics card. You can use any model.") }
                    }
                    // progress of this model's download
                    ColumnLayout {
                        Layout.fillWidth: true
                        visible: card.downloading
                        spacing: 4
                        ProgressGlow { Layout.fillWidth: true; implicitHeight: 6; value: root.pull.progress }
                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                Layout.fillWidth: true
                                color: Theme.text; font.pixelSize: 12
                                text: Status.pullStatus(root.pull.status)
                                      + (root.pull.progress >= 0 ? "  " + Math.round(root.pull.progress * 100) + "%" : "")
                                      + (root.pull.total > 0 ? "  ·  " + qsTr("%1 of %2").arg(Status.size(root.pull.completed)).arg(Status.size(root.pull.total)) : "")
                                      + (root.pull.speed > 0 ? "  ·  " + Status.speed(root.pull.speed) : "")
                            }
                            AppButton { compact: true; variant: "ghost"; iconName: "x"; text: qsTr("Cancel"); onClicked: root.center.cancelPull() }
                        }
                    }
                    Text {
                        Layout.fillWidth: true
                        visible: root.pull.model === card.modelData.name && root.pull.state === "error"
                        text: qsTr("The download failed: %1").arg(root.pull.error || ""); color: Theme.danger; font.pixelSize: 12; wrapMode: Text.WordWrap
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        visible: !card.downloading
                        Item { Layout.fillWidth: true }
                        AppButton {
                            visible: !card.isInstalled
                            compact: true; variant: "primary"; iconName: "download"; text: qsTr("Download and install")
                            enabled: root.online && root.pull.state !== "downloading"
                            onClicked: root.askDownload(card.modelData.name)
                        }
                        AppButton {
                            visible: card.isInstalled && !card.inUse
                            compact: true; iconName: "check"; text: qsTr("Installed — Use this model")
                            onClicked: root.center.selectModel(card.modelData.name)
                        }
                        StateChip { visible: card.inUse; text: qsTr("In use"); tone: "ok"; iconName: "check" }
                    }
                }
            }
        }
    }

    // any other model by name (advanced)
    RowLayout {
        Layout.fillWidth: true
        visible: backend.config.advanced && !root.compact
        spacing: 8
        AppTextField {
            id: custom
            Layout.fillWidth: true
            iconName: "search"
            placeholderText: qsTr("Another model from ollama.com/library, e.g. mistral:7b")
            onAccepted: getCustom.clicked()
            Accessible.name: qsTr("Model name")
        }
        AppButton {
            id: getCustom
            iconName: "download"; text: qsTr("Download")
            enabled: root.online && custom.text.trim() !== "" && root.pull.state !== "downloading"
            onClicked: { root.askDownload(custom.text.trim()); custom.text = "" }
        }
    }
    // a custom download in progress (not one of the cards)
    ColumnLayout {
        Layout.fillWidth: true
        visible: root.pull.state === "downloading" && root.center.suggestions.findIndex(s => s.name === root.pull.model) < 0
        spacing: 4
        Text { text: qsTr("Downloading %1").arg(root.pull.model || ""); color: Theme.text; font.pixelSize: 12 }
        ProgressGlow { Layout.fillWidth: true; implicitHeight: 6; value: root.pull.progress }
        AppButton { compact: true; variant: "ghost"; iconName: "x"; text: qsTr("Cancel"); onClicked: root.center.cancelPull() }
    }
}
