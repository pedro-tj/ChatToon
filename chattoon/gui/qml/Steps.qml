import QtQuick
import QtQuick.Layouts
import "."

// Numbered instructions (model = list of strings).
ColumnLayout {
    id: root
    property var model: []
    spacing: 10
    Layout.fillWidth: true
    Repeater {
        model: root.model
        RowLayout {
            required property string modelData
            required property int index
            Layout.fillWidth: true
            spacing: 10
            Rectangle {
                Layout.alignment: Qt.AlignTop
                width: 24; height: 24; radius: 12
                color: Theme.tint(Theme.accent, 0.18)
                Text { anchors.centerIn: parent; text: index + 1; color: Theme.accent; font.pixelSize: 12; font.weight: Font.Bold }
            }
            Text { Layout.fillWidth: true; text: modelData; color: Theme.text; font.pixelSize: 13; wrapMode: Text.WordWrap; textFormat: Text.PlainText }
        }
    }
}
