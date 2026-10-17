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

    // what the local classifier decided a viewer's message was (AI › diagnostics)
    function intent(kind) {
        return ({
            math: qsTr("Math"), compare: qsTr("Comparison"), factual: qsTr("Fact"), explain: qsTr("Explanation"),
            tech: qsTr("Tech"), personal: qsTr("About the avatar"), recall: qsTr("Follow-up"), greeting: qsTr("Greeting"),
            farewell: qsTr("Goodbye"), joke: qsTr("Joke"), tease: qsTr("Teasing"), good_news: qsTr("Good news"),
            bad_news: qsTr("A problem"), sad: qsTr("Feelings"), stream: qsTr("About the live"), opinion: qsTr("Opinion"),
            injection: qsTr("Order ignored"), ambiguous: qsTr("Unclear"), chat: qsTr("Chat")
        })[kind] || kind
    }
    // kinds of spontaneous lines: a fact is never confused with the character's fiction
    function lineKind(kind) {
        return ({ fact: qsTr("Fact"), fiction: qsTr("Character fiction"), invite: qsTr("Invitation"), humor: qsTr("Humour"),
                  reflection: qsTr("Thought"), channel: qsTr("Yours") })[kind] || kind
    }
    function lineTone(kind) {
        return kind === "fact" ? Theme.success : kind === "fiction" ? Theme.accent2 : kind === "channel" ? Theme.accent
             : Theme.textMuted
    }
    function category(c) {
        return ({ invite: qsTr("Invitations to talk"), curiosity: qsTr("Curiosities"), context: qsTr("Comments on the topic"),
                  humor: qsTr("Humour"), reflection: qsTr("Funny thoughts"), catchphrase: qsTr("Catchphrases"),
                  cta: qsTr("Calls to action") })[c] || c
    }
    // what a platform said when asked for the live's information
    function meta(code) {
        return ({ found: qsTr("Information found"), offline: qsTr("Not live right now"), unavailable: qsTr("The platform does not provide it"),
                  "auth-required": qsTr("Needs the platform login"), "not-found": qsTr("Not found"), network: qsTr("No connection"),
                  invalid: qsTr("Invalid link"), unsupported: qsTr("Not available"), "rate-limited": qsTr("Too many requests — try later") })[code]
               || qsTr("Could not read")
    }
    function metaTone(code) {
        return code === "found" ? Theme.success : code === "offline" ? Theme.warning
             : code === "unavailable" || code === "unsupported" ? Theme.textMuted : Theme.danger
    }

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
            "pusher-outdated": qsTr("Kick changed its public chat socket, so the unofficial reader stopped working. Use the official webhook mode with your own Kick app (Accounts below), or update ChatToon."),
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

    // sizes and speeds in the interface language ("3,4 GB", "12 MB/s")
    function size(bytes) {
        const n = Number(bytes) || 0
        if (n <= 0) return ""
        if (n >= 1e9) return Number(n / 1e9).toLocaleString(Qt.locale(), "f", 1) + " GB"
        if (n >= 1e6) return Number(n / 1e6).toLocaleString(Qt.locale(), "f", 0) + " MB"
        return Number(n / 1e3).toLocaleString(Qt.locale(), "f", 0) + " KB"
    }
    // memory as the system reports it (binary units: a "16 GB" card shows 16, not 17.2)
    function memory(bytes) {
        const n = Number(bytes) || 0
        return n > 0 ? Number(n / 1073741824).toLocaleString(Qt.locale(), "f", n >= 10 * 1073741824 ? 0 : 1) + " GB" : ""
    }
    function speed(bytesPerSecond) { const s = size(bytesPerSecond); return s ? s + "/s" : "" }

    // what Ollama says while downloading a model
    function pullStatus(status) {
        if (!status) return ""
        if (status.indexOf("manifest") >= 0 && status.indexOf("writing") < 0) return qsTr("Preparing")
        if (status.startsWith("pulling")) return qsTr("Downloading")
        if (status.startsWith("verifying")) return qsTr("Checking the files")
        if (status.startsWith("writing") || status.startsWith("removing")) return qsTr("Finishing")
        if (status === "success") return qsTr("Done")
        return status
    }

    // capabilities reported by Ollama (/api/show)
    function capability(c) {
        return ({ completion: qsTr("Chat"), vision: qsTr("Vision"), tools: qsTr("Tools"), thinking: qsTr("Reasoning"),
                  embedding: qsTr("Embedding"), insert: qsTr("Code fill") })[c] || c
    }

    function preset(p) {
        return ({ friendly: qsTr("Friendly"), comedian: qsTr("Comedian"), troll: qsTr("Teaser"), geek: qsTr("Geek"),
                  chaotic: qsTr("Controlled chaos"), custom: qsTr("Custom") })[p] || p || ""
    }
}
