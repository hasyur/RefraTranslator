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
    readonly property var themeValues: ["system", "dark", "light"]

    PrismDialog {
        id: createProfileDialog
        objectName: "createProfileDialog"
        surfaceName: "createProfileDialog"
        theme: root.theme
        parent: Overlay.overlay
        anchors.centerIn: parent
        title: "新建游戏配置"
        acceptText: "创建并切换"
        rejectText: "取消"
        acceptEnabled: profileName.text.trim().length > 0
        width: 420

        Text {
            text: "为不同游戏保存独立的区域、术语与提示词。"
            color: root.theme.textSoft
            font.family: root.theme.uiFontFor(text)
            font.pixelSize: 13
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        PrismTextField {
            id: profileName
            objectName: "createProfileNameField"
            theme: root.theme
            accessibleName: "新游戏配置名称"
            placeholderText: "例如：游戏名称"
            Layout.fillWidth: true
            onAccepted: {
                if (createProfileDialog.acceptEnabled)
                    createProfileDialog.accept()
            }
        }

        onOpened: profileName.forceActiveFocus()
        onClosed: profileName.clear()
        onAccepted: root.workbench.createProfile(profileName.text.trim())
    }

    RowLayout {
        anchors.fill: parent
        spacing: 16

        PrismPanel {
            objectName: "homePrimaryPanel"
            theme: root.theme
            motionRole: "primary"
            transitionSerial: root.transitionSerial
            motionEnabled: root.pageMotionEnabled && root.visible
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumWidth: 390

            ColumnLayout {
                anchors.fill: parent
                spacing: 18

                SectionHeader {
                    theme: root.theme
                    title: "光学信号场"
                    meta: "LIVE CONTROL"
                    Layout.fillWidth: true
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 5
                    Text {
                        objectName: "homeRunHero"
                        text: root.workbench.runState
                        color: root.workbench.runTone === "error" ? root.theme.danger
                             : root.workbench.runTone === "warning" ? root.theme.amber
                             : root.workbench.running ? root.theme.accent : root.theme.text
                        font.family: root.theme.displayFontFor(text)
                        font.pixelSize: 34
                        font.weight: Font.DemiBold
                    }
                    Text {
                        text: root.workbench.currentProfileName
                        color: root.theme.textSoft
                        font.family: root.theme.uiFontFor(text)
                        font.pixelSize: 14
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: 118
                    color: "transparent"
                    border.color: root.theme.line

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 16
                        spacing: 10

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 5
                            Text {
                                text: "OCR"
                                color: root.theme.accent
                                font.family: root.theme.monoFontFor(text)
                                font.pixelSize: 10
                                font.letterSpacing: 1
                            }
                            Text {
                                text: root.workbench.ocrStatus
                                color: root.theme.text
                                font.family: root.theme.uiFontFor(text)
                                font.pixelSize: 14
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }
                            Text {
                                text: root.workbench.detectionQualitySummary
                                color: root.theme.textDim
                                font.family: root.theme.monoFontFor(text)
                                font.pixelSize: 10
                            }
                        }

                        Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; color: root.theme.line }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 5
                            Text {
                                text: "TRANSLATION"
                                color: root.theme.spectrum
                                font.family: root.theme.monoFontFor(text)
                                font.pixelSize: 10
                                font.letterSpacing: 1
                            }
                            Text {
                                text: root.workbench.backend === "builtin" ? "内置本地模型" : "外部 API"
                                color: root.theme.text
                                font.family: root.theme.uiFontFor(text)
                                font.pixelSize: 14
                            }
                            Text {
                                text: root.workbench.backend === "builtin" ? root.workbench.builtinModel : root.workbench.model
                                color: root.theme.textDim
                                font.family: root.theme.monoFontFor(text)
                                font.pixelSize: 10
                                elide: Text.ElideMiddle
                                Layout.fillWidth: true
                            }
                        }
                    }
                }

                UnavailableState {
                    objectName: "homeLastRunUnavailable"
                    theme: root.theme
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    visible: !root.workbench.lastRunAvailable
                    eyebrow: "LAST RUN METRICS · UNAVAILABLE"
                    title: "尚无上次运行结果"
                    detail: root.workbench.lastRunStatus
                }

                Rectangle {
                    objectName: "homeLastRunMetrics"
                    visible: root.workbench.lastRunAvailable
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    color: "transparent"
                    border.color: root.theme.line
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 16
                        spacing: 9
                        Text {
                            text: root.workbench.lastRunStatus
                            color: root.theme.accent
                            font.family: root.theme.monoFontFor(text)
                            font.pixelSize: 10
                            Layout.fillWidth: true
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 12
                            ColumnLayout {
                                Layout.fillWidth: true
                                Text {
                                    text: "OCR 峰值"
                                    color: root.theme.textDim
                                    font.family: root.theme.uiFontFor(text)
                                    font.pixelSize: 11
                                }
                                Text {
                                    text: root.workbench.lastRunOcrPeakText
                                    color: root.theme.accent
                                    font.family: root.theme.displayFontFor(text)
                                    font.pixelSize: 25
                                    font.weight: Font.DemiBold
                                }
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                Text {
                                    text: "LLM 峰值"
                                    color: root.theme.textDim
                                    font.family: root.theme.uiFontFor(text)
                                    font.pixelSize: 11
                                }
                                Text {
                                    text: root.workbench.lastRunLlmPeakText
                                    color: root.theme.spectrum
                                    font.family: root.theme.displayFontFor(text)
                                    font.pixelSize: 25
                                    font.weight: Font.DemiBold
                                }
                            }
                        }
                        Text {
                            text: "仅统计上次正常且有效运行；未产生的单项显示“未产生”。"
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

        PrismPanel {
            objectName: "homeSecondaryPanel"
            theme: root.theme
            raised: true
            motionRole: "secondary"
            transitionSerial: root.transitionSerial
            motionEnabled: root.pageMotionEnabled && root.visible
            Layout.preferredWidth: 330
            Layout.minimumWidth: 300
            Layout.fillHeight: true

            ColumnLayout {
                anchors.fill: parent
                spacing: 14

                SectionHeader {
                    theme: root.theme
                    title: "工作台"
                    meta: "PROFILE"
                    Layout.fillWidth: true
                }

                SettingLabel {
                    theme: root.theme
                    title: "当前配置"
                    meta: root.workbench.hasProfile ? root.workbench.currentProfileId : "REQUIRED"
                }
                PrismComboBox {
                    theme: root.theme
                    accessibleName: "当前配置"
                    model: root.workbench.profileNames
                    currentIndex: root.workbench.currentProfileIndex
                    enabled: model.length > 0
                    Layout.fillWidth: true
                    onActivated: index => root.workbench.selectProfile(index)
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    PrismButton {
                        theme: root.theme
                        text: "刷新"
                        Layout.fillWidth: true
                        onClicked: root.workbench.refreshProfiles()
                    }
                    PrismButton {
                        objectName: "openCreateProfileDialogButton"
                        theme: root.theme
                        primary: true
                        text: "新建"
                        Layout.fillWidth: true
                        onClicked: createProfileDialog.open()
                    }
                }

                Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: root.theme.line }

                SettingLabel {
                    theme: root.theme
                    title: "界面主题"
                    meta: "SYSTEM / DARK / LIGHT"
                }
                PrismComboBox {
                    id: themeSelector
                    theme: root.theme
                    accessibleName: "界面主题"
                    model: ["跟随系统", "深色", "浅色"]
                    currentIndex: Math.max(0, root.themeValues.indexOf(root.workbench.themePreference))
                    Layout.fillWidth: true
                    onActivated: index => {
                        if (index >= 0 && index < root.themeValues.length)
                            root.workbench.setTheme(root.themeValues[index])
                    }
                }
                PrismToggle {
                    theme: root.theme
                    text: "减少界面动效"
                    checked: root.workbench.reducedMotion
                    Layout.fillWidth: true
                    onToggled: root.workbench.setReducedMotion(checked)
                }

                Item { Layout.fillHeight: true }

                Text {
                    text: root.workbench.hasProfile
                          ? "配置切换会加载该游戏的真实区域、术语、提示词与缓存统计。"
                          : "先创建配置，之后才能保存区域、术语和人工修订。"
                    color: root.workbench.hasProfile ? root.theme.textDim : root.theme.amber
                    font.family: root.theme.uiFontFor(text)
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }
        }
    }
}
