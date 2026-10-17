import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

// "Where is your OBS Studio?" — the overlay address for this computer, the local network
// (an explicit opt-in) or the internet (RemoteWizard).
ColumnLayout {
    id: root
    readonly property var rt: backend.runtimeState
    readonly property var o: backend.config.overlay
    readonly property var net: backend.connectivity.network
    readonly property var lanTest: backend.connectivity.lanTest
    readonly property var lanChoices: (net.addresses || []).filter(a => a.lan)
    readonly property var otherChoices: (net.addresses || []).filter(a => !a.lan)
    property string where: o.lan_enabled ? "lan" : o.public_address !== "" ? "internet" : "local"
    property string chosenIp: o.lan_address || (lanChoices.length ? lanChoices[0].ip : "")

    spacing: 14
    Layout.fillWidth: true
    Component.onCompleted: backend.connectivity.refresh()

    function kindText(k) { return ({ ethernet: qsTr("Cable"), wifi: qsTr("Wi-Fi"), vpn: qsTr("VPN"), virtual: qsTr("Virtual (Docker, VMs)"), other: qsTr("Network") })[k] || k }
    function addressLabel(a) { return Privacy.local(a.ip, "lan") + " — " + kindText(a.kind) + " (" + a.interface + ")" + (a.default ? " ★" : "") }
    function lanErrorText(code) {
        return ({ "address-unavailable": qsTr("This address is not on this computer anymore (another Wi-Fi or cable?). Choose the current one."),
                  "port-busy": qsTr("Another program uses this port on the network address."),
                  "invalid-address": qsTr("Only an address of your home network can be used."),
                  "bind-failed": qsTr("The network address could not be opened.") })[code] || ""
    }

    GridLayout {
        Layout.fillWidth: true
        columns: width < 640 ? 1 : 3
        columnSpacing: 10
        rowSpacing: 10
        ChoiceCard { iconName: "monitor"; title: qsTr("On this computer"); description: qsTr("Just copy and paste the address.")
                     selected: root.where === "local"; onChosen: root.where = "local" }
        ChoiceCard { iconName: "network"; title: qsTr("Another computer on the same network"); description: qsTr("Allow access from your home network.")
                     selected: root.where === "lan"; onChosen: root.where = "lan" }
        ChoiceCard { iconName: "globe"; title: qsTr("Another computer over the internet"); description: qsTr("Needs a domain and HTTPS. A guide helps you.")
                     selected: root.where === "internet"; onChosen: root.where = "internet" }
    }

    // ------------------------------------------------------------- this computer
    ColumnLayout {
        Layout.fillWidth: true
        visible: root.where === "local"
        spacing: 12
        SecretField {
            value: root.rt.overlayUrl; shown: Privacy.url(root.rt.overlayUrl, "local-url"); revealKey: "local-url"; canOpen: true
            label: qsTr("Overlay address on this computer")
        }
        Steps {
            model: [
                qsTr("In OBS, click + under Sources and choose Browser."),
                qsTr("Paste the address above in URL. Width 1920, height 1080."),
                qsTr("Leave “Shutdown source when not visible” off so the avatar keeps its state."),
                backend.config.voice.audio_output === "overlay" ? qsTr("Enable “Control audio via OBS” — the voice will come from this source.")
                                                                : qsTr("The voice plays on this computer: capture it with Desktop Audio."),
                qsTr("The background is transparent. Resize and position the source in your scene as you like."),
            ]
        }
    }

    // ------------------------------------------------------------- local network
    ColumnLayout {
        Layout.fillWidth: true
        visible: root.where === "lan"
        spacing: 12
        Text {
            Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Theme.textMuted; font.pixelSize: 13
            text: qsTr("For an OBS on another computer of your home network (same router). Only computers of this network are answered, and the address still carries its secret code. Nothing is opened to the internet.")
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            Text { text: qsTr("Network address of this computer"); color: Theme.text; font.pixelSize: 13; font.weight: Font.Medium }
            AppCombo {
                Layout.fillWidth: true
                enabled: !root.o.lan_enabled
                textRole: "label"; valueRole: "ip"
                model: root.lanChoices.concat(backend.config.advanced ? root.otherChoices : []).map(a => ({ ip: a.ip, label: root.addressLabel(a) }))
                currentIndex: Math.max(0, model.findIndex(a => a.ip === root.chosenIp))
                onActivated: root.chosenIp = currentValue
                Accessible.name: qsTr("Network address of this computer")
            }
            AppButton { compact: true; variant: "ghost"; iconName: "refresh"; tip: qsTr("Look again (new Wi-Fi or cable)"); Accessible.name: tip; onClicked: backend.connectivity.refresh() }
        }
        Text {
            visible: root.lanChoices.length === 0 && !root.net.loading
            Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Theme.warning; font.pixelSize: 12
            text: qsTr("This computer is not connected to a home network (cable or Wi-Fi).")
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            AppButton {
                visible: !root.o.lan_enabled
                variant: "primary"; iconName: "network"; text: qsTr("Allow on my home network")
                enabled: root.chosenIp !== ""
                onClicked: win.ask({ title: qsTr("Allow the overlay on your home network?"), icon: "shield", confirm: qsTr("Allow"),
                                     message: qsTr("Computers connected to the same router will be able to open the overlay if they have its secret address. Other ChatToon functions are never exposed. You can turn it off at any time.") },
                                   () => backend.connectivity.setLan(true, root.chosenIp))
            }
            AppButton {
                visible: root.o.lan_enabled
                iconName: "x"; text: qsTr("Turn off network access")
                onClicked: backend.connectivity.setLan(false, "")
            }
        }
        ColumnLayout {
            Layout.fillWidth: true
            visible: root.o.lan_enabled
            spacing: 10
            SecretField {
                visible: root.rt.lanOverlayUrl !== ""
                value: root.rt.lanOverlayUrl; shown: Privacy.url(root.rt.lanOverlayUrl, "lan-url"); revealKey: "lan-url"
                label: qsTr("Overlay address on the local network")
            }
            Text { visible: root.rt.lanError !== ""; Layout.fillWidth: true; text: root.lanErrorText(root.rt.lanError); color: Theme.danger; font.pixelSize: 12; wrapMode: Text.WordWrap }
            // firewall: it would block the other computer even with everything right
            Rectangle {
                Layout.fillWidth: true
                visible: root.net.firewall && root.net.firewall.active === true
                implicitHeight: fwCol.implicitHeight + 22
                radius: Theme.radiusSmall
                color: Theme.tint(Theme.warning, 0.1)
                border.color: Theme.tint(Theme.warning, 0.4)
                ColumnLayout {
                    id: fwCol
                    anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; margins: 12 }
                    spacing: 8
                    Text {
                        Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Theme.text; font.pixelSize: 13
                        text: qsTr("The firewall (%1) is on: it blocks the other computer until you allow your home network on port %2.")
                              .arg(root.net.firewall.ufw ? "ufw" : "firewalld").arg(root.rt.port || root.o.port)
                    }
                    RowLayout {
                        spacing: 8
                        AppButton {
                            iconName: "shield"; text: qsTr("Allow only my home network")
                            onClicked: win.ask({ title: qsTr("Change the firewall?"), icon: "shield", confirm: qsTr("Allow"),
                                                 message: qsTr("This rule lets only your home network reach the overlay port. Your administrator password will be asked."),
                                                 details: [backend.connectivity.firewallCommand().join(" ")] },
                                               () => backend.connectivity.allowFirewall(false))
                        }
                        AppButton { variant: "ghost"; iconName: "copy"; text: qsTr("Copy the command"); onClicked: backend.copyText(backend.connectivity.firewallCommand().join(" ")) }
                    }
                }
            }
            RowLayout {
                spacing: 10
                AppButton { iconName: "activity"; text: qsTr("Test from this computer"); enabled: root.rt.lanOverlayUrl !== "" && root.lanTest.state !== "testing"; onClicked: backend.connectivity.testLan() }
                StateChip {
                    visible: root.lanTest.state !== "idle"
                    text: root.lanTest.state === "testing" ? qsTr("Testing…") : root.lanTest.state === "ok" ? qsTr("ChatToon answers on the network")
                        : qsTr("No answer (%1)").arg(root.lanTest.code)
                    tone: root.lanTest.state === "testing" ? "busy" : root.lanTest.state === "ok" ? "ok" : "error"
                }
            }
            Steps {
                model: [
                    qsTr("On the other computer, open OBS and add a Browser source."),
                    qsTr("Paste the network address above. Width 1920, height 1080."),
                    qsTr("If it does not load, check the firewall above and that both computers use the same router."),
                    qsTr("For the voice to come out of that OBS, choose Voice › Audio output › Inside OBS here."),
                ]
            }
        }
    }

    // ------------------------------------------------------------- internet
    RemoteWizard { visible: root.where === "internet" }

    RowLayout {
        Layout.fillWidth: true
        visible: backend.config.advanced
        spacing: 8
        Text { Layout.fillWidth: true; text: qsTr("Someone saw the secret address? Create a new one: every old link stops working."); color: Theme.textFaint; font.pixelSize: 12; wrapMode: Text.WordWrap }
        AppButton {
            compact: true; iconName: "key"; text: qsTr("New secret address")
            onClicked: win.ask({ title: qsTr("Create a new secret address?"), icon: "key", danger: true, confirm: qsTr("Create"),
                                 message: qsTr("OBS, browsers and proxies using the current address stop showing the character until you paste the new one.") },
                               () => backend.connectivity.rotateToken())
        }
    }
}
