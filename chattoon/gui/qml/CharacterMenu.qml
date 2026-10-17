import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

// Right-click panel of the character on the desktop: who it is, quick switches, size,
// another character, and the way back to ChatToon. Shown in its own window (popupType),
// so it is never cut by a small character window.
Popup {
    id: root
    required property var controller
    readonly property var caps: controller.capabilities
    readonly property var disp: backend.config.display
    readonly property var current: controller.characters.find(c => c.id === controller.characterId) || {}

    // Drawn inside the character window, at the click, whenever it fits (the normal and large
    // sizes): exact position on every compositor. The small window gets its own popup window.
    function openAt(px, py) {
        const w = parent ? parent.width : width, h = parent ? parent.height : implicitHeight
        const fits = w >= width + 12 && h >= implicitHeight + 12
        popupType = fits ? Popup.Item : Popup.Window
        x = Math.round(fits ? Math.max(6, Math.min(px, w - width - 6)) : px)
        y = Math.round(fits ? Math.max(6, Math.min(py - 20, h - implicitHeight - 6)) : py)
        open()
    }
    onOpened: controller.menuOpen(true)
    onClosed: controller.menuOpen(false)

    popupType: Popup.Item
    width: 320
    padding: 14
    focus: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

    enter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.animFast } }
    exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.animFast } }

    background: Rectangle {
        radius: Theme.radius + 2
        color: Theme.surfaceStrong
        border.width: 1
        border.color: Theme.borderStrong
    }

    // a quick on/off switch: icon + words, highlighted when on (never colour alone)
    component Tile: Rectangle {
        id: tile
        property string iconName
        property string label
        property bool on: false
        property bool available: true
        signal toggled()

        Layout.fillWidth: true
        implicitHeight: 64
        radius: Theme.radiusSmall
        color: on ? Theme.tint(Theme.accent, Theme.dark ? 0.22 : 0.14) : tileHover.hovered ? Theme.hover : Theme.field
        border.width: on || activeFocus ? 1.5 : 1
        border.color: on || activeFocus ? Theme.accent : Theme.border
        opacity: available ? 1 : 0.45
        activeFocusOnTab: available
        Accessible.role: Accessible.CheckBox
        Accessible.name: label
        Accessible.checked: on
        Keys.onSpacePressed: if (available) toggled()
        Behavior on color { ColorAnimation { duration: Theme.animFast } }

        HoverHandler { id: tileHover; enabled: tile.available; cursorShape: Qt.PointingHandCursor }
        TapHandler { enabled: tile.available; onTapped: tile.toggled() }
        ColumnLayout {
            anchors.centerIn: parent
            width: parent.width - 12
            spacing: 4
            Icon { Layout.alignment: Qt.AlignHCenter; name: tile.iconName; size: 18; color: tile.on ? Theme.accent : Theme.textMuted }
            Text {
                Layout.fillWidth: true
                horizontalAlignment: Text.AlignHCenter
                text: tile.label
                color: tile.on ? Theme.accent : Theme.text
                font.pixelSize: 11
                font.weight: tile.on ? Font.DemiBold : Font.Normal
                wrapMode: Text.WordWrap
                maximumLineCount: 2
            }
        }
    }

    // an action row of the footer
    component Action: Rectangle {
        id: act
        property string iconName
        property string label
        property color tone: Theme.text
        signal triggered()

        Layout.fillWidth: true
        implicitHeight: 38
        radius: Theme.radiusSmall
        color: actHover.hovered || activeFocus ? Theme.hover : "transparent"
        activeFocusOnTab: true
        Accessible.role: Accessible.Button
        Accessible.name: label
        Keys.onReturnPressed: act.triggered()
        Keys.onSpacePressed: act.triggered()
        HoverHandler { id: actHover; cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: act.triggered() }
        RowLayout {
            anchors { fill: parent; leftMargin: 10; rightMargin: 10 }
            spacing: 10
            Icon { name: act.iconName; size: 16; color: act.tone }
            Text { Layout.fillWidth: true; text: act.label; color: act.tone; font.pixelSize: 13 }
        }
    }

    contentItem: ColumnLayout {
        spacing: 12

        // who is on the desktop
        RowLayout {
            Layout.fillWidth: true
            spacing: 12
            Rectangle {
                width: 52; height: 52; radius: 26
                color: Theme.tint(root.current.color || Theme.accent, 0.2)
                border.width: 2
                border.color: root.current.color || Theme.accent
                Image {
                    anchors.centerIn: parent
                    width: 42; height: 46
                    source: "assets/characters/" + root.controller.characterId + ".png"
                    sourceSize: Qt.size(84, 92)
                    fillMode: Image.PreserveAspectFit
                }
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2
                Text { text: root.current.name || ""; color: Theme.text; font.pixelSize: 17; font.weight: Font.Bold }
                Text { text: qsTr("On your desktop"); color: Theme.textMuted; font.pixelSize: 12 }
            }
            AppButton {
                compact: true; variant: "ghost"; iconName: "x"
                Accessible.name: qsTr("Close")
                onClicked: root.close()
            }
        }

        // another character
        Text { text: qsTr("Character"); color: Theme.textFaint; font.pixelSize: 11; font.weight: Font.DemiBold; font.capitalization: Font.AllUppercase }
        RowLayout {
            Layout.fillWidth: true
            spacing: 6
            Repeater {
                model: root.controller.characters
                Rectangle {
                    id: pick
                    required property var modelData
                    readonly property bool chosen: root.controller.characterId === modelData.id
                    Layout.fillWidth: true
                    Layout.preferredHeight: width
                    radius: width / 2
                    color: chosen ? Theme.tint(modelData.color, 0.28) : pickHover.hovered ? Theme.hover : Theme.field
                    border.width: chosen || activeFocus ? 2 : 1
                    border.color: chosen ? modelData.color : activeFocus ? Theme.accent : Theme.border
                    activeFocusOnTab: true
                    Accessible.role: Accessible.RadioButton
                    Accessible.name: modelData.name
                    Accessible.checked: chosen
                    Keys.onSpacePressed: backend.selectCharacter(modelData.id)
                    Image {
                        anchors.centerIn: parent
                        width: parent.width * 0.78; height: parent.height * 0.82
                        source: "assets/characters/" + pick.modelData.id + ".png"
                        sourceSize: Qt.size(84, 92)
                        fillMode: Image.PreserveAspectFit
                    }
                    HoverHandler { id: pickHover; cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: backend.selectCharacter(pick.modelData.id) }
                    ToolTip.visible: pickHover.hovered
                    ToolTip.text: modelData.name
                    ToolTip.delay: 300
                }
            }
        }

        // size
        RowLayout {
            Layout.fillWidth: true
            Text { Layout.fillWidth: true; text: qsTr("Size"); color: Theme.textFaint; font.pixelSize: 11; font.weight: Font.DemiBold; font.capitalization: Font.AllUppercase }
            Segmented {
                model: [{ value: "small", label: qsTr("Small") }, { value: "medium", label: qsTr("Normal") }, { value: "large", label: qsTr("Large") }]
                current: root.disp.size
                onActivated: v => root.controller.setSize(v)
            }
        }

        // quick switches
        GridLayout {
            Layout.fillWidth: true
            columns: 2
            columnSpacing: 8
            rowSpacing: 8
            Tile {
                iconName: "pin"; label: qsTr("Above other windows")
                on: root.disp.keep_above; available: root.caps.keepAbove
                onToggled: root.controller.setKeepAbove(!on)
            }
            Tile {
                iconName: "lock"; label: qsTr("Lock in place")
                on: root.disp.locked
                onToggled: root.controller.setLocked(!on)
            }
            Tile {
                iconName: "chat"; label: qsTr("Speech bubble")
                on: root.disp.show_bubble
                onToggled: root.controller.setShowBubble(!on)
            }
            Tile {
                iconName: "pointer"; label: qsTr("Clicks pass through")
                on: root.disp.click_through; available: root.caps.clickThrough
                onToggled: { root.close(); root.controller.setClickThrough(!on) }
            }
        }
        Text {
            Layout.fillWidth: true
            text: qsTr("With clicks passing through, turn it off again in ChatToon › Where to show.")
            color: Theme.textFaint; font.pixelSize: 11; wrapMode: Text.WordWrap
        }

        // other screens
        RowLayout {
            Layout.fillWidth: true
            visible: root.caps.position && root.controller.screens.length > 1
            spacing: 6
            Text { text: qsTr("Screen"); color: Theme.textFaint; font.pixelSize: 11; font.weight: Font.DemiBold; font.capitalization: Font.AllUppercase }
            Item { Layout.fillWidth: true }
            Repeater {
                model: root.controller.screens
                AppButton {
                    required property var modelData
                    required property int index
                    compact: true
                    text: String(index + 1) + (modelData.primary ? " ★" : "")
                    tip: modelData.label
                    Accessible.name: modelData.label
                    variant: modelData.name === root.disp.screen ? "primary" : "secondary"
                    onClicked: root.controller.moveToScreen(modelData.name)
                }
            }
        }

        Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            Action { iconName: "dashboard"; label: qsTr("Open ChatToon"); onTriggered: { root.close(); root.controller.raiseMain() } }
            Action { iconName: "eyeOff"; label: qsTr("Hide the character"); onTriggered: { root.close(); root.controller.hide() } }
            Action { iconName: "power"; label: qsTr("Quit ChatToon"); tone: Theme.danger; onTriggered: Qt.quit() }
        }
    }
}
