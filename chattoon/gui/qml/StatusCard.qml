import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

GlassCard {
    id: root
    property string iconName
    property string title
    property string value
    property string detail
    property string status: "idle"  // ok | warn | error | busy | idle
    signal clicked()

    readonly property color tone: status === "ok" ? Theme.success : status === "warn" ? Theme.warning
                                : status === "error" ? Theme.danger : status === "busy" ? Theme.accent : Theme.textFaint
    implicitHeight: 86
    Layout.fillWidth: true

    HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
    TapHandler { onTapped: root.clicked() }
    ToolTip.visible: hover.hovered && root.detail !== ""
    ToolTip.text: root.detail
    ToolTip.delay: 500

    RowLayout {
        anchors { fill: parent; margins: 14 }
        spacing: 12
        Rectangle {
            width: 40; height: 40; radius: 12
            color: Theme.tint(root.tone, Theme.dark ? 0.16 : 0.12)
            Icon { anchors.centerIn: parent; name: root.iconName; size: 20; color: root.tone }
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            Text { text: root.title; color: Theme.textMuted; font.pixelSize: 12 }
            RowLayout {
                spacing: 6
                Rectangle { width: 8; height: 8; radius: 4; color: root.tone; visible: root.status !== "idle" }
                Text {
                    Layout.fillWidth: true
                    text: root.value
                    color: Theme.text
                    font.pixelSize: 15
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }
            }
        }
    }
}
