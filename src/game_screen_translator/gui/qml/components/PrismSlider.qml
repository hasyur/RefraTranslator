import QtQuick
import QtQuick.Controls

Slider {
    id: root

    required property var theme
    property string accessibleName: ""

    Accessible.name: accessibleName
    implicitHeight: 34
    hoverEnabled: true
    live: true
    snapMode: Slider.SnapAlways

    background: Item {
        x: root.leftPadding
        y: root.topPadding + root.availableHeight / 2 - 3
        implicitWidth: 200
        implicitHeight: 6
        width: root.availableWidth
        height: 6

        Rectangle {
            anchors.fill: parent
            color: root.theme.dark ? "#7a182333" : "#b8e3e9eb"
            border.color: root.activeFocus ? root.theme.accent : root.theme.lineStrong
            border.width: root.activeFocus ? 2 : 1
        }

        Rectangle {
            width: parent.width * root.visualPosition
            height: parent.height
            color: root.theme.accent
        }
    }

    handle: Rectangle {
        x: root.leftPadding
           + root.visualPosition * (root.availableWidth - width)
        y: root.topPadding + root.availableHeight / 2 - height / 2
        implicitWidth: 20
        implicitHeight: 20
        radius: width / 2
        color: root.pressed ? root.theme.accent : root.theme.inkRaised
        border.color: root.theme.accent
        border.width: root.activeFocus || root.hovered ? 3 : 2
    }
}
