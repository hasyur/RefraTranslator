import QtQuick
import QtQuick.Controls

TextField {
    id: control
    required property var theme
    implicitHeight: 42
    leftPadding: 11
    rightPadding: 11
    color: theme.text
    selectionColor: theme.accent
    selectedTextColor: "#ffffff"
    placeholderTextColor: theme.textDim
    font.family: theme.uiFontFor(text)
    font.pixelSize: 14
    background: Rectangle {
        color: control.enabled ? control.theme.inputSurface : control.theme.inputTrack
        border.color: control.activeFocus ? control.theme.accent
                    : control.readOnly ? control.theme.line : control.theme.lineStrong
        border.width: control.activeFocus ? 2 : 1
        radius: 0
    }
}
