import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

// Overlay for an OBS somewhere else on the internet, step by step
// (docs/34-remote-access-privacy.md). The public IP is looked up only with consent and is
// never shown unmasked by default; the test proves the real path (DNS → port → HTTPS →
// proxy → ChatToon → WebSocket) instead of trusting the filled-in form.
ColumnLayout {
    id: root
    readonly property var c: backend.connectivity
    readonly property var o: backend.config.overlay
    readonly property var rt: backend.runtimeState
    readonly property var pip: c.publicIp
    readonly property var net: c.network
    readonly property var remote: c.remote
    readonly property var proxy: c.proxy
    readonly property string localIp: ((net.addresses || []).find(a => a.lan) || {}).ip || ""
    property int step: 0
    property string route: "router"  // router | tunnel

    spacing: 12
    Layout.fillWidth: true
    Component.onCompleted: c.loadProxy()

    function stepTitle(i) {
        return [qsTr("Check your connection"), qsTr("Your domain"), qsTr("Reach this computer safely"), qsTr("HTTPS"), qsTr("Test the connection")][i]
    }
    function codeText(code, detail) {
        return ({
            "invalid-format": qsTr("Type an https address with a domain name, like https://mychannel.example.org:8443."),
            "dns-failed": qsTr("This name does not exist yet (DNS). Check the domain and its A record at your provider."),
            "dns-private": qsTr("The name points to an address inside a home network: nobody outside can reach it. Point it to your public IP."),
            "dns-mismatch": qsTr("The name points to another public IP. Did your IP change? Update the record or use dynamic DNS."),
            "cgnat": qsTr("The name points to a carrier-grade NAT address (CGNAT)."),
            "timeout": qsTr("The port did not answer. Check the port forwarding on the router and the firewall. Under CGNAT, use a tunnel."),
            "refused": qsTr("A computer answered, but nothing listens on that port. Is Caddy (or nginx) running?"),
            "unreachable": qsTr("The address cannot be reached from this network."),
            "cert-invalid": qsTr("Invalid certificate: HTTPS was not issued yet, or it belongs to another name (%1).").arg(detail || ""),
            "tls-failed": qsTr("That port does not speak HTTPS. Check the proxy configuration."),
            "host-not-allowed": qsTr("ChatToon refused the name: the address in step 2 must be exactly the proxy's (name and port)."),
            "token-invalid": qsTr("The secret address was not accepted (an old address, or another program on that port)."),
            "proxy-error": qsTr("The proxy answered but cannot reach ChatToon. Check that it forwards to 127.0.0.1:%1.").arg(root.rt.port || root.o.port),
            "http-status": qsTr("Unexpected answer from the server (HTTP %1).").arg(detail || ""),
            "http-failed": qsTr("The HTTPS request failed."),
            "ws-failed": qsTr("HTTPS works but the live connection (WebSocket) did not pass the proxy. Enable WebSocket/Upgrade forwarding.")
        })[code] || code
    }
    // the site line of the Caddy file names the domain: hidden in live privacy mode
    function maskedSnippet(text) {
        if (!Privacy.live || Privacy.isRevealed("domain")) return text
        return text.replace(/^(?!#)([^\s{]+)/m, m => { const p = m.split(":"); return Privacy.local(p[0], "domain") + (p.length > 1 ? ":" + p[1] : "") })
    }
    function checkName(id) {
        return ({ format: qsTr("Address"), dns: qsTr("Name (DNS)"), port: qsTr("Port"), tls: qsTr("Certificate (HTTPS)"),
                  http: qsTr("Proxy and ChatToon"), websocket: qsTr("Live connection (WebSocket)") })[id] || id
    }

    // step tabs
    Flow {
        Layout.fillWidth: true
        spacing: 6
        Repeater {
            model: 5
            Rectangle {
                required property int index
                readonly property bool current: root.step === index
                width: tabRow.implicitWidth + 20; height: 32; radius: 16
                color: current ? Theme.tint(Theme.accent, 0.18) : Theme.field
                border.color: current ? Theme.accent : Theme.border
                activeFocusOnTab: true
                Accessible.role: Accessible.PageTab
                Accessible.name: (index + 1) + ". " + root.stepTitle(index)
                Keys.onSpacePressed: root.step = index
                RowLayout {
                    id: tabRow
                    anchors.centerIn: parent
                    spacing: 6
                    Text { text: index + 1; color: Theme.accent; font.pixelSize: 12; font.weight: Font.Bold }
                    Text { text: root.stepTitle(index); color: parent.parent.current ? Theme.accent : Theme.textMuted; font.pixelSize: 12 }
                }
                HoverHandler { cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: root.step = index }
            }
        }
    }

    StackLayout {
        Layout.fillWidth: true
        currentIndex: root.step

        // 1 — connection
        ColumnLayout {
            spacing: 10
            Text {
                Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Theme.textMuted; font.pixelSize: 13
                text: qsTr("Your computer has a private IP inside your home (given by the router) and your connection has one public IP on the internet. An OBS elsewhere reaches the public IP, and the router passes it to this computer — unless your provider uses CGNAT (one public IP shared by many customers), when only a tunnel works.")
            }
            RowLayout {
                spacing: 8
                Text { text: qsTr("Private IP of this computer:"); color: Theme.text; font.pixelSize: 13 }
                Text { text: Privacy.local(root.localIp, "lan") || "—"; color: Theme.text; font.family: Theme.mono; font.pixelSize: 13 }
            }
            RowLayout {
                spacing: 8
                Text { text: qsTr("Public IP:"); color: Theme.text; font.pixelSize: 13 }
                Text {
                    visible: root.pip.known === true
                    text: Privacy.publicIp(root.pip.value, "public-ip"); color: Theme.text; font.family: Theme.mono; font.pixelSize: 13
                    Accessible.name: qsTr("Public IP, hidden for privacy")
                }
                AppButton {
                    visible: root.pip.known === true
                    compact: true; variant: "ghost"; iconName: Privacy.isRevealed("public-ip") ? "eyeOff" : "eye"
                    tip: qsTr("Show for 15 seconds"); Accessible.name: tip
                    onClicked: Privacy.isRevealed("public-ip") ? Privacy.hideAll() : win.askReveal("public-ip")
                }
                AppButton {
                    visible: root.pip.known !== true
                    compact: true; iconName: "search"; text: root.pip.state === "loading" ? qsTr("Asking…") : qsTr("Find my public IP")
                    enabled: root.pip.state !== "loading"
                    onClicked: win.ask({ title: qsTr("Look up your public IP?"), icon: "globe", confirm: qsTr("Look it up"),
                                         message: qsTr("ChatToon will ask api.ipify.org, which sees your connection's address when answering. The result stays only in memory and is shown hidden.") },
                                       () => root.c.lookupPublicIp())
                }
                AppButton { visible: root.pip.known === true; compact: true; variant: "ghost"; text: qsTr("Forget"); onClicked: root.c.forgetPublicIp() }
            }
            Text { visible: root.pip.state === "error"; text: qsTr("The public IP could not be found (no internet?)."); color: Theme.danger; font.pixelSize: 12 }
            Text {
                Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: 12
                visible: root.pip.known === true
                color: root.pip.cgnat ? Theme.warning : Theme.textMuted
                text: root.pip.cgnat ? qsTr("Your public IP is a CGNAT address: port forwarding will not work. Use a tunnel in step 3.")
                                     : qsTr("To be sure there is no CGNAT, compare it with the “WAN IP” on your router's status page: they must be equal.")
            }
            Text {
                Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Theme.textFaint; font.pixelSize: 12
                visible: root.net.ipv6 === true
                text: qsTr("This computer also has a public IPv6 address. It may work without port forwarding, but only for viewers with IPv6.")
            }
        }

        // 2 — domain
        ColumnLayout {
            spacing: 10
            Text {
                Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Theme.textMuted; font.pixelSize: 13
                text: qsTr("A certificate needs a name. Use your own domain or a free dynamic DNS name (DuckDNS, No-IP, DigitalPlat FreeDomain, Cloudflare…). Point it to your public IP, or to your tunnel.")
            }
            AppTextField {
                id: domain
                Layout.fillWidth: true
                iconName: "link"
                font.family: Theme.mono
                placeholderText: "https://mychannel.example.org:8443"
                text: root.o.public_address
                echoMode: Privacy.live && !activeFocus ? TextInput.Password : TextInput.Normal
                onEditingFinished: backend.setConfig("overlay.public_address", text.trim())
                Accessible.name: qsTr("Public address")
            }
            StateChip {
                visible: domain.text.trim() !== ""
                text: root.c.validDomain(domain.text) ? qsTr("Valid address") : qsTr("Use https:// and a domain name")
                tone: root.c.validDomain(domain.text) ? "ok" : "error"
            }
            SecretField {
                visible: root.rt.publicOverlayUrl !== ""
                value: root.rt.publicOverlayUrl; shown: Privacy.url(root.rt.publicOverlayUrl, "public-url"); revealKey: "public-url"
                label: qsTr("Public overlay address")
            }
            Text {
                Layout.fillWidth: true; visible: root.rt.publicOverlayUrl !== ""; wrapMode: Text.WordWrap
                text: qsTr("Anyone with this link sees the avatar and hears its voice. Keep it private.")
                color: Theme.textMuted; font.pixelSize: 12
            }
        }

        // 3 — route
        ColumnLayout {
            spacing: 10
            GridLayout {
                Layout.fillWidth: true
                columns: width < 600 ? 1 : 2
                columnSpacing: 10
                ChoiceCard { iconName: "router"; title: qsTr("Open ports on the router"); description: qsTr("Needs a real public IP (no CGNAT) and access to the router.")
                             selected: root.route === "router"; onChosen: root.route = "router" }
                ChoiceCard { iconName: "cloud"; title: qsTr("Secure tunnel"); description: qsTr("No router changes; works with CGNAT. Cloudflare Tunnel or Tailscale Funnel.")
                             selected: root.route === "tunnel"; onChosen: root.route = "tunnel" }
            }
            Steps {
                visible: root.route === "router"
                model: [
                    qsTr("On the router, reserve the address %1 for this computer (DHCP reservation).").arg(Privacy.local(root.localIp, "lan") || "—"),
                    qsTr("Forward TCP 8443 (HTTPS) and TCP 80 (certificate) to this computer. These reach only Caddy, never ChatToon directly."),
                    qsTr("Never forward port %1 (ChatToon) or 11434 (Ollama): they must stay inside this computer.").arg(root.rt.port || root.o.port),
                    qsTr("If there are two routers (provider + Wi-Fi), forward on both or put the provider's in bridge mode."),
                ]
            }
            ColumnLayout {
                visible: root.route === "tunnel"
                spacing: 8
                Text {
                    Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Theme.textMuted; font.pixelSize: 13
                    text: qsTr("A tunnel connects this computer to the provider from the inside; nothing is opened on the router. Use the tunnel's https name in step 2.")
                }
                RowLayout {
                    spacing: 8
                    StateChip { text: "cloudflared"; tone: (root.proxy.cloudflared || {}).installed ? "ok" : "idle" }
                    StateChip { text: "Tailscale"; tone: (root.proxy.tailscale || {}).active ? "ok" : (root.proxy.tailscale || {}).installed ? "warn" : "idle" }
                }
                SecretField { value: "cloudflared tunnel --url http://127.0.0.1:" + (root.rt.port || root.o.port); label: qsTr("Cloudflare quick tunnel command") }
                SecretField { value: "tailscale funnel " + (root.rt.port || root.o.port); label: qsTr("Tailscale Funnel command") }
                Text {
                    Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Theme.textFaint; font.pixelSize: 12
                    text: qsTr("Tunnels already provide HTTPS: skip step 4. A quick tunnel gets a new name every time it starts.")
                }
            }
        }

        // 4 — HTTPS
        ColumnLayout {
            spacing: 10
            RowLayout {
                spacing: 8
                StateChip { text: (root.proxy.caddy || {}).active ? qsTr("Caddy running") : (root.proxy.caddy || {}).installed ? qsTr("Caddy installed, stopped") : qsTr("Caddy not installed")
                            tone: (root.proxy.caddy || {}).active ? "ok" : (root.proxy.caddy || {}).installed ? "warn" : "idle" }
                StateChip { visible: (root.proxy.nginx || {}).installed === true; text: (root.proxy.nginx || {}).active ? qsTr("nginx running") : qsTr("nginx installed")
                            tone: (root.proxy.nginx || {}).active ? "ok" : "warn" }
                AppButton { compact: true; variant: "ghost"; iconName: "refresh"; Accessible.name: qsTr("Check again"); onClicked: root.c.loadProxy() }
            }
            Text {
                Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Theme.textMuted; font.pixelSize: 13
                text: qsTr("Caddy gets the certificate by itself and forwards to ChatToon, which keeps listening only on this computer. Save this as /etc/caddy/conf.d/chattoon.caddy and reload Caddy:")
            }
            AppTextArea {
                Layout.fillWidth: true
                readOnly: true
                font.family: Theme.mono
                text: root.maskedSnippet(root.proxy.caddySnippet || "")
            }
            RowLayout {
                spacing: 8
                AppButton { iconName: "copy"; text: qsTr("Copy Caddy configuration"); onClicked: backend.copyText(root.proxy.caddySnippet || "") }
                AppButton { visible: backend.config.advanced; variant: "ghost"; iconName: "copy"; text: qsTr("Copy nginx configuration"); onClicked: backend.copyText(root.proxy.nginxSnippet || "") }
                AppButton { variant: "ghost"; iconName: "copy"; text: qsTr("Copy install command"); onClicked: backend.copyText("sudo pacman -S --needed caddy && sudo systemctl enable --now caddy") }
            }
        }

        // 5 — test
        ColumnLayout {
            spacing: 10
            RowLayout {
                spacing: 10
                AppButton {
                    variant: "primary"; iconName: "activity"; text: root.remote.state === "checking" ? qsTr("Testing…") : qsTr("Test the connection")
                    enabled: root.o.public_address !== "" && root.remote.state !== "checking"
                    onClicked: root.c.checkRemote()
                }
                StateChip {
                    visible: root.remote.state === "done"
                    text: root.remote.ok ? qsTr("Everything works!") : qsTr("Something is missing")
                    tone: root.remote.ok ? "ok" : "error"
                }
            }
            Text { visible: root.o.public_address === ""; text: qsTr("Fill in your domain in step 2 first."); color: Theme.textFaint; font.pixelSize: 12 }
            Repeater {
                model: root.remote.steps || []
                RowLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    spacing: 10
                    Icon { Layout.alignment: Qt.AlignTop; name: modelData.ok ? "checkCircle" : "x"; size: 18; color: modelData.ok ? Theme.success : Theme.danger }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2
                        Text { text: root.checkName(modelData.id); color: Theme.text; font.pixelSize: 13; font.weight: Font.Medium }
                        Text {
                            Layout.fillWidth: true; visible: !modelData.ok || modelData.code !== ""
                            text: root.codeText(modelData.code, modelData.detail)
                            color: modelData.ok ? Theme.warning : Theme.textMuted; font.pixelSize: 12; wrapMode: Text.WordWrap
                        }
                    }
                }
            }
            Text {
                Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Theme.textFaint; font.pixelSize: 12
                text: qsTr("Testing from inside your home may fail even when everything is right (many routers do not support NAT loopback). Confirm from a phone on mobile data.")
            }
        }
    }

    RowLayout {
        Layout.fillWidth: true
        AppButton { visible: root.step > 0; text: qsTr("Back"); onClicked: root.step-- }
        Item { Layout.fillWidth: true }
        AppButton { visible: root.step < 4; variant: "primary"; text: qsTr("Next"); onClicked: root.step++ }
    }
}
