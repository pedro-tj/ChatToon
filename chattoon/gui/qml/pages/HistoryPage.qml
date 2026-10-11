import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Dialogs
import QtQuick.Layouts
import ".."

Page {
    id: page
    title: qsTr("History")
    subtitle: qsTr("What viewers said and what the avatar answered in this session. Kept only in memory.")
    header: Row {
        spacing: 8
        AppButton { iconName: "download"; text: qsTr("Export"); enabled: backend.history.length > 0; onClicked: saveDialog.open() }
        AppButton { iconName: "trash"; text: qsTr("Clear"); enabled: backend.history.length > 0; onClicked: backend.clearHistory() }
    }

    FileDialog {
        id: saveDialog
        fileMode: FileDialog.SaveFile
        nameFilters: [qsTr("JSON (*.json)")]
        defaultSuffix: "json"
        onAccepted: backend.exportHistory(selectedFile.toString())
    }

    Section {
        visible: backend.history.length === 0
        EmptyState {
            Layout.alignment: Qt.AlignHCenter
            iconName: "history"
            title: qsTr("No replies yet")
            message: qsTr("Start the demo on the Dashboard and send a message.")
        }
    }

    Repeater {
        model: backend.history
        GlassCard {
            required property var modelData
            Layout.fillWidth: true
            implicitHeight: hcol.implicitHeight + 24
            ColumnLayout {
                id: hcol
                anchors { left: parent.left; right: parent.right; top: parent.top; margins: 12 }
                spacing: 6
                RowLayout {
                    spacing: 8
                    Text { text: new Date(modelData.time * 1000).toLocaleTimeString(Qt.locale(), Locale.ShortFormat); color: Theme.textFaint; font.family: Theme.mono; font.pixelSize: 11 }
                    Chip { text: modelData.emotion; tone: Theme.accent }
                    Chip { visible: modelData.source !== "ai"; text: modelData.source === "manual" ? qsTr("typed") : qsTr("safe reply"); tone: Theme.textMuted }
                    Chip { visible: modelData.generation > 0; text: modelData.generation.toFixed(1) + " s"; iconName: "clock" }
                    Chip { visible: !modelData.voice; text: qsTr("no voice"); tone: Theme.warning }
                }
                Text { Layout.fillWidth: true; visible: modelData.author !== ""; text: modelData.author + ": " + modelData.message; color: Theme.textMuted; font.pixelSize: 12; wrapMode: Text.WordWrap }
                Text { Layout.fillWidth: true; text: modelData.reply; color: Theme.text; font.pixelSize: 14; wrapMode: Text.WordWrap }
            }
        }
    }
}
