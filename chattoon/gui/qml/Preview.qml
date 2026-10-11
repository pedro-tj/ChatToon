import QtQuick
import QtQuick.Layouts
import "."

// Live avatar: the same overlay page OBS shows, rendered by QtWebEngine (muted preview role).
Rectangle {
    id: root
    property string url
    property string query: "role=preview"
    property bool active: true

    radius: Theme.radius
    color: Theme.dark ? "#141120" : "#e7e3f3"
    clip: true

    Loader {
        id: loader
        anchors.fill: parent
        active: root.active && webEngineAvailable && root.url !== ""
        source: "WebPreview.qml"
        onLoaded: item.url = Qt.binding(() => root.url + (root.url.indexOf("?") >= 0 ? "&" : "?") + root.query
                                               + (Theme.dark ? "" : "&theme=light"))
    }
    ColumnLayout {
        anchors.centerIn: parent
        visible: !loader.active
        spacing: 8
        Icon { Layout.alignment: Qt.AlignHCenter; name: "monitor"; size: 36; color: Theme.textFaint }
        Text {
            Layout.alignment: Qt.AlignHCenter
            text: !webEngineAvailable ? qsTr("Preview needs QtWebEngine (package qt6-webengine)") : qsTr("Starting the overlay…")
            color: Theme.textFaint
            font.pixelSize: 12
        }
    }
}
