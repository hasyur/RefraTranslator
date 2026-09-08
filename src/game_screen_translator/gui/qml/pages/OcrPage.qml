import QtQuick
import QtQuick.Controls
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
            objectName: "ocrPrimaryPanel"
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
                    title: "识别输出"
                    meta: "RUNTIME VIEW"
                    Layout.fillWidth: true
                }

                UnavailableState {
                    objectName: "ocrLastRunUnavailable"
                    theme: root.theme
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    visible: !root.workbench.lastRunAvailable
                    eyebrow: "LAST RUN OCR · UNAVAILABLE"
                    title: "尚无上次运行结果"
                    detail: root.workbench.lastRunStatus
                }

                Flickable {
                    objectName: "ocrLastRunList"
                    visible: root.workbench.lastRunAvailable
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    contentWidth: width
                    contentHeight: ocrLastRunColumn.implicitHeight
                    clip: true
                    ColumnLayout {
                        id: ocrLastRunColumn
                        width: parent.width
                        spacing: 8
                        Text {
                            text: root.workbench.lastRunStatus
                            color: root.theme.accent
                            font.family: root.theme.monoFontFor(text)
                            font.pixelSize: 10
                            Layout.fillWidth: true
                        }
                        Repeater {
                            model: root.workbench.lastRunOcrResults
                            Rectangle {
                                required property var modelData
                                Layout.fillWidth: true
                                implicitHeight: 68
                                color: "transparent"
                                border.color: root.theme.line
                                ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: 10
                                    spacing: 3
                                    Text {
                                        text: modelData.sourceText
                                        color: root.theme.text
                                        font.family: root.theme.uiFontFor(text)
                                        font.pixelSize: 14
                                        elide: Text.ElideRight
                                        Layout.fillWidth: true
                                    }
                                    Text {
                                        text: "置信度 " + Number(modelData.confidence).toFixed(2)
                                              + " · 位置 " + modelData.left + "," + modelData.top
                                              + " — " + modelData.right + "," + modelData.bottom
                                        color: root.theme.textDim
                                        font.family: root.theme.monoFontFor(text)
                                        font.pixelSize: 10
                                        Layout.fillWidth: true
                                    }
                                }
                            }
                        }
                    }
                }

                Text {
                    text: "工作台只呈现控制器提供的状态；不会用示例字幕、置信度或耗时填充这里。"
                    color: root.theme.textDim
                    font.family: root.theme.uiFontFor(text)
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }
        }

        PrismPanel {
            objectName: "ocrSecondaryPanel"
            theme: root.theme
            raised: true
            motionRole: "secondary"
            transitionSerial: root.transitionSerial
            motionEnabled: root.pageMotionEnabled && root.visible
            Layout.preferredWidth: 354
            Layout.minimumWidth: 320
            Layout.fillHeight: true

            Flickable {
                id: ocrFormScroll
                anchors.fill: parent
                contentWidth: width
                contentHeight: form.implicitHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                FocusScrollGuard { flickable: ocrFormScroll }

                ColumnLayout {
                    id: form
                    width: parent.width
                    spacing: 13

                    SectionHeader {
                        theme: root.theme
                        title: "OCR 管线"
                        meta: root.workbench.ocrStatus
                        Layout.fillWidth: true
                    }

                    SettingLabel { theme: root.theme; title: "计算设备"; meta: "ISOLATED PROBE" }
                    PrismComboBox {
                        id: deviceSelector
                        theme: root.theme
                        accessibleName: "OCR 计算设备"
                        model: root.workbench.ocrDeviceNames
                        itemEnabled: root.workbench.ocrDeviceAvailability
                        currentIndex: Math.max(0, root.workbench.ocrDeviceValues.indexOf(root.workbench.ocrDevice))
                        enabled: model.length > 0
                        Layout.fillWidth: true
                        onActivated: index => {
                            if (index >= 0 && index < root.workbench.ocrDeviceValues.length) {
                                root.workbench.setOcrDevice(root.workbench.ocrDeviceValues[index])
                                root.visualAction("focus")
                            }
                        }
                    }
                    PrismButton {
                        objectName: "ocrProbeAction"
                        theme: root.theme
                        text: "重新探测设备"
                        Layout.fillWidth: true
                        onClicked: {
                            root.workbench.probeOcrDevices()
                            root.visualAction("focus")
                        }
                    }

                    Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: root.theme.line }

                    SettingLabel {
                        theme: root.theme
                        title: "检测质量"
                        meta: root.workbench.detectionQualitySummary
                    }
                    PrismSlider {
                        id: ocrQualitySlider
                        objectName: "ocrQualitySlider"
                        property bool changedDuringGesture: false
                        theme: root.theme
                        accessibleName: "OCR 检测质量"
                        from: 0
                        to: Math.max(0, root.workbench.detectionQualityNames.length - 1)
                        stepSize: 1
                        value: root.workbench.detectionQualityIndex
                        Layout.fillWidth: true
                        onMoved: {
                            root.workbench.setDetectionQualityIndex(Math.round(value))
                            if (pressed)
                                changedDuringGesture = true
                        }
                        onPressedChanged: {
                            if (pressed) {
                                changedDuringGesture = false
                            } else if (changedDuringGesture) {
                                changedDuringGesture = false
                                root.visualAction("focus")
                            }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 7
                        Repeater {
                            model: root.workbench.detectionQualityNames
                            Text {
                                required property int index
                                required property var modelData
                                text: String(modelData)
                                color: index === root.workbench.detectionQualityIndex
                                       ? root.theme.accent : root.theme.textDim
                                font.family: root.theme.uiFontFor(text)
                                font.pixelSize: 11
                                horizontalAlignment: Text.AlignHCenter
                                Layout.fillWidth: true
                            }
                        }
                    }

                    PrismToggle {
                        theme: root.theme
                        text: "启用文本过滤"
                        checked: root.workbench.ocrFilterEnabled
                        Layout.fillWidth: true
                        onToggled: {
                            root.workbench.setOcrFilterEnabled(checked)
                            root.visualAction("focus")
                        }
                    }
                    PrismToggle {
                        objectName: "textMergeToggle"
                        theme: root.theme
                        text: root.workbench.textMergeAllowed ? "合并相邻文本块" : "合并文本块（当前质量不可用）"
                        checked: root.workbench.ocrMergeEnabled
                        enabled: root.workbench.textMergeAllowed
                        Layout.fillWidth: true
                        onToggled: {
                            root.workbench.setOcrMergeEnabled(checked)
                            root.visualAction("focus")
                        }
                    }

                    Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: root.theme.line }

                    SettingLabel { theme: root.theme; title: "变化检测"; meta: "DYNAMIC ROI" }
                    PrismToggle {
                        theme: root.theme
                        text: "只识别发生变化的区域"
                        checked: root.workbench.dynamicRoiEnabled
                        Layout.fillWidth: true
                        onToggled: {
                            root.workbench.setDynamicRoiEnabled(checked)
                            root.visualAction("focus")
                        }
                    }

                    Item { Layout.fillHeight: true; Layout.minimumHeight: 6 }

                    Text {
                        text: "参数修改后由顶部“应用更改”统一校验并写入运行配置。"
                        color: root.theme.textDim
                        font.family: root.theme.uiFontFor(text)
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                }
            }
        }
    }
}
