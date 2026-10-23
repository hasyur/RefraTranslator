pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Window
import "components"
import "pages"

Item {
    id: root
    required property var appShell
    readonly property bool skinPresented: appShell.visible && appShell.activeSkin === root
    readonly property real minimumWorkbenchWidth: 980
    objectName: prism.active ? "prismWorkbenchView" : ""


    // The sole context property is intentionally injected by QmlWorkbenchHost.
    // qmllint disable unqualified
    readonly property var boundWorkbench: workbench
    // qmllint enable unqualified
    readonly property var pageOrder: ["HOME", "CAPTURE", "OCR", "TRANSLATION", "OVERLAY", "CACHE", "SETTINGS"]
    readonly property bool animationsRunning: root.skinPresented
                                              && !boundWorkbench.reducedMotion
    property bool pageContentReady: true
    readonly property bool pageMotionEnabled: animationsRunning && pageContentReady
    readonly property string visualPage: boundWorkbench.currentPage
    readonly property bool reduceMotion: boundWorkbench.reducedMotion
    readonly property bool fullCanvasHome: boundWorkbench.currentPage === "HOME"
    property bool navigationMotionArmed: false
    property bool navigationResizeActive: false
    property bool navigationTargetIsHero: false
    property int navigationGeometryRevision: 0
    readonly property bool navigationMotionEnabled: root.skinPresented
                                                   && navigationMotionArmed
                                                   && !navigationResizeActive
                                                   && !reduceMotion
    property string lastAnimatedPage: ""
    readonly property bool pageTransitioning: animationsRunning
                                              && pageTransitionAnimation.running
    property int pageTransitionSequence: 0
    readonly property bool startPreludePending: root.appShell.startPreludePending

    function navigationTargetSlot(index) {
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
                root,
                Qt.point(pageContentMotion.x, pageContentMotion.y)
            )
            point = Qt.point(contentOrigin.x + slotLocal.x, contentOrigin.y + slotLocal.y)
        } else {
            point = slot.mapToItem(root, Qt.point(0, 0))
        }
        return {
            x: point.x,
            y: point.y,
            width: slot.width,
            height: slot.height
        }
    }

    function actionTargetSlot(index) {
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
                root,
                Qt.point(pageContentMotion.x, pageContentMotion.y)
            )
            point = Qt.point(contentOrigin.x + slotLocal.x, contentOrigin.y + slotLocal.y)
        } else {
            point = slot.mapToItem(root, Qt.point(0, 0))
        }
        return { x: point.x, y: point.y, width: slot.width, height: slot.height }
    }

    function scheduleNavigationTargetRefresh() {
        
        navigationTargetRefresh.restart()
    }

    function refreshNavigationTargets() {
        navigationTargetIsHero = fullCanvasHome
        navigationGeometryRevision += 1
        if (root.skinPresented)
            navigationMotionArmed = true
    }

    function markWindowResize() {
        if (!root.skinPresented || !true)
            return
        navigationResizeActive = true
        navigationResizeSettle.restart()
        navigationTargetRefresh.restart()
    }

    onWidthChanged: markWindowResize()
    onHeightChanged: markWindowResize()



    function pageIndex(page) {
        const index = pageOrder.indexOf(page)
        return index < 0 ? 0 : index
    }

    function pageTitle(page) {
        return pageTitleLight(page) + pageTitleHeavy(page)
    }

    function pageTitleLight(page) {
        const titles = {
            "HOME": "HOME",
            "CAPTURE": "CAPTURE",
            "OCR": "OCR",
            "TRANSLATION": "TRANSLATE",
            "OVERLAY": "OVERLAY",
            "CACHE": "CACHE",
            "SETTINGS": "SETTINGS"
        }
        return titles[page] || page
    }

    function pageTitleHeavy(page) {
        return pageTitleLightChinese(page)
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

    function settlePageTransition() {
        pageContentReady = true
        pageContentTranslate.x = 0
        pageContentMotion.opacity = 1
        pageHeaderTranslate.x = 0
        pageHeaderSlice.opacity = 1
        tertiaryRail.opacity = prism.tertiaryRailOpacity
    }

    readonly property int startPreludeMotion: prism.startPreludeMotion

    function showError(title, message) {
        errorDialog.errorTitle = title
        errorDialog.errorMessage = message
        pulseVisualWarning()
        errorDialog.open()
    }

    function pulseVisualAction(action) {
        stage.pulseAction(action)
    }

    function pulseVisualWarning() {
        stage.pulseWarning()
    }

    function pulseVisualStart() {
        stage.pulseStart()
    }

    function beginPageTransition() {
        if (visualPage === lastAnimatedPage)
            return
        lastAnimatedPage = visualPage
        pageTransitionSequence += 1
        if (reduceMotion || !visible) {
            pageTransitionAnimation.stop()
            pageContentReady = true
            settlePageTransition()
            return
        }
        
        pageContentReady = false
        pageContentMotion.opacity = 0
        pageContentTranslate.x = 8
        pageHeaderSlice.opacity = 0
        pageHeaderTranslate.x = 14
        pageTransitionAnimation.restart()
    }





    function settleReducedMotion() {
        pageTransitionAnimation.stop()
        pageContentReady = true
        settlePageTransition()
        stage.settleMotion()
        if (startPreludePending)
            root.appShell.completeStartPrelude()
    }

    onVisualPageChanged: {
        beginPageTransition()
        scheduleNavigationTargetRefresh()
    }
    onReduceMotionChanged: {
        if (reduceMotion)
            settleReducedMotion()
    }
    onSkinPresentedChanged: {
        if (root.skinPresented) {
            lastAnimatedPage = ""
            beginPageTransition()
            navigationMotionArmed = false
            scheduleNavigationTargetRefresh()
        } else {
            navigationMotionArmed = false
            navigationResizeActive = false
            pageTransitionAnimation.stop()
            pageContentReady = true
            settlePageTransition()
        }
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
        objectName: active ? "prismTheme" : ""
        active: root.appShell.activeSkin === root
        dark: root.boundWorkbench.effectiveTheme !== "light"
        reducedMotion: root.boundWorkbench.reducedMotion
    }

    Item {
        objectName: prism.active ? ("skinBackground") : ""
        anchors.fill: parent
        z: -1
        Rectangle {
            anchors.fill: parent
            gradient: Gradient {
                GradientStop { position: 0; color: prism.backgroundTop }
                GradientStop { position: 0.62; color: prism.paper }
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
        objectName: prism.active ? ("errorDialog") : ""
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



    RowLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            id: navigationRail
            implicitWidth: Math.max(168, Math.min(230, root.width * 0.18))
                         
            Layout.preferredWidth: implicitWidth
            Layout.fillHeight: true
            visible: !root.fullCanvasHome
            color: prism.navigationSurface
            border.color: prism.line
            clip: false

            Rectangle {
                objectName: prism.active ? ("refraDarkSidebarFacet") : ""
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
                objectName: prism.active ? ("refraDarkSidebarLight") : ""
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
                anchors.margins: 12
                                
                spacing: 6 
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: 12 
                    spacing: 0
                    Text {
                        objectName: prism.active ? ("refraBrandWordmark") : ""
                        text: (prism.refraLight ? "<font color='#075bff'>Refra</font>Translator"
                                                  : "<font color='#00d9ff'>Refra</font>Translator")
                              
                        textFormat: Text.RichText 
                        color: prism.navigationText
                        font.family: "Arial Black" 
                        font.pixelSize: (root.width < 1100 ? 17 : 22) 
                        font.weight: Font.Black 
                        font.letterSpacing: 0 
                        fontSizeMode: Text.HorizontalFit 
                        minimumPixelSize: 14 
                        Layout.fillWidth: true
                        elide: Text.ElideNone }
                    Text {
                        text: "GAME SCREEN TRANSLATOR" 
                        color: prism.accentText
                        font.family: prism.monoFontFor(text)
                        font.pixelSize: 10 
                        font.letterSpacing: 0.8 
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.topMargin: 8
                    Layout.bottomMargin: 5
                    Layout.preferredHeight: 2 
                    color: prism.electric 
                    opacity: 0.8 }

                Repeater {
                    id: navigationRepeater
                    model: root.pageOrder
                    Item {
                        objectName: prism.active ? ("navigationSlot" + index) : ""
                        readonly property Item p3Slot: p3NavigationSlot
                        required property int index
                        required property var modelData
                        implicitWidth: 150
                        implicitHeight: 66 
                        Layout.fillWidth: true
                        Layout.minimumWidth: -1
                        Layout.preferredHeight: implicitHeight
                        // Overscan the rotated bar; the sidebar clips both ends
                        // flush, while the enlarged control remains clickable.
                        Layout.leftMargin: 0
                        Layout.rightMargin: Layout.leftMargin
                        Layout.maximumWidth: Number.POSITIVE_INFINITY
                        // Preserve the visible gap of the original 50 px strips
                        // when their thickness changes under the same rotation.
                        Layout.bottomMargin: 0

                        Item {
                            id: p3NavigationSlot
                            objectName: prism.active ? ("navigationSlotGeometry" + index) : ""
                            anchors.fill: parent
                            visible: true
                        }


                    }
                }

                Item { Layout.fillHeight: true }




            }
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true



            PrismMotionFeedback {
                id: stage
                objectName: prism.active ? ("prismMotionFeedback") : ""
                theme: prism
                pageTransitionSequence: root.pageTransitionSequence
                reducedMotion: root.boundWorkbench.reducedMotion
                motionEnabled: root.animationsRunning && !false
            }

            ColumnLayout {
                anchors.fill: parent
                spacing: 0

                Rectangle {
                    objectName: prism.active ? ("pageHeaderBar") : ""
                    clip: false || true
                    Layout.fillWidth: true
                    visible: !root.fullCanvasHome
                    Layout.preferredHeight: Math.max(
                        root.fullCanvasHome ? 0
                        : (root.height <= 820 ? 148 : 164)
                        ,
                        pageHeaderTextColumn.implicitHeight + 16
                    )
                    color: prism.headerSurface
                    border.color: prism.line

                    Rectangle {
                        objectName: prism.active ? ("refraDarkHeaderFacet") : ""
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
                        objectName: prism.active ? ("refraDarkHeaderLight") : ""
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

                            Item {
                                id: pageHeaderSlice
                                objectName: prism.active ? ("pageHeaderSlice") : ""
                                readonly property real titleSize: prism.displayTitleSize(root.width)
                                Layout.fillWidth: true
                                Layout.preferredHeight: Math.ceil(Math.max(
                                    refraEnglishPageTitle.implicitHeight,
                                    refraChinesePageTitle.implicitHeight
                                ) + 10)
                                Layout.minimumHeight: Layout.preferredHeight
                                clip: false
                                TextMetrics {
                                    id: refraEnglishTitleMetrics
                                    objectName: prism.active ? ("refraEnglishTitleMetrics") : ""
                                    font: refraEnglishPageTitle.font
                                    text: refraEnglishPageTitle.text
                                }
                                transform: Translate {
                                    id: pageHeaderTranslate
                                    objectName: prism.active ? ("pageHeaderTranslate") : ""
                                }


                                Text {
                                    id: refraEnglishPageTitle
                                    objectName: prism.active ? ("refraEnglishPageTitle") : ""
                                    visible: true
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
                                    objectName: prism.active ? ("refraChinesePageTitle") : ""
                                    visible: true
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
                                    objectName: prism.active ? ("refraHeaderPrism") : ""
                                    visible: true
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
                                    objectName: prism.active ? ("prismPageHeaderRule") : ""
                                    visible: !false
                                    theme: prism
                                    width: Math.min(parent.width * 0.72, 420)
                                    anchors.left: parent.left
                                    anchors.bottom: parent.bottom
                                }

                            }

                        }


                        ColumnLayout {
                            visible: true
                            Layout.maximumWidth: 170
                            spacing: 2
                            Text {
                                text: "当前配置"
                                color: prism.textDim
                                font.family: prism.monoFontFor(text)
                                font.pixelSize: 11
                            }
                            Text {
                                objectName: prism.active ? ("darkHeaderProfileName") : ""
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
                        objectName: prism.active ? ("pageContentMotion") : ""
                        anchors.fill: parent
                        transform: Translate {
                            id: pageContentTranslate
                            objectName: prism.active ? ("pageContentTranslate") : ""
                        }

                        StackLayout {
                            objectName: prism.active ? ("pageStack") : ""
                            anchors.fill: parent
                            anchors.margins: root.fullCanvasHome ? 0
                                              : (root.width < 1100 ? 10 : 14)
                                              
                            currentIndex: root.pageIndex(root.boundWorkbench.currentPage)

                            HomePage {
                                id: homePage
                                objectName: prism.active ? ("homePage") : ""
                                theme: prism
                                appShell: root.appShell
                                workbench: root.boundWorkbench
                                skinPresented: root.skinPresented
                                startPreludePending: root.startPreludePending
                                transitionSerial: root.pageTransitionSequence
                                pageMotionEnabled: root.pageMotionEnabled
                                onLiveToggleRequested: root.appShell.requestLiveToggle()
                                onSaveRequested: {
                                    root.boundWorkbench.saveAll()
                                    root.pulseVisualAction("calibrate")
                                }
                            }
                            CapturePage {
                                id: capturePage
                                objectName: prism.active ? ("capturePage") : ""
                                theme: prism
                                appShell: root.appShell
                                workbench: root.boundWorkbench
                                transitionSerial: root.pageTransitionSequence
                                pageMotionEnabled: root.pageMotionEnabled
                                onVisualAction: action => root.pulseVisualAction(action)
                            }
                            OcrPage {
                                id: ocrPage
                                objectName: prism.active ? ("ocrPage") : ""
                                theme: prism
                                appShell: root.appShell
                                workbench: root.boundWorkbench
                                transitionSerial: root.pageTransitionSequence
                                pageMotionEnabled: root.pageMotionEnabled
                                onVisualAction: action => root.pulseVisualAction(action)
                            }
                            TranslationPage {
                                id: translationPage
                                objectName: prism.active ? ("translationPage") : ""
                                theme: prism
                                appShell: root.appShell
                                workbench: root.boundWorkbench
                                transitionSerial: root.pageTransitionSequence
                                pageMotionEnabled: root.pageMotionEnabled
                                onVisualAction: action => root.pulseVisualAction(action)
                            }
                            OverlayPage {
                                objectName: prism.active ? ("overlayPage") : ""
                                theme: prism
                                appShell: root.appShell
                                workbench: root.boundWorkbench
                                transitionSerial: root.pageTransitionSequence
                                pageMotionEnabled: root.pageMotionEnabled
                                onVisualAction: action => root.pulseVisualAction(action)
                            }
                            CachePage {
                                objectName: prism.active ? ("cachePage") : ""
                                theme: prism
                                appShell: root.appShell
                                workbench: root.boundWorkbench
                                transitionSerial: root.pageTransitionSequence
                                pageMotionEnabled: root.pageMotionEnabled
                                onVisualAction: action => root.pulseVisualAction(action)
                            }
                            SettingsPage {
                                id: settingsPage
                                objectName: prism.active ? ("settingsPage") : ""
                                theme: prism
                                appShell: root.appShell
                                workbench: root.boundWorkbench
                                transitionSerial: root.pageTransitionSequence
                                pageMotionEnabled: root.pageMotionEnabled
                                onVisualAction: action => root.pulseVisualAction(action)
                            }
                        }
                    }

                    Rectangle {
                        id: tertiaryRail
                        objectName: prism.active ? ("pageTertiaryRail") : ""
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        height: 1
                        color: prism.line
                        opacity: prism.tertiaryRailOpacity
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    visible: !root.fullCanvasHome
                    Layout.preferredHeight: 64 
                    color: prism.navigationSurface
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
                            visible: true && root.boundWorkbench.settingsDirty
                            text: "● 有未应用更改"
                            color: prism.amber
                            font.family: prism.uiFontFor(text)
                            font.pixelSize: 12
                        }
                        Item { visible: true; Layout.fillWidth: true }
                        Item {
                            id: innerStartActionSlot
                            objectName: prism.active ? ("darkStartActionSlot") : ""
                            visible: true
                            Layout.preferredWidth: 194
                            Layout.preferredHeight: 48
                        }
                        Item {
                            id: innerApplyActionSlot
                            objectName: prism.active ? ("darkApplyActionSlot") : ""
                            visible: true
                            Layout.preferredWidth: 128
                            Layout.preferredHeight: 48
                        }
                    }
                }
            }

            PrismFeedbackLayer {
                objectName: prism.active ? ("prismFeedbackLayer") : ""
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

        }
    }

    Item {
        id: sharedNavigationOverlay
        objectName: prism.active ? ("sharedNavigationOverlay") : ""
        anchors.fill: parent
        visible: true
        z: 20

        Repeater {
            id: sharedNavigationRepeater
            model: root.pageOrder

            PrismNavigationMotion {
                required property int index
                required property var modelData
                motionObjectName: "prismNavigationMotion" + index
                // Keep the motion overlay's buttons distinct from the static
                // controls used when the page is not HOME.
                buttonObjectName: root.fullCanvasHome
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
        objectName: prism.active ? ("sharedActionOverlay") : ""
        anchors.fill: parent
        visible: true
        z: 21

        Repeater {
            model: [0, 1]

            PrismP3ActionMotion {
                required property int index
                actionObjectName: "prismActionMotion" + index
                buttonObjectName: root.fullCanvasHome
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
                        root.appShell.requestLiveToggle()
                    } else {
                        root.appShell.saveAll()
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
