import QtQuick
import QtQuick.Controls
import QtQuick.Shapes

Button {
    id: root

    required property var theme
    property bool primary: false
    property string settingDescription: ""
    property string settingKey: ""
    property bool quiet: false
    property bool navigation: false
    property string tone: "neutral"

    implicitWidth: Math.max(112, contentItem.implicitWidth + 30)
    implicitHeight: root.theme.dohna && root.navigation ? 50 : 42
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    scale: root.down ? 0.994 : root.hovered && root.enabled ? 1.004 : 1

    Behavior on scale {
        NumberAnimation { duration: root.theme.fast; easing.type: Easing.OutCubic }
    }

    contentItem: Text {
        objectName: "prismButtonLabel"
        text: root.text
        color: !root.enabled ? root.theme.textDim
              : root.tone === "danger" ? root.theme.danger
              : root.theme.dohna && root.quiet ? root.theme.navigationText
              : root.primary ? (root.theme.dohna ? root.theme.ink : root.theme.text)
              : root.theme.text
        font.family: root.theme.monoFontFor(text)
        font.pixelSize: root.theme.dohna && root.navigation ? 12 : 11
        font.weight: root.theme.dohna && root.navigation ? Font.Bold : Font.DemiBold
        font.letterSpacing: 0.9
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        wrapMode: root.theme.dohna && root.navigation ? Text.WordWrap : Text.NoWrap
        lineHeight: root.theme.dohna && root.navigation ? 0.82 : 1
        elide: Text.ElideRight
    }

    background: Rectangle {
        id: buttonSurface
        clip: true
        color: !root.enabled ? "transparent"
              : root.theme.dohna && root.navigation ? "transparent"
              : root.primary && root.theme.dohna ? root.theme.accent
              : root.primary ? Qt.rgba(root.theme.accent.r, root.theme.accent.g, root.theme.accent.b, root.theme.dark ? 0.22 : 0.14)
              : root.down ? Qt.rgba(root.theme.accent.r, root.theme.accent.g, root.theme.accent.b, 0.12)
              : root.hovered ? Qt.rgba(root.theme.accent.r, root.theme.accent.g, root.theme.accent.b, 0.065)
              : root.quiet ? "transparent"
              : root.theme.glassRaised
        border.color: root.activeFocus ? root.theme.accent
                    : root.tone === "danger" ? root.theme.danger
                    : root.primary && root.theme.dohna ? root.theme.selectionEdge
                    : root.primary ? root.theme.accent
                    : root.theme.lineStrong
        border.width: root.activeFocus ? 2 : root.primary ? 1.5 : 1
        opacity: root.enabled ? 1 : 0.55

        Behavior on color { ColorAnimation { duration: root.theme.ui } }
        Behavior on border.color { ColorAnimation { duration: root.theme.ui } }

        Rectangle {
            objectName: "prismButtonLightEdge"
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: root.primary ? 2 : 1
            color: root.primary && root.theme.dohna ? root.theme.selectionEdge
                 : root.primary ? root.theme.accent : root.theme.lineStrong
            opacity: root.enabled ? (root.primary || root.hovered || root.activeFocus ? 0.9 : 0.24) : 0.15
            Behavior on opacity { NumberAnimation { duration: root.theme.ui } }
        }

        Shape {
            objectName: "prismNavigationCut"
            visible: root.theme.dohna && root.navigation
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                strokeColor: root.primary ? root.theme.selectionEdge : "transparent"
                strokeWidth: root.primary ? 2 : 0
                fillColor: root.primary
                           ? root.theme.accent
                           : root.hovered ? Qt.rgba(root.theme.white.r,
                                                    root.theme.white.g,
                                                    root.theme.white.b,
                                                    0.10)
                                          : "transparent"
                startX: 0
                startY: 0
                PathLine { x: root.width - 13; y: 0 }
                PathLine { x: root.width; y: root.height }
                PathLine { x: 0; y: root.height }
                PathLine { x: 0; y: 0 }
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
