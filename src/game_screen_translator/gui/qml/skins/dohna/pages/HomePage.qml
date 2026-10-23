import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

Item {
    id: root

    required property var theme
    required property var workbench
    required property var appShell
    property bool skinPresented: false
    property int transitionSerial: 0
    property bool pageMotionEnabled: false
    property bool startPreludePending: false
    readonly property bool compactOverview: height < 580
    readonly property var themeValues: ["system", "dark", "light"]
    readonly property var skinValues: ["prism", "dohna"]
    readonly property var hotkeyBehaviorValues: ["start_only", "toggle", "toggle_show"]
    readonly property var hotkeyBehaviorLabels: ["仅启动", "启动 / 停止翻译", "启动 / 停止并打开 GUI"]
    readonly property bool hotkeyRecording: appShell.hotkeyRecording
    signal liveToggleRequested()
    signal saveRequested()

    function resumeHotkeyCapture() {
        if (!root.hotkeyRecording || !root.skinPresented
                || root.workbench.currentPage !== "HOME")
            return
        homeHotkeyField.forceActiveFocus()
    }

    onSkinPresentedChanged: {
        if (skinPresented && hotkeyRecording)
            Qt.callLater(resumeHotkeyCapture)
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
            root.appShell.setHotkeyRecording(false)
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
        root.appShell.setHotkeyRecording(false)
        root.workbench.setHotkey(modifiers.join("+") + "+" + keyName)
    }

    PrismDialog {
        id: createProfileDialog
        objectName: root.theme.active ? ("createProfileDialog") : ""
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
            objectName: root.theme.active ? ("createProfileNameField") : ""
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
        objectName: root.theme.active ? ("deleteProfileDialog") : ""
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
        objectName: root.theme.active ? ("refraPreferencesDialog") : ""
        surfaceName: "refraPreferencesDialog"
        theme: root.theme
        parent: Overlay.overlay
        anchors.centerIn: parent
        title: "工作台偏好"
        acceptText: "完成"
        showRejectButton: false
        width: Math.min(650, root.width - 54)

        ScrollView {
            objectName: root.theme.active ? ("refraPreferencesScroll") : ""
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
                    objectName: root.theme.active ? ("refraHomeSkinSelector") : ""
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
                    objectName: root.theme.active ? ("refraHomeThemeSelector") : ""
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
                    objectName: root.theme.active ? ("refraHomeReducedMotionToggle") : ""
                    theme: root.theme
                    text: "减少界面动效"
                    settingDescription: "减少页面切换和反馈动画。"
                    settingKey: "home-motion"
                    checked: root.workbench.reducedMotion
                    Layout.fillWidth: true
                    onToggled: root.workbench.setReducedMotion(checked)
                }
                PrismToggle {
                    objectName: root.theme.active ? ("refraHomeStartupToggle") : ""
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
                    objectName: root.theme.active ? ("refraHotkeyField") : ""
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
                            objectName: root.theme.active ? ("refraHotkeyDisplay") : ""
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
                    objectName: root.theme.active ? ("refraHotkeyBehaviorSelector") : ""
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
                    objectName: root.theme.active ? ("refraHotkeyRecordingHint") : ""
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
                        objectName: root.theme.active ? ("refraHotkeyRecordButton") : ""
                        theme: root.theme
                        primary: root.hotkeyRecording
                        text: root.hotkeyRecording ? "按下组合键…" : "录制快捷键"
                        Layout.fillWidth: true
                        onClicked: {
                            root.appShell.setHotkeyRecording(true)
                            refraHotkeyField.forceActiveFocus()
                        }
                    }
                    PrismButton {
                        objectName: root.theme.active ? ("refraHotkeyDefaultButton") : ""
                        theme: root.theme
                        text: "恢复默认"
                        Layout.fillWidth: true
                        onClicked: {
                            root.appShell.setHotkeyRecording(false)
                            root.workbench.setHotkey("Ctrl+Alt+T")
                        }
                    }
                }
            }
        }
        onOpened: {
            if (root.hotkeyRecording)
                Qt.callLater(function() { refraHotkeyField.forceActiveFocus() })
        }
        onClosed: root.appShell.setHotkeyRecording(false)
    }



    RowLayout {
        anchors.fill: parent
        visible: !false
        enabled: !false
        spacing: 16

        PrismPanel {
            objectName: root.theme.active ? ("homePrimaryPanel") : ""
            theme: root.theme
            padding: root.compactOverview ? 16 : 22
            motionRole: "primary"
            transitionSerial: root.transitionSerial
            motionEnabled: root.pageMotionEnabled && root.visible
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumWidth: 390

            Flickable {
                objectName: root.theme.active ? ("homePrimaryScroll") : ""
                anchors.fill: parent
                contentWidth: width
                contentHeight: homePrimaryContent.implicitHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: PrismScrollBar { id: homePrimaryBar; theme: root.theme }

                ColumnLayout {
                    id: homePrimaryContent
                    objectName: root.theme.active ? ("homePrimaryContent") : ""
                    width: parent.width - homePrimaryBar.contentInset
                    height: implicitHeight
                    spacing: root.compactOverview ? 4 : 14

                SectionHeader {
                    theme: root.theme
                    title: "光学信号场" 
                    meta: "LIVE CONTROL" 
                    Layout.fillWidth: true
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: root.compactOverview ? 4 : 7
                    Text {
                        objectName: root.theme.active ? ("homeRunHero") : ""
                        text: root.workbench.runState
                        color: root.workbench.runTone === "error" ? root.theme.danger
                             : root.workbench.runTone === "warning" ? root.theme.amber
                             : root.workbench.running ? root.theme.accent : root.theme.text
                        font.family: root.theme.displayFontFor(text)
                        font.pixelSize: root.compactOverview ? 40 : 54
                        font.weight: Font.Bold
                    }
                    Text {
                        objectName: root.theme.active ? ("homeProfileName") : ""
                        text: root.workbench.currentProfileName
                        color: root.theme.textSoft
                        font.family: root.theme.uiFontFor(text)
                        font.pixelSize: root.compactOverview ? 18 : 20
                        font.weight: Font.Medium
                    }
                }

                RowLayout {
                    objectName: root.theme.active ? ("homeSignalCards") : ""
                    Layout.fillWidth: true
                    Layout.preferredHeight: root.compactOverview ? 100 : 132
                    Layout.minimumHeight: Layout.preferredHeight
                    spacing: 12

                    Item {
                        objectName: root.theme.active ? ("homeOcrSignalGroup") : ""
                        Layout.fillWidth: true
                        Layout.fillHeight: true

                        Rectangle {
                            objectName: root.theme.active ? ("homeOcrSignalAccent") : ""
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
                                objectName: root.theme.active ? ("homeOcrSignalLabel") : ""
                                text: "OCR"
                                color: root.theme.accentText
                                font.family: root.theme.monoFontFor(text)
                                font.pixelSize: 13
                                font.letterSpacing: 1.4
                            }
                            Text {
                                objectName: root.theme.active ? ("homeOcrSignalValue") : ""
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
                        objectName: root.theme.active ? ("homeTranslationSignalGroup") : ""
                        Layout.fillWidth: true
                        Layout.fillHeight: true

                        Rectangle {
                            objectName: root.theme.active ? ("homeTranslationSignalSpectrum") : ""
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
                                objectName: root.theme.active ? ("homeTranslationSignalLabel") : ""
                                text: "TRANSLATION"
                                color: root.theme.spectrumText
                                font.family: root.theme.monoFontFor(text)
                                font.pixelSize: 13
                                font.letterSpacing: 1.4
                            }
                            Text {
                                objectName: root.theme.active ? ("homeTranslationSignalValue") : ""
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
                    objectName: root.theme.active ? ("homeLastRunUnavailable") : ""
                    theme: root.theme
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    visible: !root.workbench.lastRunAvailable
                    eyebrow: "LAST RUN METRICS · UNAVAILABLE"
                    title: "尚无上次运行结果"
                    detail: root.workbench.lastRunStatus
                }

                Rectangle {
                    objectName: root.theme.active ? ("homeLastRunMetrics") : ""
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
                        objectName: root.theme.active ? ("homeLastRunMetricsContent") : ""
                        anchors.fill: parent
                        anchors.margins: 16
                        spacing: root.compactOverview ? 8 : 12
                        Text {
                            objectName: root.theme.active ? ("homeLastRunStatus") : ""
                            text: root.workbench.lastRunStatus
                            color: root.theme.accentText
                            font.family: root.theme.monoFontFor(text)
                            font.pixelSize: 13
                            font.letterSpacing: 1.1
                            Layout.fillWidth: true
                        }
                        RowLayout {
                            objectName: root.theme.active ? ("homePeakCards") : ""
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            spacing: 12

                            Item {
                                objectName: root.theme.active ? ("homeOcrPeakGroup") : ""
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
                                        objectName: root.theme.active ? ("homeOcrPeakValue") : ""
                                        text: root.workbench.lastRunOcrPeakText
                                        color: root.theme.accentText
                                        font.family: root.theme.displayFontFor(text)
                                        font.pixelSize: 44
                                        font.weight: Font.Bold
                                    }
                                    Item { Layout.fillHeight: true }
                                }
                            }

                            Item {
                                objectName: root.theme.active ? ("homeLlmPeakGroup") : ""
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
                                        color: root.theme.spectrumText
                                        opacity: 0.6
                                    }
                                    Text {
                                        objectName: root.theme.active ? ("homeLlmPeakValue") : ""
                                        text: root.workbench.lastRunLlmPeakText
                                        color: root.theme.spectrumText
                                        font.family: root.theme.displayFontFor(text)
                                        font.pixelSize: 44
                                        font.weight: Font.Bold
                                    }
                                    Item { Layout.fillHeight: true }
                                }
                            }
                        }
                        Text {
                            objectName: root.theme.active ? ("homeLastRunFootnote") : ""
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
            objectName: root.theme.active ? ("homeSecondaryPanel") : ""
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
                objectName: root.theme.active ? ("homeSecondaryScroll") : ""
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
                    objectName: root.theme.active ? ("homeProfileSelector") : ""
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
                        objectName: root.theme.active ? ("openCreateProfileDialogButton") : ""
                        theme: root.theme
                        primary: true
                        text: "新建"
                        Layout.fillWidth: true
                        onClicked: createProfileDialog.open()
                    }
                    PrismButton {
                        objectName: root.theme.active ? ("openDeleteProfileDialogButton") : ""
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
                    objectName: root.theme.active ? ("homeSkinSelector") : ""
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
                    description: "Dohna 使用固定的明亮配色；切回 Prism 后恢复此处保存的主题偏好。"
                                 
                    settingKey: "home-theme"
                }
                PrismComboBox {
                    id: themeSelector
                    objectName: root.theme.active ? ("homeThemeSelector") : ""
                    theme: root.theme
                    accessibleName: "界面主题"
                    settingDescription: "选择工作台使用的颜色主题。"
                    settingKey: "home-theme"
                    model: ["跟随系统", "深色", "浅色"]
                    currentIndex: Math.max(0, root.themeValues.indexOf( "light" ))
                    enabled: !true
                    Layout.fillWidth: true
                    onActivated: index => {
                        if (index >= 0 && index < root.themeValues.length)
                            root.workbench.setTheme(root.themeValues[index])
                    }
                }
                Text {
                    objectName: root.theme.active ? ("homeDohnaThemeHint") : ""
                    visible: true
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
                    objectName: root.theme.active ? ("homeStartupToggle") : ""
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
                    objectName: root.theme.active ? ("homeHotkeyField") : ""
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
                        clip: !true

                        Text {
                            objectName: root.theme.active ? ("homeHotkeyDisplay") : ""
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
                    objectName: root.theme.active ? ("homeHotkeyBehaviorSelector") : ""
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
                    objectName: root.theme.active ? ("homeHotkeyRecordingHint") : ""
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
                        objectName: root.theme.active ? ("homeHotkeyRecordButton") : ""
                        theme: root.theme
                        primary: root.hotkeyRecording
                        text: root.hotkeyRecording ? "按下组合键…" : "录制快捷键"
                        Layout.fillWidth: true
                        onClicked: {
                            root.appShell.setHotkeyRecording(true)
                            hotkeyField.forceActiveFocus()
                        }
                    }
                    PrismButton {
                        objectName: root.theme.active ? ("homeHotkeyDefaultButton") : ""
                        theme: root.theme
                        text: "恢复默认"
                        Layout.fillWidth: true
                        onClicked: {
                            root.appShell.setHotkeyRecording(false)
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
