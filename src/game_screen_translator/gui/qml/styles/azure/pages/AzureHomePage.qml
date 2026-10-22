import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

Item {
    id: root
    required property var theme
    required property var workbench
    required property bool startPending
    signal requestLiveToggle()
    readonly property var themeValues: ["system", "dark", "light"]
    readonly property var themeNames: ["跟随系统", "深色", "浅色"]
    readonly property var skinValues: ["prism", "dohna", "azure"]
    readonly property var skinNames: ["Prism", "Dohna", "蓝色剪影"]
    readonly property var hotkeyValues: ["start_only", "toggle", "toggle_show"]
    readonly property var hotkeyNames: ["仅启动", "启动 / 停止翻译", "启动 / 停止并打开 GUI"]
    property bool hotkeyRecording: false

    function hotkeyKeyName(key) {
        if (key >= Qt.Key_A && key <= Qt.Key_Z) return String.fromCharCode(key)
        if (key >= Qt.Key_0 && key <= Qt.Key_9) return String.fromCharCode(key)
        if (key >= Qt.Key_F1 && key <= Qt.Key_F24) return "F" + (key - Qt.Key_F1 + 1)
        if (key === Qt.Key_Space) return "Space"
        if (key === Qt.Key_Tab || key === Qt.Key_Backtab) return "Tab"
        if (key === Qt.Key_Return || key === Qt.Key_Enter) return "Enter"
        if (key === Qt.Key_Backspace) return "Backspace"
        if (key === Qt.Key_Insert) return "Insert"
        if (key === Qt.Key_Delete) return "Delete"
        if (key === Qt.Key_Home) return "Home"
        if (key === Qt.Key_End) return "End"
        if (key === Qt.Key_PageUp) return "PageUp"
        if (key === Qt.Key_PageDown) return "PageDown"
        if (key === Qt.Key_Left) return "Left"
        if (key === Qt.Key_Right) return "Right"
        if (key === Qt.Key_Up) return "Up"
        if (key === Qt.Key_Down) return "Down"
        return ""
    }
    function recordHotkey(event) {
        if (!hotkeyRecording) return
        event.accepted = true
        if (event.isAutoRepeat) return
        if (event.key === Qt.Key_Escape) {
            hotkeyRecording = false
            return
        }
        const keyName = hotkeyKeyName(event.key)
        if (!keyName.length) return
        const modifiers = []
        if (event.modifiers & Qt.ControlModifier) modifiers.push("Ctrl")
        if (event.modifiers & Qt.AltModifier) modifiers.push("Alt")
        if (event.modifiers & Qt.ShiftModifier) modifiers.push("Shift")
        if (event.modifiers & Qt.MetaModifier) modifiers.push("Win")
        if (!modifiers.length) return
        hotkeyRecording = false
        workbench.setHotkey(modifiers.join("+") + "+" + keyName)
    }

    Dialog {
        id: createProfileDialog
        objectName: "azureCreateProfileDialog"
        parent: Overlay.overlay
        anchors.centerIn: parent
        modal: true
        width: Math.min(430, root.width - 40)
        height: 290
        title: "新建游戏配置"
        standardButtons: Dialog.NoButton
        background: Rectangle { color: root.theme.white; border.color: root.theme.lineStrong }
        contentItem: ColumnLayout {
            spacing: 12
            Text {
                text: "配置会保存独立的区域、OCR、翻译、术语与运行参数。"
                color: root.theme.textSoft
                font.family: root.theme.uiFontFor(text)
                font.pixelSize: 13
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            AzureTextField {
                id: newProfileName
                objectName: "azureNewProfileName"
                theme: root.theme
                placeholderText: "游戏名称"
                Layout.fillWidth: true
                onAccepted: if (text.trim().length) createProfileDialog.accept()
            }
        }
        footer: DialogButtonBox {
            alignment: Qt.AlignRight
            AzureButton {
                theme: root.theme
                text: "取消"
                DialogButtonBox.buttonRole: DialogButtonBox.RejectRole
            }
            AzureButton {
                theme: root.theme
                text: "创建并切换"
                primary: true
                enabled: newProfileName.text.trim().length > 0
                DialogButtonBox.buttonRole: DialogButtonBox.AcceptRole
            }
        }
        onOpened: newProfileName.forceActiveFocus()
        onClosed: newProfileName.clear()
        onAccepted: root.workbench.createProfile(newProfileName.text.trim())
    }

    Dialog {
        id: deleteProfileDialog
        objectName: "azureDeleteProfileDialog"
        property string profileId: ""
        property string profileName: ""
        parent: Overlay.overlay
        anchors.centerIn: parent
        modal: true
        width: Math.min(450, root.width - 40)
        height: 250
        title: "删除游戏配置"
        standardButtons: Dialog.NoButton
        background: Rectangle { color: root.theme.white; border.color: root.theme.lineStrong }
        contentItem: Text {
            text: "确定删除“" + deleteProfileDialog.profileName
                  + "”？该配置的设置、术语表、翻译缓存、人工修正和运行快照将一并删除，无法撤销。"
            color: root.theme.textSoft
            font.family: root.theme.uiFontFor(text)
            font.pixelSize: 14
            wrapMode: Text.WordWrap
        }
        footer: DialogButtonBox {
            alignment: Qt.AlignRight
            AzureButton {
                objectName: "azureDeleteProfileCancelButton"
                theme: root.theme
                text: "取消"
                DialogButtonBox.buttonRole: DialogButtonBox.RejectRole
            }
            AzureButton {
                objectName: "azureDeleteProfileConfirmButton"
                theme: root.theme
                text: "删除配置"
                tone: "danger"
                quiet: true
                enabled: root.workbench.hasProfile && !root.workbench.running
                         && root.workbench.runPhase !== "stopping"
                DialogButtonBox.buttonRole: DialogButtonBox.AcceptRole
            }
        }
        onAccepted: root.workbench.deleteProfile(profileId)
    }

    Flickable {
        id: homeScroll
        objectName: "azureHomeScroll"
        anchors.fill: parent
        contentWidth: width
        contentHeight: homeColumn.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        ColumnLayout {
            id: homeColumn
            width: homeScroll.width
            spacing: 7

            Item {
                id: hero
                objectName: "azureHomeHero"
                Layout.fillWidth: true
                Layout.preferredHeight: root.height < 610 ? 254 : 305
                clip: true

                Text {
                    objectName: "azureHomeWordmark"
                    x: -12
                    y: -55
                    width: parent.width * 0.94
                    text: "REFRA"
                    color: root.theme.dark ? "#162a57" : "#dce6ff"
                    font.family: root.theme.displayFontFor(text)
                    font.pixelSize: Math.max(92, Math.min(160, parent.width * 0.155))
                    font.weight: Font.Black
                    font.letterSpacing: -7
                    rotation: -6
                    opacity: 0.96
                }
                Rectangle {
                    x: parent.width * 0.32
                    y: parent.height * 0.72
                    width: parent.width * 0.7
                    height: 30
                    rotation: -17
                    color: root.theme.spectrum
                    opacity: 0.88
                }
                Rectangle {
                    x: parent.width * 0.54
                    y: parent.height * 0.21
                    width: parent.width * 0.48
                    height: 15
                    rotation: -17
                    color: root.theme.accent
                    opacity: 0.82
                }
                Image {
                    objectName: "azureHomeHeroine"
                    source: Qt.resolvedUrl("../assets/heroine-home.png")
                    sourceSize.width: 1000
                    sourceSize.height: 800
                    fillMode: Image.PreserveAspectFit
                    horizontalAlignment: Image.AlignRight
                    verticalAlignment: Image.AlignBottom
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    width: parent.width * 0.66
                    height: parent.height * 1.12
                    z: 2
                    asynchronous: true
                    visible: status === Image.Ready
                    smooth: true
                }
                ColumnLayout {
                    x: 25
                    y: 48
                    width: Math.max(275, Math.min(parent.width * 0.51, 520))
                    spacing: 5
                    z: 3
                    Text {
                        text: "GAME SCREEN TRANSLATION / 01"
                        color: root.theme.accentText
                        font.family: root.theme.monoFontFor(text)
                        font.pixelSize: 10
                        font.letterSpacing: 1
                    }
                    Text {
                        text: "让看不懂的世界\n变得清晰。"
                        color: root.theme.text
                        font.family: root.theme.displayFontFor(text)
                        font.pixelSize: root.height < 610 ? 31 : 42
                        font.weight: Font.Bold
                        lineHeight: 1.06
                    }
                    Text {
                        objectName: "azureHomeRunState"
                        text: root.workbench.runState + "  ·  " + root.workbench.currentProfileName
                        color: root.workbench.runTone === "error" ? root.theme.danger
                             : root.workbench.runTone === "warning" ? root.theme.amber
                             : root.workbench.running ? root.theme.accent : root.theme.textSoft
                        font.family: root.theme.uiFontFor(text)
                        font.pixelSize: 13
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                    RowLayout {
                        Layout.topMargin: 5
                        spacing: 8
                        AzureButton {
                            objectName: "azureHomeStartButton"
                            theme: root.theme
                            primary: true
                            text: root.startPending ? "正在准备…" : root.workbench.startButtonText
                            enabled: root.workbench.runPhase !== "stopping"
                                     && !root.startPending
                                     && (root.workbench.canStart || root.workbench.running)
                            implicitWidth: 180
                            implicitHeight: 44
                            onClicked: root.requestLiveToggle()
                        }
                        AzureButton {
                            objectName: "azureManageProfilesButton"
                            theme: root.theme
                            quiet: true
                            text: "管理配置 ↓"
                            onClicked: homeScroll.contentY = Math.min(
                                           homeScroll.contentHeight - homeScroll.height,
                                           hero.height + 110)
                        }
                    }
                }
            }

            Item {
                objectName: "azureHomeSignalPanel"
                Layout.fillWidth: true
                Layout.preferredHeight: 126
                RowLayout {
                    anchors.fill: parent
                    spacing: 7
                    Repeater {
                        model: 4
                        Item {
                            required property int index
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            Layout.minimumWidth: 0
                            Rectangle {
                                anchors.left: parent.left
                                anchors.top: parent.top
                                width: index === 0 ? 3 : 2
                                height: parent.height
                                color: [root.theme.accent, root.theme.spectrum, root.theme.violet, root.theme.lineStrong][index]
                            }
                            ColumnLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 12
                                spacing: 4
                                Text {
                                    text: ["RUN STATE", "OCR", "TRANSLATION", "LAST RUN"][index]
                                    color: root.theme.accentText
                                    font.family: root.theme.monoFontFor(text)
                                    font.pixelSize: 9
                                    font.letterSpacing: 0.7
                                }
                                Text {
                                    text: [root.workbench.runState,
                                           root.workbench.ocrStatus,
                                           root.workbench.backend === "builtin" ? "内置本地模型" : "外部 API",
                                           root.workbench.lastRunStatus][index]
                                    color: root.theme.text
                                    font.family: root.theme.uiFontFor(text)
                                    font.pixelSize: index === 3 ? 11 : 13
                                    font.weight: Font.DemiBold
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                                Text {
                                    visible: index === 1 || index === 2 || index === 3
                                    text: index === 1 ? root.workbench.detectionQualitySummary
                                        : index === 2 ? (root.workbench.backend === "builtin"
                                            ? root.workbench.builtinModel : root.workbench.model)
                                        : index === 3 && root.workbench.lastRunAvailable
                                            ? "OCR " + root.workbench.lastRunOcrPeakText
                                              + "  /  LLM " + root.workbench.lastRunLlmPeakText
                                            : ""
                                    color: root.theme.textSoft
                                    font.family: root.theme.monoFontFor(text)
                                    font.pixelSize: 10
                                    elide: Text.ElideMiddle
                                    Layout.fillWidth: true
                                }
                            }
                        }
                    }
                }
            }

            Item {
                objectName: "azureHomeControlPanel"
                Layout.fillWidth: true
                Layout.preferredHeight: 458
                RowLayout {
                    anchors.fill: parent
                    spacing: 18

                    ColumnLayout {
                        objectName: "azureHomeProfileColumn"
                        Layout.fillWidth: true
                        Layout.minimumWidth: 190
                        Layout.topMargin: 0
                        Layout.leftMargin: 0
                        Layout.alignment: Qt.AlignTop
                        spacing: 7
                        Text {
                            text: "01  /  CONFIGURATION"
                            color: root.theme.accentText
                            font.family: root.theme.monoFontFor(text)
                            font.pixelSize: 10
                            font.letterSpacing: 0.7
                        }
                        Text {
                            text: "当前游戏配置"
                            color: root.theme.text
                            font.family: root.theme.displayFontFor(text)
                            font.pixelSize: 19
                            font.weight: Font.Bold
                        }
                        AzureComboBox {
                            objectName: "azureHomeProfileSelector"
                            theme: root.theme
                            Accessible.name: "当前游戏配置"
                            model: root.workbench.profileNames
                            currentIndex: root.workbench.currentProfileIndex
                            enabled: model.length > 0
                            Layout.fillWidth: true
                            onActivated: index => root.workbench.selectProfile(index)
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 5
                            AzureButton {
                                theme: root.theme; text: "刷新"; quiet: true
                                Layout.fillWidth: true
                                onClicked: root.workbench.refreshProfiles()
                            }
                            AzureButton {
                                objectName: "azureCreateProfileButton"
                                theme: root.theme; text: "＋ 新建"; primary: true
                                Layout.fillWidth: true
                                onClicked: createProfileDialog.open()
                            }
                            AzureButton {
                                objectName: "azureDeleteProfileButton"
                                theme: root.theme; text: "删除"; tone: "danger"; quiet: true
                                enabled: root.workbench.hasProfile && !root.workbench.running
                                         && root.workbench.runPhase !== "stopping"
                                Layout.fillWidth: true
                                onClicked: {
                                    deleteProfileDialog.profileId = root.workbench.currentProfileId
                                    deleteProfileDialog.profileName = root.workbench.currentProfileName
                                    deleteProfileDialog.open()
                                }
                            }
                        }
                        Text {
                            text: root.workbench.profileDirectory
                            color: root.theme.textDim
                            font.family: root.theme.monoFontFor(text)
                            font.pixelSize: 10
                            wrapMode: Text.WrapAnywhere
                            maximumLineCount: 2
                            elide: Text.ElideMiddle
                            Layout.fillWidth: true
                        }
                    }

                    ColumnLayout {
                        objectName: "azureHomeAppearanceColumn"
                        Layout.fillWidth: true
                        Layout.minimumWidth: 190
                        Layout.topMargin: 24
                        Layout.leftMargin: 12
                        Layout.alignment: Qt.AlignTop
                        spacing: 7
                        Text {
                            text: "02  /  APPEARANCE"
                            color: root.theme.accentText
                            font.family: root.theme.monoFontFor(text)
                            font.pixelSize: 10
                            font.letterSpacing: 0.7
                        }
                        Text {
                            text: "外观与动效"
                            color: root.theme.text
                            font.family: root.theme.displayFontFor(text)
                            font.pixelSize: 19
                            font.weight: Font.Bold
                        }
                        AzureComboBox {
                            objectName: "azureHomeSkinSelector"
                            theme: root.theme
                            Accessible.name: "界面皮肤"
                            model: root.skinNames
                            currentIndex: Math.max(0, root.skinValues.indexOf(root.workbench.skinPreference))
                            Layout.fillWidth: true
                            onActivated: index => {
                                if (index >= 0 && index < root.skinValues.length)
                                    root.workbench.setSkin(root.skinValues[index])
                            }
                        }
                        AzureComboBox {
                            objectName: "azureHomeThemeSelector"
                            theme: root.theme
                            Accessible.name: "界面主题"
                            model: root.themeNames
                            currentIndex: Math.max(0, root.themeValues.indexOf(root.workbench.themePreference))
                            Layout.fillWidth: true
                            onActivated: index => {
                                if (index >= 0 && index < root.themeValues.length)
                                    root.workbench.setTheme(root.themeValues[index])
                            }
                        }
                        AzureToggle {
                            theme: root.theme
                            text: "减少界面动效"
                            description: "减少页面切换和反馈动画。"
                            checked: root.workbench.reducedMotion
                            Layout.fillWidth: true
                            onToggled: root.workbench.setReducedMotion(checked)
                        }
                    }

                    ColumnLayout {
                        objectName: "azureHomeBehaviorColumn"
                        Layout.fillWidth: true
                        Layout.minimumWidth: 190
                        Layout.topMargin: 48
                        Layout.leftMargin: 20
                        Layout.alignment: Qt.AlignTop
                        spacing: 7
                        Text {
                            text: "03  /  BEHAVIOR"
                            color: root.theme.accentText
                            font.family: root.theme.monoFontFor(text)
                            font.pixelSize: 10
                            font.letterSpacing: 0.7
                        }
                        Text {
                            text: "启动与快捷键"
                            color: root.theme.text
                            font.family: root.theme.displayFontFor(text)
                            font.pixelSize: 19
                            font.weight: Font.Bold
                        }
                        AzureToggle {
                            objectName: "azureHomeStartupToggle"
                            theme: root.theme
                            text: "开机自启动"
                            description: "Windows 登录后静默启动并驻留系统托盘。"
                            checked: root.workbench.startWithWindows
                            Layout.fillWidth: true
                            onToggled: root.workbench.setStartWithWindows(checked)
                        }
                        FocusScope {
                            id: hotkeyField
                            objectName: "azureHotkeyField"
                            Layout.fillWidth: true
                            Layout.preferredHeight: 40
                            activeFocusOnTab: true
                            Accessible.name: "全局翻译快捷键"
                            Accessible.description: "按住 Ctrl、Alt、Shift 或 Win 中至少一个，再按另一个键。"
                            Keys.onPressed: event => root.recordHotkey(event)
                            Rectangle {
                                anchors.fill: parent
                                color: root.theme.inputSurface
                                border.color: hotkeyField.activeFocus ? root.theme.spectrum : root.theme.lineStrong
                                border.width: hotkeyField.activeFocus ? 2 : 1
                                Text {
                                    objectName: "azureHotkeyDisplay"
                                    anchors.fill: parent
                                    anchors.leftMargin: 11
                                    anchors.rightMargin: 9
                                    text: root.hotkeyRecording ? "按下组合键…（Esc 取消）" : root.workbench.hotkeyPreference
                                    color: root.theme.text
                                    font.family: root.theme.monoFontFor(text)
                                    font.pixelSize: 13
                                    verticalAlignment: Text.AlignVCenter
                                    elide: Text.ElideRight
                                }
                            }
                        }
                        AzureComboBox {
                            objectName: "azureHotkeyBehaviorSelector"
                            theme: root.theme
                            Accessible.name: "快捷键行为"
                            model: root.hotkeyNames
                            currentIndex: Math.max(0, root.hotkeyValues.indexOf(root.workbench.hotkeyBehaviorPreference))
                            Layout.fillWidth: true
                            onActivated: index => {
                                if (index >= 0 && index < root.hotkeyValues.length)
                                    root.workbench.setHotkeyBehavior(root.hotkeyValues[index])
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 5
                            AzureButton {
                                objectName: "azureHotkeyRecordButton"
                                theme: root.theme
                                text: root.hotkeyRecording ? "录制中…" : "录制"
                                primary: root.hotkeyRecording
                                Layout.fillWidth: true
                                onClicked: {
                                    root.hotkeyRecording = true
                                    hotkeyField.forceActiveFocus()
                                }
                            }
                            AzureButton {
                                objectName: "azureHotkeyDefaultButton"
                                theme: root.theme
                                text: "恢复默认"
                                quiet: true
                                Layout.fillWidth: true
                                onClicked: {
                                    root.hotkeyRecording = false
                                    root.workbench.setHotkey("Ctrl+Alt+T")
                                }
                            }
                        }
                        Text {
                            visible: root.hotkeyRecording
                            text: "按住 Ctrl、Alt、Shift 或 Win，再按另一个键。"
                            color: root.theme.amber
                            font.family: root.theme.uiFontFor(text)
                            font.pixelSize: 10
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                    }
                }
            }
        }
    }
}
