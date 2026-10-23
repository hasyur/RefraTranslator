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
    readonly property var p3PageOrder: ["HOME", "CAPTURE", "OCR", "TRANSLATION", "OVERLAY", "CACHE", "SETTINGS"]
    readonly property var p3MenuOffsetFractions: [0.022, 0.026, 0.043, 0.028, 0.049, 0.045, 0.074]
    readonly property alias p3NavigationSlots: p3NavigationSlotsRepeater
    readonly property alias p3StartActionSlot: homeStartActionSlot
    readonly property alias p3ApplyActionSlot: homeApplyActionSlot
    readonly property bool hotkeyRecording: appShell.hotkeyRecording
    signal liveToggleRequested()
    signal saveRequested()

    function resumeHotkeyCapture() {
        if (!root.hotkeyRecording || !root.skinPresented
                || root.workbench.currentPage !== "HOME")
            return
        
        refraPreferencesDialog.open()
        Qt.callLater(function() { refraHotkeyField.forceActiveFocus() })
    }

    onSkinPresentedChanged: {
        if (skinPresented && hotkeyRecording)
            Qt.callLater(resumeHotkeyCapture)
    }

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

    Item {
        id: refraDarkHome
        objectName: root.theme.active ? ("refraDarkHome") : ""
        anchors.fill: parent
        visible: true
        enabled: true

        ColumnLayout {
            anchors.fill: parent
            spacing: 0

            Item {
                objectName: root.theme.active ? ("refraDarkHomeStage") : ""
                Layout.fillWidth: true
                Layout.preferredHeight: root.height * 0.648
                Layout.minimumHeight: 390
                clip: true

                Rectangle {
                    objectName: root.theme.active ? ("refraLightHomeBlueStage") : ""
                    visible: root.theme.refraLight
                    x: root.width * (root.width < 1100 ? 0.572 : 0.57)
                    y: -parent.height * 0.12
                    width: root.width * 0.58
                    height: parent.height * 1.24
                    rotation: root.width < 1100 ? 7.5 : 17
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0; color: "#075BFF" }
                        GradientStop { position: 1; color: "#167BFF" }
                    }
                }

                Rectangle {
                    objectName: root.theme.active ? ("refraDarkHomeBlueLight") : ""
                    visible: root.theme.refraDark
                    x: root.width * 0.57
                    y: -parent.height * 0.14
                    width: root.width * 0.55
                    height: parent.height * 1.28
                    rotation: 17
                    opacity: 0.40
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0; color: "#09275a" }
                        GradientStop { position: 0.42; color: "#0c367e" }
                        GradientStop { position: 1; color: "#1649b0" }
                    }
                }
                Rectangle {
                    visible: root.theme.refraDark
                    x: root.width * 0.72
                    y: -parent.height * 0.18
                    width: root.width * 0.15
                    height: parent.height * 1.34
                    rotation: 17
                    color: "#1767ff"
                    opacity: 0.11
                }
                Rectangle {
                    objectName: root.theme.active ? ("refraDarkHeroDownRayOuter") : ""
                    x: root.width * 0.68
                    y: parent.height * 0.62 - height / 2
                    width: root.width * 0.45
                    height: 54
                    rotation: 17
                    transformOrigin: Item.Left
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0; color: Qt.rgba(0, 0.76, 1, 0) }
                        GradientStop { position: 0.045; color: Qt.rgba(0, 0.76, 1, 0.075) }
                        GradientStop { position: 0.24; color: Qt.rgba(0.03, 0.34, 1, 0.045) }
                        GradientStop { position: 0.68; color: Qt.rgba(0.03, 0.12, 0.42, 0) }
                        GradientStop { position: 1; color: Qt.rgba(0.03, 0.12, 0.42, 0) }
                    }
                }
                Rectangle {
                    objectName: root.theme.active ? ("refraDarkHeroDownRayMid") : ""
                    x: root.width * 0.68
                    y: parent.height * 0.62 - height / 2
                    width: root.width * 0.45
                    height: 24
                    rotation: 17
                    transformOrigin: Item.Left
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0; color: Qt.rgba(0, 0.82, 1, 0) }
                        GradientStop { position: 0.045; color: Qt.rgba(0, 0.82, 1, 0.15) }
                        GradientStop { position: 0.24; color: Qt.rgba(0.03, 0.38, 1, 0.085) }
                        GradientStop { position: 0.68; color: Qt.rgba(0.03, 0.14, 0.46, 0) }
                        GradientStop { position: 1; color: Qt.rgba(0.03, 0.14, 0.46, 0) }
                    }
                }
                Rectangle {
                    objectName: root.theme.active ? ("refraDarkHeroDownRayCore") : ""
                    x: root.width * 0.68
                    y: parent.height * 0.62 - height / 2
                    width: root.width * 0.45
                    height: 5
                    rotation: 17
                    transformOrigin: Item.Left
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0; color: Qt.rgba(0, 0.88, 1, 0) }
                        GradientStop { position: 0.045; color: Qt.rgba(0, 0.88, 1, 0.24) }
                        GradientStop { position: 0.24; color: Qt.rgba(0.03, 0.42, 1, 0.13) }
                        GradientStop { position: 0.68; color: Qt.rgba(0.03, 0.15, 0.48, 0) }
                        GradientStop { position: 1; color: Qt.rgba(0.03, 0.15, 0.48, 0) }
                    }
                }

                Text {
                    objectName: root.theme.active ? ("refraDarkHomeBrand") : ""
                    x: root.width * 0.024
                    y: parent.height * 0.032
                    width: root.width * 0.34
                    height: 40
                    text: root.theme.refraLight
                          ? "<font color='#075bff'>Refra</font>Translator"
                          : "<font color='#00d9ff'>Refra</font>Translator"
                    textFormat: Text.RichText
                    color: root.theme.text
                    font.family: "Arial Black"
                    font.pixelSize: 26
                    font.weight: Font.Black
                    font.letterSpacing: -0.7
                    fontSizeMode: Text.HorizontalFit
                    minimumPixelSize: 24
                    verticalAlignment: Text.AlignVCenter
                }

                Item {
                    objectName: root.theme.active ? ("refraDarkNavigationMenu") : ""
                    anchors.fill: parent

                    Repeater {
                        id: p3NavigationSlotsRepeater
                        model: root.p3PageOrder
                        Item {
                            objectName: root.theme.active ? ("refraDarkNavigationSlot" + index) : ""
                            required property int index
                            required property var modelData
                            x: root.width * root.p3MenuOffsetFractions[index]
                            y: parent.height * (0.105 + index * 0.115)
                            width: root.width * 0.51
                            height: Math.max(70, Math.min(92, parent.height * 0.17))
                        }
                    }
                }

                Image {
                    objectName: root.theme.active ? ("refraDarkHeroImage") : ""
                    x: root.width * (root.theme.refraLight && root.width < 1100 ? 0.56 : 0.52)
                    y: parent.height * 0.12
                    width: root.width * (root.theme.refraLight && root.width < 1100 ? 0.44 : 0.48)
                    height: root.height * 0.33
                    source: "../assets/refra-hero-dark.png"
                    fillMode: Image.PreserveAspectFit
                    smooth: true
                }
                ColumnLayout {
                    objectName: root.theme.active ? ("refraDarkHeroProfileMarker") : ""
                    x: root.width * 0.69
                    y: parent.height * 0.66
                    width: root.width * 0.28
                    spacing: 4
                    Text {
                        text: root.workbench.currentProfileName
                        color: root.theme.refraLight ? "#FFFFFF" : root.theme.text
                        font.family: root.theme.uiFontFor(text)
                        font.pixelSize: 19
                        font.weight: Font.DemiBold
                        horizontalAlignment: Text.AlignHCenter
                        Layout.alignment: Qt.AlignHCenter
                        Layout.fillWidth: true
                    }
                    Text {
                        text: root.workbench.running ? "● 正在翻译" : "● 未启动"
                        color: root.workbench.running
                               ? root.theme.refraLight ? "#FFFFFF" : root.theme.accentText
                              : root.theme.refraLight ? "#EAF2FF" : root.theme.textSoft
                        font.family: root.theme.uiFontFor(text)
                        font.pixelSize: 15
                        horizontalAlignment: Text.AlignHCenter
                        Layout.alignment: Qt.AlignHCenter
                        Layout.fillWidth: true
                    }
                }
            }

            Rectangle {
                objectName: root.theme.active ? ("refraDarkHomeRule") : ""
                Layout.fillWidth: true
                Layout.preferredHeight: 1
                color: root.theme.lineStrong
                opacity: 0.76
            }

            RowLayout {
                objectName: root.theme.active ? ("refraDarkHomeStatusBand") : ""
                Layout.fillWidth: true
                Layout.preferredHeight: root.height * 0.21
                Layout.minimumHeight: 126
                Layout.leftMargin: root.width < 1100 ? root.width * 0.065 : root.width * 0.175
                Layout.rightMargin: root.width < 1100 ? root.width * 0.04 : root.width * 0.03
                    Layout.topMargin: root.width < 1100 ? 6 : root.height * 0.018
                spacing: 0

                Item {
                    objectName: root.theme.active ? ("refraDarkProfileSummary") : ""
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumWidth: 210
                    Layout.preferredWidth: 270
                    Layout.rightMargin: 18
                    ColumnLayout {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        spacing: root.width < 1100 ? 3 : 6
                        Text {
                            objectName: root.theme.active ? ("refraDarkProfileHeading") : ""
                            text: "系统状态"
                            color: root.theme.text
                            font.family: root.theme.uiFontFor(text)
                            font.pixelSize: root.width < 1100 ? 16 : 18
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
                                objectName: root.theme.active ? ("refraDarkRunState") : ""
                                text: root.workbench.runState
                                color: root.workbench.runTone === "error" ? root.theme.danger
                                     : root.workbench.runTone === "warning" ? root.theme.amber
                                     : root.workbench.running ? root.theme.accentText : root.theme.text
                                font.family: root.theme.uiFontFor(text)
                                font.pixelSize: root.width < 1100 ? 18 : 20
                                font.weight: Font.DemiBold
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }
                        }
                        PrismComboBox {
                            objectName: root.theme.active ? ("refraDarkProfileSelector") : ""
                            theme: root.theme
                            accessibleName: "当前配置"
                            settingDescription: "选择当前游戏的配置。"
                            settingKey: "home-profile"
                            model: root.workbench.profileNames
                            currentIndex: root.workbench.currentProfileIndex
                            enabled: model.length > 0
                            implicitHeight: root.width < 1100 ? 36 : 42
                            Layout.fillWidth: true
                            onActivated: index => root.workbench.selectProfile(index)
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 5
                            PrismButton {
                                objectName: root.theme.active ? ("refraDarkRefreshProfiles") : ""
                                theme: root.theme
                                text: "刷新"
                                implicitHeight: root.width < 1100 ? 34 : 42
                                Layout.fillWidth: true
                                Layout.minimumWidth: 45
                                onClicked: root.workbench.refreshProfiles()
                            }
                            PrismButton {
                                objectName: root.theme.active ? ("refraDarkCreateProfile") : ""
                                theme: root.theme
                                text: "新建"
                                primary: true
                                implicitHeight: root.width < 1100 ? 34 : 42
                                Layout.fillWidth: true
                                Layout.minimumWidth: 45
                                onClicked: createProfileDialog.open()
                            }
                            PrismButton {
                                objectName: root.theme.active ? ("refraDarkDeleteProfile") : ""
                                theme: root.theme
                                text: "删除"
                                tone: "danger"
                                implicitHeight: root.width < 1100 ? 34 : 42
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
                }

                Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; color: root.theme.lineStrong; opacity: 0.75 }

                Item {
                    objectName: root.theme.active ? ("refraDarkOcrSummary") : ""
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumWidth: root.width < 1100 ? 135 : 170
                    Layout.preferredWidth: root.width < 1100 ? 150 : 220
                    Layout.leftMargin: 22
                    Layout.rightMargin: 18
                    ColumnLayout {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        spacing: 7
                        Text { objectName: "refraDarkOcrHeading"; text: "OCR"; color: root.theme.accentText; font.family: root.theme.uiFontFor(text); font.pixelSize: 18; font.weight: Font.Bold }
                        Text {
                            objectName: root.theme.active ? ("refraDarkOcrStatus") : ""
                            text: root.workbench.ocrStatus
                            color: root.theme.text
                            font.family: root.theme.uiFontFor(text)
                            font.pixelSize: root.width < 1100 ? 18 : 20
                            font.weight: Font.Medium
                            wrapMode: Text.WordWrap
                            maximumLineCount: 2
                            Layout.fillWidth: true
                        }
                        Text {
                            text: root.workbench.detectionQualitySummary
                            color: root.theme.textSoft
                            font.family: root.theme.monoFontFor(text)
                            font.pixelSize: 14
                            wrapMode: Text.WordWrap
                            maximumLineCount: 2
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                    }
                }

                Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; color: root.theme.lineStrong; opacity: 0.75 }

                Item {
                    objectName: root.theme.active ? ("refraDarkTranslationSummary") : ""
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumWidth: root.width < 1100 ? 150 : 175
                    Layout.leftMargin: 22
                    Layout.rightMargin: 18
                    ColumnLayout {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        spacing: 7
                        Text { objectName: "refraDarkTranslationHeading"; text: "翻译引擎"; color: root.theme.text; font.family: root.theme.uiFontFor(text); font.pixelSize: 18; font.weight: Font.Bold }
                        Text {
                            text: root.workbench.backend === "builtin" ? "内置本地模型" : "外部 API"
                            color: root.theme.text
                            font.family: root.theme.uiFontFor(text)
                            font.pixelSize: 20
                            font.weight: Font.Medium
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                        Flickable {
                            objectName: root.theme.active ? ("refraDarkModelScroll") : ""
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
                                objectName: root.theme.active ? ("refraDarkModelName") : ""
                                width: parent.width
                                text: root.workbench.backend === "builtin" ? root.workbench.builtinModel : root.workbench.model
                                color: root.theme.textSoft
                                font.family: root.theme.monoFontFor(text)
                                font.pixelSize: 14
                                wrapMode: Text.WrapAnywhere
                            }
                        }
                    }
                }

                Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; color: root.theme.lineStrong; opacity: 0.75 }

                Item {
                    objectName: root.theme.active ? ("refraDarkLastRunSummary") : ""
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumWidth: root.width < 1100 ? 160 : 190
                    Layout.leftMargin: 22
                    ColumnLayout {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        spacing: 6
                        Text { objectName: "refraDarkLastRunHeading"; text: "上次运行"; color: root.theme.text; font.family: root.theme.uiFontFor(text); font.pixelSize: 18; font.weight: Font.Bold }
                        Text {
                            objectName: root.theme.active ? ("refraDarkLastRunStatus") : ""
                            text: root.workbench.lastRunAvailable ? root.workbench.lastRunStatus
                                  : "尚无上次正常且有效的运行结果"
                            color: root.workbench.lastRunAvailable ? root.theme.textSoft : root.theme.textDim
                            font.family: root.theme.uiFontFor(text)
                            font.pixelSize: 15
                            wrapMode: Text.WordWrap
                            maximumLineCount: 2
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                        Text {
                            text: root.workbench.lastRunAvailable
                                  ? "OCR " + root.workbench.lastRunOcrPeakText + "  ·  LLM " + root.workbench.lastRunLlmPeakText
                                  : "快捷键  " + root.workbench.hotkeyPreference
                            color: root.theme.accentText
                            font.family: root.theme.monoFontFor(text)
                            font.pixelSize: 14
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                        Text {
                            visible: root.workbench.lastRunAvailable
                            text: "快捷键  " + root.workbench.hotkeyPreference
                            color: root.theme.textDim
                            font.family: root.theme.monoFontFor(text)
                            font.pixelSize: 13
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                    }
                }
            }

            Rectangle {
                objectName: root.theme.active ? ("refraDarkHomeActionRule") : ""
                Layout.fillWidth: true
                Layout.preferredHeight: 1
                Layout.leftMargin: root.width < 1100 ? 22 : 42
                Layout.rightMargin: root.width < 1100 ? 20 : 36
                color: root.theme.line
            }

            RowLayout {
                objectName: root.theme.active ? ("refraDarkHomeActions") : ""
                Layout.fillWidth: true
                Layout.preferredHeight: root.height * 0.137
                Layout.minimumHeight: 72
                Layout.leftMargin: root.width < 1100 ? root.width * 0.065 : root.width * 0.175
                Layout.rightMargin: root.width < 1100 ? root.width * 0.04 : root.width * 0.02
                Layout.bottomMargin: 0
                spacing: 8
                PrismButton {
                    objectName: root.theme.active ? ("refraDarkPreferencesButton") : ""
                    theme: root.theme
                    text: "工作台偏好"
                    implicitWidth: 154
                    implicitHeight: 44
                    Layout.preferredWidth: 154
                    Layout.preferredHeight: 44
                    Layout.alignment: Qt.AlignVCenter
                    onClicked: refraPreferencesDialog.open()
                }
                ColumnLayout {
                    objectName: root.theme.active ? ("refraDarkHomeActionFeedback") : ""
                    Layout.fillWidth: true
                    Layout.minimumWidth: 110
                    spacing: 2
                    Text {
                        text: "皮肤 · 主题 · 动效 · 自启动"
                        color: root.theme.textDim
                        font.family: root.theme.uiFontFor(text)
                        font.pixelSize: 13
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                    RowLayout {
                        objectName: root.theme.active ? ("refraDarkHomeFeedbackRow") : ""
                        Layout.fillWidth: true
                        spacing: 5
                        Rectangle {
                            objectName: root.theme.active ? ("refraDarkHomeStatusDot") : ""
                            Layout.preferredWidth: 6
                            Layout.preferredHeight: 6
                            radius: 3
                            color: root.workbench.settingsDirty ? root.theme.amber
                                 : root.workbench.statusTone === "error" ? root.theme.danger
                                 : root.workbench.statusTone === "warning" ? root.theme.amber
                                 : root.workbench.statusTone === "success" ? root.theme.accentText
                                 : root.theme.textDim
                        }
                        Text {
                            objectName: root.theme.active ? ("refraDarkHomeStatusText") : ""
                            visible: !root.workbench.settingsDirty
                            text: root.workbench.statusText
                            color: root.workbench.statusTone === "error" ? root.theme.danger
                                 : root.workbench.statusTone === "warning" ? root.theme.amber
                                 : root.workbench.statusTone === "success" ? root.theme.accentText
                                 : root.theme.textSoft
                            font.family: root.theme.uiFontFor(text)
                            font.pixelSize: 13
                            wrapMode: Text.WordWrap
                            maximumLineCount: 2
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                        Text {
                            objectName: root.theme.active ? ("refraDarkHomeUnsavedStatus") : ""
                            visible: root.workbench.settingsDirty
                            text: "有未应用更改"
                            color: root.theme.amber
                            font.family: root.theme.uiFontFor(text)
                            font.pixelSize: 13
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                    }
                }
                Item {
                    id: homeStartActionSlot
                    objectName: root.theme.active ? ("refraDarkStartActionSlot") : ""
                    implicitWidth: root.width * 0.21
                    implicitHeight: root.height * 0.073
                    Layout.preferredWidth: implicitWidth
                    Layout.preferredHeight: implicitHeight
                    Layout.alignment: Qt.AlignVCenter
                }
                Item {
                    id: homeApplyActionSlot
                    objectName: root.theme.active ? ("refraDarkApplyActionSlot") : ""
                    implicitWidth: root.width * 0.13
                    implicitHeight: root.height * 0.073
                    Layout.preferredWidth: implicitWidth
                    Layout.preferredHeight: implicitHeight
                    Layout.alignment: Qt.AlignVCenter
                }
            }
        }
    }


}
