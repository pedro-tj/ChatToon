import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

// Add or edit one streaming source: pick the platform (or just paste a link — it is
// recognised), test the connection, save. Works with keyboard only (Tab, Enter, Esc).
Popup {
    id: dialog
    property string editingId: ""          // "" = adding
    property string platform: "youtube"
    property var check: ({ ok: false })     // backend.detectSource() result for the typed text
    property var probe: null                // last "Test connection" result
    property bool testing: false
    property var options: ({})
    readonly property var info: win.platformInfo[platform] || {}
    readonly property bool canSave: check.ok === true && target.text.trim() !== ""

    modal: true
    focus: true
    closePolicy: Popup.CloseOnEscape
    anchors.centerIn: Overlay.overlay
    width: Math.min(640, (parent ? parent.width : 700) - 60)
    padding: 26
    Overlay.modal: Rectangle { color: Qt.rgba(0, 0, 0, 0.5) }
    background: Rectangle { radius: Theme.radius + 4; color: Theme.surfaceStrong; border.color: Theme.border }

    function openNew(platformId) {
        editingId = ""
        platform = platformId || "youtube"
        options = {}
        target.text = ""
        label.text = ""
        enabledBox.checked = true
        probe = null
        recheck()
        open()
        target.forceActiveFocus()
    }
    function openEdit(source) {
        editingId = source.id
        platform = source.platform
        options = Object.assign({}, source.options || {})
        target.text = source.target
        label.text = source.label || ""
        enabledBox.checked = source.enabled
        probe = null
        recheck()
        open()
        target.forceActiveFocus()
    }
    function recheck() {
        check = target.text.trim() === "" ? { ok: false } : backend.detectSource(target.text, platform, editingId)
        // a pasted link of another platform switches the selector by itself
        if (check.code === "unknown" && target.text.indexOf("/") >= 0) {
            const any = backend.detectSource(target.text, "", editingId)
            if (any.platform) { platform = any.platform; check = any }
        }
    }
    function setOption(key, value) {
        const copy = Object.assign({}, options)
        if (value === "" || value === undefined) delete copy[key]
        else copy[key] = value
        options = copy
        probe = null
    }
    function save() {
        if (!canSave) return
        if (editingId) {
            backend.updateSource(editingId, { platform: platform, target: target.text, label: label.text,
                                              enabled: enabledBox.checked, options: options })
        } else {
            backend.addSource(platform, target.text, label.text, enabledBox.checked, options)
        }
        close()
    }

    Connections {
        target: backend
        function onProbeFinished(id, result) {
            if (id !== "draft") return
            dialog.testing = false
            dialog.probe = result
        }
    }

    contentItem: ColumnLayout {
        spacing: 16

        RowLayout {
            spacing: 12
            PlatformBadge { platform: dialog.platform; size: 40 }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 1
                Text {
                    text: dialog.editingId ? qsTr("Edit source") : qsTr("Add a streaming platform")
                    color: Theme.text; font.pixelSize: 19; font.weight: Font.Bold
                    Accessible.role: Accessible.Heading
                }
                Text {
                    Layout.fillWidth: true
                    text: qsTr("Paste the link of your live or channel — the platform is recognised automatically.")
                    color: Theme.textMuted; font.pixelSize: 12; wrapMode: Text.WordWrap
                }
            }
        }

        // platform picker
        Flow {
            Layout.fillWidth: true
            spacing: 6
            Repeater {
                model: backend.platforms
                Rectangle {
                    id: tile
                    required property var modelData
                    readonly property bool selected: dialog.platform === modelData.id
                    width: tileRow.implicitWidth + 20
                    height: 36
                    radius: Theme.radiusSmall
                    color: selected ? Theme.tint(Theme.accent, Theme.dark ? 0.2 : 0.12) : tileHover.hovered ? Theme.hover : Theme.field
                    border.width: selected || tile.activeFocus ? 2 : 1
                    border.color: selected || tile.activeFocus ? Theme.accent : Theme.border
                    activeFocusOnTab: true
                    Accessible.role: Accessible.RadioButton
                    Accessible.name: modelData.label
                    Accessible.checked: selected
                    Keys.onSpacePressed: pick()
                    Keys.onReturnPressed: pick()
                    function pick() { dialog.platform = modelData.id; dialog.options = {}; dialog.probe = null; dialog.recheck() }
                    RowLayout {
                        id: tileRow
                        anchors.centerIn: parent
                        spacing: 7
                        PlatformBadge { platform: tile.modelData.id; size: 20 }
                        Text { text: tile.modelData.label; color: Theme.text; font.pixelSize: 13; font.weight: tile.selected ? Font.DemiBold : Font.Normal }
                    }
                    HoverHandler { id: tileHover; cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: tile.pick() }
                }
            }
        }

        // support level of the chosen platform, said honestly
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: noteRow.implicitHeight + 18
            radius: Theme.radiusSmall
            color: Theme.tint(Status.supportTone(dialog.info.support), 0.1)
            border.width: 1
            border.color: Theme.tint(Status.supportTone(dialog.info.support), 0.3)
            RowLayout {
                id: noteRow
                anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; margins: 10 }
                spacing: 10
                Chip { text: Status.support(dialog.info.support); tone: Status.supportTone(dialog.info.support) }
                Text {
                    Layout.fillWidth: true
                    text: dialog.info.note || ""
                    color: Theme.text; font.pixelSize: 12; wrapMode: Text.WordWrap
                }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 6
            Text { text: qsTr("Link, channel or @user"); color: Theme.text; font.pixelSize: 13; font.weight: Font.Medium }
            AppTextField {
                id: target
                Layout.fillWidth: true
                iconName: "link"
                placeholderText: dialog.info.accepts || ""
                onTextChanged: { dialog.probe = null; dialog.recheck() }
                onAccepted: dialog.save()
                Accessible.name: qsTr("Link, channel or @user")
            }
            RowLayout {
                visible: target.text.trim() !== ""
                spacing: 6
                Icon {
                    name: dialog.check.ok ? "check" : "alert"
                    size: 14
                    color: dialog.check.ok ? Theme.success : Theme.danger
                }
                Text {
                    Layout.fillWidth: true
                    text: dialog.check.ok ? qsTr("Recognised: %1 · %2").arg((win.platformInfo[dialog.check.platform] || {}).label || "").arg(dialog.check.display)
                                          : (dialog.check.error || "")
                    color: dialog.check.ok ? Theme.success : Theme.danger
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 12
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 6
                Text { text: qsTr("Name shown in ChatToon (optional)"); color: Theme.text; font.pixelSize: 13; font.weight: Font.Medium }
                AppTextField { id: label; Layout.fillWidth: true; placeholderText: qsTr("e.g. Main channel"); Accessible.name: qsTr("Name shown in ChatToon (optional)") }
            }
        }

        // platform-specific choices
        SettingRow {
            visible: dialog.platform === "twitch"
            label: qsTr("How to read")
            description: (dialog.options.mode || "auto") === "anonymous" ? qsTr("Guest mode: no login, read-only. Twitch keeps it working, but does not document it.")
                       : (dialog.options.mode || "auto") === "account" ? qsTr("Official EventSub with your Twitch account (connect it in Accounts).")
                       : qsTr("Uses your Twitch account when connected; otherwise guest mode.")
            Segmented {
                model: [{ value: "auto", label: qsTr("Automatic") }, { value: "account", label: qsTr("Account") },
                        { value: "anonymous", label: qsTr("Guest") }]
                current: dialog.options.mode || "auto"
                onActivated: v => dialog.setOption("mode", v === "auto" ? "" : v)
            }
        }
        SettingRow {
            visible: dialog.platform === "kick"
            label: qsTr("How to read")
            description: (dialog.options.mode || "auto") === "webhook" ? qsTr("Official webhooks: your Kick app plus a public HTTPS address forwarding to this computer.")
                       : qsTr("Public chat socket used by kick.com. Unofficial: may change without notice.")
            Segmented {
                model: [{ value: "auto", label: qsTr("Automatic") }, { value: "pusher", label: qsTr("Public chat") },
                        { value: "webhook", label: qsTr("Official webhook") }]
                current: dialog.options.mode || "auto"
                onActivated: v => dialog.setOption("mode", v === "auto" ? "" : v)
            }
        }
        RowLayout {
            Layout.fillWidth: true
            visible: dialog.platform === "kick" && (dialog.options.mode || "auto") !== "webhook"
            spacing: 8
            Text { text: qsTr("Chatroom number (only if the automatic lookup is blocked)"); color: Theme.textMuted; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.WordWrap }
            AppTextField {
                Layout.preferredWidth: 140
                implicitHeight: 36
                text: dialog.options.chatroom_id || ""
                validator: RegularExpressionValidator { regularExpression: /\d{0,12}/ }
                onEditingFinished: dialog.setOption("chatroom_id", text)
                Accessible.name: qsTr("Chatroom number")
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 10
            AppCheck { id: enabledBox; text: qsTr("Read this chat when the live starts"); checked: true }
            Item { Layout.fillWidth: true }
        }

        // test connection
        RowLayout {
            Layout.fillWidth: true
            spacing: 10
            AppButton {
                iconName: "activity"
                text: qsTr("Test connection")
                enabled: dialog.canSave && !dialog.testing
                onClicked: {
                    dialog.testing = true
                    dialog.probe = null
                    backend.testSource("draft", dialog.platform, dialog.check.target, dialog.options)
                }
            }
            BusyDots { visible: dialog.testing }
            Icon {
                visible: !!dialog.probe
                name: dialog.probe && dialog.probe.ok ? "check" : dialog.probe && dialog.probe.code === "offline" ? "hourglass" : "alert"
                size: 16
                color: dialog.probe && dialog.probe.ok ? Theme.success : dialog.probe && dialog.probe.code === "offline" ? Theme.warning : Theme.danger
            }
            Text {
                Layout.fillWidth: true
                visible: !!dialog.probe
                text: dialog.probe ? Status.reason(dialog.probe.code, dialog.probe.detail) : ""
                color: Theme.text
                font.pixelSize: 12
                wrapMode: Text.WordWrap
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: 4
            spacing: 8
            Item { Layout.fillWidth: true }
            AppButton { variant: "ghost"; text: qsTr("Cancel"); onClicked: dialog.close() }
            AppButton {
                variant: "primary"
                iconName: dialog.editingId ? "check" : "plus"
                text: dialog.editingId ? qsTr("Save") : qsTr("Add")
                enabled: dialog.canSave
                onClicked: dialog.save()
            }
        }
    }
}
