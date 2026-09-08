import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../components"

Item {
    id: root

    required property var theme
    required property var workbench
    property int transitionSerial: 0
    property bool pageMotionEnabled: false
    property bool regionSelectionRequested: false
    property bool regionSelectionWasHidden: false
    property bool regionSelectionSaved: false
    readonly property bool workbenchVisible: root.Window.window
                                             ? root.Window.window.visible
                                             : false
    signal visualAction(string action)

    function finishRegionSelectionFeedback() {
        if (root.workbenchVisible)
            root.visualAction("scan")
    }

    function clearRegionSelectionFeedback() {
        root.regionSelectionRequested = false
        root.regionSelectionWasHidden = false
        root.regionSelectionSaved = false
    }

    onWorkbenchVisibleChanged: {
        if (!workbenchVisible && regionSelectionRequested) {
            regionSelectionWasHidden = true
            return
        }
        if (workbenchVisible && regionSelectionRequested && regionSelectionWasHidden) {
            const shouldPulse = regionSelectionSaved
            root.clearRegionSelectionFeedback()
            if (shouldPulse)
                Qt.callLater(root.finishRegionSelectionFeedback)
        }
    }

    Connections {
        target: root.workbench

        function onNoticeRaised(message) {
            if (!root.regionSelectionRequested)
                return
            if (message === "已取消框选") {
                root.clearRegionSelectionFeedback()
            } else if (message.indexOf("区域已保存到 ") === 0) {
                root.regionSelectionSaved = true
            }
        }

        function onErrorRaised(_title, _message) {
            if (root.regionSelectionRequested)
                root.clearRegionSelectionFeedback()
        }
    }

    function updateRegion(field, value) {
        let left = root.workbench.captureLeft
        let top = root.workbench.captureTop
        let width = root.workbench.captureWidth
        let height = root.workbench.captureHeight
        if (field === "left") left = value
        if (field === "top") top = value
        if (field === "width") width = value
        if (field === "height") height = value
        root.workbench.setCaptureRegion(left, top, width, height)
    }

    RowLayout {
        anchors.fill: parent
        spacing: 16

        PrismPanel {
            objectName: "capturePrimaryPanel"
            theme: root.theme
            motionRole: "primary"
            transitionSerial: root.transitionSerial
            motionEnabled: root.pageMotionEnabled && root.visible
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumWidth: 380

            ColumnLayout {
                anchors.fill: parent
                spacing: 16

                SectionHeader {
                    theme: root.theme
                    title: "捕获几何"
                    meta: "CONFIGURATION"
                    Layout.fillWidth: true
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    color: Qt.rgba(root.theme.accent.r, root.theme.accent.g, root.theme.accent.b, 0.025)
                    border.color: root.theme.line

                    Item {
                        id: geometryStage
                        objectName: "captureGeometryStage"
                        anchors.fill: parent
                        anchors.margins: 28

                        Rectangle {
                            anchors.fill: parent
                            color: "transparent"
                            border.color: root.theme.lineStrong
                            border.width: 1
                        }

                        Rectangle {
                            id: captureRegionPreview
                            objectName: "captureRegionPreview"
                            readonly property real scaledWidth: parent.width
                                                                * root.workbench.captureWidth
                                                                / Math.max(1, root.workbench.captureDisplayWidth)
                            readonly property real scaledHeight: parent.height
                                                                 * root.workbench.captureHeight
                                                                 / Math.max(1, root.workbench.captureDisplayHeight)
                            visible: root.workbench.customRegion
                                     && root.workbench.captureDisplayWidth > 0
                                     && root.workbench.captureDisplayHeight > 0
                            width: Math.min(parent.width, Math.max(2, scaledWidth))
                            height: Math.min(parent.height, Math.max(2, scaledHeight))
                            x: Math.max(0, Math.min(
                                parent.width - width,
                                parent.width * root.workbench.captureLeft
                                / Math.max(1, root.workbench.captureDisplayWidth)
                            ))
                            y: Math.max(0, Math.min(
                                parent.height - height,
                                parent.height * root.workbench.captureTop
                                / Math.max(1, root.workbench.captureDisplayHeight)
                            ))
                            color: Qt.rgba(root.theme.accent.r, root.theme.accent.g, root.theme.accent.b, 0.07)
                            border.color: root.theme.accent
                            border.width: 2
                        }

                        Text {
                            anchors.centerIn: parent
                            text: root.workbench.customRegion ? root.workbench.captureSummary : "整个显示器"
                            color: root.theme.text
                            font.family: root.theme.monoFontFor(text)
                            font.pixelSize: 12
                        }

                        Text {
                            anchors.left: parent.left
                            anchors.bottom: parent.bottom
                            anchors.margins: 12
                            text: "仅显示已配置的几何关系，不是实时画面"
                            color: root.theme.textDim
                            font.family: root.theme.uiFontFor(text)
                            font.pixelSize: 11
                        }
                    }
                }

            }
        }

        PrismPanel {
            objectName: "captureSecondaryPanel"
            theme: root.theme
            raised: true
            motionRole: "secondary"
            transitionSerial: root.transitionSerial
            motionEnabled: root.pageMotionEnabled && root.visible
            Layout.preferredWidth: 344
            Layout.minimumWidth: 310
            Layout.fillHeight: true

            Flickable {
                id: captureFormScroll
                anchors.fill: parent
                contentWidth: width
                contentHeight: form.implicitHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                FocusScrollGuard { flickable: captureFormScroll }

                ColumnLayout {
                    id: form
                    width: parent.width
                    spacing: 12

                    SectionHeader {
                        theme: root.theme
                        title: "捕获区域"
                        meta: root.workbench.settingsDirty ? "UNSAVED" : "SAVED"
                        Layout.fillWidth: true
                    }

                    SettingLabel { theme: root.theme; title: "目标显示器"; meta: "PHYSICAL DISPLAY" }
                    PrismComboBox {
                        theme: root.theme
                        accessibleName: "目标显示器"
                        model: root.workbench.monitorNames
                        currentIndex: root.workbench.monitorIndex
                        enabled: root.workbench.hasProfile && model.length > 0
                        Layout.fillWidth: true
                        onActivated: index => root.workbench.setMonitorIndex(index)
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        PrismButton {
                            objectName: "captureScanAction"
                            theme: root.theme
                            text: "整个显示器"
                            primary: !root.workbench.customRegion
                            enabled: root.workbench.hasProfile
                            Layout.fillWidth: true
                            onClicked: {
                                root.workbench.useFullScreen()
                                root.visualAction("scan")
                            }
                        }
                        PrismButton {
                            theme: root.theme
                            text: "自定义区域"
                            primary: root.workbench.customRegion
                            enabled: root.workbench.hasProfile
                            Layout.fillWidth: true
                            onClicked: {
                                root.workbench.setCustomRegion(true)
                                root.visualAction("scan")
                            }
                        }
                    }

                    SettingLabel { theme: root.theme; title: "左边界"; meta: "PIXELS" }
                    NumberStepper {
                        theme: root.theme
                        accessibleName: "捕获区域左边界"
                        value: root.workbench.captureLeft
                        minimum: 0
                        maximum: 32768
                        stepSize: 10
                        suffix: "px"
                        enabled: root.workbench.hasProfile && root.workbench.customRegion
                        Layout.fillWidth: true
                        onEdited: value => root.updateRegion("left", value)
                    }
                    SettingLabel { theme: root.theme; title: "上边界"; meta: "PIXELS" }
                    NumberStepper {
                        theme: root.theme
                        accessibleName: "捕获区域上边界"
                        value: root.workbench.captureTop
                        minimum: 0
                        maximum: 32768
                        stepSize: 10
                        suffix: "px"
                        enabled: root.workbench.hasProfile && root.workbench.customRegion
                        Layout.fillWidth: true
                        onEdited: value => root.updateRegion("top", value)
                    }
                    SettingLabel { theme: root.theme; title: "宽度"; meta: "PIXELS" }
                    NumberStepper {
                        theme: root.theme
                        accessibleName: "捕获区域宽度"
                        value: root.workbench.captureWidth
                        minimum: 1
                        maximum: 32768
                        stepSize: 10
                        suffix: "px"
                        enabled: root.workbench.hasProfile && root.workbench.customRegion
                        Layout.fillWidth: true
                        onEdited: value => root.updateRegion("width", value)
                    }
                    SettingLabel { theme: root.theme; title: "高度"; meta: "PIXELS" }
                    NumberStepper {
                        theme: root.theme
                        accessibleName: "捕获区域高度"
                        value: root.workbench.captureHeight
                        minimum: 1
                        maximum: 32768
                        stepSize: 10
                        suffix: "px"
                        enabled: root.workbench.hasProfile && root.workbench.customRegion
                        Layout.fillWidth: true
                        onEdited: value => root.updateRegion("height", value)
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        PrismButton {
                            objectName: "captureRegionSelectAction"
                            theme: root.theme
                            text: "框选区域"
                            enabled: root.workbench.hasProfile
                            Layout.fillWidth: true
                            onClicked: {
                                root.regionSelectionRequested = true
                                root.regionSelectionWasHidden = false
                                root.regionSelectionSaved = false
                                root.workbench.selectRegion()
                            }
                        }
                        PrismButton {
                            theme: root.theme
                            primary: true
                            text: "保存区域"
                            enabled: root.workbench.hasProfile
                            Layout.fillWidth: true
                            onClicked: {
                                root.workbench.saveCapture()
                                root.visualAction("scan")
                            }
                        }
                    }
                }
            }
        }
    }
}
