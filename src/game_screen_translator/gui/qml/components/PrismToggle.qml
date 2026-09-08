import QtQuick
import QtQuick.Controls

CheckBox {
    id: root

    required property var theme

    implicitHeight: 42
    spacing: 11
    focusPolicy: Qt.StrongFocus

    indicator: Rectangle {
        implicitWidth: 34
        implicitHeight: 18
        x: 0
        y: (root.height - height) / 2
        color: root.checked
               ? Qt.rgba(root.theme.accent.r, root.theme.accent.g, root.theme.accent.b, 0.24)
               : "transparent"
        border.color: root.activeFocus || root.checked ? root.theme.accent : root.theme.lineStrong
        border.width: root.activeFocus ? 2 : 1

        Rectangle {
            width: 8
            height: 8
            x: root.checked ? parent.width - width - 5 : 5
            y: (parent.height - height) / 2
            color: root.checked ? root.theme.accent : root.theme.textDim
            Behavior on x { NumberAnimation { duration: root.theme.fast } }
        }
    }

    contentItem: Text {
        leftPadding: root.indicator.width + root.spacing
        text: root.text
        color: root.enabled ? root.theme.text : root.theme.textDim
        font.family: root.theme.uiFontFor(text)
        font.pixelSize: 13
        verticalAlignment: Text.AlignVCenter
        wrapMode: Text.WordWrap
    }
}
