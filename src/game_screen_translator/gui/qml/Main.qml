pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "components"
import "pages"

ApplicationWindow {
    id: root
    objectName: "prismWorkbenchWindow"

    visible: false
    width: 1280
    height: 820
    minimumWidth: 980
    minimumHeight: 700
    title: "RefraTranslator · Prism Workbench"

    // The sole context property is intentionally injected by QmlWorkbenchHost.
    // qmllint disable unqualified
    readonly property var boundWorkbench: workbench
    // qmllint enable unqualified
    readonly property var pageOrder: ["HOME", "CAPTURE", "OCR", "TRANSLATION", "OVERLAY", "CACHE", "SETTINGS"]
    readonly property bool animationsRunning: visible
                                              && !boundWorkbench.reducedMotion
    readonly property string visualPage: boundWorkbench.currentPage
    readonly property bool reduceMotion: boundWorkbench.reducedMotion
    property string lastAnimatedPage: ""
    readonly property bool pageTransitioning: pageTransitionAnimation.running
    property int pageTransitionSequence: 0
    property bool startPreludePending: false

    function pageIndex(page) {
        const index = pageOrder.indexOf(page)
        return index < 0 ? 0 : index
    }

    function pageTitle(page) {
        return pageTitleLight(page) + pageTitleHeavy(page)
    }

    function pageTitleLight(page) {
        const titles = {
            "HOME": "折射",
            "CAPTURE": "捕获",
            "OCR": "识别",
            "TRANSLATION": "译文",
            "OVERLAY": "覆盖层",
            "CACHE": "缓存",
            "SETTINGS": "高级"
        }
        return titles[page] || page
    }

    function pageTitleHeavy(page) {
        const titles = {
            "HOME": "控制台",
            "CAPTURE": "光圈",
            "OCR": "矩阵",
            "TRANSLATION": "分光器",
            "OVERLAY": "投影",
            "CACHE": "阵列",
            "SETTINGS": "设置"
        }
        return titles[page] || ""
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
        pageContentTranslate.x = 0
        pageContentMotion.opacity = 1
        pageHeaderTranslate.x = 0
        pageHeaderSlice.opacity = 1
        transitionSweep.opacity = 0
        transitionSweep.x = root.width
        tertiaryRail.opacity = prism.tertiaryRailOpacity
    }

    function beginPageTransition() {
        if (visualPage === lastAnimatedPage)
            return
        lastAnimatedPage = visualPage
        pageTransitionSequence += 1
        if (reduceMotion || !visible) {
            pageTransitionAnimation.stop()
            settlePageTransition()
            return
        }
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
        stage.pulseStart()
        startPreludeTimer.restart()
    }

    function settleReducedMotion() {
        pageTransitionAnimation.stop()
        settlePageTransition()
        stage.settleMotion()
        if (startPreludePending)
            completeStartPrelude()
    }

    onVisualPageChanged: beginPageTransition()
    onReduceMotionChanged: {
        if (reduceMotion)
            settleReducedMotion()
    }
    onVisibleChanged: {
        if (visible) {
            lastAnimatedPage = ""
            beginPageTransition()
        } else {
            if (startPreludePending) {
                startPreludeTimer.stop()
                startPreludePending = false
                stage.settleMotion()
            }
            pageTransitionAnimation.stop()
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

    PrismTheme {
        id: prism
        objectName: "prismTheme"
        dark: root.boundWorkbench.effectiveTheme !== "light"
        reducedMotion: root.boundWorkbench.reducedMotion
    }

    background: Rectangle {
        gradient: Gradient {
            GradientStop { position: 0; color: prism.ink }
            GradientStop { position: 0.62; color: prism.inkRaised }
            GradientStop { position: 1; color: prism.dark ? "#0b1118" : "#b8c5ca" }
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
            font.pixelSize: 13
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
    }

    Connections {
        target: root.boundWorkbench

        function onErrorRaised(title, message) {
            errorDialog.errorTitle = title
            errorDialog.errorMessage = message
            stage.pulseWarning()
            errorDialog.open()
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            Layout.preferredWidth: root.width < 1100 ? 178 : 222
            Layout.fillHeight: true
            color: prism.dark ? "#d4070a0d" : "#c8d1dade"
            border.color: prism.line

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: root.width < 1100 ? 14 : 20
                spacing: 10

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: 7
                    spacing: 0
                    Text {
                        text: "REFRA"
                        color: prism.text
                        font.family: prism.displayFontFor(text)
                        font.pixelSize: 23
                        font.weight: Font.Bold
                        font.letterSpacing: 4
                    }
                    Text {
                        text: "TRANSLATOR / WORKBENCH"
                        color: prism.accent
                        font.family: prism.monoFontFor(text)
                        font.pixelSize: 8
                        font.letterSpacing: 1.1
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.topMargin: 8
                    Layout.bottomMargin: 5
                    Layout.preferredHeight: 1
                    color: prism.lineStrong
                }

                Repeater {
                    model: root.pageOrder
                    PrismButton {
                        required property int index
                        required property var modelData
                        theme: prism
                        text: String(index + 1).padStart(2, "0") + "   " + String(modelData)
                        primary: root.boundWorkbench.currentPage === modelData
                        quiet: root.boundWorkbench.currentPage !== modelData
                        implicitWidth: 150
                        Layout.fillWidth: true
                        onClicked: root.boundWorkbench.setPage(String(modelData))
                    }
                }

                Item { Layout.fillHeight: true }

                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: 92
                    color: "transparent"
                    border.color: prism.line
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 12
                        spacing: 3
                        Text {
                            text: "ACTIVE PROFILE"
                            color: prism.textDim
                            font.family: prism.monoFontFor(text)
                            font.pixelSize: 8
                            font.letterSpacing: 1
                        }
                        Text {
                            text: root.boundWorkbench.currentProfileName
                            color: prism.text
                            font.family: prism.uiFontFor(text)
                            font.pixelSize: 12
                            font.weight: Font.Medium
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                        Text {
                            text: root.boundWorkbench.hasProfile ? root.boundWorkbench.currentProfileId : "配置必需"
                            color: root.boundWorkbench.hasProfile ? prism.accent : prism.amber
                            font.family: prism.monoFontFor(text)
                            font.pixelSize: 8
                            elide: Text.ElideMiddle
                            Layout.fillWidth: true
                        }
                    }
                }

                Text {
                    text: "NATIVE QML · 7 SURFACES"
                    color: prism.textDim
                    font.family: prism.monoFontFor(text)
                    font.pixelSize: 8
                    font.letterSpacing: 0.8
                    Layout.alignment: Qt.AlignHCenter
                    Layout.bottomMargin: 5
                }
            }
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            OpticalStage {
                id: stage
                objectName: "opticalStage"
                anchors.fill: parent
                anchors.margins: 12
                theme: prism
                page: root.boundWorkbench.currentPage
                reducedMotion: root.boundWorkbench.reducedMotion
                motionEnabled: root.animationsRunning
                opacity: prism.opticalStageOpacity
            }

            ColumnLayout {
                anchors.fill: parent
                spacing: 0

                Rectangle {
                    objectName: "pageHeaderBar"
                    Layout.fillWidth: true
                    Layout.preferredHeight: Math.max(
                        root.height <= 820 ? 116 : 142,
                        prism.displayTitleSize(root.width) + 52
                    )
                    color: prism.dark ? "#c20b0f13" : "#d8d7dde0"
                    border.color: prism.line

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 22
                        anchors.rightMargin: 22
                        spacing: 14

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 0
                            Text {
                                text: String(root.pageIndex(root.boundWorkbench.currentPage) + 1).padStart(2, "0")
                                      + " / " + root.boundWorkbench.currentPage
                                color: prism.accent
                                font.family: prism.monoFontFor(text)
                                font.pixelSize: 9
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
                                transform: Translate {
                                    id: pageHeaderTranslate
                                    objectName: "pageHeaderTranslate"
                                }

                                RefractedTitle {
                                    id: displayTitleGroup
                                    objectName: "pageDisplayTitle"
                                    anchors.fill: parent
                                    theme: prism
                                    lightText: root.pageTitleLight(root.boundWorkbench.currentPage)
                                    heavyText: root.pageTitleHeavy(root.boundWorkbench.currentPage)
                                    titleSize: pageHeaderSlice.titleSize
                                    transitionSequence: root.pageTransitionSequence
                                    motionEnabled: root.animationsRunning
                                }
                                Rectangle {
                                    width: Math.min(parent.width * 0.72, 420)
                                    height: 1
                                    anchors.left: parent.left
                                    anchors.bottom: parent.bottom
                                    color: prism.accent
                                    opacity: 0.46
                                    rotation: -1.2
                                }
                            }
                            Text {
                                text: root.pageSubtitle(root.boundWorkbench.currentPage)
                                color: prism.textSoft
                                font.family: prism.uiFontFor(text)
                                font.pixelSize: 11
                            }
                        }

                        Text {
                            visible: root.boundWorkbench.settingsDirty
                            text: "● 未应用"
                            color: prism.amber
                            font.family: prism.monoFontFor(text)
                            font.pixelSize: 10
                        }
                        PrismButton {
                            objectName: "saveAllButton"
                            theme: prism
                            text: "应用更改"
                            enabled: root.boundWorkbench.hasProfile
                            onClicked: {
                                root.boundWorkbench.saveAll()
                                if (root.boundWorkbench.currentPage === "SETTINGS")
                                    stage.pulseAction("calibrate")
                            }
                        }
                        PrismButton {
                            objectName: "startLiveButton"
                            theme: prism
                            primary: true
                            text: root.startPreludePending ? "正在点亮光路…" : root.boundWorkbench.startButtonText
                            enabled: root.boundWorkbench.runPhase !== "stopping"
                                     && !root.startPreludePending
                                     && (root.boundWorkbench.canStart || root.boundWorkbench.running)
                            onClicked: root.requestLiveToggle()
                        }
                    }
                }

                Item {
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
                            anchors.margins: root.width < 1100 ? 14 : 18
                            currentIndex: root.pageIndex(root.boundWorkbench.currentPage)

                            HomePage {
                                objectName: "homePage"
                                theme: prism
                                workbench: root.boundWorkbench
                                transitionSerial: root.pageTransitionSequence
                                pageMotionEnabled: root.animationsRunning
                            }
                            CapturePage {
                                objectName: "capturePage"
                                theme: prism
                                workbench: root.boundWorkbench
                                transitionSerial: root.pageTransitionSequence
                                pageMotionEnabled: root.animationsRunning
                                onVisualAction: action => stage.pulseAction(action)
                            }
                            OcrPage {
                                objectName: "ocrPage"
                                theme: prism
                                workbench: root.boundWorkbench
                                transitionSerial: root.pageTransitionSequence
                                pageMotionEnabled: root.animationsRunning
                                onVisualAction: action => stage.pulseAction(action)
                            }
                            TranslationPage {
                                objectName: "translationPage"
                                theme: prism
                                workbench: root.boundWorkbench
                                transitionSerial: root.pageTransitionSequence
                                pageMotionEnabled: root.animationsRunning
                                onVisualAction: action => stage.pulseAction(action)
                            }
                            OverlayPage {
                                objectName: "overlayPage"
                                theme: prism
                                workbench: root.boundWorkbench
                                transitionSerial: root.pageTransitionSequence
                                pageMotionEnabled: root.animationsRunning
                                onVisualAction: action => stage.pulseAction(action)
                            }
                            CachePage {
                                objectName: "cachePage"
                                theme: prism
                                workbench: root.boundWorkbench
                                transitionSerial: root.pageTransitionSequence
                                pageMotionEnabled: root.animationsRunning
                                onVisualAction: action => stage.pulseAction(action)
                            }
                            SettingsPage {
                                objectName: "settingsPage"
                                theme: prism
                                workbench: root.boundWorkbench
                                transitionSerial: root.pageTransitionSequence
                                pageMotionEnabled: root.animationsRunning
                                onVisualAction: action => stage.pulseAction(action)
                            }
                        }
                    }

                    Rectangle {
                        id: tertiaryRail
                        objectName: "pageTertiaryRail"
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        height: 3
                        color: prism.spectrum
                        opacity: prism.tertiaryRailOpacity
                    }

                    Rectangle {
                        id: transitionSweep
                        objectName: "pageTransitionSweep"
                        readonly property real accentAlpha: prism.sweepAccentAlpha
                        readonly property real spectrumAlpha: prism.sweepSpectrumAlpha
                        width: Math.max(190, parent.width * 0.28)
                        height: parent.height * 1.3
                        y: -parent.height * 0.15
                        rotation: -12
                        opacity: 0
                        gradient: Gradient {
                            orientation: Gradient.Horizontal
                            GradientStop { position: 0; color: "transparent" }
                            GradientStop { position: 0.42; color: Qt.rgba(prism.accent.r, prism.accent.g, prism.accent.b, transitionSweep.accentAlpha) }
                            GradientStop { position: 0.62; color: Qt.rgba(prism.spectrum.r, prism.spectrum.g, prism.spectrum.b, transitionSweep.spectrumAlpha) }
                            GradientStop { position: 1; color: "transparent" }
                        }
                        Rectangle {
                            objectName: "pageTransitionSweepCore"
                            anchors.centerIn: parent
                            width: 2
                            height: parent.height
                            color: prism.text
                            opacity: 0.62
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 34
                    color: prism.dark ? "#d4070a0d" : "#c8d1dade"
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
                            color: prism.textSoft
                            font.family: prism.uiFontFor(text)
                            font.pixelSize: 10
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                        Text {
                            text: root.boundWorkbench.runPhase.toUpperCase()
                            color: root.boundWorkbench.running ? prism.accent : prism.textDim
                            font.family: prism.monoFontFor(text)
                            font.pixelSize: 9
                            font.letterSpacing: 1
                        }
                    }
                }
            }

            TransientFeedbackLayer {
                objectName: "transientFeedbackLayer"
                anchors.fill: parent
                theme: prism
                startProgress: stage.startProgress
                startRunning: stage.startPreludeRunning
                reducedMotion: root.reduceMotion
            }
        }
    }

    ParallelAnimation {
        id: pageTransitionAnimation
        onStopped: root.settlePageTransition()

        SequentialAnimation {
            PropertyAction { target: pageContentTranslate; property: "x"; value: 15 }
            PropertyAction { target: pageContentMotion; property: "opacity"; value: 0.1 }
            ParallelAnimation {
                NumberAnimation { target: pageContentTranslate; property: "x"; to: 0; duration: prism.pageMotion; easing.type: Easing.OutCubic }
                NumberAnimation { target: pageContentMotion; property: "opacity"; to: 1; duration: prism.pageMotion; easing.type: Easing.OutCubic }
            }
        }
        SequentialAnimation {
            PropertyAction { target: pageHeaderTranslate; property: "x"; value: 22 }
            PropertyAction { target: pageHeaderSlice; property: "opacity"; value: 0.08 }
            PauseAnimation { duration: prism.fast }
            ParallelAnimation {
                NumberAnimation { target: pageHeaderTranslate; property: "x"; to: 0; duration: prism.pageSecondaryMotion; easing.type: Easing.OutCubic }
                NumberAnimation { target: pageHeaderSlice; property: "opacity"; to: 1; duration: prism.pageSecondaryMotion; easing.type: Easing.OutCubic }
            }
        }
        SequentialAnimation {
            PropertyAction { target: transitionSweep; property: "x"; value: -transitionSweep.width }
            PropertyAction { target: transitionSweep; property: "opacity"; value: 0 }
            ParallelAnimation {
                NumberAnimation { target: transitionSweep; property: "x"; to: root.width + transitionSweep.width; duration: prism.pageMotion; easing.type: Easing.InOutCubic }
                SequentialAnimation {
                    NumberAnimation { target: transitionSweep; property: "opacity"; to: 1; duration: prism.ui }
                    PauseAnimation { duration: prism.pageMotion - prism.ui * 2 }
                    NumberAnimation { target: transitionSweep; property: "opacity"; to: 0; duration: prism.ui }
                }
            }
        }
        SequentialAnimation {
            PropertyAction { target: tertiaryRail; property: "opacity"; value: 0 }
            PauseAnimation { duration: prism.ui }
            NumberAnimation { target: tertiaryRail; property: "opacity"; to: prism.tertiaryRailOpacity; duration: prism.pageTertiaryMotion; easing.type: Easing.OutCubic }
        }
    }
}
