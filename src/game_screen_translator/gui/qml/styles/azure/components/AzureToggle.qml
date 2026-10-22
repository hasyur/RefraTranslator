import QtQuick
import QtQuick.Controls

Switch {
    id: control
    required property var theme
    property string description: ""
    implicitHeight: 48
    leftPadding: 0
    rightPadding: 4
    spacing: 10
    Accessible.description: description

    contentItem: Text {
        leftPadding: 0
        rightPadding: control.indicator.width + control.spacing
        text: control.text
        color: control.enabled ? control.theme.text : control.theme.textDim
        font.family: control.theme.uiFontFor(text)
        font.pixelSize: 14
        verticalAlignment: Text.AlignVCenter
        wrapMode: Text.WordWrap
    }
    indicator: Rectangle {
        x: control.width - width - control.rightPadding
        y: (control.height - height) / 2
        width: 42
        height: 24
        radius: 12
        color: control.checked ? control.theme.accent : control.theme.inputTrack
        border.color: control.visualFocus ? control.theme.spectrum
                    : control.checked ? control.theme.accent : control.theme.lineStrong
        border.width: control.visualFocus ? 3 : 1
        Rectangle {
            x: control.checked ? parent.width - width - 3 : 3
            y: 3
            width: 18
            height: 18
            radius: 9
            color: "#ffffff"
            Behavior on x { NumberAnimation { duration: control.theme.reducedMotion ? 0 : 120 } }
        }
    }
}
