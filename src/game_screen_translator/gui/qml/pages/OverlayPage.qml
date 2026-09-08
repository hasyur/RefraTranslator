import QtQuick
import QtQuick.Layouts
import "../components"

Item {
    id: root

    required property var theme
    required property var workbench
    property int transitionSerial: 0
    property bool pageMotionEnabled: false
    signal visualAction(string action)

    RowLayout {
        anchors.fill: parent
        spacing: 16

        PrismPanel {
            objectName: "overlayPrimaryPanel"
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
                    title: "覆盖层投影"
                    meta: "RUNTIME VIEW"
                    Layout.fillWidth: true
                }

                UnavailableState {
                    objectName: "overlayLastRunUnavailable"
                    theme: root.theme
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    visible: !root.workbench.lastRunAvailable
                    eyebrow: "LAST RUN OVERLAY · UNAVAILABLE"
                    title: "尚无上次覆盖结果"
                    detail: root.workbench.lastRunStatus
                }

                Item {
                    id: lastRunCanvas
                    objectName: "overlayLastRunCanvas"
                    visible: root.workbench.lastRunAvailable
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    property real canvasWidth: root.workbench.lastRunCanvasWidth > 0
                                               ? root.workbench.lastRunCanvasWidth : 16
                    property real canvasHeight: root.workbench.lastRunCanvasHeight > 0
                                                ? root.workbench.lastRunCanvasHeight : 9
                    Rectangle {
                        id: overlayCanvas
                        objectName: "overlayCanvas"
                        anchors.centerIn: parent
                        property real fitScale: Math.min(
                            lastRunCanvas.width / lastRunCanvas.canvasWidth,
                            lastRunCanvas.height / lastRunCanvas.canvasHeight
                        )
                        width: Math.max(1, lastRunCanvas.canvasWidth * fitScale)
                        height: Math.max(1, lastRunCanvas.canvasHeight * fitScale)
                        color: root.theme.dark ? "#141b24" : "#edf2f4"
                        border.color: root.theme.lineStrong
                        clip: true

                        Repeater {
                            model: root.workbench.lastRunOverlayResults
                            Rectangle {
                                objectName: "overlayLastRunEntry"
                                required property var modelData
                                readonly property real maskOpacity: root.workbench.overlayOpacity
                                x: modelData.left * overlayCanvas.width / lastRunCanvas.canvasWidth
                                y: modelData.top * overlayCanvas.height / lastRunCanvas.canvasHeight
                                width: Math.max(2, (modelData.right - modelData.left)
                                                   * overlayCanvas.width / lastRunCanvas.canvasWidth)
                                height: Math.max(2, (modelData.bottom - modelData.top)
                                                    * overlayCanvas.height / lastRunCanvas.canvasHeight)
                                color: Qt.rgba(0, 0, 0, maskOpacity)
                                border.color: root.theme.accent
                                border.width: 1
                                Text {
                                    anchors.fill: parent
                                    anchors.margins: 3
                                    text: modelData.translatedText
                                    color: root.theme.text
                                    font.family: root.theme.uiFontFor(text)
                                    font.pixelSize: Math.max(9, Math.min(16, parent.height * 0.42))
                                    elide: Text.ElideRight
                                    verticalAlignment: Text.AlignVCenter
                                }
                            }
                        }
                    }
                }

                Text {
                    text: root.workbench.overlayStatus
                    color: root.theme.textSoft
                    font.family: root.theme.uiFontFor(text)
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }
        }

        PrismPanel {
            objectName: "overlaySecondaryPanel"
            theme: root.theme
            raised: true
            motionRole: "secondary"
            transitionSerial: root.transitionSerial
            motionEnabled: root.pageMotionEnabled && root.visible
            Layout.preferredWidth: 344
            Layout.minimumWidth: 310
            Layout.fillHeight: true

            ColumnLayout {
                anchors.fill: parent
                spacing: 14

                SectionHeader {
                    theme: root.theme
                    title: "画面合成"
                    meta: "PREVIEW WINDOW"
                    Layout.fillWidth: true
                }

                SettingLabel { theme: root.theme; title: "背景处理"; meta: "0—100%" }
                PrismSlider {
                    id: overlayOpacitySlider
                    objectName: "overlayProjectionAction"
                    property bool changedDuringGesture: false
                    theme: root.theme
                    accessibleName: "黑色遮罩强度"
                    from: 0
                    to: 1
                    stepSize: 0.01
                    value: root.workbench.overlayOpacity
                    Layout.fillWidth: true
                    onMoved: {
                        root.workbench.setOverlayOpacity(value)
                        if (pressed)
                            changedDuringGesture = true
                    }
                    onPressedChanged: {
                        if (pressed) {
                            changedDuringGesture = false
                        } else if (changedDuringGesture) {
                            changedDuringGesture = false
                            root.visualAction("projection")
                        }
                    }
                }
                Text {
                    text: "0% 仅模糊；1–100% 在模糊背景上叠加对应强度的黑色遮罩。"
                    color: root.theme.textDim
                    font.family: root.theme.uiFontFor(text)
                    font.pixelSize: 11
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }

                Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: root.theme.line }

                SettingLabel { theme: root.theme; title: "当前黑色遮罩"; meta: "CONFIGURED VALUE" }
                Text {
                    objectName: "overlayOpacityValue"
                    text: Math.round(root.workbench.overlayOpacity * 100) + "%"
                    color: root.theme.accent
                    font.family: root.theme.displayFontFor(text)
                    font.pixelSize: 38
                    font.weight: Font.DemiBold
                }
                Text {
                    text: "拖动只更新草稿；点顶部“应用更改”后才写入运行配置。"
                    color: root.theme.textSoft
                    font.family: root.theme.uiFontFor(text)
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }

                Item { Layout.fillHeight: true }

                Text {
                    text: "OBS 浏览器源设置集中在 SETTINGS 页面。"
                    color: root.theme.textDim
                    font.family: root.theme.monoFontFor(text)
                    font.pixelSize: 10
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }
        }
    }
}
