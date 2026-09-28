import QtQuick
import QtQuick.Controls

Button {
    id: root

    required property var theme
    property bool primary: false
    property string settingDescription: ""
    property string settingKey: ""
    property bool quiet: false
    property string tone: "neutral"

    implicitWidth: Math.max(112, contentItem.implicitWidth + 30)
    implicitHeight: 42
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
              : root.primary ? root.theme.text
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
              : root.primary ? Qt.rgba(root.theme.accent.r, root.theme.accent.g, root.theme.accent.b, root.theme.dark ? 0.22 : 0.14)
              : root.down ? Qt.rgba(root.theme.accent.r, root.theme.accent.g, root.theme.accent.b, 0.12)
              : root.hovered ? Qt.rgba(root.theme.accent.r, root.theme.accent.g, root.theme.accent.b, 0.065)
              : root.quiet ? "transparent"
              : root.theme.glassRaised
        border.color: root.activeFocus ? root.theme.accent
                    : root.tone === "danger" ? root.theme.danger
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
            color: root.primary ? root.theme.accent : root.theme.lineStrong
            opacity: root.enabled ? (root.primary || root.hovered || root.activeFocus ? 0.9 : 0.24) : 0.15
            Behavior on opacity { NumberAnimation { duration: root.theme.ui } }
        }
    }

    SettingHint {
        theme: root.theme
        target: root
        description: root.settingDescription
        settingKey: root.settingKey
    }
}
