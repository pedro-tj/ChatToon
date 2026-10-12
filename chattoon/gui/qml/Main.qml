import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."
import "pages"

ApplicationWindow {
    id: win
    readonly property var cfg: backend.config
    readonly property var rt: backend.runtimeState
    readonly property bool running: rt.state === "running"
    readonly property bool paused: rt.state === "paused"
    property alias currentPage: nav.currentIndex
    // platform id -> { label, color, glyph, support, … } (PlatformBadge, pages)
    readonly property var platformInfo: {
        const map = {}
        for (const p of backend.platforms) map[p.id] = p
        return map
    }
    readonly property var pageIndex: ({ dashboard: 0, characters: 1, personality: 2, ai: 3, platforms: 4, livechat: 5,
                                        voice: 6, context: 7, obs: 8, history: 9, settings: 10 })
    function go(name) { nav.currentIndex = pageIndex[name] }

    width: 1360
    height: 880
    minimumWidth: 1020
    minimumHeight: 660
    visible: true
    title: "ChatToon"
    color: Theme.bg
    font.family: Theme.sans

    palette.window: Theme.bg
    palette.windowText: Theme.text
    palette.base: Theme.surfaceStrong
    palette.text: Theme.text
    palette.button: Theme.surfaceStrong
    palette.buttonText: Theme.text
    palette.highlight: Theme.accent
    palette.highlightedText: Theme.accentText
    palette.toolTipBase: Theme.surfaceStrong
    palette.toolTipText: Theme.text
    palette.placeholderText: Theme.textFaint

    Binding { target: Theme; property: "mode"; value: win.cfg.theme }

    // sources that need the streamer (login, error) — shown as a badge on the menu
    readonly property int attention: backend.sources.filter(s => s.enabled && ["auth_required", "error"].indexOf(s.status.state) >= 0).length

    function stateLabel(s) {
        return { running: qsTr("Live"), paused: qsTr("Paused"), stopped: qsTr("Stopped"), emergency: qsTr("Emergency stop") }[s] || s
    }
    function toggleRun() {
        if (running) backend.pause()
        else if (paused) backend.resume()
        else backend.start()
    }

    Shortcut { sequence: "Ctrl+Space"; onActivated: win.toggleRun() }
    Shortcut { sequences: ["Ctrl+Shift+X", "Pause"]; onActivated: backend.emergencyStop() }
    Shortcut { sequence: "Ctrl+."; onActivated: backend.interrupt() }
    Shortcut { sequence: "Ctrl+M"; onActivated: backend.setConfig("voice.enabled", !win.cfg.voice.enabled) }
    Repeater {
        model: 9
        Item {
            required property int index
            Shortcut { sequence: "Ctrl+" + (index + 1); onActivated: nav.currentIndex = index }
        }
    }

    Connections {
        target: backend
        function onToast(message, kind) { if (message) toast.show(message, kind) }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        // ------------------------------------------------------------ sidebar
        Rectangle {
            Layout.fillHeight: true
            Layout.preferredWidth: 236
            color: Theme.sidebar

            ColumnLayout {
                anchors { fill: parent; margins: 14 }
                spacing: 4

                RowLayout {
                    Layout.bottomMargin: 14
                    Layout.leftMargin: 4
                    spacing: 10
                    Image { source: "assets/chattoon.svg"; sourceSize: Qt.size(76, 76); Layout.preferredWidth: 38; Layout.preferredHeight: 38 }
                    ColumnLayout {
                        spacing: 0
                        Text { text: "ChatToon"; color: Theme.text; font.pixelSize: 18; font.weight: Font.Bold }
                        Text { text: qsTr("Live co-host"); color: Theme.textFaint; font.pixelSize: 11 }
                    }
                }

                ListView {
                    id: nav
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    interactive: false
                    spacing: 2
                    keyNavigationEnabled: true
                    activeFocusOnTab: true
                    model: [
                        { icon: "dashboard", label: qsTr("Dashboard") },
                        { icon: "smile", label: qsTr("Characters") },
                        { icon: "sparkles", label: qsTr("Personality") },
                        { icon: "bot", label: qsTr("Artificial intelligence") },
                        { icon: "layers", label: qsTr("Streaming platforms") },
                        { icon: "chat", label: qsTr("Live chat") },
                        { icon: "volume", label: qsTr("Voice") },
                        { icon: "book", label: qsTr("Stream context") },
                        { icon: "broadcast", label: qsTr("OBS Studio") },
                        { icon: "history", label: qsTr("History") },
                        { icon: "settings", label: qsTr("Settings") },
                    ]
                    delegate: NavButton {
                        required property var modelData
                        required property int index
                        width: ListView.view.width
                        text: modelData.label
                        iconName: modelData.icon
                        current: nav.currentIndex === index
                        badge: index === 0 && (backend.queue.suggestions || []).length > 0 ? String(backend.queue.suggestions.length)
                             : index === 4 && win.attention > 0 ? "!" : ""
                        onClicked: nav.currentIndex = index
                    }
                }

                // live state + main control, always reachable
                GlassCard {
                    Layout.fillWidth: true
                    implicitHeight: liveCol.implicitHeight + 24
                    ColumnLayout {
                        id: liveCol
                        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 12 }
                        spacing: 10
                        RowLayout {
                            spacing: 8
                            Rectangle {
                                width: 10; height: 10; radius: 5
                                color: win.running ? Theme.success : win.rt.state === "emergency" ? Theme.danger
                                     : win.paused ? Theme.warning : Theme.textFaint
                                SequentialAnimation on opacity {
                                    running: win.running; loops: Animation.Infinite
                                    NumberAnimation { to: 0.35; duration: 700 }
                                    NumberAnimation { to: 1; duration: 700 }
                                }
                            }
                            Text { text: win.stateLabel(win.rt.state); color: Theme.text; font.pixelSize: 13; font.weight: Font.DemiBold }
                            Item { Layout.fillWidth: true }
                            Text {
                                text: { const m = { demo: qsTr("Demo"), assisted: qsTr("Assisted"), auto: qsTr("Automatic") }; return m[win.cfg.mode] || "" }
                                color: Theme.textFaint; font.pixelSize: 11
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 6
                            AppButton {
                                Layout.fillWidth: true
                                variant: "primary"
                                iconName: win.running ? "pause" : "play"
                                text: win.running ? qsTr("Pause") : win.paused ? qsTr("Resume") : qsTr("Start")
                                tip: "Ctrl+Space"
                                onClicked: win.toggleRun()
                            }
                            AppButton {
                                variant: "danger"
                                iconName: "emergency"
                                tip: qsTr("Emergency stop: silence everything now (Ctrl+Shift+X)")
                                Accessible.name: qsTr("Emergency stop")
                                onClicked: backend.emergencyStop()
                            }
                        }
                    }
                }
            }
        }

        // ------------------------------------------------------------ pages
        StackLayout {
            id: stack
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.margins: 22
            currentIndex: nav.currentIndex

            DashboardPage {}
            Loader { active: stack.currentIndex === 1; sourceComponent: CharactersPage {} }
            PersonalityPage {}
            AiPage {}
            PlatformsPage {}
            LiveChatPage {}
            VoicePage {}
            StreamPage {}
            Loader { active: stack.currentIndex === 8; sourceComponent: ObsPage {} }
            HistoryPage {}
            SettingsPage {}
        }
    }

    // emergency banner: obvious safe state
    Rectangle {
        anchors { top: parent.top; horizontalCenter: parent.horizontalCenter; topMargin: 10 }
        visible: win.rt.state === "emergency"
        width: bannerRow.implicitWidth + 32; height: 40; radius: 20
        color: Theme.danger
        z: 50
        RowLayout {
            id: bannerRow
            anchors.centerIn: parent
            spacing: 10
            Icon { name: "emergency"; size: 18; color: "white" }
            Text { text: qsTr("Emergency stop: the avatar is silent. Press Start to continue."); color: "white"; font.pixelSize: 13; font.weight: Font.DemiBold }
        }
    }

    Toast { id: toast }

    FirstRunWizard {
        id: wizard
        anchors.centerIn: parent
    }
    Component.onCompleted: if (!cfg.first_run_done) wizard.open()
}
