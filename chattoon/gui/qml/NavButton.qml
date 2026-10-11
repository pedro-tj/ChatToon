import QtQuick
import QtQuick.Controls.Basic
import "."

ItemDelegate {
    id: control
    property string iconName
    property bool current: false
    property string badge: ""

    implicitHeight: 40
    leftPadding: 12
    hoverEnabled: true
    Accessible.name: text

    contentItem: Row {
        spacing: 12
        Icon { name: control.iconName; size: 18; color: control.current ? Theme.accent : Theme.textMuted; anchors.verticalCenter: parent.verticalCenter }
        Text {
            text: control.text
            color: control.current ? Theme.text : Theme.textMuted
            font.pixelSize: 13
            font.weight: control.current ? Font.DemiBold : Font.Normal
            anchors.verticalCenter: parent.verticalCenter
        }
        Rectangle {
            visible: control.badge !== ""
            anchors.verticalCenter: parent.verticalCenter
            width: Math.max(18, badgeText.implicitWidth + 10); height: 18; radius: 9
            color: Theme.accent2
            Text { id: badgeText; anchors.centerIn: parent; text: control.badge; color: "white"; font.pixelSize: 10; font.weight: Font.Bold }
        }
    }
    background: Rectangle {
        radius: Theme.radiusSmall
        color: control.current ? Theme.tint(Theme.accent, Theme.dark ? 0.16 : 0.12) : control.hovered ? Theme.hover : "transparent"
        Behavior on color { ColorAnimation { duration: Theme.animFast } }
        Rectangle {
            visible: control.current
            width: 3; height: 18; radius: 2
            anchors.verticalCenter: parent.verticalCenter
            gradient: Gradient {
                GradientStop { position: 0; color: Theme.accent }
                GradientStop { position: 1; color: Theme.accent2 }
            }
        }
        Rectangle {
            anchors { fill: parent; margins: -2 }
            radius: Theme.radiusSmall + 2
            color: "transparent"
            border.width: 2
            border.color: Theme.accent
            visible: control.visualFocus
        }
    }
}
