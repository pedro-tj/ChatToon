pragma Singleton
import QtQuick

// What may appear on screen during a live (docs/SECURITY.md).
// Always masked: the token inside overlay addresses, the public IP, secrets.
// Live privacy mode (default on) also masks local addresses, domains and account names.
// "Reveal" shows one value for 15 seconds, after a warning; then everything is hidden again.
QtObject {
    id: root
    property bool live: true
    property var revealed: ({})
    readonly property string mask: "••••••"

    property Timer timer: Timer { interval: 15000; onTriggered: root.revealed = ({}) }

    function isRevealed(key) { return key !== "" && root.revealed[key] === true }
    function reveal(key) {
        const next = Object.assign({}, root.revealed)
        next[key] = true
        root.revealed = next
        root.timer.restart()
    }
    function hideAll() { root.revealed = ({}) }

    function isLoopback(host) { return host === "127.0.0.1" || host === "localhost" || host === "[::1]" }

    // overlay address: the token always, the host too in live mode (unless it is this computer)
    function url(value, key) {
        if (!value || isRevealed(key)) return value || ""
        let out = value.replace(/\/o\/[A-Za-z0-9_-]{6,}(\/?)/, "/o/" + mask + "$1")
        if (live) out = out.replace(/^(\w+:\/\/)([^/:]+)/, (m, scheme, host) => isLoopback(host) ? m : scheme + hostMask(host))
        return out
    }
    function hostMask(host) {
        if (/^\d{1,3}(\.\d{1,3}){3}$/.test(host)) return "•••.•••.•••.•••"
        const parts = host.split(".")
        return parts.length > 2 ? "•••." + parts.slice(-2).join(".") : "•••." + parts[parts.length - 1]
    }
    // the public IP: never shown unless revealed
    function publicIp(value, key) { return !value ? "" : isRevealed(key) ? value : "***.***.***.***" }
    // a local address or domain: hidden only in live mode
    function local(value, key) { return !value || !live || isRevealed(key) ? (value || "") : hostMask(value) }
    // any text that may carry an address (errors, diagnostics)
    function text(value) {
        if (!value) return ""
        let out = value.replace(/\/o\/[A-Za-z0-9_-]{6,}/g, "/o/" + mask)
        if (live) out = out.replace(/\b(?!127\.)(\d{1,3}(\.\d{1,3}){3})\b/g, "•••.•••.•••.•••")
        return out
    }
    // account names, logins: hidden only in live mode
    function name(value, key) { return !value || !live || isRevealed(key) ? (value || "") : mask }
}
