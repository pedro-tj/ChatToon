import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."

Page {
    id: page
    readonly property var cfg: backend.config
    readonly property var cur: cfg.current
    readonly property var anim: cfg.animation
    readonly property var current: backend.characters.find(c => c.id === cfg.character) || {}
    readonly property var expressions: [
        { e: "happy", l: qsTr("Happy") }, { e: "laugh", l: qsTr("Laugh") }, { e: "surprised", l: qsTr("Surprise") },
        { e: "confused", l: qsTr("Confused") }, { e: "annoyed", l: qsTr("Annoyed") }, { e: "celebrate", l: qsTr("Celebrate") }]

    title: qsTr("Characters")
    subtitle: qsTr("Pick who joins your stream. Each one has its own look, voice, gestures and sense of humour.")

    // ------------------------------------------------------------------- cast
    GridLayout {
        id: grid
        Layout.fillWidth: true
        columns: width > 1180 ? 3 : 2
        columnSpacing: 14
        rowSpacing: 14
        uniformCellWidths: true

        Repeater {
            model: backend.characters
            GlassCard {
                id: card
                objectName: "card-" + modelData.id
                required property var modelData
                readonly property bool selected: cfg.character === modelData.id
                Layout.fillWidth: true
                implicitHeight: 196
                border.width: selected ? 2 : 1
                border.color: selected ? modelData.color : hover.hovered ? Theme.borderStrong : Theme.border
                Behavior on border.color { ColorAnimation { duration: Theme.anim } }
                Accessible.role: Accessible.Button
                Accessible.name: qsTr("Use %1").arg(modelData.name)

                HoverHandler { id: hover }
                // behind the content: buttons on the card keep their own clicks
                MouseArea {
                    anchors.fill: parent
                    z: -1
                    cursorShape: card.selected ? Qt.ArrowCursor : Qt.PointingHandCursor
                    onClicked: if (!card.selected) backend.selectCharacter(card.modelData.id)
                }

                RowLayout {
                    anchors { fill: parent; margins: 12 }
                    spacing: 14

                    // thumbnail rendered from the 3D model, on a soft tint of the character colour
                    Rectangle {
                        Layout.preferredWidth: 150
                        Layout.fillHeight: true
                        radius: Theme.radiusSmall
                        gradient: Gradient {
                            GradientStop { position: 0; color: Theme.tint(Qt.lighter(card.modelData.color, 1), Theme.dark ? 0.24 : 0.28) }
                            GradientStop { position: 1; color: Theme.tint(Qt.lighter(card.modelData.color, 1), Theme.dark ? 0.04 : 0.06) }
                        }
                        Image {
                            id: thumb
                            anchors { fill: parent; margins: 6 }
                            source: "../assets/characters/" + card.modelData.id + ".png"
                            sourceSize: Qt.size(300, 340)
                            fillMode: Image.PreserveAspectFit
                            smooth: true
                            asynchronous: true
                            scale: hover.hovered ? 1.05 : 1
                            Behavior on scale { NumberAnimation { duration: Theme.anim; easing.type: Easing.OutCubic } }
                        }
                        Text {
                            anchors.centerIn: parent
                            visible: thumb.status === Image.Error
                            text: card.modelData.name.charAt(0)
                            color: card.modelData.color; font.pixelSize: 54; font.weight: Font.Black
                        }
                        AppButton {
                            objectName: "expand-" + card.modelData.id
                            anchors { right: parent.right; bottom: parent.bottom; margins: 6 }
                            compact: true; variant: "secondary"; iconName: "maximize"
                            tip: qsTr("See %1 up close").arg(card.modelData.name)
                            Accessible.name: tip
                            onClicked: zoom.show(card.modelData)
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        spacing: 6
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8
                            Text { text: card.modelData.name; color: Theme.text; font.pixelSize: 19; font.weight: Font.Bold }
                            Chip { visible: card.selected; text: qsTr("On air"); tone: Theme.success; iconName: "check" }
                            Item { Layout.fillWidth: true }
                        }
                        Text { text: card.modelData.species; color: Theme.dark ? card.modelData.color : Qt.darker(card.modelData.color, 1.9); font.pixelSize: 12; font.weight: Font.DemiBold
                               Layout.fillWidth: true; elide: Text.ElideRight; visible: text !== "" }
                        Text {
                            Layout.fillWidth: true
                            text: card.modelData.tagline
                            color: Theme.textMuted; font.pixelSize: 13; wrapMode: Text.WordWrap; maximumLineCount: 2; elide: Text.ElideRight
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 6
                            visible: voiceText.text !== ""
                            Icon { name: "mic"; size: 13; color: Theme.textFaint }
                            Text {
                                id: voiceText
                                Layout.fillWidth: true
                                text: { cfg; backend.services; return backend.voiceFor(card.modelData.id) }
                                color: Theme.textFaint; font.pixelSize: 12; elide: Text.ElideRight
                            }
                        }
                        Item { Layout.fillHeight: true }
                        AppButton {
                            Layout.fillWidth: true
                            compact: true
                            variant: card.selected ? "secondary" : "primary"
                            enabled: !card.selected
                            text: card.selected ? qsTr("Selected") : qsTr("Use %1").arg(card.modelData.name)
                            onClicked: backend.selectCharacter(card.modelData.id)
                        }
                    }
                }
            }
        }
    }

    // --------------------------------------------------------- live try-out
    RowLayout {
        Layout.fillWidth: true
        spacing: 16

        Preview {
            id: live
            Layout.fillWidth: true
            Layout.preferredWidth: 3
            Layout.preferredHeight: 540
            Layout.alignment: Qt.AlignTop
            url: backend.runtimeState.overlayUrl
            Rectangle {
                anchors { left: parent.left; top: parent.top; margins: 14 }
                width: liveRow.implicitWidth + 20; height: 30; radius: 15
                color: Qt.rgba(0, 0, 0, 0.45)
                RowLayout {
                    id: liveRow
                    anchors.centerIn: parent
                    spacing: 8
                    Rectangle { width: 8; height: 8; radius: 4; color: page.current.color || Theme.accent }
                    Text { text: qsTr("Live preview — exactly what OBS shows"); color: "white"; font.pixelSize: 12; font.weight: Font.DemiBold }
                }
            }
        }

        Section {
            Layout.preferredWidth: 2
            Layout.alignment: Qt.AlignTop
            title: qsTr("Try %1").arg(page.current.name || "")
            iconName: "wand"
            description: qsTr("Everything here plays on the live overlay, with the real voice and lip sync.")

            Text { text: qsTr("Expressions"); color: Theme.textMuted; font.pixelSize: 12; font.weight: Font.DemiBold }
            Flow {
                Layout.fillWidth: true
                spacing: 6
                Repeater {
                    model: page.expressions
                    AppButton { required property var modelData; compact: true; text: modelData.l; onClicked: backend.react(modelData.e) }
                }
            }
            Text { text: qsTr("Gestures"); color: Theme.textMuted; font.pixelSize: 12; font.weight: Font.DemiBold }
            Flow {
                Layout.fillWidth: true
                spacing: 6
                Repeater {
                    model: page.current.gestures || []
                    AppButton { required property var modelData; compact: true; iconName: "hand"; text: modelData.label; onClicked: backend.gesture(modelData.id) }
                }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }
            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                Icon { name: "mic"; size: 15; color: Theme.textMuted }
                Text {
                    Layout.fillWidth: true
                    text: { cfg; backend.services; const v = backend.voiceFor(cfg.character); return v || qsTr("No voice available") }
                    color: Theme.text; font.pixelSize: 13; elide: Text.ElideRight
                }
                AppButton { compact: true; iconName: "play"; text: qsTr("Test voice"); enabled: backend.services.tts.ok === true
                            onClicked: backend.previewVoice(cfg.current.voice_id) }
            }
            Text { text: qsTr("Simulate a viewer message"); color: Theme.textMuted; font.pixelSize: 12; font.weight: Font.DemiBold }
            RowLayout {
                Layout.fillWidth: true
                spacing: 6
                AppTextField { id: simAuthor; Layout.preferredWidth: 110; text: qsTr("Viewer"); placeholderText: qsTr("Name") }
                AppTextField {
                    id: simText
                    Layout.fillWidth: true
                    placeholderText: qsTr("Good evening! Which Linux distro do you recommend?")
                    onAccepted: simSend.clicked()
                }
                AppButton {
                    id: simSend
                    compact: true; variant: "primary"; iconName: "send"
                    tip: qsTr("Reads the message (if enabled) and answers it with the AI")
                    Accessible.name: qsTr("Send")
                    onClicked: { backend.testReply(simText.text || simText.placeholderText, simAuthor.text); simText.text = "" }
                }
            }
            Text { text: qsTr("Simulate a reply"); color: Theme.textMuted; font.pixelSize: 12; font.weight: Font.DemiBold }
            RowLayout {
                Layout.fillWidth: true
                spacing: 6
                AppTextField { id: sayText; Layout.fillWidth: true; placeholderText: qsTr("Make it say exactly this…"); onAccepted: sayBtn.clicked() }
                AppButton { id: sayBtn; compact: true; iconName: "volume"; text: qsTr("Say"); enabled: sayText.text !== ""
                            onClicked: { backend.say(sayText.text, "happy"); sayText.text = "" } }
            }
            AppButton { compact: true; variant: "ghost"; iconName: "sparkles"; text: qsTr("Tune the personality"); onClicked: win.go("personality") }
        }
    }

    // ------------------------------------------------------- idle animation
    Section {
        title: qsTr("Idle animations")
        iconName: "activity"
        description: qsTr("While nobody is talking, the character breathes, looks around and makes small gestures. Applies to all characters.")
        SettingRow {
            label: qsTr("Move while idle")
            description: qsTr("When off, only breathing and blinking remain.")
            AppSwitch { checked: page.anim.idle; onToggled: backend.setConfig("animation.idle", checked); Accessible.name: qsTr("Move while idle") }
        }
        SettingRow {
            label: qsTr("Intensity")
            Segmented {
                enabled: page.anim.idle
                model: [{ value: "subtle", label: qsTr("Subtle") }, { value: "normal", label: qsTr("Normal") }, { value: "lively", label: qsTr("Lively") }]
                current: page.anim.intensity
                onActivated: v => backend.setConfig("animation.intensity", v)
            }
        }
        SettingRow {
            label: qsTr("Gesture frequency")
            Segmented {
                enabled: page.anim.idle
                model: [{ value: "low", label: qsTr("Low") }, { value: "normal", label: qsTr("Normal") }, { value: "high", label: qsTr("High") }]
                current: page.anim.frequency
                onActivated: v => backend.setConfig("animation.frequency", v)
            }
        }
        SettingRow {
            label: qsTr("Reduce motion")
            description: qsTr("No jumps or spins, softer and slower movement. For viewers sensitive to motion.")
            AppSwitch { checked: page.anim.reduce_motion; onToggled: backend.setConfig("animation.reduce_motion", checked); Accessible.name: qsTr("Reduce motion") }
        }
    }

    Section {
        title: qsTr("Look and catchphrases")
        iconName: "palette"
        description: qsTr("Applies to the selected character.")
        SettingRow {
            label: qsTr("Main colour")
            description: page.current.id === "tux" ? qsTr("For Tux it colours the band of the top hat.") : ""
            Row {
                spacing: 6
                Repeater {
                    model: ["", "#ff7eb6", "#ff9f43", "#ffd93d", "#6fd65a", "#4ecdc4", "#5b8cff", "#a66bff"]
                    Rectangle {
                        required property string modelData
                        width: 28; height: 28; radius: 14
                        color: modelData || Theme.hover
                        border.width: (cur.color || "") === modelData ? 3 : 1
                        border.color: (cur.color || "") === modelData ? Theme.text : Theme.border
                        Text { anchors.centerIn: parent; visible: modelData === ""; text: "A"; color: Theme.textMuted; font.pixelSize: 11 }
                        ToolTip.visible: tap.hovered
                        ToolTip.text: modelData === "" ? qsTr("Default colour") : modelData
                        HoverHandler { id: tap; cursorShape: Qt.PointingHandCursor }
                        TapHandler { onTapped: backend.setConfig("current.color", modelData) }
                        Accessible.name: modelData === "" ? qsTr("Default colour") : modelData
                    }
                }
            }
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 6
            Text { text: qsTr("Catchphrases (one per line, used now and then)"); color: Theme.text; font.pixelSize: 13; font.weight: Font.Medium }
            AppTextArea {
                Layout.fillWidth: true
                text: (cur.catchphrases || []).join("\n")
                placeholderText: qsTr("E.g.: Minhocou!")
                onEditingFinished: backend.setConfig("current.catchphrases", text)
            }
        }
    }

    // ------------------------------------------------------- enlarged view
    Popup {
        id: zoom
        property var who: ({})
        function show(c) { who = c; open() }
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: Math.min(parent.width - 80, 1000)
        height: Math.min(parent.height - 80, 760)
        modal: true
        padding: 16
        background: Rectangle { radius: Theme.radius; color: Theme.surfaceStrong; border.width: 1; border.color: Theme.borderStrong }

        ColumnLayout {
            anchors.fill: parent
            spacing: 12
            RowLayout {
                Layout.fillWidth: true
                spacing: 10
                Rectangle { width: 12; height: 12; radius: 6; color: zoom.who.color || Theme.accent }
                Text { text: zoom.who.name || ""; color: Theme.text; font.pixelSize: 20; font.weight: Font.Bold }
                Text { text: zoom.who.species || ""; color: Theme.textMuted; font.pixelSize: 13 }
                Chip { text: qsTr("Animation demo · simulated lip sync"); tone: Theme.textMuted; iconName: "info" }
                Item { Layout.fillWidth: true }
                AppButton {
                    variant: "primary"; compact: true
                    visible: zoom.who.id !== cfg.character
                    text: qsTr("Use %1").arg(zoom.who.name || "")
                    onClicked: { backend.selectCharacter(zoom.who.id); zoom.close() }
                }
                AppButton { objectName: "zoom-close"; compact: true; variant: "ghost"; iconName: "x"; tip: qsTr("Close"); Accessible.name: qsTr("Close"); onClicked: zoom.close() }
            }
            Preview {
                id: big
                Layout.fillWidth: true
                Layout.fillHeight: true
                active: zoom.visible
                url: backend.runtimeState.overlayUrl
                query: "demo=" + (zoom.who.id || "worm") + "&quality=high&idle=1" + (zoom.who.id === cfg.character && cfg.current.color ? "&color=" + encodeURIComponent(cfg.current.color) : "")
            }
            Flow {
                Layout.fillWidth: true
                spacing: 6
                Repeater {
                    model: page.expressions
                    AppButton { required property var modelData; compact: true; text: modelData.l; onClicked: big.run("chattoonDemo.emotion('" + modelData.e + "')") }
                }
                Repeater {
                    model: zoom.who.gestures || []
                    AppButton { required property var modelData; compact: true; iconName: "hand"; text: modelData.label; onClicked: big.run("chattoonDemo.gesture('" + modelData.id + "')") }
                }
                AppButton { compact: true; iconName: "chat"; text: qsTr("Talk")
                            onClicked: big.run("chattoonDemo.talk(" + JSON.stringify(qsTr("Hi! This is how I move when I talk.")) + ", 3)") }
            }
        }
    }
}
