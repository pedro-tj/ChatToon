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
    property int currentPage: 0  // index in the page stack (see pageIndex)
    // platform id -> { label, color, glyph, support, … } (PlatformBadge, pages)
    readonly property var platformInfo: {
        const map = {}
        for (const p of backend.platforms) map[p.id] = p
        return map
    }
    readonly property var pageIndex: ({ dashboard: 0, characters: 1, personality: 2, ai: 3, platforms: 4, livechat: 5,
                                        voice: 6, context: 7, obs: 8, display: 8, history: 9, settings: 10 })
    function go(name) { currentPage = pageIndex[name] }
    // menu: the simple mode shows the essentials; the advanced mode adds the technical pages
    readonly property var pages: [
        { id: "dashboard", icon: "dashboard", label: qsTr("Dashboard") },
        { id: "characters", icon: "smile", label: qsTr("Characters") },
        { id: "personality", icon: "sparkles", label: qsTr("Personality"), advanced: true },
        { id: "ai", icon: "bot", label: qsTr("Artificial intelligence") },
        { id: "voice", icon: "volume", label: qsTr("Voice") },
        { id: "platforms", icon: "layers", label: qsTr("Streaming platforms") },
        { id: "display", icon: "monitor", label: qsTr("Where to show") },
        { id: "livechat", icon: "chat", label: qsTr("Live chat") },
        { id: "context", icon: "book", label: qsTr("Stream context"), advanced: true },
        { id: "history", icon: "history", label: qsTr("History"), advanced: true },
        { id: "settings", icon: "settings", label: qsTr("Settings") },
    ]
    readonly property var visiblePages: pages.filter(p => !p.advanced || cfg.advanced || pageIndex[p.id] === currentPage)
    function ask(options, callback) { confirm.ask(options, callback) }
    function askReveal(key) {
        confirm.ask({ title: qsTr("Show this information?"), icon: "eye", danger: true, confirm: qsTr("Show for 15 seconds"),
                      message: qsTr("It stays visible for 15 seconds. If you are streaming or sharing your screen, viewers will see it too.") },
                    () => Privacy.reveal(key))
    }

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
    Binding { target: Privacy; property: "live"; value: win.cfg.privacy_mode }

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
            Shortcut { sequence: "Ctrl+" + (index + 1); onActivated: if (index < win.visiblePages.length) win.go(win.visiblePages[index].id) }
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
                    model: win.visiblePages
                    currentIndex: win.visiblePages.findIndex(p => win.pageIndex[p.id] === win.currentPage)
                    // arrow keys on the menu open the page (the binding above follows clicks and shortcuts)
                    onCurrentIndexChanged: if (activeFocus && currentIndex >= 0 && win.pageIndex[win.visiblePages[currentIndex].id] !== win.currentPage)
                                               win.go(win.visiblePages[currentIndex].id)
                    delegate: NavButton {
                        required property var modelData
                        required property int index
                        width: ListView.view.width
                        text: modelData.label
                        iconName: modelData.icon
                        current: win.pageIndex[modelData.id] === win.currentPage
                        badge: modelData.id === "dashboard" && (backend.queue.suggestions || []).length > 0 ? String(backend.queue.suggestions.length)
                             : modelData.id === "platforms" && win.attention > 0 ? "!" : ""
                        onClicked: win.go(modelData.id)
                    }
                }

                // live privacy: always visible, one click away
                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: 34
                    radius: Theme.radiusSmall
                    color: win.cfg.privacy_mode ? Theme.tint(Theme.success, 0.12) : Theme.tint(Theme.warning, 0.12)
                    activeFocusOnTab: true
                    Accessible.role: Accessible.CheckBox
                    Accessible.name: qsTr("Live privacy mode")
                    Accessible.checked: win.cfg.privacy_mode
                    Keys.onSpacePressed: backend.setConfig("privacy_mode", !win.cfg.privacy_mode)
                    RowLayout {
                        anchors { fill: parent; leftMargin: 10; rightMargin: 10 }
                        spacing: 8
                        Icon { name: win.cfg.privacy_mode ? "shield" : "eye"; size: 15; color: win.cfg.privacy_mode ? Theme.success : Theme.warning }
                        Text {
                            Layout.fillWidth: true
                            text: win.cfg.privacy_mode ? qsTr("Live privacy: on") : qsTr("Live privacy: off")
                            color: win.cfg.privacy_mode ? Theme.success : Theme.warning; font.pixelSize: 12; font.weight: Font.DemiBold
                            elide: Text.ElideRight
                        }
                    }
                    HoverHandler { id: privHover; cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: backend.setConfig("privacy_mode", !win.cfg.privacy_mode) }
                    ToolTip.visible: privHover.hovered
                    ToolTip.text: qsTr("Hides addresses, IPs and account names on every page — safe to show on stream.")
                    ToolTip.delay: 400
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
            currentIndex: win.currentPage

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
    ConfirmDialog { id: confirm }
    StartReport { id: startReport }

    FirstRunWizard {
        id: wizard
        anchors.centerIn: parent
    }
    Component.onCompleted: if (!cfg.first_run_done) wizard.open()
}
