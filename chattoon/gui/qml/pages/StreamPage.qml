import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."

Page {
    id: page
    readonly property var ctx: backend.config.context

    title: qsTr("Stream context")
    subtitle: qsTr("Tell the avatar what your channel is about so the jokes fit. It never invents what is not here.")

    component Field: ColumnLayout {
        property string label
        property string key
        property string placeholder
        property bool multiline: false
        Layout.fillWidth: true
        spacing: 6
        Text { text: parent.label; color: Theme.text; font.pixelSize: 13; font.weight: Font.Medium }
        AppTextField {
            Layout.fillWidth: true
            visible: !parent.multiline
            text: page.ctx[parent.key] || ""
            placeholderText: parent.placeholder
            onEditingFinished: backend.setConfig("context." + parent.key, text)
        }
        AppTextArea {
            Layout.fillWidth: true
            visible: parent.multiline
            text: page.ctx[parent.key] || ""
            placeholderText: parent.placeholder
            onEditingFinished: backend.setConfig("context." + parent.key, text)
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
}
