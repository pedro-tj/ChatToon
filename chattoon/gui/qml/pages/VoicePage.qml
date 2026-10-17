import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."

Page {
    id: page
    readonly property var cfg: backend.config
    readonly property var tts: backend.services.tts
    readonly property var current: backend.characters.find(c => c.id === cfg.character) || {}
    readonly property var engineNames: ({ rhvoice: "RHVoice", "espeak-ng": "espeak-ng", piper: "Piper", kokoro: "Kokoro" })
    readonly property var voices: (tts.voices || []).slice().sort((a, b) => {
        const lang = cfg.ai.reply_language.toLowerCase().split("-")[0]
        const pa = a.language.toLowerCase().startsWith(lang) ? 0 : 1, pb = b.language.toLowerCase().startsWith(lang) ? 0 : 1
        return pa - pb || a.name.localeCompare(b.name)
    })
    readonly property var voiceList: voices.map(v => ({ id: v.id, label: v.name + " · " + (engineNames[v.backend] || v.backend) + " · " + v.language }))
    readonly property var voiceItems: [{ id: "", label: qsTr("Automatic (best match for the character)") }].concat(voiceList)
    readonly property var readingItems: [{ id: "", label: qsTr("Same voice as the character") }].concat(voiceList)
    // the voice the character really uses (chosen, or the automatic match)
    readonly property var activeVoice: {
        const chosen = voices.find(v => v.id === cfg.current.voice_id)
        if (chosen) return chosen
        const label = backend.voiceFor(cfg.character)
        return voices.find(v => label.startsWith(v.name + " · ")) || null
    }
    readonly property bool pitchSupported: !activeVoice || activeVoice.pitch !== false

    title: qsTr("Voice")
    subtitle: qsTr("Speech comes from TTS BigLinux (RHVoice, Piper, espeak-ng and Kokoro). Each character can have its own voice.")

    // what the character will really sound like, at a glance
    readonly property bool chosenMissing: cfg.current.voice_id !== "" && !voices.find(v => v.id === cfg.current.voice_id)
    readonly property string readyTone: !cfg.voice.enabled ? "idle" : tts.ok !== true ? "warn" : activeVoice ? "ok" : "warn"
    readonly property string readyText: !cfg.voice.enabled ? qsTr("Muted — replies only in the bubble")
                                      : tts.ok === false ? qsTr("The voice is not ready yet")
                                      : tts.ok !== true ? qsTr("Checking…")
                                      : activeVoice ? qsTr("Ready to speak") : qsTr("No voice in this language yet")

    Section {
        title: qsTr("Voice of %1").arg(page.current.name || "")
        iconName: "mic"
        actions: AppButton { compact: true; variant: "ghost"; iconName: "undo"; text: qsTr("Restore defaults"); onClicked: backend.voiceCenter.resetVoice() }
        RowLayout {
            Layout.fillWidth: true
            spacing: 14
            Image {
                Layout.preferredWidth: 64; Layout.preferredHeight: 72
                source: "../assets/characters/" + cfg.character + ".png"
                sourceSize: Qt.size(128, 144)
                fillMode: Image.PreserveAspectFit
                asynchronous: true
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4
                Text {
                    text: page.activeVoice ? (page.engineNames[page.activeVoice.backend] || page.activeVoice.backend) + " — " + page.activeVoice.name
                                           : qsTr("No voice selected")
                    color: Theme.text; font.pixelSize: 16; font.weight: Font.DemiBold
                }
                StateChip { text: page.readyText; tone: page.readyTone }
                Text {
                    Layout.fillWidth: true
                    visible: page.chosenMissing
                    text: qsTr("The voice chosen for %1 is no longer installed, so the automatic voice is used.").arg(page.current.name || "")
                    color: Theme.warning; font.pixelSize: 12; wrapMode: Text.WordWrap
                }
            }
            AppButton {
                variant: "primary"; iconName: "play"; text: qsTr("Hear a sample")
                enabled: tts.ok === true && page.activeVoice !== null
                onClicked: backend.previewVoice(page.activeVoice ? page.activeVoice.id : "")
            }
        }
        SettingRow {
            label: qsTr("Speak the replies")
            description: qsTr("When off, replies appear only in the speech bubble.")
            AppSwitch { checked: cfg.voice.enabled; onToggled: backend.setConfig("voice.enabled", checked); Accessible.name: qsTr("Speak the replies") }
        }
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
                Accessible.name: qsTr("Voice of %1").arg(page.current.name || "")
            }
            AppButton { iconName: "play"; text: qsTr("Preview"); enabled: tts.ok === true; onClicked: backend.previewVoice(voiceBox.currentValue) }
        }
        Text {
            visible: page.activeVoice !== null && page.activeVoice.backend === "kokoro"
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            color: Theme.textFaint; font.pixelSize: 12
            text: qsTr("Kokoro voices are neural and very natural, but take about as long to create as they last. ChatToon prepares the reply while the viewer's message is being read.")
        }
        GridLayout {
            Layout.fillWidth: true
            columns: 2
            columnSpacing: 28
            uniformCellWidths: true
            LabeledSlider { Layout.alignment: Qt.AlignTop; label: qsTr("Speed"); from: -100; to: 100; value: cfg.current.voice_rate; onMoved: v => backend.setConfig("current.voice_rate", Math.round(v)) }
            LabeledSlider {
                Layout.alignment: Qt.AlignTop
                label: qsTr("Pitch"); from: -100; to: 100; value: cfg.current.voice_pitch
                enabled: page.pitchSupported
                hint: page.pitchSupported ? qsTr("Supported by RHVoice and espeak-ng (Piper changes the expressiveness).")
                                          : qsTr("This voice has no pitch control.")
                onMoved: v => backend.setConfig("current.voice_pitch", Math.round(v))
            }
        }
    }

    Section {
        title: qsTr("Engines")
        iconName: "volume"
        description: tts.ok === true ? qsTr("%n voice(s) available", "", (tts.voices || []).length) + " · " + qsTr("Speech comes from TTS BigLinux.")
                   : tts.ok === false ? (tts.error || "") : qsTr("Checking…")
        actions: AppButton { compact: true; variant: "ghost"; iconName: "refresh"; text: qsTr("Check again"); onClicked: backend.refreshServices() }
        EngineCards { activeBackend: page.activeVoice ? page.activeVoice.backend : "" }
    }

    Section {
        title: qsTr("Message reading")
        iconName: "quote"
        description: qsTr("Before replying, the character can read who wrote and what they wrote — exactly as written, never changed by the AI.")
        SettingRow {
            label: qsTr("Read before replying")
            Segmented {
                model: [{ value: "off", label: qsTr("Off") }, { value: "name", label: qsTr("Name") },
                        { value: "name_message", label: qsTr("Name + message") }]
                current: cfg.reading.mode
                onActivated: v => backend.setConfig("reading.mode", v)
            }
        }
        Rectangle {
            Layout.fillWidth: true
            visible: cfg.reading.mode !== "off"
            implicitHeight: sample.implicitHeight + 20
            radius: Theme.radiusSmall
            color: Theme.hover
            RowLayout {
                id: sample
                anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; margins: 12 }
                spacing: 10
                Icon { name: "quote"; size: 16; color: Theme.accent }
                Text {
                    Layout.fillWidth: true
                    text: { cfg; return "“" + backend.readingSample() + "”" }
                    color: Theme.text; font.pixelSize: 13; font.italic: true; wrapMode: Text.WordWrap
                }
                AppButton { compact: true; iconName: "play"; text: qsTr("Preview"); enabled: tts.ok === true && cfg.voice.enabled; onClicked: backend.previewReading() }
            }
        }
        SettingRow {
            visible: cfg.reading.mode !== "off"
            label: qsTr("Say which platform the message came from")
            description: cfg.reading.platform === "multi" ? qsTr("Only while two or more platforms are live, e.g. “On Twitch, Ana asked…”.")
                       : cfg.reading.platform === "always" ? qsTr("Every message says its platform, even with only one live.")
                       : qsTr("Never — just the name (and the message).")
            Segmented {
                model: [{ value: "never", label: qsTr("Never") }, { value: "multi", label: qsTr("Multistream") },
                        { value: "always", label: qsTr("Always") }]
                current: cfg.reading.platform
                onActivated: v => backend.setConfig("reading.platform", v)
            }
        }
        SettingRow {
            visible: cfg.reading.mode === "name_message"
            label: qsTr("Read at most")
            description: qsTr("Longer messages are cut at a word boundary — never summarised or rewritten.")
            NumberStepper { implicitWidth: 190; value: cfg.reading.max_chars; from: 40; to: 400; step: 20; suffix: qsTr(" chars"); onEdited: v => backend.setConfig("reading.max_chars", v) }
        }
        SettingRow {
            visible: cfg.reading.mode !== "off"
            label: qsTr("Pause before the reply")
            NumberStepper { value: cfg.reading.pause; from: 0; to: 3; step: 0.1; suffix: " s"; onEdited: v => backend.setConfig("reading.pause", v) }
        }
        RowLayout {
            Layout.fillWidth: true
            visible: cfg.reading.mode !== "off"
            spacing: 8
            Text { text: qsTr("Reading voice"); color: Theme.text; font.pixelSize: 13; font.weight: Font.Medium }
            AppCombo {
                Layout.fillWidth: true
                textRole: "label"; valueRole: "id"
                model: page.readingItems
                currentIndex: Math.max(0, indexOfValue(cfg.reading.voice_id))
                onActivated: backend.setConfig("reading.voice_id", currentValue)
                Accessible.name: qsTr("Reading voice")
            }
        }
        Text {
            Layout.fillWidth: true
            visible: cfg.reading.mode !== "off"
            wrapMode: Text.WordWrap
            color: Theme.textFaint; font.pixelSize: 12
            text: qsTr("Links and emoji are skipped and odd user names are made pronounceable. Messages blocked by your filters are never read, and off-limits topics are read as the name only.")
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
