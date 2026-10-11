import QtQuick
import QtWebEngine

WebEngineView {
    backgroundColor: "transparent"
    settings.playbackRequiresUserGesture: true  // the preview never plays audio
    settings.showScrollBars: false
    onContextMenuRequested: request => request.accepted = true
}
