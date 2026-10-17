import QtQuick
import "."

// Vector icon coloured by the theme (served by gui/icons.py).
// Outer Item: Image cannot set an implicit size, and layouts need one.
Item {
    id: root
    property string name
    property color color: Theme.text
    property int size: 18

    implicitWidth: size
    implicitHeight: size

    Image {
        anchors.fill: parent
        sourceSize: Qt.size(root.size * 2, root.size * 2)
        fillMode: Image.PreserveAspectFit
        smooth: true
        source: root.name ? "image://icon/" + root.name + "/" + root.color.toString().substring(1) : ""
    }
}
