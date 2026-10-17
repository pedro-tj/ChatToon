import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Window
import "."

// The character alone on the desktop: transparent, frameless, dragged with the mouse.
// Created by gui/character_window.py (which also sets the window flags and the icon).
Window {
    id: win
    required property var controller
    property int initialWidth: 440
    property int initialHeight: 660
    readonly property var caps: controller.capabilities
    readonly property var disp: backend.config.display

    width: initialWidth
    height: initialHeight
    minimumWidth: 260
    minimumHeight: 390
    color: "transparent"
    title: controller.title
    onClosing: controller.closed()

    Item {
        id: stage
        anchors.fill: parent
        focus: true
        Accessible.role: Accessible.Animation
        Accessible.name: qsTr("%1, your ChatToon character").arg(win.title.split(" — ")[0])
        Keys.onMenuPressed: menu.openAt(stage.width / 2, stage.height * 0.45)
        Keys.onEscapePressed: win.controller.hide()

        Loader {
            id: web
            anchors.fill: parent
            active: webEngineAvailable && win.controller.url !== ""
            source: "WebPreview.qml"
            onLoaded: item.url = Qt.binding(() => win.controller.url)
        }
        // without QtWebEngine (or before the overlay starts): the character's portrait
        Image {
            anchors { horizontalCenter: parent.horizontalCenter; bottom: parent.bottom; bottomMargin: parent.height * 0.05 }
            visible: !web.active
            width: parent.width * 0.7
            height: parent.height * 0.6
            fillMode: Image.PreserveAspectFit
            source: "assets/characters/" + win.controller.characterId + ".png"
            sourceSize: Qt.size(300, 340)
        }

        MouseArea {
            id: grab
            anchors.fill: parent
            acceptedButtons: Qt.LeftButton | Qt.RightButton
            hoverEnabled: true
            cursorShape: win.disp.locked ? Qt.ArrowCursor : pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
            onPressed: mouse => {
                if (mouse.button === Qt.RightButton) menu.openAt(mouse.x, mouse.y)
                else if (!win.disp.locked) win.startSystemMove()
            }
            onDoubleClicked: win.controller.raiseMain()
            onWheel: wheel => {
                if (wheel.modifiers & Qt.ControlModifier) win.controller.scaleBy(wheel.angleDelta.y > 0 ? 1.08 : 0.926)
                else wheel.accepted = false
            }
        }

        // resize grip (bottom-right), only while the mouse is over the window
        Rectangle {
            id: grip
            anchors { right: parent.right; bottom: parent.bottom; margins: 4 }
            width: 26; height: 26; radius: 8
            visible: !win.disp.locked && (grab.containsMouse || gripArea.containsMouse)
            color: Qt.rgba(0, 0, 0, 0.45)
            Text { anchors.centerIn: parent; text: "⤡"; color: "white"; font.pixelSize: 15 }
            MouseArea {
                id: gripArea
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.SizeFDiagCursor
                onPressed: win.startSystemResize(Qt.RightEdge | Qt.BottomEdge)
                onReleased: win.controller.resized(win.width, win.height)
            }
            ToolTip.visible: gripArea.containsMouse
            ToolTip.text: qsTr("Drag to resize · Ctrl + wheel also works")
        }
    }

    CharacterMenu {
        id: menu
        objectName: "characterMenu"
        controller: win.controller
    }
}
