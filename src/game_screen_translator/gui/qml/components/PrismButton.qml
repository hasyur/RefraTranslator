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
    property real dohnaImpact: 0
    // NumberStepper embeds its two actions in one shared Dohna surface.  The
    // defaults keep every existing Prism and standalone Dohna button intact.
    property bool dohnaEmbedded: false
    property bool dohnaGroupFrame: false
    property bool dohnaGroupVisible: dohnaGroupFrame
    property bool dohnaGroupEnabled: true
    property real dohnaGroupWidth: width
    property real dohnaGroupHeight: height
    property bool dohnaGroupHovered: hovered
    property bool dohnaGroupPressed: down
    property real dohnaGroupDivider1X: -1
    property real dohnaGroupDivider2X: -1

    implicitWidth: Math.max(112, contentItem.implicitWidth + 30)
    implicitHeight: root.theme.dohna && root.navigation ? 50 : 42
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    scale: root.theme.dohna ? 1 : (root.down ? 0.994 : root.hovered && root.enabled ? 1.004 : 1)

    Behavior on scale {
        NumberAnimation { duration: root.theme.fast; easing.type: Easing.OutCubic }
    }

    onPressedChanged: {
        if (!root.theme.dohna || root.theme.reducedMotion) {
            dohnaPressPulse.stop()
            dohnaImpact = 0
        } else if (root.pressed) {
            dohnaPressPulse.restart()
        } else {
            dohnaPressPulse.stop()
            dohnaImpact = 0
        }
    }

    Connections {
        target: root.theme
        function onDohnaChanged() {
            if (!root.theme.dohna) {
                dohnaPressPulse.stop()
                root.dohnaImpact = 0
            }
        }
        function onReducedMotionChanged() {
            if (root.theme.reducedMotion) {
                dohnaPressPulse.stop()
                root.dohnaImpact = 0
            }
        }
    }

    contentItem: Text {
        objectName: "prismButtonLabel"
        text: root.text
        color: !root.enabled ? root.theme.textDim
              : root.tone === "danger" ? root.theme.danger
              : root.theme.dohna && root.navigation
                && (root.hovered || root.down || root.activeFocus) ? root.theme.ink
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
        clip: !root.theme.dohna
        transform: Translate {
            y: root.theme.dohna ? root.dohnaImpact * 2 : 0
        }
        color: !root.enabled ? "transparent"
              : root.theme.dohna && root.navigation ? "transparent"
              : root.theme.dohna ? "transparent"
              : root.primary ? Qt.rgba(root.theme.accent.r, root.theme.accent.g, root.theme.accent.b, root.theme.dark ? 0.22 : 0.14)
              : root.down ? Qt.rgba(root.theme.accent.r, root.theme.accent.g, root.theme.accent.b, 0.12)
              : root.hovered ? Qt.rgba(root.theme.accent.r, root.theme.accent.g, root.theme.accent.b, 0.065)
              : root.quiet ? "transparent"
              : root.theme.glassRaised
        border.color: root.theme.dohna ? "transparent"
                    : root.activeFocus ? root.theme.accent
                    : root.tone === "danger" ? root.theme.danger
                    : root.primary && root.theme.dohna ? root.theme.selectionEdge
                    : root.primary ? root.theme.accent
                    : root.theme.lineStrong
        border.width: root.theme.dohna ? 0 : (root.activeFocus ? 2 : root.primary ? 1.5 : 1)
        opacity: root.dohnaGroupFrame
                 ? (root.dohnaGroupEnabled ? 1 : 0.55)
                 : root.enabled ? 1 : 0.55

        Behavior on color { ColorAnimation { duration: root.theme.ui } }
        Behavior on border.color { ColorAnimation { duration: root.theme.ui } }

        Rectangle {
            objectName: "prismButtonLightEdge"
            visible: !root.theme.dohna
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: root.primary ? 2 : 1
            color: root.primary && root.theme.dohna ? root.theme.selectionEdge
                 : root.primary ? root.theme.accent : root.theme.lineStrong
            opacity: root.enabled ? (root.primary || root.hovered || root.activeFocus ? 0.9 : 0.24) : 0.15
            Behavior on opacity { NumberAnimation { duration: root.theme.ui } }
        }

        Rectangle {
            objectName: "prismButtonDohnaShadow"
            visible: root.theme.dohna
                     && root.enabled
                     && !root.dohnaEmbedded
                     && !root.dohnaGroupFrame
            x: 5
            y: 5
            width: parent.width
            height: parent.height
            color: root.theme.stageShadow
            z: -1
        }

        Shape {
            objectName: "prismNavigationCut"
            visible: root.theme.dohna && root.navigation
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                strokeColor: root.primary || root.activeFocus ? root.theme.selectionEdge
                            : root.hovered ? root.theme.ink : "transparent"
                strokeWidth: root.primary || root.activeFocus || root.hovered ? 2 : 0
                fillColor: root.primary
                           ? root.theme.accent
                           : root.hovered ? root.theme.violet
                                          : "transparent"
                startX: 0
                startY: 0
                PathLine { x: root.width - 13; y: 0 }
                PathLine { x: root.width; y: root.height }
                PathLine { x: 0; y: root.height }
                PathLine { x: 0; y: 0 }
            }
        }

        Shape {
            objectName: "prismButtonDohnaCut"
            visible: root.theme.dohna
                     && root.enabled
                     && !root.navigation
                     && !root.dohnaEmbedded
                     && !root.dohnaGroupFrame
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                strokeColor: root.activeFocus || root.down ? root.theme.selectionEdge : root.theme.ink
                strokeWidth: root.activeFocus || root.down ? 3 : 2
                fillColor: root.primary ? root.theme.accent
                           : root.down ? root.theme.accent
                           : root.hovered ? root.theme.violet
                           : root.theme.white
                startX: 0
                startY: 0
                PathLine { x: root.width - 14; y: 0 }
                PathLine { x: root.width; y: root.height }
                PathLine { x: 0; y: root.height }
                PathLine { x: 0; y: 0 }
            }
        }

        Shape {
            objectName: "prismButtonDohnaGroupShadow"
            visible: root.theme.dohna && root.dohnaGroupVisible
            x: 5
            y: 5
            width: root.dohnaGroupWidth
            height: root.dohnaGroupHeight
            z: -2
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                strokeColor: "transparent"
                fillColor: root.theme.stageShadow
                startX: 0
                startY: 0
                PathLine { x: root.dohnaGroupWidth - 14; y: 0 }
                PathLine { x: root.dohnaGroupWidth; y: root.dohnaGroupHeight }
                PathLine { x: 0; y: root.dohnaGroupHeight }
                PathLine { x: 0; y: 0 }
            }
        }

        Shape {
            objectName: "prismButtonDohnaGroupSurface"
            visible: root.theme.dohna && root.dohnaGroupVisible
            width: root.dohnaGroupWidth
            height: root.dohnaGroupHeight
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                objectName: "prismButtonDohnaGroupPath"
                strokeColor: root.dohnaGroupPressed || root.activeFocus
                             ? root.theme.selectionEdge : root.theme.ink
                strokeWidth: root.dohnaGroupPressed || root.activeFocus ? 3 : 2
                fillColor: root.dohnaGroupPressed
                           ? root.theme.accent
                           : root.dohnaGroupHovered
                             ? root.theme.violet
                             : root.theme.white
                startX: 0
                startY: 0
                PathLine { x: root.dohnaGroupWidth - 14; y: 0 }
                PathLine { x: root.dohnaGroupWidth; y: root.dohnaGroupHeight }
                PathLine { x: 0; y: root.dohnaGroupHeight }
                PathLine { x: 0; y: 0 }
            }
            opacity: root.dohnaGroupEnabled ? 1 : 0.55
        }

        Rectangle {
            objectName: "prismButtonDohnaGroupDivider1"
            visible: root.theme.dohna
                     && root.dohnaGroupVisible
                     && root.dohnaGroupDivider1X >= 0
            x: root.dohnaGroupDivider1X
            y: 4
            width: 2
            height: Math.max(0, root.dohnaGroupHeight - 8)
            color: root.theme.ink
        }

        Rectangle {
            objectName: "prismButtonDohnaGroupDivider2"
            visible: root.theme.dohna
                     && root.dohnaGroupVisible
                     && root.dohnaGroupDivider2X >= 0
            x: root.dohnaGroupDivider2X
            y: 4
            width: 2
            height: Math.max(0, root.dohnaGroupHeight - 8)
            color: root.theme.ink
        }

        Shape {
            objectName: "prismButtonDohnaFocusSlash"
            visible: root.theme.dohna
                     && root.enabled
                     && !root.dohnaEmbedded
                     && !root.dohnaGroupFrame
                     && (root.hovered || root.activeFocus || root.down)
            x: Math.max(0, root.width - 24)
            y: -4
            width: 30
            height: 13
            rotation: -8
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                strokeColor: root.theme.ink
                strokeWidth: root.down ? 2 : 1
                fillColor: root.down ? root.theme.accent : root.theme.violet
                startX: 2
                startY: 1
                PathLine { x: 25; y: 0 }
                PathLine { x: 30; y: 11 }
                PathLine { x: 6; y: 12 }
                PathLine { x: 2; y: 1 }
            }
        }
    }

    SettingHint {
        theme: root.theme
        target: root
        description: root.settingDescription
        settingKey: root.settingKey
    }

    SequentialAnimation {
        id: dohnaPressPulse
        PropertyAction { target: root; property: "dohnaImpact"; value: 1 }
        NumberAnimation {
            target: root
            property: "dohnaImpact"
            to: 0
            duration: root.theme.popPressMotion
            easing.type: Easing.OutBack
        }
    }
}
