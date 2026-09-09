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
            objectName: "settingsPrimaryPanel"
            theme: root.theme
            motionRole: "primary"
            transitionSerial: root.transitionSerial
            motionEnabled: root.pageMotionEnabled && root.visible
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumWidth: 360

            Flickable {
                id: scheduleFormScroll
                anchors.fill: parent
                contentWidth: width
                contentHeight: scheduleForm.implicitHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                FocusScrollGuard { flickable: scheduleFormScroll }

                ColumnLayout {
                    id: scheduleForm
                    width: parent.width
                    spacing: 12

                    SectionHeader {
                        theme: root.theme
                        title: "扫描调度"
                        meta: "RUNTIME CONFIG"
                        Layout.fillWidth: true
                    }

                    Text {
                        text: "动态 ROI 开关位于 OCR 页；这里仅调整与当前模式对应的调度参数。"
                        color: root.theme.textDim
                        font.family: root.theme.uiFontFor(text)
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }

                    SettingLabel {
                        theme: root.theme
                        title: "画面变化轮询"
                        meta: "FPS"
                        description: "设置画面变化的检查频率。"
                        settingKey: "settings-poll-fps"
                    }
                    NumberStepper {
                        objectName: "settingsCalibrationStepper"
                        theme: root.theme
                        accessibleName: "画面变化轮询频率"
                        settingDescription: "设置画面变化的检查频率。"
                        settingKey: "settings-poll-fps"
                        value: root.workbench.changePollFps
                        minimum: 1
                        maximum: 120
                        suffix: "fps"
                        Layout.fillWidth: true
                        onEdited: value => {
                            root.workbench.setChangePollFps(value)
                            root.visualAction("calibrate")
                        }
                    }

                    SettingLabel {
                        theme: root.theme
                        title: "字幕消失判定"
                        meta: "50—1000 MS"
                        description: "设置字幕多久未更新后被判定为消失。"
                        settingKey: "settings-clear-after"
                    }
                    NumberStepper {
                        theme: root.theme
                        accessibleName: "字幕消失判定时间"
                        settingDescription: "设置字幕多久未更新后被判定为消失。"
                        settingKey: "settings-clear-after"
                        value: root.workbench.clearAfterMs
                        minimum: 50
                        maximum: 1000
                        stepSize: 50
                        suffix: "ms"
                        Layout.fillWidth: true
                        onEdited: value => {
                            root.workbench.setClearAfterMs(value)
                            root.visualAction("calibrate")
                        }
                    }

                    ColumnLayout {
                        objectName: "dynamicRoiSchedule"
                        visible: root.workbench.dynamicRoiEnabled
                        Layout.fillWidth: true
                        spacing: 10
                        SettingLabel {
                            theme: root.theme
                            title: "ROI 响应目标"
                            meta: "100—5000 MS"
                            description: "设置变化区域处理的目标响应时间。"
                            settingKey: "settings-roi-response"
                        }
                        NumberStepper {
                            theme: root.theme
                            accessibleName: "动态 ROI 响应目标"
                            settingDescription: "设置变化区域处理的目标响应时间。"
                            settingKey: "settings-roi-response"
                            value: root.workbench.roiResponseTargetMs
                            minimum: 100
                            maximum: 5000
                            stepSize: 50
                            suffix: "ms"
                            Layout.fillWidth: true
                            onEdited: value => {
                                root.workbench.setRoiResponseTargetMs(value)
                                root.visualAction("calibrate")
                            }
                        }
                    }

                    ColumnLayout {
                        objectName: "fullFrameSchedule"
                        visible: !root.workbench.dynamicRoiEnabled
                        Layout.fillWidth: true
                        spacing: 10

                        SettingLabel {
                            theme: root.theme
                            title: "稳定后复扫"
                            meta: "0—60000 MS"
                            description: "设置画面稳定后再次检查的等待时间。"
                            settingKey: "settings-stable-rescan"
                        }
                        NumberStepper {
                            theme: root.theme
                            accessibleName: "稳定后复扫时间"
                            settingDescription: "设置画面稳定后再次检查的等待时间。"
                            settingKey: "settings-stable-rescan"
                            value: root.workbench.settleRescanMs
                            minimum: 0
                            maximum: 60000
                            stepSize: 100
                            suffix: "ms"
                            Layout.fillWidth: true
                            onEdited: value => {
                                root.workbench.setSettleRescanMs(value)
                                root.visualAction("calibrate")
                            }
                        }
                        SettingLabel {
                            theme: root.theme
                            title: "空闲复扫"
                            meta: "0—60000 MS"
                            description: "设置空闲时再次检查的等待时间。"
                            settingKey: "settings-idle-rescan"
                        }
                        NumberStepper {
                            theme: root.theme
                            accessibleName: "空闲复扫时间"
                            settingDescription: "设置空闲时再次检查的等待时间。"
                            settingKey: "settings-idle-rescan"
                            value: root.workbench.idleRescanMs
                            minimum: 0
                            maximum: 60000
                            stepSize: 100
                            suffix: "ms"
                            Layout.fillWidth: true
                            onEdited: value => {
                                root.workbench.setIdleRescanMs(value)
                                root.visualAction("calibrate")
                            }
                        }
                        SettingLabel {
                            theme: root.theme
                            title: "OCR 冷却"
                            meta: "0—10000 MS"
                            description: "设置两次文字识别之间的最短等待时间。"
                            settingKey: "settings-ocr-cooldown"
                        }
                        NumberStepper {
                            theme: root.theme
                            accessibleName: "OCR 冷却时间"
                            settingDescription: "设置两次文字识别之间的最短等待时间。"
                            settingKey: "settings-ocr-cooldown"
                            value: root.workbench.ocrCooldownMs
                            minimum: 0
                            maximum: 10000
                            stepSize: 50
                            suffix: "ms"
                            Layout.fillWidth: true
                            onEdited: value => {
                                root.workbench.setOcrCooldownMs(value)
                                root.visualAction("calibrate")
                            }
                        }
                    }

                    Text {
                        text: "调度参数只在保存后进入下一次真实运行；工作台不模拟运行效果。"
                        color: root.theme.textDim
                        font.family: root.theme.uiFontFor(text)
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                }
            }
        }

        PrismPanel {
            objectName: "settingsSecondaryPanel"
            theme: root.theme
            raised: true
            motionRole: "secondary"
            transitionSerial: root.transitionSerial
            motionEnabled: root.pageMotionEnabled && root.visible
            Layout.preferredWidth: 410
            Layout.minimumWidth: 370
            Layout.fillHeight: true

            Flickable {
                id: systemFormScroll
                anchors.fill: parent
                contentWidth: width
                contentHeight: systemForm.implicitHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                FocusScrollGuard { flickable: systemFormScroll }

                ColumnLayout {
                    id: systemForm
                    width: parent.width
                    spacing: 12

                    SectionHeader {
                        theme: root.theme
                        title: "输出与诊断"
                        meta: "SYSTEM"
                        Layout.fillWidth: true
                    }

                    SettingLabel {
                        theme: root.theme
                        title: "OBS 浏览器译文源"
                        meta: "OPTIONAL OUTPUT"
                        description: "启用后提供可被 OBS 使用的译文页面。"
                        settingKey: "settings-browser-overlay"
                    }
                    PrismToggle {
                        objectName: "settingsCalibrationAction"
                        theme: root.theme
                        text: "启用浏览器覆盖层"
                        settingDescription: "启用后提供可被 OBS 使用的译文页面。"
                        settingKey: "settings-browser-overlay"
                        checked: root.workbench.browserOverlayEnabled
                        Layout.fillWidth: true
                        onToggled: {
                            root.workbench.setBrowserOverlayEnabled(checked)
                            root.visualAction("calibrate")
                        }
                    }
                    PrismTextField {
                        theme: root.theme
                        accessibleName: "OBS 浏览器译文源"
                        text: root.workbench.browserOverlayUrl
                        readOnly: true
                        selectByMouse: true
                        Layout.fillWidth: true
                    }

                    PrismToggle {
                        theme: root.theme
                        text: "下一次运行显示调试边框"
                        settingDescription: "让下一次运行显示用于排查问题的边框。"
                        settingKey: "settings-debug-border"
                        checked: root.workbench.debugEnabled
                        Layout.fillWidth: true
                        onToggled: {
                            root.workbench.setDebugEnabled(checked)
                            root.visualAction("calibrate")
                        }
                    }
                    Text {
                        text: "调试边框是启动参数，不会伪装成当前运行状态。"
                        color: root.theme.textDim
                        font.family: root.theme.uiFontFor(text)
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }

                    Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: root.theme.line }

                    SettingLabel { theme: root.theme; title: "Profile 诊断"; meta: "REAL CONFIG" }
                    TextArea {
                        Accessible.name: "Profile 诊断"
                        text: root.workbench.infoText
                        readOnly: true
                        selectByMouse: true
                        color: root.theme.textSoft
                        selectionColor: root.theme.accent
                        selectedTextColor: root.theme.ink
                        font.family: root.theme.monoFontFor(text)
                        font.pixelSize: 10
                        wrapMode: TextEdit.Wrap
                        Layout.fillWidth: true
                        Layout.preferredHeight: 158
                        background: Rectangle {
                            color: "transparent"
                            border.color: root.theme.line
                        }
                    }

                    SettingLabel { theme: root.theme; title: "运行日志末尾"; meta: "READ ONLY" }
                    TextArea {
                        Accessible.name: "运行日志末尾"
                        text: root.workbench.logTail
                        readOnly: true
                        selectByMouse: true
                        color: root.theme.textSoft
                        selectionColor: root.theme.accent
                        selectedTextColor: root.theme.ink
                        font.family: root.theme.monoFontFor(text)
                        font.pixelSize: 10
                        wrapMode: TextEdit.WrapAnywhere
                        Layout.fillWidth: true
                        Layout.preferredHeight: 142
                        background: Rectangle {
                            color: "transparent"
                            border.color: root.theme.line
                        }
                    }

                    PrismButton {
                        theme: root.theme
                        text: "刷新诊断与统计"
                        enabled: root.workbench.hasProfile
                        Layout.alignment: Qt.AlignRight
                        onClicked: {
                            root.workbench.refreshStats()
                            root.visualAction("calibrate")
                        }
                    }
                }
            }
        }
    }
}
