import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

RowLayout {
    id: root

    required property var theme
    property int value: 0
    property int minimum: 0
    property int maximum: 100
    property int stepSize: 1
    property string suffix: ""
    property string accessibleName: ""
    readonly property real compactWidth: suffix.length > 0 ? 200 : 176
    readonly property real suffixSpacing: 5
    signal edited(int value)

    spacing: 0
    implicitWidth: compactWidth
    implicitHeight: 42
    Layout.minimumWidth: compactWidth
    Layout.preferredWidth: compactWidth
    Layout.maximumWidth: compactWidth

    function submit(candidate) {
        const numeric = Math.max(minimum, Math.min(maximum, Number(candidate)))
        edited(Math.round(numeric))
    }

    PrismButton {
        objectName: "numberStepperDecrease"
        theme: root.theme
        text: "−"
        implicitWidth: 42
        Layout.preferredWidth: 42
        enabled: root.enabled && root.value > root.minimum
        onClicked: root.submit(root.value - root.stepSize)
    }

    TextField {
        id: editor
        objectName: "numberStepperEditor"
        Layout.fillWidth: true
        Layout.minimumWidth: root.suffix.length > 0 ? 116 : 92
        implicitHeight: 42
        text: String(root.value)
        color: root.theme.text
        clip: true
        leftPadding: 8
        rightPadding: suffixLabel.visible
                      ? 8 + suffixLabel.implicitWidth + root.suffixSpacing
                      : 8
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        font.family: root.theme.monoFontFor(text)
        font.pixelSize: 13
        validator: IntValidator { bottom: root.minimum; top: root.maximum }
        Accessible.name: root.accessibleName
        onEditingFinished: root.submit(text)
        background: Rectangle {
            color: root.theme.dark ? "#8f0b1016" : "#b8eef2f3"
            border.color: editor.activeFocus ? root.theme.accent : root.theme.lineStrong
            border.width: editor.activeFocus ? 2 : 1
        }

        Text {
            id: suffixLabel
            objectName: "numberStepperSuffix"
            visible: root.suffix.length > 0
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
            font.pixelSize: 11
        }
    }

    PrismButton {
        objectName: "numberStepperIncrease"
        theme: root.theme
        text: "+"
        implicitWidth: 42
        Layout.preferredWidth: 42
        enabled: root.enabled && root.value < root.maximum
        onClicked: root.submit(root.value + root.stepSize)
    }
}
