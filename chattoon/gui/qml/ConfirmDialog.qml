import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

// One question before something important (install, password, reveal…). Main owns one:
// win.ask({ title, message, details: [..], confirm, danger, icon }, function () { … })
Popup {
    id: root
    property string title
    property string message
    property var details: []
    property string confirmText: qsTr("Continue")
    property bool danger: false
    property string iconName: "info"
    property var onYes: null

    function ask(opts, callback) {
        title = opts.title || ""
        message = opts.message || ""
        details = opts.details || []
        confirmText = opts.confirm || qsTr("Continue")
        danger = !!opts.danger
        iconName = opts.icon || "info"
        onYes = callback
        open()
    }

    parent: Overlay.overlay
    anchors.centerIn: parent
    modal: true
    focus: true
    width: Math.min(520, (parent ? parent.width : 520) - 48)
    padding: 24
    Overlay.modal: Rectangle { color: Qt.rgba(0, 0, 0, 0.5) }
    background: Rectangle { radius: Theme.radius; color: Theme.surfaceStrong; border.color: Theme.border }

    contentItem: ColumnLayout {
        spacing: 14
        RowLayout {
            spacing: 12
            Rectangle {
                width: 40; height: 40; radius: 12
                color: Theme.tint(root.danger ? Theme.warning : Theme.accent, 0.16)
                Icon { anchors.centerIn: parent; name: root.iconName; size: 20; color: root.danger ? Theme.warning : Theme.accent }
            }
            Text {
                Layout.fillWidth: true
                text: root.title; color: Theme.text; font.pixelSize: 17; font.weight: Font.DemiBold; wrapMode: Text.WordWrap
                Accessible.role: Accessible.Heading
            }
        }
        Text {
            Layout.fillWidth: true
            visible: text !== ""
            text: root.message; color: Theme.textMuted; font.pixelSize: 13; wrapMode: Text.WordWrap; lineHeight: 1.25
        }
        Repeater {
            model: root.details
            RowLayout {
                required property string modelData
                Layout.fillWidth: true
                spacing: 8
                Icon { name: "package"; size: 14; color: Theme.textFaint }
                Text { Layout.fillWidth: true; text: modelData; color: Theme.text; font.pixelSize: 13; font.family: Theme.mono; wrapMode: Text.WrapAnywhere }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: 4
            Item { Layout.fillWidth: true }
            AppButton { text: qsTr("Cancel"); onClicked: root.close() }
            AppButton {
                id: yes
                variant: "primary"
                text: root.confirmText
                onClicked: { const cb = root.onYes; root.close(); if (cb) cb() }
            }
        }
    }
    onOpened: yes.forceActiveFocus()
}
