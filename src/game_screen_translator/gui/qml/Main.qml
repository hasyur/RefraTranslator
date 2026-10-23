pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Window
import "skins/prism" as PrismSkin
import "skins/dohna" as DohnaSkin

ApplicationWindow {
    id: root
    objectName: "prismWorkbenchWindow"

    visible: false
    width: 1280
    height: 820
    minimumWidth: activeSkin ? activeSkin.minimumWorkbenchWidth : 980
    minimumHeight: 700
    title: "RefraTranslator · Workbench"

    // The sole domain controller remains owned by the host across skin changes.
    // qmllint disable unqualified
    readonly property var boundWorkbench: workbench
    // qmllint enable unqualified
    property bool startPreludePending: false
    property string translationSideMode: "settings"
    property bool hotkeyRecording: false
    property var scrollPositions: ({})

    function setTranslationSideMode(mode) {
        if (mode === "settings" || mode === "glossary")
            translationSideMode = mode
    }

    function setHotkeyRecording(recording) {
        hotkeyRecording = Boolean(recording)
    }

    function scrollPosition(pageKey, scrollKey) {
        const pagePositions = scrollPositions[pageKey]
        if (!pagePositions)
            return 0
        const value = pagePositions[scrollKey]
        return typeof value === "number" && isFinite(value) ? value : 0
    }

    function rememberScrollPosition(pageKey, scrollKey, value) {
        if (!pageKey || !scrollKey || typeof value !== "number" || !isFinite(value))
            return
        const nextPages = ({})
        for (const existingPage in scrollPositions)
            nextPages[existingPage] = scrollPositions[existingPage]
        const nextPage = ({})
        const previousPage = nextPages[pageKey] || ({})
        for (const existingScroll in previousPage)
            nextPage[existingScroll] = previousPage[existingScroll]
        nextPage[scrollKey] = Math.max(0, value)
        nextPages[pageKey] = nextPage
        scrollPositions = nextPages
    }
    readonly property var activeSkin: boundWorkbench.skinPreference === "dohna"
                                     ? dohnaSkinLoader.item : prismSkinLoader.item
    readonly property bool reduceMotion: boundWorkbench.reducedMotion
    readonly property bool animationsRunning: activeSkin ? activeSkin.animationsRunning : false
    readonly property bool pageContentReady: activeSkin ? activeSkin.pageContentReady : true
    readonly property bool pageTransitioning: activeSkin ? activeSkin.pageTransitioning : false
    readonly property bool fullCanvasHome: activeSkin !== null
                                           && activeSkin.fullCanvasHome === true
    readonly property bool navigationMotionEnabled: activeSkin
                                                     && activeSkin.navigationMotionEnabled === true
    readonly property bool navigationResizeActive: activeSkin
                                                   && activeSkin.navigationResizeActive === true

    function completeStartPrelude() {
        if (!startPreludePending)
            return
        startPreludeTimer.stop()
        startPreludePending = false
        boundWorkbench.toggleLive()
    }

    function requestLiveToggle() {
        if (startPreludePending)
            return
        if (boundWorkbench.running || reduceMotion || !activeSkin) {
            boundWorkbench.toggleLive()
            return
        }
        startPreludePending = true
        activeSkin.pulseVisualStart()
        startPreludeTimer.interval = activeSkin.startPreludeMotion
        startPreludeTimer.restart()
    }

    function saveAll() {
        boundWorkbench.saveAll()
        if (activeSkin)
            activeSkin.pulseVisualAction("calibrate")
    }

    onClosing: function(close) {
        if (boundWorkbench.running) {
            close.accepted = false
            boundWorkbench.hideWorkbench()
        }
    }

    Timer {
        id: startPreludeTimer
        objectName: "startPreludeTimer"
        interval: 160
        repeat: false
        onTriggered: root.completeStartPrelude()
    }

    Loader {
        id: prismSkinLoader
        objectName: "prismSkinLoader"
        anchors.fill: parent
        active: root.boundWorkbench.skinPreference === "prism" || item !== null
        visible: root.boundWorkbench.skinPreference === "prism"
        sourceComponent: Component {
            PrismSkin.Workbench {
                appShell: root
            }
        }
    }

    Loader {
        id: dohnaSkinLoader
        objectName: "dohnaSkinLoader"
        anchors.fill: parent
        active: root.boundWorkbench.skinPreference === "dohna" || item !== null
        visible: root.boundWorkbench.skinPreference === "dohna"
        sourceComponent: Component {
            DohnaSkin.Workbench {
                appShell: root
            }
        }
    }

    Connections {
        target: root.boundWorkbench

        function onErrorRaised(title, message) {
            if (root.activeSkin)
                root.activeSkin.showError(title, message)
        }
    }
}
