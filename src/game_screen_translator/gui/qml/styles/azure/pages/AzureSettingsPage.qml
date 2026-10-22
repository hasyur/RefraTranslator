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
    required property bool startPending
    signal visualAction(string action)
    signal requestLiveToggle()
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

    Item {
        id: settingsScene
        anchors.fill: parent
        clip: true

        Rectangle {
            anchors.fill: parent
            color: "#06132f"
            z: -5
        }

        Shape {
            id: settingsConfigBand
            x: root.width * 0.29
            y: -root.height * 0.08
            width: root.width * 0.80
            height: root.height * 0.31
            antialiasing: true
            preferredRendererType: Shape.CurveRenderer
            z: -3
            ShapePath {
                fillColor: "#f7f9ff"
                strokeWidth: 0
                startX: 68; startY: 0
                PathLine { x: settingsConfigBand.width; y: 0 }
                PathLine { x: settingsConfigBand.width; y: settingsConfigBand.height * 0.55 }
                PathLine { x: settingsConfigBand.width * 0.14; y: settingsConfigBand.height }
                PathLine { x: 0; y: settingsConfigBand.height * 0.70 }
                PathLine { x: 68; y: 0 }
            }
        }

        Shape {
            id: settingsPaper
            objectName: "azureSettingsPaper"
            x: -18
            y: root.height * 0.205
            width: root.width + 28
            height: root.height * 0.80
            antialiasing: true
            preferredRendererType: Shape.CurveRenderer
            z: 0
            ShapePath {
                fillColor: "#f7f9ff"
                strokeWidth: 0
                startX: 0; startY: 42
                PathLine { x: settingsPaper.width * 0.04; y: 14 }
                PathLine { x: settingsPaper.width * 0.16; y: 0 }
                PathLine { x: settingsPaper.width * 0.26; y: 24 }
                PathLine { x: settingsPaper.width * 0.38; y: 4 }
                PathLine { x: settingsPaper.width * 0.48; y: 22 }
                PathLine { x: settingsPaper.width * 0.64; y: 0 }
                PathLine { x: settingsPaper.width * 0.78; y: 17 }
                PathLine { x: settingsPaper.width; y: 32 }
                PathLine { x: settingsPaper.width; y: settingsPaper.height - 28 }
                PathLine { x: settingsPaper.width - 20; y: settingsPaper.height }
                PathLine { x: 0; y: settingsPaper.height * 0.96 }
                PathLine { x: 0; y: 42 }
            }
        }

        Repeater {
            z: 2
            model: [
                { x: 0.49, y: 0.33, w: 0.060, h: 0.13, c: "#1054f5" },
                { x: 0.88, y: 0.43, w: 0.090, h: 0.16, c: "#05bde9" }
            ]
            Shape {
                id: shardShape
                required property var modelData
                x: settingsScene.width * modelData.x
                y: settingsScene.height * modelData.y
                width: settingsScene.width * modelData.w
                height: settingsScene.height * modelData.h
                antialiasing: true
                preferredRendererType: Shape.CurveRenderer
                ShapePath {
                    fillColor: modelData.c
                    strokeWidth: 0
                    startX: 0; startY: 0
                    PathLine { x: shardShape.width; y: shardShape.height * 0.18 }
                    PathLine { x: shardShape.width * 0.54; y: shardShape.height }
                    PathLine { x: 0; y: 0 }
                }
            }
        }

        Shape {
            id: settingAccentShard
            x: root.width * 0.30
            y: root.height * 0.035
            width: root.width * 0.040
            height: root.height * 0.075
            antialiasing: true
            preferredRendererType: Shape.CurveRenderer
            z: 2
            ShapePath {
                fillColor: "#05bde9"
                strokeWidth: 0
                startX: 0; startY: 0
                PathLine { x: settingAccentShard.width; y: settingAccentShard.height * 0.18 }
                PathLine { x: settingAccentShard.width * 0.42; y: settingAccentShard.height }
                PathLine { x: 0; y: 0 }
            }
        }

        Shape {
            id: settingCoralShard
            x: root.width * 0.335
            y: root.height * 0.075
            width: 17
            height: 23
            antialiasing: true
            preferredRendererType: Shape.CurveRenderer
            z: 2
            ShapePath {
                fillColor: "#ff3153"
                strokeWidth: 0
                startX: 0; startY: 0
                PathLine { x: settingCoralShard.width; y: settingCoralShard.height * 0.38 }
                PathLine { x: settingCoralShard.width * 0.26; y: settingCoralShard.height }
                PathLine { x: 0; y: 0 }
            }
        }

        Shape {
            id: settingsFigureShard
            x: root.width * 0.92
            y: root.height * 0.31
            width: root.width * 0.055
            height: root.height * 0.10
            antialiasing: true
            preferredRendererType: Shape.CurveRenderer
            z: 2
            ShapePath {
                fillColor: "#104bf5"
                strokeWidth: 0
                startX: 0; startY: 0
                PathLine { x: settingsFigureShard.width; y: settingsFigureShard.height * 0.22 }
                PathLine { x: settingsFigureShard.width * 0.40; y: settingsFigureShard.height }
                PathLine { x: 0; y: 0 }
            }
        }

        Text {
            objectName: "azureSettingsWordmark"
            x: root.width * 0.34
            y: -root.height * 0.12
            width: root.width * 0.78
            height: root.height * 0.34
            text: "CONFIG"
            color: "#104bf5"
            font.family: root.theme.displayFontFor(text)
            font.pixelSize: Math.max(132, Math.min(232, root.width * 0.225))
            font.weight: Font.Black
            font.italic: true
            font.letterSpacing: -12
            rotation: -9
            opacity: 1
            z: 0.5
        }

        Image {
            objectName: "azureSettingsHeroine"
            source: Qt.resolvedUrl("../assets/heroine-settings.png")
            sourceSize.width: 1400
            sourceSize.height: 1000
            fillMode: Image.PreserveAspectFit
            horizontalAlignment: Image.AlignRight
            verticalAlignment: Image.AlignTop
            x: root.width * 0.33
            y: -root.height * 0.010
            width: root.width * 0.70
            height: root.height * 0.69
            asynchronous: true
            smooth: true
            visible: status === Image.Ready
            z: 1
        }

        Shape {
            id: parameterProtection
            objectName: "azureSettingsParameterProtection"
            x: -5
            y: root.height * 0.215
            // The narrow layout needs a slightly wider upper shoulder for the
            // first row's +/- controls, while keeping the original long diagonal.
            width: root.width * 0.61
            height: root.height * 0.64
            antialiasing: true
            preferredRendererType: Shape.CurveRenderer
            z: 2.5
            ShapePath {
                fillColor: "#f7f9ff"
                strokeWidth: 0
                startX: 0; startY: 34
                PathLine { x: parameterProtection.width * 0.08; y: 0 }
                PathLine { x: parameterProtection.width * 0.28; y: 15 }
                PathLine { x: parameterProtection.width * 0.47; y: 0 }
                PathLine {
                    x: parameterProtection.width * (root.width < 900 ? 0.76 : 0.60)
                    y: 0
                }
                PathLine { x: parameterProtection.width; y: parameterProtection.height * 0.60 }
                PathLine { x: parameterProtection.width - 18; y: parameterProtection.height }
                PathLine { x: 0; y: parameterProtection.height * 0.97 }
                PathLine { x: 0; y: 34 }
            }
        }

        Shape {
            id: diagnosticsProtection
            objectName: "azureSettingsDiagnosticsProtection"
            x: root.width * 0.50
            y: root.height * 0.50
            width: root.width * 0.50
            height: root.height * 0.45
            antialiasing: true
            preferredRendererType: Shape.CurveRenderer
            z: 2.5
            ShapePath {
                fillColor: "#f7f9ff"
                strokeWidth: 0
                startX: 0; startY: diagnosticsProtection.height * 0.18
                PathLine { x: diagnosticsProtection.width * 0.30; y: 0 }
                PathLine { x: diagnosticsProtection.width; y: 0 }
                PathLine { x: diagnosticsProtection.width; y: diagnosticsProtection.height - 20 }
                PathLine { x: diagnosticsProtection.width - 20; y: diagnosticsProtection.height }
                PathLine { x: 0; y: diagnosticsProtection.height }
                PathLine { x: 14; y: 18 }
                PathLine { x: 28; y: 0 }
            }
        }

        Item {
            objectName: "azureSettingsHero"
            x: 20
            y: 0
            width: root.width * 0.46
            height: root.height * 0.22
            clip: false
            z: 4

            ColumnLayout {
                x: 10
                y: 4
                spacing: 0
                z: 4
                RowLayout {
                    spacing: 7
                    Text {
                        text: "设置"
                        color: "#ffffff"
                        font.family: root.theme.displayFontFor(text)
                        font.pixelSize: root.height < 720 ? 72 : 94
                        font.weight: Font.Black
                        font.italic: true
                    }
                    Shape {
                        Layout.preferredWidth: 30
                        Layout.preferredHeight: 42
                        antialiasing: true
                        preferredRendererType: Shape.CurveRenderer
                        ShapePath {
                            fillColor: root.theme.spectrum
                            strokeWidth: 0
                            startX: 0; startY: 0
                            PathLine { x: 30; y: 14 }
                            PathLine { x: 13; y: 42 }
                            PathLine { x: 0; y: 0 }
                        }
                    }
                }
                Text {
                    text: "运行参数与诊断"
                    color: "#c8d7ff"
                    font.family: root.theme.uiFontFor(text)
                    font.pixelSize: root.height < 720 ? 19 : 22
                    font.weight: Font.DemiBold
                }
            }
        }

        Item {
            objectName: "azureSettingsWorkArea"
            x: 0
            y: 0
            width: root.width
            height: root.height
            z: 3

            Item {
                objectName: "azureSettingsFormPanel"
                x: root.width * 0.018
                y: root.height * 0.235
                width: root.width * 0.56
                height: root.height * 0.65
                rotation: -3.5
                transformOrigin: Item.TopLeft
                Flickable {
                    id: settingsFormScroll
                    objectName: "azureSettingsFormScroll"
                    anchors.fill: parent
                    anchors.leftMargin: 5
                    anchors.rightMargin: 6
                    anchors.topMargin: 12
                    anchors.bottomMargin: 4
                    contentWidth: width
                    contentHeight: settingsForm.implicitHeight
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                    FocusScrollGuard { flickable: settingsFormScroll }
                    ColumnLayout {
                        id: settingsForm
                        width: settingsFormScroll.width - 5
                        spacing: 2

                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                text: "01"
                                color: root.theme.accent
                                font.family: root.theme.displayFontFor(text)
                                    font.pixelSize: 35
                                font.weight: Font.Black
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: -1
                                Text {
                                    text: "扫描调度"
                                    color: root.theme.text
                                    font.family: root.theme.displayFontFor(text)
                                    font.pixelSize: 25
                                    font.weight: Font.Black
                                    font.italic: true
                                }
                                Text {
                                    objectName: "azureSettingsModeText"
                                    text: "当前模式："
                                          + (root.workbench.triggerMethodIndex === 2 ? "鼠标停留"
                                             : root.workbench.dynamicRoiEnabled ? "动态 ROI" : "整帧处理")
                                          + " · 触发来源在 OCR 页设置。"
                                    color: root.theme.textDim
                                    font.family: root.theme.uiFontFor(text)
                                    font.pixelSize: 10
                                    wrapMode: Text.WordWrap
                                    Layout.fillWidth: true
                                }
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
                                font.pixelSize: 32
                                font.weight: Font.Black
                                font.italic: true
                            }
                            Text {
                                text: "输出与调试"
                                color: root.theme.text
                                font.family: root.theme.displayFontFor(text)
                                font.pixelSize: 24
                                font.weight: Font.Black
                                font.italic: true
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
                x: root.width * 0.60
                y: root.height * 0.56
                width: root.width * 0.36
                height: root.height * 0.33
                Column {
                    id: diagnosticsColumn
                    anchors.fill: parent
                    anchors.leftMargin: 10
                    anchors.rightMargin: 8
                    anchors.topMargin: 1
                    anchors.bottomMargin: 0
                    spacing: 5
                    RowLayout {
                        id: diagnosticsHeading
                        width: diagnosticsColumn.width
                        height: 54
                        Text {
                            text: "03"
                            color: root.theme.accent
                            font.family: root.theme.displayFontFor(text)
                            font.pixelSize: 43
                            font.weight: Font.Black
                            font.italic: true
                        }
                        ColumnLayout {
                            spacing: -1
                            Layout.fillWidth: true
                            Text {
                                text: "运行诊断"
                                color: root.theme.text
                                font.family: root.theme.displayFontFor(text)
                                font.pixelSize: 29
                                font.weight: Font.Black
                                font.italic: true
                            }
                            Text {
                                text: "最近完成运行 · 独立流程与峰值"
                                color: root.theme.textDim
                                font.family: root.theme.uiFontFor(text)
                                font.pixelSize: 11
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
                            compact: true
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
                            Layout.preferredHeight: 39
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
                            Layout.preferredHeight: 39
                            onClicked: fullDiagnosticsDialog.open()
                        }
                    }
                }
            }
        }

        RowLayout {
            objectName: "azureSettingsActionRow"
            x: root.width * 0.025
            y: root.height - height - root.height * 0.020
            width: root.width * 0.58
            height: 62
            spacing: 7
            z: 5
            Item {
                objectName: "azureSettingsSaveFeedback"
                Layout.fillWidth: true
                Layout.minimumWidth: 120
                Layout.preferredWidth: root.width * 0.22
                Layout.fillHeight: true
                Rectangle {
                    x: 0
                    y: 8
                    width: 4
                    height: parent.height - 16
                    color: root.workbench.settingsDirty ? "#ff3153"
                         : root.workbench.statusTone === "error" ? root.theme.danger
                         : root.workbench.statusTone === "warning" ? root.theme.amber
                         : root.workbench.statusTone === "success" ? root.theme.spectrum
                         : "#7894d3"
                }
                Text {
                    objectName: "azureSettingsSaveFeedbackText"
                    anchors.fill: parent
                    anchors.leftMargin: 12
                    anchors.rightMargin: 12
                    text: root.workbench.settingsDirty
                          ? "有未应用更改 · 点击应用更改后生效"
                          : root.workbench.statusText
                    color: root.workbench.settingsDirty ? "#c91e43" : root.theme.text
                    font.family: root.theme.uiFontFor(text)
                    font.pixelSize: 12
                    font.weight: Font.DemiBold
                    wrapMode: Text.Wrap
                    maximumLineCount: 3
                    elide: Text.ElideRight
                    verticalAlignment: Text.AlignVCenter
                }
            }
            AzureButton {
                objectName: "azureSaveAllButton"
                theme: root.theme
                text: "应用更改  →"
                font.pixelSize: root.width < 900 ? 15 : 18
                font.weight: Font.Black
                font.italic: true
                enabled: root.workbench.hasProfile
                implicitHeight: 54
                Layout.minimumWidth: 126
                Layout.fillWidth: true
                Layout.preferredWidth: root.width * 0.17
                onClicked: root.workbench.saveAll()
            }
            AzureButton {
                objectName: "azureStartLiveButton"
                theme: root.theme
                text: root.startPending ? "正在准备…" : root.workbench.startButtonText + "  →"
                primary: true
                font.pixelSize: root.width < 900 ? 16 : 20
                font.weight: Font.Black
                font.italic: true
                enabled: root.workbench.runPhase !== "stopping"
                         && !root.startPending
                         && (root.workbench.canStart || root.workbench.running)
                implicitHeight: 54
                Layout.minimumWidth: 126
                Layout.fillWidth: true
                Layout.preferredWidth: root.width * 0.17
                onClicked: root.requestLiveToggle()
            }
        }
    }
}
