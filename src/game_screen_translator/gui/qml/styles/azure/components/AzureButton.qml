import QtQuick
import QtQuick.Controls

Button {
    id: control
    property var theme
    property bool primary: false
    property bool quiet: false
    property bool onAccent: false
    property string tone: "normal"
    property bool angular: true
    hoverEnabled: true
    implicitHeight: 42
    padding: 12
    font.family: theme ? theme.uiFontFor(text) : "Segoe UI"
    font.pixelSize: 14
    font.weight: primary ? Font.DemiBold : Font.Medium

    contentItem: Text {
        text: control.text
        color: !control.enabled ? control.theme.textDim
             : control.onAccent ? "#ffffff"
             : control.primary ? control.theme.buttonPrimaryText
             : (control.tone === "danger" ? control.theme.danger : control.theme.text)
        font: control.font
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
        opacity: 1
    }

    background: Rectangle {
        color: !control.enabled ? control.theme.inputTrack
             : control.primary ? control.theme.accent
             : control.onAccent ? (control.hovered || control.visualFocus ? "#245fe8" : "transparent")
             : control.hovered || control.visualFocus ? control.theme.white
             : control.quiet ? "transparent" : control.theme.inputSurface
        border.color: control.visualFocus ? control.theme.spectrum
                    : control.primary ? control.theme.accent
                    : control.tone === "danger" ? control.theme.danger
                    : control.quiet ? "transparent" : control.theme.lineStrong
        border.width: control.visualFocus ? 3
                    : control.primary || control.quiet ? 0 : 1
    }

    scale: pressed && !theme.reducedMotion ? 0.985 : 1
    Behavior on scale { NumberAnimation { duration: control.theme.reducedMotion ? 0 : 90 } }
}
