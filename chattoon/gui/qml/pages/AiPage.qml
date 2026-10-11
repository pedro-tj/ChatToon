import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."

Page {
    id: page
    readonly property var cfg: backend.config
    readonly property var ollama: backend.services.ollama
    readonly property var models: ollama.models || []
    readonly property var pull: backend.pull

    title: qsTr("Artificial intelligence")
    subtitle: qsTr("ChatToon thinks with Ollama, running on this computer. Nothing is sent to the cloud.")
    header: AppButton { iconName: "refresh"; text: qsTr("Check again"); onClicked: backend.refreshServices() }

    Section {
        title: qsTr("Ollama")
        iconName: "bot"
        description: ollama.ok === true ? qsTr("Running — version %1").arg(ollama.version)
                   : ollama.ok === false ? qsTr("Not reachable: %1").arg(ollama.error || "") : qsTr("Checking…")
        SettingRow {
            label: qsTr("Address")
            description: qsTr("Keep the default unless Ollama runs on another computer of your network.")
            AppTextField {
                width: 280
                text: cfg.ai.host
                onEditingFinished: { backend.setConfig("ai.host", text); backend.refreshServices() }
            }
        }
        Text {
            Layout.fillWidth: true
            visible: ollama.ok === false
            text: qsTr("Start it with:  sudo systemctl start ollama   (or install it in BigLinux Settings → AI).")
            color: Theme.warning; font.pixelSize: 12; font.family: Theme.mono; wrapMode: Text.WordWrap
        }
    }

    Section {
        title: qsTr("Model")
        iconName: "sparkles"
        description: qsTr("Smaller models answer faster. 3–4 billion parameters is a good balance for live chat.")
        SettingRow {
            label: qsTr("Model in use")
            AppCombo {
                implicitWidth: 260
                model: page.models
                enabled: page.models.length > 0
                currentIndex: Math.max(0, page.models.indexOf(cfg.ai.model))
                displayText: page.models.length ? currentText : qsTr("No model installed")
                onActivated: backend.setConfig("ai.model", currentText)
            }
        }
        Text { text: qsTr("Suggested models (good Portuguese, light):"); color: Theme.textMuted; font.pixelSize: 12 }
        Flow {
            Layout.fillWidth: true
            spacing: 8
            Repeater {
                model: backend.recommendedModels
                AppButton {
                    required property string modelData
                    readonly property bool installed: page.models.indexOf(modelData) >= 0
                    compact: true
                    variant: installed ? "ghost" : "secondary"
                    iconName: installed ? "check" : "download"
                    text: modelData
                    enabled: !installed && !(page.pull.model && page.pull.progress >= 0 && page.pull.progress < 1)
                    tip: installed ? qsTr("Installed") : qsTr("Download with Ollama")
                    onClicked: backend.pullModel(modelData)
                }
            }
        }
        ColumnLayout {
            Layout.fillWidth: true
            visible: page.pull.model !== undefined && page.pull.model !== ""
            spacing: 4
            Text {
                text: qsTr("Downloading %1: %2").arg(page.pull.model || "").arg(page.pull.status || "")
                      + (page.pull.progress >= 0 ? "  " + Math.round(page.pull.progress * 100) + "%" : "")
                color: Theme.text; font.pixelSize: 12
            }
            ProgressGlow { Layout.fillWidth: true; value: page.pull.progress === undefined ? -1 : page.pull.progress; implicitHeight: 6 }
        }
    }

    Section {
        title: qsTr("Generation")
        iconName: "settings"
        GridLayout {
            Layout.fillWidth: true
            columns: 2
            columnSpacing: 28
            uniformCellWidths: true
            rowSpacing: 14
            LabeledSlider {
                label: qsTr("Creativity (temperature)"); from: 0; to: 1.5; stepSize: 0.05; decimals: 2
                value: cfg.ai.temperature; onMoved: v => backend.setConfig("ai.temperature", v)
                hint: qsTr("Higher = more surprising, lower = more predictable.")
            }
            LabeledSlider {
                label: qsTr("Maximum characters per reply"); from: 80; to: 500; stepSize: 10
                value: cfg.ai.max_chars; onMoved: v => backend.setConfig("ai.max_chars", Math.round(v))
            }
            LabeledSlider {
                label: qsTr("Token limit"); from: 40; to: 400; stepSize: 10
                value: cfg.ai.max_tokens; onMoved: v => backend.setConfig("ai.max_tokens", Math.round(v))
            }
            LabeledSlider {
                label: qsTr("Conversation memory"); from: 0; to: 20; stepSize: 1; suffix: qsTr(" messages")
                value: cfg.ai.memory_size; onMoved: v => backend.setConfig("ai.memory_size", Math.round(v))
                hint: qsTr("Recent exchanges the avatar remembers (more = slower).")
            }
            LabeledSlider {
                label: qsTr("Timeout"); from: 10; to: 180; stepSize: 5; suffix: " s"
                value: cfg.ai.timeout; onMoved: v => backend.setConfig("ai.timeout", Math.round(v))
            }
            LabeledSlider {
                label: qsTr("Context window"); from: 1024; to: 16384; stepSize: 1024; suffix: qsTr(" tokens")
                value: cfg.ai.context_window; onMoved: v => backend.setConfig("ai.context_window", Math.round(v))
            }
        }
        SettingRow {
            label: qsTr("Reply language")
            description: qsTr("The language the avatar speaks (independent from the interface language).")
            AppCombo {
                implicitWidth: 200
                textRole: "t"; valueRole: "v"
                model: [{ v: "pt-BR", t: "Português (Brasil)" }, { v: "en", t: "English" }, { v: "es", t: "Español" }]
                currentIndex: Math.max(0, indexOfValue(cfg.ai.reply_language))
                onActivated: backend.setConfig("ai.reply_language", currentValue)
            }
        }
    }
}
