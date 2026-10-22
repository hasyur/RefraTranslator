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
    readonly property var p3MenuOffsetFractions: [0.022, 0.026, 0.043, 0.028, 0.049, 0.045, 0.074]
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
        visible: root.theme.refraStyle
        enabled: root.theme.refraStyle

        ColumnLayout {
            anchors.fill: parent
            spacing: 0

            Item {
                objectName: "refraDarkHomeStage"
                Layout.fillWidth: true
                Layout.preferredHeight: root.height * 0.648
                Layout.minimumHeight: 390
                clip: true

                Rectangle {
                    objectName: "refraLightHomeBlueStage"
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
                    objectName: "refraDarkHomeBlueLight"
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
                    objectName: "refraDarkHeroDownRayOuter"
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
                    objectName: "refraDarkHeroDownRayMid"
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
                    objectName: "refraDarkHeroDownRayCore"
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
                    objectName: "refraDarkHomeBrand"
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
                    objectName: "refraDarkNavigationMenu"
                    anchors.fill: parent

                    Repeater {
                        model: root.p3PageOrder
                        PrismButton {
                            objectName: "refraDarkNavigationButton" + index
                            required property int index
                            required property var modelData
                            theme: root.theme
                            navigation: true
                            navigationHero: true
                            navigationSlashVisible: [0, 1, 3, 5].indexOf(index) >= 0
                            navigationNumber: String(index + 1).padStart(2, "0")
                            navigationSubtitle: root.p3MenuSubtitle(String(modelData))
                            navigationCool: index % 2 === 1
                            navigationTilt: index % 2 === 0 ? -3.8 : -5.7
                            navigationHeroFontSize: Math.max(
                                58,
                                Math.min(70, (root.width * 0.55 - 122) / 8.2)
                            )
                            text: root.p3MenuTitle(String(modelData))
                            primary: root.workbench.currentPage === modelData
                            quiet: !primary
                            x: root.width * root.p3MenuOffsetFractions[index]
                            y: parent.height * (0.105 + index * 0.115)
                            width: root.width * 0.51
                            height: Math.max(70, Math.min(92, parent.height * 0.17))
                            z: primary ? 2 : 1
                            onClicked: root.workbench.setPage(String(modelData))
                        }
                    }
                }

                Image {
                    objectName: "refraDarkHeroImage"
                    x: root.width * (root.theme.refraLight && root.width < 1100 ? 0.56 : 0.52)
                    y: parent.height * 0.12
                    width: root.width * (root.theme.refraLight && root.width < 1100 ? 0.44 : 0.48)
                    height: root.height * 0.33
                    source: "../assets/refra-hero-dark.png"
                    fillMode: Image.PreserveAspectFit
                    smooth: true
                }
                ColumnLayout {
                    objectName: "refraDarkHeroProfileMarker"
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
                objectName: "refraDarkHomeRule"
                Layout.fillWidth: true
                Layout.preferredHeight: 1
                color: root.theme.lineStrong
                opacity: 0.76
            }

            RowLayout {
                objectName: "refraDarkHomeStatusBand"
                Layout.fillWidth: true
                Layout.preferredHeight: root.height * 0.21
                Layout.minimumHeight: 126
                Layout.leftMargin: root.width < 1100 ? root.width * 0.065 : root.width * 0.175
                Layout.rightMargin: root.width < 1100 ? root.width * 0.04 : root.width * 0.03
                    Layout.topMargin: root.width < 1100 ? 6 : root.height * 0.018
                spacing: 0

                Item {
                    objectName: "refraDarkProfileSummary"
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
                            objectName: "refraDarkProfileHeading"
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
                                objectName: "refraDarkRunState"
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
                            objectName: "refraDarkProfileSelector"
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
                                objectName: "refraDarkRefreshProfiles"
                                theme: root.theme
                                text: "刷新"
                                implicitHeight: root.width < 1100 ? 34 : 42
                                Layout.fillWidth: true
                                Layout.minimumWidth: 45
                                onClicked: root.workbench.refreshProfiles()
                            }
                            PrismButton {
                                objectName: "refraDarkCreateProfile"
                                theme: root.theme
                                text: "新建"
                                primary: true
                                implicitHeight: root.width < 1100 ? 34 : 42
                                Layout.fillWidth: true
                                Layout.minimumWidth: 45
                                onClicked: createProfileDialog.open()
                            }
                            PrismButton {
                                objectName: "refraDarkDeleteProfile"
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
                    objectName: "refraDarkOcrSummary"
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
                            objectName: "refraDarkOcrStatus"
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
                    objectName: "refraDarkTranslationSummary"
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
                                font.pixelSize: 14
                                wrapMode: Text.WrapAnywhere
                            }
                        }
                    }
                }

                Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; color: root.theme.lineStrong; opacity: 0.75 }

                Item {
                    objectName: "refraDarkLastRunSummary"
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
                            objectName: "refraDarkLastRunStatus"
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
                objectName: "refraDarkHomeActionRule"
                Layout.fillWidth: true
                Layout.preferredHeight: 1
                Layout.leftMargin: root.width < 1100 ? 22 : 42
                Layout.rightMargin: root.width < 1100 ? 20 : 36
                color: root.theme.line
            }

            RowLayout {
                objectName: "refraDarkHomeActions"
                Layout.fillWidth: true
                Layout.preferredHeight: root.height * 0.137
                Layout.minimumHeight: 72
                Layout.leftMargin: root.width < 1100 ? root.width * 0.065 : root.width * 0.175
                Layout.rightMargin: root.width < 1100 ? root.width * 0.04 : root.width * 0.02
                Layout.bottomMargin: 0
                spacing: 8
                PrismButton {
                    objectName: "refraDarkPreferencesButton"
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
                    objectName: "refraDarkHomeActionFeedback"
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
                                 : root.workbench.statusTone === "success" ? root.theme.accentText
                                 : root.theme.textDim
                        }
                        Text {
                            objectName: "refraDarkHomeStatusText"
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
                            objectName: "refraDarkHomeUnsavedStatus"
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
                PrismButton {
                    objectName: "refraDarkStartButton"
                    theme: root.theme
                    p3Action: true
                    primary: true
                    text: root.startPreludePending ? "正在启动…" : root.workbench.startButtonText
                    implicitWidth: root.width * 0.21
                    implicitHeight: root.height * 0.073
                    Layout.preferredWidth: root.width * 0.21
                    Layout.preferredHeight: root.height * 0.073
                    Layout.alignment: Qt.AlignVCenter
                    enabled: root.workbench.runPhase !== "stopping"
                             && !root.startPreludePending
                             && (root.workbench.canStart || root.workbench.running)
                    onClicked: root.liveToggleRequested()
                }
                PrismButton {
                    objectName: "refraDarkApplyButton"
                    theme: root.theme
                    p3Action: true
                    text: "应用更改"
                    implicitWidth: root.width * 0.13
                    implicitHeight: root.height * 0.073
                    Layout.preferredWidth: root.width * 0.13
                    Layout.preferredHeight: root.height * 0.073
                    Layout.alignment: Qt.AlignVCenter
                    enabled: root.workbench.hasProfile
                    onClicked: root.saveRequested()
                }
            }
        }
    }

    RowLayout {
        anchors.fill: parent
        visible: !root.theme.refraStyle
        enabled: !root.theme.refraStyle
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
                            color: root.theme.accentText
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
                                        color: root.theme.accentText
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
                                        color: root.theme.spectrumText
                                        opacity: 0.6
                                    }
                                    Text {
                                        objectName: "homeLlmPeakValue"
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
