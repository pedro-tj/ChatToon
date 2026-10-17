import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Dialogs
import QtQuick.Layouts
import ".."

Page {
    id: page
    readonly property var cfg: backend.config
    readonly property var sp: cfg.spontaneous
    readonly property var categories: ["invite", "curiosity", "context", "humor", "reflection", "catchphrase", "cta"]
    function toggleCategory(c, on) {
        const list = (page.sp.categories || []).filter(x => x !== c)
        if (on) list.push(c)
        backend.setConfig("spontaneous.categories", list)
    }
    title: qsTr("Settings")
    subtitle: qsTr("Appearance, language, profiles and diagnostics.")

    FileDialog { id: exportDialog; fileMode: FileDialog.SaveFile; nameFilters: [qsTr("ChatToon profile (*.json)")]; defaultSuffix: "json"; onAccepted: backend.exportProfile(selectedFile.toString()) }
    FileDialog { id: importDialog; nameFilters: [qsTr("ChatToon profile (*.json)")]; onAccepted: backend.loadProfile(selectedFile.toString()) }

    Section {
        title: qsTr("How ChatToon looks to you")
        iconName: "wand"
        SettingRow {
            label: qsTr("Advanced mode")
            description: qsTr("Shows the technical settings: network, inference parameters, diagnostics, personality fine-tuning, stream context and history. Simple mode keeps only the essentials.")
            AppSwitch { checked: cfg.advanced; onToggled: backend.setConfig("advanced", checked); Accessible.name: qsTr("Advanced mode") }
        }
        SettingRow {
            label: qsTr("Live privacy mode")
            description: qsTr("Hides addresses, IPs, domains and account names on every page, so the app can appear on stream. Secret codes and the public IP are always hidden.")
            AppSwitch { checked: cfg.privacy_mode; onToggled: backend.setConfig("privacy_mode", checked); Accessible.name: qsTr("Live privacy mode") }
        }
    }

    Section {
        title: qsTr("Appearance")
        iconName: "palette"
        SettingRow {
            label: qsTr("Theme")
            Segmented {
                model: [{ value: "system", label: qsTr("System") }, { value: "dark", label: qsTr("Dark") }, { value: "light", label: qsTr("Light") }]
                current: cfg.theme
                onActivated: v => backend.setConfig("theme", v)
            }
        }
        SettingRow {
            label: qsTr("Interface language")
            description: qsTr("Restart ChatToon to apply. The avatar's language is set on the AI page.")
            AppCombo {
                implicitWidth: 200
                textRole: "t"; valueRole: "v"
                model: [{ v: "system", t: qsTr("System default") }, { v: "en", t: "English" }, { v: "pt_BR", t: "Português (Brasil)" }]
                currentIndex: Math.max(0, indexOfValue(cfg.ui_language))
                onActivated: backend.setConfig("ui_language", currentValue)
            }
        }
    }

    Section {
        title: qsTr("Spontaneous lines")
        iconName: "chat"
        description: qsTr("When the chat is quiet, the avatar speaks up on its own — invitations, curiosities, comments on the topic. Viewers always come first: a message cancels a line still being prepared.")
        actions: AppButton { compact: true; iconName: "play"; text: qsTr("Try one now"); onClicked: backend.testSpontaneous("") }
        SettingRow {
            label: qsTr("Speak on its own")
            description: qsTr("Only while live and in Automatic or Demo mode — never paused, after an emergency stop or in Assisted mode.")
            AppSwitch { checked: page.sp.enabled; onToggled: backend.setConfig("spontaneous.enabled", checked); Accessible.name: qsTr("Speak on its own") }
        }
        SettingRow {
            label: qsTr("Frequency")
            Segmented {
                enabled: page.sp.enabled
                model: [{ value: "low", label: qsTr("Rarely") }, { value: "normal", label: qsTr("Normal") }, { value: "high", label: qsTr("Often") }]
                current: page.sp.frequency
                onActivated: v => backend.setConfig("spontaneous.frequency", v)
            }
        }
        SettingRow {
            label: qsTr("Quiet chat for at least")
            description: qsTr("Seconds without any viewer message before the avatar may speak.")
            NumberStepper { enabled: page.sp.enabled; value: page.sp.min_idle; from: 15; to: 1800; step: 15; suffix: " s"; onEdited: v => backend.setConfig("spontaneous.min_idle", v) }
        }
        SettingRow {
            label: qsTr("At most one line every")
            NumberStepper { enabled: page.sp.enabled; value: page.sp.min_interval; from: 30; to: 3600; step: 30; suffix: " s"; onEdited: v => backend.setConfig("spontaneous.min_interval", v) }
        }
        SettingRow {
            label: qsTr("Energy")
            description: qsTr("How strong the expressions and gestures of these lines are.")
            Segmented {
                enabled: page.sp.enabled
                model: [{ value: "calm", label: qsTr("Calm") }, { value: "normal", label: qsTr("Normal") }, { value: "lively", label: qsTr("Lively") }]
                current: page.sp.intensity
                onActivated: v => backend.setConfig("spontaneous.intensity", v)
            }
        }
        Text { text: qsTr("What it may say"); color: Theme.text; font.pixelSize: 13; font.weight: Font.Medium }
        Flow {
            Layout.fillWidth: true
            spacing: 6
            Repeater {
                model: page.categories
                Rectangle {
                    required property string modelData
                    width: catRow.implicitWidth + 12; height: 40; radius: Theme.radiusSmall
                    color: Theme.field; border.width: 1; border.color: Theme.border
                    Row {
                        id: catRow
                        anchors.centerIn: parent
                        spacing: 2
                        AppCheck {
                            text: Status.category(modelData)
                            checked: (page.sp.categories || []).indexOf(modelData) >= 0
                            onToggled: page.toggleCategory(modelData, checked)
                        }
                        AppButton {
                            compact: true; variant: "ghost"; iconName: "play"
                            tip: qsTr("Try this kind of line now"); Accessible.name: tip
                            anchors.verticalCenter: parent.verticalCenter
                            onClicked: backend.testSpontaneous(modelData)
                        }
                    }
                }
            }
        }
        Text {
            Layout.fillWidth: true
            text: qsTr("Curiosities are checked facts, spoken exactly as written. Calls to action come from Stream context. Catchphrases come from the character and the channel.")
            color: Theme.textFaint; font.pixelSize: 12; wrapMode: Text.WordWrap
        }
        SettingRow {
            label: qsTr("Let the AI vary invitations and comments")
            description: qsTr("The AI never writes facts: lines with numbers or “did you know” are replaced by a written one.")
            AppSwitch { enabled: page.sp.enabled; checked: page.sp.use_ai; onToggled: backend.setConfig("spontaneous.use_ai", checked); Accessible.name: qsTr("Let the AI vary invitations and comments") }
        }
        SettingRow {
            label: qsTr("Quiet hours")
            description: qsTr("No spontaneous lines between these times (HH:MM). Leave empty to allow them at any time.")
            Row {
                spacing: 6
                AppTextField { width: 86; text: page.sp.quiet_start; placeholderText: "23:00"; onEditingFinished: backend.setConfig("spontaneous.quiet_start", text.trim()); Accessible.name: qsTr("Quiet hours start") }
                Text { text: "–"; color: Theme.textMuted; anchors.verticalCenter: parent.verticalCenter }
                AppTextField { width: 86; text: page.sp.quiet_end; placeholderText: "07:00"; onEditingFinished: backend.setConfig("spontaneous.quiet_end", text.trim()); Accessible.name: qsTr("Quiet hours end") }
            }
        }
    }

    Section {
        title: qsTr("Stream profiles")
        iconName: "users"
        description: qsTr("Save different setups for different shows. Exported files contain no secrets.")
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            AppTextField { id: profileName; Layout.fillWidth: true; placeholderText: qsTr("Profile name, e.g. Linux Friday") }
            AppButton { iconName: "check"; text: qsTr("Save"); enabled: profileName.text.trim() !== ""; onClicked: if (backend.saveProfile(profileName.text)) profileName.text = "" }
        }
        Flow {
            Layout.fillWidth: true
            spacing: 8
            Repeater {
                model: backend.profiles
                AppButton { required property string modelData; compact: true; iconName: "file"; text: modelData; tip: qsTr("Load this profile"); onClicked: backend.loadProfile(modelData) }
            }
        }
        RowLayout {
            spacing: 8
            AppButton { iconName: "download"; text: qsTr("Export to file…"); onClicked: exportDialog.open() }
            AppButton { iconName: "file"; text: qsTr("Import from file…"); onClicked: importDialog.open() }
        }
    }

    Section {
        title: qsTr("Privacy and safety")
        iconName: "shield"
        Repeater {
            model: [
                qsTr("AI and voice run on this computer (Ollama and TTS BigLinux). Only the chats of your streaming platforms are read from the internet."),
                qsTr("Platform logins use official sign-in or tokens you paste — never passwords — and stay in the system keyring. Profiles never include them."),
                qsTr("The overlay listens only on this computer and requires a secret address. Your home network is reached only if you allow it (Where to show); Ollama and the app's controls are never exposed."),
                qsTr("Your public IP is looked up only when you ask, and secret addresses, IPs and logins stay hidden on screen in live privacy mode."),
                qsTr("Chat messages are never executed and cannot change the avatar's rules."),
                qsTr("History stays in memory and is lost when you close the app, unless you export it."),
                qsTr("Conversation memories stay in RAM during the live. Saving them between lives is optional, stays on this computer and is erased after the period you choose. Messages removed by moderators are forgotten."),
                qsTr("No telemetry."),
            ]
            RowLayout {
                required property string modelData
                Layout.fillWidth: true
                spacing: 8
                Icon { name: "check"; size: 16; color: Theme.success }
                Text { Layout.fillWidth: true; text: modelData; color: Theme.text; font.pixelSize: 13; wrapMode: Text.WordWrap }
            }
        }
    }

    Section {
        title: qsTr("Memories")
        iconName: "users"
        description: qsTr("Everything the avatar remembers about viewers: this live and, if enabled, earlier ones.")
        RowLayout {
            spacing: 8
            AppButton { iconName: "chat"; text: qsTr("See and manage"); onClicked: win.go("livechat") }
            AppButton { variant: "danger"; iconName: "trash"; text: qsTr("Erase all memories…"); onClicked: eraseDialog.open() }
        }
    }

    Dialog {
        id: eraseDialog
        parent: Overlay.overlay
        anchors.centerIn: parent
        modal: true
        title: qsTr("Erase all memories?")
        standardButtons: Dialog.Cancel | Dialog.Yes
        onAccepted: backend.clearMemory()
        Text { width: 360; text: qsTr("The avatar forgets every viewer, in RAM and on disk. This cannot be undone."); color: Theme.text; wrapMode: Text.WordWrap }
        background: Rectangle { radius: Theme.radius; color: Theme.surfaceStrong; border.width: 1; border.color: Theme.borderStrong }
    }

    Section {
        title: qsTr("Restore defaults")
        iconName: "undo"
        description: qsTr("Puts one part back as it came, without touching the others, your platforms or your logins.")
        Flow {
            Layout.fillWidth: true
            spacing: 8
            Repeater {
                model: [{ id: "ai.generation", label: qsTr("AI generation") }, { id: "voice", label: qsTr("Voice") },
                        { id: "reading", label: qsTr("Message reading") }, { id: "animation", label: qsTr("Animations") },
                        { id: "overlay.appearance", label: qsTr("Appearance in OBS") }, { id: "display", label: qsTr("Desktop window") }]
                AppButton {
                    required property var modelData
                    compact: true; iconName: "undo"; text: modelData.label
                    onClicked: win.ask({ title: qsTr("Restore “%1”?").arg(modelData.label), icon: "undo", confirm: qsTr("Restore"),
                                         message: qsTr("Only this part goes back to the default values.") },
                                       () => backend.resetSection(modelData.id))
                }
            }
        }
    }

    Section {
        title: qsTr("Diagnostics")
        iconName: "info"
        actions: AppButton { compact: true; iconName: "refresh"; text: qsTr("Run checks"); onClicked: backend.refreshServices() }
        Repeater {
            model: [
                { label: qsTr("Ollama"), ok: backend.services.ollama.ok, text: backend.services.ollama.ok ? backend.services.ollama.version : Privacy.text(backend.services.ollama.error || "") },
                { label: qsTr("TTS BigLinux"), ok: backend.services.tts.ok, text: backend.services.tts.ok ? qsTr("%n voice(s)", "", (backend.services.tts.voices || []).length) : Privacy.text(backend.services.tts.error || "") },
                { label: qsTr("Audio player"), ok: backend.services.player, text: backend.services.player ? qsTr("found") : qsTr("missing") },
                { label: qsTr("3D preview (QtWebEngine)"), ok: webEngineAvailable, text: webEngineAvailable ? qsTr("available") : qsTr("missing") },
                { label: qsTr("Login storage"), ok: backend.accounts.store ? backend.accounts.encrypted : undefined,
                  text: backend.accounts.encrypted ? qsTr("system keyring") : backend.accounts.store === "file" ? qsTr("private file (no keyring found)") : "" },
                { label: qsTr("TikTok support (TikTokLive)"), ok: !!(backend.accounts.tiktok && backend.accounts.tiktok.installed),
                  text: backend.accounts.tiktok && backend.accounts.tiktok.installed ? qsTr("installed") : qsTr("optional — chattoon extras install tiktok") },
            ].concat(backend.sources.map(s => ({
                label: (win.platformInfo[s.platform] || {}).label + " · " + (s.label || s.status.channel || s.target),
                ok: !s.enabled ? undefined : s.status.state === "connected" ? true
                    : ["error", "auth_required", "unsupported"].indexOf(s.status.state) >= 0 ? false : undefined,
                text: Status.label(s.enabled ? s.status.state : "disabled") + (s.status.code ? " — " + Status.reason(s.status.code, "") : "")
            })))
            RowLayout {
                required property var modelData
                Layout.fillWidth: true
                spacing: 10
                Icon { name: modelData.ok ? "check" : modelData.ok === false ? "x" : "clock"; size: 16; color: modelData.ok ? Theme.success : modelData.ok === false ? Theme.danger : Theme.textFaint }
                Text { Layout.preferredWidth: 220; text: modelData.label; textFormat: Text.PlainText; color: Theme.text; font.pixelSize: 13; elide: Text.ElideRight }
                Text { Layout.fillWidth: true; text: modelData.text || ""; textFormat: Text.PlainText; color: Theme.textMuted; font.pixelSize: 12; elide: Text.ElideRight }
            }
        }
        Text { text: "ChatToon " + Qt.application.version + " · GPL-3.0-or-later"; color: Theme.textFaint; font.pixelSize: 11 }
    }
}
