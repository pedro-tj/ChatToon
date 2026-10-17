import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

// Controls of the character window on the desktop, with what this session really allows.
ColumnLayout {
    id: root
    property bool compact: false
    readonly property var ctl: backend.characterWindow
    readonly property var caps: ctl.capabilities
    readonly property var d: backend.config.display
    spacing: 12
    Layout.fillWidth: true

    function platformText() {
        return caps.platform === "wayland" ? (caps.kwin ? qsTr("Wayland with KDE Plasma") : qsTr("Wayland"))
             : caps.platform === "x11" ? (caps.kwin ? qsTr("X11 with KDE Plasma") : qsTr("X11")) : caps.platform
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: 10
        StateChip { text: root.ctl.isOpen ? qsTr("On the desktop") : qsTr("Hidden"); tone: root.ctl.isOpen ? "ok" : "idle"
                    iconName: root.ctl.isOpen ? "checkCircle" : "eyeOff" }
        Item { Layout.fillWidth: true }
        AppButton {
            variant: root.ctl.isOpen ? "secondary" : "primary"
            iconName: root.ctl.isOpen ? "eyeOff" : "eye"
            text: root.ctl.isOpen ? qsTr("Hide the character") : qsTr("Show the character")
            onClicked: root.ctl.toggle()
        }
    }
    Text {
        Layout.fillWidth: true
        visible: !root.compact
        text: qsTr("Drag the character to move it. Right-click opens its menu. Ctrl + mouse wheel changes the size.")
        color: Theme.textMuted; font.pixelSize: 12; wrapMode: Text.WordWrap
    }
    SettingRow {
        label: qsTr("Size")
        Segmented {
            model: [{ value: "small", label: qsTr("Small") }, { value: "medium", label: qsTr("Normal") }, { value: "large", label: qsTr("Large") }]
            current: root.d.size
            onActivated: v => root.ctl.setSize(v)
        }
    }
    SettingRow {
        visible: !root.compact
        label: qsTr("Keep above other windows")
        description: root.caps.keepAbove ? "" : qsTr("This desktop does not let apps stay above others. In KDE Plasma it works automatically; elsewhere use your window manager's “always on top”.")
        AppSwitch { checked: root.d.keep_above; enabled: root.caps.keepAbove; onToggled: root.ctl.setKeepAbove(checked); Accessible.name: qsTr("Keep above other windows") }
    }
    SettingRow {
        visible: !root.compact
        label: qsTr("Lock position and size")
        AppSwitch { checked: root.d.locked; onToggled: root.ctl.setLocked(checked); Accessible.name: qsTr("Lock position and size") }
    }
    SettingRow {
        visible: !root.compact
        label: qsTr("Speech bubble")
        AppSwitch { checked: root.d.show_bubble; onToggled: root.ctl.setShowBubble(checked); Accessible.name: qsTr("Speech bubble") }
    }
    SettingRow {
        visible: !root.compact
        label: qsTr("Let clicks pass through the character")
        description: qsTr("The character becomes untouchable: clicks go to the windows below. Turn it off here to drag it again.")
        AppSwitch { checked: root.d.click_through; enabled: root.caps.clickThrough; onToggled: root.ctl.setClickThrough(checked); Accessible.name: qsTr("Let clicks pass through the character") }
    }
    SettingRow {
        visible: !root.compact && backend.config.advanced
        label: qsTr("Hide from the taskbar")
        description: root.caps.skipTaskbar ? qsTr("Off by default, so the character's icon is easy to find.") : qsTr("Not available on this desktop.")
        AppSwitch { checked: root.d.skip_taskbar; enabled: root.caps.skipTaskbar; onToggled: root.ctl.setSkipTaskbar(checked); Accessible.name: qsTr("Hide from the taskbar") }
    }
    RowLayout {
        Layout.fillWidth: true
        visible: !root.compact && root.caps.position
        spacing: 8
        Text { text: qsTr("Screen"); color: Theme.text; font.pixelSize: 13; font.weight: Font.Medium }
        AppCombo {
            Layout.fillWidth: true
            enabled: root.ctl.screens.length > 1
            textRole: "label"; valueRole: "name"
            model: root.ctl.screens
            currentIndex: Math.max(0, root.ctl.screens.findIndex(s => s.name === root.d.screen))
            onActivated: root.ctl.moveToScreen(currentValue)
            Accessible.name: qsTr("Screen")
        }
        AppButton { iconName: "pin"; text: qsTr("Back to the corner"); onClicked: root.ctl.resetPosition() }
    }
    Text {
        Layout.fillWidth: true
        visible: !root.compact
        wrapMode: Text.WordWrap
        color: Theme.textFaint; font.pixelSize: 11
        text: qsTr("Session: %1.").arg(root.platformText()) + " "
              + (root.caps.position ? qsTr("The position is remembered.") : qsTr("This desktop places the window itself; the position is not remembered."))
              + " " + (root.caps.dynamicIcon ? qsTr("The window carries the character's icon; a taskbar that groups ChatToon's windows shows the ChatToon icon instead.")
                                             : qsTr("The taskbar shows the ChatToon icon."))
    }
}
