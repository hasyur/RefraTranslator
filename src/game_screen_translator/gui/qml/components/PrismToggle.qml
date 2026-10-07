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
        id: toggleIndicator
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

        Item {
            objectName: "prismToggleDohnaArtwork"
            visible: root.theme.dohna
            x: -3
            y: -3
            width: toggleIndicator.width + 6
            height: toggleIndicator.height + 6
            // Supersample just the small artwork, preserving its display size
            // and leaving room for the outer stroke and antialiased fringe.
            layer.enabled: root.theme.dohna
            layer.smooth: true
            layer.textureSize: Qt.size(Math.ceil(width * 4), Math.ceil(height * 4))

            Shape {
                id: dohnaToggleCut
                objectName: "prismToggleDohnaCut"
                x: 3
                y: 3
                width: toggleIndicator.width
                height: toggleIndicator.height
                antialiasing: true
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
                objectName: "prismToggleDohnaKnob"
                antialiasing: true
                width: 9
                height: 9
                x: 3 + (root.checked ? toggleIndicator.width - width - 5 : 5)
                y: 3 + (toggleIndicator.height - height) / 2
                rotation: root.checked ? -7 : 5
                color: root.checked ? root.theme.violet : root.theme.ink
                border.color: root.theme.ink
                border.width: 1
                Behavior on x { NumberAnimation { duration: root.theme.popPressMotion } }
            }
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
