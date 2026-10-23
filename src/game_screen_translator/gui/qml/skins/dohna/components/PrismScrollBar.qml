import QtQuick
import QtQuick.Controls.Basic

ScrollBar {
    id: control

    required property var theme
    objectName: root.theme.active ? ("prismScrollBar") : ""
    // Reserve this lane in the content even when it fits, avoiding reflow
    // as the scroll range or window size changes.
    readonly property real contentInset: implicitWidth + 8
    implicitWidth: 12
    padding: 0
    topPadding: 2
    bottomPadding: 2
    policy: ScrollBar.AsNeeded
    visible: policy === ScrollBar.AlwaysOn || (policy === ScrollBar.AsNeeded && size < 1)
    hoverEnabled: true
    minimumSize: Math.min(1, 28 / Math.max(1, height))

    background: Item {
        Rectangle {
            objectName: root.theme.active ? ("prismScrollTrack") : ""
            anchors.horizontalCenter: parent.horizontalCenter
            y: control.topPadding
            height: control.availableHeight
            width: 6
            color: control.theme.inputTrack
        }
    }

    contentItem: Item {
        Rectangle {
            objectName: root.theme.active ? ("prismScrollThumb") : ""
            anchors.horizontalCenter: parent.horizontalCenter
            height: parent.height
            width: control.pressed || control.hovered ? 6 : 4
            radius: 0
            color: control.pressed || control.hovered
                   ? control.theme.accent : control.theme.textDim
        }
    }
}
