import QtQuick
import QtQuick.Layouts
import "."

GlassCard {
    id: root
    property string title
    property string description
    property string iconName
    default property alias content: body.data
    property alias actions: actionSlot.data

    Layout.fillWidth: true
    implicitHeight: col.implicitHeight + 36

    ColumnLayout {
        id: col
        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 18 }
        spacing: 14

        RowLayout {
            Layout.fillWidth: true
            visible: root.title !== ""
            spacing: 10
            Rectangle {
                visible: root.iconName !== ""
                width: 30; height: 30; radius: 9
                color: Theme.tint(Theme.accent, Theme.dark ? 0.18 : 0.12)
                Icon { anchors.centerIn: parent; name: root.iconName; size: 16; color: Theme.accent }
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 1
                Text { text: root.title; color: Theme.text; font.pixelSize: 15; font.weight: Font.DemiBold }
                Text {
                    Layout.fillWidth: true
                    text: root.description
                    visible: text !== ""
                    color: Theme.textFaint
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                }
            }
            Row { id: actionSlot; spacing: 6 }
        }
        ColumnLayout { id: body; Layout.fillWidth: true; spacing: 14 }
    }
}
