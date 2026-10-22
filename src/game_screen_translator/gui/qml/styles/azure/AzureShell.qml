pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
import "../../pages"
import "components"
import "pages"

Item {
    id: root
    required property var workbench
    required property var legacyTheme
    required property bool reducedMotion
    required property bool startPending
    signal requestLiveToggle()
    signal visualAction(string action)

    readonly property var pageOrder: ["HOME", "CAPTURE", "OCR", "TRANSLATION", "OVERLAY", "CACHE", "SETTINGS"]
    readonly property var pageNames: ["首页", "画面捕获", "文字识别", "翻译", "字幕叠加", "缓存", "设置"]
    readonly property int currentIndex: Math.max(0, pageOrder.indexOf(workbench.currentPage))
    readonly property int navWidth: width < 1080 ? 184 : 204
    readonly property bool fullScenePage: workbench.currentPage === "HOME"
                                         || workbench.currentPage === "SETTINGS"
    property int transitionSerial: 0

    function pageName(page) {
        const index = pageOrder.indexOf(page)
        return index >= 0 ? pageNames[index] : String(page)
    }
    function requestPage(page) {
        if (page === workbench.currentPage)
            return
        transitionSerial += 1
        workbench.setPage(page)
    }

    onCurrentIndexChanged: {
        if (reducedMotion || width <= 0) {
            pageSurface.opacity = 1
        } else {
            pageSurface.opacity = 0.78
            pageFade.restart()
        }
    }
    onReducedMotionChanged: {
        if (reducedMotion) {
            pageFade.stop()
            pageSurface.opacity = 1
        }
    }

    AzureTheme {
        id: theme
        dark: true
        reducedMotion: root.reducedMotion
    }

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0; color: theme.backgroundTop }
            GradientStop { position: 1; color: theme.backgroundBottom }
        }
    }

    Shape {
        id: heroPlane
        x: root.navWidth - 12
        y: 0
        width: Math.max(0, root.width - x)
        height: Math.min(root.height * 0.36, 300)
        enabled: false
        antialiasing: true
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            fillColor: theme.heroPlane
            strokeWidth: 0
            startX: heroPlane.width * 0.41; startY: 0
            PathLine { x: heroPlane.width; y: 0 }
            PathLine { x: heroPlane.width; y: heroPlane.height * 0.68 }
            PathLine { x: heroPlane.width * 0.8; y: heroPlane.height }
            PathLine { x: heroPlane.width * 0.41; y: 0 }
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            id: rail
            objectName: "azureNavigationRail"
            color: theme.navigationSurface
            z: 1
            Layout.preferredWidth: root.navWidth
            Layout.minimumWidth: root.navWidth
            Layout.maximumWidth: root.navWidth
            Layout.fillHeight: true
            clip: true

                Shape {
                    id: railBottomPlane
                    x: 0
                    y: parent.height * 0.61
                    width: root.navWidth
                    height: parent.height * 0.27
                    antialiasing: true
                    preferredRendererType: Shape.CurveRenderer
                    ShapePath {
                        fillColor: "#0b2b6c"
                        strokeWidth: 0
                        startX: 0; startY: 0
                        PathLine { x: railBottomPlane.width; y: railBottomPlane.height * 0.12 }
                        PathLine { x: railBottomPlane.width * 0.65; y: railBottomPlane.height }
                        PathLine { x: 0; y: railBottomPlane.height }
                        PathLine { x: 0; y: 0 }
                    }
                }
                Shape {
                    id: railCyanPlane
                    x: 0
                    y: parent.height * 0.74
                    width: root.navWidth * 0.62
                    height: parent.height * 0.12
                    antialiasing: true
                    preferredRendererType: Shape.CurveRenderer
                    ShapePath {
                        fillColor: "#05bde9"
                        strokeWidth: 0
                        startX: 0; startY: 0
                        PathLine { x: railCyanPlane.width * 0.48; y: 0 }
                        PathLine { x: railCyanPlane.width; y: railCyanPlane.height }
                        PathLine { x: 0; y: railCyanPlane.height }
                        PathLine { x: 0; y: 0 }
                    }
                }

            Shape {
                anchors.right: parent.right
                width: 18
                height: parent.height
                enabled: false
                antialiasing: true
                preferredRendererType: Shape.CurveRenderer
                ShapePath {
                    fillColor: theme.backgroundTop
                    strokeWidth: 0
                    startX: 18; startY: 0
                    PathLine { x: 18; y: rail.height }
                    PathLine { x: 0; y: rail.height }
                    PathLine { x: 18; y: 0 }
                }
            }

            ColumnLayout {
                anchors.fill: parent
                anchors.leftMargin: root.width < 1080 ? 10 : 14
                anchors.rightMargin: 7
                    anchors.topMargin: 18
                anchors.bottomMargin: 12
                spacing: root.height < 760 ? 5 : 9

                Item {
                    objectName: "azureBrandBadge"
                    Layout.fillWidth: true
                    Layout.preferredHeight: root.height < 760 ? 40 : 44
                    Layout.bottomMargin: 9
                    Shape {
                        id: brandBadgeShape
                        anchors.fill: parent
                        antialiasing: true
                        preferredRendererType: Shape.CurveRenderer
                        ShapePath {
                            fillColor: "#ffffff"
                            strokeWidth: 0
                            startX: 0; startY: 0
                            PathLine { x: brandBadgeShape.width - 9; y: 0 }
                            PathLine { x: brandBadgeShape.width; y: brandBadgeShape.height * 0.72 }
                            PathLine { x: brandBadgeShape.width - 7; y: brandBadgeShape.height }
                            PathLine { x: 0; y: brandBadgeShape.height }
                            PathLine { x: 0; y: 0 }
                        }
                    }
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 8
                        anchors.rightMargin: 10
                        spacing: 8
                        Rectangle {
                            Layout.preferredWidth: 23
                            Layout.preferredHeight: 23
                            color: "#104bf5"
                            Shape {
                                anchors.fill: parent
                                antialiasing: true
                                preferredRendererType: Shape.CurveRenderer
                                ShapePath {
                                    fillColor: "#05bde9"
                                    strokeWidth: 0
                                    startX: 2; startY: 19
                                    PathLine { x: 19; y: 2 }
                                    PathLine { x: 19; y: 8 }
                                    PathLine { x: 8; y: 19 }
                                    PathLine { x: 2; y: 19 }
                                }
                            }
                        }
                        Text {
                            text: "RefraTranslator"
                            color: "#071b50"
                            font.family: theme.displayFontFor(text)
                            font.pixelSize: root.width < 1080 ? 15 : 16
                            font.weight: Font.Black
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 1
                    Layout.bottomMargin: 6
                    color: "#345083"
                }

                Repeater {
                    model: root.pageOrder
                    AzureNavItem {
                        required property int index
                        required property var modelData
                        objectName: "azureNavigationButton" + index
                        Layout.fillWidth: true
                        Layout.preferredHeight: root.height < 760 ? 52 : 68
                        Layout.minimumHeight: root.height < 760 ? 52 : 68
                        Layout.maximumHeight: root.height < 760 ? 52 : 68
                        Layout.leftMargin: [0, 14, 3, 18, 1, 15, 4][index]
                        Layout.rightMargin: 8
                        theme: theme
                        number: String(index + 1).padStart(2, "0")
                        code: String(modelData)
                        text: root.pageNames[index]
                        selected: root.workbench.currentPage === modelData
                        selectedFontSize: root.height < 760 ? 35 : 46
                        idleFontSize: root.height < 760 ? 17 : 21
                        onClicked: root.requestPage(String(modelData))
                        Accessible.description: "切换到" + text
                    }
                }

                Item { Layout.fillHeight: true }

                Shape {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 1
                    antialiasing: true
                    preferredRendererType: Shape.CurveRenderer
                    ShapePath {
                        strokeColor: "#355083"
                        strokeWidth: 1
                        startX: 0; startY: 0
                        PathLine { x: root.navWidth - 28; y: 0 }
                    }
                }

                Text {
                    text: "CURRENT PROFILE"
                    color: theme.navigationTextDim
                    font.family: theme.monoFontFor(text)
                    font.pixelSize: 9
                    font.letterSpacing: 0.8
                }
                Text {
                    objectName: "azureActiveProfileName"
                    text: root.workbench.currentProfileName
                    color: theme.navigationText
                    font.family: theme.uiFontFor(text)
                    font.pixelSize: 12
                    font.weight: Font.Medium
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
                Text {
                    text: "GAME SCREEN\nTRANSLATION TOOL"
                    color: "#7894d3"
                    font.family: theme.monoFontFor(text)
                    font.pixelSize: 9
                    font.letterSpacing: 1
                    lineHeight: 1.25
                    Layout.topMargin: 6
                }
            }
        }

        Item {
            id: workspace
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true

            ColumnLayout {
                id: workspaceColumn
                anchors.fill: parent
                anchors.leftMargin: root.fullScenePage ? 0 : (root.width < 1080 ? 14 : 20)
                anchors.rightMargin: root.fullScenePage ? 0 : (root.width < 1080 ? 14 : 20)
                anchors.topMargin: root.fullScenePage ? 0 : 8
                anchors.bottomMargin: root.fullScenePage ? 0 : 8
                spacing: root.fullScenePage ? 0 : 8

                RowLayout {
                    objectName: "azureActionBar"
                    visible: !root.fullScenePage
                    Layout.fillWidth: true
                    Layout.preferredHeight: 42
                    spacing: 8
                    Text {
                        objectName: "azureActionBarTitle"
                        text: String(root.currentIndex + 1).padStart(2, "0")
                              + "  /  " + root.pageName(root.workbench.currentPage).toUpperCase()
                        color: "#dce7ff"
                        font.family: theme.monoFontFor(text)
                        font.pixelSize: 11
                        font.letterSpacing: 1
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                    }
                    Text {
                        objectName: "azureActionBarDirtyText"
                        visible: root.workbench.settingsDirty
                        text: "● 有未应用更改"
                        color: "#ffd16d"
                        font.family: theme.uiFontFor(text)
                        font.pixelSize: 12
                    }
                    AzureButton {
                        objectName: root.fullScenePage
                                    ? "azureHiddenGlobalSaveAllButton" : "azureSaveAllButton"
                        theme: theme
                        text: "应用更改"
                        enabled: root.workbench.hasProfile
                        visible: !root.fullScenePage
                        implicitHeight: 36
                        onClicked: root.workbench.saveAll()
                    }
                    AzureButton {
                        objectName: root.fullScenePage
                                    ? "azureHiddenGlobalStartLiveButton" : "azureStartLiveButton"
                        theme: theme
                        visible: root.workbench.currentPage !== "HOME"
                                 && root.workbench.currentPage !== "SETTINGS"
                        primary: true
                        text: root.startPending ? "正在准备…" : root.workbench.startButtonText
                        enabled: root.workbench.runPhase !== "stopping"
                                 && !root.startPending
                                 && (root.workbench.canStart || root.workbench.running)
                        implicitHeight: 36
                        onClicked: root.requestLiveToggle()
                    }
                }

                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true

                    Item {
                        id: pageSurface
                        objectName: "azurePageSurface"
                        anchors.fill: parent
                        opacity: 1
                        transform: Translate {
                            x: root.reducedMotion ? 0 : (1 - pageSurface.opacity) * 12
                        }

                        Rectangle {
                            objectName: "azureLegacyPageBacking"
                            anchors.fill: parent
                            visible: !root.fullScenePage
                            color: root.legacyTheme.paper
                        }

                        StackLayout {
                            id: azurePageStack
                            objectName: "azurePageStack"
                            anchors.fill: parent
                            currentIndex: root.currentIndex

                            AzureHomePage {
                                objectName: "azureHomePage"
                                theme: theme
                                workbench: root.workbench
                                startPending: root.startPending
                                onRequestLiveToggle: root.requestLiveToggle()
                            }
                            CapturePage {
                                theme: root.legacyTheme
                                workbench: root.workbench
                                transitionSerial: root.transitionSerial
                                pageMotionEnabled: !root.reducedMotion
                                onVisualAction: action => root.visualAction(action)
                            }
                            OcrPage {
                                theme: root.legacyTheme
                                workbench: root.workbench
                                transitionSerial: root.transitionSerial
                                pageMotionEnabled: !root.reducedMotion
                                onVisualAction: action => root.visualAction(action)
                            }
                            TranslationPage {
                                theme: root.legacyTheme
                                workbench: root.workbench
                                transitionSerial: root.transitionSerial
                                pageMotionEnabled: !root.reducedMotion
                                onVisualAction: action => root.visualAction(action)
                            }
                            OverlayPage {
                                theme: root.legacyTheme
                                workbench: root.workbench
                                transitionSerial: root.transitionSerial
                                pageMotionEnabled: !root.reducedMotion
                                onVisualAction: action => root.visualAction(action)
                            }
                            CachePage {
                                theme: root.legacyTheme
                                workbench: root.workbench
                                transitionSerial: root.transitionSerial
                                pageMotionEnabled: !root.reducedMotion
                            }
                            AzureSettingsPage {
                                objectName: "azureSettingsPage"
                                theme: theme
                                workbench: root.workbench
                                startPending: root.startPending
                                onRequestLiveToggle: root.requestLiveToggle()
                                onVisualAction: action => root.visualAction(action)
                            }
                        }
                    }
                    NumberAnimation {
                        id: pageFade
                        target: pageSurface
                        property: "opacity"
                        to: 1
                        duration: theme.pageMotion
                        easing.type: Easing.OutCubic
                    }
                }

                Rectangle {
                    id: statusBar
                    objectName: "azureGlobalStatusBar"
                    Layout.fillWidth: true
                    Layout.preferredHeight: 28
                    visible: !root.fullScenePage
                    color: "transparent"
                    Rectangle {
                        anchors.left: parent.left
                        anchors.top: parent.top
                        width: 3
                        height: parent.height
                        color: root.workbench.statusTone === "error" ? theme.danger
                             : root.workbench.statusTone === "warning" ? theme.amber
                             : root.workbench.statusTone === "success" ? theme.accent : theme.spectrum
                    }
                    Text {
                        objectName: "azureGlobalStatusText"
                        anchors.fill: parent
                        anchors.leftMargin: 12
                        anchors.rightMargin: 8
                        text: root.workbench.statusText
                        color: "#dce7ff"
                        font.family: theme.uiFontFor(text)
                        font.pixelSize: 11
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideRight
                    }
                }
            }
        }
    }
}
