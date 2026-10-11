import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

// Scrollable page with a title. Children go into the content column.
ScrollView {
    id: page
    property string title
    property string subtitle
    default property alias content: column.data
    property alias header: headerSlot.data

    contentWidth: availableWidth
    clip: true

    ColumnLayout {
        id: column
        width: page.availableWidth - 8
        spacing: 16

        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: 4
            spacing: 12
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2
                Text { text: page.title; color: Theme.text; font.pixelSize: 24; font.weight: Font.Bold; Accessible.role: Accessible.Heading }
                Text {
                    Layout.fillWidth: true
                    text: page.subtitle
                    visible: text !== ""
                    color: Theme.textMuted
                    font.pixelSize: 13
                    wrapMode: Text.WordWrap
                }
            }
            Row { id: headerSlot; spacing: 8 }
        }
    }
}
