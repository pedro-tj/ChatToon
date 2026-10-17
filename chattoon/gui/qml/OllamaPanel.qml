import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

// Ollama, the character's brain: is it installed, is it running, start/stop, install.
// Used by the AI page and the first-run wizard.
ColumnLayout {
    id: root
    property bool compact: false
    readonly property var center: backend.aiCenter
    readonly property var st: center.status
    readonly property var inst: center.install
    readonly property var plan: center.plan
    readonly property string state_: st.state || "checking"
    property bool wantInstall: false

    spacing: 12
    Layout.fillWidth: true

    function stateText() {
        switch (state_) {
        case "not_installed": return qsTr("Not installed")
        case "stopped": return qsTr("Installed and stopped")
        case "starting": return qsTr("Starting…")
        case "running": return qsTr("Running — version %1").arg(st.version || "?")
        case "error": return qsTr("Error — the service failed")
        case "remote": return st.api ? qsTr("Remote server — connected (version %1)").arg(st.version || "?")
                                     : qsTr("Remote server — not reachable")
        default: return qsTr("Checking…")
        }
    }
    function stateTone() {
        return state_ === "running" || (state_ === "remote" && st.api) ? "ok" : state_ === "starting" || state_ === "checking" ? "busy"
             : state_ === "error" || (state_ === "remote" && !st.api) ? "error" : "warn"
    }
    function managerText() {
        return ({ system: qsTr("System service (ollama.service) — models in /var/lib/ollama"),
                  user: qsTr("Your user's service — models in your home folder"),
                  chattoon: qsTr("Started by ChatToon — it stops when ChatToon closes"),
                  external: qsTr("Opened by another program (Alpaca, a terminal, Docker…)"),
                  remote: qsTr("On another computer: ChatToon only uses its API") })[st.manager || ""] || ""
    }
    function installError(code) {
        return ({ cancelled: qsTr("The installation was cancelled: the administrator password was not confirmed."),
                  "not-found": qsTr("The package is not in your repositories. Update the system and try again."),
                  locked: qsTr("Another program is installing or updating packages. Wait for it to finish and try again."),
                  network: qsTr("The packages could not be downloaded. Check your internet connection."),
                  conflict: qsTr("The package conflicts with something already installed. See the details."),
                  disk: qsTr("Not enough free disk space."),
                  "no-pkexec": qsTr("The password dialog (polkit) is not available."),
                  timeout: qsTr("The installation took too long and was stopped.") })[code]
               || qsTr("The installation failed. See the details.")
    }

    Connections {
        target: root.center
        function onPlanChanged() { if (root.wantInstall && root.plan.base) { root.wantInstall = false; installDialog.open() } }
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: 10
        StateChip { text: root.stateText(); tone: root.stateTone() }
        Item { Layout.fillWidth: true }
        AppButton {
            compact: true; variant: "ghost"; iconName: "refresh"; tip: qsTr("Check again"); Accessible.name: tip
            enabled: !root.st.checking
            onClicked: root.center.refresh()
        }
    }
    Text {
        Layout.fillWidth: true
        visible: text !== "" && !root.compact
        text: root.managerText()
        color: Theme.textFaint; font.pixelSize: 12; wrapMode: Text.WordWrap
    }

    // ---- actions for each state
    Flow {
        Layout.fillWidth: true
        spacing: 8
        visible: !root.inst.running
        AppButton {
            visible: root.state_ === "not_installed"
            variant: "primary"; iconName: "download"; text: qsTr("Install Ollama")
            onClicked: { root.wantInstall = true; root.center.loadPlan() }
        }
        AppButton {
            visible: root.state_ === "stopped" || root.state_ === "error"
            variant: "primary"; iconName: "play"; text: qsTr("Start Ollama")
            enabled: !root.st.busy
            onClicked: root.center.start()
        }
        AppButton {
            visible: root.state_ === "running" && root.st.canStop
            iconName: "stop"; text: qsTr("Stop")
            enabled: !root.st.busy
            onClicked: {
                const busy = ["thinking", "speaking", "reading"].indexOf(backend.runtimeState.phase) >= 0
                if (busy) win.ask({ title: qsTr("Stop Ollama now?"), icon: "alert", danger: true, confirm: qsTr("Stop"),
                                    message: qsTr("The character is answering right now. Stopping Ollama interrupts this reply.") },
                                  () => root.center.stop())
                else root.center.stop()
            }
        }
        AppButton {
            visible: (root.state_ === "running" && root.st.canStop) || root.state_ === "error"
            iconName: "refresh"; text: qsTr("Restart")
            enabled: !root.st.busy
            onClicked: root.center.restart()
        }
        AppButton {
            visible: root.state_ === "not_installed" && !root.compact
            variant: "ghost"; iconName: "external"; text: qsTr("Open in the software centre")
            onClicked: root.center.openStore("ollama")
        }
    }
    RowLayout {
        Layout.fillWidth: true
        visible: root.st.local !== false && root.st.canEnable === true && !root.compact
        spacing: 10
        Text { Layout.fillWidth: true; text: qsTr("Start Ollama with the computer"); color: Theme.text; font.pixelSize: 13 }
        AppSwitch {
            checked: root.st.enabled === true
            enabled: !root.st.busy
            Accessible.name: qsTr("Start Ollama with the computer")
            onToggled: root.center.setAutostart(checked)
        }
    }

    // ---- other Ollama servers on this computer (Alpaca, manual…): "where are my models?"
    Repeater {
        model: root.st.others || []
        Rectangle {
            required property var modelData
            Layout.fillWidth: true
            implicitHeight: otherRow.implicitHeight + 20
            radius: Theme.radiusSmall
            color: Theme.tint(Theme.warning, 0.1)
            border.color: Theme.tint(Theme.warning, 0.4)
            RowLayout {
                id: otherRow
                anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; margins: 12 }
                spacing: 10
                Icon { name: "server"; size: 18; color: Theme.warning }
                Text {
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap; color: Theme.text; font.pixelSize: 12
                    text: qsTr("Another Ollama is running on this computer (%1) with %n model(s). Models installed there do not appear here.", "", modelData.models)
                          .arg(modelData.host)
                }
                AppButton { compact: true; text: qsTr("Use this one"); onClicked: root.center.useHost(modelData.host) }
            }
        }
    }

    // ---- install progress / result
    ColumnLayout {
        Layout.fillWidth: true
        visible: root.inst.running === true
        spacing: 6
        Text { text: qsTr("Installing %1…").arg((root.inst.packages || []).join(", ")); color: Theme.text; font.pixelSize: 13; font.weight: Font.Medium }
        ProgressGlow { Layout.fillWidth: true; implicitHeight: 6; value: root.inst.progress > 0 ? root.inst.progress : -1 }
        Text {
            Layout.fillWidth: true
            text: root.inst.line || qsTr("Waiting for the administrator password…")
            color: Theme.textFaint; font.family: Theme.mono; font.pixelSize: 11; elide: Text.ElideMiddle
        }
        Text {
            Layout.fillWidth: true
            text: qsTr("Once the password is confirmed, the installation finishes on its own (it cannot be cancelled halfway).")
            color: Theme.textFaint; font.pixelSize: 11; wrapMode: Text.WordWrap
        }
    }
    Rectangle {
        Layout.fillWidth: true
        visible: !root.inst.running && root.inst.result !== undefined && root.inst.result.ok === false
        implicitHeight: errCol.implicitHeight + 20
        radius: Theme.radiusSmall
        color: Theme.tint(Theme.danger, 0.1)
        ColumnLayout {
            id: errCol
            anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; margins: 12 }
            spacing: 4
            Text { Layout.fillWidth: true; text: root.installError((root.inst.result || {}).code || ""); color: Theme.danger; font.pixelSize: 13; wrapMode: Text.WordWrap }
            Text {
                Layout.fillWidth: true
                visible: text !== ""
                text: (root.inst.result || {}).detail || ""
                color: Theme.textFaint; font.family: Theme.mono; font.pixelSize: 11; wrapMode: Text.WrapAnywhere; maximumLineCount: 4; elide: Text.ElideRight
            }
        }
    }
    Text {
        Layout.fillWidth: true
        visible: root.state_ === "stopped" && !root.compact
        text: qsTr("Tip: after installing, Ollama only runs when started. Turn on “Start Ollama with the computer” to never think about it again.")
        color: Theme.textFaint; font.pixelSize: 12; wrapMode: Text.WordWrap
    }

    // ---- install confirmation: what, how big, from where
    Popup {
        id: installDialog
        parent: Overlay.overlay
        anchors.centerIn: parent
        modal: true
        focus: true
        width: Math.min(560, (parent ? parent.width : 560) - 48)
        padding: 24
        property string accel: root.plan.recommended || ""
        onOpened: accel = root.plan.recommended || ""
        Overlay.modal: Rectangle { color: Qt.rgba(0, 0, 0, 0.5) }
        background: Rectangle { radius: Theme.radius; color: Theme.surfaceStrong; border.color: Theme.border }
        contentItem: ColumnLayout {
            spacing: 14
            Text { text: qsTr("Install Ollama"); color: Theme.text; font.pixelSize: 18; font.weight: Font.DemiBold }
            Text {
                Layout.fillWidth: true
                visible: !root.plan.pacman
                wrapMode: Text.WordWrap; color: Theme.warning; font.pixelSize: 13
                text: qsTr("Automatic installation works on BigLinux, Manjaro and Arch. On %1, install Ollama from your software centre or from ollama.com, then press “Check again”.")
                      .arg((root.plan.distro || {}).name || qsTr("this system"))
            }
            ColumnLayout {
                visible: root.plan.pacman === true
                Layout.fillWidth: true
                spacing: 8
                Text {
                    Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Theme.textMuted; font.pixelSize: 13
                    text: qsTr("From your system's official repositories (%1). Your administrator password will be asked.")
                          .arg((root.plan.base || {}).repository || "")
                }
                RowLayout {
                    Layout.fillWidth: true
                    Icon { name: "package"; size: 16; color: Theme.accent }
                    Text { Layout.fillWidth: true; text: "ollama " + ((root.plan.base || {}).version || ""); color: Theme.text; font.family: Theme.mono; font.pixelSize: 13 }
                    Text { text: (root.plan.base || {}).downloadSize || ""; color: Theme.textMuted; font.pixelSize: 12 }
                }
                Text { text: qsTr("Graphics card acceleration (optional)"); color: Theme.text; font.pixelSize: 13; font.weight: Font.Medium; Layout.topMargin: 4 }
                Repeater {
                    model: [{ name: "", downloadSize: "" }].concat(root.plan.acceleration || [])
                    RowLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        spacing: 8
                        RadioButton {
                            checked: installDialog.accel === modelData.name
                            onClicked: installDialog.accel = modelData.name
                            Accessible.name: label.text
                        }
                        Text {
                            id: label
                            Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Theme.text; font.pixelSize: 13
                            text: modelData.name === "" ? qsTr("Processor only (works everywhere, slower)")
                                : modelData.name === "ollama-vulkan" ? qsTr("Vulkan — AMD, Intel and NVIDIA cards (small download)")
                                : modelData.name === "ollama-cuda" ? qsTr("CUDA — NVIDIA cards")
                                : modelData.name === "ollama-rocm" ? qsTr("ROCm — AMD cards (large download)") : modelData.name
                        }
                        Chip { visible: modelData.name !== "" && modelData.name === root.plan.recommended; text: qsTr("recommended for your card"); tone: Theme.success }
                        Text { text: modelData.downloadSize || ""; color: Theme.textMuted; font.pixelSize: 12 }
                    }
                }
            }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                AppButton { text: qsTr("Cancel"); onClicked: installDialog.close() }
                AppButton {
                    variant: "primary"; iconName: "download"; text: qsTr("Install")
                    visible: root.plan.pacman === true && root.plan.pkexec === true && (root.plan.base || {}).available === true
                    onClicked: {
                        installDialog.close()
                        root.center.installOllama(installDialog.accel ? ["ollama", installDialog.accel] : ["ollama"])
                    }
                }
            }
        }
    }
}
