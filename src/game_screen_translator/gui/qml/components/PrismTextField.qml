import QtQuick
import QtQuick.Controls

TextField {
    id: root

    required property var theme
    property string accessibleName: ""

    Accessible.name: root.accessibleName.length > 0 ? root.accessibleName : root.placeholderText

    implicitHeight: 42
    leftPadding: 12
    rightPadding: 12
    color: root.theme.text
    placeholderTextColor: root.theme.textDim
    selectionColor: root.theme.accent
    selectedTextColor: root.theme.ink
    font.family: root.theme.uiFontFor(text.length > 0 ? text : placeholderText)
    font.pixelSize: 13

    background: Rectangle {
        color: root.theme.dark ? "#8f0b1016" : "#b8eef2f3"
        border.color: root.activeFocus ? root.theme.accent : root.theme.lineStrong
        border.width: root.activeFocus ? 2 : 1
    }
}
