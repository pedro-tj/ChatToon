import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Popup {
    id: wizard
    property int step: 0
    readonly property var svc: backend.services
    readonly property var cfg: backend.config

    modal: true
    focus: true
    closePolicy: Popup.NoAutoClose
    width: Math.min(720, parent ? parent.width - 80 : 720)
    padding: 28
    Overlay.modal: Rectangle { color: Qt.rgba(0, 0, 0, 0.5) }
    background: Rectangle { radius: Theme.radius + 4; color: Theme.surfaceStrong; border.color: Theme.border }

    function finish() { backend.finishFirstRun(); close() }

    contentItem: ColumnLayout {
        spacing: 18

        RowLayout {
            spacing: 6
            Repeater {
                model: 4
                Rectangle {
                    required property int index
                    Layout.preferredWidth: 36; height: 5; radius: 3
                    color: index <= wizard.step ? Theme.accent : Theme.hover
                }
            }
            Item { Layout.fillWidth: true }
            AppButton { compact: true; variant: "ghost"; text: qsTr("Skip"); onClicked: wizard.finish() }
        }

        StackLayout {
            Layout.fillWidth: true
            currentIndex: wizard.step

            // 0 — welcome
            ColumnLayout {
                spacing: 12
                Image { source: "assets/chattoon.svg"; sourceSize: Qt.size(128, 128); Layout.preferredWidth: 64; Layout.preferredHeight: 64 }
                Text { text: qsTr("Welcome to ChatToon"); color: Theme.text; font.pixelSize: 26; font.weight: Font.Bold }
                Text {
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                    color: Theme.textMuted; font.pixelSize: 14; lineHeight: 1.3
                    text: qsTr("A 3D character that reads your YouTube chat, answers with its own sense of humour and talks with a real voice — all running on your computer. Let's check a couple of things and you are ready in a minute.")
                }
            }

            // 1 — services
            ColumnLayout {
                spacing: 12
                Text { text: qsTr("Checking your computer"); color: Theme.text; font.pixelSize: 22; font.weight: Font.Bold }
                StatusCard {
                    iconName: "bot"
                    title: qsTr("Ollama (the brain)")
                    status: wizard.svc.ollama.ok === true ? ((wizard.svc.ollama.models || []).length ? "ok" : "warn") : wizard.svc.ollama.ok === false ? "error" : "busy"
                    value: wizard.svc.ollama.ok === false ? qsTr("Not running — start Ollama and check again")
                         : (wizard.svc.ollama.models || []).length ? qsTr("Ready — model %1").arg(wizard.cfg.ai.model) : qsTr("Running, but no model installed")
                }
                AppButton {
                    visible: wizard.svc.ollama.ok === true && !(wizard.svc.ollama.models || []).length
                    variant: "primary"; iconName: "download"
                    text: qsTr("Download the recommended model (gemma3:4b, 3.3 GB)")
                    onClicked: backend.pullModel("gemma3:4b")
                }
                StatusCard {
                    iconName: "volume"
                    title: qsTr("TTS BigLinux (the voice)")
                    status: wizard.svc.tts.ok === true ? "ok" : wizard.svc.tts.ok === false ? "error" : "busy"
                    value: wizard.svc.tts.ok === true ? qsTr("Ready — %n voice(s)", "", (wizard.svc.tts.voices || []).length)
                         : wizard.svc.tts.ok === false ? qsTr("Missing — install the tts-biglinux package") : qsTr("Checking…")
                }
                AppButton { iconName: "refresh"; text: qsTr("Check again"); onClicked: backend.refreshServices() }
            }

            // 2 — character
            ColumnLayout {
                spacing: 12
                Text { text: qsTr("Who joins your stream?"); color: Theme.text; font.pixelSize: 22; font.weight: Font.Bold }
                GridLayout {
                    Layout.fillWidth: true
                    columns: 2
                    columnSpacing: 10
                    rowSpacing: 10
                    uniformCellWidths: true
                    Repeater {
                        model: backend.characters
                        Rectangle {
                            required property var modelData
                            readonly property bool selected: wizard.cfg.character === modelData.id
                            Layout.fillWidth: true
                            implicitHeight: 70
                            radius: Theme.radiusSmall
                            color: selected ? Theme.tint(Qt.lighter(modelData.color, 1), 0.18) : Theme.hover
                            border.width: selected ? 2 : 0
                            border.color: modelData.color
                            RowLayout {
                                anchors { fill: parent; margins: 8 }
                                spacing: 10
                                Image {
                                    Layout.preferredWidth: 48; Layout.preferredHeight: 54
                                    source: "assets/characters/" + modelData.id + ".png"
                                    sourceSize: Qt.size(96, 108)
                                    fillMode: Image.PreserveAspectFit
                                    asynchronous: true
                                }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 2
                                    Text { text: modelData.name; color: Theme.text; font.pixelSize: 15; font.weight: Font.DemiBold }
                                    Text { Layout.fillWidth: true; text: modelData.tagline; color: Theme.textMuted; font.pixelSize: 12; elide: Text.ElideRight }
                                }
                            }
                            HoverHandler { cursorShape: Qt.PointingHandCursor }
                            TapHandler { onTapped: backend.selectCharacter(modelData.id) }
                            Accessible.role: Accessible.RadioButton
                            Accessible.name: modelData.name
                        }
                    }
                }
            }

            // 3 — done
            ColumnLayout {
                spacing: 12
                Text { text: qsTr("All set!"); color: Theme.text; font.pixelSize: 26; font.weight: Font.Bold }
                Text {
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                    color: Theme.textMuted; font.pixelSize: 14; lineHeight: 1.3
                    text: qsTr("Try it now in Demo mode: type a message on the Dashboard as if you were a viewer. When you go live, paste the stream link on the YouTube chat page, add the overlay to OBS and switch to Assisted or Automatic.")
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            AppButton { visible: wizard.step > 0; text: qsTr("Back"); onClicked: wizard.step-- }
            Item { Layout.fillWidth: true }
            AppButton {
                variant: "primary"
                text: wizard.step < 3 ? qsTr("Continue") : qsTr("Open the dashboard")
                onClicked: wizard.step < 3 ? wizard.step++ : wizard.finish()
            }
        }
    }
}
