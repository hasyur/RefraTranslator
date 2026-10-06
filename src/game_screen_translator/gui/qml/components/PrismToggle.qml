import QtQuick
import QtQuick.Controls
import QtQuick.Shapes

CheckBox {
    id: root

    required property var theme
    property string settingDescription: ""
    property string settingKey: ""

    implicitHeight: 42
    spacing: 11
    focusPolicy: Qt.StrongFocus

    indicator: Item {
        implicitWidth: 34
        implicitHeight: 18
        x: 0
        y: (root.height - height) / 2

        Rectangle {
            objectName: "prismToggleTrack"
            visible: !root.theme.dohna
            anchors.fill: parent
            color: root.checked
                   ? Qt.rgba(root.theme.accent.r, root.theme.accent.g, root.theme.accent.b, 0.24)
                   : "transparent"
            border.color: root.activeFocus || root.checked ? root.theme.accent : root.theme.lineStrong
            border.width: root.activeFocus ? 2 : 1
        }

        Shape {
            id: dohnaToggleCut
            objectName: "prismToggleDohnaCut"
            visible: root.theme.dohna
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                strokeColor: root.activeFocus || root.checked ? root.theme.selectionEdge : root.theme.ink
                strokeWidth: root.activeFocus ? 3 : 2
                fillColor: root.checked ? root.theme.accent : root.theme.paper
                startX: 2
                startY: 2
                PathLine {
                    objectName: "prismToggleDohnaPathTopRight"
                    x: dohnaToggleCut.width - 5
                    y: 0
                }
                PathLine {
                    objectName: "prismToggleDohnaPathBottomRight"
                    x: dohnaToggleCut.width
                    y: dohnaToggleCut.height - 3
                }
                PathLine {
                    objectName: "prismToggleDohnaPathBottomLeft"
                    x: 4
                    y: dohnaToggleCut.height
                }
                PathLine { x: 2; y: 2 }
            }
        }

        Rectangle {
            objectName: "prismToggleKnob"
            visible: !root.theme.dohna
            width: 8
            height: 8
            x: root.checked ? parent.width - width - 5 : 5
            y: (parent.height - height) / 2
            color: root.checked ? root.theme.accent : root.theme.textDim
            Behavior on x { NumberAnimation { duration: root.theme.fast } }
        }

        Rectangle {
            objectName: "prismToggleDohnaKnob"
            visible: root.theme.dohna
            width: 9
            height: 9
            x: root.checked ? parent.width - width - 5 : 5
            y: (parent.height - height) / 2
            rotation: root.checked ? -7 : 5
            color: root.checked ? root.theme.violet : root.theme.ink
            border.color: root.theme.ink
            border.width: 1
            Behavior on x { NumberAnimation { duration: root.theme.popPressMotion } }
        }
    }

    contentItem: Text {
        leftPadding: root.indicator.width + root.spacing
        text: root.text
        color: root.enabled ? root.theme.text : root.theme.textDim
        font.family: root.theme.uiFontFor(text)
        font.pixelSize: 13
        verticalAlignment: Text.AlignVCenter
        wrapMode: Text.WordWrap
    }

    SettingHint {
        theme: root.theme
        target: root
        description: root.settingDescription
        settingKey: root.settingKey
    }
}
