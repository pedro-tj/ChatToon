pragma Singleton
import QtQuick

// Design tokens. "system" follows the Plasma/GNOME colour scheme.
// Every colour used for text meets WCAG AA (4.5:1) — see tests/test_theme.py.
QtObject {
    property string mode: "system"
    readonly property bool dark: mode === "dark"
        || (mode === "system" && Qt.styleHints.colorScheme !== Qt.ColorScheme.Light)

    readonly property color bg: dark ? "#100e18" : "#f2f0f8"
    readonly property color sidebar: dark ? "#16131f" : "#e9e6f3"
    readonly property color surface: dark ? Qt.rgba(0.13, 0.12, 0.19, 0.78) : Qt.rgba(1, 1, 1, 0.82)
    readonly property color surfaceStrong: dark ? "#1d1a28" : "#fcfbff"
    readonly property color hover: dark ? Qt.rgba(1, 1, 1, 0.06) : Qt.rgba(0.1, 0.05, 0.25, 0.05)
    readonly property color field: dark ? Qt.rgba(0, 0, 0, 0.28) : Qt.rgba(1, 1, 1, 0.95)
    readonly property color border: dark ? Qt.rgba(1, 1, 1, 0.09) : Qt.rgba(0.1, 0.05, 0.25, 0.11)
    readonly property color borderStrong: dark ? Qt.rgba(1, 1, 1, 0.18) : Qt.rgba(0.1, 0.05, 0.25, 0.22)
    readonly property color text: dark ? "#efedf6" : "#1a1726"
    readonly property color textMuted: dark ? "#a9a5bd" : "#554f6e"
    readonly property color textFaint: dark ? "#8d89a3" : "#635d7a"
    readonly property color accent: dark ? "#b49cff" : "#6233c9"
    readonly property color accent2: dark ? "#ff8fc4" : "#b3175f"
    readonly property color accentText: dark ? "#1a1033" : "#ffffff"  // text on the accent gradient
    readonly property color success: dark ? "#4ade80" : "#14632f"
    readonly property color warning: dark ? "#fbbf24" : "#8a3b0a"
    readonly property color danger: dark ? "#fb7185" : "#a3122f"

    readonly property int radius: 16
    readonly property int radiusSmall: 10
    readonly property int animFast: 150
    readonly property int anim: 220
    readonly property var curve: [0.4, 0.0, 0.2, 1.0, 1.0, 1.0]

    readonly property string sans: pick(["Inter", "Noto Sans", "Cantarell", "DejaVu Sans"])
    readonly property string mono: pick(["JetBrains Mono", "Fira Code", "Noto Sans Mono", "DejaVu Sans Mono"])

    function tint(c, alpha) { return Qt.rgba(c.r, c.g, c.b, alpha) }

    function pick(families) {
        const available = Qt.fontFamilies()
        for (const f of families)
            if (available.indexOf(f) >= 0)
                return f
        return Qt.application.font.family
    }
}
