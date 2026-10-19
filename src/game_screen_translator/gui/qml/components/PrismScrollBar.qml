import QtQuick
import QtQuick.Controls.Basic

ScrollBar {
    id: control

    required property var theme
    objectName: "prismScrollBar"
    // Reserve this lane in the content even when it fits, avoiding reflow
    // as the scroll range or window size changes.
    readonly property real contentInset: implicitWidth + 8
    implicitWidth: 12
    padding: 0
    policy: ScrollBar.AsNeeded
    hoverEnabled: true
    minimumSize: Math.min(1, 28 / Math.max(1, height))

    background: Item {
        Rectangle {
            anchors.horizontalCenter: parent.horizontalCenter
            height: parent.height
            width: 1
            color: control.theme.line
        }
    }

    contentItem: Item {
        Rectangle {
            objectName: "prismScrollThumb"
            anchors.horizontalCenter: parent.horizontalCenter
            height: parent.height
            width: control.pressed || control.hovered ? 6 : 4
            radius: 0
            color: control.pressed || control.hovered
                   ? control.theme.accent : control.theme.textDim
        }
    }
}
