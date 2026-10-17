import QtQuick
import QtQuick.Layouts
import "."

// A state in words + icon + tone (never colour alone). tone: ok | warn | error | busy | idle
Rectangle {
    id: root
    property string text
    property string tone: "idle"
    property string iconName: tone === "ok" ? "checkCircle" : tone === "warn" ? "alert" : tone === "error" ? "x"
                            : tone === "busy" ? "refresh" : "minus"
    readonly property color color_: tone === "ok" ? Theme.success : tone === "warn" ? Theme.warning
                                  : tone === "error" ? Theme.danger : tone === "busy" ? Theme.accent : Theme.textMuted

    implicitHeight: 26
    implicitWidth: row.implicitWidth + 20
    radius: height / 2
    color: Theme.tint(color_, Theme.dark ? 0.16 : 0.12)
    Accessible.role: Accessible.StaticText
    Accessible.name: text

    RowLayout {
        id: row
        anchors.centerIn: parent
        spacing: 6
        Icon { name: root.iconName; size: 14; color: root.color_ }
        Text { text: root.text; color: root.color_; font.pixelSize: 12; font.weight: Font.DemiBold }
    }
}
