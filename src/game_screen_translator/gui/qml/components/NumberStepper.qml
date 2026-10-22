import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

GridLayout {
    id: root

    required property var theme
    property int value: 0
    property int minimum: 0
    property int maximum: 100
    property int stepSize: 1
    property string suffix: ""
    property string accessibleName: ""
    property string settingDescription: ""
    property string settingKey: ""
    property string rowTitle: ""
    property string rowMeta: ""
    property bool compact: false
    readonly property bool detailed: theme.refraDark && rowTitle.length > 0
    readonly property bool stackedDetails: detailed && width < 400
    readonly property real compactWidth: compact ? 144 : suffix.length > 0 ? 200 : 176
    readonly property real suffixSpacing: 5
    signal edited(int value)

    columns: detailed && !stackedDetails ? 2 : 1
    columnSpacing: detailed && !stackedDetails ? 12 : 0
    rowSpacing: stackedDetails ? 6 : 0
    implicitWidth: detailed ? 360 : compactWidth
    implicitHeight: detailed
                    ? (stackedDetails
                       ? rowInformation.implicitHeight + controlsRow.implicitHeight + rowSpacing
                       : Math.max(64, rowInformation.implicitHeight, controlsRow.implicitHeight))
                    : 42
    Layout.fillWidth: detailed
    Layout.minimumWidth: detailed ? 260 : compactWidth
    Layout.preferredWidth: detailed ? -1 : compactWidth
    Layout.maximumWidth: detailed ? Number.POSITIVE_INFINITY : compactWidth

    function submit(candidate) {
        const numeric = Math.max(minimum, Math.min(maximum, Number(candidate)))
        edited(Math.round(numeric))
    }

    ColumnLayout {
        id: rowInformation
        objectName: "numberStepperRowInformation"
        visible: root.detailed
        Layout.fillWidth: true
        Layout.minimumWidth: root.stackedDetails ? 0 : 120
        Layout.row: 0
        Layout.column: 0
        spacing: 2
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            Text {
                objectName: "numberStepperRowTitle"
                text: root.rowTitle
                color: root.theme.text
                font.family: root.theme.uiFontFor(text)
                font.pixelSize: 15
                font.weight: Font.DemiBold
                elide: Text.ElideNone
                wrapMode: Text.NoWrap
                Layout.fillWidth: true
                Layout.minimumWidth: 0
            }
            Text {
                objectName: "numberStepperRowMeta"
                visible: root.rowMeta.length > 0
                text: root.rowMeta
                color: root.theme.accent
                font.family: root.theme.monoFontFor(text)
                font.pixelSize: 10
                font.letterSpacing: 0.6
                elide: Text.ElideNone
                wrapMode: Text.NoWrap
                Layout.minimumWidth: 0
            }
        }
        Text {
            text: root.settingDescription
            color: root.theme.textSoft
            font.family: root.theme.uiFontFor(text)
            font.pixelSize: 12
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
    }

    RowLayout {
        id: controlsRow
        objectName: "numberStepperControlsRow"
        Layout.row: root.stackedDetails ? 1 : 0
        Layout.column: root.detailed && !root.stackedDetails ? 1 : 0
        Layout.fillWidth: root.stackedDetails
        Layout.alignment: root.stackedDetails ? Qt.AlignHCenter : Qt.AlignRight
        spacing: root.detailed ? 8 : 0

    PrismButton {
        id: decreaseButton
        objectName: "numberStepperDecrease"
        theme: root.theme
        text: "−"
        implicitWidth: root.theme.refraDark && root.rowTitle.length > 0 ? 30 : root.compact ? 32 : 42
        Layout.preferredWidth: implicitWidth
        enabled: root.enabled && root.value > root.minimum
        dohnaEmbedded: root.theme.dohna
        dohnaGroupFrame: root.theme.dohna
        dohnaGroupVisible: root.theme.dohna
        dohnaGroupEnabled: root.enabled
        dohnaGroupWidth: root.width
        dohnaGroupHeight: root.height
        dohnaGroupHovered: decreaseButton.hovered
                                || increaseButton.hovered
                                || decreaseButton.activeFocus
                                || increaseButton.activeFocus
                                || editor.activeFocus
        dohnaGroupPressed: decreaseButton.down || increaseButton.down
        dohnaGroupDivider1X: decreaseButton.width
        dohnaGroupDivider2X: root.width - increaseButton.width
        onClicked: root.submit(root.value - root.stepSize)
    }

    TextField {
        id: editor
        objectName: "numberStepperEditor"
        Layout.fillWidth: !(root.theme.refraDark && root.rowTitle.length > 0)
        Layout.minimumWidth: root.theme.refraDark && root.rowTitle.length > 0
                             ? 148 : root.compact ? 80 : root.suffix.length > 0 ? 116 : 92
        Layout.preferredWidth: root.theme.refraDark && root.rowTitle.length > 0 ? 148 : -1
        Layout.maximumWidth: root.theme.refraDark && root.rowTitle.length > 0
                             ? 148 : Number.POSITIVE_INFINITY
        implicitHeight: 42
        text: String(root.value)
        color: root.theme.text
        clip: true
        leftPadding: root.compact ? 6 : 8
        rightPadding: suffixLabel.visible
                      ? 8 + suffixLabel.implicitWidth + root.suffixSpacing
                      : leftPadding
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        font.family: root.theme.monoFontFor(text)
        font.pixelSize: 15
        validator: IntValidator { bottom: root.minimum; top: root.maximum }
        Accessible.name: root.accessibleName
        onEditingFinished: root.submit(text)
        background: Rectangle {
            color: root.theme.dohna ? "transparent" : root.theme.inputSurface
            border.color: editor.activeFocus ? root.theme.accent : root.theme.lineStrong
            border.width: root.theme.dohna ? 0 : editor.activeFocus ? 2 : 1
        }

        Text {
            id: suffixLabel
            objectName: "numberStepperSuffix"
            visible: root.suffix.length > 0 && !root.compact
            x: editor.leftPadding
               + Math.max(0, (editor.width
                              - editor.leftPadding
                              - editor.rightPadding
                              - editor.contentWidth) / 2)
               + editor.contentWidth
               + root.suffixSpacing
            anchors.verticalCenter: parent.verticalCenter
            text: root.suffix
            color: root.theme.textDim
            font.family: root.theme.monoFontFor(text)
            font.pixelSize: 13
        }
    }

    PrismButton {
        id: increaseButton
        objectName: "numberStepperIncrease"
        theme: root.theme
        text: "+"
        implicitWidth: root.theme.refraDark && root.rowTitle.length > 0 ? 30 : root.compact ? 32 : 42
        Layout.preferredWidth: implicitWidth
        enabled: root.enabled && root.value < root.maximum
        dohnaEmbedded: root.theme.dohna
        onClicked: root.submit(root.value + root.stepSize)
    }
    }

    SettingHint {
        theme: root.theme
        target: root
        description: root.settingDescription
        settingKey: root.settingKey
    }
}
