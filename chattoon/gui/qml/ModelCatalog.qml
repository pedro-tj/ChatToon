import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

// Every model installed in Ollama: the one in use, the ones that can chat and the ones that
// cannot (with the reason). "Installed", "in use" and "loaded in memory" are separate states.
ColumnLayout {
    id: root
    property bool compact: false
    readonly property var ollama: backend.services.ollama || ({})
    readonly property var catalog: ollama.catalog && ollama.catalog.length ? ollama.catalog
                                 : (ollama.models || []).map(n => ({ name: n, chat: true, capabilities: ["completion"], size: 0 }))
    readonly property var chat: catalog.filter(m => m.chat)
    readonly property var other: catalog.filter(m => !m.chat)
    readonly property var loaded: ollama.loaded || []
    readonly property string selected: backend.config.ai.model
    readonly property bool selectedMissing: ollama.ok === true && selected !== "" && chat.findIndex(m => m.name === selected) < 0

    spacing: 12
    Layout.fillWidth: true

    function reasonText(m) {
        return ({ embedding: qsTr("Embedding model: turns text into numbers for search. It cannot hold a conversation."),
                  "no-completion": qsTr("This model does not generate text, so it cannot answer the chat."),
                  unreadable: qsTr("Ollama could not read this model: %1").arg(m.error || "") })[m.reason] || ""
    }
    function details(m) {
        const parts = []
        if (m.size) parts.push(Status.size(m.size))
        if (m.family) parts.push(m.family)
        if (m.parameters) parts.push(m.parameters)
        if (m.quantization) parts.push(m.quantization)
        if (m.contextLength) parts.push(qsTr("%1k context").arg(Math.round(m.contextLength / 1024)))
        return parts.join(" · ")
    }

    // the model the person chose disappeared: say so, never pick another silently
    Rectangle {
        Layout.fillWidth: true
        visible: root.selectedMissing
        implicitHeight: missRow.implicitHeight + 22
        radius: Theme.radiusSmall
        color: Theme.tint(Theme.warning, 0.12)
        border.color: Theme.tint(Theme.warning, 0.45)
        RowLayout {
            id: missRow
            anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; margins: 12 }
            spacing: 10
            Icon { name: "alert"; size: 18; color: Theme.warning }
            Text {
                Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Theme.text; font.pixelSize: 13
                text: qsTr("The model in use, %1, is not installed in this Ollama. Choose another one below or download it again.").arg(root.selected)
            }
        }
    }

    Text {
        visible: root.ollama.ok === true && root.catalog.length === 0
        Layout.fillWidth: true
        text: qsTr("No model installed yet. Download one of the suggestions below.")
        color: Theme.textMuted; font.pixelSize: 13; wrapMode: Text.WordWrap
    }
    Text {
        visible: root.ollama.ok !== true
        Layout.fillWidth: true
        text: qsTr("Start Ollama to see the installed models.")
        color: Theme.textFaint; font.pixelSize: 13
    }

    GridLayout {
        Layout.fillWidth: true
        columns: root.compact ? 1 : Math.max(1, Math.floor(width / 330))
        columnSpacing: 10
        rowSpacing: 10
        Repeater {
            // the model in use first, then by name
            model: root.chat.slice().sort((a, b) => (b.name === root.selected) - (a.name === root.selected) || a.name.localeCompare(b.name))
            Rectangle {
                id: card
                required property var modelData
                readonly property bool inUse: modelData.name === root.selected
                readonly property bool inMemory: root.loaded.indexOf(modelData.name) >= 0
                Layout.fillWidth: true
                implicitHeight: cardCol.implicitHeight + 24
                radius: Theme.radiusSmall
                color: inUse ? Theme.tint(Theme.success, Theme.dark ? 0.1 : 0.07) : Theme.field
                border.width: inUse ? 2 : 1
                border.color: inUse ? Theme.success : Theme.border
                Accessible.role: Accessible.ListItem
                Accessible.name: modelData.name + (inUse ? ", " + qsTr("In use") : ", " + qsTr("Installed"))

                ColumnLayout {
                    id: cardCol
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 12 }
                    spacing: 6
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Icon { name: card.inUse ? "checkCircle" : "bot"; size: 18; color: card.inUse ? Theme.success : Theme.textMuted }
                        Text {
                            Layout.fillWidth: true
                            text: card.modelData.name; textFormat: Text.PlainText
                            color: Theme.text; font.family: Theme.mono; font.pixelSize: 13; font.weight: Font.DemiBold; elide: Text.ElideMiddle
                        }
                        StateChip { text: card.inUse ? qsTr("In use") : qsTr("Installed"); tone: card.inUse ? "ok" : "idle"
                                    iconName: card.inUse ? "check" : "package" }
                    }
                    Text {
                        Layout.fillWidth: true
                        visible: text !== ""
                        text: root.details(card.modelData)
                        color: Theme.textMuted; font.pixelSize: 12; elide: Text.ElideRight
                    }
                    Flow {
                        Layout.fillWidth: true
                        spacing: 4
                        Repeater {
                            model: (card.modelData.capabilities || []).filter(c => c !== "completion")
                            Chip { required property string modelData; text: Status.capability(modelData); tone: Theme.accent }
                        }
                        Chip { visible: card.inMemory; text: qsTr("loaded in memory"); iconName: "zap"; tone: Theme.success }
                        Chip { visible: card.modelData.remote === true; text: qsTr("cloud (not local)"); iconName: "cloud"; tone: Theme.warning }
                        Chip { visible: card.modelData.capabilitiesKnown === false; text: qsTr("capabilities estimated"); tone: Theme.textMuted
                               tip: qsTr("This Ollama version does not report what the model can do.") }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        visible: !card.inUse
                        Item { Layout.fillWidth: true }
                        AppButton {
                            compact: true; iconName: "check"; text: qsTr("Use this model")
                            onClicked: backend.aiCenter.selectModel(card.modelData.name)
                        }
                    }
                }
            }
        }
    }

    // installed, but unable to answer the chat — shown, never hidden
    ColumnLayout {
        Layout.fillWidth: true
        visible: root.other.length > 0
        spacing: 8
        Text {
            text: qsTr("Installed, but cannot answer the chat (%1)").arg(root.other.length)
            color: Theme.textMuted; font.pixelSize: 13; font.weight: Font.Medium
        }
        Repeater {
            model: root.other
            RowLayout {
                required property var modelData
                Layout.fillWidth: true
                spacing: 10
                Icon { name: "minus"; size: 16; color: Theme.textFaint }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 1
                    Text { text: modelData.name + (modelData.size ? "  ·  " + Status.size(modelData.size) : ""); textFormat: Text.PlainText
                           color: Theme.text; font.family: Theme.mono; font.pixelSize: 12 }
                    Text { Layout.fillWidth: true; text: root.reasonText(modelData); color: Theme.textFaint; font.pixelSize: 12; wrapMode: Text.WordWrap }
                }
            }
        }
    }
}
