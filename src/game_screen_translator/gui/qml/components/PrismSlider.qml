import QtQuick
import QtQuick.Controls

Slider {
    id: root

    required property var theme
    property string accessibleName: ""
    property string settingDescription: ""
    property string settingKey: ""

    Accessible.name: accessibleName
    implicitHeight: 34
    hoverEnabled: true
    live: true
    snapMode: Slider.SnapAlways

    background: Item {
        x: root.leftPadding
        y: root.topPadding + root.availableHeight / 2 - (root.theme.dohna ? 4 : 3)
        implicitWidth: 200
        implicitHeight: root.theme.dohna ? 8 : 6
        width: root.availableWidth
        height: root.theme.dohna ? 8 : 6

        Rectangle {
            anchors.fill: parent
            color: root.theme.inputTrack
            border.color: root.activeFocus ? root.theme.selectionEdge : root.theme.lineStrong
            border.width: root.theme.dohna || root.activeFocus ? 2 : 1
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
        radius: root.theme.dohna ? 2 : width / 2
        rotation: root.theme.dohna ? (root.pressed ? -12 : -7) : 0
        color: root.pressed && root.theme.dohna
               ? root.theme.violet
               : root.pressed ? root.theme.accent : root.theme.inkRaised
        border.color: root.theme.dohna
                      ? root.theme.selectionEdge
                      : root.theme.accent
        border.width: root.theme.dohna ? 3 : (root.activeFocus || root.hovered ? 3 : 2)
    }

    SettingHint {
        theme: root.theme
        target: root
        description: root.settingDescription
        settingKey: root.settingKey
    }
}
