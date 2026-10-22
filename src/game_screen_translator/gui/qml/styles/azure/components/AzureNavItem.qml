import QtQuick
import QtQuick.Controls
import QtQuick.Shapes

Button {
    id: control
    required property var theme
    required property string number
    property bool selected: false
    property string code: ""
    property int selectedFontSize: 38
    property int idleFontSize: 20
    readonly property int fittedSelectedFontSize: Math.min(
        selectedFontSize,
        Math.max(18, Math.floor((Math.max(0, width - 47) / Math.max(1, text.length)) * 0.92)))
    hoverEnabled: true
    implicitWidth: 148
    implicitHeight: 62
    padding: 10
    Accessible.role: Accessible.PageTab
    Accessible.name: number + " " + text

    contentItem: Row {
        x: 8
        width: Math.max(0, control.width - 16)
        spacing: 9
        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: control.number
            color: control.selected ? control.theme.accent : control.theme.navigationTextDim
            font.family: control.theme.monoFontFor(text)
            font.pixelSize: control.selected ? 19 : 13
            font.weight: control.selected ? Font.Black : Font.DemiBold
        }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            width: Math.max(0, control.width - 47)
            text: control.text
            color: control.selected ? control.theme.ink : control.theme.navigationText
            font.family: control.theme.uiFontFor(text)
            font.pixelSize: control.selected ? control.fittedSelectedFontSize : control.idleFontSize
            font.weight: control.selected ? Font.Black : Font.Bold
            font.italic: true
            elide: Text.ElideRight
        }
    }

    background: Item {
        Shape {
            anchors.fill: parent
            antialiasing: true
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                fillColor: control.selected ? control.theme.spectrum : "transparent"
                strokeWidth: 0
                startX: 4; startY: 4
                PathLine { x: control.width - 11; y: 4 }
                PathLine { x: control.width + 2; y: control.height + 4 }
                PathLine { x: 15; y: control.height + 4 }
                PathLine { x: 4; y: 15 }
                PathLine { x: 4; y: 4 }
            }
            ShapePath {
                fillColor: control.selected ? "#f6f8ff"
                         : control.hovered || control.visualFocus ? "#203568" : "transparent"
                strokeColor: control.visualFocus ? control.theme.spectrum : "transparent"
                strokeWidth: control.visualFocus ? 2 : 0
                startX: control.selected ? 0 : 8
                startY: 0
                PathLine { x: control.width - 15; y: 0 }
                PathLine { x: control.width; y: control.height }
                PathLine { x: control.selected ? 12 : 8; y: control.height }
                PathLine { x: 0; y: control.selected ? 11 : 0 }
            }
        }
    }

    rotation: control.selected ? -8 : -5
    transformOrigin: Item.Center
    scale: control.selected ? 1.075 : 0.97
    Behavior on scale {
        NumberAnimation { duration: control.theme.reducedMotion ? 0 : 120; easing.type: Easing.OutCubic }
    }

    Rectangle {
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        width: 3
        height: control.selected ? 26 : 0
        color: control.theme.spectrum
        visible: control.selected
    }
    Rectangle {
        x: -2
        y: control.height * 0.48
        width: 9
        height: 3
        color: "#ff3153"
        visible: control.selected
    }
}
