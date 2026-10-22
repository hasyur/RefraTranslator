import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
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
                Layout.preferredHeight: root.height
                clip: true

                Rectangle {
                    anchors.fill: parent
                    color: "#06132f"
                    z: -5
                }

                Shape {
                    id: homeRefraBand
                    x: parent.width * 0.045
                    y: -parent.height * 0.055
                    width: parent.width * 0.96
                    height: parent.height * 0.34
                    antialiasing: true
                    z: -3
                    ShapePath {
                        fillColor: "#f7f9ff"
                        strokeWidth: 0
                        startX: 0; startY: homeRefraBand.height * 0.18
                        PathLine { x: homeRefraBand.width; y: 0 }
                        PathLine { x: homeRefraBand.width; y: homeRefraBand.height * 0.78 }
                        PathLine { x: 0; y: homeRefraBand.height }
                        PathLine { x: 0; y: homeRefraBand.height * 0.18 }
                    }
                }

                Repeater {
                    z: 0
                    model: [
                        { x: 0.05, y: 0.40, w: 0.10, h: 0.15, c: "#05bde9" },
                        { x: 0.22, y: 0.37, w: 0.07, h: 0.12, c: "#104bf5" },
                        { x: 0.78, y: 0.31, w: 0.08, h: 0.13, c: "#05bde9" },
                        { x: 0.94, y: 0.52, w: 0.06, h: 0.18, c: "#104bf5" },
                        { x: 0.50, y: 0.84, w: 0.10, h: 0.15, c: "#05bde9" },
                        { x: 0.88, y: 0.80, w: 0.08, h: 0.14, c: "#104bf5" }
                    ]
                    Shape {
                        id: homeShard
                        required property var modelData
                        x: hero.width * modelData.x
                        y: hero.height * modelData.y
                        width: hero.width * modelData.w
                        height: hero.height * modelData.h
                        antialiasing: true
                        ShapePath {
                            fillColor: modelData.c
                            strokeWidth: 0
                            startX: 0; startY: 0
                            PathLine { x: homeShard.width; y: homeShard.height * 0.20 }
                            PathLine { x: homeShard.width * 0.46; y: homeShard.height }
                            PathLine { x: 0; y: 0 }
                        }
                    }
                }

                Text {
                    objectName: "azureHomeWordmark"
                    x: parent.width * 0.10
                    y: -parent.height * 0.07
                    width: parent.width * 0.90
                    height: parent.height * 0.34
                    text: "REFRA"
                    color: "#104bf5"
                    font.family: root.theme.displayFontFor(text)
                    font.pixelSize: Math.max(116, Math.min(210, parent.width * 0.22))
                    font.weight: Font.Black
                    font.italic: true
                    font.letterSpacing: -11
                    rotation: -8
                    z: 1
                }

                Image {
                    objectName: "azureHomeHeroine"
                    source: Qt.resolvedUrl("../assets/heroine-home.png")
                    sourceSize.width: 1430
                    sourceSize.height: 1100
                    fillMode: Image.PreserveAspectFit
                    horizontalAlignment: Image.AlignRight
                    verticalAlignment: Image.AlignVCenter
                    x: parent.width * 0.035
                    y: parent.height * 0.015
                    width: parent.width * 0.99
                    height: parent.height * 0.96
                    z: 2
                    asynchronous: true
                    visible: status === Image.Ready
                    smooth: true
                }

                Item {
                    objectName: "azureHomeRunStatePlate"
                    x: 18
                    y: parent.height * 0.76
                    width: parent.width * 0.34
                    height: parent.height * 0.15
                    z: 4
                    Shape {
                        id: homeStatusShape
                        anchors.fill: parent
                        antialiasing: true
                        ShapePath {
                            fillColor: "#071535"
                            strokeWidth: 0
                            startX: 0; startY: 0
                            PathLine { x: homeStatusShape.width - 22; y: 0 }
                            PathLine { x: homeStatusShape.width; y: homeStatusShape.height }
                            PathLine { x: 12; y: homeStatusShape.height }
                            PathLine { x: 0; y: homeStatusShape.height - 12 }
                            PathLine { x: 0; y: 0 }
                        }
                    }
                    Rectangle {
                        x: 0; y: 0
                        width: 4; height: parent.height
                        color: "#05bde9"
                    }
                    Column {
                        anchors.fill: parent
                        anchors.leftMargin: 15
                        anchors.rightMargin: 12
                        anchors.topMargin: 13
                        spacing: 4
                        Text {
                            text: "RUN STATE"
                            color: "#05bde9"
                            font.family: root.theme.monoFontFor(text)
                            font.pixelSize: 10
                            font.letterSpacing: 0.8
                        }
                        Text {
                            objectName: "azureHomeRunState"
                            text: root.workbench.runState
                            color: root.workbench.runTone === "error" ? "#ff6b82"
                                 : root.workbench.runTone === "warning" ? "#ffd16d"
                                 : root.workbench.running ? "#05bde9" : "#f4f7ff"
                            font.family: root.theme.displayFontFor(text)
                            font.pixelSize: root.height < 760 ? 21 : 25
                            font.weight: Font.Black
                            font.italic: true
                            elide: Text.ElideRight
                            width: parent.width - 24
                        }
                        Text {
                            objectName: "azureHomeStatusMessage"
                            text: root.workbench.statusText
                            color: "#a7b9e4"
                            font.family: root.theme.uiFontFor(text)
                            font.pixelSize: 10
                            elide: Text.ElideRight
                            width: parent.width - 24
                        }
                    }
                }

                Item {
                    objectName: "azureHomeCommandPanel"
                    x: parent.width * 0.64
                    y: parent.height * 0.68
                    width: parent.width * 0.34
                    height: parent.height * 0.28
                    z: 5
                    Shape {
                        id: homeCommandOffset
                        x: 5; y: 6
                        width: parent.width
                        height: parent.height
                        antialiasing: true
                        ShapePath {
                            fillColor: "#05bde9"
                            strokeWidth: 0
                            startX: 0; startY: 0
                            PathLine { x: homeCommandOffset.width - 24; y: 0 }
                            PathLine { x: homeCommandOffset.width; y: 20 }
                            PathLine { x: homeCommandOffset.width - 18; y: homeCommandOffset.height }
                            PathLine { x: 0; y: homeCommandOffset.height - 14 }
                            PathLine { x: 0; y: 0 }
                        }
                    }
                    Shape {
                        id: homeCommandPaper
                        anchors.fill: parent
                        antialiasing: true
                        ShapePath {
                            fillColor: "#f7f9ff"
                            strokeWidth: 0
                            startX: 0; startY: 0
                            PathLine { x: homeCommandPaper.width - 24; y: 0 }
                            PathLine { x: homeCommandPaper.width; y: 20 }
                            PathLine { x: homeCommandPaper.width - 18; y: homeCommandPaper.height }
                            PathLine { x: 0; y: homeCommandPaper.height - 14 }
                            PathLine { x: 0; y: 0 }
                        }
                    }
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 15
                        anchors.rightMargin: 18
                        anchors.topMargin: 12
                        anchors.bottomMargin: 10
                        spacing: 4
                        Text {
                            text: "CURRENT PROFILE"
                            color: "#164fc9"
                            font.family: root.theme.monoFontFor(text)
                            font.pixelSize: 9
                            font.letterSpacing: 0.7
                        }
                        Text {
                            objectName: "azureHomeCurrentProfile"
                            text: root.workbench.currentProfileName
                            color: "#071b50"
                            font.family: root.theme.displayFontFor(text)
                            font.pixelSize: root.height < 760 ? 18 : 21
                            font.weight: Font.Black
                            font.italic: true
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 6
                            AzureButton {
                                objectName: "azureManageProfilesButton"
                                theme: root.theme
                                quiet: true
                                text: "配置管理 ↓"
                                font.pixelSize: 13
                                font.weight: Font.Bold
                                Layout.fillWidth: true
                                Layout.minimumWidth: 90
                                onClicked: homeScroll.contentY = Math.min(
                                               homeScroll.contentHeight - homeScroll.height,
                                               hero.height + 110)
                            }
                            AzureButton {
                                objectName: "azureHomeStartButton"
                                theme: root.theme
                                primary: true
                                text: root.startPending ? "准备中…" : root.workbench.startButtonText
                                font.pixelSize: 14
                                font.weight: Font.Black
                                font.italic: true
                                enabled: root.workbench.runPhase !== "stopping"
                                         && !root.startPending
                                         && (root.workbench.canStart || root.workbench.running)
                                Layout.fillWidth: true
                                Layout.minimumWidth: 96
                                implicitHeight: 42
                                onClicked: root.requestLiveToggle()
                            }
                        }
                    }
                }

                Text {
                    x: parent.width * 0.045
                    y: parent.height * 0.14
                    text: "BLUE / CUT / MOTION"
                    color: "#05bde9"
                    font.family: root.theme.monoFontFor(text)
                    font.pixelSize: 9
                    font.letterSpacing: 1
                    rotation: -8
                    z: 3
                }
                Shape {
                    x: parent.width * 0.05
                    y: parent.height * 0.28
                    width: 28
                    height: 32
                    antialiasing: true
                    z: 3
                    ShapePath {
                        fillColor: "#ff3153"
                        strokeWidth: 0
                        startX: 0; startY: 0
                        PathLine { x: 28; y: 10 }
                        PathLine { x: 13; y: 32 }
                        PathLine { x: 0; y: 0 }
                    }
                }
            }

            Item {
                objectName: "azureHomeSignalPanel"
                Layout.fillWidth: true
                Layout.preferredHeight: 126
                Shape {
                    id: homeSignalPaper
                    anchors.fill: parent
                    antialiasing: true
                    ShapePath {
                        fillColor: root.theme.panel
                        strokeWidth: 0
                        startX: 0; startY: 12
                        PathLine { x: 22; y: 0 }
                        PathLine { x: homeSignalPaper.width - 18; y: 0 }
                        PathLine { x: homeSignalPaper.width; y: 18 }
                        PathLine { x: homeSignalPaper.width; y: homeSignalPaper.height - 10 }
                        PathLine { x: homeSignalPaper.width - 12; y: homeSignalPaper.height }
                        PathLine { x: 0; y: homeSignalPaper.height }
                        PathLine { x: 0; y: 12 }
                    }
                }
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
                Layout.preferredHeight: root.width < 1000
                                        ? homeControlGrid.implicitHeight + 8 : 458
                Shape {
                    id: homeControlPaper
                    anchors.fill: parent
                    antialiasing: true
                    ShapePath {
                        fillColor: root.theme.panel
                        strokeWidth: 0
                        startX: 0; startY: 18
                        PathLine { x: 28; y: 0 }
                        PathLine { x: homeControlPaper.width * 0.22; y: 0 }
                        PathLine { x: homeControlPaper.width * 0.30; y: 16 }
                        PathLine { x: homeControlPaper.width * 0.42; y: 0 }
                        PathLine { x: homeControlPaper.width - 26; y: 0 }
                        PathLine { x: homeControlPaper.width; y: 24 }
                        PathLine { x: homeControlPaper.width - 14; y: homeControlPaper.height }
                        PathLine { x: 0; y: homeControlPaper.height }
                        PathLine { x: 0; y: 18 }
                    }
                }
                GridLayout {
                    id: homeControlGrid
                    anchors.fill: parent
                    columns: root.width < 1000 ? 2 : 3
                    rowSpacing: 14
                    columnSpacing: 18

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
                        Layout.topMargin: root.width < 1000 ? 0 : 24
                        Layout.leftMargin: root.width < 1000 ? 0 : 12
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
                            objectName: "azureHomeReduceMotionToggle"
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
                        Layout.topMargin: root.width < 1000 ? 0 : 48
                        Layout.leftMargin: root.width < 1000 ? 0 : 20
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
