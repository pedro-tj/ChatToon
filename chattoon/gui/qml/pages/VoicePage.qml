import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."

Page {
    id: page
    readonly property var cfg: backend.config
    readonly property var tts: backend.services.tts
    readonly property var current: backend.characters.find(c => c.id === cfg.character) || {}
    readonly property var voices: (tts.voices || []).slice().sort((a, b) => {
        const lang = cfg.ai.reply_language.toLowerCase().split("-")[0]
        const pa = a.language.toLowerCase().startsWith(lang) ? 0 : 1, pb = b.language.toLowerCase().startsWith(lang) ? 0 : 1
        return pa - pb || a.name.localeCompare(b.name)
    })
    readonly property var voiceItems: [{ id: "", label: qsTr("Automatic (best match for the character)") }].concat(
        voices.map(v => ({ id: v.id, label: v.name + " · " + v.backend + " · " + v.language })))

    title: qsTr("Voice")
    subtitle: qsTr("Speech comes from TTS BigLinux (RHVoice, Piper, espeak-ng). Each character can have its own voice.")
    header: AppButton { iconName: "refresh"; text: qsTr("Check again"); onClicked: backend.refreshServices() }

    Section {
        title: qsTr("TTS BigLinux")
        iconName: "volume"
        description: tts.ok === true ? qsTr("%n voice(s) available", "", (tts.voices || []).length)
                   : tts.ok === false ? (tts.error || "") : qsTr("Checking…")
        SettingRow {
            label: qsTr("Speak the replies")
            description: qsTr("When off, replies appear only in the speech bubble.")
            AppSwitch { checked: cfg.voice.enabled; onToggled: backend.setConfig("voice.enabled", checked) }
        }
        Text {
            visible: tts.ok === false
            Layout.fillWidth: true
            text: qsTr("Install it with:  sudo pacman -S tts-biglinux")
            color: Theme.warning; font.family: Theme.mono; font.pixelSize: 12
        }
    }

    Section {
        title: qsTr("Voice of %1").arg(page.current.name || "")
        iconName: "mic"
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            AppCombo {
                id: voiceBox
                Layout.fillWidth: true
                textRole: "label"; valueRole: "id"
                model: page.voiceItems
                currentIndex: Math.max(0, indexOfValue(cfg.current.voice_id))
                onActivated: backend.setConfig("current.voice_id", currentValue)
            }
            AppButton { iconName: "play"; text: qsTr("Preview"); enabled: tts.ok === true; onClicked: backend.previewVoice(voiceBox.currentValue) }
        }
        GridLayout {
            Layout.fillWidth: true
            columns: 2
            columnSpacing: 28
            uniformCellWidths: true
            LabeledSlider { label: qsTr("Speed"); from: -100; to: 100; value: cfg.current.voice_rate; onMoved: v => backend.setConfig("current.voice_rate", Math.round(v)) }
            LabeledSlider { label: qsTr("Pitch"); from: -100; to: 100; value: cfg.current.voice_pitch; hint: qsTr("Supported by RHVoice and espeak-ng."); onMoved: v => backend.setConfig("current.voice_pitch", Math.round(v)) }
        }
    }

    Section {
        title: qsTr("Audio output")
        iconName: "broadcast"
        description: qsTr("Each reply is played exactly once, in one place.")
        LabeledSlider { label: qsTr("Volume"); value: cfg.voice.volume; suffix: "%"; onMoved: v => backend.setConfig("voice.volume", Math.round(v)) }
        Segmented {
            model: [{ value: "desktop", label: qsTr("This computer") }, { value: "overlay", label: qsTr("Inside OBS") }]
            current: cfg.voice.audio_output
            onActivated: v => backend.setConfig("voice.audio_output", v)
        }
        Text {
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            color: Theme.textMuted; font.pixelSize: 12
            text: cfg.voice.audio_output === "overlay"
                  ? qsTr("The OBS browser source plays the voice. In its properties enable “Control audio via OBS” so it goes to the stream and to your monitoring. If OBS is not connected, the app plays it instead.")
                  : qsTr("The app plays the voice through your speakers/headphones. Capture it in OBS with Desktop Audio (or an application audio capture of ChatToon).")
        }
    }
}
