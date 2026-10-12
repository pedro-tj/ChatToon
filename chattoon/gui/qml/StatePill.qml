import QtQuick
import QtQuick.Layouts
import "."

// Connection state of a source: icon + words + tone (never colour alone).
Rectangle {
    id: root
    property string value: "idle"
    property string text: Status.label(value)
    readonly property color tone: Status.tone(value)

    implicitHeight: 24
    implicitWidth: row.implicitWidth + 18
    radius: height / 2
    color: Theme.tint(tone, Theme.dark ? 0.16 : 0.12)
    border.width: 1
    border.color: Theme.tint(tone, 0.35)

    RowLayout {
        id: row
        anchors.centerIn: parent
        spacing: 5
        Icon {
            name: Status.icon(root.value)
            size: 12
            color: root.tone
            RotationAnimation on rotation {
                running: Status.busy(root.value)
                alwaysRunToEnd: true  // stops upright
                from: 0; to: 360; duration: 1100; loops: Animation.Infinite
            }
        }
        Text { text: root.text; color: root.tone; font.pixelSize: 11; font.weight: Font.DemiBold }
    }
    Accessible.role: Accessible.StaticText
    Accessible.name: text
}
