import QtQuick

QtObject {
    id: theme
    property bool active: true
    readonly property bool dark: false
    readonly property bool dohna: true
    readonly property bool refraStyle: false
    readonly property bool refraDark: false
    readonly property bool refraLight: false
    property bool reducedMotion: false

    // Dohna uses a fixed-light print palette.
    readonly property color paper: "#F7F3E8" 
    readonly property color white: "#FFFDF7" 
    readonly property color ink: "#17151E" 
    readonly property color inkRaised: "#FFFDF7" 
    readonly property color panel: "#FFFDF7" 
    readonly property color line: "#17151E" 
    readonly property color lineStrong: "#17151E" 
    readonly property color text: "#17151E" 
    readonly property color textSoft: "#4F4653" 
    readonly property color textDim: "#766D77" 
    readonly property color accent: "#FF4384" 
    readonly property color spectrum: "#00DAD5" 
    readonly property color accentText: "#B51F59" 
    readonly property color spectrumText: "#007A78" 
    readonly property color violet: "#F5F044" 
    readonly property color amber: "#8D7600" 
    readonly property color electric: "#00DAD5" 
    readonly property color glass: "#FFFDF7" 
    readonly property color glassRaised: "#FFFDF7" 
    readonly property color stageShadow: "#4017151E" 
    readonly property color danger: "#D62855" 
    readonly property color backgroundTop: paper 
    readonly property color backgroundBottom: paper 
    readonly property color navigationSurface: ink 
    readonly property color navigationText: white 
    readonly property color navigationTextDim: "#F5F044" 
    readonly property color headerSurface: paper 
    readonly property color inputSurface: white 
    readonly property color inputTrack: paper 
    readonly property color previewSurface: white 
    readonly property color selectionEdge: "#F5F044" 
    readonly property color buttonPrimary: white 
    readonly property color buttonPrimaryText: ink 
    readonly property var displayFonts: [
        "Arial Black",
        "Microsoft YaHei UI",
        "Bahnschrift",
        "Arial",
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
        return false
                ? Math.max(46, Math.min(74, viewportWidth * 0.056))
                : Math.max(48, Math.min(68, viewportWidth * 0.052))
                }

    readonly property real tertiaryRailOpacity: 0 
    readonly property int ui: reducedMotion ? 0 : 150
    readonly property int startPreludeMotion: 350
    readonly property int popPageMotion: reducedMotion ? 0 : 220
    readonly property int popActionMotion: reducedMotion ? 0 : 180
    readonly property int popWarningMotion: reducedMotion ? 0 : 260
    readonly property int popPressMotion: reducedMotion ? 0 : 120
    readonly property int dohnaPageMotion: reducedMotion ? 0 : 320
    readonly property int dohnaTitleDelay: reducedMotion ? 0 : 48
    readonly property int dohnaTitleMotion: reducedMotion ? 0 : 300
}
