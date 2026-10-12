pragma Singleton
import QtQuick

// Words, icons and tones for source states and error codes, shared by every page.
// A state is never told by colour alone: each one has its own icon and label.
QtObject {
    function label(state) {
        return ({
            idle: qsTr("Ready — connects on Start"), connecting: qsTr("Connecting…"), connected: qsTr("Connected"),
            reconnecting: qsTr("Reconnecting…"), waiting: qsTr("Waiting for the live"), ended: qsTr("Live ended"),
            auth_required: qsTr("Login required"), error: qsTr("Error"), unsupported: qsTr("Not available"),
            stopped: qsTr("Disconnected"), disabled: qsTr("Disabled")
        })[state] || state
    }
    function icon(state) {
        return ({
            idle: "power", connecting: "refresh", connected: "check", reconnecting: "refresh", waiting: "hourglass",
            ended: "stop", auth_required: "lock", error: "alert", unsupported: "minus", stopped: "wifiOff", disabled: "minus"
        })[state] || "info"
    }
    function tone(state) {
        if (state === "connected") return Theme.success
        if (state === "connecting" || state === "reconnecting") return Theme.accent
        if (state === "waiting" || state === "auth_required") return Theme.warning
        if (state === "error") return Theme.danger
        return Theme.textMuted
    }
    function busy(state) { return state === "connecting" || state === "reconnecting" }

    function support(level) {
        return ({ functional: qsTr("Supported"), limited: qsTr("Limited"), experimental: qsTr("Experimental"),
                  unavailable: qsTr("Unavailable") })[level] || level
    }
    function supportTone(level) {
        return level === "functional" ? Theme.success : level === "unavailable" ? Theme.danger
             : level === "experimental" ? Theme.accent2 : Theme.warning
    }

    // stable error codes from the connectors, in the interface language
    function reason(code, detail) {
        const text = ({
            "network": qsTr("Network problem — trying again."),
            "rate-limited": qsTr("The platform asked to slow down — waiting before trying again."),
            "not-live": qsTr("Not live right now. ChatToon keeps checking and connects when the live starts."),
            "offline": qsTr("Not live right now."),
            "ended": qsTr("This live has ended."),
            "auth-required": qsTr("Connect the account for this platform in Accounts below."),
            "auth-failed": qsTr("The login failed."),
            "no-client-id": qsTr("Set the Twitch Client ID in Accounts below."),
            "no-app": qsTr("Official Kick webhooks need your Kick app (Client ID and secret) in Accounts below."),
            "missing-dependency": qsTr("An optional component is not installed — see Accounts below."),
            "unsupported": qsTr("Not available on this computer or platform."),
            "no-api": qsTr("This platform has no API to read this kind of live."),
            "plan-required": qsTr("Your API plan does not allow reading these posts."),
            "not-found": qsTr("Channel or live not found."),
            "invalid": qsTr("This link or name is not valid for this platform."),
            "chat-unavailable": qsTr("This video has no live chat (not live, ended or chat disabled)."),
            "blocked": qsTr("The platform blocked the automatic lookup. Type the chatroom number in the source options."),
            "age-restricted": qsTr("Age-restricted live: it cannot be read without a login."),
            "subscribe-failed": qsTr("The platform refused to send this chat."),
            "crashed": qsTr("Unexpected problem in this connector — the other platforms keep working."),
            "timeout": qsTr("No answer from the platform in time."),
            "sign-server": qsTr("The TikTok signing service (Euler Stream) failed — trying again."),
            "pusher-refused": qsTr("Kick's chat server refused the connection."),
            "no-chatroom": qsTr("This Kick channel has no chatroom."),
            "duplicate": qsTr("Another source already reads this chat."),
            "graph-error": qsTr("Meta refused the request."),
            "bad-request": qsTr("The platform refused the request."),
            "port-in-use": qsTr("The local webhook port is in use. Choose another port in Accounts."),
            "webhook": qsTr("Receiving official Kick webhooks — keep your public HTTPS address forwarding to ChatToon."),
            "live": qsTr("Live now — the chat can be read."),
            "ready": qsTr("Ready — the chat can be read.")
        })[code]
        return text ? text + (detail && code !== "network" && code !== "live" && code !== "ready" ? " (" + detail + ")" : "")
                    : (detail || code || "")
    }
}
