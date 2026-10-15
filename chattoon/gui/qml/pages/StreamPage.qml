import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."

Page {
    id: page
    readonly property var ctx: backend.config.context
    readonly property var meta: backend.metadata

    title: qsTr("Stream context")
    subtitle: qsTr("Tell the avatar what your channel is about so the jokes fit. It never invents what is not here.")

    function when(t) { return t ? new Date(t * 1000).toLocaleTimeString(Qt.locale(), "HH:mm") : "" }
    function factLabel(key) {
        return ({ channel: qsTr("Channel"), title: qsTr("Live title"), category: qsTr("Category"), description: qsTr("Description"),
                  tags: qsTr("Tags"), url: qsTr("Link") })[key] || key
    }

    component Field: ColumnLayout {
        id: field
        property string label
        property string key
        property string placeholder
        property bool multiline: false
        property bool assist: true  // the AI button next to the label
        Layout.fillWidth: true
        spacing: 6
        RowLayout {
            Layout.fillWidth: true
            spacing: 6
            Text { text: field.label; color: Theme.text; font.pixelSize: 13; font.weight: Font.Medium; Layout.fillWidth: true; wrapMode: Text.WordWrap }
            AppButton {
                visible: field.assist
                compact: true; variant: "ghost"; iconName: "sparkles"
                implicitHeight: 26
                tip: qsTr("Suggest with AI from your sources")
                Accessible.name: qsTr("Suggest %1 with AI").arg(field.label)
                onClicked: assistant.show(field.key, field.label)
            }
        }
        AppTextField {
            Layout.fillWidth: true
            visible: !field.multiline
            text: page.ctx[field.key] || ""
            placeholderText: field.placeholder
            onEditingFinished: backend.setConfig("context." + field.key, text)
        }
        AppTextArea {
            Layout.fillWidth: true
            visible: field.multiline
            text: page.ctx[field.key] || ""
            placeholderText: field.placeholder
            onEditingFinished: backend.setConfig("context." + field.key, text)
        }
    }

    // ------------------------------------------------------------ what the platforms publish
    Section {
        title: qsTr("From your sources")
        iconName: "layers"
        description: qsTr("What your streaming platforms publish about the channel and this live. The AI suggestions use it; nothing changes without your approval.")
        actions: AppButton {
            compact: true; iconName: "refresh"
            text: page.meta.loading ? qsTr("Reading…") : qsTr("Read from sources")
            enabled: !page.meta.loading && backend.sources.length > 0
            onClicked: backend.fetchMetadata(true)
        }
        Text {
            Layout.fillWidth: true
            visible: backend.sources.length === 0
            text: qsTr("Add a streaming platform first (Streaming platforms page).")
            color: Theme.textFaint; font.pixelSize: 12; wrapMode: Text.WordWrap
        }
        Text {
            Layout.fillWidth: true
            visible: backend.sources.length > 0 && (page.meta.sources || []).length === 0 && !page.meta.loading
            text: qsTr("Press “Read from sources” to see what each platform says about this live.")
            color: Theme.textFaint; font.pixelSize: 12; wrapMode: Text.WordWrap
        }
        BusyDots { visible: page.meta.loading }
        Repeater {
            model: page.meta.sources || []
            ColumnLayout {
                required property var modelData
                Layout.fillWidth: true
                spacing: 3
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    PlatformBadge { platform: modelData.platform; size: 18 }
                    Text { text: (win.platformInfo[modelData.platform] || {}).label || modelData.platform; color: Theme.text; font.pixelSize: 13; font.weight: Font.DemiBold }
                    Chip { text: Status.meta(modelData.code); tone: Status.metaTone(modelData.code) }
                    Item { Layout.fillWidth: true }
                    Text { text: qsTr("read at %1").arg(page.when(modelData.fetchedAt)); color: Theme.textFaint; font.pixelSize: 11 }
                }
                Repeater {
                    model: ["channel", "title", "category", "tags"].filter(k => modelData[k] && (k !== "tags" || modelData.tags.length))
                    Text {
                        required property string modelData
                        Layout.fillWidth: true
                        Layout.leftMargin: 26
                        text: page.factLabel(modelData) + ": " + (modelData === "tags" ? parent.modelData.tags.join(", ") : parent.modelData[modelData])
                        textFormat: Text.PlainText; color: Theme.textMuted; font.pixelSize: 12; elide: Text.ElideRight
                    }
                }
                Text {
                    Layout.fillWidth: true
                    Layout.leftMargin: 26
                    visible: (modelData.method || "") !== ""
                    text: qsTr("Read with: %1").arg(modelData.method.replace("(unofficial)", qsTr("(unofficial)")).replace("(official)", qsTr("(official)")))
                    textFormat: Text.PlainText; color: Theme.textFaint; font.pixelSize: 11; wrapMode: Text.WordWrap
                }
            }
        }
    }

    Section {
        title: qsTr("About the channel")
        iconName: "book"
        GridLayout {
            Layout.fillWidth: true
            columns: 2
            columnSpacing: 20
            rowSpacing: 14
            Field { label: qsTr("Channel name"); key: "channel_name"; placeholder: "BigLinux" }
            Field { label: qsTr("Host"); key: "host_name"; placeholder: qsTr("Who presents the stream") }
            Field { label: qsTr("Today's topic"); key: "topic"; placeholder: qsTr("KDE Plasma 6, gaming on Linux…") }
            Field { label: qsTr("Guests"); key: "guests"; placeholder: qsTr("Names, separated by commas") }
        }
        Field { label: qsTr("Description"); key: "description"; multiline: true; placeholder: qsTr("A few lines about the channel and this live stream.") }
        Field { label: qsTr("Links and projects worth mentioning"); key: "links"; multiline: true }
        Field { label: qsTr("Channel catchphrases"); key: "catchphrases"; placeholder: qsTr("Phrases the community knows") }
    }

    Section {
        title: qsTr("Topics")
        iconName: "shield"
        Field { label: qsTr("Welcome topics"); key: "allowed_topics"; placeholder: qsTr("Linux, free software, games, AI…") }
        Field {
            label: qsTr("Forbidden topics — the avatar dodges them with a joke")
            key: "forbidden_topics"
            placeholder: qsTr("Politics, religion…")
        }
    }

    Section {
        title: qsTr("Calls to action")
        iconName: "zap"
        description: qsTr("Occasionally appended to a reply — never in every one.")
        actions: AppButton {
            compact: true; variant: "ghost"; iconName: "sparkles"; text: qsTr("Suggest")
            tip: qsTr("Suggest with AI from your sources")
            onClicked: assistant.show("promo_messages", qsTr("Calls to action"))
        }
        SettingRow {
            label: qsTr("Enable calls to action")
            AppSwitch { checked: page.ctx.promo_enabled; onToggled: backend.setConfig("context.promo_enabled", checked) }
        }
        AppTextArea {
            Layout.fillWidth: true
            text: (page.ctx.promo_messages || []).join("\n")
            placeholderText: qsTr("One per line, e.g. Drop a like!")
            onEditingFinished: backend.setConfig("context.promo_messages", text)
        }
        SettingRow {
            label: qsTr("At most one every")
            NumberStepper { value: page.ctx.promo_every; from: 1; to: 50; step: 1; suffix: qsTr(" replies"); onEdited: v => backend.setConfig("context.promo_every", v) }
        }
        SettingRow {
            label: qsTr("And never more often than")
            NumberStepper { value: page.ctx.promo_cooldown; from: 30; to: 3600; step: 30; suffix: " s"; onEdited: v => backend.setConfig("context.promo_cooldown", v) }
        }
    }

    // ------------------------------------------------------------ AI assistant
    Popup {
        id: assistant
        objectName: "contextAssistant"
        property string key
        property string label
        property var selected: []  // source ids the suggestion may use
        readonly property var sg: backend.suggestion
        readonly property bool mine: sg.field === key
        readonly property bool loading: mine && !!sg.loading
        function show(k, l) {
            key = k; label = l
            selected = backend.sources.map(s => s.id)
            open()
            backend.suggestContext(k, selected)
        }
        function regenerate() { backend.suggestContext(key, selected) }
        function errorText(code) {
            return ({
                "no-data": qsTr("There is nothing to suggest from: fill in the topic or connect a source that publishes the live's information."),
                "no-model": qsTr("Choose an Ollama model on the Artificial intelligence page first."),
                "ai-failed": qsTr("The AI could not write a suggestion this time. Try again."),
                "no-guests": qsTr("No platform says who the guests are, so ChatToon does not guess. Type them yourself."),
                "unknown-field": qsTr("This field has no assistant.")
            })[code] || code
        }

        parent: Overlay.overlay
        anchors.centerIn: parent
        width: Math.min(parent.width - 80, 720)
        height: Math.min(parent.height - 60, body.implicitHeight + 40)
        modal: true
        padding: 20
        background: Rectangle { radius: Theme.radius; color: Theme.surfaceStrong; border.width: 1; border.color: Theme.borderStrong }

        Flickable {
            anchors.fill: parent
            contentHeight: body.implicitHeight
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            ColumnLayout {
                id: body
                width: parent.width
                spacing: 12

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10
                    Rectangle {
                        width: 30; height: 30; radius: 9
                        color: Theme.tint(Theme.accent, Theme.dark ? 0.18 : 0.12)
                        Icon { anchors.centerIn: parent; name: "sparkles"; size: 16; color: Theme.accent }
                    }
                    Text { Layout.fillWidth: true; text: qsTr("AI assistant — %1").arg(assistant.label); color: Theme.text; font.pixelSize: 17; font.weight: Font.Bold; wrapMode: Text.WordWrap }
                    AppButton { compact: true; variant: "ghost"; iconName: "x"; tip: qsTr("Cancel"); Accessible.name: tip; onClicked: assistant.close() }
                }

                // which sources to use
                Flow {
                    Layout.fillWidth: true
                    spacing: 6
                    visible: backend.sources.length > 1
                    Text { text: qsTr("Use:"); color: Theme.textMuted; font.pixelSize: 12; height: 32; verticalAlignment: Text.AlignVCenter }
                    Repeater {
                        model: backend.sources
                        AppCheck {
                            required property var modelData
                            text: ((win.platformInfo[modelData.platform] || {}).label || modelData.platform) + (modelData.label ? " · " + modelData.label : "")
                            checked: assistant.selected.indexOf(modelData.id) >= 0
                            onToggled: {
                                const list = assistant.selected.filter(x => x !== modelData.id)
                                if (checked) list.push(modelData.id)
                                assistant.selected = list
                            }
                        }
                    }
                }

                RowLayout {
                    visible: assistant.loading
                    spacing: 8
                    BusyDots {}
                    Text { text: qsTr("Reading your sources and writing a suggestion…"); color: Theme.textMuted; font.pixelSize: 13 }
                }

                // what was found (and what was not)
                ColumnLayout {
                    Layout.fillWidth: true
                    visible: assistant.mine && !assistant.loading && ((assistant.sg.facts || []).length + (assistant.sg.missing || []).length) > 0
                    spacing: 4
                    Text { text: qsTr("Information found"); color: Theme.textMuted; font.pixelSize: 12; font.weight: Font.DemiBold }
                    Repeater {
                        model: (assistant.sg.facts || []).filter(f => f.key !== "description").slice(0, 8)
                        RowLayout {
                            required property var modelData
                            Layout.fillWidth: true
                            spacing: 6
                            PlatformBadge { platform: modelData.platform; size: 16 }
                            Text {
                                Layout.fillWidth: true
                                text: page.factLabel(modelData.key) + ": " + modelData.value
                                textFormat: Text.PlainText; color: Theme.text; font.pixelSize: 12; elide: Text.ElideRight
                            }
                            Text { text: page.when(modelData.fetchedAt); color: Theme.textFaint; font.pixelSize: 11 }
                        }
                    }
                    Repeater {
                        model: assistant.sg.missing || []
                        RowLayout {
                            required property var modelData
                            Layout.fillWidth: true
                            spacing: 6
                            PlatformBadge { platform: modelData.platform; size: 16 }
                            Text { Layout.fillWidth: true; text: modelData.label + ": " + Status.meta(modelData.code); color: Theme.textFaint; font.pixelSize: 12; elide: Text.ElideRight }
                        }
                    }
                }

                // sources that disagree: shown, never decided silently
                Rectangle {
                    Layout.fillWidth: true
                    visible: assistant.mine && !assistant.loading && (assistant.sg.conflicts || []).length > 0
                    implicitHeight: conflictCol.implicitHeight + 16
                    radius: Theme.radiusSmall
                    color: Theme.tint(Theme.warning, 0.12)
                    ColumnLayout {
                        id: conflictCol
                        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 8 }
                        spacing: 2
                        Text { text: qsTr("Your sources disagree — choose which ones to use above:"); color: Theme.text; font.pixelSize: 12; font.weight: Font.DemiBold; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                        Repeater {
                            model: assistant.sg.conflicts || []
                            Text {
                                required property var modelData
                                Layout.fillWidth: true
                                text: page.factLabel(modelData.key) + ": " + modelData.values.map(v => v.label + " “" + v.value + "”").join(" · ")
                                textFormat: Text.PlainText; color: Theme.textMuted; font.pixelSize: 12; wrapMode: Text.WordWrap
                            }
                        }
                    }
                }

                Text {
                    Layout.fillWidth: true
                    visible: assistant.mine && !assistant.loading && (assistant.sg.error || "") !== ""
                    text: assistant.errorText(assistant.sg.error || "")
                    color: Theme.warning; font.pixelSize: 13; wrapMode: Text.WordWrap
                }

                // current value vs suggestion
                ColumnLayout {
                    Layout.fillWidth: true
                    visible: assistant.mine && !assistant.loading && (assistant.sg.error || "") === ""
                    spacing: 6
                    Text { text: qsTr("Current value"); color: Theme.textMuted; font.pixelSize: 12; font.weight: Font.DemiBold }
                    Text {
                        Layout.fillWidth: true
                        text: (assistant.sg.current || "") !== "" ? assistant.sg.current : qsTr("(empty)")
                        textFormat: Text.PlainText; color: Theme.textMuted; font.pixelSize: 13; wrapMode: Text.WordWrap
                        maximumLineCount: 6; elide: Text.ElideRight
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: qsTr("Suggestion"); color: Theme.text; font.pixelSize: 12; font.weight: Font.DemiBold; Layout.fillWidth: true }
                        Chip { visible: !!assistant.sg.ai; text: qsTr("written by AI — check it"); iconName: "sparkles"; tone: Theme.accent }
                        Chip { visible: assistant.mine && !assistant.sg.ai; text: qsTr("taken from your sources"); iconName: "check"; tone: Theme.success }
                    }
                    AppTextArea {
                        id: suggestionText
                        Layout.fillWidth: true
                        text: assistant.mine ? (assistant.sg.value || "") : ""
                        Accessible.name: qsTr("Suggestion")
                    }
                    Text {
                        Layout.fillWidth: true
                        visible: !!assistant.sg.merge
                        text: qsTr("New items come after yours; nothing you wrote is removed.")
                        color: Theme.textFaint; font.pixelSize: 12; wrapMode: Text.WordWrap
                    }
                    Text {
                        Layout.fillWidth: true
                        visible: (assistant.sg.note || "") !== ""
                        text: assistant.sg.note === "account-name" ? qsTr("This is the account name on the platform — confirm it is how the host wants to be called.")
                            : assistant.sg.note === "promo-disabled" ? qsTr("Calls to action are switched off. Applying keeps them off; switch them on yourself if you want.")
                            : (assistant.sg.note || "").startsWith("category:") ? qsTr("Category on the platform: %1").arg((assistant.sg.note || "").slice(9))
                            : ""
                        color: Theme.textFaint; font.pixelSize: 12; wrapMode: Text.WordWrap
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    Item { Layout.fillWidth: true }
                    AppButton { text: qsTr("Cancel"); variant: "ghost"; onClicked: assistant.close() }
                    AppButton {
                        iconName: "edit"; text: qsTr("Edit")
                        enabled: assistant.mine && !assistant.loading && (assistant.sg.error || "") === ""
                        onClicked: suggestionText.edit()
                    }
                    AppButton {
                        iconName: "refresh"; text: qsTr("Regenerate")
                        enabled: !assistant.loading
                        onClicked: assistant.regenerate()
                    }
                    AppButton {
                        variant: "primary"; iconName: "check"; text: qsTr("Apply suggestion")
                        enabled: assistant.mine && !assistant.loading && suggestionText.text.trim() !== ""
                        onClicked: { backend.applySuggestion(assistant.key, suggestionText.text); assistant.close() }
                    }
                }
            }
        }
    }
}
