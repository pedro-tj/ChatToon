import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

// First run: everything needed to try the character, in one guided sequence. Each step shows
// a real result (installed, running, ready) and the fix right there — no page hopping.
Popup {
    id: wizard
    property int step: 0
    readonly property int last: 5
    readonly property var svc: backend.services
    readonly property var cfg: backend.config
    readonly property var current: backend.characters.find(c => c.id === cfg.character) || {}
    readonly property bool aiReady: svc.ollama.ok === true && (svc.ollama.models || []).indexOf(cfg.ai.model) >= 0
    readonly property bool voiceReady: svc.tts.ok === true && (svc.tts.voices || []).length > 0

    parent: Overlay.overlay
    anchors.centerIn: parent
    modal: true
    focus: true
    closePolicy: Popup.NoAutoClose
    width: Math.min(800, parent ? parent.width - 60 : 800)
    height: Math.min(implicitHeight, parent ? parent.height - 40 : 720)
    padding: 26
    Overlay.modal: Rectangle { color: Qt.rgba(0, 0, 0, 0.5) }
    background: Rectangle { radius: Theme.radius + 4; color: Theme.surfaceStrong; border.color: Theme.border }

    function finish() { backend.finishFirstRun(); close() }
    onStepChanged: {
        if (step === 2) backend.aiCenter.refresh()
        if (step === 3) backend.refreshServices()
    }

    contentItem: ColumnLayout {
        spacing: 16

        RowLayout {
            spacing: 6
            Repeater {
                model: wizard.last + 1
                Rectangle {
                    required property int index
                    Layout.preferredWidth: 34; height: 5; radius: 3
                    color: index <= wizard.step ? Theme.accent : Theme.hover
                    Accessible.ignored: true
                }
            }
            Text { Layout.leftMargin: 8; text: qsTr("Step %1 of %2").arg(wizard.step + 1).arg(wizard.last + 1); color: Theme.textFaint; font.pixelSize: 12 }
            Item { Layout.fillWidth: true }
            AppButton { compact: true; variant: "ghost"; text: qsTr("Skip"); onClicked: wizard.finish() }
        }

        ScrollView {
            id: scroller
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.preferredHeight: stack.implicitHeight
            clip: true
            contentWidth: availableWidth

            StackLayout {
                id: stack
                width: scroller.availableWidth
                currentIndex: wizard.step
                // as tall as the current step, not the tallest one
                implicitHeight: children[currentIndex] ? children[currentIndex].implicitHeight : 0

                // 0 — welcome
                ColumnLayout {
                    spacing: 12
                    Image { source: "assets/chattoon.svg"; sourceSize: Qt.size(128, 128); Layout.preferredWidth: 64; Layout.preferredHeight: 64 }
                    Text { text: qsTr("Welcome to ChatToon"); color: Theme.text; font.pixelSize: 26; font.weight: Font.Bold }
                    Text {
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                        color: Theme.textMuted; font.pixelSize: 14; lineHeight: 1.3
                        text: qsTr("A 3D character that reads your live chat — YouTube, Twitch, Kick, TikTok and more at the same time — answers with its own sense of humour and talks with a real voice, all running on your computer. Let's check a couple of things and you are ready in a minute.")
                    }
                    Steps {
                        model: [qsTr("Choose your character"), qsTr("Give it a brain (AI)"), qsTr("Give it a voice"), qsTr("Decide where it appears")]
                    }
                }

                // 1 — character
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
                                border.width: selected ? 2 : activeFocus ? 2 : 0
                                border.color: selected ? modelData.color : Theme.accent
                                activeFocusOnTab: true
                                Keys.onSpacePressed: backend.selectCharacter(modelData.id)
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
                                    Icon { visible: parent.parent.selected; name: "checkCircle"; size: 20; color: modelData.color }
                                }
                                HoverHandler { cursorShape: Qt.PointingHandCursor }
                                TapHandler { onTapped: backend.selectCharacter(modelData.id) }
                                Accessible.role: Accessible.RadioButton
                                Accessible.name: modelData.name
                                Accessible.checked: selected
                            }
                        }
                    }
                }

                // 2 — AI
                ColumnLayout {
                    spacing: 12
                    RowLayout {
                        Text { Layout.fillWidth: true; text: qsTr("The brain: Ollama"); color: Theme.text; font.pixelSize: 22; font.weight: Font.Bold }
                        StateChip { text: wizard.aiReady ? qsTr("Ready — %1").arg(wizard.cfg.ai.model) : qsTr("Not ready yet"); tone: wizard.aiReady ? "ok" : "warn" }
                    }
                    Text {
                        Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Theme.textMuted; font.pixelSize: 13
                        text: qsTr("Ollama runs the AI on this computer. Install it, start it and download one model — all from here.")
                    }
                    OllamaPanel { compact: true }
                    ModelCatalog { compact: true; visible: wizard.svc.ollama.ok === true && (wizard.svc.ollama.catalog || []).length > 0 }
                    Text {
                        visible: wizard.svc.ollama.ok === true
                        text: (wizard.svc.ollama.models || []).length ? qsTr("Or download another:") : qsTr("Download a model to start:")
                        color: Theme.text; font.pixelSize: 13; font.weight: Font.Medium
                    }
                    ModelSuggestions { compact: true; limit: 3; visible: wizard.svc.ollama.ok === true }
                }

                // 3 — voice
                ColumnLayout {
                    spacing: 12
                    RowLayout {
                        Text { Layout.fillWidth: true; text: qsTr("The voice: TTS BigLinux"); color: Theme.text; font.pixelSize: 22; font.weight: Font.Bold }
                        StateChip { text: wizard.voiceReady ? qsTr("Ready — %n voice(s)", "", (wizard.svc.tts.voices || []).length) : qsTr("Not ready yet")
                                    tone: wizard.voiceReady ? "ok" : "warn" }
                    }
                    Text {
                        Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Theme.textMuted; font.pixelSize: 13
                        text: qsTr("Pick an engine that is ready, or install one. Without a voice the character still answers in its speech bubble.")
                    }
                    EngineCards { compact: true }
                    RowLayout {
                        visible: wizard.voiceReady
                        spacing: 10
                        Text { Layout.fillWidth: true; text: qsTr("%1 will speak with: %2").arg(wizard.current.name || "").arg(backend.voiceFor(wizard.cfg.character) || "—")
                               color: Theme.text; font.pixelSize: 13; wrapMode: Text.WordWrap }
                        AppButton { iconName: "play"; text: qsTr("Hear it"); onClicked: backend.previewVoice("") }
                    }
                }

                // 4 — where
                ColumnLayout {
                    spacing: 12
                    Text { text: qsTr("Where should your character appear?"); color: Theme.text; font.pixelSize: 22; font.weight: Font.Bold }
                    DisplayModePicker { compact: true }
                    Text {
                        Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Theme.textMuted; font.pixelSize: 13
                        text: wizard.cfg.display.mode === "window" ? qsTr("The character is on your desktop now: drag it wherever you like.")
                            : qsTr("Later, the “Where to show” page gives you the address to paste in OBS — on this computer or another one.")
                    }
                }

                // 5 — done
                ColumnLayout {
                    spacing: 12
                    Text { text: qsTr("All set!"); color: Theme.text; font.pixelSize: 26; font.weight: Font.Bold }
                    RowLayout {
                        spacing: 8
                        StateChip { text: qsTr("AI"); tone: wizard.aiReady ? "ok" : "warn" }
                        StateChip { text: qsTr("Voice"); tone: wizard.voiceReady ? "ok" : "warn" }
                        StateChip { text: wizard.cfg.display.mode === "obs" ? qsTr("OBS") : wizard.cfg.display.mode === "window" ? qsTr("Desktop") : qsTr("OBS + desktop"); tone: "ok" }
                    }
                    Text {
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                        color: Theme.textMuted; font.pixelSize: 14; lineHeight: 1.3
                        text: qsTr("Try it now in Demo mode: type a message on the Dashboard as if you were a viewer. When you go live, add your platforms on the Streaming platforms page and press Start — ChatToon checks everything and tells you what is ready.")
                    }
                    AppButton {
                        visible: wizard.aiReady
                        iconName: "chat"; text: qsTr("Test the character now")
                        onClicked: { backend.testReply(qsTr("Hi! Are you ready for the live?"), qsTr("Test")); wizard.finish() }
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            AppButton { visible: wizard.step > 0; text: qsTr("Back"); onClicked: wizard.step-- }
            Item { Layout.fillWidth: true }
            Text {
                visible: (wizard.step === 2 && !wizard.aiReady) || (wizard.step === 3 && !wizard.voiceReady)
                text: qsTr("You can finish this later")
                color: Theme.textFaint; font.pixelSize: 12
            }
            AppButton {
                variant: "primary"
                text: wizard.step < wizard.last ? qsTr("Continue") : qsTr("Open the dashboard")
                onClicked: wizard.step < wizard.last ? wizard.step++ : wizard.finish()
            }
        }
    }
}
