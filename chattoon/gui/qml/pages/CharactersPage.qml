import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."

Page {
    id: page
    readonly property var cfg: backend.config
    readonly property var cur: cfg.current

    title: qsTr("Characters")
    subtitle: qsTr("Pick who joins your stream. Each one has its own look, voice and sense of humour.")

    RowLayout {
        Layout.fillWidth: true
        spacing: 16
        Repeater {
            model: backend.characters
            GlassCard {
                id: card
                required property var modelData
                readonly property bool selected: cfg.character === modelData.id
                Layout.fillWidth: true
                Layout.preferredWidth: 1
                implicitHeight: cardCol.implicitHeight + 24
                border.width: selected ? 2 : 1
                border.color: selected ? modelData.color : Theme.border
                Behavior on border.color { ColorAnimation { duration: Theme.anim } }

                ColumnLayout {
                    id: cardCol
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 12 }
                    spacing: 10
                    Preview {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 260
                        url: backend.runtimeState.overlayUrl
                        query: "demo=" + card.modelData.id + "&emotion=cycle&talk=1&bubble=0&quality=medium"
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Rectangle { width: 12; height: 12; radius: 6; color: card.modelData.color }
                        Text { Layout.fillWidth: true; text: card.modelData.name; color: Theme.text; font.pixelSize: 18; font.weight: Font.Bold }
                        Chip { visible: card.selected; text: qsTr("On air"); tone: Theme.success; iconName: "check" }
                    }
                    Text { Layout.fillWidth: true; text: card.modelData.persona; color: Theme.textMuted; font.pixelSize: 12; wrapMode: Text.WordWrap; maximumLineCount: 5; elide: Text.ElideRight }
                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: example.implicitHeight + 18
                        radius: Theme.radiusSmall
                        color: Theme.hover
                        Text {
                            id: example
                            anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; margins: 10 }
                            text: "“" + card.modelData.exampleIn + "”\n→ " + card.modelData.example
                            color: Theme.text; font.pixelSize: 12; font.italic: true; wrapMode: Text.WordWrap
                        }
                    }
                    AppButton {
                        Layout.fillWidth: true
                        variant: card.selected ? "secondary" : "primary"
                        enabled: !card.selected
                        text: card.selected ? qsTr("Selected") : qsTr("Use %1").arg(card.modelData.name)
                        onClicked: backend.selectCharacter(card.modelData.id)
                    }
                }
            }
        }
    }

    Section {
        title: qsTr("Look and catchphrases")
        iconName: "palette"
        description: qsTr("Applies to the selected character.")
        SettingRow {
            label: qsTr("Main colour")
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
}
