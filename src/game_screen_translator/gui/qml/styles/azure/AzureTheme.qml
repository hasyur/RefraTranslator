import QtQuick

QtObject {
    id: theme

    required property bool dark
    required property bool reducedMotion
    readonly property bool dohna: false

    // Azure is an art-directed skin: its navy/cyan scene stays consistent
    // while the user's system theme preference remains untouched elsewhere.
    readonly property color paper: "#071535"
    readonly property color white: "#ffffff"
    readonly property color ink: "#040d22"
    readonly property color inkRaised: "#ffffff"
    readonly property color panel: "#f5f7ff"
    readonly property color line: "#c5d2ef"
    readonly property color lineStrong: "#7089c5"
    readonly property color text: "#071b50"
    readonly property color textSoft: "#233b74"
    readonly property color textDim: "#5d70a0"
    readonly property color accent: "#104bf5"
    readonly property color spectrum: "#05bde9"
    readonly property color accentText: "#164fc9"
    readonly property color spectrumText: "#007d9d"
    readonly property color violet: "#314fd1"
    readonly property color amber: "#ffd16d"
    readonly property color electric: spectrum
    readonly property color glass: "#f5f7ff"
    readonly property color glassRaised: "#ffffff"
    readonly property color stageShadow: "#88020b26"
    readonly property color danger: "#c32748"
    readonly property color backgroundTop: "#06132f"
    readonly property color backgroundBottom: "#06112a"
    readonly property color heroPlane: "#124df4"
    readonly property color navigationSurface: "#06112c"
    readonly property color navigationText: "#f4f7ff"
    readonly property color navigationTextDim: "#a6b8e7"
    readonly property color headerSurface: "#f7f9ff"
    readonly property color inputSurface: "#f8faff"
    readonly property color inputTrack: "#dce6ff"
    readonly property color previewSurface: "#f7f9ff"
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
