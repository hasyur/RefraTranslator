import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"
import "../../../shared" as Shared

Item {
    id: root

    required property var theme
    required property var workbench
    required property var appShell
    property int transitionSerial: 0
    property bool pageMotionEnabled: false
    readonly property var diagnostics: root.workbench.latencyDiagnostics
    signal visualAction(string action)
    property alias scheduleScroll: scheduleFormScroll
    property alias profileDiagnosticScroll: profileScroll.contentItem
    property alias latencyDiagnosticScroll: logScroll.contentItem

    RowLayout {
        anchors.fill: parent
        spacing: 16 
        PrismPanel {
            objectName: root.theme.active ? ("settingsPrimaryPanel") : ""
            theme: root.theme
            rightPadding: padding 
            motionRole: "primary"
            transitionSerial: root.transitionSerial
            motionEnabled: root.pageMotionEnabled && root.visible
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumWidth: 360

            Flickable {
                id: scheduleFormScroll
                onContentYChanged: {
                    if (scheduleScrollSync.active && !scheduleScrollSync.restoring
                            && root.workbench.currentPage === "SETTINGS")
                        root.appShell.rememberScrollPosition(
                            "SETTINGS", "scheduleForm", contentY
                        )
                }
                Shared.ScrollPositionSync {
                    id: scheduleScrollSync
                    appShell: root.appShell
                    flickable: scheduleFormScroll
                    pageKey: "SETTINGS"
                    scrollKey: "scheduleForm"
                    active: root.theme.active && root.visible
                            && root.workbench.currentPage === "SETTINGS"
                }
                objectName: root.theme.active ? ("settingsFormScroll") : ""
                anchors.fill: parent
                contentWidth: width
                contentHeight: scheduleForm.implicitHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: PrismScrollBar { id: scheduleBar; theme: root.theme }

                FocusScrollGuard { flickable: scheduleFormScroll }

                ColumnLayout {
                    id: scheduleForm
                    width: parent.width - scheduleBar.contentInset
                    spacing: 12

                    SectionHeader {
                        theme: root.theme
                        title: "扫描调度"
                        meta: "RUNTIME CONFIG"
                        Layout.fillWidth: true
                    }

                    Text {
                        text: root.workbench.triggerMethodIndex === 2
                              ? "触发方式在 OCR 页选择。鼠标模式仅在触发后推进 ROI 处理，等待期间保留上次译文。"
                              : "触发方式在 OCR 页选择；这里调整与当前方式对应的调度参数。"
                        color: root.theme.textDim
                        font.family: root.theme.uiFontFor(text)
                        font.pixelSize: 13
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }

                    SettingLabel {
                        objectName: root.theme.active ? ("settingsPollLegacyLabel") : ""
                        theme: root.theme
                        visible: !false && root.workbench.triggerMethodIndex !== 2
                        title: "画面变化轮询"
                        meta: "FPS"
                        description: "设置画面变化的检查频率。"
                        settingKey: "settings-poll-fps"
                    }
                    NumberStepper {
                        objectName: root.theme.active ? ("settingsCalibrationStepper") : ""
                        visible: root.workbench.triggerMethodIndex !== 2
                        theme: root.theme
                        accessibleName: "画面变化轮询频率"
                        settingDescription: "设置画面变化的检查频率。"
                        settingKey: "settings-poll-fps"
                        rowTitle: "画面变化轮询"
                        rowMeta: "FPS"
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
                        objectName: root.theme.active ? ("settingsClearAfterLegacyLabel") : ""
                        theme: root.theme
                        visible: !false && root.workbench.triggerMethodIndex !== 2
                        title: "字幕消失判定"
                        meta: "50—1000 MS"
                        description: "设置字幕多久未更新后被判定为消失。"
                        settingKey: "settings-clear-after"
                    }
                    NumberStepper {
                        objectName: root.theme.active ? ("settingsClearAfterStepper") : ""
                        theme: root.theme
                        accessibleName: "字幕消失判定时间"
                        visible: root.workbench.triggerMethodIndex !== 2
                        settingDescription: "设置字幕多久未更新后被判定为消失。"
                        settingKey: "settings-clear-after"
                        rowTitle: "字幕消失判定"
                        rowMeta: "50—1000 MS"
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
                        objectName: root.theme.active ? ("dynamicRoiSchedule") : ""
                        visible: root.workbench.dynamicRoiEnabled
                        Layout.fillWidth: true
                        spacing: 10
                        SettingLabel {
                            objectName: root.theme.active ? ("settingsRoiLegacyLabel") : ""
                            theme: root.theme
                            visible: !false
                            title: "ROI 响应目标"
                            meta: "100—5000 MS"
                            description: "设置变化区域处理的目标响应时间。"
                            settingKey: "settings-roi-response"
                        }
                        NumberStepper {
                            objectName: root.theme.active ? ("settingsRoiResponseStepper") : ""
                            theme: root.theme
                            accessibleName: "动态 ROI 响应目标"
                            settingDescription: "设置变化区域处理的目标响应时间。"
                            settingKey: "settings-roi-response"
                            rowTitle: "ROI 响应目标"
                            rowMeta: "100—5000 MS"
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
                        objectName: root.theme.active ? ("fullFrameSchedule") : ""
                        visible: !root.workbench.dynamicRoiEnabled
                        Layout.fillWidth: true
                        spacing: 10

                        SettingLabel {
                            objectName: root.theme.active ? ("settingsStableRescanLegacyLabel") : ""
                            theme: root.theme
                            visible: !false
                            title: "稳定后复扫"
                            meta: "0—60000 MS"
                            description: "设置画面稳定后再次检查的等待时间。"
                            settingKey: "settings-stable-rescan"
                        }
                        NumberStepper {
                            objectName: root.theme.active ? ("settingsStableRescanStepper") : ""
                            theme: root.theme
                            accessibleName: "稳定后复扫时间"
                            settingDescription: "设置画面稳定后再次检查的等待时间。"
                            settingKey: "settings-stable-rescan"
                            rowTitle: "稳定后复扫"
                            rowMeta: "0—60000 MS"
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
                            objectName: root.theme.active ? ("settingsIdleRescanLegacyLabel") : ""
                            theme: root.theme
                            visible: !false
                            title: "空闲复扫"
                            meta: "0—60000 MS"
                            description: "设置空闲时再次检查的等待时间。"
                            settingKey: "settings-idle-rescan"
                        }
                        NumberStepper {
                            objectName: root.theme.active ? ("settingsIdleRescanStepper") : ""
                            theme: root.theme
                            accessibleName: "空闲复扫时间"
                            settingDescription: "设置空闲时再次检查的等待时间。"
                            settingKey: "settings-idle-rescan"
                            rowTitle: "空闲复扫"
                            rowMeta: "0—60000 MS"
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
                            objectName: root.theme.active ? ("settingsOcrCooldownLegacyLabel") : ""
                            theme: root.theme
                            visible: !false
                            title: "OCR 冷却"
                            meta: "0—10000 MS"
                            description: "设置两次文字识别之间的最短等待时间。"
                            settingKey: "settings-ocr-cooldown"
                        }
                        NumberStepper {
                            objectName: root.theme.active ? ("settingsOcrCooldownStepper") : ""
                            theme: root.theme
                            accessibleName: "OCR 冷却时间"
                            settingDescription: "设置两次文字识别之间的最短等待时间。"
                            settingKey: "settings-ocr-cooldown"
                            rowTitle: "OCR 冷却"
                            rowMeta: "0—10000 MS"
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
                        text: "调度参数保存后在下一次运行生效。"
                        color: root.theme.textDim
                        font.family: root.theme.uiFontFor(text)
                        font.pixelSize: 13
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }

                    ColumnLayout {
                        objectName: root.theme.active ? ("settingsOutputGroup") : ""
                        Layout.fillWidth: true
                        Layout.topMargin: 8
                        spacing: 8

                        SectionHeader {
                            theme: root.theme
                            title: "输出与调试"
                            meta: "OUTPUT CONFIG"
                            Layout.fillWidth: true
                        }

                        PrismToggle {
                            objectName: root.theme.active ? ("settingsDebugToggle") : ""
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
                            text: "调试边框设置保存后在下一次运行生效。"
                            color: root.theme.textDim
                            font.family: root.theme.uiFontFor(text)
                            font.pixelSize: 13
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }

                        SettingLabel {
                            theme: root.theme
                            title: "OBS 浏览器译文源"
                            meta: "OPTIONAL OUTPUT"
                            description: "启用后提供可被 OBS 使用的译文页面。"
                            settingKey: "settings-browser-overlay"
                            Layout.topMargin: 4
                        }
                        PrismToggle {
                            objectName: root.theme.active ? ("settingsCalibrationAction") : ""
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
                            objectName: root.theme.active ? ("settingsBrowserOverlayUrl") : ""
                            theme: root.theme
                            accessibleName: "OBS 浏览器译文源"
                            text: root.workbench.browserOverlayUrl
                            readOnly: true
                            selectByMouse: true
                            Layout.fillWidth: true
                        }
                    }
                }
            }
        }

        PrismPanel {
            objectName: root.theme.active ? ("settingsSecondaryPanel") : ""
            theme: root.theme
            raised: true
            motionRole: "secondary"
            transitionSerial: root.transitionSerial
            motionEnabled: root.pageMotionEnabled && root.visible
            Layout.fillWidth: true
            Layout.preferredWidth: 410
            Layout.maximumWidth: 410
            Layout.minimumWidth: 370
            Layout.fillHeight: true

            ColumnLayout {
                anchors.fill: parent
                spacing: 12

                SectionHeader {
                    theme: root.theme
                    title: "日志与诊断"
                    meta: "DIAGNOSTICS"
                    Layout.fillWidth: true
                }

                SettingLabel { theme: root.theme; title: "Profile 诊断"; meta: "REAL CONFIG" }
                ScrollView {
                    id: profileScroll
                    Connections {
                        target: profileScroll.contentItem
                        function onContentYChanged() {
                            if (profileScrollSync.active && !profileScrollSync.restoring
                                    && root.workbench.currentPage === "SETTINGS")
                                root.appShell.rememberScrollPosition(
                                    "SETTINGS", "profileDiagnostics",
                                    profileScroll.contentItem.contentY
                                )
                        }
                    }
                    Shared.ScrollPositionSync {
                        id: profileScrollSync
                        appShell: root.appShell
                        flickable: profileScroll.contentItem
                        pageKey: "SETTINGS"
                        scrollKey: "profileDiagnostics"
                        active: root.theme.active && root.visible
                                && root.workbench.currentPage === "SETTINGS"
                    }
                    objectName: root.theme.active ? ("settingsProfileScroll") : ""
                    contentWidth: availableWidth
                    clip: true
                    Layout.fillWidth: true
                    Layout.minimumHeight: 110
                    Layout.preferredHeight: 158
                    Layout.maximumHeight: 158
                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                    ScrollBar.vertical: PrismScrollBar {
                        id: profileBar
                        theme: root.theme
                        parent: profileScroll
                        x: parent.width - width
                        height: parent.height
                    }
                    rightPadding: profileBar.contentInset
                    background: Rectangle {
                        color: "transparent"
                        border.color: root.theme.line
                    }

                    TextArea {
                        objectName: root.theme.active ? ("settingsProfileDiagnostic") : ""
                        Accessible.name: "Profile 诊断"
                        width: profileScroll.availableWidth
                        text: root.workbench.infoText
                        readOnly: true
                        selectByMouse: true
                        color: root.theme.textSoft
                        selectionColor: root.theme.accent
                        selectedTextColor: root.theme.ink
                        font.family: root.theme.monoFontFor(text)
                        font.pixelSize: 12
                        wrapMode: TextEdit.Wrap
                        background: null
                    }
                }

                SettingLabel {
                    theme: root.theme
                    title: "最近运行延迟"
                    meta: root.diagnostics.scope
                }
                ScrollView {
                    id: logScroll
                    Connections {
                        target: logScroll.contentItem
                        function onContentYChanged() {
                            if (logScrollSync.active && !logScrollSync.restoring
                                    && root.workbench.currentPage === "SETTINGS")
                                root.appShell.rememberScrollPosition(
                                    "SETTINGS", "latencyDiagnostics",
                                    logScroll.contentItem.contentY
                                )
                        }
                    }
                    Shared.ScrollPositionSync {
                        id: logScrollSync
                        appShell: root.appShell
                        flickable: logScroll.contentItem
                        pageKey: "SETTINGS"
                        scrollKey: "latencyDiagnostics"
                        active: root.theme.active && root.visible
                                && root.workbench.currentPage === "SETTINGS"
                    }
                    objectName: root.theme.active ? ("settingsLatencyScroll") : ""
                    contentWidth: availableWidth
                    clip: true
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumHeight: 100
                    Layout.preferredHeight: 260
                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                    ScrollBar.vertical: PrismScrollBar {
                        id: logBar
                        theme: root.theme
                        parent: logScroll
                        x: parent.width - width
                        height: parent.height
                    }
                    rightPadding: logBar.contentInset
                    background: Rectangle {
                        color: "transparent"
                        border.color: root.theme.line
                    }

                    // One wheel owner keeps all three selectable text blocks
                    // on the same scroll range, including over a TextArea.
                    WheelHandler {
                        target: null
                        onWheel: event => {
                            const delta = event.pixelDelta.y !== 0
                                          ? event.pixelDelta.y : event.angleDelta.y / 3
                            if (delta === 0)
                                return
                            const flickable = logScroll.contentItem
                            const maximum = Math.max(0, flickable.contentHeight - flickable.height)
                            flickable.contentY = Math.max(0, Math.min(maximum, flickable.contentY - delta))
                            event.accepted = true
                        }
                    }

                    ColumnLayout {
                        width: logScroll.availableWidth
                        spacing: 8

                        Text {
                            objectName: root.theme.active ? ("settingsLatencyStatus") : ""
                            text: root.diagnostics.status
                            color: root.theme.textDim
                            font.family: root.theme.uiFontFor(text)
                            font.pixelSize: 13
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                        SettingLabel { theme: root.theme; title: "OCR 流程" }
                        TextArea {
                            id: ocrLatencyText
                            objectName: root.theme.active ? ("settingsOcrLatency") : ""
                            Accessible.name: "OCR 流程延迟"
                            text: root.diagnostics.ocr
                            readOnly: true
                            selectByMouse: true
                            color: root.theme.textSoft
                            selectionColor: root.theme.accent
                            selectedTextColor: root.theme.ink
                            font.family: root.theme.monoFontFor(text)
                            font.pixelSize: 13
                            wrapMode: TextEdit.Wrap
                            Layout.preferredHeight: -1
                            Layout.fillWidth: true
                            background: null
                        }
                        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: root.theme.line }
                        SettingLabel { theme: root.theme; title: "翻译流程" }
                        TextArea {
                            id: translationLatencyText
                            objectName: root.theme.active ? ("settingsTranslationLatency") : ""
                            Accessible.name: "翻译流程延迟"
                            text: root.diagnostics.translation
                            readOnly: true
                            selectByMouse: true
                            color: root.theme.textSoft
                            selectionColor: root.theme.accent
                            selectedTextColor: root.theme.ink
                            font.family: root.theme.monoFontFor(text)
                            font.pixelSize: 13
                            wrapMode: TextEdit.Wrap
                            Layout.preferredHeight: -1
                            Layout.fillWidth: true
                            background: null
                        }
                        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: root.theme.line }
                        SettingLabel { theme: root.theme; title: "延迟汇总" }
                        TextArea {
                            id: latencySummaryText
                            objectName: root.theme.active ? ("settingsLatencySummary") : ""
                            Accessible.name: "延迟汇总"
                            text: root.diagnostics.summary
                            readOnly: true
                            selectByMouse: true
                            color: root.theme.textSoft
                            selectionColor: root.theme.accent
                            selectedTextColor: root.theme.ink
                            font.family: root.theme.monoFontFor(text)
                            font.pixelSize: 13
                            wrapMode: TextEdit.Wrap
                            Layout.preferredHeight: -1
                            Layout.fillWidth: true
                            background: null
                        }
                    }
                }

                PrismButton {
                    objectName: root.theme.active ? ("settingsRefreshDiagnostics") : ""
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
