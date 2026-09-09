import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

Item {
    id: root

    required property var theme
    required property var workbench
    property string sideMode: "settings"
    property int transitionSerial: 0
    property bool pageMotionEnabled: false
    signal visualAction(string action)

    PrismDialog {
        id: deleteModelDialog
        objectName: "deleteModelDialog"
        surfaceName: "deleteModelDialog"
        theme: root.theme
        parent: Overlay.overlay
        anchors.centerIn: parent
        title: "确认删除内置模型"
        acceptText: "删除模型"
        rejectText: "取消"
        acceptTone: "danger"
        width: Math.min(480, root.width - 40)

        Text {
            text: "将删除当前选择的模型文件并释放磁盘空间。运行时文件不会被删除。\n\n模型：" + root.workbench.builtinModel
            color: root.theme.text
            font.family: root.theme.uiFontFor(text)
            font.pixelSize: 13
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        onAccepted: root.workbench.deleteBuiltinModel(true)
    }

    RowLayout {
        anchors.fill: parent
        spacing: 16

        PrismPanel {
            objectName: "translationPrimaryPanel"
            theme: root.theme
            motionRole: "primary"
            transitionSerial: root.transitionSerial
            motionEnabled: root.pageMotionEnabled && root.visible
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumWidth: 360

            ColumnLayout {
                anchors.fill: parent
                spacing: 16

                SectionHeader {
                    theme: root.theme
                    title: "翻译流"
                    meta: root.workbench.backend === "builtin" ? "LOCAL" : "EXTERNAL"
                    Layout.fillWidth: true
                }

                UnavailableState {
                    objectName: "translationLastRunUnavailable"
                    theme: root.theme
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    visible: !root.workbench.lastRunAvailable
                    eyebrow: "LAST RUN TRANSLATION · UNAVAILABLE"
                    title: "尚无上次运行结果"
                    detail: root.workbench.lastRunStatus
                }

                Flickable {
                    objectName: "translationLastRunList"
                    visible: root.workbench.lastRunAvailable
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    contentWidth: width
                    contentHeight: translationLastRunColumn.implicitHeight
                    clip: true
                    ColumnLayout {
                        id: translationLastRunColumn
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
                            model: root.workbench.lastRunTranslationResults
                            Rectangle {
                                required property var modelData
                                Layout.fillWidth: true
                                implicitHeight: Math.max(76, translationText.implicitHeight + 26)
                                color: "transparent"
                                border.color: root.theme.line
                                ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: 10
                                    spacing: 3
                                    Text {
                                        text: modelData.sourceText
                                        color: root.theme.textDim
                                        font.family: root.theme.uiFontFor(text)
                                        font.pixelSize: 12
                                        elide: Text.ElideRight
                                        Layout.fillWidth: true
                                    }
                                    Text {
                                        id: translationText
                                        text: modelData.translatedText
                                        color: root.theme.text
                                        font.family: root.theme.uiFontFor(text)
                                        font.pixelSize: 14
                                        wrapMode: Text.WordWrap
                                        Layout.fillWidth: true
                                    }
                                }
                            }
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: 82
                    color: "transparent"
                    border.color: root.theme.line
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 13
                        spacing: 4
                        Text {
                            text: "连接状态"
                            color: root.theme.accent
                            font.family: root.theme.monoFontFor(text)
                            font.pixelSize: 10
                            font.letterSpacing: 1
                        }
                        Text {
                            text: root.workbench.backend === "builtin"
                                  ? root.workbench.localModelStatus
                                  : root.workbench.connectionState
                            color: root.theme.textSoft
                            font.family: root.theme.uiFontFor(text)
                            font.pixelSize: 12
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                    }
                }
            }
        }

        PrismPanel {
            objectName: "translationSecondaryPanel"
            theme: root.theme
            raised: true
            motionRole: "secondary"
            transitionSerial: root.transitionSerial
            motionEnabled: root.pageMotionEnabled && root.visible
            Layout.preferredWidth: 390
            Layout.minimumWidth: 350
            Layout.fillHeight: true

            ColumnLayout {
                anchors.fill: parent
                spacing: 12

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 7
                    PrismButton {
                        theme: root.theme
                        text: "翻译设置"
                        primary: root.sideMode === "settings"
                        Layout.fillWidth: true
                        onClicked: root.sideMode = "settings"
                    }
                    PrismButton {
                        theme: root.theme
                        text: "术语表"
                        primary: root.sideMode === "glossary"
                        Layout.fillWidth: true
                        onClicked: root.sideMode = "glossary"
                    }
                }

                StackLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    currentIndex: root.sideMode === "settings" ? 0 : 1

                    Flickable {
                        id: translationFormScroll
                        contentWidth: width
                        contentHeight: settingsForm.implicitHeight
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                        FocusScrollGuard { flickable: translationFormScroll }

                        ColumnLayout {
                            id: settingsForm
                            width: parent.width
                            spacing: 12

                            SectionHeader {
                                theme: root.theme
                                title: "翻译后端"
                                meta: root.workbench.backend.toUpperCase()
                                Layout.fillWidth: true
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                PrismButton {
                                    objectName: "translationTraceAction"
                                    theme: root.theme
                                    text: "内置本地模型"
                                    settingDescription: "选择使用本机模型或外部 API 翻译。"
                                    settingKey: "translation-backend"
                                    primary: root.workbench.backend === "builtin"
                                    enabled: !root.workbench.downloading
                                    Layout.fillWidth: true
                                    onClicked: {
                                        root.workbench.setBackend("builtin")
                                        root.visualAction("trace")
                                    }
                                }
                                PrismButton {
                                    theme: root.theme
                                    text: "外部 API"
                                    settingDescription: "选择使用本机模型或外部 API 翻译。"
                                    settingKey: "translation-backend"
                                    primary: root.workbench.backend === "external"
                                    enabled: !root.workbench.downloading
                                    Layout.fillWidth: true
                                    onClicked: {
                                        root.workbench.setBackend("external")
                                        root.visualAction("trace")
                                    }
                                }
                            }

                            ColumnLayout {
                                objectName: "builtinSettings"
                                visible: root.workbench.backend === "builtin"
                                Layout.fillWidth: true
                                spacing: 11

                                SettingLabel {
                                    theme: root.theme
                                    title: "内置模型"
                                    meta: "GGUF"
                                    description: "选择用于本地翻译的模型文件。"
                                    settingKey: "translation-builtin-model"
                                }
                                PrismComboBox {
                                    theme: root.theme
                                    accessibleName: "内置翻译模型"
                                    settingDescription: "选择用于本地翻译的模型文件。"
                                    settingKey: "translation-builtin-model"
                                    model: root.workbench.builtinModelNames
                                    currentIndex: Math.max(0, root.workbench.builtinModelIds.indexOf(root.workbench.builtinModel))
                                    enabled: !root.workbench.downloading
                                    Layout.fillWidth: true
                                    onActivated: index => {
                                        if (index >= 0 && index < root.workbench.builtinModelIds.length)
                                            root.workbench.setBuiltinModel(root.workbench.builtinModelIds[index])
                                    }
                                }

                                Text {
                                    text: root.workbench.localModelStatus
                                    color: root.theme.textSoft
                                    font.family: root.theme.uiFontFor(text)
                                    font.pixelSize: 11
                                    wrapMode: Text.WordWrap
                                    Layout.fillWidth: true
                                }

                                ProgressBar {
                                    visible: root.workbench.downloading || root.workbench.downloadProgress > 0
                                    from: 0
                                    to: 100
                                    value: root.workbench.downloadProgress
                                    Layout.fillWidth: true
                                    background: Rectangle { color: root.theme.line; implicitHeight: 4 }
                                    contentItem: Item {
                                        implicitHeight: 4
                                        Rectangle {
                                            width: parent.width * Math.max(0, Math.min(1, root.workbench.downloadProgress / 100))
                                            height: parent.height
                                            color: root.theme.accent
                                        }
                                    }
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 8
                                    PrismButton {
                                        theme: root.theme
                                        text: root.workbench.modelInstallActionText
                                        primary: !root.workbench.downloading
                                        enabled: root.workbench.canDownloadBuiltinModel
                                        Layout.fillWidth: true
                                        onClicked: root.workbench.downloadBuiltinModel()
                                    }
                                    PrismButton {
                                        objectName: "openDeleteModelDialogButton"
                                        theme: root.theme
                                        text: "删除模型"
                                        tone: "danger"
                                        enabled: root.workbench.canDeleteBuiltinModel
                                        Layout.fillWidth: true
                                        onClicked: deleteModelDialog.open()
                                    }
                                }

                                SettingLabel {
                                    theme: root.theme
                                    title: "CUDA 设备"
                                    meta: "LOCAL INFERENCE"
                                    description: "选择本地模型使用的计算设备。"
                                    settingKey: "translation-builtin-device"
                                }
                                PrismComboBox {
                                    theme: root.theme
                                    accessibleName: "CUDA 设备"
                                    settingDescription: "选择本地模型使用的计算设备。"
                                    settingKey: "translation-builtin-device"
                                    model: root.workbench.builtinDeviceNames
                                    itemEnabled: root.workbench.builtinDeviceAvailability
                                    currentIndex: Math.max(0, root.workbench.builtinDeviceValues.indexOf(root.workbench.builtinCudaDevice))
                                    Layout.fillWidth: true
                                    onActivated: index => {
                                        if (index >= 0 && index < root.workbench.builtinDeviceValues.length)
                                            root.workbench.setBuiltinCudaDevice(root.workbench.builtinDeviceValues[index])
                                    }
                                }

                                SettingLabel {
                                    theme: root.theme
                                    title: "并行槽"
                                    meta: "1—32"
                                    description: "设置本地模型同时处理的请求数量。"
                                    settingKey: "translation-builtin-parallel"
                                }
                                NumberStepper {
                                    theme: root.theme
                                    accessibleName: "内置模型并行槽"
                                    settingDescription: "设置本地模型同时处理的请求数量。"
                                    settingKey: "translation-builtin-parallel"
                                    value: root.workbench.builtinParallel
                                    minimum: 1
                                    maximum: 32
                                    Layout.fillWidth: true
                                    onEdited: value => root.workbench.setBuiltinParallel(value)
                                }

                                SettingLabel {
                                    theme: root.theme
                                    title: "KV Cache"
                                    meta: "PRECISION"
                                    description: "选择本地模型上下文缓存的精度。"
                                    settingKey: "translation-builtin-cache"
                                }
                                PrismComboBox {
                                    theme: root.theme
                                    accessibleName: "KV Cache 精度"
                                    settingDescription: "选择本地模型上下文缓存的精度。"
                                    settingKey: "translation-builtin-cache"
                                    model: root.workbench.builtinKvCacheOptions
                                    currentIndex: Math.max(0, root.workbench.builtinKvCacheOptions.indexOf(root.workbench.builtinKvCacheType))
                                    Layout.fillWidth: true
                                    onActivated: index => {
                                        if (index >= 0 && index < root.workbench.builtinKvCacheOptions.length)
                                            root.workbench.setBuiltinKvCacheType(root.workbench.builtinKvCacheOptions[index])
                                    }
                                }

                                Text {
                                    text: root.workbench.builtinContextSummary
                                    color: root.theme.textDim
                                    font.family: root.theme.monoFontFor(text)
                                    font.pixelSize: 10
                                    wrapMode: Text.WordWrap
                                    Layout.fillWidth: true
                                }
                            }

                            ColumnLayout {
                                objectName: "externalSettings"
                                visible: root.workbench.backend === "external"
                                Layout.fillWidth: true
                                spacing: 11

                                SettingLabel {
                                    theme: root.theme
                                    title: "API 服务器"
                                    meta: "BASE URL"
                                    description: "设置外部翻译服务的地址。"
                                    settingKey: "translation-external-url"
                                }
                                PrismTextField {
                                    theme: root.theme
                                    accessibleName: "API 服务器"
                                    settingDescription: "设置外部翻译服务的地址。"
                                    settingKey: "translation-external-url"
                                    text: root.workbench.baseUrl
                                    placeholderText: "http://127.0.0.1:8000/v1"
                                    Layout.fillWidth: true
                                    onTextEdited: root.workbench.setBaseUrl(text)
                                }

                                SettingLabel {
                                    theme: root.theme
                                    title: "API 密钥"
                                    meta: root.workbench.apiKeyStatusText
                                    description: "设置访问外部翻译服务所需的密钥。"
                                    settingKey: "translation-external-key"
                                }
                                PrismTextField {
                                    id: apiKeyDraft
                                    theme: root.theme
                                    accessibleName: "API 密钥"
                                    settingDescription: "设置访问外部翻译服务所需的密钥。"
                                    settingKey: "translation-external-key"
                                    text: ""
                                    echoMode: TextInput.Password
                                    passwordCharacter: "●"
                                    placeholderText: root.workbench.apiKeyConfigured
                                                     ? "输入本地密钥以覆盖当前来源"
                                                     : "输入密钥"
                                    Layout.fillWidth: true
                                    onTextEdited: root.workbench.setApiKey(text)
                                }
                                PrismButton {
                                    theme: root.theme
                                    text: "清除本地密钥"
                                    tone: "danger"
                                    enabled: root.workbench.apiKeyOverrideConfigured || apiKeyDraft.text.length > 0
                                    Layout.fillWidth: true
                                    onClicked: {
                                        apiKeyDraft.clear()
                                        root.workbench.clearApiKey()
                                    }
                                }

                                SettingLabel {
                                    theme: root.theme
                                    title: "模型"
                                    meta: "MODEL ID"
                                    description: "设置外部翻译服务使用的模型名称。"
                                    settingKey: "translation-external-model"
                                }
                                PrismTextField {
                                    theme: root.theme
                                    accessibleName: "模型 ID"
                                    settingDescription: "设置外部翻译服务使用的模型名称。"
                                    settingKey: "translation-external-model"
                                    text: root.workbench.model
                                    placeholderText: "模型 ID"
                                    Layout.fillWidth: true
                                    onTextEdited: root.workbench.setModel(text)
                                }
                                PrismComboBox {
                                    visible: root.workbench.modelNames.length > 0
                                    theme: root.theme
                                    accessibleName: "已读取的模型"
                                    settingDescription: "设置外部翻译服务使用的模型名称。"
                                    settingKey: "translation-external-model"
                                    model: root.workbench.modelNames
                                    currentIndex: Math.max(0, root.workbench.modelNames.indexOf(root.workbench.model))
                                    Layout.fillWidth: true
                                    onActivated: index => root.workbench.setModel(root.workbench.modelNames[index])
                                }
                                PrismButton {
                                    theme: root.theme
                                    text: "连接并读取模型"
                                    Layout.fillWidth: true
                                    onClicked: {
                                        root.workbench.testConnection()
                                        root.visualAction("trace")
                                    }
                                }

                                SettingLabel {
                                    theme: root.theme
                                    title: "最大并发"
                                    meta: "1—32"
                                    description: "设置同时提交给外部翻译服务的请求数量。"
                                    settingKey: "translation-external-concurrency"
                                }
                                NumberStepper {
                                    theme: root.theme
                                    accessibleName: "最大并发"
                                    settingDescription: "设置同时提交给外部翻译服务的请求数量。"
                                    settingKey: "translation-external-concurrency"
                                    value: root.workbench.maxConcurrency
                                    minimum: 1
                                    maximum: 32
                                    Layout.fillWidth: true
                                    onEdited: value => root.workbench.setMaxConcurrency(value)
                                }
                            }

                            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: root.theme.line }

                            SettingLabel {
                                theme: root.theme
                                title: "当前游戏提示词"
                                meta: "PROFILE SCOPE"
                                description: "为当前游戏设置发送给翻译服务的专用提示词。"
                                settingKey: "translation-prompt"
                            }
                            TextArea {
                                id: promptEditor
                                objectName: "profilePromptEditor"
                                Accessible.name: "当前游戏提示词"
                                SettingHint {
                                    theme: root.theme
                                    target: promptEditor
                                    description: "为当前游戏设置发送给翻译服务的专用提示词。"
                                    settingKey: "translation-prompt"
                                }
                                enabled: root.workbench.hasProfile
                                text: root.workbench.customPrompt
                                placeholderText: "留空使用内置默认提示词"
                                color: root.theme.text
                                placeholderTextColor: root.theme.textDim
                                selectionColor: root.theme.accent
                                selectedTextColor: root.theme.ink
                                font.family: root.theme.uiFontFor(text)
                                font.pixelSize: 12
                                wrapMode: TextEdit.Wrap
                                Layout.fillWidth: true
                                Layout.preferredHeight: 116
                                onTextChanged: {
                                    if (activeFocus)
                                        root.workbench.setCustomPrompt(text)
                                }
                                background: Rectangle {
                                    color: root.theme.dark ? "#8f0b1016" : "#b8eef2f3"
                                    border.color: promptEditor.activeFocus ? root.theme.accent : root.theme.lineStrong
                                    border.width: promptEditor.activeFocus ? 2 : 1
                                }
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                PrismButton {
                                    theme: root.theme
                                    text: "恢复默认"
                                    enabled: root.workbench.hasProfile
                                    Layout.fillWidth: true
                                    onClicked: root.workbench.resetCustomPrompt()
                                }
                                PrismButton {
                                    theme: root.theme
                                    primary: true
                                    text: "保存提示词"
                                    enabled: root.workbench.hasProfile
                                    Layout.fillWidth: true
                                    onClicked: root.workbench.saveCustomPrompt()
                                }
                            }
                        }
                    }

                    PairEditor {
                        objectName: "glossaryEditor"
                        theme: root.theme
                        initialEntries: root.workbench.glossaryEntries
                        initialDirty: root.workbench.glossaryDirty
                        revisionKey: root.workbench.currentProfileId + ":" + root.workbench.profileRevision
                        sourceTitle: "原文 / 术语"
                        targetTitle: "固定译法"
                        saveText: "保存术语表"
                        settingDescription: "编辑当前游戏的原文与固定译文对应关系。"
                        settingKey: "translation-glossary"
                        enabled: root.workbench.hasProfile
                        onDraftChanged: entries => root.workbench.setGlossaryDraft(entries)
                        onSaveRequested: entries => root.workbench.saveGlossary(entries)
                    }
                }
            }
        }
    }
}
