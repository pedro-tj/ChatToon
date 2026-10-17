import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."

Page {
    id: page
    readonly property var cfg: backend.config
    readonly property var ollama: backend.services.ollama
    readonly property var hw: backend.aiCenter.hardware
    readonly property var mem: backend.memory.stats || ({})

    onVisibleChanged: if (visible) { backend.refreshMemory(); backend.aiCenter.refresh() }
    Component.onCompleted: backend.aiCenter.refresh()

    title: qsTr("Artificial intelligence")
    subtitle: qsTr("ChatToon thinks with Ollama, running on this computer. Nothing is sent to the cloud.")

    Section {
        title: qsTr("Ollama")
        iconName: "bot"
        description: qsTr("The character's brain. Install, start and stop it here — no terminal needed.")
        OllamaPanel {}
        SettingRow {
            visible: cfg.advanced
            label: qsTr("Server address")
            description: qsTr("Keep the default unless Ollama runs on another computer of your network. A remote Ollama is used, never controlled.")
            AppTextField {
                width: 280
                text: cfg.ai.host
                onEditingFinished: if (text.trim() !== cfg.ai.host) backend.aiCenter.useHost(text.trim())
                Accessible.name: qsTr("Server address")
            }
        }
    }

    Section {
        title: qsTr("Model in use")
        iconName: "sparkles"
        description: qsTr("Every model installed in this Ollama. The green one answers your chat.")
        actions: AppButton { compact: true; variant: "ghost"; iconName: "refresh"; text: qsTr("Update list"); onClicked: backend.refreshServices() }
        ModelCatalog {}
    }

    Section {
        title: qsTr("Suggested models")
        iconName: "download"
        description: qsTr("Good Portuguese and light. These still need to be downloaded; you can use any other model too.")
        Text {
            Layout.fillWidth: true
            visible: !!page.hw.cpu
            wrapMode: Text.WordWrap
            color: Theme.textFaint; font.pixelSize: 12
            text: page.hw.cpu ? qsTr("Your computer: %1 · %2 of memory").arg(page.hw.cpu.name || qsTr("processor")).arg(Status.memory(page.hw.memory.total))
                                + (page.hw.vram > 0 ? " · " + qsTr("graphics card with %1").arg(Status.memory(page.hw.vram)) : "") : ""
        }
        ModelSuggestions {}
    }

    Section {
        visible: cfg.advanced
        title: qsTr("Generation")
        iconName: "settings"
        actions: AppButton { compact: true; variant: "ghost"; iconName: "undo"; text: qsTr("Restore defaults"); onClicked: backend.resetSection("ai.generation") }
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
                label: qsTr("Live context"); from: 0; to: 10; stepSize: 1; suffix: qsTr(" messages")
                value: cfg.ai.memory_size; onMoved: v => backend.setConfig("ai.memory_size", Math.round(v))
                hint: qsTr("Latest exchanges with other viewers sent with each message (more = slower).")
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

    Section {
        visible: cfg.advanced
        title: qsTr("Answer quality")
        iconName: "check"
        description: qsTr("Correct first, funny second: a funny wrong answer is worse than a correct plain one.")
        SettingRow {
            label: qsTr("Precision first")
            description: qsTr("Math, facts and explanations are answered with little randomness; jokes and greetings keep the creativity set above.")
            AppSwitch { checked: cfg.ai.adaptive; onToggled: backend.setConfig("ai.adaptive", checked); Accessible.name: qsTr("Precision first") }
        }
        SettingRow {
            label: qsTr("Exact calculator")
            description: qsTr("Arithmetic in the chat (“how much is 15 times 3?”) is computed by ChatToon — never guessed — and the avatar says the result.")
            AppSwitch { checked: cfg.ai.math_tool; onToggled: backend.setConfig("ai.math_tool", checked); Accessible.name: qsTr("Exact calculator") }
        }
        SettingRow {
            label: qsTr("Verified reference")
            description: qsTr("Questions about computing and Linux get short checked facts (what CPU stands for, which distro BigLinux is based on…).")
            AppSwitch { checked: cfg.ai.reference; onToggled: backend.setConfig("ai.reference", checked); Accessible.name: qsTr("Verified reference") }
        }
        SettingRow {
            label: qsTr("Check every reply")
            description: qsTr("When a reply misses the verified result or repeats its own instructions, the avatar tries once more.")
            AppSwitch { checked: cfg.ai.validate; onToggled: backend.setConfig("ai.validate", checked); Accessible.name: qsTr("Check every reply") }
        }
    }

    Section {
        title: qsTr("Conversation memory")
        iconName: "users"
        description: qsTr("The avatar remembers what each viewer told it — separately per platform and account, so two people with the same name never mix.")
        actions: AppButton { compact: true; iconName: "chat"; text: qsTr("See memories"); onClicked: win.go("livechat") }
        SettingRow {
            label: qsTr("Remember during the live")
            description: qsTr("Follow-ups like “do you remember my app?” work. Kept in RAM only.")
            AppSwitch { checked: cfg.memory.enabled; onToggled: backend.setConfig("memory.enabled", checked); Accessible.name: qsTr("Remember during the live") }
        }
        SettingRow {
            label: qsTr("Remember between lives")
            description: qsTr("Saves what was really said in a private file on this computer, never sent anywhere. Off by default.")
            AppSwitch { enabled: cfg.memory.enabled; checked: cfg.memory.persist; onToggled: backend.setConfig("memory.persist", checked); Accessible.name: qsTr("Remember between lives") }
        }
        SettingRow {
            label: qsTr("Keep saved memories for")
            AppCombo {
                implicitWidth: 200
                enabled: cfg.memory.enabled && cfg.memory.persist
                textRole: "t"; valueRole: "v"
                model: [{ v: 1, t: qsTr("1 day") }, { v: 7, t: qsTr("7 days") }, { v: 30, t: qsTr("30 days") },
                        { v: 90, t: qsTr("90 days") }, { v: 365, t: qsTr("1 year") }, { v: 0, t: qsTr("Until I erase them") }]
                currentIndex: Math.max(0, model.findIndex(m => m.v === Number(cfg.memory.retention_days)))
                onActivated: backend.setConfig("memory.retention_days", currentValue)
            }
        }
        SettingRow {
            label: qsTr("Summarize long conversations")
            description: qsTr("While the chat is quiet, the model folds a long conversation into a short note. Cancelled as soon as someone writes.")
            AppSwitch { enabled: cfg.memory.enabled; checked: cfg.memory.summaries; onToggled: backend.setConfig("memory.summaries", checked); Accessible.name: qsTr("Summarize long conversations") }
        }
        Text {
            Layout.fillWidth: true
            text: qsTr("%1 viewer(s) remembered in this live · %2 exchange(s) saved on disk").arg(page.mem.viewers || 0).arg(page.mem.saved || 0)
            color: Theme.textMuted; font.pixelSize: 12; wrapMode: Text.WordWrap
        }
    }

    Section {
        visible: cfg.advanced
        title: qsTr("Generation diagnostics")
        iconName: "activity"
        description: qsTr("The latest replies: what kind of message it was, the settings used and the time spent. Nothing leaves this computer.")
        Text {
            visible: backend.diagnostics.length === 0
            text: qsTr("No reply generated yet. Simulate a message on the Characters page or go live.")
            color: Theme.textFaint; font.pixelSize: 12
        }
        Repeater {
            model: backend.diagnostics.slice(0, 8)
            RowLayout {
                required property var modelData
                Layout.fillWidth: true
                spacing: 8
                Text { text: new Date(modelData.time * 1000).toLocaleTimeString(Qt.locale(), "HH:mm:ss"); color: Theme.textFaint; font.family: Theme.mono; font.pixelSize: 11 }
                Chip { text: Status.intent(modelData.intent); tone: modelData.intent === "injection" ? Theme.warning : Theme.accent }
                Chip { visible: modelData.source === "tool"; text: qsTr("exact result"); tone: Theme.success; iconName: "check" }
                Chip { visible: modelData.source === "fallback"; text: qsTr("safe line"); tone: Theme.warning; iconName: "alert" }
                Chip { visible: (modelData.memory || 0) > 0; text: qsTr("%n memory item(s)", "", modelData.memory || 0); tone: Theme.accent2; iconName: "users" }
                Chip { visible: (modelData.references || 0) > 0; text: qsTr("reference"); tone: Theme.success; iconName: "book" }
                Chip { visible: (modelData.retries || 0) > 0; text: qsTr("retried"); tone: Theme.warning; iconName: "refresh" }
                Item { Layout.fillWidth: true }
                Text {
                    text: qsTr("temp. %1 · %2 + %3 tokens · %4 s").arg(Number(modelData.temperature).toFixed(2))
                              .arg(modelData.promptTokens || 0).arg(modelData.evalTokens || 0).arg(Number(modelData.seconds).toFixed(2))
                    color: Theme.textMuted; font.family: Theme.mono; font.pixelSize: 11
                }
            }
        }
    }
}
