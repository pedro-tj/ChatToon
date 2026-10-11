import QtQuick
import QtQuick.Controls.Basic
import "."

ScrollView {
    id: root
    property alias text: area.text
    property alias placeholderText: area.placeholderText
    signal editingFinished()

    implicitHeight: Math.max(84, Math.min(180, area.contentHeight + 24))
    clip: true

    TextArea {
        id: area
        wrapMode: TextArea.Wrap
        color: Theme.text
        placeholderTextColor: Theme.textFaint
        selectionColor: Theme.accent
        selectedTextColor: Theme.accentText
        font.pixelSize: 13
        padding: 10
        onEditingFinished: root.editingFinished()
        Accessible.name: root.placeholderText
        background: Rectangle {
            radius: Theme.radiusSmall
            color: Theme.field
            border.width: area.activeFocus ? 2 : 1
            border.color: area.activeFocus ? Theme.accent : Theme.border
        }
    }
}
