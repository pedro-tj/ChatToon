import QtQuick
import "."

// Platform mark: brand colour + short name (no trademarked logos are bundled).
Rectangle {
    id: root
    property string platform
    property int size: 28
    readonly property var info: (win.platformInfo || {})[platform] || ({ color: Theme.textFaint, glyph: "?", label: platform })
    // dark ink on light brand colours (Kick green), white on the others
    readonly property color ink: (0.299 * color.r + 0.587 * color.g + 0.114 * color.b) > 0.6 ? "#101010" : "#ffffff"

    implicitWidth: size
    implicitHeight: size
    radius: Math.round(size * 0.3)
    color: info.color

    Text {
        anchors.centerIn: parent
        text: root.info.glyph
        color: root.ink
        font.pixelSize: Math.round(root.size * (root.info.glyph.length > 1 ? 0.38 : 0.5))
        font.weight: Font.Black
        font.family: Theme.sans
    }
    Accessible.role: Accessible.StaticText
    Accessible.name: info.label
}
