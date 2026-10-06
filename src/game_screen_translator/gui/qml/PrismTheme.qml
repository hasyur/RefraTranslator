import QtQuick

QtObject {
    id: theme

    property bool dark: true
    property bool dohna: false
    property bool reducedMotion: false

    // Prism keeps its original palette. Dohna is a fixed-light print palette;
    // the controller still remembers the user's Prism light/dark preference.
    readonly property color paper: dohna ? "#F7F3E8" : (dark ? "#07090b" : "#cbd4d7")
    readonly property color white: dohna ? "#FFFDF7" : (dark ? "#0b0f13" : "#d7dde0")
    readonly property color ink: dohna ? "#17151E" : (dark ? "#07090b" : "#cbd4d7")
    readonly property color inkRaised: dohna ? "#FFFDF7" : (dark ? "#0b0f13" : "#d7dde0")
    readonly property color panel: dohna ? "#FFFDF7" : (dark ? "#0e1318" : "#becace")
    readonly property color line: dohna ? "#17151E" : (dark ? "#252d34" : "#9eacb3")
    readonly property color lineStrong: dohna ? "#17151E" : (dark ? "#46545f" : "#687c86")
    readonly property color text: dohna ? "#17151E" : (dark ? "#edf2f5" : "#111a1f")
    readonly property color textSoft: dohna ? "#4F4653" : (dark ? "#a4afb8" : "#384a53")
    readonly property color textDim: dohna ? "#766D77" : (dark ? "#66727c" : "#60727b")
    readonly property color accent: dohna ? "#FF4384" : (dark ? "#62e1ff" : "#00758f")
    readonly property color spectrum: dohna ? "#00DAD5" : (dark ? "#f27bd7" : "#992477")
    readonly property color accentText: dohna ? "#B51F59" : accent
    readonly property color spectrumText: dohna ? "#007A78" : spectrum
    readonly property color violet: dohna ? "#F5F044" : (dark ? "#8f7cff" : "#6655cf")
    readonly property color amber: dohna ? "#8D7600" : (dark ? "#ffc857" : "#9b6800")
    readonly property color electric: dohna ? "#00DAD5" : (dark ? "#4d8dff" : "#2f67c7")
    readonly property color glass: dohna ? "#FFFDF7" : (dark ? "#99121a22" : "#bfd3dde0")
    readonly property color glassRaised: dohna ? "#FFFDF7" : (dark ? "#c4182430" : "#dce7ecee")
    readonly property color stageShadow: dohna ? "#4017151E" : (dark ? "#6b000000" : "#3d253d47")
    readonly property color danger: dohna ? "#D62855" : (dark ? "#ff7f8f" : "#a62d43")
    readonly property color backgroundTop: dohna ? paper : ink
    readonly property color backgroundBottom: dohna ? paper : (dark ? "#0b1118" : "#b8c5ca")
    readonly property color navigationSurface: dohna ? ink : (dark ? "#d4070a0d" : "#c8d1dade")
    readonly property color navigationText: dohna ? white : text
    readonly property color navigationTextDim: dohna ? "#F5F044" : textDim
    readonly property color headerSurface: dohna ? paper : (dark ? "#c20b0f13" : "#d8d7dde0")
    readonly property color inputSurface: dohna ? white : (dark ? "#8f0b1016" : "#b8eef2f3")
    readonly property color inputTrack: dohna ? paper : (dark ? "#7a182333" : "#b8e3e9eb")
    readonly property color previewSurface: dohna ? white : (dark ? "#141b24" : "#edf2f4")
    readonly property color selectionEdge: dohna ? "#F5F044" : accent

    readonly property var displayFonts: dohna ? [
        "Arial Black",
        "Microsoft YaHei UI",
        "Bahnschrift",
        "Arial",
        "sans-serif"
    ] : [
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
        return dohna
                ? Math.max(48, Math.min(68, viewportWidth * 0.052))
                : Math.max(52, Math.min(80, viewportWidth * 0.0625))
    }

    readonly property real opticalStageOpacity: dohna ? 0 : (dark ? 0.64 : 0.56)
    readonly property real sweepAccentAlpha: dohna ? 0 : (dark ? 0.48 : 0.34)
    readonly property real sweepSpectrumAlpha: dohna ? 0 : (dark ? 0.42 : 0.3)
    readonly property real tertiaryRailOpacity: dohna ? 0 : (dark ? 0.58 : 0.5)
    readonly property real feedbackLineWidth: 3

    readonly property int fast: reducedMotion ? 0 : 100
    readonly property int ui: reducedMotion ? 0 : 150
    readonly property int panelMotion: reducedMotion ? 0 : 190
    // Event animations are explicitly gated and stopped by their coordinators.
    // Their durations stay stable while an animation is being stopped; changing
    // a running Qt 6.9 animation's duration to zero can defer its running-state
    // notification even though its visuals have already been hidden.
    readonly property int backgroundMotion: 230
    readonly property int pageMotion: 390
    readonly property int pageSecondaryMotion: 320
    readonly property int pageTertiaryMotion: 260
    readonly property int deviceEntryDelay: 24
    readonly property int startPreludeMotion: 350
    readonly property int startMotion: 900
    readonly property int actionMotion: 520
    readonly property int settleMotion: 460
    readonly property int warningMotion: 780
    readonly property int popPageMotion: reducedMotion ? 0 : 220
    readonly property int popActionMotion: reducedMotion ? 0 : 180
    readonly property int popStartMotion: reducedMotion ? 0 : 240
    readonly property int popWarningMotion: reducedMotion ? 0 : 260
    readonly property int popPressMotion: reducedMotion ? 0 : 120
}
