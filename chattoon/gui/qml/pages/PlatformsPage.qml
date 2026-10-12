import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."

Page {
    id: page
    readonly property var cfg: backend.config
    readonly property var rt: backend.runtimeState
    readonly property var acc: backend.accounts
    readonly property var sources: backend.sources
    readonly property int connected: sources.filter(s => s.status.state === "connected").length
    readonly property bool live: rt.state === "running" || rt.state === "paused"

    title: qsTr("Streaming platforms")
    subtitle: qsTr("Read the chat of every platform you stream to — at the same time, with one avatar.")
    header: AppButton { variant: "primary"; iconName: "plus"; text: qsTr("Add platform"); onClicked: dialog.openNew() }

    SourceDialog { id: dialog; objectName: "sourceDialog" }

    function sourceName(s) {
        if (s.label) return s.label
        if (s.status.channel) return s.status.channel
        return s.target.replace(/^https?:\/\/(www\.)?/, "")
    }

    // ------------------------------------------------------------------ summary + sources
    Section {
        title: page.sources.length ? qsTr("Your sources") : ""
        iconName: "layers"
        description: page.sources.length === 0 ? ""
                   : cfg.mode === "demo" ? qsTr("Demo mode does not read any chat. Switch to Assisted or Automatic on the Dashboard to go live.")
                   : page.live ? qsTr("%1 of %2 connected. Changes apply right away — no restart needed.").arg(page.connected).arg(page.sources.length)
                   : qsTr("They connect together when you press Start.")

        EmptyState {
            visible: page.sources.length === 0
            Layout.alignment: Qt.AlignHCenter
            Layout.topMargin: 8
            iconName: "layers"
            title: qsTr("No platform yet")
            message: qsTr("Add YouTube, Twitch, Kick, TikTok and more. The avatar answers all of them, one at a time.")
        }
        Flow {
            visible: page.sources.length === 0
            Layout.alignment: Qt.AlignHCenter
            Layout.maximumWidth: 640
            Layout.bottomMargin: 8
            spacing: 8
            Repeater {
                model: backend.platforms
                AppButton {
                    required property var modelData
                    compact: true
                    text: modelData.label
                    tip: Status.support(modelData.support)
                    onClicked: dialog.openNew(modelData.id)
                }
            }
        }

        Repeater {
            model: page.sources
            GlassCard {
                id: card
                required property var modelData
                readonly property var st: modelData.status
                readonly property bool problem: ["auth_required", "error", "unsupported"].indexOf(st.state) >= 0
                Layout.fillWidth: true
                implicitHeight: cardCol.implicitHeight + 26
                opacity: modelData.enabled ? 1 : 0.62
                border.color: problem && modelData.enabled ? Theme.tint(Status.tone(st.state), 0.45) : Theme.border
                Accessible.role: Accessible.Grouping
                Accessible.name: (win.platformInfo[modelData.platform] || {}).label + " " + page.sourceName(modelData)

                ColumnLayout {
                    id: cardCol
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 13 }
                    spacing: 10

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 12
                        PlatformBadge { platform: card.modelData.platform; size: 38 }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2
                            RowLayout {
                                spacing: 8
                                Text {
                                    Layout.maximumWidth: card.width * 0.32
                                    text: page.sourceName(card.modelData)
                                    textFormat: Text.PlainText
                                    color: Theme.text; font.pixelSize: 15; font.weight: Font.DemiBold; elide: Text.ElideRight
                                }
                                StatePill { value: card.modelData.held ? "stopped" : card.st.state }
                            }
                            Text {
                                Layout.fillWidth: true
                                text: (win.platformInfo[card.modelData.platform] || {}).label + " · " + card.modelData.target
                                textFormat: Text.PlainText
                                color: Theme.textFaint; font.pixelSize: 11; elide: Text.ElideMiddle
                            }
                        }
                        // live counters
                        Repeater {
                            model: [{ v: card.modelData.received, l: qsTr("messages") }, { v: card.modelData.rate, l: qsTr("per min") },
                                    { v: card.modelData.answered, l: qsTr("answered") }]
                            ColumnLayout {
                                required property var modelData
                                visible: page.live || card.modelData.received > 0
                                spacing: 0
                                Text { Layout.alignment: Qt.AlignHCenter; text: modelData.v; color: Theme.text; font.family: Theme.mono; font.pixelSize: 14; font.weight: Font.Bold }
                                Text { Layout.alignment: Qt.AlignHCenter; text: modelData.l; color: Theme.textFaint; font.pixelSize: 10 }
                            }
                        }
                        AppSwitch {
                            checked: card.modelData.enabled
                            onToggled: backend.updateSource(card.modelData.id, { enabled: checked })
                            Accessible.name: qsTr("Read this chat")
                            ToolTip.visible: hovered
                            ToolTip.text: checked ? qsTr("Enabled") : qsTr("Disabled")
                        }
                    }

                    // reason / guidance when something needs attention
                    RowLayout {
                        Layout.fillWidth: true
                        visible: card.modelData.enabled && (card.st.code !== "" || card.st.state === "waiting") && card.st.state !== "connected"
                                 || card.st.code === "webhook"
                        spacing: 8
                        Icon { name: Status.icon(card.st.state); size: 14; color: Status.tone(card.st.state) }
                        Text {
                            Layout.fillWidth: true
                            text: Status.reason(card.st.code || (card.st.state === "waiting" ? "not-live" : ""), card.st.detail)
                                  + (card.st.retryIn > 0 && card.st.state === "reconnecting" ? " " + qsTr("Next try in %1 s.").arg(Math.round(card.st.retryIn)) : "")
                            textFormat: Text.PlainText; color: Theme.textMuted; font.pixelSize: 12; wrapMode: Text.WordWrap
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 6
                        Text {
                            visible: cfg.chat.selection === "weighted"
                            text: qsTr("Share of attention")
                            color: Theme.textMuted; font.pixelSize: 12
                        }
                        NumberStepper {
                            visible: cfg.chat.selection === "weighted"
                            implicitWidth: 100
                            value: card.modelData.priority; from: 1; to: 5; step: 1; suffix: "×"
                            onEdited: v => backend.updateSource(card.modelData.id, { priority: v })
                        }
                        Item { Layout.fillWidth: true }
                        AppButton {
                            compact: true; variant: "ghost"
                            visible: page.live && card.modelData.enabled && cfg.mode !== "demo"
                            iconName: card.modelData.held || ["stopped", "error", "ended", "auth_required", "idle"].indexOf(card.st.state) >= 0 ? "plug" : "power"
                            text: card.modelData.held || ["stopped", "idle"].indexOf(card.st.state) >= 0 ? qsTr("Connect")
                                : ["error", "ended", "auth_required", "waiting", "reconnecting"].indexOf(card.st.state) >= 0 ? qsTr("Reconnect")
                                : qsTr("Disconnect")
                            onClicked: text === qsTr("Disconnect") ? backend.disconnectSource(card.modelData.id) : backend.connectSource(card.modelData.id)
                        }
                        AppButton {
                            id: testBtn
                            property var result: null
                            property bool busy: false
                            compact: true; variant: "ghost"; iconName: "activity"
                            text: busy ? qsTr("Testing…") : qsTr("Test")
                            enabled: !busy
                            tip: result ? Status.reason(result.code, result.detail) : qsTr("Check the link without reading the chat")
                            onClicked: { busy = true; result = null; backend.testSource(card.modelData.id) }
                            Connections {
                                target: backend
                                function onProbeFinished(id, r) {
                                    if (id !== card.modelData.id) return
                                    testBtn.busy = false
                                    testBtn.result = r
                                    backend.toast(Status.reason(r.code, r.detail), r.ok ? "success" : (r.code === "offline" ? "info" : "error"))
                                }
                            }
                        }
                        AppButton { compact: true; variant: "ghost"; iconName: "edit"; tip: qsTr("Edit"); Accessible.name: qsTr("Edit"); onClicked: dialog.openEdit(card.modelData) }
                        AppButton {
                            compact: true; variant: "ghost"; iconName: "trash"
                            tip: confirm ? qsTr("Click again to remove") : qsTr("Remove")
                            Accessible.name: qsTr("Remove")
                            property bool confirm: false
                            text: confirm ? qsTr("Remove?") : ""
                            onClicked: { if (confirm) backend.removeSource(card.modelData.id); else { confirm = true; confirmTimer.restart() } }
                            Timer { id: confirmTimer; interval: 3000; onTriggered: parent.confirm = false }
                        }
                    }
                }
            }
        }
    }

    // ------------------------------------------------------------------ selection
    Section {
        title: qsTr("Attention between platforms")
        iconName: "users"
        description: qsTr("Busy chats send more than any avatar can answer. Choose how ChatToon picks — and how it shares replies between platforms.")
        AppCombo {
            Layout.preferredWidth: 560
            Layout.maximumWidth: parent.width
            textRole: "t"; valueRole: "v"
            model: [
                { v: "smart", t: qsTr("Smart — questions, mentions and paid messages first, fair to every platform") },
                { v: "balanced", t: qsTr("Balanced — each platform gets its turn") },
                { v: "weighted", t: qsTr("Custom priority — you set each platform's share") },
                { v: "all", t: qsTr("Arrival order — oldest first, within the limits") },
                { v: "mentions", t: qsTr("Mentions — only when the avatar is called") },
                { v: "questions", t: qsTr("Questions first") },
                { v: "moderators", t: qsTr("Moderators first") },
                { v: "members", t: qsTr("Members and subscribers first") },
                { v: "random", t: qsTr("Random") },
                { v: "manual", t: qsTr("Manual — you choose each message in Live chat") },
            ]
            currentIndex: Math.max(0, indexOfValue(cfg.chat.selection))
            onActivated: backend.setConfig("chat.selection", currentValue)
            Accessible.name: qsTr("Selection mode")
        }
        SettingRow {
            visible: ["smart", "questions", "moderators", "members", "mentions"].indexOf(cfg.chat.selection) >= 0
            label: qsTr("Share replies between platforms")
            description: qsTr("A platform that got fewer of the latest replies gains priority, so the busiest chat never takes them all.")
            AppSwitch { checked: cfg.chat.fairness; onToggled: backend.setConfig("chat.fairness", checked); Accessible.name: qsTr("Share replies between platforms") }
        }
        SettingRow {
            label: qsTr("Paid messages jump the queue")
            description: qsTr("Super Chats, Bits, Kicks and gifts. They are never compared by value: each platform pays differently.")
            AppSwitch { checked: cfg.chat.superchat_priority; onToggled: backend.setConfig("chat.superchat_priority", checked); Accessible.name: qsTr("Paid messages jump the queue") }
        }
        SettingRow {
            label: qsTr("Also thank gifts, follows and new subscribers")
            description: qsTr("Events without text. Off by default: on busy lives they arrive in floods.")
            AppSwitch { checked: cfg.chat.include_events; onToggled: backend.setConfig("chat.include_events", checked); Accessible.name: qsTr("Also thank gifts, follows and new subscribers") }
        }
        SettingRow {
            label: qsTr("Wait before answering the same person again")
            description: qsTr("Per platform: “ana” on Twitch and “ana” on YouTube are different people.")
            NumberStepper { value: cfg.chat.user_cooldown; from: 0; to: 900; step: 10; suffix: " s"; onEdited: v => backend.setConfig("chat.user_cooldown", v) }
        }
        SettingRow {
            label: qsTr("Ignore messages older than")
            description: qsTr("The topic moves on: old questions are dropped instead of answered late.")
            NumberStepper { value: cfg.chat.message_ttl; from: 15; to: 900; step: 15; suffix: " s"; onEdited: v => backend.setConfig("chat.message_ttl", v) }
        }
        SettingRow {
            label: qsTr("Queue size")
            description: qsTr("When full, the busiest platform loses its weakest message first.")
            NumberStepper { value: cfg.chat.max_queue; from: 5; to: 200; step: 5; onEdited: v => backend.setConfig("chat.max_queue", v) }
        }
        SettingRow {
            label: qsTr("Skip messages sent before connecting")
            AppSwitch { checked: cfg.chat.skip_backlog; onToggled: backend.setConfig("chat.skip_backlog", checked); Accessible.name: qsTr("Skip messages sent before connecting") }
        }
        SettingRow {
            label: qsTr("Ignore bot commands (messages starting with !)")
            AppSwitch { checked: cfg.chat.ignore_commands; onToggled: backend.setConfig("chat.ignore_commands", checked); Accessible.name: qsTr("Ignore bot commands (messages starting with !)") }
        }
        SettingRow {
            label: qsTr("Read the viewer's name and message before replying")
            description: cfg.reading.mode === "off" ? qsTr("Off — the avatar answers directly.")
                       : cfg.reading.mode === "name" ? qsTr("On — reads who wrote, then answers.")
                       : qsTr("On — reads who wrote and the message, then answers.")
            AppButton { compact: true; iconName: "quote"; text: qsTr("Configure"); onClicked: win.go("voice") }
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 6
            Text { text: qsTr("Favourite viewers — answered first (comma separated; “twitch:ana” for one platform only)"); color: Theme.text; font.pixelSize: 13; Layout.fillWidth: true; wrapMode: Text.WordWrap }
            AppTextField { Layout.fillWidth: true; iconName: "star"; text: cfg.chat.priority_viewers; onEditingFinished: backend.setConfig("chat.priority_viewers", text); Accessible.name: qsTr("Favourite viewers") }
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 6
            Text { text: qsTr("Blocked words (comma separated) — messages containing them are ignored"); color: Theme.text; font.pixelSize: 13 }
            AppTextField { Layout.fillWidth: true; text: cfg.chat.blocked_words; onEditingFinished: backend.setConfig("chat.blocked_words", text); Accessible.name: qsTr("Blocked words") }
        }
    }

    // ------------------------------------------------------------------ accounts
    Section {
        id: accounts
        title: qsTr("Accounts")
        iconName: "key"
        description: qsTr("Only where a platform requires it. ChatToon never asks for passwords; logins stay on this computer and are never exported in profiles.")

        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            Icon { name: acc.encrypted ? "lock" : "alert"; size: 16; color: acc.encrypted ? Theme.success : Theme.warning }
            Text {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                font.pixelSize: 12
                color: Theme.textMuted
                text: acc.encrypted ? qsTr("Stored in your system keyring (KWallet, GNOME Keyring or compatible).")
                    : acc.store === "file" ? qsTr("No system keyring found: logins are kept in a private file only your user can read. Enable KWallet or GNOME Keyring for encrypted storage.")
                    : qsTr("Checking the keyring…")
            }
        }

        // Twitch
        AccountBlock {
            platform: "twitch"
            status: acc.twitch && acc.twitch.connected ? qsTr("Connected as %1").arg(acc.twitch.login) : qsTr("Not connected — guest mode is used")
            ok: !!(acc.twitch && acc.twitch.connected)
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 8
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    AppTextField {
                        Layout.fillWidth: true
                        implicitHeight: 38
                        placeholderText: qsTr("Client ID of your Twitch app (public, not a secret)")
                        text: cfg.streams.apps.twitch_client_id
                        onEditingFinished: { backend.setConfig("streams.apps.twitch_client_id", text.trim()); backend.refreshAccounts() }
                        Accessible.name: qsTr("Twitch Client ID")
                    }
                    AppButton {
                        visible: !(acc.twitch && acc.twitch.connected)
                        variant: "primary"; iconName: "plug"; text: qsTr("Connect account")
                        enabled: !!(acc.twitch && acc.twitch.clientId) && backend.login.state !== "waiting"
                        onClicked: backend.loginTwitch()
                    }
                    AppButton {
                        visible: !!(acc.twitch && acc.twitch.connected)
                        iconName: "power"; text: qsTr("Disconnect")
                        onClicked: backend.logoutTwitch()
                    }
                }
                // device code
                Rectangle {
                    Layout.fillWidth: true
                    visible: backend.login.platform === "twitch" && backend.login.state === "waiting"
                    implicitHeight: codeCol.implicitHeight + 24
                    radius: Theme.radiusSmall
                    color: Theme.tint(Theme.accent, 0.1)
                    border.color: Theme.tint(Theme.accent, 0.4)
                    ColumnLayout {
                        id: codeCol
                        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 12 }
                        spacing: 8
                        Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Theme.text; font.pixelSize: 13
                               text: qsTr("Approve ChatToon on Twitch. If the page asks for a code, type:") }
                        RowLayout {
                            spacing: 10
                            Text { text: backend.login.code || ""; color: Theme.accent; font.family: Theme.mono; font.pixelSize: 26; font.weight: Font.Bold; font.letterSpacing: 3 }
                            AppButton { compact: true; iconName: "copy"; tip: qsTr("Copy"); Accessible.name: qsTr("Copy"); onClicked: backend.copyText(backend.login.code) }
                            AppButton { compact: true; iconName: "external"; text: qsTr("Open twitch.tv/activate"); onClicked: backend.openUrl(backend.login.url) }
                            BusyDots {}
                            Item { Layout.fillWidth: true }
                            AppButton { compact: true; variant: "ghost"; text: qsTr("Cancel"); onClicked: backend.cancelLogin() }
                        }
                    }
                }
                Text {
                    Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Theme.textFaint; font.pixelSize: 11
                    text: qsTr("Create a free app at dev.twitch.tv/console with Client Type “Public” (any OAuth redirect, e.g. http://localhost). Only the “read chat” permission is requested; the token is validated every hour and renewed automatically.")
                }
            }
        }

        // Kick
        AccountBlock {
            platform: "kick"
            status: acc.kick && acc.kick.secret && cfg.streams.apps.kick_client_id ? qsTr("Official webhooks ready") : qsTr("Not needed for the public chat")
            ok: !!(acc.kick && acc.kick.secret && cfg.streams.apps.kick_client_id)
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 8
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    AppTextField {
                        Layout.fillWidth: true; implicitHeight: 38
                        placeholderText: qsTr("Client ID of your Kick app")
                        text: cfg.streams.apps.kick_client_id
                        onEditingFinished: backend.setConfig("streams.apps.kick_client_id", text.trim())
                        Accessible.name: qsTr("Kick Client ID")
                    }
                    SecretField { key: "kick/app"; field: "client_secret"; stored: !!(acc.kick && acc.kick.secret); placeholder: qsTr("Client secret") }
                }
                SettingRow {
                    label: qsTr("Local webhook port")
                    description: qsTr("ChatToon listens on 127.0.0.1 only. Forward your public HTTPS address (set as Webhook URL in the Kick app) to http://127.0.0.1:%1/kick/webhook — ChatToon never opens ports to the internet.").arg(cfg.streams.apps.kick_webhook_port)
                    NumberStepper { implicitWidth: 130; value: cfg.streams.apps.kick_webhook_port; from: 1024; to: 65535; step: 1; onEdited: v => backend.setConfig("streams.apps.kick_webhook_port", v) }
                }
            }
        }

        // TikTok
        AccountBlock {
            platform: "tiktok"
            status: acc.tiktok && acc.tiktok.installed ? qsTr("TikTokLive installed") : qsTr("Optional component not installed")
            ok: !!(acc.tiktok && acc.tiktok.installed)
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 8
                RowLayout {
                    Layout.fillWidth: true
                    visible: !(acc.tiktok && acc.tiktok.installed)
                    spacing: 8
                    Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Theme.text; font.pixelSize: 12
                           text: qsTr("Install it in a private folder (nothing changes in your system), then restart ChatToon:") }
                    AppButton { compact: true; iconName: "copy"; text: qsTr("Copy command"); onClicked: backend.copyText("chattoon extras install tiktok") }
                }
                Text {
                    visible: !(acc.tiktok && acc.tiktok.installed)
                    text: "chattoon extras install tiktok"
                    color: Theme.accent; font.family: Theme.mono; font.pixelSize: 12
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    Text { text: qsTr("Euler Stream API key (optional, raises the daily limit)"); color: Theme.textMuted; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                    SecretField { key: "tiktok/sign"; field: "api_key"; stored: !!(acc.tiktok && acc.tiktok.key); placeholder: qsTr("API key") }
                }
                Text {
                    Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Theme.textFaint; font.pixelSize: 11
                    text: qsTr("TikTok has no official API for LIVE comments. The unofficial TikTokLive library asks Euler Stream (a third-party service) to sign each connection: it receives the live's room id and your IP address, never your login. It may stop working without notice.")
                }
            }
        }

        // Meta
        AccountBlock {
            platform: "facebook"
            title: "Facebook · Instagram"
            status: acc.meta && acc.meta.token ? qsTr("Token saved") : qsTr("No token")
            ok: !!(acc.meta && acc.meta.token)
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 8
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    Text { text: qsTr("Page or user access token"); color: Theme.textMuted; font.pixelSize: 12; Layout.fillWidth: true }
                    SecretField { key: "meta/token"; field: "access_token"; stored: !!(acc.meta && acc.meta.token); placeholder: qsTr("Access token") }
                }
                Text {
                    Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Theme.textFaint; font.pixelSize: 11
                    text: qsTr("Create your own app at developers.facebook.com (it can stay in Development mode), open the Graph API Explorer, choose your Page and the permissions pages_read_engagement, pages_read_user_content, pages_show_list (plus instagram_basic and instagram_manage_comments for Instagram), generate the token and extend it in the Access Token Debugger. Only Pages and professional Instagram accounts can be read.")
                }
            }
        }

        // X
        AccountBlock {
            platform: "x"
            status: acc.x && acc.x.token ? qsTr("Bearer token saved") : qsTr("No token")
            ok: !!(acc.x && acc.x.token)
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 8
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    Text { text: qsTr("Bearer token of your X developer app"); color: Theme.textMuted; font.pixelSize: 12; Layout.fillWidth: true }
                    SecretField { key: "x/bearer"; field: "bearer_token"; stored: !!(acc.x && acc.x.token); placeholder: qsTr("Bearer token") }
                }
                Text {
                    Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Theme.textFaint; font.pixelSize: 11
                    text: qsTr("X has no API for the chat of live videos or Spaces. ChatToon can read replies to the post that announces your live, using the paid X API (charged per post read, about every 20 seconds).")
                }
            }
        }
    }

    // ------------------------------------------------------------------ honest support sheet
    Section {
        title: qsTr("What each platform allows")
        iconName: "info"
        description: qsTr("Tested with the official documentation in October 2026. Platforms change their rules; ChatToon tells you when a source stops working.")
        Repeater {
            model: backend.platforms
            RowLayout {
                required property var modelData
                Layout.fillWidth: true
                spacing: 12
                PlatformBadge { platform: modelData.id; size: 26; Layout.alignment: Qt.AlignTop }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2
                    RowLayout {
                        spacing: 8
                        Text { text: modelData.label; color: Theme.text; font.pixelSize: 13; font.weight: Font.DemiBold }
                        Chip { text: Status.support(modelData.support); tone: Status.supportTone(modelData.support) }
                    }
                    Text { Layout.fillWidth: true; text: modelData.note; color: Theme.textMuted; font.pixelSize: 12; wrapMode: Text.WordWrap }
                }
            }
        }
    }

    component AccountBlock: ColumnLayout {
        id: block
        property string platform
        property string title: (win.platformInfo[platform] || {}).label || ""
        property string status
        property bool ok: false
        default property alias body: slot.data
        Layout.fillWidth: true
        spacing: 8
        Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }
        RowLayout {
            spacing: 10
            PlatformBadge { platform: block.platform; size: 26 }
            Text { text: block.title; color: Theme.text; font.pixelSize: 14; font.weight: Font.DemiBold }
            Chip { text: block.status; tone: block.ok ? Theme.success : Theme.textMuted; iconName: block.ok ? "check" : "" }
        }
        ColumnLayout { id: slot; Layout.fillWidth: true; spacing: 8 }
    }

    component SecretField: RowLayout {
        id: secret
        property string key
        property string field
        property bool stored: false
        property string placeholder
        spacing: 6
        AppTextField {
            id: secretInput
            Layout.preferredWidth: 220
            implicitHeight: 38
            echoMode: TextInput.Password
            placeholderText: secret.stored ? qsTr("Saved — type to replace") : secret.placeholder
            Accessible.name: secret.placeholder
            onAccepted: saveBtn.clicked()
        }
        AppButton {
            id: saveBtn
            compact: true; iconName: "check"; tip: qsTr("Save in the keyring"); Accessible.name: qsTr("Save in the keyring")
            enabled: secretInput.text.trim() !== ""
            onClicked: { backend.setSecret(secret.key, secret.field, secretInput.text); secretInput.text = "" }
        }
        AppButton {
            compact: true; variant: "ghost"; iconName: "trash"; tip: qsTr("Delete from this computer"); Accessible.name: qsTr("Delete from this computer")
            visible: secret.stored
            onClicked: backend.clearSecret(secret.key)
        }
    }
}
