import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."

Page {
    id: page
    readonly property var cfg: backend.config
    readonly property var o: cfg.overlay
    readonly property var rt: backend.runtimeState

    title: qsTr("OBS Studio")
    subtitle: qsTr("Add the avatar to your scene as a Browser Source. The address only works on this computer.")

    Section {
        title: qsTr("Overlay address")
        iconName: "broadcast"
        description: rt.obs > 0 ? qsTr("%n OBS source(s) connected right now", "", rt.obs) : qsTr("Not connected to OBS yet")
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            AppTextField { Layout.fillWidth: true; readOnly: true; text: rt.overlayUrl; font.family: Theme.mono; Accessible.name: qsTr("Overlay address") }
            AppButton { variant: "primary"; iconName: "copy"; text: qsTr("Copy"); enabled: rt.overlayUrl !== ""; onClicked: backend.copyText(rt.overlayUrl) }
            AppButton { iconName: "external"; tip: qsTr("Open in the browser"); enabled: rt.overlayUrl !== ""; onClicked: backend.openUrl(rt.overlayUrl) }
        }
        Repeater {
            model: [
                qsTr("In OBS, click + under Sources and choose Browser."),
                qsTr("Paste the address above in URL. Width 1920, height 1080."),
                qsTr("Leave “Shutdown source when not visible” off so the avatar keeps its state."),
                cfg.voice.audio_output === "overlay" ? qsTr("Enable “Control audio via OBS” — the voice will come from this source.")
                                                     : qsTr("The voice plays on this computer: capture it with Desktop Audio."),
                qsTr("The background is transparent. Resize and position the source in your scene as you like."),
            ]
            RowLayout {
                required property string modelData
                required property int index
                Layout.fillWidth: true
                spacing: 10
                Rectangle {
                    width: 24; height: 24; radius: 12
                    color: Theme.tint(Theme.accent, 0.18)
                    Text { anchors.centerIn: parent; text: index + 1; color: Theme.accent; font.pixelSize: 12; font.weight: Font.Bold }
                }
                Text { Layout.fillWidth: true; text: modelData; color: Theme.text; font.pixelSize: 13; wrapMode: Text.WordWrap }
            }
        }
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: 16
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
            title: qsTr("Appearance")
            iconName: "palette"
            LabeledSlider { label: qsTr("Size"); from: 0.3; to: 2.5; stepSize: 0.05; decimals: 2; value: o.scale; onMoved: v => backend.setConfig("overlay.scale", v) }
            LabeledSlider { label: qsTr("Horizontal position"); from: -1; to: 1; stepSize: 0.02; decimals: 2; value: o.position_x; onMoved: v => backend.setConfig("overlay.position_x", v) }
            LabeledSlider { label: qsTr("Vertical position"); from: -1; to: 1; stepSize: 0.02; decimals: 2; value: o.position_y; onMoved: v => backend.setConfig("overlay.position_y", v) }
            LabeledSlider { label: qsTr("Rotation"); from: -60; to: 60; value: o.rotation; suffix: "°"; onMoved: v => backend.setConfig("overlay.rotation", v) }
            LabeledSlider { label: qsTr("Camera zoom"); from: 0.5; to: 2.5; stepSize: 0.05; decimals: 2; value: o.camera_zoom; onMoved: v => backend.setConfig("overlay.camera_zoom", v) }
            LabeledSlider { label: qsTr("Lighting"); from: 0.3; to: 2; stepSize: 0.05; decimals: 2; value: o.light; onMoved: v => backend.setConfig("overlay.light", v) }
            SettingRow { label: qsTr("Speech bubble"); AppSwitch { checked: o.show_bubble; onToggled: backend.setConfig("overlay.show_bubble", checked) } }
            SettingRow { label: qsTr("Show the viewer's name"); AppSwitch { checked: o.show_author; onToggled: backend.setConfig("overlay.show_author", checked) } }
            SettingRow { label: qsTr("Soft shadow"); AppSwitch { checked: o.shadows; onToggled: backend.setConfig("overlay.shadows", checked) } }
            SettingRow {
                label: qsTr("Background")
                Segmented {
                    model: [{ value: "transparent", label: qsTr("Transparent") }, { value: "green", label: qsTr("Green (chroma key)") }]
                    current: o.background
                    onActivated: v => backend.setConfig("overlay.background", v)
                }
            }
            SettingRow {
                label: qsTr("Quality")
                description: qsTr("Lower it on modest GPUs.")
                Segmented {
                    model: [{ value: "low", label: qsTr("Low") }, { value: "medium", label: qsTr("Medium") }, { value: "high", label: qsTr("High") }]
                    current: o.quality
                    onActivated: v => backend.setConfig("overlay.quality", v)
                }
            }
            SettingRow {
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
