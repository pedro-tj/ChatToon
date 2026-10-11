import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root
    property string label
    property string hint
    property real value: 0
    property real from: 0
    property real to: 100
    property real stepSize: 1
    property int decimals: 0
    property string suffix: ""
    signal moved(real value)

    Layout.fillWidth: true
    spacing: 4

    RowLayout {
        Layout.fillWidth: true
        Text { Layout.fillWidth: true; text: root.label; color: Theme.text; font.pixelSize: 13; font.weight: Font.Medium; elide: Text.ElideRight }
        Text { text: root.value.toFixed(root.decimals) + root.suffix; color: Theme.accent; font.family: Theme.mono; font.pixelSize: 12 }
    }
    Slider {
        id: slider
        Layout.fillWidth: true
        from: root.from; to: root.to; stepSize: root.stepSize
        value: root.value
        live: false
        Accessible.name: root.label
        onMoved: root.moved(value)
        onPressedChanged: if (!pressed) root.moved(value)
        background: Rectangle {
            x: slider.leftPadding
            y: slider.topPadding + slider.availableHeight / 2 - height / 2
            width: slider.availableWidth
            height: 6
            radius: 3
            color: Theme.hover
            Rectangle {
                width: slider.visualPosition * parent.width
                height: parent.height
                radius: 3
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0; color: Theme.accent }
                    GradientStop { position: 1; color: Theme.accent2 }
                }
            }
        }
        handle: Rectangle {
            x: slider.leftPadding + slider.visualPosition * (slider.availableWidth - width)
            y: slider.topPadding + slider.availableHeight / 2 - height / 2
            width: 18; height: 18; radius: 9
            color: "white"
            border.width: slider.visualFocus ? 3 : 1
            border.color: slider.visualFocus ? Theme.accent : Theme.borderStrong
            scale: slider.pressed ? 1.15 : 1
            Behavior on scale { NumberAnimation { duration: Theme.animFast } }
        }
    }
    Text {
        Layout.fillWidth: true
        visible: root.hint !== ""
        text: root.hint
        color: Theme.textFaint
        font.pixelSize: 11
        wrapMode: Text.WordWrap
    }
}
