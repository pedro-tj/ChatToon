import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."

Page {
    id: page
    readonly property var cfg: backend.config
    readonly property var p: cfg.current.personality
    readonly property var current: backend.characters.find(c => c.id === cfg.character) || {}

    title: qsTr("Personality")
    subtitle: qsTr("Tune %1's humour. Changes apply to the next reply.").arg(current.name || "")

    Section {
        title: qsTr("Style")
        iconName: "sparkles"
        description: qsTr("Start from a profile and fine-tune it below. Moving a slider switches to Custom.")
        Segmented {
            model: [{ value: "friendly", label: qsTr("Friendly") }, { value: "comedian", label: qsTr("Comedian") },
                    { value: "troll", label: qsTr("Teaser") }, { value: "geek", label: qsTr("Geek") },
                    { value: "chaotic", label: qsTr("Controlled chaos") }, { value: "custom", label: qsTr("Custom") }]
            current: page.p.preset
            onActivated: v => v === "custom" ? backend.setConfig("current.personality.preset", "custom") : backend.applyPreset(v)
        }
    }

    Section {
        title: qsTr("Humour dials")
        iconName: "smile"
        GridLayout {
            Layout.fillWidth: true
            columns: width > 760 ? 3 : 2
            columnSpacing: 28
            uniformCellWidths: true
            rowSpacing: 14
            Repeater {
                model: [
                    { key: "humor", label: qsTr("Humour") }, { key: "sarcasm", label: qsTr("Sarcasm") },
                    { key: "irony", label: qsTr("Irony") }, { key: "creativity", label: qsTr("Creativity") },
                    { key: "energy", label: qsTr("Energy") }, { key: "formality", label: qsTr("Formality") },
                    { key: "memes", label: qsTr("Memes") }, { key: "geek", label: qsTr("Geek references") },
                    { key: "provocation", label: qsTr("Friendly teasing") },
                ]
                LabeledSlider {
                    required property var modelData
                    label: modelData.label
                    value: page.p[modelData.key]
                    onMoved: v => backend.setConfig("current.personality." + modelData.key, Math.round(v))
                }
            }
        }
    }

    Section {
        title: qsTr("Replies")
        iconName: "chat"
        SettingRow {
            label: qsTr("Reply length")
            description: qsTr("Short replies keep the stream flowing.")
            Segmented {
                model: [{ value: "short", label: qsTr("Short") }, { value: "medium", label: qsTr("Medium") }]
                current: page.p.length
                onActivated: v => backend.setConfig("current.personality.length", v)
            }
        }
        SettingRow {
            label: qsTr("Pause between replies")
            description: qsTr("How often the avatar may talk. Higher values make it chat less.")
            NumberStepper { value: cfg.chat.min_interval; from: 0; to: 120; step: 1; suffix: " s"; onEdited: v => backend.setConfig("chat.min_interval", v) }
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 6
            Text { text: qsTr("Your own instructions (optional)"); color: Theme.text; font.pixelSize: 13; font.weight: Font.Medium }
            AppTextArea {
                Layout.fillWidth: true
                text: page.p.custom_prompt
                placeholderText: qsTr("E.g.: Call everyone 'creature' and make jokes about coffee.")
                onEditingFinished: backend.setConfig("current.personality.custom_prompt", text)
            }
            Text {
                Layout.fillWidth: true
                text: qsTr("Viewers can never change these rules: chat messages are treated as content, not instructions.")
                color: Theme.textFaint; font.pixelSize: 11; wrapMode: Text.WordWrap
            }
        }
    }
}
