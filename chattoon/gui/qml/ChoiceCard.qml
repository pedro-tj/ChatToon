import QtQuick
import QtQuick.Layouts
import "."

// A big, friendly option ("OBS Studio — ideal for live streams"). Keyboard: Tab + Space/Enter.
Rectangle {
    id: root
    property string title
    property string description
    property string iconName
    property bool selected: false
    property bool enabledChoice: true
    signal chosen()

    implicitHeight: col.implicitHeight + 28
    Layout.fillWidth: true
    radius: Theme.radius
    color: selected ? Theme.tint(Theme.accent, Theme.dark ? 0.16 : 0.1) : hover.hovered ? Theme.hover : Theme.field
    border.width: selected || activeFocus ? 2 : 1
    border.color: selected ? Theme.accent : activeFocus ? Theme.accent : Theme.border
    opacity: enabledChoice ? 1 : 0.5
    activeFocusOnTab: true
    Accessible.role: Accessible.RadioButton
    Accessible.name: title
    Accessible.description: description
    Accessible.checked: selected
    Keys.onSpacePressed: if (enabledChoice) chosen()
    Keys.onReturnPressed: if (enabledChoice) chosen()
    Behavior on color { ColorAnimation { duration: Theme.animFast } }

    HoverHandler { id: hover; cursorShape: root.enabledChoice ? Qt.PointingHandCursor : Qt.ArrowCursor }
    TapHandler { enabled: root.enabledChoice; onTapped: root.chosen() }

    ColumnLayout {
        id: col
        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 14 }
        spacing: 6
        RowLayout {
            spacing: 10
            Rectangle {
                width: 36; height: 36; radius: 11
                color: Theme.tint(Theme.accent, root.selected ? 0.24 : 0.12)
                Icon { anchors.centerIn: parent; name: root.iconName; size: 18; color: Theme.accent }
            }
            Text { Layout.fillWidth: true; text: root.title; color: Theme.text; font.pixelSize: 15; font.weight: Font.DemiBold; wrapMode: Text.WordWrap }
            Icon { visible: root.selected; name: "checkCircle"; size: 20; color: Theme.accent }
        }
        Text {
            Layout.fillWidth: true
            text: root.description; visible: text !== ""
            color: Theme.textMuted; font.pixelSize: 12; wrapMode: Text.WordWrap
        }
    }
}
