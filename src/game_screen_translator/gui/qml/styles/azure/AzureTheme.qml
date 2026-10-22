import QtQuick

QtObject {
    id: theme

    required property bool dark
    required property bool reducedMotion
    readonly property bool dohna: false

    readonly property color paper: dark ? "#071535" : "#f7f9ff"
    readonly property color white: dark ? "#10224b" : "#ffffff"
    readonly property color ink: dark ? "#040d22" : "#071b50"
    readonly property color inkRaised: dark ? "#10224b" : "#ffffff"
    readonly property color panel: dark ? "#0d1d42" : "#ffffff"
    readonly property color line: dark ? "#283e72" : "#c8d6ff"
    readonly property color lineStrong: dark ? "#536da7" : "#7896e7"
    readonly property color text: dark ? "#f1f5ff" : "#10255e"
    readonly property color textSoft: dark ? "#c2d0f5" : "#40578d"
    readonly property color textDim: dark ? "#879bcc" : "#6b7ea9"
    readonly property color accent: dark ? "#4382ff" : "#1054f5"
    readonly property color spectrum: dark ? "#18d7ff" : "#05bde9"
    readonly property color accentText: dark ? "#8bb0ff" : "#164fc9"
    readonly property color spectrumText: dark ? "#75e9ff" : "#007d9d"
    readonly property color violet: dark ? "#5c75dc" : "#314fd1"
    readonly property color amber: dark ? "#ffd16d" : "#a86a00"
    readonly property color electric: spectrum
    readonly property color glass: dark ? "#10224b" : "#ffffff"
    readonly property color glassRaised: dark ? "#172c5a" : "#ffffff"
    readonly property color stageShadow: dark ? "#88020b26" : "#2d244ca1"
    readonly property color danger: dark ? "#ff829b" : "#bf3150"
    readonly property color backgroundTop: dark ? "#091a3c" : "#ffffff"
    readonly property color backgroundBottom: dark ? "#06112a" : "#eaf0ff"
    readonly property color heroPlane: dark ? "#195dfa" : "#1656ee"
    readonly property color navigationSurface: dark ? "#06112c" : "#081b4d"
    readonly property color navigationText: "#f4f7ff"
    readonly property color navigationTextDim: dark ? "#a6b8e7" : "#a7b9ef"
    readonly property color headerSurface: dark ? "#0b1b3b" : "#f7f9ff"
    readonly property color inputSurface: dark ? "#071632" : "#f9fbff"
    readonly property color inputTrack: dark ? "#1a2d56" : "#dce6ff"
    readonly property color previewSurface: dark ? "#071632" : "#f7f9ff"
    readonly property color selectionEdge: spectrum
    readonly property color buttonPrimary: accent
    readonly property color buttonPrimaryText: "#ffffff"

    readonly property var displayFonts: [
        "Bahnschrift", "Microsoft YaHei UI", "DIN Alternate", "Arial Narrow", "sans-serif"
    ]
    readonly property var uiFonts: [
        "Segoe UI Variable", "Microsoft YaHei UI", "Segoe UI", "sans-serif"
    ]
    readonly property var monoFonts: [
        "Cascadia Code", "Microsoft YaHei UI", "Consolas", "monospace"
    ]
    readonly property string displayFont: displayFonts[0]
    readonly property string uiFont: uiFonts[0]
    readonly property string monoFont: monoFonts[0]
    readonly property string displayCjkFont: displayFonts[1]
    readonly property string uiCjkFont: uiFonts[1]
    readonly property string monoCjkFont: monoFonts[1]

    readonly property real tertiaryRailOpacity: 0.48
    readonly property int fast: reducedMotion ? 0 : 90
    readonly property int ui: reducedMotion ? 0 : 130
    readonly property int panelMotion: reducedMotion ? 0 : 170
    readonly property int backgroundMotion: 210
    readonly property int pageMotion: reducedMotion ? 0 : 300
    readonly property int pageSecondaryMotion: reducedMotion ? 0 : 250
    readonly property int pageTertiaryMotion: reducedMotion ? 0 : 200
    readonly property int deviceEntryDelay: 20
    readonly property int startPreludeMotion: 350
    readonly property int startMotion: 850
    readonly property int actionMotion: 480
    readonly property int settleMotion: 430
    readonly property int warningMotion: 700
    readonly property int popPageMotion: reducedMotion ? 0 : 190
    readonly property int popActionMotion: reducedMotion ? 0 : 150
    readonly property int popStartMotion: reducedMotion ? 0 : 210
    readonly property int popWarningMotion: reducedMotion ? 0 : 230
    readonly property int popPressMotion: reducedMotion ? 0 : 100

    function containsCjk(value) {
        return /[\u2e80-\u9fff\uf900-\ufaff]/.test(String(value))
    }
    function displayFontFor(value) { return containsCjk(value) ? displayCjkFont : displayFont }
    function uiFontFor(value) { return containsCjk(value) ? uiCjkFont : uiFont }
    function monoFontFor(value) { return containsCjk(value) ? monoCjkFont : monoFont }
    function displayTitleSize(viewportWidth) {
        return Math.max(38, Math.min(60, viewportWidth * 0.046))
    }
}
