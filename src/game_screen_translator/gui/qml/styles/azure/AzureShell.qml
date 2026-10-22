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
    readonly property int navWidth: width < 1080 ? 178 : 194
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
        dark: root.workbench.effectiveTheme === "dark"
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
            Layout.preferredWidth: root.navWidth
            Layout.minimumWidth: root.navWidth
            Layout.maximumWidth: root.navWidth
            Layout.fillHeight: true
            clip: true

            Shape {
                anchors.right: parent.right
                width: 18
                height: parent.height
                enabled: false
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
                anchors.topMargin: 16
                anchors.bottomMargin: 12
                spacing: 9

                RowLayout {
                    Layout.fillWidth: true
                    Layout.bottomMargin: 9
                    spacing: 9
                    Rectangle {
                        Layout.preferredWidth: 30
                        Layout.preferredHeight: 30
                        color: "#ffffff"
                        Shape {
                            anchors.fill: parent
                            ShapePath {
                                fillColor: theme.accent
                                strokeWidth: 0
                                startX: 2; startY: 25
                                PathLine { x: 25; y: 2 }
                                PathLine { x: 25; y: 9 }
                                PathLine { x: 9; y: 25 }
                                PathLine { x: 2; y: 25 }
                            }
                        }
                    }
                    ColumnLayout {
                        spacing: -2
                        Text {
                            text: "Refra"
                            color: theme.navigationText
                            font.family: theme.displayFontFor(text)
                            font.pixelSize: 16
                            font.weight: Font.Bold
                        }
                        Text {
                            text: "TRANSLATOR"
                            color: theme.navigationTextDim
                            font.family: theme.monoFontFor(text)
                            font.pixelSize: 8
                            font.letterSpacing: 1.1
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
                        Layout.leftMargin: [0, 12, 3, 15, 1, 13, 4][index]
                        Layout.rightMargin: 8
                        theme: theme
                        number: String(index + 1).padStart(2, "0")
                        code: String(modelData)
                        text: root.pageNames[index]
                        selected: root.workbench.currentPage === modelData
                        onClicked: root.requestPage(String(modelData))
                        Accessible.description: "切换到" + text
                    }
                }

                Item { Layout.fillHeight: true }

                Shape {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 1
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
                anchors.fill: parent
                anchors.leftMargin: root.width < 1080 ? 14 : 20
                anchors.rightMargin: root.width < 1080 ? 14 : 20
                anchors.topMargin: 8
                anchors.bottomMargin: 8
                spacing: 8

                RowLayout {
                    objectName: "azureActionBar"
                    Layout.fillWidth: true
                    Layout.preferredHeight: 42
                    spacing: 8
                    Text {
                        text: String(root.currentIndex + 1).padStart(2, "0")
                              + "  /  " + root.pageName(root.workbench.currentPage).toUpperCase()
                        color: theme.accentText
                        font.family: theme.monoFontFor(text)
                        font.pixelSize: 11
                        font.letterSpacing: 1
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                    }
                    Text {
                        visible: root.workbench.settingsDirty
                        text: "● 有未应用更改"
                        color: theme.amber
                        font.family: theme.uiFontFor(text)
                        font.pixelSize: 12
                    }
                    AzureButton {
                        objectName: "azureSaveAllButton"
                        theme: theme
                        text: "应用更改"
                        enabled: root.workbench.hasProfile
                        implicitHeight: 36
                        onClicked: root.workbench.saveAll()
                    }
                    AzureButton {
                        objectName: "azureStartLiveButton"
                        theme: theme
                        visible: root.workbench.currentPage !== "HOME"
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
                    Layout.fillWidth: true
                    Layout.preferredHeight: 28
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
                        anchors.fill: parent
                        anchors.leftMargin: 12
                        anchors.rightMargin: 8
                        text: root.workbench.statusText
                        color: theme.textSoft
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
