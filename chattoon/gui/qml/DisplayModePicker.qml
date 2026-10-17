import QtQuick
import QtQuick.Layouts
import "."

// "Where should your character appear?" — OBS Studio, a window on the desktop, or both.
ColumnLayout {
    id: root
    property bool compact: false
    readonly property string mode: backend.config.display.mode
    spacing: 10
    Layout.fillWidth: true

    GridLayout {
        Layout.fillWidth: true
        columns: root.compact || width < 640 ? 1 : 3
        columnSpacing: 10
        rowSpacing: 10
        ChoiceCard {
            iconName: "broadcast"
            title: qsTr("OBS Studio")
            description: qsTr("Ideal for live streams. The character appears in your scene with a transparent background.")
            selected: root.mode === "obs"
            onChosen: backend.setDisplayMode("obs")
        }
        ChoiceCard {
            iconName: "appWindow"
            title: qsTr("Window on the computer")
            description: qsTr("Your character lives on the desktop, above your windows.")
            selected: root.mode === "window"
            onChosen: backend.setDisplayMode("window")
        }
        ChoiceCard {
            iconName: "layers"
            title: qsTr("Both")
            description: qsTr("On the desktop and in OBS at the same time, perfectly in sync.")
            selected: root.mode === "both"
            onChosen: backend.setDisplayMode("both")
        }
    }
    Text {
        Layout.fillWidth: true
        wrapMode: Text.WordWrap
        color: Theme.textFaint; font.pixelSize: 12
        text: root.mode === "obs" ? ""
            : backend.config.voice.audio_output === "overlay"
              ? qsTr("The voice is heard once: inside OBS (or on this computer while OBS is not connected). The desktop window never plays sound.")
              : qsTr("The voice is heard once, on this computer. The desktop window never plays sound itself.")
        visible: text !== ""
    }
}
