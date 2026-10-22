import QtQuick

QtObject {
    id: theme

    property bool dark: true
    property bool dohna: false
    property bool reducedMotion: false
    readonly property bool refraStyle: !dohna
    readonly property bool refraDark: !dohna && dark
    readonly property bool refraLight: refraStyle && !dark

    // Dohna keeps its fixed-light print palette. Prism shares the P3 layout
    // while its dark and light palettes remain distinct.
    readonly property color paper: dohna ? "#F7F3E8" : refraDark ? "#03143b" : refraLight ? "#F7F9FC" : (dark ? "#14191d" : "#f2f3ed")
    readonly property color white: dohna ? "#FFFDF7" : refraDark ? "#071d48" : refraLight ? "#FFFFFF" : (dark ? "#1c2429" : "#e5e9e4")
    readonly property color ink: dohna ? "#17151E" : refraDark ? "#020d27" : refraLight ? "#07162E" : "#14191d"
    readonly property color inkRaised: dohna ? "#FFFDF7" : refraDark ? "#061a42" : refraLight ? "#FFFFFF" : (dark ? "#1c2429" : "#e5e9e4")
    readonly property color panel: dohna ? "#FFFDF7" : refraDark ? "#071a3c" : refraLight ? "#FFFFFF" : (dark ? "#1c2429" : "#e5e9e4")
    readonly property color line: dohna ? "#17151E" : refraDark ? "#17467e" : refraLight ? "#D5DFED" : (dark ? "#354147" : "#bbc4bf")
    readonly property color lineStrong: dohna ? "#17151E" : refraDark ? "#2871bb" : refraLight ? "#AFC1DC" : (dark ? "#536168" : "#88948e")
    readonly property color text: dohna ? "#17151E" : refraDark ? "#f1f7ff" : refraLight ? "#101A32" : (dark ? "#edf0ec" : "#182126")
    readonly property color textSoft: dohna ? "#4F4653" : refraDark ? "#b8c9e5" : refraLight ? "#435472" : (dark ? "#b2bbb8" : "#46534f")
    readonly property color textDim: dohna ? "#766D77" : refraDark ? "#7894bc" : refraLight ? "#72819A" : (dark ? "#87938f" : "#65716c")
    readonly property color accent: dohna ? "#FF4384" : refraDark ? "#00d9ff" : refraLight ? "#00D9F5" : (dark ? "#62cbd0" : "#177780")
    readonly property color spectrum: dohna ? "#00DAD5" : refraDark ? "#ff36c7" : refraLight ? "#FF36C7" : (dark ? "#62cbd0" : "#177780")
    readonly property color accentText: dohna ? "#B51F59" : refraLight ? "#075BFF" : accent
    readonly property color spectrumText: dohna ? "#007A78" : spectrum
    readonly property color violet: dohna ? "#F5F044" : refraDark ? "#5e87ff" : refraLight ? "#167BFF" : (dark ? "#92a9a7" : "#526b69")
    readonly property color amber: dohna ? "#8D7600" : (dark ? "#ffc857" : "#9b6800")
    readonly property color electric: dohna ? "#00DAD5" : refraDark ? "#00aaff" : refraLight ? "#075BFF" : (dark ? "#62cbd0" : "#177780")
    readonly property color glass: dohna ? "#FFFDF7" : refraDark ? "#0a2455" : refraLight ? "#F4F8FF" : (dark ? "#1c2429" : "#e5e9e4")
    readonly property color glassRaised: dohna ? "#FFFDF7" : refraDark ? "#0c2a61" : refraLight ? "#FFFFFF" : (dark ? "#1c2429" : "#e5e9e4")
    readonly property color stageShadow: dohna ? "#4017151E" : (dark ? "#6b000000" : "#3d253d47")
    readonly property color danger: dohna ? "#D62855" : (dark ? "#ff7f8f" : "#a62d43")
    readonly property color backgroundTop: dohna ? paper : refraDark ? "#061c51" : paper
    readonly property color backgroundBottom: dohna ? paper : refraDark ? "#020d2c" : paper
    readonly property color navigationSurface: dohna ? ink : refraDark ? "#041338" : refraLight ? "#FFFFFF" : (dark ? "#1c2429" : "#e5e9e4")
    readonly property color navigationText: dohna ? white : text
    readonly property color navigationTextDim: dohna ? "#F5F044" : textDim
    readonly property color headerSurface: dohna ? paper : refraDark ? "#05183f" : refraLight ? "#FFFFFF" : paper
    readonly property color inputSurface: dohna ? white : refraDark ? "#071c43" : refraLight ? "#F5F8FD" : (dark ? "#252f34" : "#f2f3ed")
    readonly property color inputTrack: dohna ? paper : refraDark ? "#123166" : refraLight ? "#E4ECF8" : (dark ? "#303a3f" : "#d1d8d2")
    readonly property color previewSurface: dohna ? white : refraDark ? "#020d27" : refraLight ? "#F4F8FF" : (dark ? "#14191d" : "#f2f3ed")
    readonly property color selectionEdge: dohna ? "#F5F044" : accent
    readonly property color buttonPrimary: dohna ? white : refraDark ? "#0758dd" : refraLight ? "#075BFF" : (dark ? "#e5e9e4" : "#1c2429")
    readonly property color buttonPrimaryText: dohna ? ink : refraDark || refraLight ? "#ffffff" : (dark ? "#14191d" : "#f2f3ed")

    readonly property var displayFonts: dohna ? [
        "Arial Black",
        "Microsoft YaHei UI",
        "Bahnschrift",
        "Arial",
        "sans-serif"
    ] : refraStyle ? [
        "Arial Narrow",
        "Bahnschrift",
        "DIN Alternate",
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
    readonly property string displayCjkFont: dohna ? displayFonts[1] : "Microsoft YaHei UI"
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
        return refraStyle
                ? Math.max(46, Math.min(74, viewportWidth * 0.056))
                : dohna
                ? Math.max(48, Math.min(68, viewportWidth * 0.052))
                : Math.max(40, Math.min(54, viewportWidth * 0.042))
    }

    readonly property real tertiaryRailOpacity: dohna ? 0 : 0.16

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
    // Dohna pages arrive as one opaque group; the title settles just after
    // the card bodies instead of replaying Prism's fade-in sequence.
    readonly property int dohnaPageMotion: reducedMotion ? 0 : 320
    readonly property int dohnaTitleDelay: reducedMotion ? 0 : 48
    readonly property int dohnaTitleMotion: reducedMotion ? 0 : 300
}
