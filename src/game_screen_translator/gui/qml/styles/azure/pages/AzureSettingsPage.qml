import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
import "../../../components"
import "../components"

Item {
    id: root
    required property var theme
    required property var workbench
    signal visualAction(string action)
    property string selectedParameter: root.workbench.dynamicRoiEnabled
                                        ? "settings-roi-response" : "settings-ocr-cooldown"

    Dialog {
        id: fullDiagnosticsDialog
        objectName: "azureFullDiagnosticsDialog"
        parent: Overlay.overlay
        anchors.centerIn: parent
        modal: true
        width: Math.min(root.width - 42, 1040)
        height: Math.min(root.height - 42, 720)
        title: "完整运行诊断"
        standardButtons: Dialog.NoButton
        background: Rectangle { color: root.theme.white; border.color: root.theme.lineStrong }
        contentItem: ScrollView {
            objectName: "azureFullDiagnosticsScroll"
            clip: true
            contentWidth: availableWidth
            AzureDiagnosticsView {
                theme: root.theme
                workbench: root.workbench
                width: parent.width
            }
        }
        footer: DialogButtonBox {
            alignment: Qt.AlignRight
            AzureButton {
                theme: root.theme
                text: "刷新诊断与统计"
                onClicked: root.workbench.refreshStats()
                DialogButtonBox.buttonRole: DialogButtonBox.ActionRole
            }
            AzureButton {
                theme: root.theme
                text: "关闭"
                primary: true
                DialogButtonBox.buttonRole: DialogButtonBox.RejectRole
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 4

        Item {
            objectName: "azureSettingsHero"
            Layout.fillWidth: true
            Layout.preferredHeight: root.height < 610 ? 132 : 166
            clip: false

            Text {
                objectName: "azureSettingsWordmark"
                x: -4
                y: -45
                width: parent.width * 0.9
                text: "SETTING"
                color: "#9eb7f2"
                font.family: root.theme.displayFontFor(text)
                font.pixelSize: Math.max(70, Math.min(130, parent.width * 0.13))
                font.weight: Font.Black
                font.letterSpacing: -5
                rotation: -5
                opacity: 0.38
            }
            Rectangle {
                x: parent.width * 0.27
                y: parent.height * 0.67
                width: parent.width * 0.73
                height: 23
                rotation: -15
                color: root.theme.spectrum
                opacity: 0.82
            }
            Image {
                objectName: "azureSettingsHeroine"
                source: Qt.resolvedUrl("../assets/heroine-settings.png")
                sourceSize.width: 980
                sourceSize.height: 700
                fillMode: Image.PreserveAspectFit
                horizontalAlignment: Image.AlignRight
                verticalAlignment: Image.AlignTop
                x: parent.width * 0.44
                y: -2
                width: parent.width * 0.68
                height: root.height < 610 ? 255 : 320
                asynchronous: true
                smooth: true
                visible: status === Image.Ready
                z: 2
            }
            ColumnLayout {
                x: 16
                y: 8
                spacing: 0
                z: 3
                Text {
                    text: "07  /  SYSTEM CONFIGURATION"
                    color: root.theme.accentText
                    font.family: root.theme.monoFontFor(text)
                    font.pixelSize: 10
                    font.letterSpacing: 0.7
                }
                Text {
                    text: "设置"
                    color: root.theme.text
                    font.family: root.theme.displayFontFor(text)
                    font.pixelSize: root.height < 610 ? 42 : 50
                    font.weight: Font.Black
                }
                Text {
                    text: "运行参数与诊断"
                    color: root.theme.textSoft
                    font.family: root.theme.uiFontFor(text)
                    font.pixelSize: 12
                }
            }
        }

        RowLayout {
            objectName: "azureSettingsWorkArea"
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 10

            Item {
                objectName: "azureSettingsFormPanel"
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.preferredWidth: 1.13
                Layout.minimumWidth: 330
                Flickable {
                    id: settingsFormScroll
                    objectName: "azureSettingsFormScroll"
                    anchors.fill: parent
                    contentWidth: width
                    contentHeight: settingsForm.implicitHeight
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                    FocusScrollGuard { flickable: settingsFormScroll }
                    ColumnLayout {
                        id: settingsForm
                        width: settingsFormScroll.width - 5
                        spacing: 7

                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                text: "01"
                                color: root.theme.accent
                                font.family: root.theme.displayFontFor(text)
                                font.pixelSize: 27
                                font.weight: Font.Black
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: -1
                                Text {
                                    text: "扫描调度"
                                    color: root.theme.text
                                    font.family: root.theme.displayFontFor(text)
                                    font.pixelSize: 17
                                    font.weight: Font.Bold
                                }
                                Text {
                                    text: "触发方式在 OCR 页选择；此处调整对应参数。"
                                    color: root.theme.textDim
                                    font.family: root.theme.uiFontFor(text)
                                    font.pixelSize: 10
                                    wrapMode: Text.WordWrap
                                    Layout.fillWidth: true
                                }
                            }
                            Text {
                                text: root.workbench.triggerMethodIndex === 2 ? "鼠标停留"
                                    : root.workbench.dynamicRoiEnabled ? "动态 ROI" : "整帧处理"
                                color: root.theme.accentText
                                font.family: root.theme.monoFontFor(text)
                                font.pixelSize: 10
                            }
                        }

                        AzureNumberSetting {
                            objectName: "azureSettingsPollFpsRow"
                            visible: root.workbench.triggerMethodIndex !== 2
                            theme: root.theme
                            title: "画面变化轮询"
                            description: "检查频率"
                            value: root.workbench.changePollFps
                            minimum: 1; maximum: 120; suffix: "fps"
                            settingKey: "settings-poll-fps"
                            stagger: 0
                            highlighted: root.selectedParameter === settingKey
                            onActivated: key => root.selectedParameter = key
                            onEdited: value => {
                                root.workbench.setChangePollFps(value)
                                root.visualAction("calibrate")
                            }
                        }
                        AzureNumberSetting {
                            objectName: "azureSettingsClearAfterRow"
                            visible: root.workbench.triggerMethodIndex !== 2
                            theme: root.theme
                            title: "字幕消失判定"
                            description: "判定字幕未更新的等待时间"
                            value: root.workbench.clearAfterMs
                            minimum: 50; maximum: 1000; stepSize: 50; suffix: "ms"
                            settingKey: "settings-clear-after"
                            stagger: 12
                            highlighted: root.selectedParameter === settingKey
                            onActivated: key => root.selectedParameter = key
                            onEdited: value => {
                                root.workbench.setClearAfterMs(value)
                                root.visualAction("calibrate")
                            }
                        }
                        AzureNumberSetting {
                            objectName: "azureSettingsRoiResponseRow"
                            visible: root.workbench.dynamicRoiEnabled
                            theme: root.theme
                            title: "ROI 响应目标"
                            description: "变化区域处理目标时间"
                            value: root.workbench.roiResponseTargetMs
                            minimum: 100; maximum: 5000; stepSize: 50; suffix: "ms"
                            settingKey: "settings-roi-response"
                            stagger: 24
                            highlighted: root.selectedParameter === settingKey
                            onActivated: key => root.selectedParameter = key
                            onEdited: value => {
                                root.workbench.setRoiResponseTargetMs(value)
                                root.visualAction("calibrate")
                            }
                        }
                        AzureNumberSetting {
                            objectName: "azureSettingsStableRescanRow"
                            visible: !root.workbench.dynamicRoiEnabled
                            theme: root.theme
                            title: "稳定后复扫"
                            description: "画面稳定后再次检查"
                            value: root.workbench.settleRescanMs
                            maximum: 60000; stepSize: 100; suffix: "ms"
                            settingKey: "settings-stable-rescan"
                            stagger: 24
                            highlighted: root.selectedParameter === settingKey
                            onActivated: key => root.selectedParameter = key
                            onEdited: value => {
                                root.workbench.setSettleRescanMs(value)
                                root.visualAction("calibrate")
                            }
                        }
                        AzureNumberSetting {
                            objectName: "azureSettingsIdleRescanRow"
                            visible: !root.workbench.dynamicRoiEnabled
                            theme: root.theme
                            title: "空闲复扫"
                            description: "空闲时再次检查"
                            value: root.workbench.idleRescanMs
                            maximum: 60000; stepSize: 100; suffix: "ms"
                            settingKey: "settings-idle-rescan"
                            stagger: 36
                            highlighted: root.selectedParameter === settingKey
                            onActivated: key => root.selectedParameter = key
                            onEdited: value => {
                                root.workbench.setIdleRescanMs(value)
                                root.visualAction("calibrate")
                            }
                        }
                        AzureNumberSetting {
                            objectName: "azureSettingsOcrCooldownRow"
                            visible: !root.workbench.dynamicRoiEnabled
                            theme: root.theme
                            title: "OCR 冷却"
                            description: "两次识别之间的最短等待时间"
                            value: root.workbench.ocrCooldownMs
                            maximum: 10000; stepSize: 50; suffix: "ms"
                            settingKey: "settings-ocr-cooldown"
                            stagger: 48
                            highlighted: root.selectedParameter === settingKey
                            onActivated: key => root.selectedParameter = key
                            onEdited: value => {
                                root.workbench.setOcrCooldownMs(value)
                                root.visualAction("calibrate")
                            }
                        }
                        Text {
                            text: "保存后在下一次运行生效。"
                            color: root.theme.textDim
                            font.family: root.theme.uiFontFor(text)
                            font.pixelSize: 10
                        }
                        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: root.theme.line }
                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                text: "02"
                                color: root.theme.spectrumText
                                font.family: root.theme.displayFontFor(text)
                                font.pixelSize: 25
                                font.weight: Font.Black
                            }
                            Text {
                                text: "输出与调试"
                                color: root.theme.text
                                font.family: root.theme.displayFontFor(text)
                                font.pixelSize: 16
                                font.weight: Font.Bold
                                Layout.fillWidth: true
                            }
                            Text {
                                text: "OBS"
                                color: root.theme.spectrumText
                                font.family: root.theme.monoFontFor(text)
                                font.pixelSize: 10
                            }
                        }
                        AzureToggle {
                            objectName: "azureSettingsDebugToggle"
                            theme: root.theme
                            text: "下一次运行显示调试边框"
                            description: "显示用于排查问题的边框。"
                            checked: root.workbench.debugEnabled
                            Layout.fillWidth: true
                            onToggled: {
                                root.workbench.setDebugEnabled(checked)
                                root.visualAction("calibrate")
                            }
                        }
                        AzureToggle {
                            objectName: "azureSettingsBrowserOverlayToggle"
                            theme: root.theme
                            text: "启用 OBS 浏览器覆盖层"
                            description: "提供可供 OBS 使用的译文页面。"
                            checked: root.workbench.browserOverlayEnabled
                            Layout.fillWidth: true
                            onToggled: {
                                root.workbench.setBrowserOverlayEnabled(checked)
                                root.visualAction("calibrate")
                            }
                        }
                        AzureTextField {
                            objectName: "azureSettingsBrowserOverlayUrl"
                            theme: root.theme
                            Accessible.name: "OBS 浏览器译文源"
                            text: root.workbench.browserOverlayUrl
                            readOnly: true
                            selectByMouse: true
                            Layout.fillWidth: true
                        }
                    }
                }
            }

            Item {
                objectName: "azureSettingsDiagnosticsPanel"
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.preferredWidth: 0.87
                Layout.minimumWidth: 285
                Layout.topMargin: 88
                Shape {
                    id: diagnosticsBackdrop
                    anchors.fill: parent
                    antialiasing: true
                    ShapePath {
                        fillColor: root.theme.dark ? "#172c5a" : "#eaf0ff"
                        strokeWidth: 0
                        startX: 24; startY: 0
                        PathLine { x: diagnosticsBackdrop.width; y: 0 }
                        PathLine { x: diagnosticsBackdrop.width; y: diagnosticsBackdrop.height - 20 }
                        PathLine { x: diagnosticsBackdrop.width - 20; y: diagnosticsBackdrop.height }
                        PathLine { x: 0; y: diagnosticsBackdrop.height }
                        PathLine { x: 0; y: 24 }
                        PathLine { x: 24; y: 0 }
                    }
                }
                Rectangle {
                    x: 0
                    y: 20
                    width: 3
                    height: Math.max(80, parent.height - 20)
                    color: root.theme.spectrum
                }
                Column {
                    id: diagnosticsColumn
                    anchors.fill: parent
                    anchors.leftMargin: 16
                    anchors.rightMargin: 8
                    anchors.topMargin: 8
                    anchors.bottomMargin: 8
                    spacing: 7
                    RowLayout {
                        id: diagnosticsHeading
                        width: diagnosticsColumn.width
                        height: 48
                        Text {
                            text: "03"
                            color: root.theme.accent
                            font.family: root.theme.displayFontFor(text)
                            font.pixelSize: 28
                            font.weight: Font.Black
                        }
                        ColumnLayout {
                            spacing: -1
                            Layout.fillWidth: true
                            Text {
                                text: "运行诊断"
                                color: root.theme.text
                                font.family: root.theme.displayFontFor(text)
                                font.pixelSize: 17
                                font.weight: Font.Bold
                            }
                            Text {
                                text: "完整 Profile · OCR · 翻译 · 汇总"
                                color: root.theme.textDim
                                font.family: root.theme.monoFontFor(text)
                                font.pixelSize: 9
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }
                        }
                    }
                    Flickable {
                        id: diagnosticsScroll
                        objectName: "azureSettingsDiagnosticsScroll"
                        width: diagnosticsColumn.width
                        height: Math.max(90, diagnosticsColumn.height
                                         - diagnosticsHeading.height
                                         - diagnosticsActions.height
                                         - diagnosticsColumn.spacing * 2)
                        contentWidth: width
                        contentHeight: embeddedDiagnostics.implicitHeight
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                        AzureDiagnosticsView {
                            id: embeddedDiagnostics
                            theme: root.theme
                            workbench: root.workbench
                            width: diagnosticsScroll.width
                        }
                    }
                    RowLayout {
                        id: diagnosticsActions
                        width: diagnosticsColumn.width
                        height: 42
                        spacing: 6
                        AzureButton {
                            objectName: "azureSettingsRefreshDiagnostics"
                            theme: root.theme
                            text: "刷新"
                            quiet: true
                            Layout.fillWidth: true
                            Layout.minimumWidth: 66
                            Layout.preferredHeight: 42
                            enabled: root.workbench.hasProfile
                            onClicked: root.workbench.refreshStats()
                        }
                        AzureButton {
                            objectName: "azureSettingsExpandDiagnostics"
                            theme: root.theme
                            text: "展开完整诊断 ↗"
                            primary: true
                            Layout.fillWidth: true
                            Layout.minimumWidth: 100
                            Layout.preferredHeight: 42
                            onClicked: fullDiagnosticsDialog.open()
                        }
                    }
                }
            }
        }
    }
}
