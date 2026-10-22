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
    property string lastAnimatedPage: ""
    readonly property bool pageTransitioning: animationsRunning
                                              && (pageTransitionAnimation.running
                                                  || dohnaPageTransitionAnimation.running)
    property int pageTransitionSequence: 0
    property bool startPreludePending: false

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
        return ""
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
            root.pageContentReady = true
            root.settlePageTransition()
            dohnaFeedback.settle()
        }
    }

    background: Rectangle {
        gradient: Gradient {
            GradientStop { position: 0; color: prism.backgroundTop }
            GradientStop { position: 0.62; color: prism.dohna ? prism.inkRaised : prism.paper }
            GradientStop { position: 1; color: prism.backgroundBottom }
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
            : root.width < 1100 ? 176 : 184
            Layout.preferredWidth: implicitWidth
            Layout.fillHeight: true
            color: prism.navigationSurface
            border.color: prism.line
            clip: prism.dohna

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
                                : (root.width < 1100 ? 12 : 16)
                spacing: 10

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: 7
                    spacing: 0
                    Text {
                        text: "REFRA"
                        color: prism.navigationText
                        font.family: prism.displayFontFor(text)
                        font.pixelSize: 23
                        font.weight: Font.Bold
                        font.letterSpacing: 4
                    }
                    Text {
                        text: "TRANSLATOR / WORKBENCH"
                        color: prism.accent
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
                }

                Repeater {
                    model: root.pageOrder
                    PrismButton {
                        objectName: "navigationButton" + index
                        required property int index
                        required property var modelData
                        theme: prism
                        navigation: true
                        text: prism.dohna
                              ? String(modelData) + "  " + root.navigationLabel(String(modelData))
                              : root.navigationLabel(String(modelData))
                        navigationNumber: String(index + 1).padStart(2, "0")
                        navigationCode: root.pageCode(String(modelData))
                        primary: root.boundWorkbench.currentPage === modelData
                        quiet: root.boundWorkbench.currentPage !== modelData
                        implicitWidth: 150
                        Layout.fillWidth: true
                        Layout.minimumWidth: prism.dohna ? 0 : -1
                        // Overscan the rotated bar; the sidebar clips both ends
                        // flush, while the enlarged control remains clickable.
                        Layout.leftMargin: prism.dohna ? -navigationLayout.anchors.margins - 16 : 0
                        Layout.rightMargin: Layout.leftMargin
                        Layout.maximumWidth: prism.dohna ? navigationRail.width + 32 : Number.POSITIVE_INFINITY
                        // Preserve the visible gap of the original 50 px strips
                        // when their thickness changes under the same rotation.
                        Layout.bottomMargin: prism.dohna
                                             ? Math.round((implicitHeight - 50) * (1 / Math.cos(rotation * Math.PI / 180) - 1)) : 0
                        onClicked: root.boundWorkbench.setPage(String(modelData))
                    }
                }

                Item { Layout.fillHeight: true }

                Rectangle {
                    objectName: "activeProfileCard"
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
                    visible: !prism.dohna
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
                    clip: prism.dohna
                    Layout.fillWidth: true
                    Layout.preferredHeight: Math.max(
                        prism.dohna
                            ? (root.height <= 820 ? 116 : 142)
                            : (root.height <= 820 ? 104 : 116),
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
                                    motionEnabled: root.pageMotionEnabled
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
                                color: prism.textSoft
                                font.family: prism.uiFontFor(text)
                                font.pixelSize: 13
                                Layout.topMargin: prism.dohna ? 10 : 8
                            }
                        }

                        Text {
                            visible: root.boundWorkbench.settingsDirty
                            text: "● 未应用"
                            color: prism.amber
                            font.family: prism.monoFontFor(text)
                            font.pixelSize: 12
                        }
                        PrismButton {
                            objectName: "saveAllButton"
                            theme: prism
                            text: "应用更改"
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
                            text: root.startPreludePending
                                  ? (prism.dohna ? "正在点亮光路…" : "正在启动…")
                                  : root.boundWorkbench.startButtonText
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
                                pageMotionEnabled: root.pageMotionEnabled
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
                    Layout.preferredHeight: 34
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
                            color: root.boundWorkbench.running ? prism.accent : prism.navigationTextDim
                            font.family: prism.monoFontFor(text)
                            font.pixelSize: 12
                            font.letterSpacing: 1
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
