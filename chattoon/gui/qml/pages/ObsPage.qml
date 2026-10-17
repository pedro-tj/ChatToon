import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."

Page {
    id: page
    readonly property var cfg: backend.config
    readonly property var o: cfg.overlay
    readonly property var rt: backend.runtimeState

    readonly property string mode: cfg.display.mode

    title: qsTr("Where to show")
    subtitle: qsTr("Choose where your character appears: in OBS Studio for live streams, in a window on your desktop, or both.")

    Section {
        title: qsTr("Where should your character appear?")
        iconName: "monitor"
        DisplayModePicker {}
    }

    Section {
        visible: page.mode !== "obs"
        title: qsTr("Window on the computer")
        iconName: "appWindow"
        description: qsTr("Only the character and its speech bubble, with a transparent background.")
        actions: AppButton { visible: cfg.advanced; compact: true; variant: "ghost"; iconName: "undo"; text: qsTr("Restore defaults"); onClicked: backend.resetSection("display") }
        CharacterWindowCard {}
    }

    Section {
        visible: page.mode !== "window"
        title: qsTr("Where is your OBS Studio?")
        iconName: "broadcast"
        description: rt.obs > 0 ? qsTr("%n OBS source(s) connected right now", "", rt.obs) : qsTr("Not connected to OBS yet")
        ObsAccess {}
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: 16
        visible: page.mode !== "window"
        Preview {
            Layout.fillWidth: true
            Layout.preferredWidth: 1
            Layout.preferredHeight: 520
            Layout.alignment: Qt.AlignTop
            url: rt.overlayUrl
        }
        Section {
            Layout.preferredWidth: 1
            Layout.alignment: Qt.AlignTop
            title: qsTr("Appearance in OBS")
            iconName: "palette"
            actions: AppButton { compact: true; variant: "ghost"; iconName: "undo"; text: qsTr("Restore defaults"); onClicked: backend.resetSection("overlay.appearance") }
            LabeledSlider { label: qsTr("Size"); from: 0.3; to: 2.5; stepSize: 0.05; decimals: 2; value: o.scale; onMoved: v => backend.setConfig("overlay.scale", v) }
            LabeledSlider { label: qsTr("Horizontal position"); from: -1; to: 1; stepSize: 0.02; decimals: 2; value: o.position_x; onMoved: v => backend.setConfig("overlay.position_x", v) }
            LabeledSlider { label: qsTr("Vertical position"); from: -1; to: 1; stepSize: 0.02; decimals: 2; value: o.position_y; onMoved: v => backend.setConfig("overlay.position_y", v) }
            LabeledSlider { visible: cfg.advanced; label: qsTr("Rotation"); from: -60; to: 60; value: o.rotation; suffix: "°"; onMoved: v => backend.setConfig("overlay.rotation", v) }
            LabeledSlider { visible: cfg.advanced; label: qsTr("Camera zoom"); from: 0.5; to: 2.5; stepSize: 0.05; decimals: 2; value: o.camera_zoom; onMoved: v => backend.setConfig("overlay.camera_zoom", v) }
            LabeledSlider { visible: cfg.advanced; label: qsTr("Lighting"); from: 0.3; to: 2; stepSize: 0.05; decimals: 2; value: o.light; onMoved: v => backend.setConfig("overlay.light", v) }
            SettingRow { label: qsTr("Speech bubble"); AppSwitch { checked: o.show_bubble; onToggled: backend.setConfig("overlay.show_bubble", checked) } }
            SettingRow { label: qsTr("Show the viewer's name"); AppSwitch { checked: o.show_author; onToggled: backend.setConfig("overlay.show_author", checked) } }
            SettingRow {
                label: qsTr("Show the platform of the message")
                description: qsTr("A small “Twitch • Ana” tag on the viewer's message.")
                AppSwitch { checked: o.show_platform; onToggled: backend.setConfig("overlay.show_platform", checked); Accessible.name: qsTr("Show the platform of the message") }
            }
            SettingRow { visible: cfg.advanced; label: qsTr("Soft shadow"); AppSwitch { checked: o.shadows; onToggled: backend.setConfig("overlay.shadows", checked) } }
            SettingRow {
                label: qsTr("Background")
                Segmented {
                    model: [{ value: "transparent", label: qsTr("Transparent") }, { value: "green", label: qsTr("Green (chroma key)") }]
                    current: o.background
                    onActivated: v => backend.setConfig("overlay.background", v)
                }
            }
            SettingRow {
                visible: cfg.advanced
                label: qsTr("Quality")
                description: qsTr("Lower it on modest GPUs.")
                Segmented {
                    model: [{ value: "low", label: qsTr("Low") }, { value: "medium", label: qsTr("Medium") }, { value: "high", label: qsTr("High") }]
                    current: o.quality
                    onActivated: v => backend.setConfig("overlay.quality", v)
                }
            }
            SettingRow {
                visible: cfg.advanced
                label: qsTr("Frame rate limit")
                Segmented {
                    model: [{ value: 30, label: "30" }, { value: 60, label: "60" }]
                    current: o.fps
                    onActivated: v => backend.setConfig("overlay.fps", v)
                }
            }
        }
    }
}
