import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Dialogs
import QtQuick.Layouts
import ".."

Page {
    id: page
    readonly property var cfg: backend.config
    title: qsTr("Settings")
    subtitle: qsTr("Appearance, language, profiles and diagnostics.")

    FileDialog { id: exportDialog; fileMode: FileDialog.SaveFile; nameFilters: [qsTr("ChatToon profile (*.json)")]; defaultSuffix: "json"; onAccepted: backend.exportProfile(selectedFile.toString()) }
    FileDialog { id: importDialog; nameFilters: [qsTr("ChatToon profile (*.json)")]; onAccepted: backend.loadProfile(selectedFile.toString()) }

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
                qsTr("AI and voice run on this computer (Ollama and TTS BigLinux). Only the YouTube chat is read from the internet."),
                qsTr("The overlay server listens only on 127.0.0.1 and requires a secret address."),
                qsTr("Chat messages are never executed and cannot change the avatar's rules."),
                qsTr("History stays in memory and is lost when you close the app, unless you export it."),
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
        title: qsTr("Diagnostics")
        iconName: "info"
        actions: AppButton { compact: true; iconName: "refresh"; text: qsTr("Run checks"); onClicked: backend.refreshServices() }
        Repeater {
            model: [
                { label: qsTr("Ollama"), ok: backend.services.ollama.ok, text: backend.services.ollama.ok ? backend.services.ollama.version : (backend.services.ollama.error || "") },
                { label: qsTr("TTS BigLinux"), ok: backend.services.tts.ok, text: backend.services.tts.ok ? qsTr("%n voice(s)", "", (backend.services.tts.voices || []).length) : (backend.services.tts.error || "") },
                { label: qsTr("Audio player"), ok: backend.services.player, text: backend.services.player ? qsTr("found") : qsTr("missing") },
                { label: qsTr("3D preview (QtWebEngine)"), ok: webEngineAvailable, text: webEngineAvailable ? qsTr("available") : qsTr("missing") },
            ]
            RowLayout {
                required property var modelData
                Layout.fillWidth: true
                spacing: 10
                Icon { name: modelData.ok ? "check" : modelData.ok === false ? "x" : "clock"; size: 16; color: modelData.ok ? Theme.success : modelData.ok === false ? Theme.danger : Theme.textFaint }
                Text { Layout.preferredWidth: 220; text: modelData.label; color: Theme.text; font.pixelSize: 13 }
                Text { Layout.fillWidth: true; text: modelData.text || ""; color: Theme.textMuted; font.pixelSize: 12; elide: Text.ElideRight }
            }
        }
        Text { text: "ChatToon " + Qt.application.version + " · GPL-3.0-or-later"; color: Theme.textFaint; font.pixelSize: 11 }
    }
}
