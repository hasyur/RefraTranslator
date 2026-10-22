import QtQuick
import QtQuick.Controls
import QtQuick.Shapes

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
        color: "transparent"
        border.color: control.visualFocus ? control.theme.spectrum
                    : control.primary ? control.theme.accent
                    : control.tone === "danger" ? control.theme.danger
                    : control.quiet ? "transparent" : control.theme.lineStrong
        border.width: control.visualFocus ? 3
                    : control.angular || control.primary || control.quiet ? 0 : 1

        Shape {
            id: angularSurface
            anchors.fill: parent
            antialiasing: true
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                fillColor: control.angular && !control.quiet
                         ? control.theme.spectrum : "transparent"
                strokeWidth: 0
                startX: 4; startY: 4
                PathLine { x: control.width - 8; y: 4 }
                PathLine { x: control.width + 4; y: control.height - 6 }
                PathLine { x: control.width - 6; y: control.height + 4 }
                PathLine { x: 4; y: control.height + 4 }
                PathLine { x: 4; y: 4 }
            }
            ShapePath {
                fillColor: !control.enabled ? control.theme.inputTrack
                         : control.primary ? control.theme.accent
                         : control.onAccent ? (control.hovered || control.visualFocus ? "#245fe8" : "transparent")
                         : control.hovered || control.visualFocus ? control.theme.white
                         : control.quiet ? "transparent" : control.theme.inputSurface
                strokeColor: control.visualFocus ? control.theme.spectrum : "transparent"
                strokeWidth: control.visualFocus ? 3 : 0
                startX: control.angular ? 8 : 0; startY: 0
                PathLine { x: control.width - (control.angular ? 12 : 0); y: 0 }
                PathLine { x: control.width; y: control.angular ? control.height - 10 : control.height }
                PathLine { x: control.width - (control.angular ? 10 : 0); y: control.height }
                PathLine { x: 0; y: control.height }
                PathLine { x: 0; y: control.angular ? 8 : 0 }
                PathLine { x: control.angular ? 8 : 0; y: 0 }
            }
        }
    }

    scale: pressed && !theme.reducedMotion ? 0.985 : 1
    Behavior on scale { NumberAnimation { duration: control.theme.reducedMotion ? 0 : 90 } }
}
