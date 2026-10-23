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
        y: root.topPadding + root.availableHeight / 2 - ( 4 )
        implicitWidth: 200
        implicitHeight: 8 
        width: root.availableWidth
        height: 8 
        Rectangle {
            anchors.fill: parent
            color: root.theme.inputTrack
            border.color: root.activeFocus ? root.theme.selectionEdge : root.theme.lineStrong
            border.width: 2 }

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
        radius: 2
        rotation: (root.pressed ? -12 : -7) 
        color: root.pressed
               ? root.theme.violet
               : root.pressed ? root.theme.accent : root.theme.inkRaised
        border.color: root.theme.selectionEdge
                      
        border.width: 3 }

    SettingHint {
        theme: root.theme
        target: root
        description: root.settingDescription
        settingKey: root.settingKey
    }
}
