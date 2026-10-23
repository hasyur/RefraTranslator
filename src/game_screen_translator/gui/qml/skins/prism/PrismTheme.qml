import QtQuick

QtObject {
    id: theme
    property bool active: true
    property bool dark: true
    readonly property bool dohna: false
    readonly property bool refraStyle: true
    readonly property bool refraDark: dark
    readonly property bool refraLight: !dark
    property bool reducedMotion: false

    // Dohna keeps its fixed-light print palette. Prism shares the P3 layout
    // while its dark and light palettes remain distinct.
    readonly property color paper: refraDark ? "#03143b" : refraLight ? "#F7F9FC" : (dark ? "#14191d" : "#f2f3ed")
    readonly property color white: refraDark ? "#071d48" : refraLight ? "#FFFFFF" : (dark ? "#1c2429" : "#e5e9e4")
    readonly property color ink: refraDark ? "#020d27" : refraLight ? "#07162E" : "#14191d"
    readonly property color inkRaised: refraDark ? "#061a42" : refraLight ? "#FFFFFF" : (dark ? "#1c2429" : "#e5e9e4")
    readonly property color panel: refraDark ? "#071a3c" : refraLight ? "#FFFFFF" : (dark ? "#1c2429" : "#e5e9e4")
    readonly property color line: refraDark ? "#17467e" : refraLight ? "#D5DFED" : (dark ? "#354147" : "#bbc4bf")
    readonly property color lineStrong: refraDark ? "#2871bb" : refraLight ? "#AFC1DC" : (dark ? "#536168" : "#88948e")
    readonly property color text: refraDark ? "#f1f7ff" : refraLight ? "#101A32" : (dark ? "#edf0ec" : "#182126")
    readonly property color textSoft: refraDark ? "#b8c9e5" : refraLight ? "#435472" : (dark ? "#b2bbb8" : "#46534f")
    readonly property color textDim: refraDark ? "#7894bc" : refraLight ? "#72819A" : (dark ? "#87938f" : "#65716c")
    readonly property color accent: refraDark ? "#00d9ff" : refraLight ? "#00D9F5" : (dark ? "#62cbd0" : "#177780")
    readonly property color spectrum: refraDark ? "#ff36c7" : refraLight ? "#FF36C7" : (dark ? "#62cbd0" : "#177780")
    readonly property color accentText: refraLight ? "#075BFF" : accent
    readonly property color spectrumText: spectrum
    readonly property color violet: refraDark ? "#5e87ff" : refraLight ? "#167BFF" : (dark ? "#92a9a7" : "#526b69")
    readonly property color amber: (dark ? "#ffc857" : "#9b6800")
    readonly property color electric: refraDark ? "#00aaff" : refraLight ? "#075BFF" : (dark ? "#62cbd0" : "#177780")
    readonly property color glass: refraDark ? "#0a2455" : refraLight ? "#F4F8FF" : (dark ? "#1c2429" : "#e5e9e4")
    readonly property color glassRaised: refraDark ? "#0c2a61" : refraLight ? "#FFFFFF" : (dark ? "#1c2429" : "#e5e9e4")
    readonly property color stageShadow: (dark ? "#6b000000" : "#3d253d47")
    readonly property color danger: (dark ? "#ff7f8f" : "#a62d43")
    readonly property color backgroundTop: refraDark ? "#061c51" : paper
    readonly property color backgroundBottom: refraDark ? "#020d2c" : paper
    readonly property color navigationSurface: refraDark ? "#041338" : refraLight ? "#FFFFFF" : (dark ? "#1c2429" : "#e5e9e4")
    readonly property color navigationText: text
    readonly property color navigationTextDim: textDim
    readonly property color headerSurface: refraDark ? "#05183f" : refraLight ? "#FFFFFF" : paper
    readonly property color inputSurface: refraDark ? "#071c43" : refraLight ? "#F5F8FD" : (dark ? "#252f34" : "#f2f3ed")
    readonly property color inputTrack: refraDark ? "#123166" : refraLight ? "#E4ECF8" : (dark ? "#303a3f" : "#d1d8d2")
    readonly property color previewSurface: refraDark ? "#020d27" : refraLight ? "#F4F8FF" : (dark ? "#14191d" : "#f2f3ed")
    readonly property color selectionEdge: accent
    readonly property color buttonPrimary: refraDark ? "#0758dd" : refraLight ? "#075BFF" : (dark ? "#e5e9e4" : "#1c2429")
    readonly property color buttonPrimaryText: refraDark || refraLight ? "#ffffff" : (dark ? "#14191d" : "#f2f3ed")

    readonly property var displayFonts: [
        "Arial Narrow",
        "Bahnschrift",
        "DIN Alternate",
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
    readonly property string displayCjkFont: "Microsoft YaHei UI"
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
        return true
                ? Math.max(46, Math.min(74, viewportWidth * 0.056))
                : Math.max(40, Math.min(54, viewportWidth * 0.042))
    }

    readonly property real tertiaryRailOpacity: 0.16

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
}
