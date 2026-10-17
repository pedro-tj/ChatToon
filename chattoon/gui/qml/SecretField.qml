import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

// A value that may be sensitive (an address with a token, an IP…): shown masked, copied whole.
// The eye reveals it for 15 seconds after a warning (Main › reveal dialog).
RowLayout {
    id: root
    property string value
    property string shown: value
    property string revealKey
    property bool canReveal: revealKey !== "" && shown !== value
    property bool canOpen: false
    property string label

    spacing: 8
    AppTextField {
        Layout.fillWidth: true
        readOnly: true
        text: root.shown
        font.family: Theme.mono
        font.pixelSize: 13
        Accessible.name: root.label
        Accessible.description: root.shown !== root.value ? qsTr("Hidden for privacy") : ""
    }
    AppButton {
        visible: root.revealKey !== ""
        iconName: Privacy.isRevealed(root.revealKey) ? "eyeOff" : "eye"
        enabled: root.value !== "" && (root.canReveal || Privacy.isRevealed(root.revealKey))
        tip: Privacy.isRevealed(root.revealKey) ? qsTr("Hide") : qsTr("Show for 15 seconds")
        Accessible.name: tip
        onClicked: Privacy.isRevealed(root.revealKey) ? Privacy.hideAll() : win.askReveal(root.revealKey)
    }
    AppButton {
        variant: "primary"; iconName: "copy"; text: qsTr("Copy")
        enabled: root.value !== ""
        onClicked: backend.copyText(root.value)
    }
    AppButton {
        visible: root.canOpen
        iconName: "external"; tip: qsTr("Open in the browser"); Accessible.name: tip
        enabled: root.value !== ""
        onClicked: backend.openUrl(root.value)
    }
}
