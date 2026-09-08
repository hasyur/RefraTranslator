import QtQuick

QtObject {
    id: theme

    property bool dark: true
    property bool reducedMotion: false

    readonly property color ink: dark ? "#07090b" : "#cbd4d7"
    readonly property color inkRaised: dark ? "#0b0f13" : "#d7dde0"
    readonly property color panel: dark ? "#0e1318" : "#becace"
    readonly property color line: dark ? "#252d34" : "#9eacb3"
    readonly property color lineStrong: dark ? "#46545f" : "#687c86"
    readonly property color text: dark ? "#edf2f5" : "#111a1f"
    readonly property color textSoft: dark ? "#a4afb8" : "#384a53"
    readonly property color textDim: dark ? "#66727c" : "#60727b"
    readonly property color accent: dark ? "#62e1ff" : "#00758f"
    readonly property color spectrum: dark ? "#f27bd7" : "#992477"
    readonly property color violet: dark ? "#8f7cff" : "#6655cf"
    readonly property color amber: dark ? "#ffc857" : "#9b6800"
    readonly property color electric: dark ? "#4d8dff" : "#2f67c7"
    readonly property color glass: dark ? "#b80f1b28" : "#d9e2e9eb"
    readonly property color glassRaised: dark ? "#d1182333" : "#ebebf0f1"
    readonly property color stageShadow: dark ? "#6b000000" : "#3d253d47"
    readonly property color danger: dark ? "#ff7f8f" : "#a62d43"

    readonly property var displayFonts: [
        "Bahnschrift",
        "Microsoft YaHei UI",
        "DIN Alternate",
        "Arial Narrow",
        "sans-serif"
    ]
    readonly property var uiFonts: [
        "Segoe UI Variable",
        "Microsoft YaHei UI",
        "Segoe UI",
        "sans-serif"
    ]
    readonly property var monoFonts: [
        "Cascadia Code",
        "Microsoft YaHei UI",
        "Consolas",
        "monospace"
    ]

    // Single-family aliases keep the existing controls compatible; prominent
    // typography uses the complete stacks above so CJK glyphs never inherit a
    // platform-dependent emergency fallback.
    readonly property string displayFont: displayFonts[0]
    readonly property string uiFont: uiFonts[0]
    readonly property string monoFont: monoFonts[0]
    readonly property string displayCjkFont: displayFonts[1]
    readonly property string uiCjkFont: uiFonts[1]
    readonly property string monoCjkFont: monoFonts[1]

    function containsCjk(value) {
        return /[\u2e80-\u9fff\uf900-\ufaff]/.test(String(value))
    }

    function displayFontFor(value) {
        return containsCjk(value) ? displayCjkFont : displayFont
    }

    function uiFontFor(value) {
        return containsCjk(value) ? uiCjkFont : uiFont
    }

    function monoFontFor(value) {
        return containsCjk(value) ? monoCjkFont : monoFont
    }

    function displayTitleSize(viewportWidth) {
        return Math.max(52, Math.min(80, viewportWidth * 0.0625))
    }

    readonly property real opticalStageOpacity: dark ? 0.5 : 0.4
    readonly property real sweepAccentAlpha: dark ? 0.48 : 0.34
    readonly property real sweepSpectrumAlpha: dark ? 0.42 : 0.3
    readonly property real tertiaryRailOpacity: dark ? 0.58 : 0.5
    readonly property real feedbackLineWidth: 3

    readonly property int fast: reducedMotion ? 0 : 110
    readonly property int ui: reducedMotion ? 0 : 180
    readonly property int panelMotion: reducedMotion ? 0 : 280
    // Event animations are explicitly gated and stopped by their coordinators.
    // Their durations stay stable while an animation is being stopped; changing
    // a running Qt 6.9 animation's duration to zero can defer its running-state
    // notification even though its visuals have already been hidden.
    readonly property int pageMotion: 720
    readonly property int pageSecondaryMotion: 540
    readonly property int pageTertiaryMotion: 480
    readonly property int deviceEntryDelay: 70
    readonly property int startPreludeMotion: 350
    readonly property int startMotion: 900
    readonly property int actionMotion: 720
    readonly property int settleMotion: 460
    readonly property int warningMotion: 780
}
