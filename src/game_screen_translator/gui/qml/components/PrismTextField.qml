import QtQuick
import QtQuick.Shapes
import QtQuick.Controls

TextField {
    id: root

    required property var theme
    property string accessibleName: ""
    property string settingDescription: ""
    property string settingKey: ""

    Accessible.name: root.accessibleName.length > 0 ? root.accessibleName : root.placeholderText

    implicitHeight: 42
    leftPadding: 12
    rightPadding: 12
    color: root.theme.text
    placeholderTextColor: root.theme.textDim
    selectionColor: root.theme.accent
    selectedTextColor: root.theme.ink
    font.family: root.theme.uiFontFor(text.length > 0 ? text : placeholderText)
    font.pixelSize: 13

    background: Rectangle {
        objectName: "prismTextFieldBackground"
        clip: !root.theme.dohna
        color: root.theme.inputSurface
        border.color: root.activeFocus ? root.theme.selectionEdge : root.theme.lineStrong
        border.width: root.theme.dohna || root.activeFocus ? 2 : 1

        Rectangle {
            objectName: "prismTextFieldDohnaShadow"
            visible: root.theme.dohna
            x: 4
            y: 4
            width: parent.width
            height: parent.height
            color: root.theme.stageShadow
            z: -1
        }

        Shape {
            objectName: "prismTextFieldDohnaCorner"
            visible: root.theme.dohna && root.activeFocus
            anchors.right: parent.right
            anchors.top: parent.top
            width: 36
            height: 16
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                strokeColor: root.theme.ink
                strokeWidth: 1
                fillColor: root.theme.violet
                startX: 2
                startY: 0
                PathLine { x: 33; y: 0 }
                PathLine { x: 36; y: 14 }
                PathLine { x: 8; y: 16 }
                PathLine { x: 2; y: 0 }
            }
        }
    }

    SettingHint {
        theme: root.theme
        target: root
        description: root.settingDescription
        settingKey: root.settingKey
    }
}
