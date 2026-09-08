import QtQuick
import QtQuick.Controls

Button {
    id: root

    required property var theme
    property bool primary: false
    property bool quiet: false
    property string tone: "neutral"

    implicitWidth: Math.max(112, contentItem.implicitWidth + 30)
    implicitHeight: 42
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    scale: root.down ? 0.975 : root.hovered && root.enabled ? 1.012 : 1

    Behavior on scale {
        NumberAnimation { duration: root.theme.fast; easing.type: Easing.OutCubic }
    }

    contentItem: Text {
        objectName: "prismButtonLabel"
        text: root.text
        color: !root.enabled ? root.theme.textDim
              : root.tone === "danger" ? root.theme.danger
              : root.primary ? root.theme.ink
              : root.theme.text
        font.family: root.theme.monoFontFor(text)
        font.pixelSize: 11
        font.weight: Font.DemiBold
        font.letterSpacing: 0.9
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    background: Rectangle {
        id: buttonSurface
        clip: true
        color: !root.enabled ? "transparent"
              : root.primary ? root.theme.accent
              : root.down ? Qt.rgba(root.theme.accent.r, root.theme.accent.g, root.theme.accent.b, 0.16)
              : root.hovered ? Qt.rgba(root.theme.accent.r, root.theme.accent.g, root.theme.accent.b, 0.09)
              : root.quiet ? "transparent"
              : root.theme.glassRaised
        border.color: root.activeFocus ? root.theme.accent
                    : root.tone === "danger" ? root.theme.danger
                    : root.primary ? root.theme.accent
                    : root.theme.lineStrong
        border.width: root.activeFocus ? 2 : 1
        opacity: root.enabled ? 1 : 0.55

        Behavior on color { ColorAnimation { duration: root.theme.fast } }

        Rectangle {
            width: parent.width * 0.48
            height: parent.height * 1.8
            x: root.down ? parent.width * 0.72 : -width
            y: -parent.height * 0.4
            rotation: -18
            color: Qt.rgba(root.theme.text.r, root.theme.text.g, root.theme.text.b, 0.12)
            opacity: root.primary || root.hovered ? 1 : 0
            Behavior on x { NumberAnimation { duration: root.theme.ui; easing.type: Easing.OutCubic } }
            Behavior on opacity { NumberAnimation { duration: root.theme.fast } }
        }
    }
}
