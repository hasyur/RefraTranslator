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
    property bool startPreludePending: false
    readonly property bool compactOverview: height < 580
    readonly property var themeValues: ["system", "dark", "light"]
    readonly property var skinValues: ["prism", "dohna"]
    readonly property var hotkeyBehaviorValues: ["start_only", "toggle", "toggle_show"]
    readonly property var hotkeyBehaviorLabels: ["仅启动", "启动 / 停止翻译", "启动 / 停止并打开 GUI"]
    readonly property var p3PageOrder: ["HOME", "CAPTURE", "OCR", "TRANSLATION", "OVERLAY", "CACHE", "SETTINGS"]
    property bool hotkeyRecording: false
    signal liveToggleRequested()
    signal saveRequested()

    function p3MenuTitle(page) {
        const titles = {
            "HOME": "HOME", "CAPTURE": "CAPTURE", "OCR": "OCR",
            "TRANSLATION": "TRANSLATE", "OVERLAY": "OVERLAY",
            "CACHE": "CACHE", "SETTINGS": "SETTINGS"
        }
        return titles[page] || page
    }

    function p3MenuSubtitle(page) {
        const labels = {
            "HOME": "总览", "CAPTURE": "捕获", "OCR": "文字识别",
            "TRANSLATION": "翻译", "OVERLAY": "覆盖层",
            "CACHE": "缓存", "SETTINGS": "设置"
        }
        return labels[page] || page
    }

    function hotkeyKeyName(key) {
        if (key >= Qt.Key_A && key <= Qt.Key_Z)
            return String.fromCharCode(key)
        if (key >= Qt.Key_0 && key <= Qt.Key_9)
            return String.fromCharCode(key)
        if (key >= Qt.Key_F1 && key <= Qt.Key_F24)
            return "F" + (key - Qt.Key_F1 + 1)
        if (key === Qt.Key_Space)
            return "Space"
        if (key === Qt.Key_Tab || key === Qt.Key_Backtab)
            return "Tab"
        if (key === Qt.Key_Return || key === Qt.Key_Enter)
            return "Enter"
        if (key === Qt.Key_Backspace)
            return "Backspace"
        if (key === Qt.Key_Escape
                || key === Qt.Key_Control || key === Qt.Key_Alt
                || key === Qt.Key_Shift || key === Qt.Key_Meta)
            return ""
        if (key === Qt.Key_Insert)
            return "Insert"
        if (key === Qt.Key_Delete)
            return "Delete"
        if (key === Qt.Key_Home)
            return "Home"
        if (key === Qt.Key_End)
            return "End"
        if (key === Qt.Key_PageUp)
            return "PageUp"
        if (key === Qt.Key_PageDown)
            return "PageDown"
        if (key === Qt.Key_Left)
            return "Left"
        if (key === Qt.Key_Right)
            return "Right"
        if (key === Qt.Key_Up)
            return "Up"
        if (key === Qt.Key_Down)
            return "Down"
        return ""
    }

    function recordHotkey(event) {
        if (!root.hotkeyRecording)
            return
        event.accepted = true
        if (event.isAutoRepeat)
            return
        if (event.key === Qt.Key_Escape) {
            root.hotkeyRecording = false
            return
        }
        var keyName = root.hotkeyKeyName(event.key)
        if (keyName.length === 0)
            return
        var modifiers = []
        if ((event.modifiers & Qt.ControlModifier) !== 0)
            modifiers.push("Ctrl")
        if ((event.modifiers & Qt.AltModifier) !== 0)
            modifiers.push("Alt")
        if ((event.modifiers & Qt.ShiftModifier) !== 0)
            modifiers.push("Shift")
        if ((event.modifiers & Qt.MetaModifier) !== 0)
            modifiers.push("Win")
        if (modifiers.length === 0)
            return
        root.hotkeyRecording = false
        root.workbench.setHotkey(modifiers.join("+") + "+" + keyName)
    }

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
            font.pixelSize: 15
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

    PrismDialog {
        id: deleteProfileDialog
        objectName: "deleteProfileDialog"
        surfaceName: "deleteProfileDialog"
        property string profileId: ""
        property string profileName: ""
        theme: root.theme
        parent: Overlay.overlay
        anchors.centerIn: parent
        title: "删除游戏配置"
        acceptText: "删除配置"
        acceptTone: "danger"
        rejectText: "取消"
        acceptEnabled: root.workbench.hasProfile && !root.workbench.running
                       && root.workbench.runPhase !== "stopping"
        width: 420

        Text {
            text: "确定删除“" + deleteProfileDialog.profileName
                  + "”？该配置的设置、术语表、翻译缓存、手动修正和运行快照将一并删除，无法撤销。"
            color: root.theme.textSoft
            font.family: root.theme.uiFontFor(text)
            font.pixelSize: 15
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        onAccepted: root.workbench.deleteProfile(profileId)
    }

    PrismDialog {
        id: refraPreferencesDialog
        objectName: "refraPreferencesDialog"
        surfaceName: "refraPreferencesDialog"
        theme: root.theme
        parent: Overlay.overlay
        anchors.centerIn: parent
        title: "工作台偏好"
        acceptText: "完成"
        showRejectButton: false
        width: Math.min(650, root.width - 54)

        ScrollView {
            objectName: "refraPreferencesScroll"
            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(470, root.height - 280)
            clip: true
            ScrollBar.vertical: PrismScrollBar { theme: root.theme }

            ColumnLayout {
                width: parent.width
                spacing: 12

                SectionHeader {
                    theme: root.theme
                    title: "外观"
                    meta: "APPEARANCE"
                    Layout.fillWidth: true
                }
                PrismComboBox {
                    objectName: "refraHomeSkinSelector"
                    theme: root.theme
                    accessibleName: "界面皮肤"
                    settingDescription: "选择工作台的视觉皮肤；Dohna 使用固定的明亮配色。"
                    settingKey: "home-skin"
                    model: ["Prism", "Dohna"]
                    currentIndex: root.workbench.skinPreference === "dohna" ? 1 : 0
                    Layout.fillWidth: true
                    onActivated: index => {
                        root.workbench.setSkin(index === 1 ? "dohna" : "prism")
                        refraPreferencesDialog.close()
                    }
                }
                PrismComboBox {
                    objectName: "refraHomeThemeSelector"
                    theme: root.theme
                    accessibleName: "界面主题"
                    settingDescription: "选择工作台使用的颜色主题。"
                    settingKey: "home-theme"
                    model: ["跟随系统", "深色", "浅色"]
                    currentIndex: Math.max(0, root.themeValues.indexOf(root.workbench.themePreference))
                    enabled: root.workbench.skinPreference !== "dohna"
                    Layout.fillWidth: true
                    onActivated: index => {
                        if (index >= 0 && index < root.themeValues.length)
                            root.workbench.setTheme(root.themeValues[index])
                        refraPreferencesDialog.close()
                    }
                }
                PrismToggle {
                    objectName: "refraHomeReducedMotionToggle"
                    theme: root.theme
                    text: "减少界面动效"
                    settingDescription: "减少页面切换和反馈动画。"
                    settingKey: "home-motion"
                    checked: root.workbench.reducedMotion
                    Layout.fillWidth: true
                    onToggled: root.workbench.setReducedMotion(checked)
                }
                PrismToggle {
                    objectName: "refraHomeStartupToggle"
                    theme: root.theme
                    text: "开机自启动"
                    settingDescription: "Windows 登录后静默启动 RefraTranslator，并在系统托盘驻留。"
                    settingKey: "home-startup"
                    checked: root.workbench.startWithWindows
                    Layout.fillWidth: true
                    onToggled: root.workbench.setStartWithWindows(checked)
                }

                SectionHeader {
                    theme: root.theme
                    title: "全局快捷键"
                    meta: "HOTKEY"
                    Layout.fillWidth: true
                    Layout.topMargin: 6
                }
                Item {
                    id: refraHotkeyField
                    objectName: "refraHotkeyField"
                    Layout.fillWidth: true
                    Layout.preferredHeight: 42
                    focus: root.hotkeyRecording
                    activeFocusOnTab: true
                    Accessible.name: "全局翻译快捷键"
                    Keys.onPressed: event => root.recordHotkey(event)
                    Rectangle {
                        anchors.fill: parent
                        color: root.theme.inputSurface
                        border.color: refraHotkeyField.activeFocus ? root.theme.selectionEdge : root.theme.lineStrong
                        border.width: refraHotkeyField.activeFocus ? 2 : 1
                        Text {
                            objectName: "refraHotkeyDisplay"
                            anchors.fill: parent
                            anchors.leftMargin: 12
                            anchors.rightMargin: 12
                            text: root.workbench.hotkeyPreference
                            color: root.theme.text
                            font.family: root.theme.uiFontFor(text)
                            font.pixelSize: 15
                            verticalAlignment: Text.AlignVCenter
                        }
                    }
                    SettingHint {
                        theme: root.theme
                        target: refraHotkeyField
                        description: "按住 Ctrl、Alt、Shift 或 Win 中的至少一个，再按另一个键，例如 Ctrl+Alt+T。"
                        settingKey: "home-hotkey"
                    }
                }
                PrismComboBox {
                    objectName: "refraHotkeyBehaviorSelector"
                    theme: root.theme
                    accessibleName: "快捷键行为"
                    settingDescription: "选择翻译已经运行时再次按下全局快捷键的处理方式。"
                    settingKey: "home-hotkey-behavior"
                    model: root.hotkeyBehaviorLabels
                    currentIndex: Math.max(0, root.hotkeyBehaviorValues.indexOf(root.workbench.hotkeyBehaviorPreference))
                    Layout.fillWidth: true
                    onActivated: index => {
                        if (index >= 0 && index < root.hotkeyBehaviorValues.length)
                            root.workbench.setHotkeyBehavior(root.hotkeyBehaviorValues[index])
                    }
                }
                Text {
                    objectName: "refraHotkeyRecordingHint"
                    visible: root.hotkeyRecording
                    text: "正在录制：按住 Ctrl、Alt、Shift 或 Win，再按另一个键；Esc 取消"
                    color: root.theme.amber
                    font.family: root.theme.uiFontFor(text)
                    font.pixelSize: 13
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    PrismButton {
                        objectName: "refraHotkeyRecordButton"
                        theme: root.theme
                        primary: root.hotkeyRecording
                        text: root.hotkeyRecording ? "按下组合键…" : "录制快捷键"
                        Layout.fillWidth: true
                        onClicked: {
                            root.hotkeyRecording = true
                            refraHotkeyField.forceActiveFocus()
                        }
                    }
                    PrismButton {
                        objectName: "refraHotkeyDefaultButton"
                        theme: root.theme
                        text: "恢复默认"
                        Layout.fillWidth: true
                        onClicked: {
                            root.hotkeyRecording = false
                            root.workbench.setHotkey("Ctrl+Alt+T")
                        }
                    }
                }
            }
        }
        onClosed: root.hotkeyRecording = false
    }

    Item {
        id: refraDarkHome
        objectName: "refraDarkHome"
        anchors.fill: parent
        visible: root.theme.refraDark
        enabled: root.theme.refraDark

        ColumnLayout {
            anchors.fill: parent
            spacing: 0

            Item {
                objectName: "refraDarkHomeStage"
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumHeight: 390

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: root.width < 1100 ? 24 : 42
                    anchors.rightMargin: root.width < 1100 ? 18 : 34
                    anchors.topMargin: root.height < 760 ? 16 : 24
                    anchors.bottomMargin: 8
                    spacing: 14

                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.preferredWidth: parent.width * 0.55
                        Layout.minimumWidth: 420
                        Layout.maximumWidth: 570
                        spacing: 0

                        RowLayout {
                            spacing: 8
                            Text {
                                text: "REFRA"
                                color: root.theme.accent
                                font.family: "Arial Narrow"
                                font.pixelSize: 22
                                font.weight: Font.Bold
                                font.letterSpacing: 0.8
                            }
                            Text {
                                text: "TRANSLATOR"
                                color: root.theme.text
                                font.family: root.theme.monoFontFor(text)
                                font.pixelSize: 12
                                font.letterSpacing: 1.4
                            }
                        }
                        ColumnLayout {
                            objectName: "refraDarkNavigationMenu"
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            Layout.topMargin: 7
                            spacing: 0

                            Repeater {
                                model: root.p3PageOrder
                                PrismButton {
                                    objectName: "refraDarkNavigationButton" + index
                                    required property int index
                                    required property var modelData
                                    theme: root.theme
                                    navigation: true
                                    navigationHero: true
                                    navigationNumber: String(index + 1).padStart(2, "0")
                                    navigationSubtitle: root.p3MenuSubtitle(String(modelData))
                                    navigationCool: index % 2 === 1
                                    navigationTilt: index % 2 === 0 ? -3.8 : -5.7
                                    text: root.p3MenuTitle(String(modelData))
                                    primary: root.workbench.currentPage === modelData
                                    quiet: !primary
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: Math.max(44, Math.min(54, root.height * 0.066))
                                    Layout.minimumHeight: 44
                                    Layout.leftMargin: index % 3 === 1 ? 14 : index % 3 === 2 ? 6 : 0
                                    Layout.rightMargin: index % 3 === 0 ? 18 : 4
                                    onClicked: root.workbench.setPage(String(modelData))
                                }
                            }
                        }
                    }

                    Item {
                        objectName: "refraDarkHeroStage"
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.preferredWidth: parent.width * 0.45
                        Layout.minimumWidth: 280

                        Rectangle {
                            x: parent.width * 0.08
                            y: parent.height * 0.48
                            width: parent.width * 0.92
                            height: 1
                            color: root.theme.accent
                            opacity: 0.24
                            rotation: -12
                        }
                        Rectangle {
                            x: parent.width * 0.17
                            y: parent.height * 0.60
                            width: parent.width * 0.78
                            height: 1
                            color: root.theme.spectrum
                            opacity: 0.22
                            rotation: -12
                        }
                        Image {
                            objectName: "refraDarkHeroImage"
                            anchors.horizontalCenter: parent.horizontalCenter
                            anchors.verticalCenter: parent.verticalCenter
                            width: parent.width * 0.82
                            height: parent.height * 0.65
                            source: "../assets/refra-hero-dark.png"
                            fillMode: Image.PreserveAspectFit
                            smooth: true
                        }
                        ColumnLayout {
                            anchors.horizontalCenter: parent.horizontalCenter
                            anchors.bottom: parent.bottom
                            anchors.bottomMargin: 12
                            spacing: 4
                            Text {
                                text: root.workbench.currentProfileName
                                color: root.theme.text
                                font.family: root.theme.uiFontFor(text)
                                font.pixelSize: 18
                                font.weight: Font.DemiBold
                                horizontalAlignment: Text.AlignHCenter
                                Layout.alignment: Qt.AlignHCenter
                            }
                            Text {
                                text: root.workbench.running ? "● 正在翻译" : "● 未启动"
                                color: root.workbench.running ? root.theme.accent : root.theme.textSoft
                                font.family: root.theme.uiFontFor(text)
                                font.pixelSize: 13
                                horizontalAlignment: Text.AlignHCenter
                                Layout.alignment: Qt.AlignHCenter
                            }
                        }
                    }
                }
            }

            Rectangle {
                objectName: "refraDarkHomeRule"
                Layout.fillWidth: true
                Layout.preferredHeight: 1
                color: root.theme.lineStrong
                opacity: 0.76
            }

            RowLayout {
                objectName: "refraDarkHomeStatusBand"
                Layout.fillWidth: true
                Layout.preferredHeight: root.height < 760 ? 136 : 160
                Layout.minimumHeight: 126
                Layout.leftMargin: root.width < 1100 ? 22 : 42
                Layout.rightMargin: root.width < 1100 ? 20 : 36
                Layout.topMargin: 5
                Layout.bottomMargin: 2
                spacing: 0

                ColumnLayout {
                    objectName: "refraDarkProfileSummary"
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignTop
                    Layout.minimumWidth: 210
                    Layout.preferredWidth: 270
                    Layout.rightMargin: 18
                    spacing: 4
                    Text {
                        text: "系统状态"
                        color: root.theme.text
                        font.family: root.theme.uiFontFor(text)
                        font.pixelSize: 14
                        font.weight: Font.Bold
                    }
                    RowLayout {
                        spacing: 7
                        Rectangle {
                            Layout.preferredWidth: 7
                            Layout.preferredHeight: 7
                            radius: 4
                            color: root.workbench.runTone === "error" ? root.theme.danger
                                 : root.workbench.runTone === "warning" ? root.theme.amber
                                 : root.workbench.running ? root.theme.accent : root.theme.textDim
                        }
                        Text {
                            objectName: "refraDarkRunState"
                            text: root.workbench.runState
                            color: root.workbench.runTone === "error" ? root.theme.danger
                                 : root.workbench.runTone === "warning" ? root.theme.amber
                                 : root.workbench.running ? root.theme.accent : root.theme.text
                            font.family: root.theme.uiFontFor(text)
                            font.pixelSize: 18
                            font.weight: Font.DemiBold
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                    }
                    PrismComboBox {
                        objectName: "refraDarkProfileSelector"
                        theme: root.theme
                        accessibleName: "当前配置"
                        settingDescription: "选择当前游戏的配置。"
                        settingKey: "home-profile"
                        model: root.workbench.profileNames
                        currentIndex: root.workbench.currentProfileIndex
                        enabled: model.length > 0
                        Layout.fillWidth: true
                        onActivated: index => root.workbench.selectProfile(index)
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 5
                        PrismButton {
                            objectName: "refraDarkRefreshProfiles"
                            theme: root.theme
                            text: "刷新"
                            Layout.fillWidth: true
                            Layout.minimumWidth: 45
                            onClicked: root.workbench.refreshProfiles()
                        }
                        PrismButton {
                            objectName: "refraDarkCreateProfile"
                            theme: root.theme
                            text: "新建"
                            primary: true
                            Layout.fillWidth: true
                            Layout.minimumWidth: 45
                            onClicked: createProfileDialog.open()
                        }
                        PrismButton {
                            objectName: "refraDarkDeleteProfile"
                            theme: root.theme
                            text: "删除"
                            tone: "danger"
                            enabled: root.workbench.hasProfile && !root.workbench.running
                                     && root.workbench.runPhase !== "stopping"
                            Layout.fillWidth: true
                            Layout.minimumWidth: 45
                            onClicked: {
                                deleteProfileDialog.profileId = root.workbench.profileIds[root.workbench.currentProfileIndex]
                                deleteProfileDialog.profileName = root.workbench.currentProfileName
                                deleteProfileDialog.open()
                            }
                        }
                    }
                }

                Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; color: root.theme.lineStrong; opacity: 0.75 }

                ColumnLayout {
                    objectName: "refraDarkOcrSummary"
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignTop
                    Layout.minimumWidth: 170
                    Layout.leftMargin: 22
                    Layout.rightMargin: 18
                    spacing: 5
                    Text { text: "OCR"; color: root.theme.accent; font.family: root.theme.monoFontFor(text); font.pixelSize: 12; font.letterSpacing: 1 }
                    Text {
                        objectName: "refraDarkOcrStatus"
                        text: root.workbench.ocrStatus
                        color: root.theme.text
                        font.family: root.theme.uiFontFor(text)
                        font.pixelSize: 17
                        font.weight: Font.Medium
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                    Text {
                        text: root.workbench.detectionQualitySummary
                        color: root.theme.textSoft
                        font.family: root.theme.monoFontFor(text)
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                        maximumLineCount: 2
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                }

                Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; color: root.theme.lineStrong; opacity: 0.75 }

                ColumnLayout {
                    objectName: "refraDarkTranslationSummary"
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignTop
                    Layout.minimumWidth: 175
                    Layout.leftMargin: 22
                    Layout.rightMargin: 18
                    spacing: 5
                    Text { text: "TRANSLATION"; color: root.theme.textSoft; font.family: root.theme.monoFontFor(text); font.pixelSize: 12; font.letterSpacing: 0.7 }
                    Text {
                        text: root.workbench.backend === "builtin" ? "内置本地模型" : "外部 API"
                        color: root.theme.text
                        font.family: root.theme.uiFontFor(text)
                        font.pixelSize: 17
                        font.weight: Font.Medium
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                    Flickable {
                        objectName: "refraDarkModelScroll"
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.minimumHeight: 20
                        contentWidth: width
                        contentHeight: modelName.implicitHeight
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        ScrollBar.vertical: PrismScrollBar { theme: root.theme }
                        Text {
                            id: modelName
                            objectName: "refraDarkModelName"
                            width: parent.width
                            text: root.workbench.backend === "builtin" ? root.workbench.builtinModel : root.workbench.model
                            color: root.theme.textSoft
                            font.family: root.theme.monoFontFor(text)
                            font.pixelSize: 11
                            wrapMode: Text.WrapAnywhere
                        }
                    }
                }

                Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; color: root.theme.lineStrong; opacity: 0.75 }

                ColumnLayout {
                    objectName: "refraDarkLastRunSummary"
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignTop
                    Layout.minimumWidth: 190
                    Layout.leftMargin: 22
                    spacing: 5
                    Text { text: "上次运行"; color: root.theme.text; font.family: root.theme.uiFontFor(text); font.pixelSize: 14; font.weight: Font.Bold }
                    Text {
                        objectName: "refraDarkLastRunStatus"
                        text: root.workbench.lastRunAvailable ? root.workbench.lastRunStatus
                              : "尚无上次正常且有效的运行结果"
                        color: root.workbench.lastRunAvailable ? root.theme.textSoft : root.theme.textDim
                        font.family: root.theme.uiFontFor(text)
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                        maximumLineCount: 2
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                    Text {
                        text: root.workbench.lastRunAvailable
                              ? "OCR " + root.workbench.lastRunOcrPeakText + "  ·  LLM " + root.workbench.lastRunLlmPeakText
                              : "快捷键  " + root.workbench.hotkeyPreference
                        color: root.theme.accent
                        font.family: root.theme.monoFontFor(text)
                        font.pixelSize: 11
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                    Text {
                        visible: root.workbench.lastRunAvailable
                        text: "快捷键  " + root.workbench.hotkeyPreference
                        color: root.theme.textDim
                        font.family: root.theme.monoFontFor(text)
                        font.pixelSize: 10
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 1
                Layout.leftMargin: root.width < 1100 ? 22 : 42
                Layout.rightMargin: root.width < 1100 ? 20 : 36
                color: root.theme.line
            }

            RowLayout {
                objectName: "refraDarkHomeActions"
                Layout.fillWidth: true
                Layout.preferredHeight: root.height < 760 ? 56 : 64
                Layout.leftMargin: root.width < 1100 ? 22 : 42
                Layout.rightMargin: root.width < 1100 ? 20 : 36
                Layout.bottomMargin: 4
                spacing: 12
                PrismButton {
                    objectName: "refraDarkPreferencesButton"
                    theme: root.theme
                    text: "工作台偏好"
                    onClicked: refraPreferencesDialog.open()
                }
                ColumnLayout {
                    objectName: "refraDarkHomeActionFeedback"
                    Layout.fillWidth: true
                    Layout.minimumWidth: 110
                    spacing: 2
                    Text {
                        text: "皮肤 · 主题 · 动效 · 自启动"
                        color: root.theme.textDim
                        font.family: root.theme.uiFontFor(text)
                        font.pixelSize: 11
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                    RowLayout {
                        objectName: "refraDarkHomeFeedbackRow"
                        Layout.fillWidth: true
                        spacing: 5
                        Rectangle {
                            objectName: "refraDarkHomeStatusDot"
                            Layout.preferredWidth: 6
                            Layout.preferredHeight: 6
                            radius: 3
                            color: root.workbench.settingsDirty ? root.theme.amber
                                 : root.workbench.statusTone === "error" ? root.theme.danger
                                 : root.workbench.statusTone === "warning" ? root.theme.amber
                                 : root.workbench.statusTone === "success" ? root.theme.accent
                                 : root.theme.textDim
                        }
                        Text {
                            objectName: "refraDarkHomeStatusText"
                            visible: !root.workbench.settingsDirty
                            text: root.workbench.statusText
                            color: root.workbench.statusTone === "error" ? root.theme.danger
                                 : root.workbench.statusTone === "warning" ? root.theme.amber
                                 : root.workbench.statusTone === "success" ? root.theme.accent
                                 : root.theme.textSoft
                            font.family: root.theme.uiFontFor(text)
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                            maximumLineCount: 2
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                        Text {
                            objectName: "refraDarkHomeUnsavedStatus"
                            visible: root.workbench.settingsDirty
                            text: "有未应用更改"
                            color: root.theme.amber
                            font.family: root.theme.uiFontFor(text)
                            font.pixelSize: 11
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                    }
                }
                PrismButton {
                    objectName: "refraDarkApplyButton"
                    theme: root.theme
                    text: "应用更改"
                    enabled: root.workbench.hasProfile
                    onClicked: root.saveRequested()
                }
                PrismButton {
                    objectName: "refraDarkStartButton"
                    theme: root.theme
                    primary: true
                    text: root.startPreludePending ? "正在启动…" : root.workbench.startButtonText
                    enabled: root.workbench.runPhase !== "stopping"
                             && !root.startPreludePending
                             && (root.workbench.canStart || root.workbench.running)
                    onClicked: root.liveToggleRequested()
                }
            }
        }
    }

    RowLayout {
        anchors.fill: parent
        visible: !root.theme.refraDark
        enabled: !root.theme.refraDark
        spacing: 16

        PrismPanel {
            objectName: "homePrimaryPanel"
            theme: root.theme
            padding: root.compactOverview ? 16 : 22
            motionRole: "primary"
            transitionSerial: root.transitionSerial
            motionEnabled: root.pageMotionEnabled && root.visible
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumWidth: 390

            Flickable {
                objectName: "homePrimaryScroll"
                anchors.fill: parent
                contentWidth: width
                contentHeight: homePrimaryContent.implicitHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: PrismScrollBar { id: homePrimaryBar; theme: root.theme }

                ColumnLayout {
                    id: homePrimaryContent
                    objectName: "homePrimaryContent"
                    width: parent.width - homePrimaryBar.contentInset
                    height: implicitHeight
                    spacing: root.compactOverview ? 4 : 14

                SectionHeader {
                    theme: root.theme
                    title: root.theme.dohna ? "光学信号场" : "系统状态"
                    meta: root.theme.dohna ? "LIVE CONTROL" : "SYSTEM STATUS"
                    Layout.fillWidth: true
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: root.compactOverview ? 4 : 7
                    Text {
                        objectName: "homeRunHero"
                        text: root.workbench.runState
                        color: root.workbench.runTone === "error" ? root.theme.danger
                             : root.workbench.runTone === "warning" ? root.theme.amber
                             : root.workbench.running ? root.theme.accent : root.theme.text
                        font.family: root.theme.displayFontFor(text)
                        font.pixelSize: root.compactOverview ? 40 : 54
                        font.weight: Font.Bold
                    }
                    Text {
                        objectName: "homeProfileName"
                        text: root.workbench.currentProfileName
                        color: root.theme.textSoft
                        font.family: root.theme.uiFontFor(text)
                        font.pixelSize: root.compactOverview ? 18 : 20
                        font.weight: Font.Medium
                    }
                }

                RowLayout {
                    objectName: "homeSignalCards"
                    Layout.fillWidth: true
                    Layout.preferredHeight: root.compactOverview ? 100 : 132
                    Layout.minimumHeight: Layout.preferredHeight
                    spacing: 12

                    Item {
                        objectName: "homeOcrSignalGroup"
                        Layout.fillWidth: true
                        Layout.fillHeight: true

                        Rectangle {
                            objectName: "homeOcrSignalAccent"
                            width: 4
                            anchors.left: parent.left
                            anchors.top: parent.top
                            anchors.bottom: parent.bottom
                            color: root.theme.accent
                        }

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: root.compactOverview ? 10 : 18
                            anchors.leftMargin: root.compactOverview ? 16 : 24
                            spacing: 6
                            Text {
                                objectName: "homeOcrSignalLabel"
                                text: "OCR"
                                color: root.theme.accentText
                                font.family: root.theme.monoFontFor(text)
                                font.pixelSize: 13
                                font.letterSpacing: 1.4
                            }
                            Text {
                                objectName: "homeOcrSignalValue"
                                text: root.workbench.ocrStatus
                                color: root.theme.text
                                font.family: root.theme.uiFontFor(text)
                                font.pixelSize: 20
                                font.weight: Font.Medium
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }
                            Text {
                                text: root.workbench.detectionQualitySummary
                                color: root.theme.textSoft
                                font.family: root.theme.monoFontFor(text)
                                font.pixelSize: 12
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }
                            Item { Layout.fillHeight: true }
                        }
                    }

                    Item {
                        objectName: "homeTranslationSignalGroup"
                        Layout.fillWidth: true
                        Layout.fillHeight: true

                        Rectangle {
                            objectName: "homeTranslationSignalSpectrum"
                            width: 4
                            anchors.left: parent.left
                            anchors.top: parent.top
                            anchors.bottom: parent.bottom
                            color: root.theme.spectrum
                        }

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: root.compactOverview ? 10 : 18
                            anchors.leftMargin: root.compactOverview ? 16 : 24
                            spacing: 6
                            Text {
                                objectName: "homeTranslationSignalLabel"
                                text: "TRANSLATION"
                                color: root.theme.spectrumText
                                font.family: root.theme.monoFontFor(text)
                                font.pixelSize: 13
                                font.letterSpacing: 1.4
                            }
                            Text {
                                objectName: "homeTranslationSignalValue"
                                text: root.workbench.backend === "builtin" ? "内置本地模型" : "外部 API"
                                color: root.theme.text
                                font.family: root.theme.uiFontFor(text)
                                font.pixelSize: 20
                                font.weight: Font.Medium
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }
                            Text {
                                text: root.workbench.backend === "builtin" ? root.workbench.builtinModel : root.workbench.model
                                color: root.theme.textSoft
                                font.family: root.theme.monoFontFor(text)
                                font.pixelSize: 12
                                elide: Text.ElideMiddle
                                Layout.fillWidth: true
                            }
                            Item { Layout.fillHeight: true }
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
                    Layout.minimumHeight: 196
                    implicitHeight: Math.max(
                        196,
                        homeLastRunMetricsContent.implicitHeight + 32
                    )
                    color: Qt.rgba(root.theme.accent.r, root.theme.accent.g, root.theme.accent.b, 0.025)
                    border.color: root.theme.line
                    ColumnLayout {
                        id: homeLastRunMetricsContent
                        objectName: "homeLastRunMetricsContent"
                        anchors.fill: parent
                        anchors.margins: 16
                        spacing: root.compactOverview ? 8 : 12
                        Text {
                            objectName: "homeLastRunStatus"
                            text: root.workbench.lastRunStatus
                            color: root.theme.accent
                            font.family: root.theme.monoFontFor(text)
                            font.pixelSize: 13
                            font.letterSpacing: 1.1
                            Layout.fillWidth: true
                        }
                        RowLayout {
                            objectName: "homePeakCards"
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            spacing: 12

                            Item {
                                objectName: "homeOcrPeakGroup"
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                Layout.minimumHeight: 142
                                ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: 18
                                    spacing: 7
                                    Text {
                                        text: "OCR 峰值"
                                        color: root.theme.textSoft
                                        font.family: root.theme.uiFontFor(text)
                                        font.pixelSize: 14
                                    }
                                    Rectangle {
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 2
                                        color: root.theme.accent
                                        opacity: 0.6
                                    }
                                    Text {
                                        objectName: "homeOcrPeakValue"
                                        text: root.workbench.lastRunOcrPeakText
                                        color: root.theme.accent
                                        font.family: root.theme.displayFontFor(text)
                                        font.pixelSize: 44
                                        font.weight: Font.Bold
                                    }
                                    Item { Layout.fillHeight: true }
                                }
                            }

                            Item {
                                objectName: "homeLlmPeakGroup"
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                Layout.minimumHeight: 142
                                ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: 18
                                    spacing: 7
                                    Text {
                                        text: "LLM 峰值"
                                        color: root.theme.textSoft
                                        font.family: root.theme.uiFontFor(text)
                                        font.pixelSize: 14
                                    }
                                    Rectangle {
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 2
                                        color: root.theme.spectrum
                                        opacity: 0.6
                                    }
                                    Text {
                                        objectName: "homeLlmPeakValue"
                                        text: root.workbench.lastRunLlmPeakText
                                        color: root.theme.spectrum
                                        font.family: root.theme.displayFontFor(text)
                                        font.pixelSize: 44
                                        font.weight: Font.Bold
                                    }
                                    Item { Layout.fillHeight: true }
                                }
                            }
                        }
                        Text {
                            objectName: "homeLastRunFootnote"
                            text: "仅统计上次正常且有效运行；未产生的单项显示“未产生”。"
                            color: root.theme.textDim
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

            Flickable {
                id: homeSecondaryScroll
                objectName: "homeSecondaryScroll"
                anchors.fill: parent
                contentWidth: width
                contentHeight: homeSecondaryContent.implicitHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: PrismScrollBar { id: homeSecondaryBar; theme: root.theme }

                ColumnLayout {
                    id: homeSecondaryContent
                    width: homeSecondaryScroll.width - homeSecondaryBar.contentInset
                    height: implicitHeight
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
                    meta: root.workbench.hasProfile ? "" : "REQUIRED"
                    description: "选择要整套读取和保存捕获、OCR、翻译、覆盖层与运行参数的游戏配置。"
                    settingKey: "home-profile"
                }
                PrismComboBox {
                    objectName: "homeProfileSelector"
                    theme: root.theme
                    accessibleName: "当前配置"
                    settingDescription: "选择要整套读取和保存捕获、OCR、翻译、覆盖层与运行参数的游戏配置。"
                    settingKey: "home-profile"
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
                    PrismButton {
                        objectName: "openDeleteProfileDialogButton"
                        theme: root.theme
                        text: "删除"
                        tone: "danger"
                        enabled: root.workbench.hasProfile && !root.workbench.running
                                 && root.workbench.runPhase !== "stopping"
                        Layout.fillWidth: true
                        onClicked: {
                            deleteProfileDialog.profileId = root.workbench.profileIds[root.workbench.currentProfileIndex]
                            deleteProfileDialog.profileName = root.workbench.currentProfileName
                            deleteProfileDialog.open()
                        }
                    }
                }

                Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: root.theme.line }

                SettingLabel {
                    theme: root.theme
                    title: "界面皮肤"
                    meta: "PRISM / DOHNA"
                    description: "选择工作台的视觉皮肤；Dohna 使用固定的明亮配色。"
                    settingKey: "home-skin"
                }
                PrismComboBox {
                    id: skinSelector
                    objectName: "homeSkinSelector"
                    theme: root.theme
                    accessibleName: "界面皮肤"
                    settingDescription: "选择工作台的视觉皮肤；Dohna 使用固定的明亮配色。"
                    settingKey: "home-skin"
                    model: ["Prism", "Dohna"]
                    currentIndex: Math.max(0, root.skinValues.indexOf(root.workbench.skinPreference))
                    Layout.fillWidth: true
                    onActivated: index => {
                        if (index >= 0 && index < root.skinValues.length)
                            root.workbench.setSkin(root.skinValues[index])
                    }
                }

                SettingLabel {
                    theme: root.theme
                    title: "界面主题"
                    meta: "SYSTEM / DARK / LIGHT"
                    description: root.theme.dohna
                                 ? "Dohna 使用固定的明亮配色；切回 Prism 后恢复此处保存的主题偏好。"
                                 : "选择工作台使用的颜色主题。"
                    settingKey: "home-theme"
                }
                PrismComboBox {
                    id: themeSelector
                    objectName: "homeThemeSelector"
                    theme: root.theme
                    accessibleName: "界面主题"
                    settingDescription: "选择工作台使用的颜色主题。"
                    settingKey: "home-theme"
                    model: ["跟随系统", "深色", "浅色"]
                    currentIndex: Math.max(0, root.themeValues.indexOf(
                        root.theme.dohna ? "light" : root.workbench.themePreference
                    ))
                    enabled: !root.theme.dohna
                    Layout.fillWidth: true
                    onActivated: index => {
                        if (index >= 0 && index < root.themeValues.length)
                            root.workbench.setTheme(root.themeValues[index])
                    }
                }
                Text {
                    objectName: "homeDohnaThemeHint"
                    visible: root.theme.dohna
                    text: "Dohna 使用固定的明亮配色"
                    color: root.theme.amber
                    font.family: root.theme.uiFontFor(text)
                    font.pixelSize: 13
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                PrismToggle {
                    theme: root.theme
                    text: "减少界面动效"
                    settingDescription: "减少页面切换和反馈动画。"
                    settingKey: "home-motion"
                    checked: root.workbench.reducedMotion
                    Layout.fillWidth: true
                    onToggled: root.workbench.setReducedMotion(checked)
                }

                PrismToggle {
                    objectName: "homeStartupToggle"
                    theme: root.theme
                    text: "开机自启动"
                    settingDescription: "Windows 登录后静默启动 RefraTranslator，并在系统托盘驻留。"
                    settingKey: "home-startup"
                    checked: root.workbench.startWithWindows
                    Layout.fillWidth: true
                    onToggled: root.workbench.setStartWithWindows(checked)
                }

                SettingLabel {
                    theme: root.theme
                    title: "全局快捷键"
                    meta: "START TRANSLATION"
                    description: "软件运行或驻留托盘时，使用此快捷键启动实时翻译；具体行为由下方选项决定。"
                    settingKey: "home-hotkey"
                    Layout.topMargin: 4
                }
                Item {
                    id: hotkeyField
                    objectName: "homeHotkeyField"
                    Layout.fillWidth: true
                    Layout.preferredHeight: 42
                    focus: root.hotkeyRecording
                    activeFocusOnTab: true
                    Accessible.name: "全局翻译快捷键"
                    Keys.onPressed: event => root.recordHotkey(event)

                    Rectangle {
                        anchors.fill: parent
                        color: root.theme.inputSurface
                        border.color: hotkeyField.activeFocus
                                      ? root.theme.selectionEdge
                                      : root.theme.lineStrong
                        border.width: hotkeyField.activeFocus ? 2 : 1
                        clip: !root.theme.dohna

                        Text {
                            objectName: "homeHotkeyDisplay"
                            anchors.fill: parent
                            anchors.leftMargin: 12
                            anchors.rightMargin: 12
                            text: root.workbench.hotkeyPreference
                            color: root.theme.text
                            font.family: root.theme.uiFontFor(text)
                            font.pixelSize: 15
                            verticalAlignment: Text.AlignVCenter
                            elide: Text.ElideRight
                        }
                    }

                    SettingHint {
                        theme: root.theme
                        target: hotkeyField
                        description: "按住 Ctrl、Alt、Shift 或 Win 中的至少一个，再按另一个键，例如 Ctrl+Alt+T。"
                        settingKey: "home-hotkey"
                    }
                }
                SettingLabel {
                    theme: root.theme
                    title: "快捷键行为"
                    meta: "HOTKEY ACTION"
                    description: "选择翻译已经运行时再次按下全局快捷键的处理方式。"
                    settingKey: "home-hotkey-behavior"
                }
                PrismComboBox {
                    objectName: "homeHotkeyBehaviorSelector"
                    theme: root.theme
                    accessibleName: "快捷键行为"
                    settingDescription: "选择翻译已经运行时再次按下全局快捷键的处理方式。"
                    settingKey: "home-hotkey-behavior"
                    model: root.hotkeyBehaviorLabels
                    currentIndex: Math.max(0, root.hotkeyBehaviorValues.indexOf(
                        root.workbench.hotkeyBehaviorPreference
                    ))
                    Layout.fillWidth: true
                    onActivated: index => {
                        if (index >= 0 && index < root.hotkeyBehaviorValues.length)
                            root.workbench.setHotkeyBehavior(root.hotkeyBehaviorValues[index])
                    }
                }
                Text {
                    objectName: "homeHotkeyRecordingHint"
                    visible: root.hotkeyRecording
                    text: "正在录制：按住 Ctrl、Alt、Shift 或 Win，再按另一个键；Esc 取消"
                    color: root.theme.amber
                    font.family: root.theme.uiFontFor(text)
                    font.pixelSize: 13
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    PrismButton {
                        objectName: "homeHotkeyRecordButton"
                        theme: root.theme
                        primary: root.hotkeyRecording
                        text: root.hotkeyRecording ? "按下组合键…" : "录制快捷键"
                        Layout.fillWidth: true
                        onClicked: {
                            root.hotkeyRecording = true
                            hotkeyField.forceActiveFocus()
                        }
                    }
                    PrismButton {
                        objectName: "homeHotkeyDefaultButton"
                        theme: root.theme
                        text: "恢复默认"
                        Layout.fillWidth: true
                        onClicked: {
                            root.hotkeyRecording = false
                            root.workbench.setHotkey("Ctrl+Alt+T")
                        }
                    }
                }

                Item { Layout.fillHeight: true }

                Text {
                    text: root.workbench.hasProfile
                          ? "配置切换会加载该游戏的真实区域、术语、提示词与缓存统计。"
                          : "先创建配置，之后才能保存区域、术语和人工修订。"
                    color: root.workbench.hasProfile ? root.theme.textDim : root.theme.amber
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
