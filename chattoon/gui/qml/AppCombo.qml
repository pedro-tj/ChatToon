import QtQuick
import QtQuick.Controls.Basic
import "."

ComboBox {
    id: control
    implicitHeight: 34
    implicitWidth: 150
    font.pixelSize: 13
    hoverEnabled: true

    background: Rectangle {
        radius: Theme.radiusSmall
        color: Theme.field
        border.width: control.activeFocus ? 2 : 1
        border.color: control.activeFocus ? Theme.accent : control.hovered ? Theme.borderStrong : Theme.border
    }
    contentItem: Text {
        leftPadding: 12
        rightPadding: control.indicator.width + 8
        text: control.displayText
        color: Theme.text
        font: control.font
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    indicator: Text {
        x: control.width - width - 12
        y: (control.height - height) / 2
        text: "▾"
        color: Theme.textMuted
        font.pixelSize: 12
    }
    delegate: ItemDelegate {
        id: item
        required property int index
        required property var modelData
        width: control.width
        height: 32
        highlighted: control.highlightedIndex === index
        contentItem: Text {
            text: item.modelData[control.textRole] !== undefined ? item.modelData[control.textRole] : item.modelData
            color: item.highlighted ? Theme.accent : Theme.text
            font.pixelSize: 13
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle { color: item.highlighted ? Theme.hover : "transparent"; radius: 6 }
    }
    // margins keep the list inside the window and the scroll bar shows that there are more
    // items (long lists used to be cut silently: e.g. many installed models)
    popup: Popup {
        y: control.height + 4
        width: control.width
        padding: 4
        margins: 8
        implicitHeight: Math.min(contentItem.implicitHeight + 8, 360)
        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: control.popup.visible ? control.delegateModel : null
            currentIndex: control.highlightedIndex
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
        }
        background: Rectangle {
            radius: Theme.radiusSmall
            color: Theme.surfaceStrong
            border.width: 1
            border.color: Theme.borderStrong
        }
    }
}
