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
    readonly property real minimumWorkbenchWidth: navigationRail.implicitWidth + 802
    objectName: prism.active ? "dohnaWorkbenchView" : ""


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
    property string lastAnimatedPage: ""
    readonly property bool pageTransitioning: animationsRunning
                                              && dohnaPageTransitionAnimation.running
    property int pageTransitionSequence: 0
    readonly property bool startPreludePending: root.appShell.startPreludePending

    function pageIndex(page) {
        const index = pageOrder.indexOf(page)
        return index < 0 ? 0 : index
    }

    function pageTitle(page) {
        return pageTitleLight(page) + pageTitleHeavy(page)
    }

    function pageTitleLight(page) {
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

    function pageTitleHeavy(page) {
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

    function navigationLabel(page) {
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

    readonly property int startPreludeMotion: prism.startPreludeMotion

    function showError(title, message) {
        errorDialog.errorTitle = title
        errorDialog.errorMessage = message
        pulseVisualWarning()
        errorDialog.open()
    }

    function pulseVisualAction(action) {
        dohnaFeedback.pulseAction(action)
    }

    function pulseVisualWarning() {
        dohnaFeedback.pulseWarning()
    }

    function pulseVisualStart() {
        dohnaFeedback.pulseStart()
    }

    function beginPageTransition() {
        if (visualPage === lastAnimatedPage)
            return
        lastAnimatedPage = visualPage
        pageTransitionSequence += 1
        if (reduceMotion || !visible) {
            dohnaPageTransitionAnimation.stop()
            pageContentReady = true
            settlePageTransition()
            return
        }

        pageContentReady = true
        pageContentMotion.opacity = 1
        pageContentTranslate.x = Math.max(54, Math.min(132, root.width * 0.12))
        pageHeaderSlice.opacity = 1
        pageHeaderTranslate.x = -Math.max(28, Math.min(72, root.width * 0.055))
        dohnaPageTransitionAnimation.restart()
    }





    function settleReducedMotion() {
        dohnaPageTransitionAnimation.stop()
        pageContentReady = true
        settlePageTransition()
        dohnaFeedback.settle()
        if (startPreludePending)
            root.appShell.completeStartPrelude()
    }

    onVisualPageChanged: {
        beginPageTransition()
    }
    onReduceMotionChanged: {
        if (reduceMotion)
            settleReducedMotion()
    }
    onSkinPresentedChanged: {
        if (root.skinPresented) {
            lastAnimatedPage = ""
            beginPageTransition()
        } else {
            dohnaPageTransitionAnimation.stop()
            pageContentReady = true
            settlePageTransition()
        }
    }

    DohnaTheme {
        id: prism
        objectName: active ? "dohnaTheme" : ""
        active: root.appShell.activeSkin === root
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
                GradientStop { position: 0.62; color: prism.inkRaised }
                GradientStop { position: 1; color: prism.backgroundBottom }
            }
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
            implicitWidth: Math.ceil(dohnaNavigationText.width + 40)
                         
            Layout.preferredWidth: implicitWidth
            Layout.fillHeight: true
            visible: true
            color: prism.navigationSurface
            border.color: prism.line
            clip: true





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
                anchors.margins: (root.width < 1100 ? 14 : 20)
                                
                spacing: 10

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: 7
                    spacing: 0
                    Text {
                        objectName: prism.active ? ("refraBrandWordmark") : ""
                        text: "REFRA"
                        textFormat: Text.PlainText
                        color: prism.navigationText
                        font.family: prism.displayFontFor(text)
                        font.pixelSize: 23
                        font.weight: Font.Bold
                        font.letterSpacing: 4
                        fontSizeMode: Text.FixedSize
                        minimumPixelSize: 1
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                    }
                    Text {
                        text: "TRANSLATOR / WORKBENCH"
                        color: prism.accentText
                        font.family: prism.monoFontFor(text)
                        font.pixelSize: 12
                        font.letterSpacing: 1.1
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.topMargin: 8
                    Layout.bottomMargin: 5
                    Layout.preferredHeight: 1
                    color: prism.lineStrong
                    opacity: 1
                }

                Repeater {
                    id: navigationRepeater
                    model: root.pageOrder
                    Item {
                        objectName: prism.active ? ("navigationSlot" + index) : ""
                        required property int index
                        required property var modelData
                        implicitWidth: 150
                        implicitHeight: Math.ceil(dohnaNavigationText.tightBoundingRect.height / 0.85)
                                        
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0 
                        Layout.preferredHeight: implicitHeight
                        // Overscan the rotated bar; the sidebar clips both ends
                        // flush, while the enlarged control remains clickable.
                        Layout.leftMargin: -navigationLayout.anchors.margins - 16 
                        Layout.rightMargin: Layout.leftMargin
                        Layout.maximumWidth: navigationRail.width + 32 
                        PrismButton {
                            objectName: prism.active ? ( "navigationButton" + index) : ""
                            anchors.fill: parent
                            theme: prism
                            navigation: true
                            text: String(modelData) + "  " + root.navigationLabel(String(modelData))
                                  
                            primary: root.boundWorkbench.currentPage === modelData
                            quiet: root.boundWorkbench.currentPage !== modelData
                            visible: !false
                            onClicked: root.boundWorkbench.setPage(String(modelData))
                        }
                    }
                }

                Item { Layout.fillHeight: true }

                Rectangle {
                    objectName: prism.active ? ("activeProfileCard") : ""
                    visible: !false
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
                            objectName: prism.active ? ("activeProfileName") : ""
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


            }
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            DohnaBackdrop {
                id: dohnaBackdrop
                objectName: prism.active ? ("dohnaBackdrop") : ""
                anchors.fill: parent
                anchors.margins: 12
                theme: prism
                visible: true
            }

            ColumnLayout {
                anchors.fill: parent
                spacing: 0

                Rectangle {
                    objectName: prism.active ? ("pageHeaderBar") : ""
                    clip: true
                    Layout.fillWidth: true
                    visible: true
                    Layout.preferredHeight: Math.max(
                        root.height <= 820 ? 116 : 142,
                        pageHeaderTextColumn.implicitHeight + 16
                    )
                    color: prism.headerSurface
                    border.color: prism.line




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
                                visible: !false
                                text: String(root.pageIndex(root.boundWorkbench.currentPage) + 1).padStart(2, "0")
                                      + " / " + ( root.boundWorkbench.currentPage
                                                  )
                                color: prism.accentText
                                font.family: prism.monoFontFor(text)
                                font.pixelSize: 12
                                font.letterSpacing: 1.8
                            }
                            Item {
                                id: pageHeaderSlice
                                objectName: prism.active ? ("pageHeaderSlice") : ""
                                readonly property real titleSize: prism.displayTitleSize(root.width)
                                Layout.fillWidth: true
                                Layout.preferredHeight: displayTitleGroup.implicitHeight
                                Layout.minimumHeight: displayTitleGroup.implicitHeight
                                clip: false
                                transform: Translate {
                                    id: pageHeaderTranslate
                                    objectName: prism.active ? ("pageHeaderTranslate") : ""
                                }

                                RefractedTitle {
                                    id: displayTitleGroup
                                    objectName: prism.active ? ("pageDisplayTitle") : ""
                                    anchors.fill: parent
                                    visible: !false
                                    theme: prism
                                    lightText: root.pageTitleLight(root.boundWorkbench.currentPage)
                                    heavyText: root.pageTitleHeavy(root.boundWorkbench.currentPage)
                                    titleSize: pageHeaderSlice.titleSize
                                    transitionSequence: root.pageTransitionSequence
                                    motionEnabled: root.pageMotionEnabled
                                }




                                Rectangle {
                                    objectName: prism.active ? ("pageHeaderUnderline") : ""
                                    visible: true
                                    width: Math.min(parent.width * 0.72, 420)
                                    height: 5 
                                    anchors.left: parent.left
                                    anchors.bottom: parent.bottom
                                    color: prism.violet 
                                    opacity: 1 
                                    rotation: -1.8 
                                    antialiasing: true
                                }
                            }
                            Text {
                                objectName: prism.active ? ("pageSubtitle") : ""
                                text: root.pageSubtitle(root.boundWorkbench.currentPage)
                                visible: !false
                                color: prism.textSoft
                                font.family: prism.uiFontFor(text)
                                font.pixelSize: 13
                                Layout.topMargin: 10 }
                        }

                        Text {
                            visible: root.boundWorkbench.settingsDirty
                                     && !false
                            text: "● 未应用"
                            color: prism.amber
                            font.family: prism.monoFontFor(text)
                            font.pixelSize: 12
                        }
                        PrismButton {
                            objectName: prism.active ? ("saveAllButton") : ""
                            theme: prism
                            text: "应用更改"
                            visible: !false
                            enabled: root.boundWorkbench.hasProfile
                            onClicked: {
                                root.boundWorkbench.saveAll()
                                if (root.boundWorkbench.currentPage === "SETTINGS")
                                    root.pulseVisualAction("calibrate")
                            }
                        }
                        PrismButton {
                            objectName: prism.active ? ("startLiveButton") : ""
                            theme: prism
                            primary: true
                            visible: !false
                            text: root.startPreludePending
                                  ? ( "正在点亮光路…" )
                                  : root.boundWorkbench.startButtonText
                            enabled: root.boundWorkbench.runPhase !== "stopping"
                                     && !root.startPreludePending
                                     && (root.boundWorkbench.canStart || root.boundWorkbench.running)
                            onClicked: root.appShell.requestLiveToggle()
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
                            anchors.margins: root.width < 1100 ? 14 : 18
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
                        height: 3 
                        color: prism.spectrum 
                        opacity: prism.tertiaryRailOpacity
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    visible: true
                    Layout.preferredHeight: 34
                    color: prism.ink 
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
                            visible: !false
                            color: root.boundWorkbench.running ? prism.accentText : prism.navigationTextDim
                            font.family: prism.monoFontFor(text)
                            font.pixelSize: 12
                            font.letterSpacing: 1
                        }

                        Item { visible: false; Layout.fillWidth: true }


                    }
                }
            }

            DohnaFeedbackLayer {
                id: dohnaFeedback
                objectName: prism.active ? ("dohnaFeedbackLayer") : ""
                anchors.fill: parent
                theme: prism
                reducedMotion: root.reduceMotion
                motionEnabled: root.animationsRunning
            }
        }
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

}
