pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Window
import "components"
import "pages"

ApplicationWindow {
    id: root
    objectName: "prismWorkbenchWindow"

    visible: false
    width: 1280
    height: 820
    minimumWidth: prism.dohna ? navigationRail.implicitWidth + 802 : 980
    minimumHeight: 700
    title: "RefraTranslator · Prism Workbench"

    // The sole context property is intentionally injected by QmlWorkbenchHost.
    // qmllint disable unqualified
    readonly property var boundWorkbench: workbench
    // qmllint enable unqualified
    readonly property var pageOrder: ["HOME", "CAPTURE", "OCR", "TRANSLATION", "OVERLAY", "CACHE", "SETTINGS"]
    readonly property bool animationsRunning: visible
                                              && !boundWorkbench.reducedMotion
    property bool pageContentReady: true
    readonly property bool pageMotionEnabled: animationsRunning && pageContentReady
    readonly property string visualPage: boundWorkbench.currentPage
    readonly property bool reduceMotion: boundWorkbench.reducedMotion
    readonly property bool fullCanvasHome: prism.refraStyle && boundWorkbench.currentPage === "HOME"
    property bool navigationMotionArmed: false
    property bool navigationResizeActive: false
    property bool navigationTargetIsHero: false
    property int navigationGeometryRevision: 0
    readonly property bool navigationMotionEnabled: visible && prism.refraStyle
                                                   && navigationMotionArmed
                                                   && !navigationResizeActive
                                                   && !reduceMotion
    property string lastAnimatedPage: ""
    readonly property bool pageTransitioning: animationsRunning
                                              && (pageTransitionAnimation.running
                                                  || dohnaPageTransitionAnimation.running)
    property int pageTransitionSequence: 0
    property bool startPreludePending: false

    function navigationTargetSlot(index) {
        if (!prism.refraStyle)
            return null
        if (navigationTargetIsHero)
            return homePage.p3NavigationSlots.itemAt(index)
        const delegate = navigationRepeater.itemAt(index)
        return delegate ? delegate.p3Slot : null
    }

    function navigationTargetBounds(index, geometryRevision) {
        // The caller passes navigationGeometryRevision directly in its
        // binding. QML cannot infer Layout dependencies hidden inside
        // mapToItem(), so this invalidates the mapped target after layout.
        const slot = navigationTargetSlot(index)
        if (!slot)
            return { x: 0, y: 0, width: 0, height: 0 }
        let point
        if (navigationTargetIsHero) {
            // Map through the untransformed page-content parent so the slot
            // stays at its final layout position while the page itself enters.
            const slotLocal = slot.mapToItem(pageContentMotion, Qt.point(0, 0))
            const contentOrigin = pageContentMotion.parent.mapToItem(
                root.contentItem,
                Qt.point(pageContentMotion.x, pageContentMotion.y)
            )
            point = Qt.point(contentOrigin.x + slotLocal.x, contentOrigin.y + slotLocal.y)
        } else {
            point = slot.mapToItem(root.contentItem, Qt.point(0, 0))
        }
        return {
            x: point.x,
            y: point.y,
            width: slot.width,
            height: slot.height
        }
    }

    function actionTargetSlot(index) {
        if (!prism.refraStyle)
            return null
        if (navigationTargetIsHero)
            return index === 0 ? homePage.p3StartActionSlot : homePage.p3ApplyActionSlot
        return index === 0 ? innerStartActionSlot : innerApplyActionSlot
    }

    function actionTargetBounds(index, geometryRevision) {
        // mapToItem() returns geometry through a JS call, so QML cannot infer
        // the Layout ancestors it depends on. The caller passes the settled
        // geometry revision directly to invalidate this binding after layout.
        const slot = actionTargetSlot(index)
        if (!slot)
            return { x: 0, y: 0, width: 0, height: 0 }
        let point
        if (navigationTargetIsHero) {
            const slotLocal = slot.mapToItem(pageContentMotion, Qt.point(0, 0))
            const contentOrigin = pageContentMotion.parent.mapToItem(
                root.contentItem,
                Qt.point(pageContentMotion.x, pageContentMotion.y)
            )
            point = Qt.point(contentOrigin.x + slotLocal.x, contentOrigin.y + slotLocal.y)
        } else {
            point = slot.mapToItem(root.contentItem, Qt.point(0, 0))
        }
        return { x: point.x, y: point.y, width: slot.width, height: slot.height }
    }

    function scheduleNavigationTargetRefresh() {
        if (!prism.refraStyle) {
            navigationMotionArmed = false
            navigationTargetRefresh.restart()
            return
        }
        navigationTargetRefresh.restart()
    }

    function refreshNavigationTargets() {
        navigationTargetIsHero = fullCanvasHome
        navigationGeometryRevision += 1
        if (visible)
            navigationMotionArmed = true
    }

    function markWindowResize() {
        if (!visible || !prism.refraStyle)
            return
        navigationResizeActive = true
        navigationResizeSettle.restart()
        navigationTargetRefresh.restart()
    }

    onWidthChanged: markWindowResize()
    onHeightChanged: markWindowResize()

    onClosing: function(close) {
        if (boundWorkbench.running) {
            close.accepted = false
            boundWorkbench.hideWorkbench()
        }
    }

    function pageIndex(page) {
        const index = pageOrder.indexOf(page)
        return index < 0 ? 0 : index
    }

    function pageTitle(page) {
        return pageTitleLight(page) + pageTitleHeavy(page)
    }

    function pageTitleLight(page) {
        if (prism.refraStyle) {
            const p3Titles = {
                "HOME": "HOME",
                "CAPTURE": "CAPTURE",
                "OCR": "OCR",
                "TRANSLATION": "TRANSLATE",
                "OVERLAY": "OVERLAY",
                "CACHE": "CACHE",
                "SETTINGS": "SETTINGS"
            }
            return p3Titles[page] || page
        }
        if (root.boundWorkbench.skinPreference === "dohna") {
            const titles = {
                "HOME": "翻译控制台",
                "CAPTURE": "画面捕获",
                "OCR": "文字识别",
                "TRANSLATION": "译文设置",
                "OVERLAY": "字幕叠加",
                "CACHE": "翻译缓存",
                "SETTINGS": "高级设置"
            }
            return titles[page] || page
        }
        const titles = {
            "HOME": "总览",
            "CAPTURE": "捕获",
            "OCR": "文字识别",
            "TRANSLATION": "翻译",
            "OVERLAY": "覆盖层",
            "CACHE": "缓存",
            "SETTINGS": "设置"
        }
        return titles[page] || page
    }

    function pageTitleHeavy(page) {
        if (prism.refraStyle)
            return pageTitleLightChinese(page)
        return ""
    }

    function pageTitleLightChinese(page) {
        const labels = {
            "HOME": "总览",
            "CAPTURE": "捕获",
            "OCR": "文字识别",
            "TRANSLATION": "翻译",
            "OVERLAY": "覆盖层",
            "CACHE": "缓存",
            "SETTINGS": "设置"
        }
        return labels[page] || ""
    }

    function navigationMenuTitle(page) {
        const titles = {
            "HOME": "HOME",
            "CAPTURE": "CAPTURE",
            "OCR": "OCR",
            "TRANSLATION": "TRANSLATE",
            "OVERLAY": "OVERLAY",
            "CACHE": "CACHE",
            "SETTINGS": "SETTINGS"
        }
        return titles[page] || String(page)
    }

    function pageCode(page) {
        const codes = {
            "HOME": "OVERVIEW",
            "CAPTURE": "CAPTURE",
            "OCR": "OCR",
            "TRANSLATION": "TRANSLATION",
            "OVERLAY": "OVERLAY",
            "CACHE": "CACHE",
            "SETTINGS": "SETTINGS"
        }
        return codes[page] || String(page)
    }

    function navigationLabel(page) {
        if (root.boundWorkbench.skinPreference === "dohna") {
            const labels = {
                "HOME": "总览",
                "CAPTURE": "画面捕获",
                "OCR": "文字识别",
                "TRANSLATION": "译文设置",
                "OVERLAY": "字幕叠加",
                "CACHE": "翻译缓存",
                "SETTINGS": "高级设置"
            }
            return labels[page] || page
        }
        const labels = {
            "HOME": "总览",
            "CAPTURE": "捕获",
            "OCR": "文字识别",
            "TRANSLATION": "翻译",
            "OVERLAY": "覆盖层",
            "CACHE": "缓存",
            "SETTINGS": "设置"
        }
        return labels[page] || page
    }

    function pageSubtitle(page) {
        const subtitles = {
            "HOME": "配置、状态与运行入口",
            "CAPTURE": "选择显示器与字幕捕获区域",
            "OCR": "设置真实 OCR 设备和识别策略",
            "TRANSLATION": "配置本地模型、外部 API 与游戏术语",
            "OVERLAY": "控制现有预览窗口的背景合成",
            "CACHE": "查看真实计数并维护人工修订",
            "SETTINGS": "调度、OBS 输出与诊断信息"
        }
        return subtitles[page] || ""
    }

    function settlePageTransition() {
        pageContentReady = true
        pageContentTranslate.x = 0
        pageContentMotion.opacity = 1
        pageHeaderTranslate.x = 0
        pageHeaderSlice.opacity = 1
        tertiaryRail.opacity = prism.tertiaryRailOpacity
    }

    function pulseVisualAction(action) {
        stage.pulseAction(action)
        dohnaFeedback.pulseAction(action)
    }

    function pulseVisualWarning() {
        stage.pulseWarning()
        dohnaFeedback.pulseWarning()
    }

    function pulseVisualStart() {
        stage.pulseStart()
        dohnaFeedback.pulseStart()
    }

    function beginPageTransition() {
        if (visualPage === lastAnimatedPage)
            return
        lastAnimatedPage = visualPage
        pageTransitionSequence += 1
        if (reduceMotion || !visible) {
            pageTransitionAnimation.stop()
            dohnaPageTransitionAnimation.stop()
            pageContentReady = true
            settlePageTransition()
            return
        }
        if (prism.dohna) {
            pageTransitionAnimation.stop()
            pageContentReady = true
            pageContentMotion.opacity = 1
            pageContentTranslate.x = Math.max(54, Math.min(132, root.width * 0.12))
            pageHeaderSlice.opacity = 1
            pageHeaderTranslate.x = -Math.max(28, Math.min(72, root.width * 0.055))
            dohnaPageTransitionAnimation.restart()
            return
        }
        pageContentReady = false
        pageContentMotion.opacity = 0
        pageContentTranslate.x = 8
        pageHeaderSlice.opacity = 0
        pageHeaderTranslate.x = 14
        pageTransitionAnimation.restart()
    }

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
        if (boundWorkbench.running) {
            boundWorkbench.toggleLive()
            return
        }
        if (reduceMotion) {
            boundWorkbench.toggleLive()
            return
        }
        startPreludePending = true
        pulseVisualStart()
        startPreludeTimer.restart()
    }

    function settleReducedMotion() {
        pageTransitionAnimation.stop()
        dohnaPageTransitionAnimation.stop()
        pageContentReady = true
        settlePageTransition()
        stage.settleMotion()
        dohnaFeedback.settle()
        if (startPreludePending)
            completeStartPrelude()
    }

    onVisualPageChanged: {
        beginPageTransition()
        scheduleNavigationTargetRefresh()
    }
    onReduceMotionChanged: {
        if (reduceMotion)
            settleReducedMotion()
    }
    onVisibleChanged: {
        if (visible) {
            lastAnimatedPage = ""
            beginPageTransition()
            navigationMotionArmed = false
            scheduleNavigationTargetRefresh()
        } else {
            navigationMotionArmed = false
            navigationResizeActive = false
            if (startPreludePending) {
                startPreludeTimer.stop()
                startPreludePending = false
                stage.settleMotion()
                dohnaFeedback.settle()
            }
            pageTransitionAnimation.stop()
            dohnaPageTransitionAnimation.stop()
            pageContentReady = true
            settlePageTransition()
        }
    }

    Timer {
        id: startPreludeTimer
        objectName: "startPreludeTimer"
        interval: prism.startPreludeMotion
        repeat: false
        onTriggered: root.completeStartPrelude()
    }

    Timer {
        id: navigationTargetRefresh
        interval: 0
        repeat: false
        onTriggered: root.refreshNavigationTargets()
    }

    Timer {
        id: navigationResizeSettle
        interval: 130
        repeat: false
        onTriggered: root.navigationResizeActive = false
    }

    PrismTheme {
        id: prism
        objectName: "prismTheme"
        dark: root.boundWorkbench.effectiveTheme !== "light"
        dohna: root.boundWorkbench.skinPreference === "dohna"
        reducedMotion: root.boundWorkbench.reducedMotion
    }

    Connections {
        target: prism
        function onDohnaChanged() {
            pageTransitionAnimation.stop()
            dohnaPageTransitionAnimation.stop()
            root.navigationMotionArmed = false
            root.scheduleNavigationTargetRefresh()
            root.pageContentReady = true
            root.settlePageTransition()
            dohnaFeedback.settle()
        }
    }

    background: Item {
        Rectangle {
            anchors.fill: parent
            gradient: Gradient {
                GradientStop { position: 0; color: prism.backgroundTop }
                GradientStop { position: 0.62; color: prism.dohna ? prism.inkRaised : prism.paper }
                GradientStop { position: 1; color: prism.backgroundBottom }
            }
        }
        Rectangle {
            visible: prism.refraDark
            x: root.width * 0.16
            y: -root.height * 0.24
            width: root.width * 0.16
            height: root.height * 1.55
            rotation: 24
            color: "#154b9c"
            opacity: 0.13
        }
        Rectangle {
            visible: prism.refraDark
            x: root.width * 0.70
            y: -root.height * 0.28
            width: root.width * 0.12
            height: root.height * 1.65
            rotation: 24
            color: "#1660c1"
            opacity: 0.09
        }
        Rectangle {
            visible: prism.refraDark
            x: root.width * 0.46
            y: root.height * 0.49
            width: root.width * 0.55
            height: root.height * 0.44
            rotation: -16
            color: "#092d74"
            opacity: 0.16
        }
    }

    PrismDialog {
        id: errorDialog
        objectName: "errorDialog"
        surfaceName: "errorDialog"
        theme: prism
        parent: Overlay.overlay
        anchors.centerIn: parent
        property string errorTitle: "操作失败"
        property string errorMessage: ""
        title: errorTitle
        acceptText: "确认"
        showRejectButton: false
        acceptTone: "danger"
        width: Math.min(480, root.width - 80)

        Text {
            text: errorDialog.errorMessage
            color: prism.text
            font.family: prism.uiFontFor(text)
            font.pixelSize: 15
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
    }

    Connections {
        target: root.boundWorkbench

        function onErrorRaised(title, message) {
            errorDialog.errorTitle = title
            errorDialog.errorMessage = message
            root.pulseVisualWarning()
            errorDialog.open()
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            id: navigationRail
            implicitWidth: prism.dohna ? Math.ceil(dohnaNavigationText.width + 40)
                         : prism.refraStyle ? Math.max(168, Math.min(230, root.width * 0.18))
                         : root.width < 1100 ? 176 : 184
            Layout.preferredWidth: implicitWidth
            Layout.fillHeight: true
            visible: !root.fullCanvasHome
            color: prism.navigationSurface
            border.color: prism.line
            clip: prism.dohna

            Rectangle {
                objectName: "refraDarkSidebarFacet"
                visible: prism.refraDark
                x: parent.width * 0.59
                y: -root.height * 0.06
                width: parent.width * 0.34
                height: root.height * 1.12
                rotation: 13
                color: "#124ab1"
                opacity: 0.18
            }

            Rectangle {
                objectName: "refraDarkSidebarLight"
                visible: prism.refraDark
                x: parent.width * 0.81
                y: -root.height * 0.08
                width: parent.width * 0.11
                height: root.height * 1.16
                rotation: 13
                color: "#1767ff"
                opacity: 0.10
            }

            TextMetrics {
                id: dohnaNavigationText
                text: "TRANSLATION  " + root.navigationLabel("TRANSLATION")
                font.family: prism.monoFontFor(text)
                font.pixelSize: 24
                font.weight: Font.Bold
                font.letterSpacing: 0.4
            }

            ColumnLayout {
                id: navigationLayout
                anchors.fill: parent
                anchors.margins: prism.dohna
                                ? (root.width < 1100 ? 14 : 20)
                                : prism.refraStyle ? 12
                                : (root.width < 1100 ? 12 : 16)
                spacing: prism.refraStyle ? 6 : 10

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: prism.refraStyle ? 12 : 7
                    spacing: 0
                    Text {
                        objectName: "refraBrandWordmark"
                        text: prism.refraStyle
                              ? (prism.refraLight ? "<font color='#075bff'>Refra</font>Translator"
                                                  : "<font color='#00d9ff'>Refra</font>Translator")
                              : "REFRA"
                        textFormat: prism.refraStyle ? Text.RichText : Text.PlainText
                        color: prism.navigationText
                        font.family: prism.refraStyle ? "Arial Black" : prism.displayFontFor(text)
                        font.pixelSize: prism.refraStyle
                                        ? (root.width < 1100 ? 17 : 22) : 23
                        font.weight: prism.refraStyle ? Font.Black : Font.Bold
                        font.letterSpacing: prism.refraStyle ? 0 : 4
                        fontSizeMode: prism.refraStyle ? Text.HorizontalFit : Text.FixedSize
                        minimumPixelSize: prism.refraStyle ? 14 : 1
                        Layout.fillWidth: true
                        elide: prism.refraStyle ? Text.ElideNone : Text.ElideRight
                    }
                    Text {
                        text: prism.refraStyle ? "GAME SCREEN TRANSLATOR" : "TRANSLATOR / WORKBENCH"
                        color: prism.accentText
                        font.family: prism.monoFontFor(text)
                        font.pixelSize: prism.refraStyle ? 10 : 12
                        font.letterSpacing: prism.refraStyle ? 0.8 : 1.1
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.topMargin: 8
                    Layout.bottomMargin: 5
                    Layout.preferredHeight: prism.refraStyle ? 2 : 1
                    color: prism.refraStyle ? prism.electric : prism.lineStrong
                    opacity: prism.refraStyle ? 0.8 : 1
                }

                Repeater {
                    id: navigationRepeater
                    model: root.pageOrder
                    Item {
                        objectName: "navigationSlot" + index
                        readonly property Item p3Slot: p3NavigationSlot
                        required property int index
                        required property var modelData
                        implicitWidth: 150
                        implicitHeight: prism.dohna
                                        ? Math.ceil(dohnaNavigationText.tightBoundingRect.height / 0.85)
                                        : prism.refraStyle ? 66 : 52
                        Layout.fillWidth: true
                        Layout.minimumWidth: prism.dohna ? 0 : -1
                        Layout.preferredHeight: implicitHeight
                        // Overscan the rotated bar; the sidebar clips both ends
                        // flush, while the enlarged control remains clickable.
                        Layout.leftMargin: prism.dohna ? -navigationLayout.anchors.margins - 16 : 0
                        Layout.rightMargin: Layout.leftMargin
                        Layout.maximumWidth: prism.dohna ? navigationRail.width + 32 : Number.POSITIVE_INFINITY
                        // Preserve the visible gap of the original 50 px strips
                        // when their thickness changes under the same rotation.
                        Layout.bottomMargin: prism.dohna
                                             ? Math.round((implicitHeight - 50) * (1 / Math.cos(12 * Math.PI / 180) - 1)) : 0

                        Item {
                            id: p3NavigationSlot
                            objectName: "navigationSlotGeometry" + index
                            anchors.fill: parent
                            visible: prism.refraStyle
                        }

                        PrismButton {
                            objectName: prism.refraStyle ? "" : "navigationButton" + index
                            anchors.fill: parent
                            theme: prism
                            navigation: true
                            text: prism.dohna
                                  ? String(modelData) + "  " + root.navigationLabel(String(modelData))
                                  : root.navigationLabel(String(modelData))
                            navigationNumber: String(index + 1).padStart(2, "0")
                            navigationCode: root.pageCode(String(modelData))
                            navigationSubtitle: ""
                            navigationTilt: 0
                            primary: root.boundWorkbench.currentPage === modelData
                            quiet: root.boundWorkbench.currentPage !== modelData
                            visible: !prism.refraStyle
                            onClicked: root.boundWorkbench.setPage(String(modelData))
                        }
                    }
                }

                Item { Layout.fillHeight: true }

                Rectangle {
                    objectName: "activeProfileCard"
                    visible: !prism.refraStyle
                    Layout.fillWidth: true
                    implicitHeight: 72
                    color: "transparent"
                    border.color: prism.line
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 12
                        spacing: 3
                        Text {
                            text: "ACTIVE PROFILE"
                            color: prism.navigationTextDim
                            font.family: prism.monoFontFor(text)
                            font.pixelSize: 12
                            font.letterSpacing: 1
                        }
                        Text {
                            objectName: "activeProfileName"
                            text: root.boundWorkbench.currentProfileName
                            color: prism.navigationText
                            font.family: prism.uiFontFor(text)
                            font.pixelSize: 15
                            font.weight: Font.Medium
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                    }
                }

                Text {
                    text: "PRISM  /  SWISS GRID"
                    visible: !prism.dohna && !prism.refraStyle
                    color: prism.navigationTextDim
                    font.family: prism.monoFontFor(text)
                    font.pixelSize: 12
                    font.letterSpacing: 0.8
                    wrapMode: Text.WordWrap
                    horizontalAlignment: Text.AlignHCenter
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignHCenter
                    Layout.bottomMargin: 5
                }
            }
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            DohnaBackdrop {
                id: dohnaBackdrop
                objectName: "dohnaBackdrop"
                anchors.fill: parent
                anchors.margins: 12
                theme: prism
                visible: prism.dohna
            }

            PrismMotionFeedback {
                id: stage
                objectName: "prismMotionFeedback"
                theme: prism
                pageTransitionSequence: root.pageTransitionSequence
                reducedMotion: root.boundWorkbench.reducedMotion
                motionEnabled: root.animationsRunning && !prism.dohna
            }

            ColumnLayout {
                anchors.fill: parent
                spacing: 0

                Rectangle {
                    objectName: "pageHeaderBar"
                    clip: prism.dohna || prism.refraStyle
                    Layout.fillWidth: true
                    visible: !root.fullCanvasHome
                    Layout.preferredHeight: Math.max(
                        root.fullCanvasHome ? 0
                        : prism.refraStyle ? (root.height <= 820 ? 148 : 164)
                        : prism.dohna ? (root.height <= 820 ? 116 : 142)
                        : (root.height <= 820 ? 104 : 116),
                        pageHeaderTextColumn.implicitHeight + 16
                    )
                    color: prism.headerSurface
                    border.color: prism.line

                    Rectangle {
                        objectName: "refraDarkHeaderFacet"
                        visible: prism.refraDark
                        x: parent.width * 0.36
                        y: -parent.height * 0.54
                        width: parent.width * 0.48
                        height: parent.height * 2.1
                        rotation: 14
                        color: "#0b2a62"
                        opacity: 0.58
                    }
                    Rectangle {
                        objectName: "refraDarkHeaderLight"
                        visible: prism.refraDark
                        x: parent.width * 0.76
                        y: -parent.height * 0.44
                        width: parent.width * 0.16
                        height: parent.height * 1.9
                        rotation: 14
                        color: "#1455c4"
                        opacity: 0.24
                    }

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 22
                        anchors.rightMargin: 22
                        spacing: 14

                        ColumnLayout {
                            id: pageHeaderTextColumn
                            Layout.fillWidth: true
                            spacing: 0
                            Text {
                                visible: !prism.refraStyle
                                text: String(root.pageIndex(root.boundWorkbench.currentPage) + 1).padStart(2, "0")
                                      + " / " + (prism.dohna
                                                  ? root.boundWorkbench.currentPage
                                                  : root.pageCode(root.boundWorkbench.currentPage))
                                color: prism.accentText
                                font.family: prism.monoFontFor(text)
                                font.pixelSize: 12
                                font.letterSpacing: 1.8
                            }
                            Item {
                                id: pageHeaderSlice
                                objectName: "pageHeaderSlice"
                                readonly property real titleSize: prism.displayTitleSize(root.width)
                                Layout.fillWidth: true
                                Layout.preferredHeight: displayTitleGroup.implicitHeight
                                Layout.minimumHeight: displayTitleGroup.implicitHeight
                                clip: false
                                TextMetrics {
                                    id: refraEnglishTitleMetrics
                                    objectName: "refraEnglishTitleMetrics"
                                    font: refraEnglishPageTitle.font
                                    text: refraEnglishPageTitle.text
                                }
                                transform: Translate {
                                    id: pageHeaderTranslate
                                    objectName: "pageHeaderTranslate"
                                }

                                RefractedTitle {
                                    id: displayTitleGroup
                                    objectName: "pageDisplayTitle"
                                    anchors.fill: parent
                                    visible: !prism.refraStyle
                                    theme: prism
                                    lightText: root.pageTitleLight(root.boundWorkbench.currentPage)
                                    heavyText: root.pageTitleHeavy(root.boundWorkbench.currentPage)
                                    titleSize: pageHeaderSlice.titleSize
                                    transitionSequence: root.pageTransitionSequence
                                    motionEnabled: root.pageMotionEnabled
                                }
                                Text {
                                    id: refraEnglishPageTitle
                                    objectName: "refraEnglishPageTitle"
                                    visible: prism.refraStyle
                                    x: 0
                                    y: -2
                                    width: Math.min(540, parent.width * 0.72)
                                    height: parent.height
                                    text: root.pageTitleLight(root.boundWorkbench.currentPage)
                                    color: prism.text
                                    font.family: "Arial Black"
                                    font.pixelSize: Math.min(76, Math.max(48, root.width * 0.058))
                                    font.weight: Font.Black
                                    font.italic: true
                                    font.letterSpacing: -3.2
                                    fontSizeMode: Text.HorizontalFit
                                    horizontalAlignment: Text.AlignLeft
                                    verticalAlignment: Text.AlignVCenter
                                    elide: Text.ElideNone
                                    rotation: -3.2
                                }
                                Text {
                                    id: refraChinesePageTitle
                                    objectName: "refraChinesePageTitle"
                                    visible: prism.refraStyle
                                    x: refraEnglishTitleMetrics.tightBoundingRect.width + 16
                                    y: 0
                                    width: Math.min(100, parent.width - x - 58)
                                    height: parent.height
                                    text: root.pageTitleHeavy(root.boundWorkbench.currentPage)
                                    color: prism.accentText
                                    font.family: prism.uiFontFor(text)
                                    font.pixelSize: 24
                                    font.weight: Font.Bold
                                    verticalAlignment: Text.AlignVCenter
                                    elide: Text.ElideRight
                                }
                                Item {
                                    objectName: "refraHeaderPrism"
                                    visible: prism.refraStyle
                                    x: refraChinesePageTitle.x + refraChinesePageTitle.implicitWidth + 9
                                    y: Math.max(0, (parent.height - height) / 2)
                                    width: 76
                                    height: 74
                                    Image {
                                        anchors.fill: parent
                                        source: "assets/refra-prism.png"
                                        fillMode: Image.PreserveAspectFit
                                        smooth: true
                                        scale: 1.2
                                    }
                                }
                                PrismFoldRule {
                                    objectName: "prismPageHeaderRule"
                                    visible: !prism.dohna
                                    theme: prism
                                    width: Math.min(parent.width * 0.72, 420)
                                    anchors.left: parent.left
                                    anchors.bottom: parent.bottom
                                }
                                Rectangle {
                                    objectName: "pageHeaderUnderline"
                                    visible: prism.dohna
                                    width: Math.min(parent.width * 0.72, 420)
                                    height: prism.dohna ? 5 : 1
                                    anchors.left: parent.left
                                    anchors.bottom: parent.bottom
                                    color: prism.dohna ? prism.violet : prism.accent
                                    opacity: prism.dohna ? 1 : 0.46
                                    rotation: prism.dohna ? -1.8 : -1.2
                                    antialiasing: true
                                }
                            }
                            Text {
                                objectName: "pageSubtitle"
                                text: root.pageSubtitle(root.boundWorkbench.currentPage)
                                visible: !prism.refraStyle
                                color: prism.textSoft
                                font.family: prism.uiFontFor(text)
                                font.pixelSize: 13
                                Layout.topMargin: prism.dohna ? 10 : 8
                            }
                        }

                        Text {
                            visible: root.boundWorkbench.settingsDirty
                                     && !prism.refraStyle
                            text: "● 未应用"
                            color: prism.amber
                            font.family: prism.monoFontFor(text)
                            font.pixelSize: 12
                        }
                        PrismButton {
                            objectName: "saveAllButton"
                            theme: prism
                            text: "应用更改"
                            visible: !prism.refraStyle
                            enabled: root.boundWorkbench.hasProfile
                            onClicked: {
                                root.boundWorkbench.saveAll()
                                if (root.boundWorkbench.currentPage === "SETTINGS")
                                    root.pulseVisualAction("calibrate")
                            }
                        }
                        PrismButton {
                            objectName: "startLiveButton"
                            theme: prism
                            primary: true
                            visible: !prism.refraStyle
                            text: root.startPreludePending
                                  ? (prism.dohna ? "正在点亮光路…" : "正在启动…")
                                  : root.boundWorkbench.startButtonText
                            enabled: root.boundWorkbench.runPhase !== "stopping"
                                     && !root.startPreludePending
                                     && (root.boundWorkbench.canStart || root.boundWorkbench.running)
                            onClicked: root.requestLiveToggle()
                        }
                        ColumnLayout {
                            visible: prism.refraStyle
                            Layout.maximumWidth: 170
                            spacing: 2
                            Text {
                                text: "当前配置"
                                color: prism.textDim
                                font.family: prism.monoFontFor(text)
                                font.pixelSize: 11
                            }
                            Text {
                                objectName: "darkHeaderProfileName"
                                text: root.boundWorkbench.currentProfileName
                                color: prism.text
                                font.family: prism.uiFontFor(text)
                                font.pixelSize: 15
                                font.weight: Font.DemiBold
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }
                            Text {
                                text: root.boundWorkbench.running ? "● 正在翻译" : "● 未启动"
                                color: root.boundWorkbench.running ? prism.accentText : prism.textSoft
                                font.family: prism.uiFontFor(text)
                                font.pixelSize: 12
                            }
                        }
                    }
                }

                Item {
                    id: pageContentHost
                    Layout.fillWidth: true
                    Layout.fillHeight: true

                    Item {
                        id: pageContentMotion
                        objectName: "pageContentMotion"
                        anchors.fill: parent
                        transform: Translate {
                            id: pageContentTranslate
                            objectName: "pageContentTranslate"
                        }

                        StackLayout {
                            objectName: "pageStack"
                            anchors.fill: parent
                            anchors.margins: root.fullCanvasHome ? 0
                                              : prism.refraStyle ? (root.width < 1100 ? 10 : 14)
                                              : root.width < 1100 ? 14 : 18
                            currentIndex: root.pageIndex(root.boundWorkbench.currentPage)

                            HomePage {
                                id: homePage
                                objectName: "homePage"
                                theme: prism
                                workbench: root.boundWorkbench
                                startPreludePending: root.startPreludePending
                                transitionSerial: root.pageTransitionSequence
                                pageMotionEnabled: root.pageMotionEnabled
                                onLiveToggleRequested: root.requestLiveToggle()
                                onSaveRequested: {
                                    root.boundWorkbench.saveAll()
                                    root.pulseVisualAction("calibrate")
                                }
                            }
                            CapturePage {
                                objectName: "capturePage"
                                theme: prism
                                workbench: root.boundWorkbench
                                transitionSerial: root.pageTransitionSequence
                                pageMotionEnabled: root.pageMotionEnabled
                                onVisualAction: action => root.pulseVisualAction(action)
                            }
                            OcrPage {
                                objectName: "ocrPage"
                                theme: prism
                                workbench: root.boundWorkbench
                                transitionSerial: root.pageTransitionSequence
                                pageMotionEnabled: root.pageMotionEnabled
                                onVisualAction: action => root.pulseVisualAction(action)
                            }
                            TranslationPage {
                                objectName: "translationPage"
                                theme: prism
                                workbench: root.boundWorkbench
                                transitionSerial: root.pageTransitionSequence
                                pageMotionEnabled: root.pageMotionEnabled
                                onVisualAction: action => root.pulseVisualAction(action)
                            }
                            OverlayPage {
                                objectName: "overlayPage"
                                theme: prism
                                workbench: root.boundWorkbench
                                transitionSerial: root.pageTransitionSequence
                                pageMotionEnabled: root.pageMotionEnabled
                                onVisualAction: action => root.pulseVisualAction(action)
                            }
                            CachePage {
                                objectName: "cachePage"
                                theme: prism
                                workbench: root.boundWorkbench
                                transitionSerial: root.pageTransitionSequence
                                pageMotionEnabled: root.pageMotionEnabled
                                onVisualAction: action => root.pulseVisualAction(action)
                            }
                            SettingsPage {
                                objectName: "settingsPage"
                                theme: prism
                                workbench: root.boundWorkbench
                                transitionSerial: root.pageTransitionSequence
                                pageMotionEnabled: root.pageMotionEnabled
                                onVisualAction: action => root.pulseVisualAction(action)
                            }
                        }
                    }

                    Rectangle {
                        id: tertiaryRail
                        objectName: "pageTertiaryRail"
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        height: prism.dohna ? 3 : 1
                        color: prism.dohna ? prism.spectrum : prism.line
                        opacity: prism.tertiaryRailOpacity
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    visible: !root.fullCanvasHome
                    Layout.preferredHeight: prism.refraStyle ? 64 : 34
                    color: prism.dohna ? prism.ink : prism.navigationSurface
                    border.color: prism.line

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 18
                        anchors.rightMargin: 18
                        spacing: 10
                        Rectangle {
                            Layout.preferredWidth: 6
                            Layout.preferredHeight: 6
                            radius: 3
                            color: root.boundWorkbench.statusTone === "error" ? prism.danger
                                 : root.boundWorkbench.statusTone === "warning" ? prism.amber
                                 : root.boundWorkbench.statusTone === "success" ? prism.accent
                                 : prism.textDim
                        }
                        Text {
                            text: root.boundWorkbench.statusText
                            color: prism.navigationText
                            font.family: prism.uiFontFor(text)
                            font.pixelSize: 12
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                        Text {
                            text: root.boundWorkbench.runPhase.toUpperCase()
                            visible: !prism.refraStyle
                            color: root.boundWorkbench.running ? prism.accentText : prism.navigationTextDim
                            font.family: prism.monoFontFor(text)
                            font.pixelSize: 12
                            font.letterSpacing: 1
                        }
                        Text {
                            visible: prism.refraStyle && root.boundWorkbench.settingsDirty
                            text: "● 有未应用更改"
                            color: prism.amber
                            font.family: prism.uiFontFor(text)
                            font.pixelSize: 12
                        }
                        Item { visible: prism.refraStyle; Layout.fillWidth: true }
                        Item {
                            id: innerStartActionSlot
                            objectName: "darkStartActionSlot"
                            visible: prism.refraStyle
                            Layout.preferredWidth: 194
                            Layout.preferredHeight: 48
                        }
                        Item {
                            id: innerApplyActionSlot
                            objectName: "darkApplyActionSlot"
                            visible: prism.refraStyle
                            Layout.preferredWidth: 128
                            Layout.preferredHeight: 48
                        }
                    }
                }
            }

            PrismFeedbackLayer {
                objectName: "prismFeedbackLayer"
                anchors.fill: parent
                theme: prism
                startProgress: stage.startProgress
                startRunning: stage.startPreludeRunning
                actionProgress: stage.actionProgress
                actionRunning: stage.actionPulseRunning
                actionKind: stage.actionKind
                warningProgress: stage.warningProgress
                warningRunning: stage.warningPulseRunning
                reducedMotion: root.reduceMotion
            }

            DohnaFeedbackLayer {
                id: dohnaFeedback
                objectName: "dohnaFeedbackLayer"
                anchors.fill: parent
                theme: prism
                reducedMotion: root.reduceMotion
                motionEnabled: root.animationsRunning
            }
        }
    }

    Item {
        id: sharedNavigationOverlay
        objectName: "sharedNavigationOverlay"
        anchors.fill: parent
        visible: prism.refraStyle
        z: 20

        Repeater {
            id: sharedNavigationRepeater
            model: root.pageOrder

            PrismNavigationMotion {
                required property int index
                required property var modelData
                motionObjectName: "prismNavigationMotion" + index
                // Keep the hidden Prism overlay out of Dohna's object-name
                // namespace. Dohna's visible legacy buttons retain their
                // original navigationButtonN names and remain the sole
                // controls returned by QML lookup.
                buttonObjectName: !prism.refraStyle ? ""
                                  : root.fullCanvasHome
                                    ? "refraDarkNavigationButton" + index
                                    : "navigationButton" + index
                theme: prism
                positionMotionEnabled: root.navigationMotionEnabled
                targetX: root.navigationTargetBounds(index, root.navigationGeometryRevision).x
                targetY: root.navigationTargetBounds(index, root.navigationGeometryRevision).y
                targetWidth: root.navigationTargetBounds(index, root.navigationGeometryRevision).width
                targetHeight: root.navigationTargetBounds(index, root.navigationGeometryRevision).height
                targetPresentation: root.navigationTargetIsHero ? 1 : 0
                targetTilt: root.navigationTargetIsHero
                             ? (index % 2 === 0 ? -3.8 : -5.7)
                             : (index % 2 === 0 ? -4 : -6.2)
                slashVisible: [0, 1, 3, 5].indexOf(index) >= 0
                number: String(index + 1).padStart(2, "0")
                code: root.pageCode(String(modelData))
                subtitle: root.navigationLabel(String(modelData))
                cool: index % 2 === 1
                heroFontSize: Math.max(
                    58,
                    Math.min(70, (root.width * 0.55 - 122) / 8.2)
                )
                text: root.navigationMenuTitle(String(modelData))
                selected: root.boundWorkbench.currentPage === modelData
                z: selected ? 2 : 1
                onClicked: root.boundWorkbench.setPage(String(modelData))
            }
        }
    }

    Item {
        id: sharedActionOverlay
        objectName: "sharedActionOverlay"
        anchors.fill: parent
        visible: prism.refraStyle
        z: 21

        Repeater {
            model: [0, 1]

            PrismP3ActionMotion {
                required property int index
                actionObjectName: "prismActionMotion" + index
                buttonObjectName: !prism.refraStyle ? ""
                                  : root.fullCanvasHome
                                    ? (index === 0 ? "refraDarkStartButton" : "refraDarkApplyButton")
                                    : (index === 0 ? "darkStartLiveButton" : "darkSaveAllButton")
                theme: prism
                positionMotionEnabled: root.navigationMotionEnabled
                targetX: root.actionTargetBounds(index, root.navigationGeometryRevision).x
                targetY: root.actionTargetBounds(index, root.navigationGeometryRevision).y
                targetWidth: root.actionTargetBounds(index, root.navigationGeometryRevision).width
                targetHeight: root.actionTargetBounds(index, root.navigationGeometryRevision).height
                primary: index === 0
                text: index === 0
                      ? (root.startPreludePending ? "正在启动…" : root.boundWorkbench.startButtonText)
                      : "应用更改"
                enabled: index === 0
                         ? (root.boundWorkbench.runPhase !== "stopping"
                            && !root.startPreludePending
                            && (root.boundWorkbench.canStart || root.boundWorkbench.running))
                         : root.boundWorkbench.hasProfile
                z: index
                onClicked: {
                    if (index === 0) {
                        root.requestLiveToggle()
                    } else {
                        root.boundWorkbench.saveAll()
                        if (root.boundWorkbench.currentPage === "HOME"
                                || root.boundWorkbench.currentPage === "SETTINGS")
                            root.pulseVisualAction("calibrate")
                    }
                }
            }
        }
    }

    // mapToItem() inside the target helpers is not a declarative dependency on
    // Layout geometry. Refresh once per event-loop turn when either real slot
    // or the page-content host is repolished, so initial and resized endpoints
    // use their final coordinates without polling or an arbitrary delay.
    Connections {
        target: pageContentHost
        function onXChanged() { root.scheduleNavigationTargetRefresh() }
        function onYChanged() { root.scheduleNavigationTargetRefresh() }
        function onWidthChanged() { root.scheduleNavigationTargetRefresh() }
        function onHeightChanged() { root.scheduleNavigationTargetRefresh() }
    }
    Connections {
        target: homePage.p3StartActionSlot
        function onXChanged() { root.scheduleNavigationTargetRefresh() }
        function onYChanged() { root.scheduleNavigationTargetRefresh() }
        function onWidthChanged() { root.scheduleNavigationTargetRefresh() }
        function onHeightChanged() { root.scheduleNavigationTargetRefresh() }
    }
    Connections {
        target: homePage.p3ApplyActionSlot
        function onXChanged() { root.scheduleNavigationTargetRefresh() }
        function onYChanged() { root.scheduleNavigationTargetRefresh() }
        function onWidthChanged() { root.scheduleNavigationTargetRefresh() }
        function onHeightChanged() { root.scheduleNavigationTargetRefresh() }
    }
    Connections {
        target: innerStartActionSlot
        function onXChanged() { root.scheduleNavigationTargetRefresh() }
        function onYChanged() { root.scheduleNavigationTargetRefresh() }
        function onWidthChanged() { root.scheduleNavigationTargetRefresh() }
        function onHeightChanged() { root.scheduleNavigationTargetRefresh() }
    }
    Connections {
        target: innerApplyActionSlot
        function onXChanged() { root.scheduleNavigationTargetRefresh() }
        function onYChanged() { root.scheduleNavigationTargetRefresh() }
        function onWidthChanged() { root.scheduleNavigationTargetRefresh() }
        function onHeightChanged() { root.scheduleNavigationTargetRefresh() }
    }

    SequentialAnimation {
        id: dohnaPageTransitionAnimation
        ParallelAnimation {
            NumberAnimation {
                target: pageContentTranslate
                property: "x"
                to: 0
                duration: prism.dohnaPageMotion
                easing.type: Easing.OutCubic
            }
            SequentialAnimation {
                PauseAnimation { duration: prism.dohnaTitleDelay }
                NumberAnimation {
                    target: pageHeaderTranslate
                    property: "x"
                    to: 0
                    duration: prism.dohnaTitleMotion
                    easing.type: Easing.OutCubic
                }
            }
        }
        ScriptAction { script: root.settlePageTransition() }
    }

    SequentialAnimation {
        id: pageTransitionAnimation
        ScriptAction {
            script: {
                root.pageContentReady = true
                pageContentMotion.opacity = 1
            }
        }
        ParallelAnimation {
            ParallelAnimation {
                NumberAnimation { target: pageHeaderTranslate; property: "x"; to: 0; duration: prism.pageSecondaryMotion; easing.type: Easing.OutQuart }
                NumberAnimation { target: pageHeaderSlice; property: "opacity"; to: 1; duration: prism.pageSecondaryMotion; easing.type: Easing.OutQuart }
                NumberAnimation { target: pageContentTranslate; property: "x"; to: 0; duration: prism.pageMotion; easing.type: Easing.OutQuart }
            }
            SequentialAnimation {
                PropertyAction { target: tertiaryRail; property: "opacity"; value: 0 }
                NumberAnimation { target: tertiaryRail; property: "opacity"; to: prism.tertiaryRailOpacity; duration: prism.pageTertiaryMotion; easing.type: Easing.OutCubic }
            }
        }
        ScriptAction { script: root.settlePageTransition() }
    }
}
